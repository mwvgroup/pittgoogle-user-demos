#!/usr/bin/env bash
# Create and configure GCP resources needed to deploy Cloud Run

# setup
testid="${1:-test}"
survey="${2:-elasticc}"
teardown="${3:-False}"
trigger_topic="${4:-elasticc-alerts}"
trigger_topic_project="${5:-avid-heading-329016}"

PROJECT_ID="${GOOGLE_CLOUD_PROJECT}"

#--- Make the user confirm the settings
echo
echo "setup.sh will run with the following configs: "
echo
echo "testid = ${testid}"
echo "survey = ${survey}"
echo "teardown = ${teardown}"
echo "trigger_topic = ${trigger_topic}"
echo "trigger_topic_project = ${trigger_topic_project}"
echo "GOOGLE_CLOUD_PROJECT = ${PROJECT_ID}"
echo
echo "Continue?  [y/(n)]: "

read input
input="${input:-n}"
if [ "${input}" != "y" ]; then
    echo "Exiting setup."
    echo
    exit
fi

# GCP resources & variables used in this script that need a testid
bq_dataset="${PROJECT_ID}:${survey}_alerts"
pubsub_SuperNNova_topic="${survey}-SuperNNova"
module_name="${survey}-classifier"
subscrip="${trigger_topic}" #pub/sub subscription used to trigger Cloud Run module

if [ "$testid" != "False" ]; then
    bq_dataset="${bq_dataset}_${testid}"
    pubsub_SuperNNova_topic="${pubsub_SuperNNova_topic}-${testid}"
    module_name="${module_name}-${testid}"
    subscrip="${subscrip}-${testid}"
fi

# additional GCP resources & variables used in this script
alerts_table="SuperNNova"
module_image_name="gcr.io/${PROJECT_ID}/${module_name}"
region="us-central1"
route="/"
runinvoker_svcact="cloud-run-invoker@${PROJECT_ID}.iam.gserviceaccount.com"

# create BigQuery, Pub/Sub resources
if [ "${teardown}" != "True" ]; then
    echo
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
        --substitutions="_SURVEY=${survey},_TESTID=${testid},_MODULE_NAME=${module_name}" \
        "${moduledir}" | sed -n 's/^Step #2: Service URL: \(.*\)$/\1/p')

    echo "Creating trigger subscription for Cloud Run..."
    # WARNING:  This is set to retry failed deliveries. If there is a bug in main.py this will 
    # retry indefinitely, until the message is delete manually.
    gcloud pubsub subscriptions create "${subscrip}" \
        --topic "${trigger_topic}" \
        --topic-project "${trigger_topic_project}" \
        --ack-deadline=600 \
        --max-delivery-attempts \
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
