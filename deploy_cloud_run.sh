#!/usr/bin/env bash
# Create and configure GCP resources needed to deploy Cloud Run

# setup
testid="${testid}"
teardown="${teardown}"
survey="${survey}"
PROJECT_ID="${GOOGLE_CLOUD_PROJECT}"
docker_compose = "cloudbuild.yaml"

# GCP resources used in this script
pubsub_trigger_topic = "${survey}-"
cloud_run_trigger_subscription = "${survey}-"
bq_dataset="${PROJECT_ID}:${survey}_alerts"
bq_topic="projects/${PROJECT_ID}/topics/${survey}-BigQuery"
alerts_table="alerts"
source_table="DIASource"

if [ "$testid" != "False" ]; then
    bq_dataset="${bq_dataset}_${testid}"
    bq_topic="${bq_topic}-${testid}"
fi

# create the necessary Pub/Sub topic(s) and subscription(s)
echo "Configuring BigQuery, Pub/Sub resources for Cloud Run..."

# create pub/sub (trigger) topics and subscriptions
gcloud pubsub topics create ""
gcloud pubsub topics create "${pubsub_trigger_topic}"
gcloud pubsub subscriptions create "${cloud_run_trigger_subscription}" --topic "${pubsub_trigger_topic}"

# create the BigQuery dataset and table(s)
bq mk --dataset "${bq_dataset}"
#want to double check with you regarding the next two lines
bq mk --table "${bq_dataset}.${alerts_table}" "templates/bq_${survey}_${alerts_table}_schema.json"
bq mk --table "${bq_dataset}.${source_table}" "templates/bq_${survey}_${source_table}_schema.json"

#should the following block go into project-setup.sh?

# prepare to create a trigger for Cloud Run, documentation found here: 
# https://cloud.google.com/run/docs/triggering/trigger-with-events#prepare
SERVICE_ACCOUNT="$(gsutil kms serviceaccount -p ${PROJECT_ID})"

gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role='roles/pubsub.publisher'

# Deploy Cloud Run
echo "Creating container image and deploying to Cloud Run..."
docker-compose ${docker_compose} up
