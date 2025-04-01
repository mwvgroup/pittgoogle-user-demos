# Pub/Sub Tutorial

**Prerequisites**

- Complete [One-Time Setup](https://mwvgroup.github.io/pittgoogle-client/one-time-setup), specifically:
    - Install the `pittgoogle-client` package
    - Setup authentication to a Google Cloud project
    - Set environment variables
    - Enable the Pub/Sub API

## Setup

```python
import pittgoogle
```

## Create a subscription to a topic in a different project

To listen to an alert stream served by Pitt-Google, you will need to create a subscription in your
Google Cloud project that is attached to a topic in Pitt-Google's project.

```python
ztopic = pittgoogle.Topic("ztf-loop", projectid=pittgoogle.ProjectIds().pittgoogle)
zloop = pittgoogle.Subscription("ztf-loop", schema_name="ztf", topic=ztopic)
# This will create a subscription in your Google Cloud project if it doesn't already exist.
zloop.touch()
zalert = zloop.pull_batch(max_messages=1)[0]
zalert.dataframe
```

## Filter messages from a Pub/Sub subscription

Subscription filters specified at the moment of the subscription's creation can be used to select messages based on
their attributes but not by the data in the message. Messages that do not match the filter are automatically
acknowledged by the Pub/Sub service. This can be done using the Google Cloud Command Line Interface (`gcloud` CLI).

### Create a subscription with a filter

```bash
gcloud pubsub subscriptions create SUBSCRIPTION_ID \
  --topic=TOPIC_ID \
  --message-filter='FILTER'
```

Where:

- `SUBSCRIPTION_ID` is the name of your subscription
- `TOPIC_ID` is the name of the topic
- `FILTER` is an expression conforming to the
[filtering syntax](https://cloud.google.com/pubsub/docs/subscription-message-filter#filtering_syntax)

### Examples

Filter messages with the `schema_version` attribute and the value of `v7_4`

```bash
PITTGOOGLE_PROJECT_ID="ardent-cycling-243415"
versiontag="v7_4"
subscription_name="lsst-alerts"

# create subscription
gcloud pubsub subscriptions create "${subscription_name}" \
    --topic="lsst-alerts" \
    --topic-project "${PITTGOOGLE_PROJECT_ID}" \
    --message-filter='attributes.schema_version = "'"${versiontag}"'"'
```
