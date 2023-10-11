#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

"""Classify alerts using SuperNNova (M¨oller & de Boissi`ere 2019)."""

import base64
from datetime import datetime, timezone
import io
import os

from google.cloud import bigquery, logging
import json
import fastavro

import numpy as np
import pandas as pd
from pathlib import Path
from supernnova.validation.validate_onthefly import classify_lcs

from broker_utils import data_utils, gcp_utils, math
from broker_utils.types import AlertIds
from broker_utils.schema_maps import load_schema_map, get_value
from broker_utils.data_utils import open_alert

from flask import Flask, request

PROJECT_ID = os.getenv("GCP_PROJECT")
TESTID = os.getenv("TESTID")
SURVEY = os.getenv("SURVEY")

# connect to the logger
logging_client = logging.Client()
log_name = "classify-snn-cloudrun"  # same log for all broker instances
logger = logging_client.logger(log_name)

# GCP resources used in this module
bq_dataset = f"{SURVEY}_alerts"
ps_topic = f"{SURVEY}-SuperNNova"
if TESTID != "False":  # attach the testid to the names
    bq_dataset = f"{bq_dataset}_{TESTID}"
    ps_topic = f"{ps_topic}-{TESTID}"
bq_table_id = f"{PROJECT_ID}.{bq_dataset}.SuperNNova"

schema_out = fastavro.schema.load_schema("elasticc.v0_9_1.brokerClassfication.avsc")
workingdir = Path(__file__).resolve().parent
schema_map = load_schema_map(SURVEY, TESTID, schema=(workingdir / f"{SURVEY}-schema-map.yml"))
alert_ids = AlertIds(schema_map)
id_keys = alert_ids.id_keys
if SURVEY == "elasticc":
    schema_in = "elasticc.v0_9_1.alert.avsc"
else:
    schema_in = None

model_dir_name = "ZTF_DMAM_V19_NoC_SNIa_vs_CC_forFink"
model_file_name = "vanilla_S_0_CLF_2_R_none_photometry_DF_1.0_N_global_lstm_32x2_0.05_128_True_mean.pt"
model_path = Path(__file__).resolve().parent / f"{model_dir_name}/{model_file_name}"
bq_client = bigquery.Client(project=PROJECT_ID)
bq_schema = [
    bigquery.SchemaField("alertId", "INTEGER"),
    bigquery.SchemaField("diaObjectId", "INTEGER"),
    bigquery.SchemaField("diaSourceId", "INTEGER"),
    bigquery.SchemaField("prob_class0", "FLOAT"),
    bigquery.SchemaField("prob_class1", "FLOAT"),
    bigquery.SchemaField("predicted_class", "INTEGER"),
    bigquery.SchemaField("elasticcPublishTimestamp", "TIMESTAMP"),
    bigquery.SchemaField("brokerIngestTimestamp", "TIMESTAMP"),
    bigquery.SchemaField("classifierTimestamp", "TIMESTAMP")
]

app = Flask(__name__)
@app.route("/", methods=["POST"])
def index():
    """Classify alert with SuperNNova; publish and store results.

    This function is intended to be triggered by Pub/Sub messages, via Cloud Run.
    """
    envelope = request.get_json()

    # do some checks
    if not envelope:
        msg = "no Pub/Sub message received"
        print(f"error: {msg}")
        return f"Bad Request: {msg}", 400

    if not isinstance(envelope, dict) or "message" not in envelope:
        msg = "invalid Pub/Sub message format"
        print(f"error: {msg}")
        return f"Bad Request: {msg}", 400

    # unpack the alert
    msg = envelope["message"]

    alert_dict = open_alert(msg["data"], load_schema=schema_in)
    a_ids = alert_ids.extract_ids(alert_dict=alert_dict)
    
    try:
        publish_time = datetime.strptime(msg["publish_time"].replace("Z","+00:00"), '%Y-%m-%dT%H:%M:%S.%f%z')
    except ValueError:
        publish_time = datetime.strptime(msg["publish_time"].replace("Z","+00:00"), '%Y-%m-%dT%H:%M:%S%z')

    attrs = {
        **msg["attributes"],
        "brokerIngestTimestamp": publish_time,
        id_keys.objectId: str(a_ids.objectId),
        id_keys.sourceId: str(a_ids.sourceId),
    }

    # classify
    snn_dict = _classify_with_snn(alert_dict, attrs)

    # create the message for elasticc and publish the stream
    avro = _create_elasticc_msg(dict(alert=alert_dict, SuperNNova=snn_dict), attrs)
    gcp_utils.publish_pubsub(ps_topic, avro, attrs=attrs)

    # write to BigQuery
    errors = bq_client.insert_rows(bq_table_id, [snn_dict], bq_schema)
    if len(errors) > 0:
        logger.log_text(f"BigQuery insert error: {errors}", severity="WARNING")

    return ("", 204)

def _classify_with_snn(alert_dict: dict, attrs: dict) -> dict:
    """Classify the alert using SuperNNova."""
    # init
    snn_df = _format_for_snn(alert_dict)
    device = "cpu"

    # classify
    _, pred_probs = classify_lcs(snn_df, model_path, device)

    # retrieve and format elasticcPublishTimestamp
    kafka_timestamp = datetime.fromtimestamp(int(attrs["kafka.timestamp"])/1000) # converts kafka.timestamp from milliseconds to seconds
    formatted_kafka_timestamp = kafka_timestamp.strftime("%Y-%m-%d %H:%M:%S.%f") + " UTC"

    # extract results to dict and attach alert/object/source ids.
    # use `.item()` to convert numpy -> python types for later json serialization
    elasticc_alert = alert_dict["alert"]
    pred_probs = pred_probs.flatten()
    snn_dict = {
        "alertId": elasticc_alert["alertId"],
        id_keys.objectId: snn_df.objectId,
        id_keys.sourceId: snn_df.sourceId,
        "prob_class0": pred_probs[0].item(),
        "prob_class1": pred_probs[1].item(),
        "predicted_class": np.argmax(pred_probs).item(),
        "elasticcPublishTimestamp": formatted_kafka_timestamp,
        "brokerIngestTimestamp": attrs["brokerIngestTimestamp"],
        "classifierTimestamp": datetime.now(timezone.utc)
    }

    return snn_dict


def _format_for_snn(alert_dict: dict) -> pd.DataFrame:
    """Compute features and cast to a DataFrame for input to SuperNNova."""
    # cast alert to dataframe
    alert_df = data_utils.alert_dict_to_dataframe(alert_dict, schema_map)

    # start a dataframe for input to SNN
    snn_df = pd.DataFrame(data={"SNID": alert_df.objectId}, index=alert_df.index)
    snn_df.objectId = alert_df.objectId
    snn_df.sourceId = alert_df.sourceId
    snn_df["FLT"] = alert_df["filterName"]
    snn_df["FLUXCAL"] = alert_df["psFlux"]
    snn_df["FLUXCALERR"] = alert_df["psFluxErr"]
    snn_df["MJD"] = alert_df["midPointTai"]

    return snn_df


def _create_elasticc_msg(alert_dict, attrs):
    """Create a message according to the ELAsTiCC broker classifications schema.
    https://github.com/LSSTDESC/plasticc_alerts/blob/main/Examples/plasticc_schema
    """
    # original elasticc alert as a dict
    elasticc_alert = alert_dict["alert"]
    supernnova_results = alert_dict["SuperNNova"]

    # here are a few things you'll need
    elasticcPublishTimestamp = int(attrs["kafka.timestamp"])
    brokerIngestTimestamp = attrs.pop("brokerIngestTimestamp")
    brokerVersion = "v0.6"

    classifications = [
        {
            "classId": 2222,
            "probability": supernnova_results["prob_class0"],
        },
    ]

    msg = {
        "alertId": elasticc_alert["alertId"],
        "diaSourceId": get_value("sourceId", elasticc_alert, schema_map),
        "elasticcPublishTimestamp": elasticcPublishTimestamp,
        "brokerIngestTimestamp": brokerIngestTimestamp,
        "brokerName": "Pitt-Google Broker",
        "brokerVersion": brokerVersion,
        "classifierName": "SuperNNova_v1.3",
        "classifierParams": "",  # leave this blank for now
        "classifications": classifications
    }

    # avro serialize the dictionary
    avro = _dict_to_avro(msg, schema_out)
    return avro

def _dict_to_avro(msg: dict, schema: dict):
    """Avro serialize a dictionary."""
    fout = io.BytesIO()
    fastavro.schemaless_writer(fout, schema, msg)
    fout.seek(0)
    avro = fout.getvalue()
    return avro
