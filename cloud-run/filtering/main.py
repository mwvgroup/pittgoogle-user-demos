#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

"""This module filters the LSST alert stream to discover never-before-seen transients."""

import os
import flask
import pittgoogle

PROJECT_ID = os.getenv("GCP_PROJECT")
TESTID = os.getenv("TESTID")
SURVEY = os.getenv("SURVEY")

# Variables for incoming data
# A url route is used in setup.sh when the trigger subscription is created.
# It is possible to define multiple routes in a single module and trigger them using different subscriptions.
ROUTE_RUN = "/"  # HTTP route that will trigger run(). Must match setup.sh

# Variables for outgoing data
HTTP_204 = 204  # HTTP code: Success
HTTP_400 = 400  # HTTP code: Bad Request
TOPIC_FIRST_DETECTION = pittgoogle.Topic.from_cloud(
    "first-detection", survey=SURVEY, testid=TESTID, projectid=PROJECT_ID
)

app = flask.Flask(__name__)


@app.route(ROUTE_RUN, methods=["POST"])
def run():
    """Processes full LSST alert stream.

    This module is intended to be deployed as a Cloud Run service. It will operate as an HTTP endpoint
    triggered by Pub/Sub messages. This function will be called once for every message sent to this route.
    It should accept the incoming HTTP request and return a response.
    """

    # extract the envelope from the request that triggered the endpoint
    # this contains a single Pub/Sub message with the alert to be processed
    envelope = flask.request.get_json()
    try:
        alert = pittgoogle.Alert.from_cloud_run(envelope, "lsst")
    except pittgoogle.exceptions.BadRequest as exc:
        return str(exc), HTTP_400

    filter_alert(alert)


def filter_alert(alert: pittgoogle.Alert):
    """Filters the LSST alert stream to identify never-before-seen non-ssObject transients.
    Discoveries are published to a Pub/Sub topic.
    """
    if not alert.get("ssobjectid") and not alert.get("prv_sources"):
        TOPIC_FIRST_DETECTION.publish(create_outgoing_alert(alert), serializer="json")
    return "", HTTP_204


def create_outgoing_alert(alert: pittgoogle.Alert) -> pittgoogle.Alert:
    """Creates a new Alert object."""
    outgoing_msg = {
        alert.get_key("objectid"): alert.get("objectid"),
        alert.get_key("ra"): alert.get("ra"),
        alert.get_key("dec"): alert.get("dec"),
        alert.get_key("mjd"): alert.get("mjd"),
    }
    attrs = {"first_detection": "True"}
    return pittgoogle.alert.Alert(outgoing_msg, attributes=attrs)
