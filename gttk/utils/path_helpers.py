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
File and Directory Path Utilities for GTTK.

This module provides helper functions for file system operations, such as
recursively finding GeoTIFF files, preparing output paths while preserving
directory structures, and locating associated XML metadata files based on
common naming conventions.
"""
import os
import sys
import subprocess
from pathlib import Path
import logging
from gttk.utils.geokey_parser import is_geotiff
from typing import List, Optional

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = ('.tif', '.tiff')

def _is_wsl() -> bool:
    """
    Detect if running in Windows Subsystem for Linux (WSL).

    Returns:
        bool: True if running in WSL, False otherwise
    """
    try:
        with open('/proc/version', 'r') as f:
            return 'microsoft' in f.read().lower()
    except (OSError, IOError):
        return False

def _convert_wsl_path_to_windows(wsl_path: str) -> str:
    """
    Convert WSL Linux path to Windows path format using wslpath utility.

    Args:
        wsl_path: Linux path in WSL (e.g., /home/user/file.html)

    Returns:
        Windows-formatted path (e.g., \\wsl.localhost\\Ubuntu\\home\\user\\file.html)
    """
    try:
        # Use wslpath utility to convert Linux path to Windows path
        result = subprocess.run(
            ['wslpath', '-w', wsl_path],
            capture_output=True,
            text=True,
            check=True,
            timeout=5
        )
        windows_path = result.stdout.strip()
        return windows_path
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
        # Fallback: manually construct path
        # Modern WSL uses wsl.localhost, older versions use wsl$
        wsl_path = os.path.abspath(wsl_path)
        windows_path = f"\\\\wsl.localhost\\Ubuntu{wsl_path.replace('/', '\\')}"
        return windows_path

def open_file(filename: str) -> None:
    """
    Open a file using the appropriate system default application.

    Handles platform-specific behavior:
    - Windows: Uses os.startfile()
    - macOS: Uses 'open' command
    - Linux (native): Uses xdg-open
    - WSL: Special handling based on file type:
        - Markdown/JSON files: Opens in WSL VS Code if available, else Windows default
        - HTML and other files: Opens in Windows default application

    Args:
        filename: Path to the file to open

    Raises:
        Exception: If the file cannot be opened
    """
    filename = str(filename)  # Ensure string (handles Path objects)

    if sys.platform == "win32":
        # Native Windows
        os.startfile(filename)
    elif _is_wsl():
        # Windows Subsystem for Linux
        file_ext = Path(filename).suffix.lower()
        opened_successfully = False

        if file_ext in ('.md', '.markdown', '.json'):
            # Try to open in VS Code first (common in WSL development environments)
            # Check if 'code' command is available
            code_available = subprocess.run(
                ['which', 'code'],
                capture_output=True,
                timeout=2
            ).returncode == 0

            if code_available:
                try:
                    result = subprocess.run(
                        ['code', filename],
                        check=False,  # Don't raise on non-zero exit
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if result.returncode == 0:
                        opened_successfully = True
                        try:
                            logger.debug(f"Opened {filename} in VS Code")
                        except:
                            pass  # Ignore logging errors
                except (subprocess.TimeoutExpired, FileNotFoundError) as e:
                    try:
                        logger.debug(f"Failed to open in VS Code: {e}")
                    except:
                        pass  # Ignore logging errors

        # If not opened in VS Code, use Windows default application
        if not opened_successfully:
            try:
                windows_path = _convert_wsl_path_to_windows(filename)
                try:
                    logger.debug(f"Opening {windows_path} with Windows default application")
                except:
                    pass  # Ignore logging errors
                # Use Popen to avoid waiting for the app to close
                subprocess.Popen(
                    ['powershell.exe', '-Command', f'Start-Process "{windows_path}"'],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            except Exception as e:
                try:
                    logger.error(f"Failed to open file with Windows application: {e}")
                except:
                    pass  # Ignore logging errors
                raise
    else:
        # macOS or native Linux
        opener = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.run([opener, filename], check=True)

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