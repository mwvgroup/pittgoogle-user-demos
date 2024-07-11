# pittgoogle-user-demos

This repo contains tutorials for accessing astronomical data that is served by the Pitt-Google Alert Broker through Google Cloud.
The data is available both from within Google Cloud and outside of it.
These tutorials demonstrate both.
For a listing of the specific data products that we serve, see [Pitt-Google Data Listings](https://mwvgroup.github.io/pittgoogle-client/listings.html).

Tutorials in this repo show how to use the `pittgoogle-client` python package along with various Google Cloud services and tools.
Concepts include:

- Basic access to data in
    - Pub/Sub : Real-time alert streams. Accessible from almost anywhere. Well-integrated with other Cloud data storage and compute services.
    - BigQuery : Tabular data. SQL accessible. Accepts streaming inserts.
    - Cloud Storage : Buckets holding alert packets in Avro format.
- Process Live Alert Streams
    - Cloud Run : Compute service. Use this to process an alert stream in real time.

## Setup

At a minimum, you will need to install the `pittgoogle-client` package and obtain/configure credentials for a Google Cloud project.
If this is your first time, please follow the [one-time setup](https://mwvgroup.github.io/pittgoogle-client/one-time-setup.html) instructions.
The process is very similar to that of other Alert Brokers except that here you will obtain authentication through Google Cloud, not through Pitt-Google Broker.
Skip the "Optional" steps for now; you will be directed to complete them at the beginning of a tutorial if needed.

## Tutorials

- [Cloud Run](cloud-run/README.md)
