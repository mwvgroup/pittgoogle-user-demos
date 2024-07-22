# Pub/Sub Tutorial

**Prerequisites**

- Complete [One-Time Setup](https://mwvgroup.github.io/pittgoogle-client/one-time-setup), specifically:
    - Install the `pittgoogle-client` package
    - Setup authentication to a Google Cloud project
    - Set environment variables
    - Enable the Pub/Sub API
    - You can skip the command-line tools

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
