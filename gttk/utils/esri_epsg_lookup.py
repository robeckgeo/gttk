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
Esri-to-EPSG Coordinate System Name Lookup Utility.

This module provides functionality to map non-standard Esri projection and
datum names found in some GeoTIFFs to their official EPSG codes. It uses a
packaged JSON lookup table and can handle deprecated Esri naming conventions,
improving the interoperability of Esri-generated files.
"""
import json
import logging
import re
from importlib import resources
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Mapping of deprecated Esri PE name parts to the latest versions
DEPRECATED_PE_NAME_PARTS: Dict[str, str] = {
    "ITRF_2008": "ITRF2008",  # Part of Mexico's UTM zone names
    "_geoid": "_height",      # Matches all EGM geoid variants (changed in ArcGIS Pro 3.5)
    # Add more deprecated parts as needed
}

_INITIALIZED = False
_lookup: Dict[str, Dict[str, int]] = {
    "ProjectedCoordinateSystems": {},
    "GeographicCoordinateSystems": {},
    "VerticalCoordinateSystems": {},
}

def get_epsg_from_esri_name(category: str, name: str) -> Optional[int]:
    """
    Find the EPSG code for a given Esri PE name from the lookup dictionary.

    This function performs a case-insensitive match and handles known deprecated
    name parts (e.g., 'EGM2008_geoid' -> 'EGM2008_height').

    Args:
        category: The CRS category (e.g., "ProjectedCoordinateSystems").
        name: The Esri PE name to look up.

    Returns:
        The matching EPSG code (latestWkid) as an integer, or None if not found.
    """
    if not _INITIALIZED:
        _initialize_lookup()

    if not name or not category:
        return None

    CAT_LOOKUP = _LOOKUP.get(category, {})
    if not CAT_LOOKUP:
        logger.warning(f"Invalid category provided to Esri EPSG lookup: {category}")
        return None

    # Primary match (case-insensitive)
    value = CAT_LOOKUP.get(name.casefold())

    # Fallback match for deprecated name parts
    if value is None:
        converted_name = _convert_deprecated_pe_names(name)
        if converted_name != name:
            value = CAT_LOOKUP.get(converted_name.casefold())
            if value:
                logger.debug(f"Matched deprecated Esri name '{name}' to '{converted_name}' -> EPSG:{value}")

    return value

def _initialize_lookup(lookup_path: Optional[str] = None) -> None:
    """
    Load and normalize the Esri→EPSG lookup JSON.
    """
    global _LOOKUP, _INITIALIZED
    if _INITIALIZED:
        return

    path = None
    try:
        # 1. Check for explicit override
        if lookup_path:
            path = lookup_path
            logger.info(f"Using custom Esri->EPSG lookup file: {path}")
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            # 2. Use packaged resource
            resource_file = resources.files('gttk.resources.esri').joinpath('esri_cs_epsg_lookup.json')
            path = str(resource_file)
            logger.debug(f"Loading packaged Esri->EPSG lookup table from {path}")
            with resource_file.open('r', encoding='utf-8') as f:
                data = json.load(f)

        # Normalize the lookup keys for case-insensitive matching
        _LOOKUP = _normalize_lookup_keys(data)
        _INITIALIZED = True
        logger.info("Esri->EPSG lookup initialized successfully.")

    except FileNotFoundError:
        logger.error(f"Esri->EPSG lookup file not found at {path}.")
        _LOOKUP = _get_empty_lookup()
    except Exception as e:
        logger.error(f"Failed to load Esri->EPSG lookup file: {e}")
        _LOOKUP = _get_empty_lookup()

def _normalize_lookup_keys(data: dict) -> Dict[str, Dict[str, int]]:
    """
    Recursively normalize all keys in the lookup dictionary to be case-insensitive.
    """
    normalized = {}
    for cat, items in data.items():
        if isinstance(items, dict):
            # Use casefold() for robust Unicode case-insensitive matching
            normalized[cat] = {str(k).casefold(): v for k, v in items.items()}
    return normalized

def _get_empty_lookup() -> Dict[str, Dict[str, int]]:
    """Return a default empty structure for the lookup dictionary."""
    return {
        "ProjectedCoordinateSystems": {},
        "GeographicCoordinateSystems": {},
        "VerticalCoordinateSystems": {},
    }

def _convert_deprecated_pe_names(name: str) -> str:
    """
    Replace known deprecated Esri PE name parts with modern equivalents.

    The replacement is case-insensitive and will replace all occurrences of the
    deprecated substrings defined in DEPRECATED_PE_NAME_PARTS.
    """
    if not name:
        return ""
    new_name = name
    for old, new in DEPRECATED_PE_NAME_PARTS.items():
        try:
            # Use case-insensitive regex substitution
            new_name = re.sub(re.escape(old), new, new_name, flags=re.IGNORECASE)
        except re.error:
            # Fallback to simple string replacement if regex fails
            logger.warning(f"Regex failed for deprecated name part '{old}'. Falling back to simple replace.")
            new_name = new_name.replace(old, new)
    return new_name