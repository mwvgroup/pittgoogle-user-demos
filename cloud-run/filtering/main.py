#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

"""This module filters the LSST alert stream to discover intra-night-confirmed never-before-seen non-ssObject transients."""

import os
import numpy as np
from typing import Dict
from astropy.coordinates import SkyCoord
import astropy.time
import astropy.units as u
from astropy.io import fits
from astropy.stats import sigma_clip
import io
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

    # determines if the source is a potential candidate for intra/inter-night discoveries
    if is_intra_night_discovery or is_inter_night_discovery:
        if _is_candidate(alert):
            if is_intra_night_discovery:
                TOPIC_INTRA_NIGHT_DISCOVERIES.publish(alert)
            elif is_inter_night_discovery:
                TOPIC_INTER_NIGHT_DISCOVERIES.publish(alert)

    return "", HTTP_204


def _is_intra_night_discovery(alert: pittgoogle.Alert) -> bool:
    """Determines if the detection is an intra-night discovery."""
    if alert.attributes["n_previous_detections"] != 1:
        return False

    # convert MJD floats to datetime strings and compare them
    prv_mjds, latest_mjd = _mjds_to_datetime_strs(alert)

    return prv_mjds[0] == latest_mjd


def _is_inter_night_discovery(alert: pittgoogle.Alert) -> bool:
    """Determines if the detection is an inter-night discovery."""
    if alert.attributes["n_previous_detections"] != 2:
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


def _is_candidate(alert: pittgoogle.Alert) -> bool:
    # define configs
    configs = {
        "sigma_clipping_kwargs": {"sigma": 3, "maxiters": 10},
        "hostless_detection_with_clipping": {
            "crop_radius": 12,
            "max_number_of_pixels_clipped": 5,
            "min_number_of_pixels_clipped": 3,
        },
    }

    # extract cutouts
    cutouts = ["Template", "Science"]
    template_stamp, science_stamp = [alert.dict.get(f"cutout{cutout}") for cutout in cutouts]

    # apply sigma clipping to the bytes data for each stamp
    science_stamp_clipped = sigma_clip(
        _read_stamp_data(template_stamp), **configs["sigma_clipping_kwargs"]
    )
    template_stamp_clipped = sigma_clip(
        _read_stamp_data(science_stamp), **configs["sigma_clipping_kwargs"]
    )

    return _run_hostless_detection_with_clipped_data(
        science_stamp_clipped, template_stamp_clipped, configs
    )


def _read_stamp_data(cutout):
    hdul = fits.open(io.BytesIO(cutout))

    return hdul[0].data


def _run_hostless_detection_with_clipped_data(
    science_stamp: np.ndarray, template_stamp: np.ndarray, configs: Dict
) -> bool:
    """Adapted from:
    https://github.com/COINtoolbox/extragalactic_hostless/blob/main/src/pipeline_utils.py#L271

    Detects potential hostless candidates with sigma clipped stamp images by cropping an image patch from the center of
    the image. If pixels are rejected in scientific image but not in corresponding template image, such candidates are
    flagged as potential hostless.
    """

    science_clipped = sigma_clip(science_stamp, **configs["sigma_clipping_kwargs"])
    template_clipped = sigma_clip(template_stamp, **configs["sigma_clipping_kwargs"])
    is_hostless_candidate = _check_hostless_conditions(
        science_clipped, template_clipped, configs["hostless_detection_with_clipping"]
    )

    if is_hostless_candidate:
        return is_hostless_candidate
    science_stamp = _crop_center_patch(
        science_stamp, configs["hostless_detection_with_clipping"]["crop_radius"]
    )
    template_stamp = _crop_center_patch(
        template_stamp, configs["hostless_detection_with_clipping"]["crop_radius"]
    )
    science_clipped = sigma_clip(science_stamp, **configs["sigma_clipping_kwargs"])
    template_clipped = sigma_clip(template_stamp, **configs["sigma_clipping_kwargs"])
    is_hostless_candidate = _check_hostless_conditions(
        science_clipped, template_clipped, configs["hostless_detection_with_clipping"]
    )

    return is_hostless_candidate


def _crop_center_patch(input_image: np.ndarray, patch_radius: int = 12) -> np.ndarray:
    """Adapted from:
    https://github.com/COINtoolbox/extragalactic_hostless/blob/main/src/pipeline_utils.py#L234

    Crops rectangular patch around image center with a given patch scale.
    """
    image_shape = input_image.shape[0:2]
    center_coords = [image_shape[0] / 2, image_shape[1] / 2]
    center_patch_x = int(center_coords[0] - patch_radius)
    center_patch_y = int(center_coords[1] - patch_radius)

    return input_image[
        center_patch_x : center_patch_x + patch_radius * 2,
        center_patch_y : center_patch_y + patch_radius * 2,
    ]


def _check_hostless_conditions(
    science_clipped: np.ndarray, template_clipped: np.ndarray, detection_config: Dict
) -> bool:
    """Adapted from:
    https://github.com/COINtoolbox/extragalactic_hostless/blob/main/src/pipeline_utils.py#L253
    """

    science_only_detection = (
        np.ma.count_masked(science_clipped) > detection_config["max_number_of_pixels_clipped"]
        and np.ma.count_masked(template_clipped) < detection_config["min_number_of_pixels_clipped"]
    )
    template_only_detection = (
        np.ma.count_masked(template_clipped) > detection_config["max_number_of_pixels_clipped"]
        and np.ma.count_masked(science_clipped) < detection_config["min_number_of_pixels_clipped"]
    )

    if science_only_detection or template_only_detection:
        return True

    return False


# def _is_within_positional_uncertainty(alert: pittgoogle.Alert) -> bool:
#     """Determines if the current diaSource is within the positional uncertainty of the initially detected diaSource."""
#     # get positions and uncertainties
#     ra, dec = alert.get("ra"), alert.get("dec")
#     prev_ra, prev_dec = alert.get("prv_sources")[0]["ra"], alert.get("prv_sources")[0]["dec"]
#     ra_err, dec_err = alert.get("ra_err"), alert.get("dec_err")
#     prev_ra_err, prev_dec_err = (
#         alert.get("prv_sources")[0]["raErr"],
#         alert.get("prv_sources")[0]["decErr"],
#     )

#     # compute angular separation in arcseconds
#     current_position = SkyCoord(ra=ra * u.deg, dec=dec * u.deg)
#     initial_position = SkyCoord(ra=prev_ra * u.deg, dec=prev_dec * u.deg)
#     separation = current_position.separation(initial_position).arcsec

#     # determine if the separation is within the positional uncertainty
#     positional_uncertainty = np.sqrt(ra_err**2 + dec_err**2 + prev_ra_err**2 + prev_dec_err**2)
#     if separation <= 3 * positional_uncertainty:
#         return True
#     return False
