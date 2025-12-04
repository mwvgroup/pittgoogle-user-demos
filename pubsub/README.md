# Pub/Sub Tutorial

**Prerequisites**

- Complete [One-Time Setup](https://mwvgroup.github.io/pittgoogle-client/one-time-setup/index.html), specifically:
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

## Alert filtering

The `pittgoogle-client` package exposes two mechanisms for filtering when creating a subscription:

1. Attribute-based filters: lightweight filters that match on Pub/Sub message attributes
2. JavaScript User Defined Function (UDF) filters: more powerful filters that operate on the full message (payload and/or attributes)

By creating a subscription with a filter, users will only receive the messages that match the filter. The Pub/Sub
service will automatically acknowledge (i.e., drop) the messages that do _not_ match the defined filter.
Both filtering methods are applied only at creation time. Because Pub/Sub subscription filters are immutable, you
cannot modify a filter after the subscription is created. To update a filter, users must delete the subscription in Google
Cloud and recreate it.

### Attribute filters

Attribute filters use Pub/Sub's built-in subscription
[filtering syntax](https://docs.cloud.google.com/pubsub/docs/subscription-message-filter#filtering_syntax). Because
Pub/Sub message attributes are strings (default), using this filtering method is recommended when the filtering logic is simple.

```python
# Topic that the subscription should be connected to
topic = pittgoogle.Topic(name="lsst-alerts-simulated", projectid=pittgoogle.ProjectIds().pittgoogle)

# messages without this attribute key are filtered out
# (e.g., sources associated with solar system objects would not have this key)
_attribute_filter = "attributes:diaObject_diaObjectId"

subscription = pittgoogle.Subscription(
                    name="my-lsst-subscription",
                    topic=topic,
                    schema_name="lsst",
                )
subscription.touch(attribute_filter=_attribute_filter)
```

### JavaScript UDFs

JavaScript UDFs are a type of Single Message Transform (SMT). UDFs attached to a subscription accept incoming messages as input, perform the defined actions on the input, and return the result of the process. Users can strategically define a UDF that drops messages that do not meet certain requirements, as outlined below:

```python
# Topic that the subscription should be connected to
topic = pittgoogle.Topic(name="lsst-alerts-simulated", projectid=pittgoogle.ProjectIds().pittgoogle)

# objects with <=20 previous detections are filtered out
_smt_javascript_udf = '''
        function filterByNPrevDetections(message, metadata) {
            const attrs = message.attributes || {};
            const nPrevDetections = attrs.n_prev_detections ? parseInt(attrs.n_prev_detections) : null;
            return (nPrevDetections > 20) ? message : null;
        }
        '''

# Create the subscription
subscription = pittgoogle.Subscription(
        name="my-lsst-subscription",
        topic=topic,
        schema_name="lsst",
    )
subscription.touch(smt_javascript_udf=_smt_javascript_udf)
```

Pub/Sub enforces resource limits on UDFs to ensure efficient transformation operations. Please visit the
[documentation](https://docs.cloud.google.com/pubsub/docs/smts/udfs-overview#limitations) for additional details.
