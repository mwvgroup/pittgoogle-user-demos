#!/usr/bin/env bash
# Create and configure GCP resources needed to deploy Cloud Run

# "False" uses production resources
# any other string will be appended to the names of all resources
testid="${1:-test}"
# "True" tearsdown/deletes resources, else setup
teardown="${2:-False}"
# name of the survey this broker instance will ingest
survey="${3:-lsst}"
region="${4:-us-central1}"
zone="${region}-a"
# get environment variables
PROJECT_ID=$GOOGLE_CLOUD_PROJECT
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")
PITTGOOGLE_PROJECT_ID="ardent-cycling-243415"

MODULE_NAME="transient-discovery-filter"  # lower case required by cloud run
ROUTE_RUN="/"  # url route that will trigger main.run()

#--- Make the user confirm the settings
echo
echo "setup.sh will run with the following configs: "
echo
echo "GOOGLE_CLOUD_PROJECT = ${PROJECT_ID}"
echo "testid = ${testid}"
echo "teardown = ${teardown}"
echo "survey = ${survey}"
echo "region = ${region}"
echo
echo "Continue?  [y/(n)]: "

read -r continue_with_setup
continue_with_setup="${continue_with_setup:-n}"
if [ "$continue_with_setup" != "y" ]; then
    echo "Exiting setup."
    echo
    exit
fi

#--- Function used to define GCP resources; appends testid if needed
define_GCP_resources() {
    local base_name="$1"
    local testid_suffix=""

    if [ "$testid" != "False" ]; then
        if [ "$base_name" = "$survey" ]; then
            testid_suffix="_${testid}"  # complies with BigQuery naming conventions
        else
            testid_suffix="-${testid}"
        fi
    fi

    echo "${base_name}${testid_suffix}"
}

#--- GCP resources used directly in this script
artifact_registry_repo=$(define_GCP_resources "${survey}-cloud-run-services")
bq_dataset=$(define_GCP_resources "${survey}")
cr_module_name=$(define_GCP_resources "${survey}-${MODULE_NAME}")  # lower case required by Cloud Run
intra_night_discovery_table="${survey}_intra_night_discovery"
inter_night_discovery_table="${survey}_inter_night_discovery"
ps_input_subscrip=$(define_GCP_resources "${survey}-alerts") # Pub/Sub subscription used to trigger Cloud Run module
runinvoker_svcact="cloud-run-invoker@${PROJECT_ID}.iam.gserviceaccount.com"
topic_intra_night_discovery=$(define_GCP_resources "${survey}-intra-night-discoveries")
topic_inter_night_discovery=$(define_GCP_resources "${survey}-inter-night-discoveries")
trigger_topic=$(define_GCP_resources "${survey}-alerts")
subscription_bigquery_intra_night_discovery=$(define_GCP_resources "${topic_intra_night_discovery}")
subscription_bigquery_inter_night_discovery=$(define_GCP_resources "${topic_inter_night_discovery}")

#--- Function used to create (or delete) GCP resources
manage_resources() {
    local mode="$1"  # setup or teardown
    local environment_type="production"

    if [ "$testid" != "False" ]; then
        environment_type="testing"
    fi

    if [ "$mode" = "setup" ]; then
        # create BigQuery dataset and tables
        bq --location="${region}" mk --dataset "${bq_dataset}"
        bq mk --table "${PROJECT_ID}:${bq_dataset}.${intra_night_discovery_table}" "bq_${survey}_${intra_night_discovery_table}_schema.json"
        bq mk --table "${PROJECT_ID}:${bq_dataset}.${inter_night_discovery_table}" "bq_${survey}_${inter_night_discovery_table}_schema.json"

        # create Pub/Sub
        gcloud pubsub topics create "${topic_intra_night_discovery}"
        gcloud pubsub topics create "${topic_inter_night_discovery}"
        gcloud pubsub subscriptions create "${subscription_bigquery_intra_night_discovery}" \
            --topic="${topic_intra_night_discovery}" \
            --bigquery-table="${PROJECT_ID}:${bq_dataset}.${intra_night_discovery_table}" \
            --use-table-schema \
            --max-delivery-attempts=5
        gcloud pubsub subscriptions create "${subscription_bigquery_inter_night_discovery}" \
            --topic="${topic_inter_night_discovery}" \
            --bigquery-table="${PROJECT_ID}:${bq_dataset}.${inter_night_discovery_table}" \
            --use-table-schema \
            --max-delivery-attempts=5

        #--- Create Artifact Registry Repository
        echo
        echo "Configuring Artifact Registry..."
        gcloud artifacts repositories create "${artifact_registry_repo}" --repository-format=docker \
            --location="${region}" --description="Docker repository for Cloud Run services" \
            --project="${PROJECT_ID}"
    else
        if [ "$environment_type" = "testing" ]; then
            bq rm -r -f "${PROJECT_ID}:${bq_dataset}"
            gcloud pubsub topics delete "${topic_intra_night_discovery}"
            gcloud pubsub topics delete "${topic_inter_night_discovery}"
            gcloud pubsub subscriptions delete "${ps_input_subscrip}"
            gcloud pubsub subscriptions delete "${subscription_bigquery_intra_night_discovery}"
            gcloud pubsub subscriptions delete "${subscription_bigquery_inter_night_discovery}"
            gcloud artifacts repositories delete "${artifact_registry_repo}" --location="${region}"
            gcloud run services delete "${cr_module_name}" --region "${region}"
        else
            echo 'ERROR: No testid supplied.'
            echo 'To avoid accidents, this script will not delete production resources.'
            echo 'If that is your intention, you must delete them manually.'
            echo 'Otherwise, please supply a testid.'
            exit 1
        fi
    fi
}

#--- Create (or delete) BigQuery and Pub/Sub resources
echo
echo "Configuring BigQuery, GCS, Pub/Sub resources..."
if [ "$teardown" = "True" ]; then
    manage_resources "teardown"
else
    manage_resources "setup"
fi

#--- Deploy Cloud Run services
echo
echo "Configuring Cloud Run services..."
echo "Creating container image and deploying to Cloud Run..."
moduledir="."  # assumes deploying what's in our current directory
config="${moduledir}/cloudbuild.yaml"
url=$(gcloud builds submit --config="${config}" \
    --substitutions="_SURVEY=${survey},_TESTID=${testid},_MODULE_NAME=${cr_module_name},_REPOSITORY=${artifact_registry_repo}" \
    "${moduledir}" | sed -n 's/^Step #2: Service URL: \(.*\)$/\1/p')

echo "Creating trigger subscription for Cloud Run..."
# WARNING:  This is set to retry failed deliveries. If there is a bug in main.py this will
# retry indefinitely, until the message is deleted manually.
gcloud pubsub subscriptions create "${ps_input_subscrip}" \
    --topic "${trigger_topic}" \
    --message-filter='attributes.ssObject.ssObjectId = "None" AND (attributes.n_previous_detections = "1" OR attributes.n_previous_detections = "2")' \
    --topic-project "${PITTGOOGLE_PROJECT_ID}" \
    --ack-deadline=600 \
    --push-endpoint="${url}${ROUTE_RUN}" \
    --push-auth-service-account="${runinvoker_svcact}"
