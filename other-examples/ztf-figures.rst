.. _ztf figures:

ZTF Figures Tutorial
==============================

.. contents:: Table of Contents
    :depth: 1
    :local:

This tutorial demonstrates plotting ZTF cutouts and light curves.
It is based heavily on https://github.com/ZwickyTransientFacility/ztf-avro-alert/blob/master/notebooks/Filtering_alerts.ipynb.

Prerequisites
-------------

1. Load a ZTF alert to a dict or a pandas DataFrame. For examples, see:

   -  :ref:`cloud storage`
   -  :ref:`bigquery`

Imports
---------

.. code:: python

    import gzip
    import io
    from typing import Optional

    import aplpy
    import matplotlib as mpl
    import numpy as np
    import pandas as pd
    from astropy.io import fits
    from astropy.time import Time
    from matplotlib import pyplot as plt

    import pittgoogle

Plot a Light Curve
------------------

.. code:: python

    def plot_lightcurve(lightcurve_df: pd.DataFrame, days_ago: bool = True):
        """Plot the per-band light curve of a single ZTF object.
        Adapted from:
        https://github.com/ZwickyTransientFacility/ztf-avro-alert/blob/master/notebooks/Filtering_alerts.ipynb

        Parameters
        ----------
        lightcurve_df
            Lightcurve history of a ZTF object. Must contain columns
            ['jd','fid','magpsf','sigmapsf','diffmaglim']
        days_ago
            If True, x-axis will be number of days in the past.
            Else x-axis will be Julian date.
        """

        filter_code = pittgoogle.utils.ztf_fid_names()  # dict
        filter_color = {1: "green", 2: "red", 3: "pink"}

        # set the x-axis (time) details
        if days_ago:
            now = Time.now().jd
            t = lightcurve_df.jd - now
            xlabel = "Days Ago"
        else:
            t = lightcurve_df.jd
            xlabel = "Time (JD)"

        # plot lightcurves by band
        for fid, color in filter_color.items():
            # plot detections in this filter:
            w = (lightcurve_df.fid == fid) & ~lightcurve_df.magpsf.isnull()
            if np.sum(w):
                label = f"{fid}: {filter_code[fid]}"
                kwargs = {"fmt": ".", "color": color, "label": label}
                plt.errorbar(t[w], lightcurve_df.loc[w, "magpsf"], lightcurve_df.loc[w, "sigmapsf"], **kwargs)
            # plot nondetections in this filter
            wnodet = (lightcurve_df.fid == fid) & lightcurve_df.magpsf.isnull()
            if np.sum(wnodet):
                plt.scatter(
                    t[wnodet],
                    lightcurve_df.loc[wnodet, "diffmaglim"],
                    marker="v",
                    color=color,
                    alpha=0.25,
                )

        plt.gca().invert_yaxis()
        plt.xlabel(xlabel)
        plt.ylabel("Magnitude")
        plt.legend()

.. code:: python

    plot_lightcurve(lightcurve_df)

Plot Cutouts
------------

.. code:: python

    def plot_stamp(stamp, fig=None, subplot=None, **kwargs):
        """Adapted from:
        https://github.com/ZwickyTransientFacility/ztf-avro-alert/blob/master/notebooks/Filtering_alerts.ipynb
        """

        with gzip.open(io.BytesIO(stamp), "rb") as f:
            with fits.open(io.BytesIO(f.read())) as hdul:
                if fig is None:
                    fig = plt.figure(figsize=(4, 4))
                if subplot is None:
                    subplot = (1, 1, 1)
                ffig = aplpy.FITSFigure(hdul[0], figure=fig, subplot=subplot, **kwargs)
                ffig.show_grayscale(stretch="arcsinh")
        return ffig


    def plot_cutouts(alert_dict):
        """Adapted from:
        https://github.com/ZwickyTransientFacility/ztf-avro-alert/blob/master/notebooks/Filtering_alerts.ipynb
        """

        # fig, axes = plt.subplots(1,3, figsize=(12,4))
        fig = plt.figure(figsize=(12, 4))
        for i, cutout in enumerate(["Science", "Template", "Difference"]):
            stamp = alert_dict["cutout{}".format(cutout)]["stampData"]
            ffig = plot_stamp(stamp, fig=fig, subplot=(1, 3, i + 1))
            ffig.set_title(cutout)


.. code:: python

    plot_cutouts(alert_dict)
    plt.show(block=False)
