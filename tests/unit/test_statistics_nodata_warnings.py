#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ******************************************************************************
# Project: GeoTIFF ToolKit (GTTK)
# Author: Eric Robeck <robeckgeo@gmail.com>
#
# Copyright (c) 2026, Eric Robeck
# Licensed under the MIT License
# ******************************************************************************

"""
A NoData value the statistics calculator cannot read as a number is reported, not
silently used as it came.

The calculator accepts a per-band NoData string ("-9999 -9999") and converts the band's
entry; when the conversion failed it fell back to the unconverted value without a word,
so masking proceeded against a string.
"""

import logging

import numpy as np
import pytest
from osgeo import gdal

from gttk.utils.statistics import calculate_statistics

pytestmark = pytest.mark.unit


def test_an_unparsable_per_band_nodata_is_warned_about(monkeypatch, caplog):
    ds = gdal.GetDriverByName('MEM').Create('', 8, 8, 2, gdal.GDT_Float32)
    for band in (1, 2):
        ds.GetRasterBand(band).WriteArray(np.full((8, 8), float(band), dtype=np.float32))
    monkeypatch.setattr(gdal.Band, 'GetNoDataValue', lambda self: '-9999 abc')
    with caplog.at_level(logging.WARNING):
        calculate_statistics(ds)
    assert 'could not be read as one number per band' in caplog.text
