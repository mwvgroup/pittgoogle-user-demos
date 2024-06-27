.. _cloud storage:

Cloud Storage Tutorial
==============================

.. contents:: Table of Contents
    :depth: 1
    :local:

This tutorial covers access via two methods: pittgoogle-client (with some direct use
of the Google Cloud API), and the gsutil CLI.

Prerequisites
-------------

1. Complete the initial setup. In particular, be sure to:

   -  :ref:`install` and/or :ref:`Install the command-line tools <install gcp cli>`.
   -  :ref:`service account`
   -  :ref:`Set your environment variables <set env vars>`

Python
------

Setup
~~~~~

Imports

.. code:: python

    import fastavro
    from google.cloud import storage
    from matplotlib import pyplot as plt
    import os
    from pathlib import Path
    import pittgoogle

Name some things

.. code:: python

    # fill in the path to the local directory to which you want to download files
    local_dir = ''

    my_project_id = os.getenv('GOOGLE_CLOUD_PROJECT')
    pgb_project_id = pittgoogle.utils.ProjectIds.pittgoogle

Download files
~~~~~~~~~~~~~~

Download alerts for a given ``objectId``

.. code:: python

    objectId = 'ZTF17aaackje'
    bucket_name = f'{pgb_project_id}-ztf-alert_avros'

    # Create a client and request a list of files
    storage_client = storage.Client(my_project_id)
    bucket = storage_client.get_bucket(bucket_name)
    blobs = bucket.list_blobs(prefix=objectId)

    # download the files
    for blob in blobs:
        local_path = f'{local_dir}/{blob.name}'
        blob.download_to_filename(local_path)
        print(f'Downloaded {local_path}')

Open a file
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Load to a dict:

.. code:: python

    paths = Path(local_dir).glob('*.avro')
    for path in paths:
        with open(path, 'rb') as fin:
            alert_list = [r for r in fastavro.reader(fin)]
        break
    alert_dict = alert_list[0]  # extract the single alert packet

    print(alert_dict.keys())

Load to a pandas DataFrame:

.. code:: python

    lightcurve_df = pittgoogle.utils.Cast.alert_dict_to_dataframe(alert_dict)


Plot light curves and cutouts
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

See :ref:`ztf figures`

Command line
------------

See also:

-   `Quickstart: Using the gsutil
    tool <https://cloud.google.com/storage/docs/quickstart-gsutil>`__
-   `gsutil cp <https://cloud.google.com/storage/docs/gsutil/commands/cp>`__

Get help

.. code:: bash

    gsutil help
    gsutil help cp

Download a single file

.. code:: bash

    # fill in the path to the local directory to which you want to download files
    local_dir=
    # fill in the name of the file you want. see above for the syntax
    file_name=
    # file_name=ZTF17aaackje.1563161493315010012.ztf_20210413_programid1.avro
    avro_bucket="${pgb_project_id}-ztf-alert_avros"

    gsutil cp "gs://${avro_bucket}/${file_name}" ${local_dir}/.
