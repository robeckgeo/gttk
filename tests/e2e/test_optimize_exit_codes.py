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
What ``python -m gttk optimize`` exits with, and what a finished product carries.

A pipeline script that calls the CLI has only the exit status to go on, and it used to be
0 whatever had happened: ``main()`` discarded the tool's return value. Every test here
runs the command in a subprocess, from a working directory that is not the repository,
and reads the status the shell would see: non-zero, with a message that says why, for a
missing or unreadable input, an unknown vertical SRS, an output that cannot be created or
would overwrite the input, an unusable GEO_METADATA record, and a batch with a failed
file; 0 when a requested report was produced.

The last case is the product header round trip: a DEM whose producer already set
TIFFTAG_SOFTWARE and GEO_METADATA, optimized with ``--software-stamp False`` and
``--decimals 2``, has to come out a DEFLATE COG with the same tags byte for byte, the same
NaN pixels, a 1 cm lattice everywhere else, EGM2008 heights, and nothing beside it.
"""

import struct
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import tifffile
from osgeo import gdal, osr

from tests.fixtures.mock_geotiff_factory import MockGeoTIFF

pytestmark = [pytest.mark.slow, pytest.mark.e2e]

#: Nothing but the output: no report, no .aux.xml, no browser.
QUIET = ['--open-report', 'false', '--report', 'false', '--write-pam-xml', 'false']

DEM = ['-t', 'dem', '-s', 'EPSG:5703']

#: The record a producer embedded before calling GTTK.
RECORD = '<?xml version="1.0" encoding="UTF-8"?>\n<record><id>SRC_N00E000_01.xml</id></record>\n'


def run_optimize(cwd, *args, timeout=120):
    """Run `gttk optimize` as a subprocess from `cwd`, never from the repo root."""
    return subprocess.run(
        [sys.executable, '-m', 'gttk', 'optimize', *args],
        capture_output=True, text=True, cwd=cwd, timeout=timeout,
    )


def output_text(result):
    """stdout and stderr joined: the CLI logs through a stdout handler, tracebacks go to stderr."""
    return result.stdout + result.stderr


def _dem(path: Path, size: int = 64, seed: int = 3) -> Path:
    """A small Float32 DEM with a few NoData pixels, deterministic for a seed."""
    rng = np.random.default_rng(seed)
    data = rng.uniform(100.0, 500.0, size=(1, size, size)).astype(np.float32)
    data[0, 0, :4] = -32767.0
    MockGeoTIFF(width=size, height=size, bands=1, data_type=gdal.GDT_Float32,
                crs='EPSG:4326', nodata_value=-32767.0, pixel_data=data).save_to_file(path)
    return path


def _truncated_dem(path: Path) -> Path:
    """A GeoTIFF the batch walker accepts and the run cannot read: an interrupted copy.

    GDAL writes the directory at the front of a file it creates and the pixels after it,
    as long as nothing in the directory changes once the first pixels are written; so this
    one carries no NoData value (MockGeoTIFF sets that after the pixels, and the grown
    directory is rewritten at the end of the file, where the cut would take it). The header
    and the GeoKey directory survive the cut, so ``is_geotiff`` says yes; half of the
    strips are gone, so the first read of them fails inside the run.

    A text file named .tif would not do: GDAL cannot open it, so the walker skips it with
    a warning and the batch exits 0. Nor would a 3-band Byte raster: the batch builds each
    file's arguments while ``input_path`` is still the directory, so the single-band rule
    for 'dem' is never applied to it and it is written as a 3-band COG.
    """
    rng = np.random.default_rng(9)
    data = rng.uniform(100.0, 500.0, size=(1, 256, 256)).astype(np.float32)
    MockGeoTIFF(width=256, height=256, bands=1, data_type=gdal.GDT_Float32,
                crs='EPSG:4326', pixel_data=data).save_to_file(path)
    size = path.stat().st_size
    header = path.read_bytes()[:8]
    first_ifd = struct.unpack('<I' if header[:2] == b'II' else '>I', header[4:8])[0]
    assert first_ifd < size // 2, f'the directory of {path.name} is at {first_ifd}, past the cut'
    with path.open('r+b') as handle:
        handle.truncate(size // 2)
    return path


class TestOptimizeExitCodes:

    def test_missing_input(self, tmp_path):
        result = run_optimize(tmp_path, '-i', 'missing.tif', '-o', 'out.tif', *DEM, *QUIET)

        assert result.returncode != 0
        assert 'not found' in output_text(result)

    def test_input_that_is_not_a_tiff(self, tmp_path):
        (tmp_path / 'notes.tif').write_text('not a tiff\n', encoding='utf-8')

        result = run_optimize(tmp_path, '-i', 'notes.tif', '-o', 'out.tif', *DEM, *QUIET)

        assert result.returncode != 0
        assert not (tmp_path / 'out.tif').exists()

    def test_vertical_srs_that_does_not_exist(self, tmp_path):
        _dem(tmp_path / 'dem_tile.tif')

        result = run_optimize(tmp_path, '-i', 'dem_tile.tif', '-o', 'out.tif',
                              '-t', 'dem', '-s', 'EPSG:999999', *QUIET)

        assert result.returncode != 0
        assert 'Failed to parse vertical SRS: EPSG:999999' in output_text(result)

    def test_output_under_an_existing_file(self, tmp_path):
        _dem(tmp_path / 'dem_tile.tif')
        (tmp_path / 'afile').write_text('x\n', encoding='utf-8')

        result = run_optimize(tmp_path, '-i', 'dem_tile.tif', '-o', 'afile/out.tif', *DEM, *QUIET)

        assert result.returncode != 0
        assert (tmp_path / 'afile').is_file()

    def test_output_equal_to_the_input(self, tmp_path):
        _dem(tmp_path / 'dem_tile.tif')

        result = run_optimize(tmp_path, '-i', 'dem_tile.tif', '-o', 'dem_tile.tif', *DEM, *QUIET)

        assert result.returncode != 0
        assert 'in place' in output_text(result)

    def test_geo_metadata_record_that_is_missing(self, tmp_path):
        """An explicit record is checked when the arguments are: before any work starts."""
        _dem(tmp_path / 'dem_tile.tif')

        result = run_optimize(tmp_path, '-i', 'dem_tile.tif', '-o', 'out.tif', *DEM,
                              '--geo-metadata', 'missing.xml', *QUIET)

        assert result.returncode != 0
        assert 'not found' in output_text(result)
        assert not (tmp_path / 'out.tif').exists()

    def test_geo_metadata_record_that_is_not_xml(self, tmp_path):
        _dem(tmp_path / 'dem_tile.tif')
        (tmp_path / 'bad.xml').write_text('not xml\n', encoding='utf-8')

        result = run_optimize(tmp_path, '-i', 'dem_tile.tif', '-o', 'out.tif', *DEM,
                              '--geo-metadata', 'bad.xml', *QUIET)

        assert result.returncode != 0
        assert 'well-formed' in output_text(result)
        assert not (tmp_path / 'out.tif').exists()

    def test_a_batch_with_one_bad_file_finishes_the_others(self, tmp_path):
        """One of three files fails (see _truncated_dem for which, and why that one): the
        other two are written, the count is reported, and the status is non-zero."""
        tiles = tmp_path / 'tiles'
        tiles.mkdir()
        _dem(tiles / 'dem_tile_01.tif', seed=1)
        _dem(tiles / 'dem_tile_02.tif', seed=2)
        _truncated_dem(tiles / 'bad.tif')

        result = run_optimize(tmp_path, '-i', 'tiles', '-o', 'optimized', *DEM, *QUIET)

        assert result.returncode != 0
        assert '1 of 3 files failed' in output_text(result)
        assert (tmp_path / 'optimized' / 'dem_tile_01.tif').is_file()
        assert (tmp_path / 'optimized' / 'dem_tile_02.tif').is_file()
        assert not (tmp_path / 'optimized' / 'bad.tif').exists()

    def test_an_unknown_option(self, tmp_path):
        """argparse's own status, not the tool's."""
        _dem(tmp_path / 'dem_tile.tif')

        result = run_optimize(tmp_path, '-i', 'dem_tile.tif', '-o', 'out.tif', *DEM,
                              '--no-such-option', *QUIET)

        assert result.returncode == 2
        assert '--no-such-option' in output_text(result)

    def test_a_report_that_is_produced_is_a_success(self, tmp_path):
        """The strict path only bites when the artifact is missing."""
        _dem(tmp_path / 'dem_tile.tif')

        result = run_optimize(tmp_path, '-i', 'dem_tile.tif', '-o', 'out.tif', *DEM,
                              '--report', 'true', '--report-format', 'md',
                              '--open-report', 'false', '--write-pam-xml', 'false')

        assert result.returncode == 0, output_text(result)
        assert (tmp_path / 'out.tif').is_file()
        assert (tmp_path / 'out_comp.md').is_file()


def _product_source(path: Path) -> np.ndarray:
    """A 300x300 Float32 DEM with 3-decimal heights, NaN NoData, and a producer's header.

    The thousandths digit is never 5: float32 cannot hold such a value exactly, and the
    pipeline (rounding through float64) and ``np.round`` on the float32 source could then
    land a cent apart, which would say nothing about the pipeline.
    """
    rng = np.random.default_rng(7)
    thousandths = rng.integers(100000, 500000, size=(300, 300))
    thousandths[thousandths % 10 == 5] += 1
    data = (thousandths / 1000.0).astype(np.float32)
    data[0, 0] = np.float32(123.456)
    data[10, 20] = np.nan
    data[150, 150] = np.nan
    data[299, 299] = np.nan
    MockGeoTIFF(width=300, height=300, bands=1, data_type=gdal.GDT_Float32, crs='EPSG:4326',
                nodata_value=np.nan, pixel_data=data[np.newaxis]).save_to_file(path)
    ds = gdal.Open(str(path), gdal.GA_Update)
    ds.SetMetadataItem('TIFFTAG_SOFTWARE', 'PRODUCER')
    ds.SetMetadataItem('GEO_METADATA', RECORD)
    ds.FlushCache()
    ds = None
    return data


class TestFinishedProduct:

    def test_the_product_header_and_pixels_come_through(self, tmp_path):
        source = _product_source(tmp_path / 'dem_tile.tif')

        result = run_optimize(tmp_path, '-i', 'dem_tile.tif', '-o', 'product.tif',
                              '-t', 'dem', '-s', 'EPSG:3855', '-a', 'DEFLATE', '-p', '2', '-d', '2',
                              '--tile-size', '1024', '--write-pam-xml', 'False', '--report', 'False',
                              '--open-report', 'False', '--software-stamp', 'False')

        assert result.returncode == 0, output_text(result)
        product = tmp_path / 'product.tif'
        assert product.is_file()
        assert not (tmp_path / 'product.tif.aux.xml').exists()

        ds = gdal.Open(str(product))
        try:
            band = ds.GetRasterBand(1)
            # Layout and codec.
            assert ds.GetMetadataItem('LAYOUT', 'IMAGE_STRUCTURE') == 'COG'
            assert ds.GetMetadataItem('COMPRESSION', 'IMAGE_STRUCTURE') == 'DEFLATE'
            assert ds.GetMetadataItem('PREDICTOR', 'IMAGE_STRUCTURE') == '2'
            # A 300 px raster is one tile; the block size need not be 1024, only a size.
            block = band.GetBlockSize()
            assert isinstance(block, list) and len(block) == 2
            assert all(isinstance(side, int) for side in block)
            # NoData, raster type, heights.
            assert np.isnan(band.GetNoDataValue())
            assert ds.GetMetadataItem('AREA_OR_POINT') == 'Point'
            srs = osr.SpatialReference(wkt=ds.GetProjection())
            assert srs.IsCompound()
            assert srs.GetAuthorityCode('VERT_CS') == '3855'
            # The producer's header, untouched.
            assert ds.GetMetadataItem('TIFFTAG_SOFTWARE') == 'PRODUCER'
            # Pixels.
            out = band.ReadAsArray()
        finally:
            band = None
            ds = None

        with tifffile.TiffFile(str(product)) as tif:
            value = tif.pages[0].tags[50909].value
        if isinstance(value, str):
            value = value.encode('utf-8')
        assert value == RECORD.encode('utf-8')

        assert out.shape == source.shape
        assert np.array_equal(np.isnan(out), np.isnan(source))
        assert int(np.isnan(out).sum()) == 3
        finite = np.isfinite(out)
        heights = out[finite].astype(np.float64)
        assert np.all(np.abs(heights * 100 - np.round(heights * 100)) < 0.05)
        expected = np.round(source, 2)[finite].astype(np.float64)
        assert np.all(np.abs(heights - expected) < 0.005)
