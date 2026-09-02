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
Command-line interface for the GeoTIFF ToolKit (GTTK).

This script provides the main entry point for the `gttk` command,
parsing user arguments and dispatching them to the appropriate tool.
"""
import argparse
import logging
import os
import sys
import textwrap
import numpy as np
from pathlib import Path
from gttk.utils.log_helpers import setup_logger
import gttk.utils.optimize_constants as oc
import gttk.utils.cli_help as ch
from gttk.utils.cli_help import GttkHelpFormatter, ShowDefaultsAction
from osgeo import gdal
from gttk.utils.script_arguments import CompareArguments, ReadArguments, OptimizeArguments, TestArguments, ValidateArguments
from gttk.utils.validation.loader import bundled_rules_dir


def _check_proj_env() -> None:
    """Warn once at startup if neither PROJ_DATA nor PROJ_LIB is set.

    PROJ 8+ uses PROJ_DATA; PROJ_LIB is the pre-8 name, deprecated but still
    honored. A healthy conda-forge install sets PROJ_DATA on activation, so
    this warning only fires when the env is genuinely unconfigured.
    """
    if 'PROJ_DATA' in os.environ or 'PROJ_LIB' in os.environ:
        return
    logging.getLogger(__name__).warning(
        "Neither PROJ_DATA nor PROJ_LIB is set. EPSG code lookups may fail "
        "if GDAL cannot find the proj.db database. Activate your conda env "
        "or set PROJ_DATA to your PROJ share directory."
    )

def str2bool(v):
    if isinstance(v, bool):
        return v
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')

def parse_decimals(v):
    """argparse type for --decimals: a non-negative integer, or 'none'/'off'/'keep' to keep
    full precision (no base-10 rounding)."""
    if isinstance(v, str) and v.strip().lower() in ('none', 'off', 'keep'):
        return 'none'
    try:
        n = int(v)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError("decimals must be a non-negative integer or 'none'")
    if n < 0:
        raise argparse.ArgumentTypeError("decimals must be >= 0 (or 'none' to keep full precision)")
    return n

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

#: How the tools that read an external XML metadata file find it (path_helpers.find_xml_metadata_file).
SIDECAR_SEARCH = textwrap.fill(
    "External XML metadata is looked up by name, and the first match is used: <stem>.xml, "
    "then <stem>_meta.xml, beside the raster; then the same two names in the raster's parent "
    "directory; then <stem>.xml in a metadatos/ directory beside the raster's directory "
    "(INEGI's delivery layout).", width=78)


def build_parser() -> argparse.ArgumentParser:
    """Build the complete gttk argument parser.

    Split out from main() so the rendered help can be exercised by tests without
    dispatching to a tool.
    """
    parser = argparse.ArgumentParser(
        description='GTTK',
        formatter_class=GttkHelpFormatter
    )
    subparsers = parser.add_subparsers(dest='tool', help='Available tools')
    subparsers.required = True

    # --- Compare Compression Tool ---
    compare_parser = subparsers.add_parser(
        'compare',
        help='Compare compression settings and metadata between two GeoTIFF files.',
        formatter_class=GttkHelpFormatter
    )
    compare_parser.add_argument('-i', '--input', '--baseline', required=True, type=Path, metavar='PATH', dest='input_path', help='The baseline (or original) GeoTIFF for comparison.')
    compare_parser.add_argument('-o', '--output', '--comparison', required=True, type=Path, metavar='PATH', dest='output_path', help='The comparison (or processed) GeoTIFF.')
    # '--report_format' is the historic spelling; every other subcommand and the README
    # use the hyphen, so that is the primary name and the underscore stays as an alias.
    compare_parser.add_argument('-f', '--report-format', '--report_format', type=str.lower, default='html', choices=['html', 'md'], dest='report_format', help='Output format for the report file.')
    compare_parser.add_argument('--open-report', type=str2bool, default=True, metavar='BOOL', dest='open_report', help='Open the report automatically after generation.')
    compare_parser.add_argument('-v', '--verbose', action='store_true', dest='verbose', help='Enable verbose logging.')

    # --- Optimize Compression Base Arguments ---
    # Help strings that state a default read it back from the resolver
    # (gttk.utils.cli_help), so they cannot drift from what the tool actually does.
    def add_optimize_args(p):
        required = p.add_argument_group('required')
        required.add_argument('-i', '--input', required=True, type=Path, metavar='PATH', dest='input_path', help='Input source GeoTIFF file path.')
        required.add_argument('-o', '--output', required=True, type=Path, metavar='PATH', dest='output_path', help='Output COG file path.')
        required.add_argument('-t', '--product-type', required=True, type=str.lower, choices=list(ch.PRODUCT_TYPES), dest='product_type',
                              help='Type of GeoTIFF product. This is what selects the defaults for '
                                   'most of the options below; see the table at the end of this help.')

        compression = p.add_argument_group('compression')
        compression.add_argument('-a', '--algorithm', type=str.upper, choices=['JPEG', 'JXL', 'LZW', 'DEFLATE', 'ZSTD', 'LERC', 'NONE'], dest='algorithm',
                                 help=f"Compression algorithm. Default: {ch.default_clause('algorithm')}. "
                                      f"JPEG/JXL are for imagery only; LERC is for "
                                      f"{', '.join(oc.LERC_PRODUCT_TYPES)}.")
        compression.add_argument('-p', '--predictor', type=int, choices=[1, 2, 3], dest='predictor',
                                 help=f"Predictor, for LZW/DEFLATE/ZSTD only. Default: "
                                      f"{ch.default_clause('predictor', algorithm='DEFLATE')}. "
                                      f"3 is the floating-point predictor and falls back to 2 on integer data.")
        compression.add_argument('-l', '--level', type=int, dest='level',
                                 help=f"Compression level, for DEFLATE/ZSTD only. Default: "
                                      f"{ch.default_clause('level', algorithm='DEFLATE')} (DEFLATE), "
                                      f"{ch.default_clause('level', algorithm='ZSTD')} (ZSTD).")
        compression.add_argument('-q', '--quality', type=valid_quality, metavar='75-100', dest='quality',
                                 help=f"Quality, for JPEG/JXL only. Default: "
                                      f"{ch.default_clause('quality', algorithm='JPEG')}. "
                                      f"100 selects lossless JXL.")
        compression.add_argument('-z', '--max-z-error', type=float, dest='max_z_error',
                                 help=f"Max Z error, for LERC only. Default: "
                                      f"{ch.default_clause('max_z_error', types=oc.LERC_PRODUCT_TYPES, algorithm='LERC')}. "
                                      f"Thematic LERC must stay lossless: a non-zero value is rejected "
                                      f"because it merges adjacent class codes.")
        compression.add_argument('-d', '--decimals', type=parse_decimals, dest='decimals',
                                 help=f"Decimal places to round DEM/error/scientific data, or 'none' (also 'off' or 'keep') "
                                      f"to keep full precision. Applies to LZW/DEFLATE/ZSTD only. Default: "
                                      f"{ch.default_clause('decimals', algorithm='DEFLATE')}. Values "
                                      f"finer than the data type can represent are treated as 'none'.")

        overviews = p.add_argument_group('overviews')
        overviews.add_argument('--overviews', type=str2bool, default=True, metavar='BOOL', dest='overviews', help='Generate internal overviews. Default: True.')
        # These two carry the longest choice lists in the CLI.  Left as the metavar they
        # blow past 80 columns in the usage block as one unbreakable token, so name them
        # and let the help text carry the list, where it can wrap.
        overviews.add_argument('--overview-resampling', type=str.upper, choices=list(oc.OVERVIEW_RESAMPLING_CHOICES), metavar='KERNEL', dest='overview_resampling',
                               help=f"Resampling kernel for overviews: "
                                    f"{', '.join(oc.OVERVIEW_RESAMPLING_CHOICES)}. Default: "
                                    f"{ch.default_clause('overview_resampling')}. Categorical data must "
                                    f"not be interpolated, so an interpolating kernel is rejected for 'thematic'.")
        overviews.add_argument('--overview-compress', type=str.upper, choices=list(oc.OVERVIEW_COMPRESS_CHOICES), metavar='CODEC', dest='overview_compress',
                               help=f"Compression for overviews: {', '.join(oc.OVERVIEW_COMPRESS_CHOICES)}. "
                                    f"Default: same as --algorithm.")
        overviews.add_argument('--overview-predictor', type=int, choices=[1, 2, 3], dest='overview_predictor', help='Predictor for overviews. Default: same as --predictor.')

        masking = p.add_argument_group('masking and nodata')
        masking.add_argument('-n', '--nodata', type=float_nodata, default=None, dest='nodata', help="NoData value, for any product type; 'nan' selects NaN. Default: inherited from the input file.")
        # default=None, not True: _resolve_defaults already supplies True (and forces
        # False for thematic), and argparse pre-empting it made every run look as though
        # the caller had asked for the value.
        masking.add_argument('--mask-alpha', type=str2bool, default=None, metavar='BOOL', dest='mask_alpha', help='If True, convert alpha band (if present) to internal mask (e.g. RGB+mask). If False, preserve unchanged (e.g. RGBA). Default: True, except thematic (False).')
        masking.add_argument('--mask-nodata', type=str2bool, default=None, metavar='BOOL', dest='mask_nodata',
                             help=f"If True, add NoData pixels to transparency mask. Default: "
                                  f"{ch.default_clause('mask_nodata')}.")

        georef = p.add_argument_group('georeferencing and metadata')
        georef.add_argument('-r', '--raster-type', type=str.lower, choices=['point', 'area'], dest='raster_type',
                            help=f"Override raster type ('point' for PixelIsPoint, 'area' for PixelIsArea). "
                                 f"Default: {ch.default_clause('raster_type').lower()}.")
        georef.add_argument('-s', '--vertical-srs', type=str, default=None, dest='vertical_srs', help="Vertical SRS, e.g. EPSG:5703. Required for 'dem'.")
        georef.add_argument('-g', '--geo-metadata', type=str2bool, default=False, metavar='BOOL', dest='geo_metadata', help='Write the external XML file (.xml or _meta.xml) to the GEO_METADATA tag.')
        georef.add_argument('-w', '--write-pam-xml', type=str2bool, default=True, metavar='BOOL', dest='write_pam_xml', help='Write an Esri-compatible .aux.xml PAM statistics file.')

        output = p.add_argument_group('output file')
        output.add_argument('--cog', type=str2bool, default=True, metavar='BOOL', dest='cog', help='Create a COG. Default: True.')
        output.add_argument('--tile-size', type=int, default=512, metavar='PX', dest='tile_size', help='Tile size in pixels for primary layer and overviews. Default: 512.')
        output.add_argument('--num-threads', type=str, default=None, metavar='N', dest='num_threads',
                            help=f"Worker threads for compression: an integer or ALL_CPUS. Default: "
                                 f"{ch.default_clause('num_threads')}. Lower it when running several "
                                 f"gttk processes in parallel.")

        report = p.add_argument_group('report')
        report.add_argument('--report', type=str2bool, default=True, metavar='BOOL', dest='report', help='Generate the before/after comparison report. Default: True. Set False for batch runs.')
        report.add_argument('-f', '--report-format', type=str.lower, default='html', choices=['html', 'md'], dest='report_format', help='Output format for the report file.')
        report.add_argument('--report-suffix', type=str, default='_comp', dest='report_suffix', help='Suffix for the report filename.')
        report.add_argument('--open-report', type=str2bool, default=True, metavar='BOOL', dest='open_report', help='Open the report automatically after generation.')

        p.add_argument('--show-defaults', action=ShowDefaultsAction, metavar='TYPE',
                       choices=['all'] + list(ch.PRODUCT_TYPES),
                       help='Print every setting that would be used, and where each one comes '
                            'from, then exit. Give a product type or omit it for all of them.')
        p.add_argument('-v', '--verbose', action='store_true', dest='verbose', help='Enable verbose logging.')

    # --- Optimize Compression (CLI) Tool ---
    optimize_parser = subparsers.add_parser(
        'optimize',
        help='Optimize a GeoTIFF using command-line tools.',
        formatter_class=GttkHelpFormatter,
        epilog=ch.profile_table() + '\n\n' + SIDECAR_SEARCH
    )
    add_optimize_args(optimize_parser)

    # --- Optimize Compression (ArcGIS) Tool ---
    optimize_arc_parser = subparsers.add_parser(
        'optimize-arc',
        help='Optimize a GeoTIFF from an ArcGIS toolbox using standalone GDAL.',
        formatter_class=GttkHelpFormatter,
        epilog=ch.profile_table() + '\n\n' + SIDECAR_SEARCH
    )
    add_optimize_args(optimize_arc_parser)
    optimize_arc_parser.add_argument('--arc-mode', type=str2bool, default=True, metavar='BOOL', dest='arc_mode', help='Flag to indicate ArcGIS Pro execution mode.')

    # --- Test Compression Tool ---
    test_compression_parser = subparsers.add_parser(
        'test',
        help='Test various compression settings on a GeoTIFF and generate a performance report.',
        formatter_class=GttkHelpFormatter
    )
    test_compression_parser.add_argument('-i', '--input', required=True, type=Path, metavar='PATH', dest='input_path', help='The source GeoTIFF file or directory to use for testing.')
    test_compression_parser.add_argument('-o', '--output', type=Path, metavar='PATH', dest='output_path', help='Path to save the output report table in Excel format (.xlsx). Default: derived from the input name, alongside the input.')
    csv_group = test_compression_parser.add_mutually_exclusive_group(required=True)
    csv_group.add_argument('-c', '--csv-params', type=Path, metavar='PATH', dest='csv_path', help='Path to a CSV file with compression parameters to test.')
    csv_group.add_argument('-t', '--product-type', type=str.lower, choices=['dem', 'image', 'error', 'scientific', 'thematic'], dest='product_type', help='Use a preset template of compression parameters for the specified product type.')
    test_compression_parser.add_argument('--temp-dir', type=Path, default=None, metavar='PATH', dest='temp_dir', help='Directory for the temporary compressed GeoTIFFs; each run uses a run_* subdirectory of it. Default: a <input stem>_gttk_test directory beside the output workbook.')
    test_compression_parser.add_argument('--log-file', type=Path, metavar='PATH', dest='log_file', help='Path to a log file for debugging. Default: test_compression_debug.log in the temporary directory.')
    test_compression_parser.add_argument('--delete-test-files', type=str2bool, default=True, metavar='BOOL', dest='delete_test_files', help='Delete the temporary compressed GeoTIFFs after the test. Default: True. Each candidate\'s comparison report stays in the run directory.')
    test_compression_parser.add_argument('--open-report', type=str2bool, default=True, metavar='BOOL', dest='open_report', help='Open the Excel report automatically after generation.')
    test_compression_parser.add_argument('--arc-mode', type=str2bool, default=False, metavar='BOOL', dest='arc_mode', help='Flag to indicate ArcPy execution mode.')
    test_compression_parser.add_argument('--optimize-script', type=Path, metavar='PATH', dest='optimize_script_path', help='Path to the optimize_compression.py script. Default: the installed gttk package is used directly.')
    test_compression_parser.add_argument('-v', '--verbose', action='store_true', dest='verbose', help='Enable verbose logging.')

    # --- Read Metadata Tool ---
    read_metadata_parser = subparsers.add_parser(
        'read',
        help='Read and report metadata from a GeoTIFF file.',
        formatter_class=GttkHelpFormatter,
        epilog=SIDECAR_SEARCH
    )
    read_metadata_parser.add_argument('-i', '--input', required=True, type=Path, metavar='PATH', dest='input_path', help='Path to the input GeoTIFF file.')
    read_metadata_parser.add_argument('-p', '--page', type=int, default=0, dest='page', help='Image File Directory (IFD) page to read.')
    read_metadata_parser.add_argument('-b', '--banner', type=str, required=False, dest='banner', help='Text for a banner at the top/bottom of the report, such as classification. Default: no banner.')
    read_group = read_metadata_parser.add_mutually_exclusive_group(required=False)
    read_group.add_argument('-r', '--reader-type', type=str.lower, default='producer',choices=['analyst', 'producer'], dest='reader_type', help='Target reader type.')
    read_group.add_argument('-s', '--sections', type=str, nargs='*', dest='sections', help='Specific metadata sections to include in the report. Default: the set implied by --reader-type.')
    read_metadata_parser.add_argument('-x', '--xml-type', type=str.lower, default='table', choices=['table', 'text'], dest='xml_type', help='Whether to present the metadata as a table or as syntax-highlighted text.')
    read_metadata_parser.add_argument('-t', '--tag-scope', type=str.lower, default='complete', choices=['complete', 'compact'], dest='tag_scope', help='Level of detail for TIFF tags.')
    read_metadata_parser.add_argument('-w', '--write-pam-xml', type=str2bool, default=False, metavar='BOOL', dest='write_pam_xml', help='Generate a .aux.xml file with statistics.')
    read_metadata_parser.add_argument('-f', '--report-format', type=str.lower, default='html', dest='report_format', choices=['html', 'md'], help='Format for the output report.')
    read_metadata_parser.add_argument('--report-suffix', type=str, default='_meta', dest='report_suffix', help='Suffix to append to the output report filename.')
    read_metadata_parser.add_argument('--open-report', type=str2bool, default=True, metavar='BOOL', dest='open_report', help='Open the report automatically after generation.')
    read_metadata_parser.add_argument('--arc-mode', type=str2bool, default=False, metavar='BOOL', dest='arc_mode', help='Flag to indicate ArcPy execution mode.')
    read_metadata_parser.add_argument('-v', '--verbose', action='store_true', dest='verbose', help='Enable verbose logging.')

    # --- Validate Metadata Tool ---
    validate_parser = subparsers.add_parser(
        'validate',
        help='Validate GeoTIFF metadata against product-specific requirements.',
        formatter_class=GttkHelpFormatter,
        epilog=SIDECAR_SEARCH
    )
    validate_parser.add_argument(
        '-i', '--input',
        required=True,
        type=Path,
        metavar='PATH',
        dest='input_path',
        help='Path to GeoTIFF file or directory to validate. '
             'If directory, all .tif/.tiff files will be processed (optionally filtered by --name-filter).'
    )
    validate_parser.add_argument(
        '-p', '--product',
        required=True,
        type=str,
        dest='product',
        help='Validation product name (must match a profile in the rules file). '
             'Example: DGED5, 3DEP, NAIP, GLO-30'
    )
    validate_parser.add_argument(
        '-r', '--rules-dir',
        type=Path,
        metavar='PATH',
        default=bundled_rules_dir(),
        dest='rules_dir',
        help='Directory containing TOML validation rule files. '
             'Default: the rules bundled with GTTK.'
    )
    validate_parser.add_argument(
        '-s', '--sections',
        type=str,
        nargs='*',
        dest='sections',
        help='Specific sections to validate (e.g., tag geokey gdal xml). '
             'Default: all sections with rules.'
    )
    validate_parser.add_argument(
        '-n', '--name-filter',
        type=str,
        default='',
        dest='name_filter',
        help='Filter files by name substring when processing directories. '
             'Only files containing this string will be validated. '
             'Example: --name-filter DSM processes only files with "DSM" in the name. '
             'Only applicable when --input is a directory. Default: no filter.'
    )
    validate_parser.add_argument(
        '-o', '--output-dir',
        type=Path,
        metavar='PATH',
        default=None,
        dest='output_dir',
        help='Parent directory for the validation output folder, which holds the JSON results '
             'and the optional HTML/MD reports. Default: <basename>_validation/ beside the input.'
    )
    validate_parser.add_argument(
        '-w', '--write-reports',
        type=str2bool,
        metavar='BOOL',
        default=True,
        dest='write_reports',
        help='Write individual HTML/MD validation reports for each file. '
             'Reports include _PASS or _FAIL suffix.'
    )
    validate_parser.add_argument(
        '-f', '--report-format',
        type=str.lower,
        default='html',
        choices=['html', 'md'],
        dest='report_format',
        help='Output format for validation reports (html or md).'
    )
    validate_parser.add_argument(
        '--open-report',
        type=str2bool,
        metavar='BOOL',
        default=True,
        dest='open_report',
        help='Automatically open the JSON results file after generation.'
    )
    validate_parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        dest='verbose',
        help='Enable verbose logging for detailed debugging information.'
    )

    return parser

def main():
    # GTTK is a library: it applies GDAL's exception mode per operation rather than
    # at import, so this application makes the choice for its own process.
    gdal.UseExceptions()
    """
    Main function to parse arguments and call the appropriate tool.
    """
    parser = build_parser()
    args = parser.parse_args()
    tool = args.tool
    args_dict = vars(args)
    args_dict.pop('tool', None)

    # --- Logger Setup ---
    log_level = logging.DEBUG if args.verbose else logging.INFO
    is_arc = getattr(args, 'arc_mode', False)
    logger = setup_logger(level=log_level, is_arc_mode=is_arc)

    # Skip in ArcGIS mode — ArcGIS brings its own GDAL/PROJ and legitimately
    # has neither variable set.
    if not is_arc:
        _check_proj_env()

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
        elif tool == 'validate':
            from gttk.tools.validate_metadata import validate_metadata
            script_args = ValidateArguments(**args_dict)
            validate_metadata(script_args)
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()