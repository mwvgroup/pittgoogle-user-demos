#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

"""This module filters the LSST alert stream to discover intra/inter-night-confirmed never-before-seen non-ssObject transients."""

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

    # unpack the alert. raises a `BadRequest` if the envelope does not contain a valid message
    try:
        alert = pittgoogle.Alert.from_cloud_run(envelope, "lsst")
    except pittgoogle.exceptions.BadRequest as exc:
        return str(exc), HTTP_400

    # filter
    filter_alert(alert)


def filter_alert(alert: pittgoogle.Alert):
    """Filters the LSST alert stream to identify intra/inter-night-confirmed never-before-seen non-ssObject transients.
    Discoveries are published to the appropriate Pub/Sub topic.
    """
    # [FIXME] assumes alert.get("ssobjectid") method implemented; need to add ssObjectId to lsst.yml
    # ensure the source is not associated with a solar system object and the number of detections
    # is equal to 2
    if len(alert.get("prv_sources")) == 1 and not alert.get("ssobjectid"):
        # determine if the discovery is intra-night or inter-night and publish result
        publish_discovery(alert)
    return "", HTTP_204


def publish_discovery(alert: pittgoogle.Alert):
    """Determines the type of detection (intra-night or inter-night) and publishes the discovery to the appropriate topic."""
    # convert MJD values to datetime strings and compare them
    initial_mjd, latest_mjd = _mjd_to_datetime(alert)
    if initial_mjd == latest_mjd:
        TOPIC_INTRA_NIGHT_DISCOVERIES.publish(_create_outgoing_alert(alert))
    else:
        TOPIC_INTER_NIGHT_DISCOVERIES.publish(_create_outgoing_alert(alert))


def _mjd_to_datetime(alert: pittgoogle.Alert):
    """Converts MJD values to datetime strings and formats them as YYYY-MM-DD."""
    initial_mjd = astropy.time.Time(
        alert.dict["prvDiaSources"][0]["midpointMjdTai"], format="mjd"
    ).datetime.strftime("%Y-%m-%d")
    latest_mjd = astropy.time.Time(alert.get("mjd"), format="mjd").datetime.strftime("%Y-%m-%d")
    return initial_mjd, latest_mjd


def _create_outgoing_alert(alert: pittgoogle.Alert) -> pittgoogle.Alert:
    """Creates a new Alert object."""
    outgoing_msg = {
        alert.get_key("objectid"): alert.get("objectid"),
        alert.get_key("ra"): alert.get("ra"),
        alert.get_key("dec"): alert.get("dec"),
        "initialMidpointMjdTai": alert.dict["prvDiaSources"][0]["midpointMjdTai"],
        "latestMidpointMjdTai": alert.get("mjd"),
    }

    return pittgoogle.alert.Alert(outgoing_msg)
