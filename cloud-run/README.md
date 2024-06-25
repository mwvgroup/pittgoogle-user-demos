# Cloud Run Tutorial

Learning Goal: Develop code to process (e.g., classify) a live alert stream and deploy it to Cloud Run.

Cloud Run is a Google Cloud service that runs containers as HTTP endpoints.
It can be used to process an alert stream as follows:

1. Pitt-Google Broker publishes an alert stream to Pub/Sub.
2. You write code to analyze a single alert.
   Package your code as a container image and deploy it to Cloud Run, specifying the Pitt-Google alert stream as the "trigger".
3. Pub/Sub automatically delivers the alerts in the trigger stream to your Cloud Run module as HTTP requests.
   Google manages the Cloud Run module for you, automatically scaling it up and down in response to the incoming alert rate.

This tutorial shows how to develop, deploy, and test the code in step 2.

The minimal set of cloud resources that will be required for this tutorial is:

- Pub/Sub subscription to a Pitt-Google alert stream (created below).
  These alerts will be the input to the classifier.

## Setup

Pre-requisite: [One-Time Setup for Cloud Run](one-time-setup-for-cloud-run.md)

Instructions:

1. Open a terminal. If you set up a conda environment during the one-time setup, activate it.

2. Make sure your environment variables are set and you've authenticated with ``gcloud auth`` (see [environment variables](https://mwvgroup.github.io/pittgoogle-client/overview/env-vars.html)).

3. Set the following additional environment variables.
   These will be used by both setup.sh and main.py.

```bash
# Choose your own testid. Lower case letters and numbers only.
export TESTID=mytest

# Choose a survey. Alerts from this survey will be used as classifier input.
export SURVEY=elasticc

# Cloud Run expects the GOOGLE_CLOUD_PROJECT variable to be called PROJECT_ID.
export PROJECT_ID=$GOOGLE_CLOUD_PROJECT
```

4. Cd into your classifier directory (``cd SuperNNova``).

5. Install other dependencies as needed.
   You may want to run ``pip install -r requirements.txt``, but note that Cloud Run requires a special install of torch, so you will need to comment that out of the SuperNNova/requirements.txt file before installing and then separately run ``pip install torch``.

6. This tutorial uses both python and shell commands, so you may want to repeat steps 1-4 so you have a separate window for each.
   In the window you will use for python, do:

```python
import logging
import pittgoogle

import main  # assuming we're in a classifier directory containing a main.py file


# Optional: For more information about what's happening, set the the logging level to INFO.
logging.basicConfig(level="INFO")

# Subscription to "elasticc-loop" alert stream to be used as classifier input.
subscrip_in = pittgoogle.Subscription("elasticc-loop", schema_name=main.SCHEMA_IN)

# Make sure we can connect. If needed, this will
# create a subscription in your Google Cloud project
# to the alert stream published by Pitt-Google.
subscrip_in.touch()

# Pull one alert to test with.
alert = subscrip_in.pull_batch(max_messages=1)[0]
```

## Example: Develop and Test a Classifier

Development and testing of a classifier or other analysis can be done locally.

The following cloud resources will be required:

- Pub/Sub subscription from the Setup section.

Here are some examples that use the `alert` (retrieved in the Setup section) to test the code in the SuperNNova module ([SuperNNova/main.py](SuperNNova/main.py)) included in this directory.

```python
# Access alert data as a dictionary (here we'll just view the keys)
alert.dict.keys()

# Access alert data as a pandas DataFrame
alert_df = alert.dataframe

# Run the entire _classify function
classifications = main._classify(alert)

# Run individual classification steps
import supernnova.validation.validate_onthefly

snn_df = main._format_for_classifier(alert)
device = "cpu"
_, pred_probs = supernnova.validation.validate_onthefly.classify_lcs(snn_df, main.MODEL_PATH, device)
```

## Example: Publish and Store the Classifications

This example tests the code in the SuperNNova module ([SuperNNova/main.py](SuperNNova/main.py)) that publishes the classification result to a Pub/Sub topic and stores it in a BigQuery table.

The following cloud resources will be required:

- Pub/Sub subscription from the Setup section.
- BigQuery dataset and table to store your classifications.
- Pub/Sub topic to publish your classifications to.
- Pub/Sub subscription to your topic so that we can check the classifications message after publishing.

Setup

```python
# [TODO] Show how to create the cloud resources for main.TOPIC and main.TABLE

# First, classify the alert retrieved in the Setup section.
classifications = main._classify(alert)
```

BigQuery

```python
# Store the classifications in the BigQuery table.
main.TABLE.insert_rows([classifications])  # Returns list of errors; empty list if none

# Query the table for the output classification.
# [TODO] add this code
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

## Example: Deploy to Cloud Run and Test

This example shows how to deploy the completed module to Cloud Run and test it end to end.
It is recommended to test locally using the previous examples before doing this.

The following cloud resources will be required:

- Pub/Sub subscription from the Setup section.
- Cloud Run service that will run the classifier code.
  This will also create a Docker image in the Container Registry.
- BigQuery dataset and table to store the classifications.
- Pub/Sub topic to publish the classifications to.
- Pub/Sub subscription to your topic so that we can check the classifications message after publishing.

Deploy:

```bash
# [FIXME]
teardown=False
trigger_topic=raentest

./setup.sh $TESTID $SURVEY $teardown $trigger_topic $PROJECT_ID
```

Test:

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

# Publish the alert (retrieved in the Setup section) to trigger the Cloud Run module.
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

## Example: Clean up

This example show how to delete the cloud resources created in previous examples

Delete resources using the setup script:

```bash
# [FIXME]
teardown=True
trigger_topic=raentest

./setup.sh $TESTID $SURVEY $teardown $trigger_topic $PROJECT_ID
# Follow the prompts to delete the resources.
```

Delete resources not managed by the setup script:

```python
subscrip_in.delete()
subscrip_out.delete()
```
