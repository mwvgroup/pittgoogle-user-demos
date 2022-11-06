#!/usr/bin/env bash
# Create and configure GCP resources needed to deploy Cloud Run

# setup
testid="${1:-test}"
teardown="${2:-False}"
survey="${3:-elasticc}"
PROJECT_ID="${GOOGLE_CLOUD_PROJECT}"

# GCP resources used in this script
pubsub_trigger_topic="${survey}-alerts"
pubsub_SuperNNova_topic="${survey}-SuperNNova"
bq_dataset="${PROJECT_ID}:${survey}_alerts"
alerts_table="SuperNNova"

if [ "$testid" != "False" ]; then
    pubsub_trigger_topic="${pubsub_trigger_topic}-${testid}"
    pubsub_SuperNNova_topic="${pubsub_SuperNNova_topic}-${testid}"
    bq_dataset="${bq_dataset}_${testid}"
fi

# create the necessary Pub/Sub topic(s) and subscription(s)
echo "Configuring BigQuery, Pub/Sub resources for Cloud Run..."

# create pub/sub topics and subscriptions
gcloud pubsub topics create "${pubsub_trigger_topic}"
gcloud pubsub topics create "${pubsub_SuperNNova_topic}"

# create the BigQuery dataset and table
bq mk --dataset "${bq_dataset}"
#want to double check with you regarding the next two lines
bq mk --table "${bq_dataset}.${alerts_table}" "templates/bq_${survey}_${alerts_table}_schema.json"

# Deploy Cloud Run
echo "Creating container image and deploying to Cloud Run..."
moduledir="classifier"  # assumes we're in the repo's root dir
config="${moduledir}/cloudbuild.yaml"
gcloud builds submit --config="${config}" \
    --substitutions=_SURVEY="${SURVEY}",_TESTID="${TESTID}" \
    "${moduledir}"

