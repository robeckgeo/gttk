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
Two optimize runs in one process at the same time give the files one after the other gives.

``gttk optimize`` kept its state in module globals: the GDAL configuration was set
process-wide at import, the progress bar remembered its last percentage in a module
dictionary, and ArcGIS mode was a module flag. Two runs on two threads could trample each
other's settings and each other's output. The configuration is now applied thread-locally
for the duration of each run and the progress bar is an object per run, so a host (an
ArcGIS toolbox, a batch service) may run several at once.

This pins what that promise means: a DEM and an image optimized on two threads at once
are byte for byte, output and .aux.xml, what the same two runs produce one after the other
on the main thread; the main thread never sees the workers' settings; and nothing is left
in /vsimem when they finish.
"""

import hashlib
import threading
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from osgeo import gdal

import gttk.tools.optimize_compression as ocmp
from gttk.utils.script_arguments import OptimizeArguments
from tests.fixtures.mock_geotiff_factory import MockGeoTIFF

pytestmark = [pytest.mark.slow, pytest.mark.integration]

#: Large enough that the two runs overlap for most of their length, small enough to be quick.
SIZE = 1024


def _dem(path: Path) -> Path:
    """A Float32 DEM with 3-decimal heights and a block of NoData, the same every time."""
    rng = np.random.default_rng(21)
    data = np.round(rng.uniform(100.0, 500.0, size=(1, SIZE, SIZE)), 3).astype(np.float32)
    data[0, :8, :8] = -32767.0
    MockGeoTIFF(width=SIZE, height=SIZE, bands=1, data_type=gdal.GDT_Float32, crs='EPSG:32614',
                nodata_value=-32767.0, pixel_data=data).save_to_file(path)
    return path


def _image(path: Path) -> Path:
    """A 3-band Byte image, the same every time."""
    rng = np.random.default_rng(22)
    data = rng.integers(0, 256, size=(3, SIZE, SIZE), dtype=np.uint8)
    MockGeoTIFF(width=SIZE, height=SIZE, bands=3, data_type=gdal.GDT_Byte, crs='EPSG:32614',
                photometric='RGB', pixel_data=data).save_to_file(path)
    return path


def _dem_arguments(source: Path, output: Path) -> OptimizeArguments:
    return OptimizeArguments(input_path=source, output_path=output, product_type='dem',
                             vertical_srs='EPSG:5703', algorithm='DEFLATE', decimals=2,
                             report=False, write_pam_xml=True, open_report=False, arc_mode=True)


def _image_arguments(source: Path, output: Path) -> OptimizeArguments:
    return OptimizeArguments(input_path=source, output_path=output, product_type='image',
                             algorithm='JPEG', report=False, write_pam_xml=True,
                             open_report=False, arc_mode=True)


def _digests(output: Path):
    """md5 of the output and of its .aux.xml."""
    sidecar = output.with_name(output.name + '.aux.xml')
    return (hashlib.md5(output.read_bytes()).hexdigest(),
            hashlib.md5(sidecar.read_bytes()).hexdigest())


@pytest.fixture(scope='class')
def runs(tmp_path_factory):
    """The two runs on two threads at once, then the same two one after the other.

    What the main thread saw and what /vsimem held are recorded the moment the threads
    are joined, before the sequential runs can tidy anything.
    """
    root = tmp_path_factory.mktemp('concurrent')
    dem = _dem(root / 'dem_tile.tif')
    image = _image(root / 'ortho_tile.tif')
    together = root / 'together'
    alone = root / 'alone'
    together.mkdir()
    alone.mkdir()

    results = {}
    errors = {}

    def run(name, args):
        try:
            results[name] = ocmp.optimize_compression(args)
        except BaseException as e:  # noqa: BLE001 - re-raised in the test, with its traceback
            errors[name] = e

    threads = [
        threading.Thread(target=run, args=('dem', _dem_arguments(dem, together / 'dem_tile.tif')),
                         name='optimize-dem'),
        threading.Thread(target=run, args=('image', _image_arguments(image, together / 'ortho_tile.tif')),
                         name='optimize-image'),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    main_thread_wkt_format = gdal.GetConfigOption('OSR_WKT_FORMAT')
    leftovers = [name for name in (gdal.ReadDirRecursive('/vsimem/') or []) if 'compress_' in name]

    sequential = {
        'dem': ocmp.optimize_compression(_dem_arguments(dem, alone / 'dem_tile.tif')),
        'image': ocmp.optimize_compression(_image_arguments(image, alone / 'ortho_tile.tif')),
    }

    return SimpleNamespace(results=results, errors=errors, together=together, alone=alone,
                           main_thread_wkt_format=main_thread_wkt_format, leftovers=leftovers,
                           sequential=sequential)


class TestTwoRunsAtOnce:

    def test_both_runs_return_0(self, runs):
        """An exception on a worker thread is raised here, with its own traceback."""
        for name, error in runs.errors.items():
            raise AssertionError(f'the {name} run raised on its thread') from error
        assert runs.results == {'dem': 0, 'image': 0}
        assert runs.sequential == {'dem': 0, 'image': 0}

    def test_the_dem_matches_the_sequential_run(self, runs):
        assert _digests(runs.together / 'dem_tile.tif') == _digests(runs.alone / 'dem_tile.tif')

    def test_the_image_matches_the_sequential_run(self, runs):
        assert _digests(runs.together / 'ortho_tile.tif') == _digests(runs.alone / 'ortho_tile.tif')

    def test_the_main_thread_never_saw_the_workers_settings(self, runs):
        """OSR_WKT_FORMAT is set for the duration of a run, on the thread that runs it."""
        assert runs.main_thread_wkt_format is None

    def test_nothing_is_left_in_vsimem(self, runs):
        assert runs.leftovers == []
