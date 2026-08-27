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
How a vertical datum without an EPSG code survives -- and does not survive -- a GeoTIFF.

This began as an exploration and keeps its prints, because the WKT it shows is the
argument for GTTK's design.  GeoTIFF GeoKeys identify a vertical CRS by EPSG code, so
a datum the registry does not know comes back as VDATUM["unknown"] no matter what was
written (Test 1).  Storing the full WKT2 in a metadata item survives the round trip
and imports back with its datum name intact (Test 2), which is why GTTK's writers set
COMPOUND_CRS_WKT2 for exactly this case and the metadata reader looks for it.

The vertical CRS is the fictional one from ``tests/fixtures/custom_vertical_crs.py``.
It used to be a hand-written "GGM10 height" with a stale ``ID["PROJ", ...]``; GGM10
is a geoid model -- the transformation onto NAVD88, Mexico's vertical datum -- not a
datum, and GTTK no longer offers it as one.
"""
import tempfile
from pathlib import Path

import numpy as np
import pytest
from osgeo import gdal, osr

from tests.fixtures.custom_vertical_crs import (
    CUSTOM_VERTICAL_WKT,
    CUSTOM_VERTICAL_DATUM_NAME,
)

pytestmark = pytest.mark.unit


def test_custom_vertical_datum_storage():
    """A custom vertical datum is lost in the GeoKeys and recovered from metadata."""

    # Create a simple test raster
    width, height = 100, 100
    data = np.random.rand(height, width).astype(np.float32)

    # Create horizontal SRS (EPSG:6368)
    horiz_srs = osr.SpatialReference()
    horiz_srs.ImportFromEPSG(6368)

    # Create the custom vertical SRS: no EPSG code, so the GeoKeys cannot name it
    vert_srs = osr.SpatialReference()
    assert vert_srs.ImportFromWkt(CUSTOM_VERTICAL_WKT) == 0
    assert vert_srs.IsVertical()

    # Create compound CRS
    compound_srs = osr.SpatialReference()
    assert compound_srs.SetCompoundCS(
        "Mexico ITRF2008 / UTM zone 13N + Test Local height",
        horiz_srs,
        vert_srs
    ) == 0
    full_wkt = compound_srs.ExportToWkt(['FORMAT=WKT2_2019'])
    assert f'VDATUM["{CUSTOM_VERTICAL_DATUM_NAME}"]' in full_wkt

    print("\n" + "="*80)
    print("ORIGINAL COMPOUND CRS (before writing to file):")
    print("="*80)
    print(full_wkt)

    with tempfile.TemporaryDirectory() as tmpdir:

        # Test 1: Standard GeoTIFF with GEOTIFF_VERSION=1.1, GeoKeys only
        print("\n" + "="*80)
        print("TEST 1: GeoTIFF 1.1 (WKT2 support)")
        print("="*80)
        tif_path = Path(tmpdir) / "test_geotiff11.tif"
        driver = gdal.GetDriverByName('GTiff')
        ds = driver.Create(
            str(tif_path), width, height, 1, gdal.GDT_Float32,
            options=['GEOTIFF_VERSION=1.1']
        )
        ds.SetProjection(compound_srs.ExportToWkt())
        ds.GetRasterBand(1).WriteArray(data)
        ds.FlushCache()
        ds = None

        # Read back
        ds = gdal.Open(str(tif_path))
        read_srs = ds.GetSpatialRef()
        print("\nRead back from GeoTIFF 1.1:")
        print(read_srs.ExportToWkt(['FORMAT=WKT2_2019']))
        assert read_srs.IsCompound(), "the compound structure itself must survive"

        # The datum name does not: the GeoKeys carry a code, and there is none. What
        # comes back is informational here (GDAL's behaviour, not GTTK's), and it is
        # the loss that Test 2 repairs.
        vert_name = read_srs.GetAttrValue("COMPD_CS|VERT_CS")
        vdatum_name = read_srs.GetAttrValue("COMPD_CS|VERT_CS|VERT_DATUM")
        print(f"\nVERT_CS name: {vert_name}")
        print(f"VDATUM name: {vdatum_name}")
        ds = None

        # Test 2: Store the full WKT2 in a GDAL metadata item as well
        print("\n" + "="*80)
        print("TEST 2: Store full WKT in TIFF metadata")
        print("="*80)
        tif_path2 = Path(tmpdir) / "test_with_metadata.tif"
        ds = driver.Create(
            str(tif_path2), width, height, 1, gdal.GDT_Float32,
            options=['GEOTIFF_VERSION=1.1']
        )
        ds.SetProjection(compound_srs.ExportToWkt())

        # Store the full WKT in metadata, as GTTK's writers do for a non-EPSG vertical CRS
        ds.SetMetadataItem('COMPOUND_CRS_WKT2', full_wkt)

        ds.GetRasterBand(1).WriteArray(data)
        ds.FlushCache()
        ds = None

        # Read back
        ds = gdal.Open(str(tif_path2))
        stored_wkt = ds.GetMetadataItem('COMPOUND_CRS_WKT2')
        ds = None
        assert stored_wkt is not None, "COMPOUND_CRS_WKT2 did not survive the write"
        assert stored_wkt == full_wkt, "the metadata round-trip must return the WKT verbatim"
        print("\nSuccessfully retrieved custom WKT from metadata:")
        print(stored_wkt[:200] + "...")

        # Import it: the datum name is back
        test_srs = osr.SpatialReference()
        assert test_srs.ImportFromWkt(stored_wkt) == 0
        vdatum_from_metadata = test_srs.GetAttrValue("COMPD_CS|VERT_CS|VERT_DATUM")
        print(f"\nVDATUM from metadata WKT: {vdatum_from_metadata}")
        assert vdatum_from_metadata == CUSTOM_VERTICAL_DATUM_NAME

        # Test 3: PROJ string representation, for the record
        print("\n" + "="*80)
        print("TEST 3: Check PROJ string representation")
        print("="*80)
        proj_string = compound_srs.ExportToProj4()
        print(f"PROJ string: {proj_string}")


if __name__ == "__main__":
    test_custom_vertical_datum_storage()
