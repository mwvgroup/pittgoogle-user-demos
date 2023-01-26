#!/usr/bin/env bash
# Create and configure GCP resources needed to deploy Cloud Run

# setup
testid="${1:-test}"
teardown="${2:-False}"
survey="${3:-elasticc}"
trigger_topic="${4:-elasticc-alerts}"
trigger_topic_project="${5:-avid-heading-329016}"
PROJECT_ID="${GOOGLE_CLOUD_PROJECT}"

# GCP resources & variables used in this script that need a testid
bq_dataset="${PROJECT_ID}:${survey}_alerts"
pubsub_SuperNNova_topic="${survey}-SuperNNova"
module_name="${survey}-classifier"
subscrip="elasticc-loop" #pub/sub subscription used to trigger Cloud Run module

if [ "$testid" != "False" ]; then
    bq_dataset="${bq_dataset}_${testid}"
    pubsub_SuperNNova_topic="${pubsub_SuperNNova_topic}-${testid}"
    module_name="${module_name}-${testid}"
    subscrip="elasticc-loop-${testid}"
fi

# additional GCP resources & variables used in this script
alerts_table="SuperNNova"
module_image_name="gcr.io/${PROJECT_ID}/${module_name}"
region="us-central1"
route="/"
runinvoker_svcact="cloud-run-invoker@${PROJECT_ID}.iam.gserviceaccount.com"

# create BigQuery, Pub/Sub resources
if [ "${teardown}" != "True" ]; then
    echo "Configuring BigQuery, Pub/Sub resources for Cloud Run..."
    # create pub/sub topics and subscriptions
    gcloud pubsub topics create "${pubsub_SuperNNova_topic}"

    # create the BigQuery dataset and table
    bq mk --dataset "${bq_dataset}"
    bq mk --table "${bq_dataset}.${alerts_table}" "templates/bq_${survey}_${alerts_table}_schema.json"

    # Deploy Cloud Run
    echo "Creating container image and deploying to Cloud Run..."
    moduledir="classifier"  # assumes we're in the repo's root dir
    config="${moduledir}/cloudbuild.yaml"
    url=$(gcloud builds submit --config="${config}" \
        --substitutions=_SURVEY="${survey}",_TESTID="-${testid}" \
        "${moduledir}" | sed -n 's/^Step #2: Service URL: \(.*\)$/\1/p')
    
    echo "Creating trigger subscription for Cloud Run"
    gcloud pubsub subscriptions create "${subscrip}" \
        --topic "${trigger_topic}" \
        --topic-project "${trigger_topic_project}" \
        --ack-deadline=600 \
        --push-endpoint="${url}${route}" \
        --push-auth-service-account="${runinvoker_svcact}"

else
    # ensure that we do not teardown production resources
    if [ "${testid}" != "False" ]; then
        echo "Removing BigQuery, Pub/Sub resources for Cloud Run..."
        gcloud pubsub subscriptions delete "${subscrip}" # needed to stop the Cloud Run module
        gcloud pubsub topics delete "${pubsub_SuperNNova_topic}"
        bq rm --table "${bq_dataset}.${alerts_table}"
        bq rm --dataset=true "${bq_dataset}"
        gcloud run services delete "${module_name}" --region "${region}"
        gcloud container images delete "${module_image_name}"
    fi
fi
