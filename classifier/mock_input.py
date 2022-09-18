#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""Load the input needed to test module locally and run a test."""
import os
from broker_utils.data_utils import open_alert
from broker_utils.gcp_utils import pull_pubsub

SURVEY = "elasticc"
TESTID = "mytest"
os.environ["GCP_PROJECT"] = os.getenv("GOOGLE_CLOUD_PROJECT")
os.environ["SURVEY"] = SURVEY
os.environ["TESTID"] = TESTID


# general setup
# assumes you are authenticated to the project "elasticc-challenge"
# schema_map = load_schema_map(SURVEY, TESTID)
# alert_ids = AlertIds(schema_map)
# id_keys = alert_ids.id_keys

# setup for pull
def input(subscrip="elasticc-loop", max_messages=10):
    """Return a generator that yields sets of input args for main.run()."""
    import main

    msg_only = False

    # pull a list of messages
    msgs = pull_pubsub(
        subscription_name=subscrip, msg_only=msg_only, max_messages=max_messages,
    )

    # take one message from the list, unpack the basic parts, and return it
    for msg in msgs:
        msg_bytes = msg.message.data
        msg_attributes = msg.message.attributes
        brokerIngestTimestamp = msg.message.publish_time

        # create alert_dict and attrs
        alert_dict = open_alert(msg_bytes, load_schema="elasticc.v0_9.alert.avsc")
        a_ids = main.alert_ids.extract_ids(alert_dict=alert_dict)
        attrs = {
            **msg_attributes,
            "brokerIngestTimestamp": brokerIngestTimestamp,
            main.id_keys.objectId: str(a_ids.objectId),
            main.id_keys.sourceId: str(a_ids.sourceId),
        }

        yield (alert_dict, attrs)
