#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

"""Classify alerts using SuperNNova (M¨oller & de Boissi`ere 2019)."""

import os
from datetime import datetime, timezone
from pathlib import Path

import google.cloud.logging
import numpy as np
import pandas as pd
from flask import Flask, request
from supernnova.validation.validate_onthefly import classify_lcs

import pittgoogle as pg

PROJECT_ID = os.getenv("GCP_PROJECT")
TESTID = os.getenv("TESTID")
SURVEY = os.getenv("SURVEY")

HTTP204 = 204
HTTP400 = 400

# connect to the logger
logging_client = google.cloud.logging.Client()
log_name = "classify-snn-cloudrun"  # same log for all broker instances
logger = logging_client.logger(log_name)

# GCP resources used in this module
bq_dataset = f"{SURVEY}_alerts"
if TESTID != "False":  # attach the testid to the names
    bq_dataset = f"{bq_dataset}_{TESTID}"
bq_table = f"{bq_dataset}.SuperNNova"

TOPIC = pg.pubsub.Topic.from_cloud(f"{SURVEY}-SuperNNova", projectid=PROJECT_ID, testid=TESTID)

SCHEMA_IN = "elasticc.v0_9_1.alert"
SCHEMA_OUT = "elasticc.v0_9_1.brokerClassfication"

alert_shell = pg.pubsub.Alert(schema_name=SCHEMA_IN)
SCHEMA_MAP = alert_shell.schema_map  # dict mapping broker -> survey field paths
OBJECTID = alert_shell.get("objectid", return_key_name=True)  # survey's objectid field name (str)
SOURCEID = alert_shell.get("sourceid", return_key_name=True)  # survey's sourceid field name (str)

# schema_out = fastavro.schema.load_schema("elasticc.v0_9_1.brokerClassfication.avsc")
# workingdir = Path(__file__).resolve().parent
# schema_map = load_schema_map(SURVEY, TESTID, schema=(workingdir / f"{SURVEY}-schema-map.yml"))
# alert_ids = AlertIds(schema_map)
# id_keys = alert_ids.id_keys
# if SURVEY == "elasticc":
#     schema_in = "elasticc.v0_9_1.alert.avsc"
# else:
#     schema_in = None

model_dir_name = "ZTF_DMAM_V19_NoC_SNIa_vs_CC_forFink"
model_file_name = (
    "vanilla_S_0_CLF_2_R_none_photometry_DF_1.0_N_global_lstm_32x2_0.05_128_True_mean.pt"
)
model_path = Path(__file__).resolve().parent / f"{model_dir_name}/{model_file_name}"

app = Flask(__name__)


@app.route("/", methods=["POST"])
def index():
    """Classify alert with SuperNNova; publish and store results.

    This function is intended to be triggered by Pub/Sub messages, via Cloud Run.
    """
    # envelope = request.get_json()
    try:
        alert = pg.pubsub.Alert.from_cloud_run(envelope=request.get_json(), schema_name=SCHEMA_IN)
    # # do some checks
    # if not envelope:
    #     msg = "no Pub/Sub message received"
    #     print(f"error: {msg}")
    #     return f"Bad Request: {msg}", 400
    # if not isinstance(envelope, dict) or "message" not in envelope:
    #     msg = "invalid Pub/Sub message format"
    #     print(f"error: {msg}")
    #     return f"Bad Request: {msg}", 400
    # if alert.bad_request:
    #     return alert.bad_request
    except pg.exceptions.BadRequest as err:
        return err.text, HTTP400

    # unpack the alert
    # msg = envelope["message"]

    # alert_dict = open_alert(msg["data"], load_schema=schema_in)
    # a_ids = alert_ids.extract_ids(alert_dict=alert_dict)

    snn_dict = classify_with_snn(alert)
    alert_out = create_outgoing_alert(alert, snn_dict)

    # attrs = {
    #     **msg["attributes"],
    #     "brokerIngestTimestamp": publish_time,
    #     id_keys.objectId: str(a_ids.objectId),
    #     id_keys.sourceId: str(a_ids.sourceId),
    # }

    # classify
    errors = gcp_utils.insert_rows_bigquery(bq_table, [snn_dict])
    if len(errors) > 0:
        logger.log_text(f"BigQuery insert error: {errors}", severity="WARNING")

    # create the message for elasticc and publish the stream
    # avro = _create_elasticc_msg(dict(alert=alert_dict, SuperNNova=snn_dict), attrs)
    # gcp_utils.publish_pubsub(ps_topic, avro, attrs=attrs)
    TOPIC.publish(alert_out, format=SCHEMA_OUT)

    return "", HTTP204


def classify_with_snn(alert: pg.pubsub.Alert) -> dict:
    """Classify the alert using SuperNNova."""
    # init
    snn_df = format_for_snn(alert)
    device = "cpu"

    # classify
    _, pred_probs = classify_lcs(snn_df, model_path, device)

    # extract results to dict and attach object/source ids.
    # use `.item()` to convert numpy -> python types for later json serialization
    pred_probs = pred_probs.flatten()
    snn_dict = {
        # id_keys.objectId: snn_df.objectId,
        # id_keys.sourceId: snn_df.sourceId,
        OBJECTID: alert.get("objectid"),
        SOURCEID: alert.get("sourceid"),
        "prob_class0": pred_probs[0].item(),
        "prob_class1": pred_probs[1].item(),
        "predicted_class": np.argmax(pred_probs).item(),
        "timestamp": datetime.now(timezone.utc),
    }

    return snn_dict


def format_for_snn(alert: pg.pubsub.Alert) -> pd.DataFrame:
    """Compute features and cast to a DataFrame for input to SuperNNova."""
    # cast alert to dataframe
    # alert_df = data_utils.alert_dict_to_dataframe(alert_dict, schema_map)

    # start a dataframe for input to SNN
    snn_df = pd.DataFrame(data={"SNID": alert.get(OBJECTID)}, index=alert.dataframe.index)
    # snn_df.objectId = alert_df.objectId
    # snn_df.sourceId = alert_df.sourceId
    snn_df["FLT"] = alert.dataframe[SCHEMA_MAP["filter"]]
    snn_df["FLUXCAL"] = alert.dataframe[SCHEMA_MAP["flux"]]
    snn_df["FLUXCALERR"] = alert.dataframe[SCHEMA_MAP["fluxerr"]]
    snn_df["MJD"] = alert.dataframe[SCHEMA_MAP["mjd"]]

    return snn_df


def create_outgoing_alert(alert, snn_dict) -> pg.pubsub.Alert:
    try:
        publish_time = datetime.strptime(
            alert.msg.publish_time.replace("Z", "+00:00"), "%Y-%m-%dT%H:%M:%S.%f%z"
        )
    except ValueError:
        publish_time = datetime.strptime(
            alert.msg.publish_time.replace("Z", "+00:00"), "%Y-%m-%dT%H:%M:%S%z"
        )

    outgoing_dict = {
        "alertId": alert.get("alertid"),
        "diaSourceId": alert.get("sourceid"),
        "elasticcPublishTimestamp": int(alert.attributes["kafka.timestamp"]),
        "brokerIngestTimestamp": publish_time,
        "brokerName": "Pitt-Google Broker",
        "brokerVersion": "v0.6",
        "classifierName": "SuperNNova_v1.3",
        "classifierParams": "",
        "classifications": [
            {
                "classId": 2222,
                "probability": snn_dict["prob_class0"],
            },
        ],
    }

    return pg.pubsub.Alert(dict=outgoing_dict, attributes=alert.attributes)
