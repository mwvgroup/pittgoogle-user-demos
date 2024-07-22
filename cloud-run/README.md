# Cloud Run Tutorial

**Learning Goals**

1. Develop code to classify a live alert stream.
2. Containerize and deploy the code to Cloud Run.

**Prerequisites**

- Complete the [One-Time Setup for Cloud Run](tutorial/cloud-run/one-time-setup-for-cloud-run.md).

## Introduction

Google [Cloud Run](https://cloud.google.com/run/docs/overview/what-is-cloud-run) is a Google Cloud service that runs containers as HTTP endpoints.
It can be used to process an alert stream in real time.
The basic process is:

1. Pitt-Google Broker publishes an alert stream to Pub/Sub.

2. You write code to analyze a single alert.
   You package your code as a container image and deploy it to Cloud Run, specifying the Pitt-Google alert stream as the "trigger".

3. Pub/Sub automatically delivers the alerts in the trigger stream to your Cloud Run module as HTTP requests.
   Google manages the Cloud Run module for you, automatically scaling it up and down in response to the incoming alert rate.

This tutorial demonstrates how to complete step 2.
It uses the pre-written SuperNNova module that is included in this repo for demonstration.

## Environment Setup

1. Open a terminal. If you set up a conda environment during the one-time setup, activate it.
   Otherwise, make sure your environment variables are set and you've authenticated with ``gcloud auth`` (see [environment variables](https://mwvgroup.github.io/pittgoogle-client/overview/env-vars.html)).

2. Set the following additional environment variables.
   They will be used by both setup.sh and main.py.

```bash
# Choose your own testid. Lower case letters and numbers only.
export TESTID=mytest

# Choose a survey. Alerts from this survey will be used as classifier input. SuperNNova uses elasticc.
export SURVEY=elasticc

# Cloud Run expects the GOOGLE_CLOUD_PROJECT variable to be called PROJECT_ID.
export PROJECT_ID=$GOOGLE_CLOUD_PROJECT
```

3. Cd into your classifier directory.
   To follow the examples below, do `cd cloud-run/SuperNNova` from the repo root directory.

4. Install other dependencies as needed.
   For the SuperNNova example, you may want to run ``pip install -r requirements.txt``, but note that Cloud Run requires a special install of torch, so you will need to comment that out of the SuperNNova/requirements.txt file before installing and then separately run ``pip install torch``.

6. This tutorial uses both python and shell commands, so you may want to repeat steps 1-4 so you have a separate window for each.
   In the window you will use for python, run the setup code given below.

Imports and logging:

```python
import logging
import pittgoogle

import main  # assuming we're in a classifier directory containing a main.py file


# Optional: For more information about what's happening, set the the logging level to INFO.
logging.basicConfig(level="INFO")
```

## Example 1: Get an alert for input to the classifier

The following cloud resources will be created:

- Pub/Sub subscription to a Pitt-Google alert stream. These alerts will be the input to the classifier.
  To see which streams are available, see the [Pitt-Google Data Listings](https://mwvgroup.github.io/pittgoogle-client/listings.html).

Create a subscription and pull an alert to use for testing:

```python
# Subscription to "elasticc-loop" alert stream to be used as classifier input.
subscrip_in = pittgoogle.Subscription("elasticc-loop", schema_name=main.SCHEMA_IN)

# Make sure we can connect. If needed, this will
# create a subscription in your Google Cloud project
# to the alert stream published by Pitt-Google.
subscrip_in.touch()

# Pull one alert to test with.
alert = subscrip_in.pull_batch(max_messages=1)[0]
```

## Example 2: Write code to classify a single alert

This example shows how to develop code to classify an alert.
It uses the `alert` obtained in Example 1 and the pre-written code in the SuperNNova module's [main.py](tutorial/SuperNNova/main.py) file.

Everything in this section can be done locally; no cloud resources required.

Access the alert data and attributes:

```python
# Alert data as a dictionary (here we'll just view the keys)
alert.dict.keys()

# Alert data as a pandas DataFrame
alert.dataframe

# Alert attributes containing custom metadata set by the publisher (in this case, Pitt-Google Broker)
alert.attributes

# Publish time of the incoming message
alert.msg.publish_time
```

Now use the alert to develop code for your classifier module in main.py.

```python
# Here we'll format the data for SuperNNova and then run the classifier.
import supernnova.validation.validate_onthefly

snn_df = main._format_for_classifier(alert)
device = "cpu"
_, pred_probs = supernnova.validation.validate_onthefly.classify_lcs(snn_df, main.MODEL_PATH, device)

# Once the classifier code is added to main.py you can run the entire _classify function.
classifications = main._classify(alert)
```

## Example 3: Store the classification results

Once the alert is classified, you should store the results somewhere.
You can send data anywhere you can write the code for, in or out of Google Cloud.
You don't need any special permissions to send the data outside the cloud, but pay attention to related charges (particularly egress).

This example shows how to send results to other Google Cloud services:

- Publish the results to a new Pub/Sub stream.
    - Pub/Sub is helpful if you want to:
        a. send the alerts to another Cloud Run module for further processing.
        b. set up a listener outside Google Cloud to receive your classifications message stream (use [`pittgoogle.Consumer`](https://mwvgroup.github.io/pittgoogle-client/api/pubsub.html#pittgoogle.pubsub.Consumer)).

- Store the results in a BigQuery table.
    - BigQuery is helpful if you want to store the data in tabular format.
      (Note that Pub/Sub messages generally "live" for 10 days or less.)

This example uses the `alert` obtained in Example 1 and the pre-written code in the SuperNNova module's [main.py](tutorial/SuperNNova/main.py) that is included in this repo.

The following cloud resources will be created:

- BigQuery dataset and table to store your classifications.
- Pub/Sub topic to publish your classifications to.
- Pub/Sub subscription to the classifications topic so that we can read the published messages.

Setup

```python
# [TODO] Show how to create the cloud resources for main.TOPIC and main.TABLE

# First, classify the alert retrieved in Example 1.
classifications = main._classify(alert)
```

BigQuery

```python
# Store the classifications in the BigQuery table.
main.TABLE.insert_rows([classifications])  # Returns list of errors; empty list if none

# Query the table for the output classification.
# [TODO] add this code

# [TODO] Another option is Pub/Sub's BigQuery subscriptions. Show how to do this.
```

Pub/Sub

```python
# Create a new alert with the classifications to publish.
alert_out = main._create_outgoing_alert(alert, classifications)

alert_out.dict  # This will be the main content of the published message
alert_out.attributes  # These will be added to the published message as metadata

# Create a subscription to the output topic so we can
# pull the classifications after we publish and check that it worked.
subscrip_out = pittgoogle.Subscription(main.TOPIC.name, topic=main.TOPIC, schema_name=main.SCHEMA_OUT)
subscrip_out.touch()  # Make sure this exists before publishing

# If you have used this subscription before, you may want to
# purge it of messages to avoid unexpected results.
subscrip_out.purge()

# Publish the new alert.
main.TOPIC.publish(alert_out)  # Returns the id of the published message

# Pull the alert that we just published.
alert_out_pulled = subscrip_out.pull_batch(max_messages=1)[0]
# If all went well this should be the classification, same as alert_out.dict
alert_out_pulled.dict
```

## Example 4: Deploy to Cloud Run and test the module

This example shows how to containerize the classification code in [main.py](tutorial/SuperNNova/main.py) and deploy it Cloud Run, then test the module end to end.
You should be sure to test the code locally before doing this (see previous examples).

This example uses the `alert` obtained in Example 1 and the pre-written code in the [SuperNNova directory](tutorial/SuperNNova) that is included in this repo.
The code includes the following notable files:

<!-- [TODO]
- link to files
- add a summary doc for the deployment files
- Explain that it's best if the classifier code you want to run is published to pypi. -->

- *main.py* : Used in the examples above.
- *setup.sh* : Bash script that we will use to deploy the module. This script uses the `gcloud` and `bq` [command line tools](https://mwvgroup.github.io/pittgoogle-client/overview/adv-setup.html#command-line).
- *Dockerfile* : Defines the container environment that main.py will run in.
- *cloudbuild.yaml* : Instructions that will be used by Cloud Build to build the container and deploy it to Cloud Run.

See the comments in individual files for more instructions on creating them.

This example will create the following cloud resources:

- Cloud Run service that will run the classifier code.
  This will also create a Docker image in the Container Registry.
- BigQuery dataset and table to store the classifications.
- Pub/Sub topic to publish the classifications to.
- Pub/Sub subscription to the classifications topic so that we can read the messages produced by the module.

Deploy (bash recommended):

```bash
# [FIXME]
teardown=False
trigger_topic=raentest  # this must already exist. # [FIXME]

# Containerize the code and deploy the module, creating all related cloud resources.
# Make sure you've set the variables from the Setup section before running this.
./setup.sh $TESTID $SURVEY $teardown $trigger_topic $PROJECT_ID
```

Test (python):

```python
import os

# Connect to the trigger topic.
trigger_topic = pittgoogle.Topic("raentest")  # Use the same trigger topic name as above.
trigger_topic.touch()  # If this doesn't already exist then there was a problem with the deployment script

# Connect to the trigger subscription.
# In case something goes wrong, we will use this to purge the messages so we can try again.
trigger_subscrip = pittgoogle.Subscription(f"{trigger_topic.name}-{os.getenv('TESTID')}")
# trigger_subscrip.purge()

# Create a subscription to the output topic so we can
# pull the classification after we publish and check that it worked.
subscrip_out = pittgoogle.Subscription(main.TOPIC.name, topic=main.TOPIC, schema_name=main.SCHEMA_OUT)
subscrip_out.touch()  # Make sure this exists before publishing

# Publish the alert (retrieved in Example 1) to trigger the Cloud Run module.
trigger_topic.publish(alert)

# Pull the output alert containing the classification.
alert_out_pulled = subscrip_out.pull_batch()[0]
alert_out_pulled.dict

# Query the table for the output classification.
# [TODO] add this code

# If something went wrong and the module did not successfully process the alert,
# uncomment the next line to purge the alert out of the trigger subscription.
# trigger_subscrip.purge()

# If you need to fix code, uncomment the next line to delete the trigger subscription before re-deploying.
# trigger_subscrip.delete()
# Now run the setup.sh script again to re-deploy the module.
```

## Clean up

This example show how to delete the cloud resources created in previous examples

Delete resources using the setup script (bash recommended):

```bash
# [FIXME]
teardown=True
trigger_topic=raentest

./setup.sh $TESTID $SURVEY $teardown $trigger_topic $PROJECT_ID
# Follow the prompts to delete the resources.
```

Delete resources not managed by the setup script (python):

```python
subscrip_in.delete()
subscrip_out.delete()
```
