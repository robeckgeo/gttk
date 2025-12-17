#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ******************************************************************************
# Project: GeoTIFF ToolKit (GTTK)
# Author: Eric Robeck <robeckgeo@gmail.com>
#
# Copyright (c) 2025, Eric Robeck
# Licensed under the MIT License
# ******************************************************************************

"""
Spatial Reference System (SRS) Handling and Logic for GTTK.

This module centralizes all functionality related to Spatial Reference Systems.
It handles parsing user input, extracting horizontal and vertical components,
creating compound SRS, and standardizing Esri-specific WKTs to their
corresponding EPSG codes to ensure interoperability.
"""
import logging
from osgeo import gdal, osr
from typing import Optional, Dict
from gttk.utils.script_arguments import OptimizeArguments
from gttk.utils.data_models import GeoTiffInfo
from gttk.utils.exceptions import ProcessingStepFailedError
from gttk.utils.esri_epsg_lookup import get_epsg_from_esri_name

logger = logging.getLogger(__name__)

# Vertical SRS Name to EPSG Code
VERTICAL_SRS_NAME_MAP: Dict[str, int] = {
    "Earth Gravitational Model 2008 (EGM2008)": 3855,
    "Earth Gravitational Model 1996 (EGM96)": 5773,
    "North America Vertical Datum 1988 (NAVD88)": 5703,
    "Canadian Geodetic Vertical Datum 2013 (CGVD2013/CGG2013)": 6647,
    "Geoide Gravimétrico Mexicano 2010 (GGM10)": 0,
    "European Vertical Reference Frame 2007 (EVRF2007)": 5621,
    "European Vertical Reference Frame 2019 (EVRF2019)": 9389,
    "European Vertical Reference Frame 2020 (EVRF2020)": 5730,
    "Australia Height Datum (AHD)": 5711,
    "New Zealand Vertical Datum 2016 (NZVD2016)": 7839,
    "Japanese Geodetic Datum 2000 (JGD2000)": 6694,
    "World Geodetic System 1984 (Ensemble) 3D": 4979,
    "World Geodetic System 1984 (G1762) 3D": 7665,
}

# Vertical SRS Abbrev. to EPSG Code
VERTICAL_SRS_ABBREV_MAP: Dict[str, int] = {
    "EGM2008": 3855,
    "EGM96": 5773,
    "NAVD88": 5703,
    "CGVD2013": 5703,
    "CGG2013": 6647,
    "GGM10": 0,
    "EVRF2007": 5621,
    "EVRF2019": 9389,
    "EVRF2020": 5730,
    "AHD)": 5711,
    "NZVD2016)": 7839,
    "JGD2000)": 6694,
    "WGS84": 4979,
    "WGS 84": 4979,
    "G1762": 7665,
}

# Registry for Custom Vertical CRS WKTs (where EPSG code does not exist)
CUSTOM_VERTICAL_WKT_REGISTRY: Dict[str, str] = {
    "GGM10": """
    VERTCRS["GGM10 height",
        VDATUM["Geoide Gravimétrico Mexicano 2010"],
        CS[vertical,1],
        AXIS["gravity-related height (H)",up],
        LENGTHUNIT["metre",1],
        USAGE[
            SCOPE["Geodesy, engineering survey, topographic mapping."],
            AREA["Mexico - onshore and offshore."],
            BBOX[14.02,-118.98,32.98,-86.02]],
        ID["PROJ","GGM2010"]]
    """
}

def get_srs_from_user_input(srs_input: str) -> Optional[osr.SpatialReference]:
    """
    Creates an osr.SpatialReference object from various user inputs.

    Args:
        srs_input (str): The user input, which can be an EPSG code (e.g., "4326", "EPSG:4326"),
                         a WKT string, or other formats recognized by GDAL.

    Returns:
        Optional[osr.SpatialReference]: A spatial reference object, or None if parsing fails.
    """
    srs = osr.SpatialReference()
    srs_upper = srs_input.upper()
    logger.info(f"Parsing user input SRS: {srs_input}")
    try:
        # Check for Custom WKT Registry matches first
        # Extract abbreviation if input matches Name Map or Abbrev Map keys
        abbrev = None
        if srs_input in VERTICAL_SRS_NAME_MAP:
            # Reverse lookup name to abbreviation isn't direct, but we can check the EPSG code
            # However, for custom CRS, the EPSG is 0000.
            # Instead, let's check if the mapped EPSG is 0, which signals a custom lookup needed.
            epsg_code = VERTICAL_SRS_NAME_MAP[srs_input]
            if epsg_code == 0:
                # Infer abbreviation from the name string (hacky but effective for GGM10)
                if "GGM10" in srs_input:
                    abbrev = "GGM10"
        elif srs_upper in VERTICAL_SRS_ABBREV_MAP:
            if VERTICAL_SRS_ABBREV_MAP[srs_upper] == 0:
                abbrev = srs_upper

        if abbrev and abbrev in CUSTOM_VERTICAL_WKT_REGISTRY:
            logger.info(f"Custom Vertical CRS detected for '{srs_input}'. Injecting WKT.")
            custom_wkt = CUSTOM_VERTICAL_WKT_REGISTRY[abbrev]
            
            if srs.ImportFromWkt(custom_wkt) != 0:
                logger.error(f"Failed to import custom WKT for {abbrev}")
                return None
            
            return srs

        # Standard EPSG Lookups
        if srs_input in VERTICAL_SRS_NAME_MAP:  # Direct match for full names (in GUI dropdown)
            srs.ImportFromEPSG(VERTICAL_SRS_NAME_MAP[srs_input])
        elif srs_upper in VERTICAL_SRS_ABBREV_MAP:  # Shortcut abbreviation match
            srs.ImportFromEPSG(VERTICAL_SRS_ABBREV_MAP[srs_upper])
        elif srs_upper.startswith('EPSG:'):  # EPSG code with prefix
            srs.ImportFromEPSG(int(srs_upper.split(':')[1]))
        elif srs_input.isdigit():  # EPSG code as integer string
            srs.ImportFromEPSG(int(srs_input))
        else:
            if srs.SetFromUserInput(srs_input) != 0:
                return None
        return srs
    except (RuntimeError, ValueError, KeyError):
        return None

def standardize_srs(wkt: str) -> osr.SpatialReference:
    """
    Standardizes a WKT string to a clean, EPSG-based OSR SpatialReference object if possible.

    Args:
        wkt (str): The WKT string to standardize.

    Returns:
        osr.SpatialReference: A standardized spatial reference object.
    """
    srs = osr.SpatialReference()
    srs.ImportFromWkt(wkt)
    if srs.AutoIdentifyEPSG() == 0:
        epsg_code = srs.GetAuthorityCode(None)
        if epsg_code:
            clean_srs = osr.SpatialReference()
            clean_srs.ImportFromEPSG(int(epsg_code))
            return clean_srs
    return srs

def get_horizontal_srs(srs: osr.SpatialReference) -> osr.SpatialReference:
    """
    Extracts the horizontal component of a spatial reference system.

    Args:
        srs (osr.SpatialReference): The input spatial reference system.

    Returns:
        osr.SpatialReference: The horizontal component of the input SRS.
    """
    horiz_srs = osr.SpatialReference()
    if srs.IsCompound():
        proj_epsg = srs.GetAuthorityCode('COMPD_CS|PROJCS')
        geog_epsg = srs.GetAuthorityCode('COMPD_CS|GEOGCS')
        if proj_epsg:
            horiz_srs.ImportFromEPSG(int(proj_epsg))
        elif geog_epsg:
            horiz_srs.ImportFromEPSG(int(geog_epsg))
        else:
            # Fallback to WKT for non-EPSG compound CRS (e.g., from Esri)
            horiz_wkt = srs.ExportToWkt(['COMPD_CS'])
            horiz_srs.ImportFromWkt(horiz_wkt)
    else:
        horiz_srs = srs.Clone()

    # If the horizontal SRS is not EPSG-based, try to find a match using the Esri name lookup
    if not horiz_srs.GetAuthorityCode(None):
        horiz_srs_name = horiz_srs.GetName()
        epsg_code = get_epsg_from_esri_name("ProjectedCoordinateSystems", horiz_srs_name)
        if not epsg_code:
            horiz_srs_name = horiz_srs.GetAttrValue("GEOGCS")
            if horiz_srs_name:
                epsg_code = get_epsg_from_esri_name("GeographicCoordinateSystems", horiz_srs_name)
        if epsg_code:
            logger.info(f"Standardized horizontal SRS '{horiz_srs_name}' to EPSG:{epsg_code} via Esri name lookup.")
            horiz_srs.ImportFromEPSG(epsg_code)

    return horiz_srs

def get_vertical_srs(ds: gdal.Dataset) -> Optional[osr.SpatialReference]:
    """
    Gets the vertical EPSG code from a GDAL dataset.

    This function attempts to extract the vertical EPSG code from the 'VERT_CS'
    or 'VERTCRS' attribute of a compound spatial reference system. If the EPSG code
    is not directly available, it uses the Esri name lookup to find a matching EPSG code.

    Args:
        ds (gdal.Dataset): The GDAL dataset.

    Returns:
        Optional[osr.SpatialReference]: The vertical EPSG code, or None if not found.
    """
    srs = ds.GetSpatialRef()
    if not srs or not srs.IsCompound():
        return None

    # Attempt to standardize the vertical SRS
    vert_srs = osr.SpatialReference()
    vert_epsg_str = srs.GetAuthorityCode('COMPD_CS|VERTCS')
    if vert_epsg_str:
        vert_srs.ImportFromEPSG(int(vert_epsg_str))
        return vert_srs

    # If no direct EPSG code, try to find one using the Esri name lookup
    vert_srs_name = None
    for attr in ['VERT_CS', 'VERTCRS']:
        try:
            name = srs.GetAttrValue(attr)
            if name:
                vert_srs_name = name
                break
        except Exception:
            continue
    if vert_srs_name:
        epsg_code = get_epsg_from_esri_name("VerticalCoordinateSystems", vert_srs_name)
        if epsg_code:
            logger.info(f"Mapped vertical SRS name '{vert_srs_name}' to EPSG:{epsg_code} via Esri name lookup.")
            vert_srs.ImportFromEPSG(epsg_code)
            return vert_srs

    return None

def check_vertical_srs_mismatch(ds: gdal.Dataset, user_vertical_srs_name: Optional[str], input_path: str) -> None:
    """
    Checks for mismatches between the file's vertical SRS and the user-provided one.

    Args:
        ds (gdal.Dataset): The input GDAL dataset.
        user_vertical_srs (Optional[str]): The vertical SRS provided by the user.
        input_path (str): The path to the input file, for logging purposes.
    """
    if not user_vertical_srs_name:
        return

    user_vertical_srs = get_srs_from_user_input(user_vertical_srs_name)
    if not user_vertical_srs:
        logger.warning(f"Could not parse user-provided vertical SRS: {user_vertical_srs_name}")
        return

    epsg_vertical_srs_name = user_vertical_srs.GetName()

    # Check for Compound CRS mismatch
    file_vertical_srs = get_vertical_srs(ds)
    if file_vertical_srs:
        file_vertical_srs_name = file_vertical_srs.GetName()
        if epsg_vertical_srs_name.lower() not in file_vertical_srs_name.lower():
            logger.warning(
                f"Specified vertical datum '{user_vertical_srs_name}' does not match file's vertical datum "
                f"'{file_vertical_srs_name}' for {input_path}"
            )

def create_compound_srs(horizontal_srs: osr.SpatialReference, vertical_srs: osr.SpatialReference) -> osr.SpatialReference:
    """
    Creates a compound spatial reference system from horizontal and vertical components.

    Args:
        horizontal_srs (osr.SpatialReference): The horizontal SRS.
        vertical_srs (osr.SpatialReference): The vertical SRS.

    Returns:
        osr.SpatialReference: The resulting compound or 3D geographic SRS.
    """
    # A compound CRS requires a vertical component.
    if not vertical_srs.IsVertical():
        raise ProcessingStepFailedError(
            f"Invalid vertical SRS for Compound CRS: '{vertical_srs.GetName()}' is not a vertical coordinate system."
        )

    compound_name = f"{horizontal_srs.GetName()} + {vertical_srs.GetName()}"

    # Treat vertical SRS without an authority code as custom; avoid SetCompoundCS in that case
    custom_vertical = not bool(vertical_srs.GetAuthorityCode(None))

    if not custom_vertical:
        compound_srs = osr.SpatialReference()
        if compound_srs.SetCompoundCS(compound_name, horizontal_srs, vertical_srs) == 0:
            # Check for dataloss/downgrade
            wkt1 = compound_srs.ExportToWkt()
            wkt2 = compound_srs.ExportToWkt(['FORMAT=WKT2_2019'])
            if 'VERT_DATUM["unknown"' not in wkt1 and 'VDATUM["unknown"' not in wkt2:
                return compound_srs
            logger.info("SetCompoundCS produced 'unknown' vertical datum. Constructing COMPOUNDCRS manually.")
        else:
            logger.warning("SetCompoundCS failed. Constructing COMPOUNDCRS manually.")
    else:
        logger.info("Custom vertical CRS detected (no authority). Building WKT2 COMPOUNDCRS manually to preserve names/axis/units.")

    # Manual WKT2 COMPOUNDCRS construction (preferred for custom vertical CRSs)
    horiz_wkt = horizontal_srs.ExportToWkt(['FORMAT=WKT2_2019'])
    vert_wkt = vertical_srs.ExportToWkt(['FORMAT=WKT2_2019'])
    compound_wkt = f'COMPOUNDCRS["{compound_name}",{horiz_wkt},{vert_wkt}]'

    manual_srs = osr.SpatialReference()
    if manual_srs.ImportFromWkt(compound_wkt) != 0:
        # If WKT2 fails (e.g., older GDAL), try WKT1 fallback
        logger.warning("WKT2_2019 COMPOUNDCRS import failed. Trying WKT1 COMPD_CS fallback.")
        horiz_wkt1 = horizontal_srs.ExportToWkt()
        vert_wkt1 = vertical_srs.ExportToWkt()
        compound_wkt1 = f'COMPD_CS["{compound_name}",{horiz_wkt1},{vert_wkt1}]'
        if manual_srs.ImportFromWkt(compound_wkt1) != 0:
            raise ProcessingStepFailedError("Failed to create Compound CRS via manual WKT stitching.")

    return manual_srs

def handle_srs_logic(args: OptimizeArguments, input_info: GeoTiffInfo) -> Optional[osr.SpatialReference]:
    """
    Orchestrates the SRS logic for GeoTIFF optimization. Standardizes the source SRS to an EPSG-based one if possible;
    otherwise, it uses the original. If a vertical SRS is specified and the data type is DEM, it creates a compound CRS.
    On the other hand, if a non-DEM data type has a compound CRS, it strips the vertical component.

    Args:
        args (OptimizeArguments): The script arguments.
        input_info (GeoTiffInfo): Information about the input GeoTIFF.

    Returns:
        Optional[osr.SpatialReference]: The target spatial reference system, or None.
    """
    source_srs = input_info.srs
    if not source_srs:
        return None

    # If not a DEM or no vertical SRS is specified, return the horizontal component of the source SRS.
    if args.product_type != 'dem':
        if source_srs.IsCompound():
            logger.info("Non-DEM product type with Compound CRS detected. Stripping vertical component.")
            return get_horizontal_srs(source_srs)
        return source_srs

    if not args.vertical_srs:
        logger.info("DEM product type but no vertical SRS specified. Keeping original SRS.")
        return source_srs

    # Parse the user-provided vertical SRS.
    parsed_vertical_srs = get_srs_from_user_input(args.vertical_srs)
    if not parsed_vertical_srs:
        raise ProcessingStepFailedError(f"Failed to parse vertical SRS: {args.vertical_srs}")

    # If the parsed SRS is a 3D geographic CRS (has 3 axes), it is the complete target SRS.
    is_3d_geographic = parsed_vertical_srs.IsGeographic() and parsed_vertical_srs.GetAxesCount() == 3
    if is_3d_geographic:
        return parsed_vertical_srs

    # Otherwise, extract the horizontal component from the source and create a compound CRS.
    horiz_srs = get_horizontal_srs(source_srs)
    return create_compound_srs(horiz_srs, parsed_vertical_srs)