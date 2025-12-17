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
GeoTIFF Metadata Reading and Reporting Tool for GTTK.

This module powers the 'read' command, providing a comprehensive utility to
extract and report metadata from TIFF and GeoTIFF files. It generates detailed
reports in HTML or Markdown, covering everything from TIFF tags and geokeys to
band statistics and COG validation.
"""

import logging
import os
from pathlib import Path
from datetime import datetime, timezone
from osgeo import gdal
from gttk.utils.geotiff_processor import calculate_compression_efficiency, check_transparency, get_uncompressed_size
from gttk.utils.metadata_extractor import MetadataExtractor
from gttk.utils.report_builders import MetadataReportBuilder
from gttk.utils.report_formatters import HtmlReportFormatter, MarkdownReportFormatter
from gttk.utils.contexts import banner_context, output_format_context, xml_type_context
from gttk.utils.script_arguments import ReadArguments
from gttk.utils.section_registry import get_section_ids_from_args, filter_sections_for_page
from gttk.utils.statistics_calculator import write_pam_xml, build_pam_data_from_stats

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
    Generate report summary section with file information.
    
    Args:
        input_path: Path to GeoTIFF file
        
    Returns:
        Markdown-formatted summary section
    """
    filepath = Path(input_path)
    file_stat = filepath.stat()
    file_size_mb = file_stat.st_size / (1024 * 1024)
    
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
    
    # Get compression info
    uncompressed_size_mb_str = "N/A"
    compression_efficiency_str = "N/A"
    has_mask_str = "N/A"
    
    try:
        gdal.PushErrorHandler('CPLQuietErrorHandler')
        ds = gdal.Open(str(filepath), gdal.GA_ReadOnly)
        gdal.PopErrorHandler()
        
        if ds and ds.RasterCount > 0:
            # Check transparency
            transparency_info = check_transparency(ds)
            if not transparency_info:
                has_mask_str = "No"
            else:
                parts = []
                if transparency_info.get('Alpha'):
                    parts.append("Alpha Band")
                if transparency_info.get('Mask'):
                    parts.append("Internal Mask")
                if transparency_info.get('NoData'):
                    parts.append(f"NoData ({transparency_info['NoData']})")
                has_mask_str = f"Yes – {', '.join(parts)}"
            
            # Get uncompressed size
            uncompressed_size_bytes = get_uncompressed_size(str(filepath))
            if uncompressed_size_bytes > 0:
                uncompressed_size_mb = uncompressed_size_bytes / (1024 * 1024)
                uncompressed_size_mb_str = f"{uncompressed_size_mb:.1f} MB"
                
                efficiency = calculate_compression_efficiency(str(filepath))
                ratio = 100 / (100 - efficiency)
                compression_efficiency_str = f"{efficiency:.2f}% ({ratio:.2f}x)"
        
        ds = None
    except Exception as e:
        logger.debug(f"Error calculating compression info: {e}")
    
    # Build summary
    current_date_str = datetime.now().strftime('%Y-%m-%d')
    lines = [
        "## Report Summary\n",
        f"**Report Date:** {current_date_str}  ",
        f"**File Name:** {filepath.name}  ",
        f"**File Size on Disk:** {file_size_mb:.1f} MB  ",
        f"**Uncompressed Size:** {uncompressed_size_mb_str}  "
    ]
    
    if compression_efficiency_str != "N/A":
        lines.append(f"**Compression Efficiency:** {compression_efficiency_str}  ")
    
    lines.extend([
        f"**Transparency:** {has_mask_str}  ",
        f"**Date Created:** {date_created_str}  ",
        f"**Date Modified:** {date_modified_str}  ",
    ])
    
    return "\n".join(lines)


def read_metadata(args: ReadArguments):
    """
    Generate GeoTIFF metadata report using ReportFormatter.
    
    Args:
        args: Parsed command-line arguments
        
    Returns:
        0 on success, 1 on failure
    """
    logger.info("=== read_metadata.py started ===")
    logger.info(f"Arguments: {args}")
    
    # Validate input file
    try:
        # Set context variables from arguments
        output_format_context.set(args.report_format)
        xml_type_context.set(args.xml_type or 'text')
        banner_context.set(str(args.banner) if args.banner is not None else None)
        
        with MetadataExtractor(str(args.input_path)) as extractor:
            # Get section IDs based on arguments
            section_ids = get_section_ids_from_args(args)
            
            # Filter sections based on page and GeoTIFF status
            section_ids = filter_sections_for_page(
                section_ids,
                page=args.page,
                is_geotiff=extractor.is_geotiff
            )
            
            logger.info(f"Generating report with sections: {section_ids}")
            
            # Build sections using MetadataReportBuilder
            builder = MetadataReportBuilder(extractor, page=args.page, tag_scope=args.tag_scope or 'complete')
            builder.build(section_ids)
            
            # Create appropriate formatter for desired file type
            if args.report_format == 'html':
                formatter = HtmlReportFormatter(filename=extractor.filepath.name)
                formatter.report_title = "Metadata Report"
            else:
                formatter = MarkdownReportFormatter(filename=extractor.filepath.name)
                formatter.report_title = "Metadata Report"
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
            os.startfile(output_path)
            logger.info(f"Opened report: {output_path}")
        except Exception as e:
            logger.warning(f"Could not open report: {e}")
    
    logger.info("Analysis completed successfully")
    return 0