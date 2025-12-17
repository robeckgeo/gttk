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
Command-line interface for the GeoTIFF ToolKit (GTTK).

This script provides the main entry point for the `gttk` command,
parsing user arguments and dispatching them to the appropriate tool.
"""
import argparse
import logging
import sys
import numpy as np
from pathlib import Path
from gttk.utils.log_helpers import setup_logger
from gttk.utils.script_arguments import CompareArguments, ReadArguments, OptimizeArguments, TestArguments

def str2bool(v):
    if isinstance(v, bool):
        return v
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')

def float_nodata(nodata_str: str) -> float:
    """Convert NoData string to float or np.nan."""
    if nodata_str.lower() == 'nan':
        return np.nan
    try:
        return float(nodata_str)
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid NoData value: '{nodata_str}'")

def valid_quality(value: str) -> int:
    """Validate that the quality value is an integer between 75 and 100."""
    try:
        ivalue = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"Quality must be an integer between 75 and 100, got '{value}'")
    if ivalue < 75 or ivalue > 100:
        raise argparse.ArgumentTypeError(f"Quality must be between 75 and 100, got '{ivalue}'")
    return ivalue

def main():
    """
    Main function to parse arguments and call the appropriate tool.
    """
    parser = argparse.ArgumentParser(
        description='GTTK',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    subparsers = parser.add_subparsers(dest='tool', help='Available tools')
    subparsers.required = True

    # --- Compare Compression Tool ---
    compare_parser = subparsers.add_parser(
        'compare',
        help='Compare compression settings and metadata between two GeoTIFF files.',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    compare_parser.add_argument('-i', '--input', '--baseline', required=True, type=Path, dest='input_path', help='The baseline (or original) GeoTIFF for comparison.')
    compare_parser.add_argument('-o', '--output', '--comparison', required=True, type=Path, dest='output_path', help='The comparison (or processed) GeoTIFF.')
    compare_parser.add_argument('-c', '--config', default='config.toml', help='Path to a custom configuration file.')
    compare_parser.add_argument('-f', '--report_format', type=str.lower, default='html', choices=['html', 'md'], dest='report_format', help='Output format for the report file.')
    compare_parser.add_argument('--open-report', type=str2bool, default=True, dest='open_report', help='Open the report automatically after generation.')
    compare_parser.add_argument('-v', '--verbose', action='store_true', dest='verbose', help='Enable verbose logging.')

    # --- Optimize Compression Base Arguments ---
    def add_optimize_args(p):
        p.add_argument('-i', '--input', required=True, type=Path, dest='input_path', help='Input source GeoTIFF file path.')
        p.add_argument('-o', '--output', required=True, type=Path, dest='output_path', help='Output COG file path.')
        p.add_argument('-t', '--product-type', required=True, type=str.lower,choices=['dem', 'image', 'error', 'scientific', 'thematic'], dest='product_type', help='Type of GeoTIFF product.')
        p.add_argument('-r', '--raster-type', type=str.lower, choices=['point', 'area'], dest='raster_type', help="Override raster type ('point' for PixelIsPoint, 'area' for PixelIsArea).")
        p.add_argument('-a', '--algorithm', required=True, type=str.upper, choices=['JPEG', 'JXL', 'LZW', 'DEFLATE', 'ZSTD', 'LERC', 'NONE'], dest='algorithm', help='Compression algorithm.')
        p.add_argument('-s', '--vertical-srs', type=str, default=None, dest='vertical_srs', help="Vertical SRS for 'dem' type.")
        p.add_argument('-n', '--nodata', type=float_nodata, default=None,dest='nodata', help="NoData value for 'dem' or 'error' type.")
        p.add_argument('-d', '--decimals', type=int, dest='decimals', help='Decimal places for rounding DEM/error data.')
        p.add_argument('-p', '--predictor', type=int, choices=[1, 2, 3], dest='predictor', help='Predictor for LZW/DEFLATE/ZSTD compression.')
        p.add_argument('-z', '--max-z-error', type=float, dest='max_z_error', help='Max Z error for LERC compression.')
        p.add_argument('-l', '--level', type=int, dest='level', help='Compression level for DEFLATE or ZSTD.')
        p.add_argument('-q', '--quality', type=valid_quality, dest='quality', help="JPEG quality (75-100) for 'image' type.")
        p.add_argument('-g', '--geo-metadata', type=str2bool, default=False, dest='geo_metadata', help='Write the external XML file (.xml or _meta.xml) to the GEO_METADATA tag.')
        p.add_argument('-w', '--write-pam-xml', type=str2bool, default=True, dest='write_pam_xml', help='Write an Esri-compatible .aux.xml PAM statistics file.')
        p.add_argument('--tile-size', type=int, default=512,dest='tile_size', help='Tile size in pixels for primary layer and overviews. Default: 512.')
        p.add_argument('--mask-alpha', type=str2bool, default=True, dest='mask_alpha', help='If True, convert alpha band (if present) to internal mask(e.g. RGB+mask). If False, preserve unchanged(e.g. RGBA). Default: True.')
        p.add_argument('--mask-nodata', type=str2bool, default=None, dest='mask_nodata', help='If True, add NoData pixels to transparency mask. Default: True for images, False for all others.')
        p.add_argument('--cog', type=str2bool, default=True, dest='cog', help='Create a COG (True/False, Yes/No). Default: True.')
        p.add_argument('--overviews', type=str2bool, default=True, dest='overviews', help='Generate internal overviews (True/False, Yes/No). Default: True.')
        p.add_argument('-f', '--report-format', type=str.lower, default='html', choices=['html', 'md'], dest='report_format', help='Output format for the report file.')
        p.add_argument('--report-suffix', type=str, default='_comp', dest='report_suffix', help='Suffix for the report filename.')
        p.add_argument('--open-report', type=str2bool, default=True, dest='open_report', help='Open the report automatically after generation.')
        p.add_argument('-v', '--verbose', action='store_true', dest='verbose', help='Enable verbose logging.')

    # --- Optimize Compression (CLI) Tool ---
    optimize_parser = subparsers.add_parser(
        'optimize',
        help='Optimize a GeoTIFF using command-line tools.',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    add_optimize_args(optimize_parser)

    # --- Optimize Compression (ArcGIS) Tool ---
    optimize_arc_parser = subparsers.add_parser(
        'optimize-arc',
        help='Optimize a GeoTIFF from an ArcGIS toolbox using standalone GDAL.',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    add_optimize_args(optimize_arc_parser)
    optimize_arc_parser.add_argument('--arc-mode', type=str2bool, default=True, dest='arc_mode', help='Flag to indicate ArcGIS Pro execution mode.')

    # --- Test Compression Tool ---
    test_compression_parser = subparsers.add_parser(
        'test',
        help='Test various compression settings on a GeoTIFF and generate a performance report.',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    test_compression_parser.add_argument('-i', '--input', required=True, type=Path, dest='input_path', help='The source GeoTIFF file or directory to use for testing.')
    test_compression_parser.add_argument('-o', '--output', type=Path, dest='output_path', help='Path to save the output report table in Excel format (.xlsx).')
    csv_group = test_compression_parser.add_mutually_exclusive_group(required=True)
    csv_group.add_argument('-c', '--csv-params', type=Path, dest='csv_path', help='Path to a CSV file with compression parameters to test.')
    csv_group.add_argument('-t', '--product-type', type=str.lower, choices=['dem', 'image', 'error', 'scientific', 'thematic'], dest='product_type', help='Use a preset template of compression parameters for the specified product type.')
    test_compression_parser.add_argument('--temp-dir', type=Path, default=Path('temp'), dest='temp_dir', help='Directory to store temporary compressed GeoTIFFs.')
    test_compression_parser.add_argument('--log-file', type=Path, dest='log_file', help='Path to a log file for debugging.')
    test_compression_parser.add_argument('--delete-test-files', type=str2bool, default=True, dest='delete_test_files', help='Delete temporary files after the test is complete.')
    test_compression_parser.add_argument('--open-report', type=str2bool, default=True, dest='open_report', help='Open the Excel report automatically after generation.')
    test_compression_parser.add_argument('--arc-mode', type=str2bool, default=False, dest='arc_mode', help='Flag to indicate ArcPy execution mode.')
    test_compression_parser.add_argument('--optimize-script', type=Path, dest='optimize_script_path', help='Path to the optimize_compression.py script.')
    test_compression_parser.add_argument('-v', '--verbose', action='store_true', dest='verbose', help='Enable verbose logging.')

    # --- Read Metadata Tool ---
    read_metadata_parser = subparsers.add_parser(
        'read',
        help='Read and report metadata from a GeoTIFF file.',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    read_metadata_parser.add_argument('-i', '--input', required=True, type=Path, dest='input_path', help='Path to the input GeoTIFF file.')
    read_metadata_parser.add_argument('-p', '--page', type=int, default=0, dest='page', help='Image File Directory (IFD) page to read.')
    read_metadata_parser.add_argument('-b', '--banner', type=str, required=False, dest='banner', help='Text for a banner at the top/bottom of the report, such as classification.')
    read_group = read_metadata_parser.add_mutually_exclusive_group(required=False)
    read_group.add_argument('-r', '--reader-type', type=str.lower, default='producer',choices=['analyst', 'producer'], dest='reader_type', help='Target reader type.')
    read_group.add_argument('-s', '--sections', type=str, nargs='*', dest='sections', help='Specific metadata sections to include in the report.')
    read_metadata_parser.add_argument('-x', '--xml-type', type=str.lower, default='table', choices=['table', 'text'], dest='xml_type', help='Whether to present the metadata as a table or as syntax-highlightedtext.')
    read_metadata_parser.add_argument('-t', '--tag-scope', type=str.lower, default='complete', choices=['complete', 'compact'], dest='tag_scope', help='Level of detail for TIFF tags.')
    read_metadata_parser.add_argument('-w', '--write-pam-xml', type=str2bool, default=False, dest='write_pam_xml', help='Generate a .aux.xml file with statistics.')
    read_metadata_parser.add_argument('-f', '--report-format', type=str.lower, default='html', dest='report_format', choices=['html', 'md'], help='Format for the output report.')
    read_metadata_parser.add_argument('--report-suffix', type=str, default='_meta', dest='report_suffix', help='Suffix to append to the output report filename.')
    read_metadata_parser.add_argument('--open-report', type=str2bool, default=True, dest='open_report', help='Open the report automatically after generation.')
    read_metadata_parser.add_argument('--arc-mode', type=str2bool, default=False, dest='arc_mode', help='Flag to indicate ArcPy execution mode.')
    read_metadata_parser.add_argument('-v', '--verbose', action='store_true', dest='verbose', help='Enable verbose logging.')

    args = parser.parse_args()
    tool = args.tool
    args_dict = vars(args)
    args_dict.pop('tool', None)

    # --- Logger Setup ---
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logger = setup_logger(level=log_level, is_arc_mode=getattr(args, 'arc_mode', False))

    try:
        if tool == 'compare':
            from gttk.tools.compare_compression import compare_compression
            script_args = CompareArguments(**args_dict)
            compare_compression(script_args)
        elif tool in ['optimize', 'optimize-arc']:
            script_args = OptimizeArguments(**args_dict)
            if tool == 'optimize':
                from gttk.tools.optimize_compression import optimize_compression
                optimize_compression(script_args)
            else:
                from gttk.tools.optimize_compression_arc import optimize_compression
                optimize_compression(script_args)
        elif tool == 'test':
            from gttk.tools.test_compression import test_compression
            if args.input_path:
                args.input_path = args.input_path.resolve()
            if args.output_path:
                args.output_path = args.output_path.resolve()
            if args.temp_dir:
                args.temp_dir = args.temp_dir.resolve()
            script_args = TestArguments(**args_dict)
            test_compression(script_args)
        elif tool == 'read':
            from gttk.tools.read_metadata import read_metadata
            script_args = ReadArguments(**args_dict)
            read_metadata(script_args)
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()