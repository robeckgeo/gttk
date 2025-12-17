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
GEO_METADATA Tag Writer for GeoTIFFs.

This utility handles the process of reading an external XML metadata file,
formatting it correctly, and embedding it into a GeoTIFF's `GEO_METADATA`
(50909) tag. It ensures that XML content is properly escaped and structured for
compliance with GDAL's expectations.
"""
import logging
from pathlib import Path
import lxml.etree as etree
from osgeo import gdal
from typing import Optional

from gttk.utils.xml_formatter import pretty_print_xml

logger = logging.getLogger(__name__)

def prepare_xml_for_gdal(xml_path: Path) -> Optional[str]:
    """
    Reads, validates, and formats XML content for GDAL's GEO_METADATA tag.

    This involves reading the XML, replacing newlines in text content with '&#xA;',
    and then pretty-printing the result.

    Args:
        xml_path: Path to the XML file.

    Returns:
        A string containing the processed XML, or None if an error occurs.
    """
    if not xml_path.exists():
        logger.error(f"Input XML file not found: {xml_path}")
        return None

    try:
        logger.info(f"Reading and preparing XML content from {xml_path}...")
        with open(xml_path, 'rb') as f:
            xml_bytes = f.read()

        # Parse the XML from bytes, allowing lxml to detect the encoding
        parser = etree.XMLParser(remove_blank_text=True)
        xml_tree_root = etree.fromstring(xml_bytes, parser)

        # Serialize to a UTF-8 string and then prettify it
        xml_content_raw = etree.tostring(xml_tree_root, encoding='UTF-8', xml_declaration=True).decode('utf-8')
        xml_content = pretty_print_xml(xml_content_raw)
        
        logger.info("Successfully prepared XML content.")
        return xml_content

    except etree.XMLSyntaxError as e:
        logger.error(f"XML syntax error in {xml_path}: {e}")
        return None
    except IOError as e:
        logger.error(f"Failed to read XML file {xml_path}: {e}")
        return None

def write_geo_metadata(ds: Optional[gdal.Dataset], xml_path: Path):
    """
    Writes XML content to a GeoTIFF's GEO_METADATA tag (50909).

    Args:
        ds: An open GDAL Dataset object.
        xml_path: Path to the XML file with metadata content.
    """
    xml_content = prepare_xml_for_gdal(xml_path)
    
    if ds and xml_content:
        try:
            ds.SetMetadataItem('GEO_METADATA', xml_content)
            logger.info("Successfully wrote GEO_METADATA to the TIFF file.")
            ds.FlushCache()
            logger.info("Flushed changes to disk.")
        except RuntimeError as e:
            logger.error(f"An error occurred during GDAL operation: {e}")
            raise
    elif not xml_content:
        logger.warning(f"Could not write metadata; XML preparation failed for {xml_path}.")
    else: # ds is None
        logger.warning("GDAL dataset is not open. Cannot write metadata.")