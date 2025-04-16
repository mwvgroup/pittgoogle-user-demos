#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

"""This module filters the LSST alert stream to discover intra-night-confirmed never-before-seen non-ssObject transients."""

import os
import numpy as np
from astropy.coordinates import SkyCoord
import astropy.time
import astropy.units as u
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
    """Processes the LSST alert stream filtered by the Pub/Sub subscription that triggers this module.

    This module is intended to be deployed as a Cloud Run service. It will operate as an HTTP endpoint
    triggered by Pub/Sub messages. This function will be called once for every message sent to this route.
    It should accept the incoming HTTP request and return a response.
    """

    # extract the envelope from the request that triggered the endpoint
    # this contains a single Pub/Sub message with the alert to be processed
    envelope = flask.request.get_json()

    # unpack the alert. raises a `BadRequest` if the envelope does not contain a valid message
    try:
        alert = pittgoogle.Alert.from_cloud_run(envelope, f"{SURVEY}")
    except pittgoogle.exceptions.BadRequest as exc:
        return str(exc), HTTP_400

    # filter
    return filter_alert(alert)


def filter_alert(alert: pittgoogle.Alert):
    """Filters the incoming LSST alert stream to identify intra/inter-night-confirmed never-before-seen non-ssObject transients.
    Discoveries are published to a Pub/Sub topic.
    """
    is_intra_night_discovery = _is_intra_night_discovery(alert)
    is_inter_night_discovery = _is_inter_night_discovery(alert)
    is_candidate = _satisfies_candidate_requirements(alert)

    if is_intra_night_discovery and is_candidate:
        TOPIC_INTRA_NIGHT_DISCOVERIES.publish(alert)
    elif is_inter_night_discovery and is_candidate:
        TOPIC_INTER_NIGHT_DISCOVERIES.publish(alert)
    return "", HTTP_204


def _is_intra_night_discovery(alert: pittgoogle.Alert) -> bool:
    """Determines if the detection is an intra-night discovery."""
    if alert.n_previous_detections != "1":
        return False

    # convert MJD floats to datetime strings and compare them
    prv_mjds, latest_mjd = _mjds_to_datetime_strs(alert)
    return prv_mjds[0] == latest_mjd


def _is_inter_night_discovery(alert: pittgoogle.Alert) -> bool:
    """Determines if the detection is an inter-night discovery."""
    if alert.n_previous_detections != "2":
        return False

    # convert MJD floats to datetime strings and compare them
    prv_mjds, latest_mjd = _mjds_to_datetime_strs(alert)
    if len(set(prv_mjds)) == 1 and prv_mjds[0] != latest_mjd:
        return True
    return False


def _mjds_to_datetime_strs(alert: pittgoogle.Alert) -> tuple[list[str], str]:
    """Converts MJD values to datetime strings and formats them as YYYY-MM-DD."""
    previous_mjd = [
        astropy.time.Time(source["midpointMjdTai"], format="mjd").datetime.strftime("%Y-%m-%d")
        for source in alert.get("prv_sources")
    ]
    latest_mjd = astropy.time.Time(alert.get("mjd"), format="mjd").datetime.strftime("%Y-%m-%d")
    return previous_mjd, latest_mjd


def _satisfies_candidate_requirements(alert: pittgoogle.Alert) -> bool:
    """Determines if the discovery meets additional requirements sought by this module."""
    in_same_position = _is_within_positional_uncertainty(alert)
    is_new_object = _xmatch_for_previous_detections(alert)

    return in_same_position and is_new_object


def _is_within_positional_uncertainty(alert: pittgoogle.Alert) -> bool:
    """Determines if the current diaSource is within the positional uncertainty of the initially detected diaSource."""
    # get positions and uncertainties
    ra, dec = alert.get("ra"), alert.get("dec")
    prev_ra, prev_dec = alert.get("prv_sources")[0]["ra"], alert.get("prv_sources")[0]["dec"]
    ra_err, dec_err = alert.get("ra_err"), alert.get("dec_err")
    prev_ra_err, prev_dec_err = (
        alert.get("prv_sources")[0]["raErr"],
        alert.get("prv_sources")[0]["decErr"],
    )

    # compute angular separation in arcseconds
    current_position = SkyCoord(ra=ra * u.deg, dec=dec * u.deg)
    initial_position = SkyCoord(ra=prev_ra * u.deg, dec=prev_dec * u.deg)
    separation = current_position.separation(initial_position).arcsec

    # determine if the separation is within the positional uncertainty
    positional_uncertainty = np.sqrt(ra_err**2 + dec_err**2 + prev_ra_err**2 + prev_dec_err**2)
    if separation <= 3 * positional_uncertainty:
        return True
    return False


def _xmatch_for_previous_detections(alert) -> bool:
    return False
