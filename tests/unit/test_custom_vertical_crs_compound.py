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
A vertical CRS supplied as WKT must survive into the compound CRS, and onto disk.

The two functions at the top validate that a custom vertical CRS WKT -- one with no
EPSG code, from ``tests/fixtures/custom_vertical_crs.py`` -- is preserved when
building a COMPOUNDCRS, and that GDAL/OSR does not downgrade the vertical datum to
"unknown" in WKT2_2019 output.  The class below writes real files and reads them
back, for EPSG vertical CRSs and for the custom one.
"""
from osgeo import osr
from gttk.utils.srs_logic import get_srs_from_user_input, create_compound_srs
from tests.fixtures.custom_vertical_crs import CUSTOM_VERTICAL_WKT


def test_compound_with_custom_vertical_preserves_vdatum_and_units():
    # Horizontal: Mexico ITRF2008 / UTM zone 13N (EPSG:6368)
    horiz = osr.SpatialReference()
    assert horiz.ImportFromEPSG(6368) == 0

    # Vertical: a datum no registry knows, supplied as WKT to get_srs_from_user_input()
    vert = get_srs_from_user_input(CUSTOM_VERTICAL_WKT)
    assert vert is not None, "Failed to parse the custom vertical CRS from its WKT"
    assert vert.IsVertical(), "The custom vertical CRS should be recognized as vertical"

    # Check vertical WKT2 (standalone) preserves datum name and unit at CS level
    wkt2_vert = vert.ExportToWkt(["FORMAT=WKT2_2019"])
    assert 'VDATUM["Test Local Vertical Datum 2000"]' in wkt2_vert, \
        f"Expected VDATUM name in vertical WKT2, got: {wkt2_vert}"
    assert 'LENGTHUNIT["metre",1]' in wkt2_vert, \
        f"Expected LENGTHUNIT at CS level in vertical WKT2, got: {wkt2_vert}"
    # Axis name is likely preserved in WKT2 (allow any whitespace variants)
    assert "gravity-related height (H)" in wkt2_vert

    # Build compound using the library helper
    compound = create_compound_srs(horiz, vert)

    # Validate the compound WKT2_2019 keeps the VERTCRS with VDATUM and unit
    wkt2_compound = compound.ExportToWkt(["FORMAT=WKT2_2019"])

    assert wkt2_compound.startswith("COMPOUNDCRS["), \
        f"Expected WKT2 COMPOUNDCRS, got: {wkt2_compound[:80]}..."

    # Confirm vertical branch name and datum are preserved
    assert 'VERTCRS["Test Local height"' in wkt2_compound, \
        "Expected VERTCRS name 'Test Local height' in compound WKT2"
    assert 'VDATUM["Test Local Vertical Datum 2000"]' in wkt2_compound, \
        "Expected VDATUM name to be preserved in compound WKT2"

    # Confirm CS-level LENGTHUNIT survives
    assert 'LENGTHUNIT["metre",1]' in wkt2_compound, \
        "Expected LENGTHUNIT metre to be present in compound WKT2"

    # Ensure OSR has not downgraded to unknown vertical datums (WKT1-style artifacts)
    assert 'VERT_DATUM["unknown"' not in wkt2_compound
    assert 'VDATUM["unknown"' not in wkt2_compound

    # Axis naming may be normalized, but the custom label should survive in WKT2
    assert "gravity-related height (H)" in wkt2_compound


def test_compound_manual_contains_vertical_wkt2_when_custom_crs():
    # Additional guard: for a custom vertical CRS with no EPSG code, the compound should
    # still be importable and exportable as valid WKT2_2019.
    horiz = osr.SpatialReference()
    assert horiz.ImportFromEPSG(6368) == 0

    vert = get_srs_from_user_input(CUSTOM_VERTICAL_WKT)
    assert vert is not None and vert.IsVertical()

    compound = create_compound_srs(horiz, vert)
    wkt2 = compound.ExportToWkt(["FORMAT=WKT2_2019"])

    # Basic structure checks
    assert "COMPOUNDCRS[" in wkt2
    assert "PROJCRS[" in wkt2 or "GEOGCRS[" in wkt2
    assert "VERTCRS[" in wkt2

    # No generic/unknown vertical datum fallback in WKT2
    assert "unknown" not in wkt2.lower()

# ---------------------------------------------------------------------------
# The compound CRS must survive the write, not just the WKT construction above.
#
# GTTK writes the resolved SRS onto an in-memory intermediate and then translates
# that to the final COG.  A compound CRS survives those GeoTIFF-key hops only
# partially: the vertical component comes back identified by its *datum*
# (VerticalDatumGeoKey) and loses its own EPSG code, so an EGM2008 DEM ended up
# naming EGM2008 without ever citing EPSG:3855.  Re-asserting the target SRS on
# the final write fixes it.  These tests read the file back.
# ---------------------------------------------------------------------------

import numpy as np
import pytest
from osgeo import gdal

from tests.fixtures.mock_geotiff_factory import MockGeoTIFF

_GLOBAL_GDAL_CONFIG = ('GDAL_NUM_THREADS', 'ESRI_XML_PAM', 'OSR_WKT_FORMAT', 'GTIFF_WRITE_SRS_WKT2')
_config_before_import = {k: gdal.GetConfigOption(k) for k in _GLOBAL_GDAL_CONFIG}
import gttk.tools.optimize_compression as ocmp  # noqa: E402  (import has side effects)
_config_after_import = {k: gdal.GetConfigOption(k) for k in _GLOBAL_GDAL_CONFIG}
for _key, _value in _config_before_import.items():
    gdal.SetConfigOption(_key, _value)

from gttk.utils.preprocessor import VirtualFileManager  # noqa: E402
from gttk.utils.script_arguments import OptimizeArguments  # noqa: E402


@pytest.fixture
def _module_gdal_config():
    """`optimize_compression` sets GDAL config process-wide at import; contain it."""
    restore = {k: gdal.GetConfigOption(k) for k in _GLOBAL_GDAL_CONFIG}
    for key, value in _config_after_import.items():
        gdal.SetConfigOption(key, value)
    yield
    for key, value in restore.items():
        gdal.SetConfigOption(key, value)


def _write_dem_cog(tmp_path, vertical_srs, decimals=2, crs='EPSG:4326'):
    src = tmp_path / "dem.tif"
    out = tmp_path / "dem_cog.tif"
    data = (np.random.default_rng(0).random((1, 600, 600)) * 100).astype(np.float32)
    MockGeoTIFF(width=600, height=600, data_type=gdal.GDT_Float32, crs=crs,
                nodata_value=-32767.0, pixel_data=data).save_to_file(src)
    prior, ocmp.arcMode = ocmp.arcMode, True
    try:
        ocmp._orchestrate_geotiff_optimization(
            OptimizeArguments(input_path=src, output_path=out, product_type='dem',
                              vertical_srs=vertical_srs, algorithm='ZSTD', predictor=2,
                              decimals=decimals, raster_type='point', cog=True,
                              overviews=True, report=False, write_pam_xml=False,
                              open_report=False),
            VirtualFileManager(), None)
    finally:
        ocmp.arcMode = prior
    return src, out


@pytest.mark.slow
@pytest.mark.usefixtures("_module_gdal_config")
class TestCompoundCrsSurvivesTheWrite:

    def test_vertical_epsg_code_is_written(self, tmp_path):
        _, out = _write_dem_cog(tmp_path, "EPSG:4326+3855")
        srs = gdal.Open(str(out)).GetSpatialRef()
        assert srs.GetAuthorityCode('COMPD_CS|VERT_CS') == '3855', (
            "the vertical CRS lost its EPSG code on the way to disk; it reads back as "
            f"{srs.ExportToWkt(['FORMAT=WKT2_2019'])}"
        )

    def test_reads_back_as_the_requested_crs(self, tmp_path):
        _, out = _write_dem_cog(tmp_path, "EPSG:4326+3855")
        want = osr.SpatialReference(); want.SetFromUserInput("EPSG:4326+3855")
        srs = gdal.Open(str(out)).GetSpatialRef()
        # Axis-mapping differs between a file (traditional GIS order) and a fresh
        # EPSG lookup (authority order); that is a read convention, not a difference
        # in the CRS, so compare with it ignored.
        assert srs.IsSame(want, ['IGNORE_DATA_AXIS_TO_SRS_AXIS_MAPPING=YES'])

    def test_assigning_the_crs_does_not_move_the_pixels(self, tmp_path):
        """-a_srs assigns; it must never warp. A shifted geotransform on a DEM is
        the kind of error that stays invisible until someone measures against it."""
        src, out = _write_dem_cog(tmp_path, "EPSG:4326+3855", decimals='none')
        source, result = gdal.Open(str(src)), gdal.Open(str(out))
        assert result.GetGeoTransform() == source.GetGeoTransform()
        assert (result.RasterXSize, result.RasterYSize) == (source.RasterXSize, source.RasterYSize)
        assert result.GetRasterBand(1).Checksum() == source.GetRasterBand(1).Checksum()
        source = result = None

    def test_a_custom_vertical_crs_still_falls_back_to_metadata(self, tmp_path):
        """A vertical CRS with no EPSG code cannot ride in the GeoTIFF keys, so the full
        WKT2 goes into COMPOUND_CRS_WKT2 instead. GTTK no longer ships such a CRS (the
        GGM10 entry it once had was a geoid model, not a datum), but a user can still
        pass one as WKT, and that path must keep working."""
        _, out = _write_dem_cog(tmp_path, CUSTOM_VERTICAL_WKT)
        ds = gdal.Open(str(out))
        stored = ds.GetMetadataItem('COMPOUND_CRS_WKT2') or ''
        name = ds.GetSpatialRef().GetName()
        assert 'Test Local' in stored or 'Test Local' in name, (
            f"custom vertical datum lost: name={name!r}, COMPOUND_CRS_WKT2={stored[:120]!r}")

    def test_navd88_compound_reads_back_intact(self, tmp_path):
        """The case the GGM10 entry was invented for. INEGI distributes 2D
        'Mexico ITRF2008 / UTM zone 13N' (EPSG:6368) rasters, and the vertical datum its
        Norma Técnica defines for Mexico is NAVD88, so the file should come out as
        'Mexico ITRF2008 / UTM zone 13N + NAVD88 height' (EPSG:6368+5703) -- and it needs
        no metadata fallback: the vertical code and the datum name both come back from
        the GeoKeys alone.  (The vertical SRS is given as the datum, not as a ready-made
        compound: handle_srs_logic() joins it to the source's horizontal CRS.)"""
        _, out = _write_dem_cog(tmp_path, "NAVD88", crs='EPSG:6368')
        ds = gdal.Open(str(out))
        srs = ds.GetSpatialRef()
        wkt2 = srs.ExportToWkt(['FORMAT=WKT2_2019'])
        assert srs.IsCompound(), wkt2
        assert srs.GetAuthorityCode('COMPD_CS|PROJCS') == '6368', wkt2
        assert srs.GetAuthorityCode('COMPD_CS|VERT_CS') == '5703', wkt2
        assert 'North American Vertical Datum 1988' in wkt2, wkt2
        assert 'GGM' not in wkt2
        assert ds.GetMetadataItem('COMPOUND_CRS_WKT2') is None, (
            "an EPSG vertical CRS must not trigger the COMPOUND_CRS_WKT2 fallback")
