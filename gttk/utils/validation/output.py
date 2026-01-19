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
Output Path Generation for Validation Package.

This module handles generating output folder paths and file names
for validation results, including the PASS/FAIL suffix convention.

Functions:
    generate_output_paths: Generate output folder and JSON file paths
    generate_report_path: Generate per-file report path with PASS/FAIL suffix
"""

from pathlib import Path
from typing import Optional, Tuple


def generate_output_paths(
    input_path: Path,
    output_dir: Optional[Path] = None
) -> Tuple[Path, Path, Path]:
    """
    Generate output folder, JSON file, and GeoPackage file paths.

    Creates a `{basename}_validation/` folder structure for validation outputs.
    The folder contains the primary JSON results file, GeoPackage with file
    footprints, and a `reports/` subfolder for HTML/MD reports.

    Args:
        input_path: Input file or directory path
        output_dir: Optional parent directory for output folder.
                   If not specified, creates alongside input.

    Returns:
        Tuple of (output_folder_path, json_file_path, gpkg_file_path)

    Examples:
        >>> generate_output_paths(Path('/data/example.tif'))
        (Path('/data/example_validation'),
         Path('/data/example_validation/example_validation_results.json'),
         Path('/data/example_validation/example_validation_map.gpkg'))

        >>> generate_output_paths(Path('/data/tiles/'))
        (Path('/data/tiles_validation'),
         Path('/data/tiles_validation/tiles_validation_results.json'),
         Path('/data/tiles_validation/tiles_validation_map.gpkg'))

        >>> generate_output_paths(Path('/data/example.tif'), Path('/reports'))
        (Path('/reports/example_validation'),
         Path('/reports/example_validation/example_validation_results.json'),
         Path('/reports/example_validation/example_validation_map.gpkg'))
    """
    # Determine basename and parent
    if input_path.is_file():
        basename = input_path.stem
        parent = input_path.parent
    else:
        # Directory input - use directory name
        basename = input_path.name
        parent = input_path.parent

    # Determine output parent directory
    if output_dir is not None:
        parent = output_dir

    # Build paths
    folder_name = f"{basename}_validation"
    output_folder = parent / folder_name
    json_file = output_folder / f"{folder_name}_results.json"
    gpkg_file = output_folder / f"{folder_name}_map.gpkg"

    return output_folder, json_file, gpkg_file


def generate_report_path(
    input_file: Path,
    output_folder: Path,
    overall_status: str,
    report_format: str
) -> Path:
    """
    Generate per-file report path with PASS/FAIL suffix in reports subfolder.

    Creates a filename like `example_PASS.html` or `example_FAIL.md`
    based on the overall validation status. Reports are placed in a
    `reports/` subfolder within the output folder.

    Args:
        input_file: The input GeoTIFF file
        output_folder: The output folder for validation results
        overall_status: Overall validation status ('PASS', 'FAIL', 'SKIP')
        report_format: Report format extension ('html' or 'md')

    Returns:
        Path to the report file in the reports subfolder

    Examples:
        >>> generate_report_path(
        ...     Path('/data/tile_001.tif'),
        ...     Path('/data/tiles_validation'),
        ...     'PASS',
        ...     'html'
        ... )
        Path('/data/tiles_validation/reports/tile_001_PASS.html')

        >>> generate_report_path(
        ...     Path('/data/tile_002.tif'),
        ...     Path('/data/tiles_validation'),
        ...     'FAIL',
        ...     'md'
        ... )
        Path('/data/tiles_validation/reports/tile_002_FAIL.md')
    """
    stem = input_file.stem
    suffix = f"_{overall_status}"
    filename = f"{stem}{suffix}.{report_format}"
    reports_folder = output_folder / 'reports'
    return reports_folder / filename


def get_input_files(input_path: Path, name_string: str = '') -> list:
    """
    Get list of GeoTIFF files to process, applying name filter if provided.

    Args:
        input_path: File or directory path
        name_string: Optional substring to filter filenames (directory mode only)

    Returns:
        List of Path objects for files to validate

    Examples:
        >>> get_input_files(Path('data/example.tif'))
        [Path('data/example.tif')]

        >>> get_input_files(Path('data/'), name_string='DSM')
        [Path('data/tile_001_DSM.tif'), Path('data/tile_002_DSM.tif')]
    """
    if input_path.is_file():
        return [input_path]

    # Collect all GeoTIFF files
    tif_files = sorted(input_path.glob('*.tif'))
    tiff_files = sorted(input_path.glob('*.tiff'))
    geotiffs = tif_files + tiff_files

    # Apply name filter if provided
    if name_string:
        filtered = [f for f in geotiffs if name_string in f.name]
        return filtered

    return geotiffs
