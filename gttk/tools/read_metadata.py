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
GeoTIFF Metadata Reading and Reporting Tool for GTTK.

This module powers the 'read' command, providing a comprehensive utility to
extract and report metadata from TIFF and GeoTIFF files. It generates detailed
reports in HTML or Markdown, covering everything from TIFF tags and geokeys to
band statistics and COG validation.
"""

import logging
from pathlib import Path
from datetime import datetime, timezone
from osgeo import gdal
from gttk.utils.contexts import banner_context, output_format_context, xml_type_context
from gttk.utils.log_helpers import setup_logger
from gttk.utils.metadata_extractor import MetadataExtractor
from gttk.utils.path_helpers import open_file
from gttk.utils.report_builders import MetadataReportBuilder
from gttk.utils.report_formatters import HtmlReportFormatter, MarkdownReportFormatter
from gttk.utils.script_arguments import ReadArguments
from gttk.utils.section_registry import get_section_ids_from_args, filter_sections_for_page
from gttk.utils.statistics import write_pam_xml, build_pam_data_from_stats

# --- Configuration & Setup ---
gdal.SetConfigOption('GDAL_NUM_THREADS', 'ALL_CPUS')
logger = logging.getLogger('read_metadata')


def get_report_path(input_path: str, suffix: str, format: str) -> str:
    """
    Determine output file path for report.
    
    Args:
        input_path: Path to input GeoTIFF file
        suffix: Suffix to add to filename (e.g., '_meta')
        format: Output format ('html' or 'markdown')
        
    Returns:
        Full path to output report file
    """
    input_file = Path(input_path)
    extension = '.html' if format == 'html' else '.md'
    output_filename = f"{input_file.stem}{suffix}{extension}"
    return str(input_file.parent / output_filename)


def _generate_report_summary(input_path: str) -> str:
    """
    Generate report summary section with file information and FileInfo table.

    Args:
        input_path: Path to GeoTIFF file

    Returns:
        Markdown-formatted summary section with FileInfo table
    """
    from gttk.utils.geotiff_processor import (
        get_transparency_str,
        calculate_compression_efficiency,
        read_geotiff,
        determine_decimal_precision,
        estimate_image_quality,
        get_lerc_max_z_error
    )
    from gttk.utils.validate_cloud_optimized_geotiff import validate as validate_cog
    from gttk.utils.data_models import FileInfo
    from gttk.utils.section_renderers import MarkdownRenderer
    from gttk.utils.tiff_tag_parser import TiffTagParser
    from gttk.utils.metadata_extractor import PREDICTOR_ABBREV_MAP

    filepath = Path(input_path)
    file_stat = filepath.stat()

    # Date created
    try:
        creation_time = getattr(file_stat, 'st_birthtime', file_stat.st_ctime)
        dt_created_utc = datetime.fromtimestamp(creation_time, timezone.utc)
        date_created_str = dt_created_utc.strftime('%Y-%m-%d %H:%M:%S UTC')
    except Exception:
        creation_time = getattr(file_stat, 'st_birthtime', file_stat.st_ctime)
        date_created_str = datetime.fromtimestamp(creation_time).strftime('%Y-%m-%d %H:%M:%S')

    # Date modified
    try:
        dt_modified_utc = datetime.fromtimestamp(file_stat.st_mtime, timezone.utc)
        date_modified_str = dt_modified_utc.strftime('%Y-%m-%d %H:%M:%S UTC')
    except Exception:
        date_modified_str = datetime.fromtimestamp(file_stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')

    # Build text summary (without removed rows)
    current_date_str = datetime.now().strftime('%Y-%m-%d')
    lines = [
        "## Report Summary\n",
        f"**Report Date:** {current_date_str}  ",
        f"**File Name:** {filepath.name}  ",
        f"**Date Created:** {date_created_str}  ",
        f"**Date Modified:** {date_modified_str}  ",
        ""  # Blank line before FileInfo table
    ]

    # Build FileInfo table
    try:
        gdal.PushErrorHandler('CPLQuietErrorHandler')
        ds = gdal.Open(str(filepath), gdal.GA_ReadOnly)
        gdal.PopErrorHandler()

        if ds and ds.RasterCount > 0:
            # Get metadata for FileInfo
            info = read_geotiff(ds)
            file_size_bytes = filepath.stat().st_size
            size_mb = file_size_bytes / (1024 * 1024)
            efficiency = calculate_compression_efficiency(str(filepath))
            ratio = 100 / (100 - efficiency) if efficiency != 100 else 0

            compression = ds.GetMetadataItem('COMPRESSION', 'IMAGE_STRUCTURE') or 'NONE'
            decimals = determine_decimal_precision(ds)

            _, cog_errors, _ = validate_cog(ds, full_check=True)
            is_cog_str = "Yes" if not cog_errors else "No"
            is_bigtiff_str = "Yes" if info.is_bigtiff else "No"

            # Determine conditional columns
            has_quality = compression in ['JPEG', 'YCbCr JPEG', 'JXL']
            has_decimals = 'Float' in str(info.data_type)
            has_predictor = compression in ['LZW', 'DEFLATE', 'ZSTD']
            has_lerc = 'LERC' in compression

            # Get quality if applicable
            quality = None
            if has_quality:
                quality = estimate_image_quality(ds, compression)

            # Get predictor if applicable
            predictor = None
            if has_predictor:
                with TiffTagParser(str(filepath)) as parser:
                    tags = parser.get_tags()

                def get_predictor_val(tags):
                    for tag in tags:
                        if tag.code == 317:
                            return tag.value if isinstance(tag.value, int) else 1
                    return 1

                pred_val = get_predictor_val(tags)
                predictor = PREDICTOR_ABBREV_MAP.get(pred_val, "")

            # Get LERC error if applicable
            lerc_error = None
            if has_lerc:
                lerc_error = get_lerc_max_z_error(ds)

            # Create FileInfo (without 'File' column for single-file report)
            file_info = FileInfo(
                name=filepath.name,  # Not used since include_name=False
                data_type=info.data_type or "Unknown",
                is_cog=is_cog_str,
                is_bigtiff=is_bigtiff_str,
                algorithm=compression,
                bands=info.bands,
                transparency=get_transparency_str(info),
                quality=quality,
                decimals=decimals if has_decimals else None,
                predictor=predictor,
                max_z_error=lerc_error,
                size_mb=f"{size_mb:,.2f}",
                space_saving=f"{efficiency:.2f}%",
                ratio=f"{ratio:.2f}x"
            )

            # Render FileInfo table (without 'File' column)
            renderer = MarkdownRenderer()
            file_info_table = renderer.render_file_info(file_info, include_name=False)
            lines.append(file_info_table)

        ds = None
    except Exception as e:
        logger.debug(f"Error generating FileInfo table: {e}")
        lines.append("_File information table could not be generated._")

    return "\n".join(lines)


def read_metadata(args: ReadArguments):
    """
    Generate GeoTIFF metadata report using ReportFormatter.
    
    Args:
        args: Parsed command-line arguments
        
    Returns:
        0 on success, 1 on failure
    """
    # Set up logger with appropriate handlers for ArcGIS or CLI
    setup_logger(is_arc_mode=args.arc_mode, level=logging.INFO)
    
    logger.info("=== read_metadata.py started ===")
    logger.info(f"Arguments: {args}")
    
    # Validate input file
    try:
        # Set context variables from arguments
        output_format_context.set(args.report_format)
        xml_type_context.set(args.xml_type or 'text')
        banner_context.set(str(args.banner) if args.banner is not None else None)
        
        with MetadataExtractor(str(args.input_path)) as extractor:
            # DIAGNOSTIC: Log is_geotiff status before filtering
            logger.info(f"File is_geotiff status: {extractor.is_geotiff}")
            
            # Get section IDs based on arguments
            section_ids = get_section_ids_from_args(args)
            logger.info(f"Section IDs from args (before filtering): {section_ids}")
            
            # Filter sections based on page and GeoTIFF status
            section_ids = filter_sections_for_page(
                section_ids,
                page=args.page,
                is_geotiff=extractor.is_geotiff
            )
            
            logger.info(f"Generating report with sections (after filtering): {section_ids}")
            
            # Build sections using MetadataReportBuilder
            builder = MetadataReportBuilder(
                extractor, 
                page=args.page, 
                tag_scope=args.tag_scope or 'complete',
                reader_type=args.reader_type
            )
            builder.build(section_ids)
            
            # Create appropriate formatter for desired file type
            if args.report_format == 'html':
                formatter = HtmlReportFormatter(filename=extractor.filepath.name)
                formatter.report_title = "Metadata Content"
            else:
                formatter = MarkdownReportFormatter(filename=extractor.filepath.name)
                formatter.report_title = "Metadata Content"
                formatter.include_title = True
            
    except (FileNotFoundError, ValueError) as e:
        logger.error(f"Input validation failed: {e}")
        return 1
    
    # Transfer sections from builder to formatter
    formatter.sections = builder.sections
    logger.info(f"Formatter prepared with {len(formatter.sections)} sections")
    logger.info(f"Report section IDs: {[section.id for section in formatter.sections]}")
    
    # Set sections in the renderer so it knows which sections are active
    # prepare_rendering handles this and other setup (like color maps)
    formatter.prepare_rendering()
    
    summary = _generate_report_summary(str(args.input_path))
    
    # Generate report with integrated summary
    try:
        if args.report_format == 'html':
            # For HTML, cast to HtmlReportFormatter and inject summary
            if not isinstance(formatter, HtmlReportFormatter):
                logger.error("Formatter type mismatch for HTML file. Aborting.")
                return 1
            
            # Get markdown body from sections
            parts = []
            parts.append(summary)  # Add summary first
            for section in formatter.sections:
                if section.has_data():
                    rendered = formatter._render_section(section)
                    if rendered:
                        parts.append(rendered)
            
            markdown_body = "\n\n".join(filter(None, parts))
            
            # Convert to HTML via formatter's methods
            html_body = formatter._markdown_to_html(markdown_body)
            final_report = formatter._wrap_in_html_template(html_body)
        else:
            # For Markdown, render header (title + TOC), then summary, then sections
            banner = banner_context.get()
            top_banner_md = f"<center>{banner}</center>\n\n" if banner else ""
            header_md = formatter._render_header()

            parts = [top_banner_md, header_md, summary]
            for section in formatter.sections:
                if section.has_data():
                    rendered = formatter._render_section(section)
                    if rendered:
                        parts.append(rendered)
            parts.append(formatter._render_footer())
            final_report = "\n\n".join(filter(None, parts))
    except Exception as e:
        logger.error(f"Error generating report: {e}")
        return 1
    
    # Determine output path
    suffix = args.report_suffix.replace("'", "").replace('"', '') if args.report_suffix else '_meta'
    output_path = get_report_path(str(args.input_path), suffix, args.report_format)
    logger.info(f"Output path: {output_path}")
    
    # Write PAM XML if requested
    if args.write_pam_xml and args.page == 0:
        try:
            with MetadataExtractor(str(args.input_path)) as extractor:
                stats = extractor.extract_statistics()
                if stats and extractor.gdal_ds:
                    pam_data = build_pam_data_from_stats(stats, extractor.gdal_ds)
                    write_pam_xml(str(args.input_path), pam_data)
                    logger.info("PAM XML (.aux.xml) written successfully")
                else:
                    logger.warning("No statistics available for PAM XML export")
        except Exception as e:
            logger.error(f"Failed to write PAM XML: {e}")
    
    # Write report to file
    try:
        with open(output_path, 'w', encoding='utf-8-sig') as f:
            f.write(final_report)
        logger.info(f"Report written successfully: {output_path}")
    except IOError as e:
        logger.error(f"Failed to write report: {e}")
        return 1
    
    # Open report if requested
    if args.open_report:
        try:
            open_file(output_path)
            logger.info(f"Opened report: {output_path}")
        except Exception as e:
            logger.warning(f"Could not open report: {e}")
    
    logger.info("Analysis completed successfully")
    return 0