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
GeoTIFF Comparison Tool for GTTK.

This module provides the core logic for the 'compare' command. It generates a
detailed side-by-side comparison report for two GeoTIFF files, highlighting
differences in metadata, compression, and file structure.
"""
import logging
import os
from datetime import datetime
from osgeo import gdal
from pathlib import Path
from typing import Union
from gttk.utils.metadata_extractor import MetadataExtractor
from gttk.utils.report_builders import ComparisonReportBuilder
from gttk.utils.report_formatters import HtmlReportFormatter, MarkdownReportFormatter
from gttk.utils.script_arguments import CompareArguments

# --- Configuration & Setup ---
gdal.SetConfigOption('GDAL_NUM_THREADS', 'ALL_CPUS')
logger = logging.getLogger('compare_compression')

def generate_report_for_datasets(
    base_ds: Union[gdal.Dataset, str, Path],
    comp_ds: Union[gdal.Dataset, str, Path],
    args,
    base_name: str = 'Baseline',
    comp_name: str = 'Comparison',
    report_suffix: str = '_comp'
):
    """
    Generate a comparison report for two GeoTIFF datasets.
    
    Args:
        base_ds: Baseline dataset (gdal.Dataset) OR path to file (str/Path)
        comp_ds: Comparison dataset (gdal.Dataset) OR path to file (str/Path)
        args: Arguments object
        base_name: Label for baseline file
        comp_name: Label for comparison file
        report_suffix: Suffix for report filename
    """
    # Resolve paths depending on input type
    if isinstance(base_ds, (str, Path)):
        base_path_str = str(base_ds)
    else:
        base_path_str = base_ds.GetDescription()

    if isinstance(comp_ds, (str, Path)):
        comp_path_str = str(comp_ds)
    else:
        comp_path_str = comp_ds.GetDescription()

    base_file = os.path.basename(base_path_str)
    comp_file = os.path.basename(comp_path_str)
    summary = _generate_report_summary(base_file, comp_file, base_name, comp_name)

    try:
        with MetadataExtractor(base_path_str) as base_extractor, \
             MetadataExtractor(comp_path_str) as comp_extractor:
            
            builder = ComparisonReportBuilder(
                base_extractor,
                comp_extractor,
                base_name,
                comp_name,
                args
            )
            builder.add_all_sections()

            comp_file = Path(comp_path_str)

            # Generate report based on format, injecting summary above all sections
            report_format = getattr(args, 'report_format', 'html')
            if report_format == 'html':
                formatter = HtmlReportFormatter(filename=comp_file.name)
                formatter.report_title = "Compression Comparison"
                formatter.sections = builder.sections
                formatter.renderer.set_sections([s.id for s in builder.sections])

                # Manually assemble markdown body to insert summary before sections
                parts = [summary]
                for section in formatter.sections:
                    if section.has_data():
                        rendered = formatter._render_section(section)
                        if rendered:
                            parts.append(rendered)
                markdown_body = "\n\n".join(filter(None, parts))

                # Convert to HTML and wrap in template
                html_body = formatter._markdown_to_html(markdown_body)
                final_report_content = formatter._wrap_in_html_template(html_body)
                report_filename = f"{comp_file.stem}{report_suffix}.html"
            else:
                formatter = MarkdownReportFormatter(filename=comp_file.name)
                formatter.report_title = "Compression Comparison"
                formatter.include_title = True
                formatter.sections = builder.sections
                formatter.renderer.set_sections([s.id for s in builder.sections])

                # Assemble markdown with header, then summary, then sections, then footer
                header_md = formatter._render_header()
                parts = [header_md, summary]
                for section in formatter.sections:
                    if section.has_data():
                        rendered = formatter._render_section(section)
                        if rendered:
                            parts.append(rendered)
                parts.append(formatter._render_footer())
                final_report_content = "\n\n".join(filter(None, parts))
                report_filename = f"{comp_file.stem}{report_suffix}.md"

        # Save the report in the same directory as the comparison file
        report_path = comp_file.parent / report_filename

        try:
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(final_report_content)
            logger.info(f"Report saved to: {report_path}")
        except IOError as e:
            logger.error(f"Failed to write report file to disk: {e}")
            return None

        # Open report if requested
        open_report = getattr(args, 'open_report', False)
        arc_mode = getattr(args, 'arc_mode', False)
        if open_report and not arc_mode:
            try:
                os.startfile(report_path)
                logger.info(f"Opening report: {report_path}")
            except Exception as e:
                logger.warning(f"Could not automatically open the report: {e}")
        
        return report_path
        
    except Exception:
        logger.exception("Failed to generate comparison report")
        return None

def _generate_report_summary(base_file: str, comp_file: str, base_name: str, comp_name: str) -> str:
    """
    Generate a simple report summary section for comparison reports.

    Args:
        base_file: Name of the baseline GeoTIFF file
        comp_file: Name of the comparison GeoTIFF file
        base_name: Display label for the baseline file (e.g., 'Input File')
        comp_name: Display label for the comparison file (e.g., 'Output File')

    Returns:
        Markdown-formatted summary section placed above all other sections
    """

    # Build summary
    current_date_str = datetime.now().strftime('%Y-%m-%d')
    lines = [
        "## Report Summary\n",
        f"**Report Date:** {current_date_str}  ",
        f"**{base_name}:** {base_file}  ",
        f"**{comp_name}:** {comp_file}  ",
    ]
    
    return "\n".join(lines)

def compare_compression(args: CompareArguments):
    """
    Compare compression for two GeoTIFF files.
    Returns the path to the generated report, or None on failure.
    """

    assert args.input_path is not None, "Baseline path is required"
    assert args.output_path is not None, "Comparison path is required"

    try:
        logger.info("=== compare_compression started ===")
        logger.info(f"Arguments: {args}")

        base_ds = gdal.Open(str(args.input_path))
        comp_ds = gdal.Open(str(args.output_path))

        if not base_ds or not comp_ds:
            logger.error("Could not open one or both GeoTIFF files. Aborting.")
            logger.error(f"Baseline open: {bool(base_ds)} ({args.input_path})")
            logger.error(f"Comparison open: {bool(comp_ds)} ({args.output_path})")
            return None

        # Get paths and close datasets immediately to avoid file locking during reporting
        base_path = base_ds.GetDescription()
        comp_path = comp_ds.GetDescription()
        logger.info(f"Opened baseline: {base_path}")
        logger.info(f"Opened comparison: {comp_path}")
        
        base_ds = None
        comp_ds = None

        # Use shared report generation function passing PATHS
        report_path = generate_report_for_datasets(
            base_path,
            comp_path,
            args,
            'Baseline',
            'Comparison',
            args.report_suffix or '_comp'
        )
        if not report_path:
            logger.error("Report generation returned None")
        return report_path

    except Exception:
        logger.exception("AN UNEXPECTED ERROR OCCURRED")
        return None