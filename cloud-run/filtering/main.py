#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

"""This module filters the LSST alert stream to discover never-before-seen transients."""

import os
import astropy.time
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
TOPIC_INTRA_NIGHT_DISCOVERIES = pittgoogle.Topic.from_cloud(
    "intra-night-discoveries", survey=SURVEY, testid=TESTID, projectid=PROJECT_ID
)
TOPIC_INTER_NIGHT_DISCOVERIES = pittgoogle.Topic.from_cloud(
    "inter-night-discoveries", survey=SURVEY, testid=TESTID, projectid=PROJECT_ID
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
    """Filters the LSST alert stream to identify intra/inter-night confirmed never-before-seen non-ssObject transients.
    Discoveries are published to a Pub/Sub topic.
    """
    # [FIXME] assumes alert.get("ssobjectid") method implemented; need to add ssObjectId to lsst.yml
    if len(alert.get("prv_sources")) == 1 and not alert.get("ssobjectid"):
        publish_discovery(alert)
    return "", HTTP_204


def publish_discovery(alert: pittgoogle.Alert):
    """Determines the type of detection (intra or inter night) and publishes the discovery to the appropriate topic."""
    detection_date, prv_detection_date = calculate_detection_dates(alert)
    if detection_date == prv_detection_date:
        TOPIC_INTRA_NIGHT_DISCOVERIES.publish(create_outgoing_alert(alert))
    else:
        TOPIC_INTER_NIGHT_DISCOVERIES.publish(create_outgoing_alert(alert))


def calculate_detection_dates(alert: pittgoogle.Alert):
    detection_date = astropy.time.Time(alert.get("mjd"), format="mjd").datetime.strftime(
        "%Y-%m-%d"
    )
    prv_detection_date = astropy.time.Time(
        alert.dict["prvDiaSources"][0]["midpointMjdTai"], format="mjd"
    ).datetime.strftime("%Y-%m-%d")

    return detection_date, prv_detection_date


def create_outgoing_alert(alert: pittgoogle.Alert) -> pittgoogle.Alert:
    """Creates a new Alert object."""
    outgoing_msg = {
        alert.get_key("objectid"): alert.get("objectid"),
        alert.get_key("ra"): alert.get("ra"),
        alert.get_key("dec"): alert.get("dec"),
        "initialMidpointMjdTai": alert.dict["prvDiaSources"][0]["midpointMjdTai"],
        "latestMidpointMjdTai": alert.get("mjd"),
    }

    return pittgoogle.alert.Alert(outgoing_msg)
