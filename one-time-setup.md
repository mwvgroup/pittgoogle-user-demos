# One-Time Setup

(Most links point to pittgoogle-client documentation.)

1. [Install pittgoogle-client](https://mwvgroup.github.io/pittgoogle-client/overview/install.html) (`pip install pittgoogle-client`).

2. [Setup a Google Cloud Project](https://mwvgroup.github.io/pittgoogle-client/overview/project.html) Follow the instructions in the pittgoogle-client docs.
  You only need to create the project; APIs will be enabled by running the setup script below.

3. [Setup a Service Account](https://mwvgroup.github.io/pittgoogle-client/overview/authentication.html#service-account-recommended) and download your credentials. Be sure to also set the environment variables.

4. [Setup the Google Cloud SDK](https://mwvgroup.github.io/pittgoogle-client/overview/adv-setup.html#command-line). Follow the instructions through and activate your service account.

5. Run the project-setup script (listed below) for each example in this repo that you want to follow.

    - [Cloud Run](cloud-run/one-time-setup-for-cloud-run.md)
