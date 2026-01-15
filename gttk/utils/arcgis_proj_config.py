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
ArcGIS PROJ Database Configuration.

This module configures the PROJ_LIB environment variable to point to OSGeo4W's
proj.db when running in ArcGIS Pro. This enables ArcGIS's bundled GDAL to
resolve modern EPSG codes (like EPSG:4979) that may not be in ArcGIS's
limited PROJ database.
"""
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def configure_proj_for_arcgis() -> bool:
    """
    Configure PROJ_LIB to use OSGeo4W's proj database when running in ArcGIS.
    
    This function should be called BEFORE any GDAL/OSR operations to ensure
    ArcGIS's bundled GDAL can access the full PROJ database from OSGeo4W.
    
    Returns:
        True if PROJ_LIB was successfully configured, False otherwise
    """
    # Check if PROJ_LIB is already set
    if 'PROJ_LIB' in os.environ:
        existing_path = os.environ['PROJ_LIB']
        logger.info(f"PROJ_LIB already set to: {existing_path}")
        return True
    
    # Get OSGeo4W path from config
    try:
        from gttk.utils.config_loader import config
        osgeo4w_root = config.get('paths.osgeo4w')
        
        if not osgeo4w_root:
            logger.warning("OSGeo4W path not configured in config.toml - cannot set PROJ_LIB")
            return False
        
        # Convert to Path object and check if it exists
        osgeo4w_path = Path(osgeo4w_root)
        if not osgeo4w_path.exists():
            logger.warning(f"OSGeo4W path does not exist: {osgeo4w_path} - cannot set PROJ_LIB")
            return False
        
        # Construct path to PROJ share directory
        proj_share_path = osgeo4w_path / "share" / "proj"
        if not proj_share_path.exists():
            logger.warning(f"PROJ share directory does not exist: {proj_share_path} - cannot set PROJ_LIB")
            return False
        
        # Check for proj.db
        proj_db_path = proj_share_path / "proj.db"
        if not proj_db_path.exists():
            logger.warning(f"proj.db not found at: {proj_db_path} - cannot set PROJ_LIB")
            return False
        
        # Set PROJ_LIB environment variable
        os.environ['PROJ_LIB'] = str(proj_share_path)
        logger.info(f"PROJ_LIB configured to use OSGeo4W proj database: {proj_share_path}")
        logger.info("ArcGIS's GDAL can now resolve modern EPSG codes via OSGeo4W's proj.db")
        return True
        
    except Exception as e:
        logger.warning(f"Failed to configure PROJ_LIB: {e}")
        return False


def get_proj_info() -> dict:
    """
    Get diagnostic information about the current PROJ configuration.
    
    Returns:
        Dictionary with PROJ configuration details
    """
    info = {
        'proj_lib_set': 'PROJ_LIB' in os.environ,
        'proj_lib_path': os.environ.get('PROJ_LIB'),
        'proj_db_exists': False
    }
    
    if info['proj_lib_path']:
        proj_db = Path(info['proj_lib_path']) / 'proj.db'
        info['proj_db_exists'] = proj_db.exists()
        info['proj_db_path'] = str(proj_db) if proj_db.exists() else None
    
    return info