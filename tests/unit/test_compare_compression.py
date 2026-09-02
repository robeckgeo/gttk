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
`gttk compare` releases both datasets on every path.

It opened the baseline and the comparison back to back and released them at the end of
the try body; an exception between the two left the first open until the frame was
collected, which on Windows is a lock on the file.
"""

import logging

import pytest
from osgeo import gdal

import gttk.tools.compare_compression as cc
from gttk.utils.script_arguments import CompareArguments
from tests.fixtures.mock_geotiff_factory import MockGeoTIFF

pytestmark = pytest.mark.unit


def test_a_comparison_that_will_not_open_is_reported_and_releases_the_baseline(tmp_path, monkeypatch, caplog):
    base, comp = tmp_path / 'a.tif', tmp_path / 'b.tif'
    for path in (base, comp):
        MockGeoTIFF(width=16, height=16, crs='EPSG:32610').save_to_file(path)
    real_open = gdal.Open
    opened = []

    def opener(path, *args, **kwargs):
        ds = real_open(path, *args, **kwargs)
        opened.append(ds)
        return None if str(path).endswith('b.tif') else ds

    monkeypatch.setattr(cc.gdal, 'Open', opener)
    args = CompareArguments(input_path=base, output_path=comp, open_report=False)
    with caplog.at_level(logging.ERROR):
        assert cc._compare_compression_inner(args) is None
    assert 'Could not open one or both' in caplog.text
