# pittgoogle-user

## Overview:
The Pitt-Google Broker is a cloud-based alert distribution service designed to provide near real-time processing of data from large-scale astronomical surveys like the [Legacy Survey of Space and Time](https://www.lsst.org). For its participation in the [DESC ELAsTiCC Challenge](https://portal.nersc.gov/cfs/lsst/DESC_TD_PUBLIC/ELASTICC/), the Pitt-Google Broker team developed this repo to process and classify alerts streamed by ELAsTiCC. Alerts are ingested into the data pipeline and classified using [SuperNNova](https://supernnova.readthedocs.io/en/latest/index.html). Supernovae classifications are published to a Pub/Sub topic and subsequently stored in BigQuery.

The deployment script in this repo can be used to create and delete some of the aforementioned Google Cloud Platform resources:
* A Pub/Sub topic & subscription used to:
    * Write SuperNNova classifications to a BigQuery table
    * Trigger a Cloud Run instance
* A BigQuery dataset & table used to:
    *  Store SuperNNova classifications
* A container image of the classifier module, which is then deployed using Cloud Run

## Tutorial: Creating a Cloud Run instance (via terminal)
* Begin a new terminal and initialize the following variables.

```
testid="<enter testid name>" (default: test)

teardown="<enter False>" (default: False)

trigger_topic="<enter trigger topic name>" (default: elasticc-alerts)

trigger_topic_project="<enter trigger topic project name>" (default: avid-heading-329016)

GOOGLE_CLOUD_PROJECT="<enter GCP project name>"
```
* NOTE: If a Cloud Run instance already exists, selecting `teardown="True"` will delete all GCP resources associated with the information provided above.


## Calling the deployment script
* Confirm that your current directory is the same as the repo's root directory (i.e., pittgoogle-user). To call on the deployment script, use the command: `source setup.sh`

* As the deployment script executes, a series of messages will appear. These messages will describe the status of deployment.


## Review Cloud Run instance(s)
* Once the deployment script has successfully created your Cloud Run instance, you can review its status, and the status of other instances on the [Google Cloud Console](https://console.cloud.google.com/run?). Verify that the number of requests per second (Req/sec) is non-zero.

## How to stop a Cloud Run module
* Cloud Run instances are triggered by a Pub/Sub subcription. To stop a Cloud Run instance without deleting it, delete the trigger subscription. This can be done on the [Google Cloud Console](https://console.cloud.google.com/cloudpubsub/subscription/list?) or on the command line using: `gcloud pubsub subscriptions delete <enter subscription name>`.

* To view which subscription is triggering your Cloud Run instance, select your instance from the [Google Cloud Console](https://console.cloud.google.com/run?) and locate the _Triggers_ tab (it is located under the _URL_ section).

## How to delete a Cloud Run instance & all associated GCP resources
* The procedure follows the first two steps of this tutorial. Begin a new terminal and initialize the same variables. This time, select `teardown="<True>"`

* Confirm that your current directory is the same as the repo's root directory, and use the command `source setup.sh` to delete all the GCP resources associated with the information you provided (e.g., `testid`, `survey`, `trigger_topic`, etc.).