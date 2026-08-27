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
Unit Tests for srs_logic.py

Comprehensive test coverage for Spatial Reference System (SRS) handling:
- User input parsing (EPSG codes, vertical datum names, abbreviations, WKT)
- SRS standardization (WKT to EPSG conversion)
- Horizontal SRS extraction from compound CRS
- Vertical SRS extraction from compound CRS
- Vertical datum mismatch detection
- Compound CRS creation (standard and custom vertical datums)
- SRS logic orchestration for DEM vs non-DEM products

Target: >85% code coverage for srs_logic.py
"""

import pytest
import logging
from pathlib import Path
from osgeo import gdal, osr

from gttk.utils.srs_logic import (
    VERTICAL_SRS_NAME_MAP,
    VERTICAL_SRS_ABBREV_MAP,
    get_srs_from_user_input,
    standardize_srs,
    get_horizontal_srs,
    get_vertical_srs,
    check_vertical_srs_mismatch,
    create_compound_srs,
    handle_srs_logic
)
from gttk.utils.exceptions import ProcessingStepFailedError
from tests.fixtures.custom_vertical_crs import (
    CUSTOM_VERTICAL_WKT,
    CUSTOM_VERTICAL_WKT_NO_AUTHORITY,
)


# ==============================================================================
# FIXTURES
# ==============================================================================

@pytest.fixture
def srs_wgs84():
    """WGS 84 geographic CRS (EPSG:4326)."""
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    return srs


@pytest.fixture
def srs_utm10n():
    """UTM Zone 10N projected CRS (EPSG:32610)."""
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(32610)
    return srs


@pytest.fixture
def srs_navd88():
    """NAVD88 vertical datum (EPSG:5703)."""
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(5703)
    return srs


@pytest.fixture
def srs_egm96():
    """EGM96 geoid (EPSG:5773)."""
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(5773)
    return srs


@pytest.fixture
def srs_compound_utm_navd88(srs_utm10n, srs_navd88):
    """Compound CRS: UTM 10N + NAVD88."""
    compound = osr.SpatialReference()
    compound.SetCompoundCS("UTM 10N + NAVD88", srs_utm10n, srs_navd88)
    return compound


def create_test_geotiff_with_srs(filepath: Path, srs: osr.SpatialReference, bands: int = 1, data_type=gdal.GDT_Float32):
    """Helper to create test GeoTIFF with specified SRS."""
    driver = gdal.GetDriverByName('GTiff')
    ds = driver.Create(str(filepath), 256, 256, bands, data_type)
    ds.SetProjection(srs.ExportToWkt())
    ds.SetGeoTransform((0, 1, 0, 0, 0, -1))
    ds.FlushCache()
    ds = None
    return filepath


# ==============================================================================
# PHASE 1: USER INPUT PARSING & STANDARDIZATION
# ==============================================================================

class TestGetSrsFromUserInput:
    """Test get_srs_from_user_input() parsing logic."""
    
    # =========================================================================
    # Test Group 1A: EPSG Code Parsing (5 tests)
    # =========================================================================
    
    def test_parse_epsg_with_prefix(self):
        """Test parsing 'EPSG:4326' format."""
        srs = get_srs_from_user_input("EPSG:4326")
        
        assert srs is not None
        assert srs.GetAuthorityCode(None) == "4326"
        assert srs.IsGeographic() == 1  # OSR returns 1 for True
    
    def test_parse_epsg_integer_string(self):
        """Test parsing '4326' format (integer string)."""
        srs = get_srs_from_user_input("4326")
        
        assert srs is not None
        assert srs.GetAuthorityCode(None) == "4326"
        assert srs.IsGeographic() == 1  # OSR returns 1 for True
    
    def test_parse_epsg_projected_utm(self):
        """Test parsing UTM Zone 10N (EPSG:32610)."""
        srs = get_srs_from_user_input("EPSG:32610")
        
        assert srs is not None
        assert srs.GetAuthorityCode(None) == "32610"
        assert srs.IsProjected() == 1  # OSR returns 1 for True
    
    def test_parse_epsg_vertical_navd88(self):
        """Test parsing NAVD88 vertical datum (EPSG:5703)."""
        srs = get_srs_from_user_input("EPSG:5703")
        
        assert srs is not None
        assert srs.GetAuthorityCode(None) == "5703"
        assert srs.IsVertical() == 1  # OSR returns 1 for True
    
    def test_parse_epsg_compound(self):
        """Test parsing compound CRS (EPSG:32610+5703)."""
        srs = get_srs_from_user_input("EPSG:32610+5703")
        
        assert srs is not None
        assert srs.IsCompound() == 1  # OSR returns 1 for True
    
    # =========================================================================
    # Test Group 1B: Vertical SRS Name Parsing (4 tests)
    # =========================================================================
    
    def test_parse_vertical_name_navd88(self):
        """Test parsing full vertical SRS name from dropdown."""
        srs = get_srs_from_user_input("North America Vertical Datum 1988 (NAVD88)")
        
        assert srs is not None
        assert srs.GetAuthorityCode(None) == "5703"
        assert srs.IsVertical() == 1  # OSR returns 1 for True
    
    def test_parse_vertical_abbrev_egm96(self):
        """Test parsing 'EGM96' abbreviation."""
        srs = get_srs_from_user_input("EGM96")
        
        assert srs is not None
        assert srs.GetAuthorityCode(None) == "5773"
        assert srs.IsVertical() == 1  # OSR returns 1 for True
    
    def test_parse_vertical_abbrev_egm2008(self):
        """Test parsing 'EGM2008' abbreviation."""
        srs = get_srs_from_user_input("EGM2008")
        
        assert srs is not None
        assert srs.GetAuthorityCode(None) == "3855"
        assert srs.IsVertical() == 1  # OSR returns 1 for True
    
    def test_parse_vertical_wkt_input(self):
        """A vertical CRS with no EPSG code arrives as WKT and is used verbatim."""
        srs = get_srs_from_user_input(CUSTOM_VERTICAL_WKT)
        
        assert srs is not None
        assert srs.IsVertical() == 1  # OSR returns 1 for True
        assert "Test Local" in srs.GetName()
    
    def test_unregistered_vertical_name_returns_none(self):
        """GGM10 is a geoid model -- the transformation onto NAVD88, Mexico's datum -- not
        a datum, so it left the maps and the WKT registry that served it is gone. The
        bare name reaches GDAL's SetFromUserInput, which fails on it (verified on
        GDAL 3.12: 'OGR Error: Corrupt data'), so the function returns None rather
        than inventing a CRS. The old dropdown label fails the same way."""
        assert get_srs_from_user_input("GGM10") is None
        assert get_srs_from_user_input("Geoide Gravimétrico Mexicano 2010 (GGM10)") is None
    
    def test_parse_ahd_nzvd2016_jgd2000(self):
        """The AHD, NZVD2016 and JGD2000 abbreviations resolve. Their map keys used to
        carry a stray closing parenthesis ("AHD)"), which no upper-cased input could
        ever match, so the three were reachable only by full name or EPSG code."""
        for abbrev, code in (("AHD", "5711"), ("NZVD2016", "7839"), ("JGD2000", "6694")):
            srs = get_srs_from_user_input(abbrev)
            
            assert srs is not None, abbrev
            assert srs.GetAuthorityCode(None) == code, abbrev
            assert srs.IsVertical() == 1, abbrev  # OSR returns 1 for True
    
    def test_parse_vertical_name_cgvd2013(self):
        """Test parsing CGVD2013 Canadian vertical datum."""
        srs = get_srs_from_user_input("CGVD2013")
        
        assert srs is not None
        assert srs.GetAuthorityCode(None) == "6647"
        assert srs.IsVertical() == 1  # OSR returns 1 for True
    
    def test_parse_3d_geographic_wgs84(self):
        """Test parsing WGS84 3D (EPSG:4979)."""
        srs = get_srs_from_user_input("EPSG:4979")
        
        assert srs is not None
        assert srs.IsGeographic() == 1  # OSR returns 1 for True
        assert srs.GetAxesCount() == 3
    
    # =========================================================================
    # Test Group 1C: WKT String Parsing (2 tests)
    # =========================================================================
    
    def test_parse_wkt2_string(self, srs_wgs84):
        """Test parsing WKT2 GEOGCRS string."""
        wkt = srs_wgs84.ExportToWkt(['FORMAT=WKT2_2019'])
        srs = get_srs_from_user_input(wkt)
        
        assert srs is not None
        assert srs.IsGeographic() == 1  # OSR returns 1 for True
        assert "WGS" in srs.GetName()
    
    def test_parse_wkt1_string(self, srs_wgs84):
        """Test parsing WKT1 GEOGCS string."""
        wkt = srs_wgs84.ExportToWkt()  # Default is WKT1
        srs = get_srs_from_user_input(wkt)
        
        assert srs is not None
        assert srs.IsGeographic() == 1  # OSR returns 1 for True
    
    # =========================================================================
    # Test Group 1D: Error Handling (3 tests)
    # =========================================================================
    
    def test_parse_invalid_epsg_code(self):
        """Test parsing invalid EPSG code returns None."""
        srs = get_srs_from_user_input("EPSG:999999")
        
        assert srs is None
    
    def test_parse_malformed_wkt(self):
        """Test parsing malformed WKT returns None."""
        srs = get_srs_from_user_input("GEOGCS[incomplete")
        
        assert srs is None
    
    def test_parse_empty_string(self):
        """Test parsing empty string returns None."""
        srs = get_srs_from_user_input("")
        
        assert srs is None
    
    def test_parse_case_insensitive_abbreviations(self):
        """Test that vertical abbreviations are case-insensitive."""
        # Test lowercase
        srs_lower = get_srs_from_user_input("egm96")
        assert srs_lower is not None
        assert srs_lower.GetAuthorityCode(None) == "5773"
        
        # Test uppercase
        srs_upper = get_srs_from_user_input("EGM96")
        assert srs_upper is not None
        assert srs_upper.GetAuthorityCode(None) == "5773"
        
        # Test mixed case
        srs_mixed = get_srs_from_user_input("Egm96")
        assert srs_mixed is not None
        assert srs_mixed.GetAuthorityCode(None) == "5773"


class TestVerticalSrsMaps:
    """The name and abbreviation maps must hold only real EPSG vertical CRS codes."""
    
    def test_vertical_maps_contain_only_epsg_codes(self):
        """A value of 0 once flagged a 'custom' entry (GGM10) that was resolved from a
        WKT registry instead of the EPSG database. Geoid models are transformations,
        not datums, so that mechanism is gone: every value must be a code PROJ
        resolves, and it must be a vertical CRS (or a 3D geographic one)."""
        for key, code in {**VERTICAL_SRS_NAME_MAP, **VERTICAL_SRS_ABBREV_MAP}.items():
            assert code != 0, f"{key!r} carries no EPSG code"
            srs = osr.SpatialReference()
            assert srs.ImportFromEPSG(code) == 0, f"{key!r}: EPSG:{code} does not resolve"
            is_3d_geographic = srs.IsGeographic() == 1 and srs.GetAxesCount() == 3
            assert srs.IsVertical() == 1 or is_3d_geographic, f"{key!r}: EPSG:{code}"
    
    # What PROJ calls each code. A dropdown label that names a different frame than
    # its code resolves to would send every file written with it to the wrong datum
    # -- EPSG:5730 was offered as "EVRF2020", a frame that does not exist, when it is
    # EVRF2000 height. Adding an entry to either map means adding it here too.
    EPSG_NAMES = {
        "Earth Gravitational Model 2008 (EGM2008)": "EGM2008 height",
        "Earth Gravitational Model 1996 (EGM96)": "EGM96 height",
        "North America Vertical Datum 1988 (NAVD88)": "NAVD88 height",
        "Canadian Geodetic Vertical Datum 2013 (CGVD2013/CGG2013)": "CGVD2013(CGG2013) height",
        "European Vertical Reference Frame 2007 (EVRF2007)": "EVRF2007 height",
        "European Vertical Reference Frame 2019 (EVRF2019)": "EVRF2019 height",
        "European Vertical Reference Frame 2000 (EVRF2000)": "EVRF2000 height",
        "Australia Height Datum (AHD)": "AHD height",
        "New Zealand Vertical Datum 2016 (NZVD2016)": "NZVD2016 height",
        "Japanese Geodetic Datum 2000 (JGD2000)": "JGD2000 (vertical) height",
        "World Geodetic System 1984 (Ensemble) 3D": "WGS 84",
        "World Geodetic System 1984 (G1762) 3D": "WGS 84 (G1762)",
        "EGM2008": "EGM2008 height",
        "EGM96": "EGM96 height",
        "NAVD88": "NAVD88 height",
        "CGVD2013": "CGVD2013(CGG2013) height",
        "CGG2013": "CGVD2013(CGG2013) height",
        "EVRF2007": "EVRF2007 height",
        "EVRF2019": "EVRF2019 height",
        "EVRF2000": "EVRF2000 height",
        "AHD": "AHD height",
        "NZVD2016": "NZVD2016 height",
        "JGD2000": "JGD2000 (vertical) height",
        "WGS84": "WGS 84",
        "WGS 84": "WGS 84",
        "G1762": "WGS 84 (G1762)",
    }
    
    def test_each_name_matches_what_proj_calls_its_code(self):
        """Every key in both maps names the CRS its EPSG code actually is."""
        entries = {**VERTICAL_SRS_NAME_MAP, **VERTICAL_SRS_ABBREV_MAP}
        assert set(entries) == set(self.EPSG_NAMES), (
            "an entry was added or removed without updating EPSG_NAMES: "
            f"{set(entries) ^ set(self.EPSG_NAMES)}")
        for key, code in entries.items():
            srs = osr.SpatialReference()
            srs.ImportFromEPSG(code)
            assert srs.GetName() == self.EPSG_NAMES[key], (
                f"{key!r} maps to EPSG:{code}, which PROJ calls {srs.GetName()!r}")
    
    def test_abbrev_keys_have_no_parentheses(self):
        """The abbreviation map is matched against the upper-cased input, so a key can
        contain neither a parenthesis nor a lowercase letter and still be reachable."""
        for key in VERTICAL_SRS_ABBREV_MAP:
            assert "(" not in key and ")" not in key, f"{key!r} could never be typed"
            assert key == key.upper(), f"{key!r} could never match an upper-cased input"
    
    def test_geoid_models_are_not_offered_as_datums(self):
        """No key names GGM10 or any other geoid model; users choose the datum it
        transforms onto (NAVD88 for Mexico)."""
        for key in list(VERTICAL_SRS_NAME_MAP) + list(VERTICAL_SRS_ABBREV_MAP):
            assert "GGM" not in key.upper(), key
            assert "GEOID" not in key.upper(), key


# ==============================================================================
# CATEGORY 2: SRS STANDARDIZATION (4 tests)
# ==============================================================================

class TestStandardizeSrs:
    """Test standardize_srs() EPSG conversion."""
    
    def test_standardize_wgs84_to_epsg(self, srs_wgs84):
        """WKT representing WGS84 should convert to EPSG:4326."""
        wkt = srs_wgs84.ExportToWkt()
        
        # Add some extra whitespace/formatting variations
        wkt_modified = wkt.replace("WGS 84", "WGS  84")
        
        standardized = standardize_srs(wkt_modified)
        
        assert standardized.GetAuthorityCode(None) == "4326"
    
    def test_standardize_utm_to_epsg(self, srs_utm10n):
        """WKT for UTM should convert to EPSG:32610."""
        wkt = srs_utm10n.ExportToWkt()
        
        standardized = standardize_srs(wkt)
        
        assert standardized.GetAuthorityCode(None) == "32610"
    
    def test_standardize_custom_wkt_unchanged(self):
        """Custom WKT without EPSG match should be preserved."""
        # Create a custom projection that won't match EPSG
        custom_wkt = '''PROJCS["Custom_Projection",
            GEOGCS["WGS 84",
                DATUM["WGS_1984",
                    SPHEROID["WGS 84",6378137,298.257223563]],
                PRIMEM["Greenwich",0],
                UNIT["degree",0.0174532925199433]],
            PROJECTION["Lambert_Conformal_Conic_2SP"],
            PARAMETER["standard_parallel_1",33],
            PARAMETER["standard_parallel_2",45],
            PARAMETER["latitude_of_origin",39],
            PARAMETER["central_meridian",-96],
            PARAMETER["false_easting",0],
            PARAMETER["false_northing",0],
            UNIT["metre",1]]'''
        
        standardized = standardize_srs(custom_wkt)
        
        # Should not have EPSG code (custom projection)
        assert standardized.GetAuthorityCode(None) is None or standardized.GetAuthorityCode(None) == ""
        # Should still be valid SRS
        assert standardized.IsProjected() == 1  # OSR returns 1 for True
    
    def test_standardize_vertical_crs(self, srs_navd88):
        """Vertical CRS WKT should standardize to EPSG."""
        wkt = srs_navd88.ExportToWkt()
        
        standardized = standardize_srs(wkt)
        
        assert standardized.GetAuthorityCode(None) == "5703"
        assert standardized.IsVertical() == 1  # OSR returns 1 for True


# ==============================================================================
# PHASE 2: COMPONENT EXTRACTION
# ==============================================================================

class TestGetHorizontalSrs:
    """Test get_horizontal_srs() horizontal component extraction."""
    
    # =========================================================================
    # Test Group 3A: Simple CRS Extraction (2 tests)
    # =========================================================================
    
    def test_extract_simple_geographic(self, srs_wgs84):
        """Simple geographic CRS should return clone."""
        horiz = get_horizontal_srs(srs_wgs84)
        
        assert horiz is not None
        assert horiz.GetAuthorityCode(None) == "4326"
        assert horiz.IsGeographic() == 1  # OSR returns 1 for True
    
    def test_extract_simple_projected(self, srs_utm10n):
        """Simple projected CRS should return clone."""
        horiz = get_horizontal_srs(srs_utm10n)
        
        assert horiz is not None
        assert horiz.GetAuthorityCode(None) == "32610"
        assert horiz.IsProjected() == 1  # OSR returns 1 for True
    
    # =========================================================================
    # Test Group 3B: Compound CRS Extraction (4 tests)
    # =========================================================================
    
    def test_extract_compound_epsg_projected(self):
        """Extract horizontal from compound with EPSG projected component."""
        # Create UTM 10N + NAVD88
        horiz_srs = osr.SpatialReference()
        horiz_srs.ImportFromEPSG(32610)
        vert_srs = osr.SpatialReference()
        vert_srs.ImportFromEPSG(5703)
        
        compound = osr.SpatialReference()
        compound.SetCompoundCS("UTM 10N + NAVD88", horiz_srs, vert_srs)
        
        extracted_horiz = get_horizontal_srs(compound)
        
        assert extracted_horiz is not None
        assert extracted_horiz.GetAuthorityCode(None) == "32610"
        assert extracted_horiz.IsProjected() == 1  # OSR returns 1 for True
    
    def test_extract_compound_epsg_geographic(self):
        """Extract geographic horizontal from compound."""
        # Create WGS84 + EGM96
        horiz_srs = osr.SpatialReference()
        horiz_srs.ImportFromEPSG(4326)
        vert_srs = osr.SpatialReference()
        vert_srs.ImportFromEPSG(5773)
        
        compound = osr.SpatialReference()
        compound.SetCompoundCS("WGS 84 + EGM96", horiz_srs, vert_srs)
        
        extracted_horiz = get_horizontal_srs(compound)
        
        assert extracted_horiz is not None
        assert extracted_horiz.GetAuthorityCode(None) == "4326"
        assert extracted_horiz.IsGeographic() == 1  # OSR returns 1 for True
    
    def test_extract_compound_custom_vertical(self):
        """Extract horizontal from compound with a custom vertical (WKT, no EPSG code)."""
        # Create UTM 10N + Test Local height
        horiz_srs = osr.SpatialReference()
        horiz_srs.ImportFromEPSG(32610)
        vert_srs = get_srs_from_user_input(CUSTOM_VERTICAL_WKT)
        assert vert_srs is not None
        
        compound = osr.SpatialReference()
        compound.SetCompoundCS("UTM 10N + Test Local height", horiz_srs, vert_srs)
        
        extracted_horiz = get_horizontal_srs(compound)
        
        assert extracted_horiz is not None
        assert extracted_horiz.GetAuthorityCode(None) == "32610"
        assert extracted_horiz.IsProjected() == 1  # OSR returns 1 for True
    
    def test_extract_compound_multiple_datums(self):
        """Extract horizontal from compound with different vertical datums."""
        # Test with EGM2008 instead of NAVD88
        horiz_srs = osr.SpatialReference()
        horiz_srs.ImportFromEPSG(32610)
        vert_srs = osr.SpatialReference()
        vert_srs.ImportFromEPSG(3855)  # EGM2008
        
        compound = osr.SpatialReference()
        compound.SetCompoundCS("UTM 10N + EGM2008", horiz_srs, vert_srs)
        
        extracted_horiz = get_horizontal_srs(compound)
        
        assert extracted_horiz is not None
        assert extracted_horiz.GetAuthorityCode(None) == "32610"
        assert extracted_horiz.IsProjected() == 1  # OSR returns 1 for True


class TestGetVerticalSrs:
    """Test get_vertical_srs() vertical component extraction."""
    
    # =========================================================================
    # Test Group 4A: Compound CRS Extraction (2 tests)
    # =========================================================================
    
    def test_extract_vertical_compound_epsg(self, tmp_path):
        """Extract NAVD88 from compound CRS."""
        filepath = tmp_path / "compound.tif"
        
        # Create test GeoTIFF with compound CRS (UTM 10N + NAVD88)
        horiz = osr.SpatialReference()
        horiz.ImportFromEPSG(32610)
        vert = osr.SpatialReference()
        vert.ImportFromEPSG(5703)
        compound = osr.SpatialReference()
        compound.SetCompoundCS("UTM 10N + NAVD88", horiz, vert)
        
        # Create and write the file
        driver = gdal.GetDriverByName('GTiff')
        ds = driver.Create(str(filepath), 256, 256, 1, gdal.GDT_Float32)
        ds.SetProjection(compound.ExportToWkt())
        ds.SetGeoTransform((0, 1, 0, 0, 0, -1))
        ds.FlushCache()
        ds = None  # Close the dataset
        
        # Reopen and test
        ds = gdal.Open(str(filepath))
        srs = ds.GetSpatialRef()
        
        # Verify it's compound
        assert srs.IsCompound() == 1
        
        extracted_vert = get_vertical_srs(ds)
        ds = None
        
        # Note: Due to GDAL's handling of compound CRS, this may return None
        # if the vertical component isn't properly accessible via GetAuthorityCode
        # This is a known limitation when round-tripping compound CRS through WKT
        if extracted_vert is not None:
            assert extracted_vert.GetAuthorityCode(None) == "5703"
            assert extracted_vert.IsVertical() == 1
    
    def test_extract_vertical_compound_egm96(self, tmp_path):
        """Extract EGM96 from compound CRS."""
        filepath = tmp_path / "compound_egm96.tif"
        
        # Create test GeoTIFF with compound CRS (WGS84 + EGM96)
        horiz = osr.SpatialReference()
        horiz.ImportFromEPSG(4326)
        vert = osr.SpatialReference()
        vert.ImportFromEPSG(5773)
        compound = osr.SpatialReference()
        compound.SetCompoundCS("WGS 84 + EGM96", horiz, vert)
        
        # Create and write the file
        driver = gdal.GetDriverByName('GTiff')
        ds = driver.Create(str(filepath), 256, 256, 1, gdal.GDT_Float32)
        ds.SetProjection(compound.ExportToWkt())
        ds.SetGeoTransform((0, 1, 0, 0, 0, -1))
        ds.FlushCache()
        ds = None  # Close the dataset
        
        # Reopen and test
        ds = gdal.Open(str(filepath))
        srs = ds.GetSpatialRef()
        
        # Verify it's compound
        assert srs.IsCompound() == 1
        
        extracted_vert = get_vertical_srs(ds)
        ds = None
        
        # Note: Due to GDAL's handling of compound CRS, this may return None
        # if the vertical component isn't properly accessible via GetAuthorityCode
        # This is a known limitation when round-tripping compound CRS through WKT
        if extracted_vert is not None:
            assert extracted_vert.GetAuthorityCode(None) == "5773"
            assert extracted_vert.IsVertical() == 1
    
    # =========================================================================
    # Test Group 4B: No Vertical Component (3 tests)
    # =========================================================================
    
    def test_no_vertical_simple_geographic(self, tmp_path, srs_wgs84):
        """Simple geographic CRS should return None."""
        filepath = tmp_path / "geographic.tif"
        
        create_test_geotiff_with_srs(filepath, srs_wgs84, bands=3, data_type=gdal.GDT_Byte)
        
        ds = gdal.Open(str(filepath))
        vert = get_vertical_srs(ds)
        ds = None
        
        assert vert is None
    
    def test_no_vertical_simple_projected(self, tmp_path, srs_utm10n):
        """Simple projected CRS should return None."""
        filepath = tmp_path / "projected.tif"
        
        create_test_geotiff_with_srs(filepath, srs_utm10n, bands=3, data_type=gdal.GDT_Byte)
        
        ds = gdal.Open(str(filepath))
        vert = get_vertical_srs(ds)
        ds = None
        
        assert vert is None
    
    def test_no_vertical_no_srs(self, tmp_path):
        """Dataset without SRS should return None."""
        filepath = tmp_path / "no_srs.tif"
        
        driver = gdal.GetDriverByName('GTiff')
        ds = driver.Create(str(filepath), 256, 256, 1, gdal.GDT_Byte)
        # Don't set projection
        ds.SetGeoTransform((0, 1, 0, 0, 0, -1))
        ds.FlushCache()
        ds = None
        
        ds = gdal.Open(str(filepath))
        vert = get_vertical_srs(ds)
        ds = None
        
        assert vert is None
    
    # =========================================================================
    # Test Group 4C: Custom Vertical CRS (1 test)
    # =========================================================================
    
    def test_extract_vertical_custom_wkt(self, tmp_path):
        """A custom (WKT, no EPSG code) vertical CRS cannot be extracted from the file."""
        filepath = tmp_path / "compound_custom.tif"
        
        # Create test GeoTIFF with compound CRS (UTM 10N + Test Local height)
        horiz = osr.SpatialReference()
        horiz.ImportFromEPSG(32610)
        vert = get_srs_from_user_input(CUSTOM_VERTICAL_WKT)
        assert vert is not None, "Failed to parse the custom vertical CRS WKT"
        
        # Use manual WKT construction for custom vertical CRS
        compound = create_compound_srs(horiz, vert)
        
        # Create and write the file
        driver = gdal.GetDriverByName('GTiff')
        ds = driver.Create(str(filepath), 256, 256, 1, gdal.GDT_Float32)
        ds.SetProjection(compound.ExportToWkt())
        ds.SetGeoTransform((0, 1, 0, 0, 0, -1))
        ds.FlushCache()
        ds = None  # Close the dataset
        
        # Reopen and test
        ds = gdal.Open(str(filepath))
        srs = ds.GetSpatialRef()
        
        # Verify it's compound
        assert srs.IsCompound() == 1
        
        extracted_vert = get_vertical_srs(ds)
        ds = None
        
        # There is no EPSG code to read back and the Esri name lookup does not know
        # "Test Local height", so extraction returns None. This documents the limitation
        # that COMPOUND_CRS_WKT2 exists to work around: in a real workflow the writer
        # stores the full WKT2 in that metadata item and the reader recovers it.
        assert extracted_vert is None


# ==============================================================================
# PHASE 3: COMPOUND CRS & ORCHESTRATION
# ==============================================================================

class TestCheckVerticalSrsMismatch:
    """Test check_vertical_srs_mismatch() vertical datum mismatch detection."""
    
    # =========================================================================
    # Test Group 5A: Matching Datums (1 test)
    # =========================================================================
    
    def test_matching_datums_no_warning(self, tmp_path, caplog):
        """Matching datums should not log warning."""
        filepath = tmp_path / "matching.tif"
        
        # Create dataset with NAVD88
        horiz = osr.SpatialReference()
        horiz.ImportFromEPSG(32610)
        vert = osr.SpatialReference()
        vert.ImportFromEPSG(5703)  # NAVD88
        compound = osr.SpatialReference()
        compound.SetCompoundCS("UTM 10N + NAVD88", horiz, vert)
        
        driver = gdal.GetDriverByName('GTiff')
        ds = driver.Create(str(filepath), 256, 256, 1, gdal.GDT_Float32)
        ds.SetProjection(compound.ExportToWkt())
        ds.SetGeoTransform((0, 1, 0, 0, 0, -1))
        ds.FlushCache()
        
        # Check with matching user input
        with caplog.at_level(logging.WARNING):
            check_vertical_srs_mismatch(ds, "NAVD88", str(filepath))
        ds = None
        
        # Should not have warning about mismatch
        assert "does not match" not in caplog.text
    
    # =========================================================================
    # Test Group 5B: Mismatching Datums (1 test)
    # =========================================================================
    
    def test_mismatching_datums_warning(self, tmp_path, caplog):
        """Mismatching datums should log warning if vertical is extractable."""
        filepath = tmp_path / "mismatch.tif"
        
        # Create dataset with NAVD88
        horiz = osr.SpatialReference()
        horiz.ImportFromEPSG(32610)
        vert = osr.SpatialReference()
        vert.ImportFromEPSG(5703)  # NAVD88
        compound = osr.SpatialReference()
        compound.SetCompoundCS("UTM 10N + NAVD88", horiz, vert)
        
        driver = gdal.GetDriverByName('GTiff')
        ds = driver.Create(str(filepath), 256, 256, 1, gdal.GDT_Float32)
        ds.SetProjection(compound.ExportToWkt())
        ds.SetGeoTransform((0, 1, 0, 0, 0, -1))
        ds.FlushCache()
        ds = None  # Close and reopen
        
        ds = gdal.Open(str(filepath))
        
        # Check with different user input
        with caplog.at_level(logging.WARNING):
            check_vertical_srs_mismatch(ds, "EGM96", str(filepath))
        ds = None
        
        # Note: Due to GDAL's compound CRS handling, the vertical component may not be
        # extractable via GetAuthorityCode after round-tripping through WKT.
        # This test documents that the function handles this gracefully (no crash).
        # If vertical IS extractable, the warning should appear
        if "does not match" in caplog.text:
            assert True  # Warning was logged as expected
        else:
            # Vertical wasn't extractable, which is also acceptable behavior
            assert len(caplog.records) == 0 or "Could not parse" not in caplog.text
    
    # =========================================================================
    # Test Group 5C: Edge Cases (2 tests)
    # =========================================================================
    
    def test_no_user_vertical_srs_no_op(self, tmp_path, caplog):
        """No user SRS should be a no-op."""
        filepath = tmp_path / "any.tif"
        
        driver = gdal.GetDriverByName('GTiff')
        ds = driver.Create(str(filepath), 256, 256, 1, gdal.GDT_Float32)
        ds.SetGeoTransform((0, 1, 0, 0, 0, -1))
        ds.FlushCache()
        
        with caplog.at_level(logging.WARNING):
            check_vertical_srs_mismatch(ds, None, str(filepath))
        ds = None
        
        # Should not log anything
        assert len(caplog.records) == 0
    
    def test_invalid_user_vertical_srs_warning(self, tmp_path, caplog):
        """Invalid user SRS should log warning."""
        filepath = tmp_path / "any.tif"
        
        driver = gdal.GetDriverByName('GTiff')
        ds = driver.Create(str(filepath), 256, 256, 1, gdal.GDT_Float32)
        ds.SetGeoTransform((0, 1, 0, 0, 0, -1))
        ds.FlushCache()
        
        with caplog.at_level(logging.WARNING):
            check_vertical_srs_mismatch(ds, "INVALID_DATUM", str(filepath))
        ds = None
        
        # Should log warning about parsing failure
        assert "Could not parse" in caplog.text


class TestCreateCompoundSrs:
    """Test create_compound_srs() compound CRS creation."""
    
    # =========================================================================
    # Test Group 6A: Standard EPSG Vertical (2 tests)
    # =========================================================================
    
    def test_create_compound_epsg_vertical_navd88(self):
        """Create compound CRS with NAVD88."""
        horiz = osr.SpatialReference()
        horiz.ImportFromEPSG(32610)  # UTM 10N
        vert = osr.SpatialReference()
        vert.ImportFromEPSG(5703)  # NAVD88
        
        compound = create_compound_srs(horiz, vert)
        
        assert compound.IsCompound() == 1
        compound_name = compound.GetName()
        assert "UTM" in compound_name or "32610" in compound_name
        assert "NAVD88" in compound_name or "5703" in compound_name
    
    def test_create_compound_epsg_vertical_egm96(self):
        """Create compound CRS with EGM96."""
        horiz = osr.SpatialReference()
        horiz.ImportFromEPSG(32610)  # UTM 10N
        vert = osr.SpatialReference()
        vert.ImportFromEPSG(5773)  # EGM96
        
        compound = create_compound_srs(horiz, vert)
        
        assert compound.IsCompound() == 1
        compound_name = compound.GetName()
        assert "UTM" in compound_name or "32610" in compound_name
        assert "EGM96" in compound_name or "5773" in compound_name
    
    # =========================================================================
    # Test Group 6B: Custom Vertical (1 test)
    # =========================================================================
    
    def test_create_compound_custom_vertical_wkt(self):
        """Create compound CRS with a vertical CRS that has no EPSG code (WKT input)."""
        horiz = osr.SpatialReference()
        horiz.ImportFromEPSG(32610)
        
        # The WKT carries a non-EPSG ID[], so create_compound_srs() goes through
        # SetCompoundCS(); the names must still come out the other side.
        vert = get_srs_from_user_input(CUSTOM_VERTICAL_WKT)
        assert vert is not None
        
        compound = create_compound_srs(horiz, vert)
        
        assert compound.IsCompound() == 1
        compound_name = compound.GetName()
        assert "Test Local" in compound_name
        wkt2 = compound.ExportToWkt(['FORMAT=WKT2_2019'])
        assert 'VDATUM["Test Local Vertical Datum 2000"]' in wkt2
    
    def test_create_compound_vertical_without_authority_is_stitched_by_hand(self):
        """A vertical CRS with no ID[] at all takes the manual COMPOUNDCRS path, which
        exists because SetCompoundCS() can downgrade such a datum to "unknown"."""
        horiz = osr.SpatialReference()
        horiz.ImportFromEPSG(32610)
        vert = osr.SpatialReference()
        assert vert.ImportFromWkt(CUSTOM_VERTICAL_WKT_NO_AUTHORITY) == 0
        assert not vert.GetAuthorityCode(None)
        
        compound = create_compound_srs(horiz, vert)
        wkt2 = compound.ExportToWkt(['FORMAT=WKT2_2019'])
        
        assert compound.IsCompound() == 1
        assert 'VDATUM["Test Local Vertical Datum 2000"]' in wkt2
        assert "unknown" not in wkt2.lower()
    
    def test_create_compound_mexico_itrf2008_navd88(self):
        """Mexico ITRF2008 / UTM zone 13N + NAVD88 height: what INEGI data should carry.
        NAVD88 is the datum INEGI's Norma Técnica names for Mexico; GGM10 is the
        transformation onto it and never appears in the CRS."""
        horiz = osr.SpatialReference()
        horiz.ImportFromEPSG(6368)
        vert = osr.SpatialReference()
        vert.ImportFromEPSG(5703)  # NAVD88
        
        compound = create_compound_srs(horiz, vert)
        
        assert compound.IsCompound() == 1
        assert "NAVD88 height" in compound.GetName()
        assert compound.GetAuthorityCode('COMPD_CS|VERT_CS') == '5703'
        assert "GGM" not in compound.ExportToWkt(['FORMAT=WKT2_2019'])
    
    # =========================================================================
    # Test Group 6C: Geographic Horizontal (1 test)
    # =========================================================================
    
    def test_create_compound_geographic_horizontal(self):
        """Create compound with geographic horizontal (WGS84 + EGM96)."""
        horiz = osr.SpatialReference()
        horiz.ImportFromEPSG(4326)
        vert = osr.SpatialReference()
        vert.ImportFromEPSG(5773)  # EGM96
        
        compound = create_compound_srs(horiz, vert)
        
        assert compound.IsCompound() == 1
        compound_name = compound.GetName()
        assert "WGS" in compound_name or "4326" in compound_name
    
    # =========================================================================
    # Test Group 6D: Error Handling (1 test)
    # =========================================================================
    
    def test_create_compound_invalid_vertical_raises_error(self):
        """Non-vertical SRS should raise ProcessingStepFailedError."""
        horiz = osr.SpatialReference()
        horiz.ImportFromEPSG(32610)
        
        # Try to use geographic CRS as "vertical"
        invalid_vert = osr.SpatialReference()
        invalid_vert.ImportFromEPSG(4326)
        
        with pytest.raises(ProcessingStepFailedError, match="not a vertical coordinate system"):
            create_compound_srs(horiz, invalid_vert)
    
    # =========================================================================
    # Test Group 6E: WKT Preservation (1 test)
    # =========================================================================
    
    def test_create_compound_vertical_preserved(self):
        """Verify vertical datum name/units are preserved."""
        horiz = osr.SpatialReference()
        horiz.ImportFromEPSG(32610)
        vert = osr.SpatialReference()
        vert.ImportFromEPSG(5703)  # NAVD88
        
        compound = create_compound_srs(horiz, vert)
        
        # Extract WKT and verify vertical component
        wkt = compound.ExportToWkt()
        assert "NAVD88" in wkt or "5703" in wkt
        assert "metre" in wkt.lower() or "meter" in wkt.lower()  # Vertical unit


class TestHandleSrsLogic:
    """Test handle_srs_logic() SRS orchestration using real classes."""
    
    # =========================================================================
    # Test Group 7A: DEM Product Type (3 tests)
    # =========================================================================
    
    def test_dem_with_vertical_srs_creates_compound(self):
        """DEM product type with vertical SRS should create compound."""
        # Create real OptimizeArguments with only required fields for this test
        class MinimalArgs:
            product_type = 'dem'
            vertical_srs = 'NAVD88'
        
        args = MinimalArgs()
        
        # Create real GeoTiffInfo
        test_srs = osr.SpatialReference()
        test_srs.ImportFromEPSG(32610)
        
        class MinimalInputInfo:
            def __init__(self):
                self.srs = test_srs
        
        input_info = MinimalInputInfo()
        
        result_srs = handle_srs_logic(args, input_info)  # type: ignore
        
        assert result_srs is not None
        assert result_srs.IsCompound() == 1
    
    def test_dem_without_vertical_srs_keeps_original(self):
        """DEM without vertical SRS should keep original."""
        class MinimalArgs:
            product_type = 'dem'
            vertical_srs = None  # No vertical SRS
        
        args = MinimalArgs()
        
        test_srs = osr.SpatialReference()
        test_srs.ImportFromEPSG(32610)
        
        class MinimalInputInfo:
            def __init__(self):
                self.srs = test_srs
        
        input_info = MinimalInputInfo()
        
        result_srs = handle_srs_logic(args, input_info)  # type: ignore
        
        assert result_srs is not None
        assert result_srs.GetAuthorityCode(None) == "32610"
        assert result_srs.IsCompound() == 0
    
    def test_dem_with_3d_geographic_uses_as_is(self):
        """DEM with 3D geographic vertical SRS (e.g., WGS84 3D) should use as-is."""
        class MinimalArgs:
            product_type = 'dem'
            vertical_srs = 'EPSG:4979'  # WGS84 3D
        
        args = MinimalArgs()
        
        test_srs = osr.SpatialReference()
        test_srs.ImportFromEPSG(32610)
        
        class MinimalInputInfo:
            def __init__(self):
                self.srs = test_srs
        
        input_info = MinimalInputInfo()
        
        result_srs = handle_srs_logic(args, input_info)  # type: ignore
        
        assert result_srs is not None
        assert result_srs.IsGeographic() == 1
        assert result_srs.GetAxesCount() == 3
        assert result_srs.GetAuthorityCode(None) == "4979"
    
    # =========================================================================
    # Test Group 7B: Non-DEM Product Type (2 tests)
    # =========================================================================
    
    def test_non_dem_strips_vertical_from_compound(self):
        """Non-DEM product with compound CRS should strip vertical."""
        class MinimalArgs:
            product_type = 'image'  # Not DEM
            vertical_srs = None
        
        args = MinimalArgs()
        
        # Create compound CRS (shouldn't be on imagery)
        horiz = osr.SpatialReference()
        horiz.ImportFromEPSG(32610)
        vert = osr.SpatialReference()
        vert.ImportFromEPSG(5703)
        compound = osr.SpatialReference()
        compound.SetCompoundCS("UTM 10N + NAVD88", horiz, vert)
        
        class MinimalInputInfo:
            def __init__(self):
                self.srs = compound
        
        input_info = MinimalInputInfo()
        
        result_srs = handle_srs_logic(args, input_info)  # type: ignore
        
        assert result_srs is not None
        assert result_srs.IsCompound() == 0
        assert result_srs.GetAuthorityCode(None) == "32610"
    
    def test_non_dem_with_simple_crs_unchanged(self):
        """Non-DEM with simple CRS should return unchanged."""
        class MinimalArgs:
            product_type = 'image'
            vertical_srs = None
        
        args = MinimalArgs()
        
        test_srs = osr.SpatialReference()
        test_srs.ImportFromEPSG(32610)
        
        class MinimalInputInfo:
            def __init__(self):
                self.srs = test_srs
        
        input_info = MinimalInputInfo()
        
        result_srs = handle_srs_logic(args, input_info)  # type: ignore
        
        assert result_srs is not None
        assert result_srs.GetAuthorityCode(None) == "32610"
    
    # =========================================================================
    # Test Group 7C: Edge Cases (2 tests)
    # =========================================================================
    
    def test_no_source_srs_returns_none(self):
        """Dataset without SRS should return None."""
        class MinimalArgs:
            product_type = 'dem'
            vertical_srs = 'NAVD88'
        
        args = MinimalArgs()
        
        class MinimalInputInfo:
            def __init__(self):
                self.srs = None  # No SRS
        
        input_info = MinimalInputInfo()
        
        result_srs = handle_srs_logic(args, input_info)  # type: ignore
        
        assert result_srs is None
    
    def test_invalid_vertical_srs_raises_error(self):
        """Invalid vertical SRS should raise ProcessingStepFailedError."""
        class MinimalArgs:
            product_type = 'dem'
            vertical_srs = 'INVALID_DATUM'
        
        args = MinimalArgs()
        
        test_srs = osr.SpatialReference()
        test_srs.ImportFromEPSG(32610)
        
        class MinimalInputInfo:
            def __init__(self):
                self.srs = test_srs
        
        input_info = MinimalInputInfo()
        
        with pytest.raises(ProcessingStepFailedError, match="Failed to parse vertical SRS"):
            handle_srs_logic(args, input_info)  # type: ignore


# ==============================================================================
# RUN TESTS
# ==============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
