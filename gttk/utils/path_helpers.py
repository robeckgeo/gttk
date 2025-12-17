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
File and Directory Path Utilities for GTTK.

This module provides helper functions for file system operations, such as
recursively finding GeoTIFF files, preparing output paths while preserving
directory structures, and locating associated XML metadata files based on
common naming conventions.
"""
import os
from pathlib import Path
import logging
from gttk.utils.geokey_parser import is_geotiff
from typing import List, Optional

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = ('.tif', '.tiff')

def get_geotiff_files(input_path: str) -> List[str]:
    """
    Get a list of GeoTIFF files from an input path (file or directory).

    Args:
        input_path (str): The path to a single GeoTIFF file or a directory.

    Returns:
        List[str]: A list of absolute paths to GeoTIFF files.
    """
    geotiff_files = []
    if os.path.isdir(input_path):
        for root, _, files in os.walk(input_path):
            for file in files:
                if file.lower().endswith(SUPPORTED_EXTENSIONS):
                    filepath = os.path.join(root, file)
                    if is_geotiff(Path(filepath)):
                        geotiff_files.append(filepath)
    elif os.path.isfile(input_path) and input_path.lower().endswith(SUPPORTED_EXTENSIONS):
        if is_geotiff(Path(input_path)):
            geotiff_files.append(os.path.abspath(input_path))
    return geotiff_files

def prepare_output_path(input_path: str, output_path: str, file_path: str) -> str:
    """
    Construct the full output path for a processed file, preserving directory structure.

    Args:
        input_path (str): The root input directory.
        output_path (str): The root output directory.
        file_path (str): The full path to the input file being processed.

    Returns:
        str: The full path for the corresponding output file.
    """
    relative_path = os.path.relpath(file_path, input_path)
    return os.path.join(output_path, relative_path)

def copy_folder_structure(input_folder: str, output_folder: str):
    """
    Create a matching folder structure in the output directory.

    Args:
        input_folder (str): The source folder.
        output_folder (str): The destination folder.
    """
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    for root, dirs, _ in os.walk(input_folder):
        for dir_name in dirs:
            input_dir = os.path.join(root, dir_name)
            relative_dir = os.path.relpath(input_dir, input_folder)
            output_dir = os.path.join(output_folder, relative_dir)
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)

def find_xml_metadata_file(tiff_path: Path) -> Optional[Path]:
    """
    Finds the corresponding XML metadata file matching the GeoTIFF's base filename.

    Search order:
    1. Same directory as the TIFF file: {basename}.xml, then {basename}_meta.xml
    2. Parent directory: {basename}.xml, then {basename}_meta.xml
    3. 'metadatos' subdirectory in parent (INEGI convention): {basename}.xml

    Args:
        tiff_path: The Path object of the input GeoTIFF file.

    Returns:
        The Path object of the found XML file, or None if no file is found.
    """
    base_name = tiff_path.stem
    dir_path = tiff_path.parent
    parent_dir_path = dir_path.parent
    metadatos_path = parent_dir_path / "metadatos"

    # Check in the same directory first
    exact_match_same_dir = dir_path / f"{base_name}.xml"
    meta_match_same_dir = dir_path / f"{base_name}_meta.xml"

    # Prioritize .xml over _meta.xml
    if exact_match_same_dir.is_file():
        return exact_match_same_dir
    if meta_match_same_dir.is_file():
        return meta_match_same_dir

    # Check in the parent directory if not found in the same directory
    exact_match_parent_dir = parent_dir_path / f"{base_name}.xml"
    meta_match_parent_dir = parent_dir_path / f"{base_name}_meta.xml"

    if exact_match_parent_dir.is_file():
        return exact_match_parent_dir
    if meta_match_parent_dir.is_file():
        return meta_match_parent_dir
    
    # Check in the 'metadatos' directory (INEGI convention, don't use '_meta' suffix)
    exact_match_metadatos_dir = metadatos_path / f"{base_name}.xml"

    if exact_match_metadatos_dir.is_file():
        return exact_match_metadatos_dir

    return None