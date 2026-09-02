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
        >>> folder, json_file, gpkg_file = generate_output_paths(Path('example.tif'))
        >>> [folder.name, json_file.name, gpkg_file.name]
        ['example_validation', 'example_validation_results.json', 'example_validation_map.gpkg']

        >>> folder, _, _ = generate_output_paths(Path('tiles'))   # a directory
        >>> folder.name
        'tiles_validation'

        >>> folder, _, _ = generate_output_paths(Path('example.tif'), Path('reports'))
        >>> folder.as_posix()
        'reports/example_validation'

        A file that has not been written yet is still named as a file:

        >>> folder, _, _ = generate_output_paths(Path('not_yet_written.tif'))
        >>> folder.name
        'not_yet_written_validation'
    """
    # Determine basename and parent
    if input_path.is_dir():
        # Directory input - use directory name
        basename = input_path.name
    elif input_path.is_file() or input_path.suffix:
        # A file, or a file-shaped path that has not been written yet. Testing
        # the suffix matters because callers build output paths for inputs that
        # do not exist on disk; without it '/data/tile.tif' would be treated as
        # a directory and every output would carry '.tif' in its name.
        basename = input_path.stem
    else:
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
        ...     Path('tiles/tile_001_DSM.tif'),
        ...     Path('tiles_validation'),
        ...     'PASS',
        ...     'html'
        ... ).as_posix()
        'tiles_validation/reports/tile_001_DSM_PASS.html'

        >>> generate_report_path(
        ...     Path('tiles/tile_002_DSM.tif'),
        ...     Path('tiles_validation'),
        ...     'FAIL',
        ...     'md'
        ... ).as_posix()
        'tiles_validation/reports/tile_002_DSM_FAIL.md'
    """
    stem = input_file.stem
    suffix = f"_{overall_status}"
    filename = f"{stem}{suffix}.{report_format}"
    reports_folder = output_folder / 'reports'
    return reports_folder / filename


def get_input_files(input_path: Path, name_filter: str = '') -> list:
    """
    Get list of GeoTIFF files to process, applying name filter if provided.

    Args:
        input_path: File or directory path
        name_filter: Optional substring to filter filenames (directory mode only)

    Returns:
        List of Path objects for files to validate

    Examples:
        >>> [f.name for f in get_input_files(Path('example.tif'))]
        ['example.tif']

        >>> [f.name for f in get_input_files(Path('tiles'))]
        ['tile_001_DSM.tif', 'tile_002_DSM.tif', 'tile_003_DTM.tif']

        >>> [f.name for f in get_input_files(Path('tiles'), name_filter='DSM')]
        ['tile_001_DSM.tif', 'tile_002_DSM.tif']
    """
    if input_path.is_file():
        return [input_path]

    # Collect all GeoTIFF files. By suffix, lower-cased: Path.glob('*.tif') is
    # case-sensitive on Linux and not on Windows, so a directory of .TIF files validated
    # completely on one and "found nothing" on the other.
    if not input_path.is_dir():
        return []
    geotiffs = sorted(p for p in input_path.iterdir()
                      if p.is_file() and p.suffix.lower() in ('.tif', '.tiff'))

    # Apply name filter if provided
    if name_filter:
        filtered = [f for f in geotiffs if name_filter in f.name]
        return filtered

    return geotiffs
