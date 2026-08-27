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

# ------------------------------------------------------------------------------
# Vertical CRS choices offered by name.
#
# Every value is an EPSG code for a *vertical CRS* -- a datum plus an axis and a
# unit -- which is what a GeoTIFF can carry in its GeoKeys and what every reader
# downstream can resolve.  The ArcGIS toolbox builds its dropdown from the keys of
# VERTICAL_SRS_NAME_MAP, so adding or removing an entry here changes the dialog.
#
# Geoid models do not belong here.  A geoid model is the *transformation* between
# ellipsoidal heights (h) and orthometric heights (H) on some datum; it is not a
# datum of its own.  EGM2008 and EGM96 appear below only because EPSG registered
# vertical CRSs for those global models (3855, 5773).  A regional model such as
# GGM10 or GGM25 (Mexico) or GEOID18 (USA) has no such code, and the code it is
# missing is not the problem: it is a transformation *onto* a datum that already
# has one.  GTTK once shipped "GGM10 height" as an invented vertical CRS, and the
# result was the worst of both worlds -- the name did not survive the GeoKeys
# (VerticalDatumGeoKey 32767, VDATUM["unknown"]), and no software could transform
# from it because nothing knows what it is, so PROJ fell back to a "ballpark"
# +proj=noop.  Mexico's vertical datum is NAVD88 (INEGI, Norma Técnica para el
# Sistema Geodésico Nacional, DOF 23-Dec-2010, art. 15); Esri (WKID 110232,
# Mexico_ITRF2008_To_NAVD88_Height_GGM10) and PROJ (PROJ:EPSG_6364_TO_EPSG_5703
# via the grid mx_inegi_ggm10.tif) already model GGM10 as the transformation onto
# it.  Choose the datum -- NAVD88, EPSG:5703 -- and the transformation stays where
# it belongs.  Never add a geoid model to these maps.
#
# A vertical datum that genuinely has no EPSG code is still supported: pass its
# WKT as the vertical SRS.  get_srs_from_user_input() hands it to GDAL,
# create_compound_srs() stitches it into a compound CRS by hand, and because the
# GeoKeys cannot carry it the writers store the full WKT2 in the
# COMPOUND_CRS_WKT2 metadata item for the reader to recover.
# ------------------------------------------------------------------------------

# Vertical SRS Name to EPSG Code
VERTICAL_SRS_NAME_MAP: Dict[str, int] = {
    "Earth Gravitational Model 2008 (EGM2008)": 3855,
    "Earth Gravitational Model 1996 (EGM96)": 5773,
    "North America Vertical Datum 1988 (NAVD88)": 5703,
    "Canadian Geodetic Vertical Datum 2013 (CGVD2013/CGG2013)": 6647,
    "European Vertical Reference Frame 2007 (EVRF2007)": 5621,
    "European Vertical Reference Frame 2019 (EVRF2019)": 9389,
    "European Vertical Reference Frame 2020 (EVRF2020)": 5730,
    "Australia Height Datum (AHD)": 5711,
    "New Zealand Vertical Datum 2016 (NZVD2016)": 7839,
    "Japanese Geodetic Datum 2000 (JGD2000)": 6694,
    "World Geodetic System 1984 (Ensemble) 3D": 4979,
    "World Geodetic System 1984 (G1762) 3D": 7665,
}

# Vertical SRS Abbrev. to EPSG Code (matched case-insensitively on the upper-cased input)
VERTICAL_SRS_ABBREV_MAP: Dict[str, int] = {
    "EGM2008": 3855,
    "EGM96": 5773,
    "NAVD88": 5703,
    "CGVD2013": 6647,
    "CGG2013": 6647,  # alternate spelling
    "EVRF2007": 5621,
    "EVRF2019": 9389,
    "EVRF2020": 5730,
    "AHD": 5711,
    "NZVD2016": 7839,
    "JGD2000": 6694,
    "WGS84": 4979,
    "WGS 84": 4979,
    "G1762": 7665,
}

def get_srs_from_user_input(srs_input: str) -> Optional[osr.SpatialReference]:
    """
    Creates an osr.SpatialReference object from the SRS text a user supplied.

    Accepted forms, tried in this order:

    1. A full name from ``VERTICAL_SRS_NAME_MAP`` -- what the ArcGIS dropdown submits.
    2. An abbreviation from ``VERTICAL_SRS_ABBREV_MAP``, case-insensitively:
       ``NAVD88``, ``egm2008``, ``CGVD2013`` ...
    3. ``EPSG:n`` for a single code, or ``EPSG:h+v`` for a compound CRS.
    4. A bare integer, taken as an EPSG code.
    5. Anything else GDAL's ``SetFromUserInput`` understands: WKT1 or WKT2, PROJJSON,
       a PROJ string, an OGC URN, and so on.  This is the route for a vertical datum
       that has no EPSG code -- pass its ``VERTCRS[...]`` WKT and it is used verbatim.

    A name GDAL cannot resolve (``"GGM10"``, ``"INVALID_DATUM"``) is not an error at
    this level: the function logs it and returns None, and the caller decides.

    Args:
        srs_input (str): The user input.

    Returns:
        Optional[osr.SpatialReference]: A spatial reference object, or None if parsing fails.
    """
    srs = osr.SpatialReference()
    srs_upper = srs_input.upper()
    logger.info(f"Parsing user input SRS: {srs_input}")

    try:
        if srs_input in VERTICAL_SRS_NAME_MAP:  # Direct match for full names (in GUI dropdown)
            epsg_code = VERTICAL_SRS_NAME_MAP[srs_input]
            logger.debug(f"Importing from EPSG:{epsg_code} for '{srs_input}'")
            srs.ImportFromEPSG(epsg_code)
        elif srs_upper in VERTICAL_SRS_ABBREV_MAP:  # Shortcut abbreviation match
            epsg_code = VERTICAL_SRS_ABBREV_MAP[srs_upper]
            logger.debug(f"Importing from EPSG:{epsg_code} for '{srs_input}'")
            srs.ImportFromEPSG(epsg_code)
        elif srs_upper.startswith('EPSG:'):  # EPSG code with prefix
            epsg_part = srs_upper.split(':')[1]
            # Check for compound CRS (e.g., "EPSG:32610+5703")
            if '+' in epsg_part:
                # Use SetFromUserInput for compound CRS
                if srs.SetFromUserInput(srs_input) != 0:
                    logger.error(f"Failed to parse compound EPSG: {srs_input}")
                    return None
            else:
                # Simple EPSG code
                epsg_code = int(epsg_part)
                logger.debug(f"Importing from EPSG:{epsg_code}")
                srs.ImportFromEPSG(epsg_code)
        elif srs_input.isdigit():  # EPSG code as integer string
            epsg_code = int(srs_input)
            logger.debug(f"Importing from EPSG:{epsg_code}")
            srs.ImportFromEPSG(epsg_code)
        else:  # WKT, PROJJSON, PROJ string, URN ... anything GDAL can make sense of
            if srs.SetFromUserInput(srs_input) != 0:
                logger.error(f"SetFromUserInput failed for: {srs_input}")
                return None
        return srs
    except RuntimeError as e:
        logger.error(
            f"Failed to parse SRS '{srs_input}': {e}\n"
            f"This may be caused by:\n"
            f"  1. PROJ database not accessible (check PROJ_LIB environment variable)\n"
            f"  2. EPSG code not found in PROJ database\n"
            f"  3. Conda environment not activated\n"
            f"If using a conda environment, ensure it's activated before running GTTK."
        )
        return None
    except (ValueError, KeyError) as e:
        logger.error(f"Invalid SRS input '{srs_input}': {e}")
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
    try:
        if srs.AutoIdentifyEPSG() == 0:
            epsg_code = srs.GetAuthorityCode(None)
            if epsg_code:
                clean_srs = osr.SpatialReference()
                clean_srs.ImportFromEPSG(int(epsg_code))
                return clean_srs
    except RuntimeError:
        # AutoIdentifyEPSG() can raise RuntimeError for unsupported/custom SRS
        # In this case, just return the original SRS
        pass
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
        raise ProcessingStepFailedError(
            f"Failed to parse vertical SRS: {args.vertical_srs}\n"
            f"See error details above. Common solutions:\n"
            f"  1. Activate your conda environment: 'conda activate gttk'\n"
            f"  2. Ensure GDAL/PROJ are properly installed in your environment\n"
            f"  3. Verify PROJ_LIB environment variable points to a valid PROJ database"
        )

    # If the parsed SRS is a 3D geographic CRS (has 3 axes), it is the complete target SRS.
    is_3d_geographic = parsed_vertical_srs.IsGeographic() and parsed_vertical_srs.GetAxesCount() == 3
    if is_3d_geographic:
        return parsed_vertical_srs

    # Otherwise, extract the horizontal component from the source and create a compound CRS.
    horiz_srs = get_horizontal_srs(source_srs)
    return create_compound_srs(horiz_srs, parsed_vertical_srs)