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
Section Registry for GeoTIFF Reports.

Single source of truth for all section configurations. 

Each section is defined once with all its properties:
- id: Unique identifier
- title: Display title for reports
- menu_name: Short name for HTML navigation
- icon: Icon identifier for HTML rendering
- renderer: Method name for section rendering
"""

from typing import Dict, List
from gttk.utils.data_models import SectionConfig


# ============================================================================
# Section Configuration Registry
# ============================================================================

SECTION_CONFIGS: Dict[str, SectionConfig] = {
    # Core GeoTIFF metadata sections
    'tags': SectionConfig(
        id='tags',
        title='TIFF Tags',
        menu_name='Tags',
        icon='tag',
        renderer='render_tags'
    ),
    'geokeys': SectionConfig(
        id='geokeys',
        title='GeoKey Directory',
        menu_name='GeoKeys',
        icon='key',
        renderer='render_geokeys'
    ),
    'georeference': SectionConfig(
        id='georeference',
        title='Spatial Reference',
        menu_name='Reference',
        icon='georeference',
        renderer='render_georeference'
    ),
    'geotransform': SectionConfig(
        id='geotransform',
        title='GeoTransform',
        menu_name='GeoTransform',
        icon='geotransform',
        renderer='render_geotransform'
    ),
    
    # Spatial extent sections
    'bbox': SectionConfig(
        id='bbox',
        title='Bounding Box',
        menu_name='BBox',
        icon='bbox',
        renderer='render_bbox'
    ),
    'geoextent': SectionConfig(
        id='geoextent',
        title='Geographic Extent',
        menu_name='Extent',
        icon='geoextent',
        renderer='render_geoextent'
    ),
    
    # Statistics and visualization sections
    'statistics': SectionConfig(
        id='statistics',
        title='Statistics',
        menu_name='Stats',
        icon='stats',
        renderer='render_statistics_data'
    ),
    'histogram': SectionConfig(
        id='histogram',
        title='Histogram',
        menu_name='Histogram',
        icon='histogram',
        renderer='render_histogram_image'
    ),
    
    # Structure and optimization sections
    'tiling': SectionConfig(
        id='tiling',
        title='Tiling and Overviews',
        menu_name='Tiling',
        icon='tiling',
        renderer='render_tiling_table'
    ),
    'ifd': SectionConfig(
        id='ifd',
        title='Image File Directory (IFD) List',
        menu_name='IFD',
        icon='ifd',
        renderer='render_ifd_table'
    ),
    'cog': SectionConfig(
        id='cog',
        title='COG Validation',
        menu_name='COG',
        icon='checkbox',
        renderer='render_cog_validation'
    ),
    
    # Coordinate system representation sections
    'esri': SectionConfig(
        id='esri',
        title='ESRI Projection Engine (PE) String',
        menu_name='ESRI',
        icon='engine',
        renderer='render_wkt_string'
    ),
    'wkt': SectionConfig(
        id='wkt',
        title='Well Known Text 2 String',
        menu_name='WKT',
        icon='wkt',
        renderer='render_wkt_string'
    ),
    'json': SectionConfig(
        id='json',
        title='PROJJSON String',
        menu_name='JSON',
        icon='json',
        renderer='render_json_string'
    ),
    
    # Metadata sections
    'gdal-metadata': SectionConfig(
        id='gdal-metadata',
        title='GDAL_METADATA (Tag 42112)',
        menu_name='GDAL',
        icon='earth',
        renderer='render_gdal_metadata'
    ),
    'xmp-metadata': SectionConfig(
        id='xmp-metadata',
        title='Extensible Metadata Platform (XMP)',
        menu_name='XMP',
        icon='xmp',
        renderer='render_xmp_metadata'
    ),
    'geo-metadata': SectionConfig(
        id='geo-metadata',
        title='GEO_METADATA (Tag 50909)',
        menu_name='GEO',
        icon='geo',
        renderer='render_geo_metadata'
    ),
    'xml-metadata': SectionConfig(
        id='xml-metadata',
        title='External XML Metadata File',
        menu_name='XML',
        icon='xml',
        renderer='render_xml_metadata'
    ),
    'pam-metadata': SectionConfig(
        id='pam-metadata',
        title='Precision Auxiliary Metadata (PAM)',
        menu_name='PAM',
        icon='pam',
        renderer='render_pam_metadata'
    ),

    # Comparison report sections
    'comparison-ifd': SectionConfig(
        id='comparison-ifd',
        title='IFDs',
        menu_name='IFDs',
        icon='ifd',
        renderer='render_comparison_ifd'
    ),
    'comparison-tiling': SectionConfig(
        id='comparison-tiling',
        title='Tiling and Overviews',
        menu_name='Tiling',
        icon='tiling',
        renderer='render_comparison_tiling'
    ),
    'comparison-statistics': SectionConfig(
        id='comparison-statistics',
        title='Statistics',
        menu_name='Statistics',
        icon='stats',
        renderer='render_comparison_statistics'
    ),
    'comparison-histogram': SectionConfig(
        id='comparison-histogram',
        title='Histograms',
        menu_name='Histograms',
        icon='histogram',
        renderer='render_comparison_histogram'
    ),
    'comparison-cog': SectionConfig(
        id='comparison-cog',
        title='COG Validation',
        menu_name='COG Validation',
        icon='checkbox',
        renderer='render_comparison_cog'
    ),

    # Validation report sections
    'validation-summary': SectionConfig(
        id='validation-summary',
        title='Validation Summary',
        menu_name='Summary',
        icon='validation',
        renderer='render_validation_summary'
    ),
    'validation-tag': SectionConfig(
        id='validation-tag',
        title='TIFF Tags Validation',
        menu_name='Tags',
        icon='tag',
        renderer='render_validation_table'
    ),
    'validation-geokey': SectionConfig(
        id='validation-geokey',
        title='GeoKeys Validation',
        menu_name='GeoKeys',
        icon='key',
        renderer='render_validation_table'
    ),
    'validation-gdal': SectionConfig(
        id='validation-gdal',
        title='GDAL Metadata Validation',
        menu_name='GDAL',
        icon='earth',
        renderer='render_validation_table'
    ),
    'validation-geo': SectionConfig(
        id='validation-geo',
        title='GEO_METADATA Validation',
        menu_name='GEO',
        icon='geo',
        renderer='render_validation_table'
    ),
    'validation-xmp': SectionConfig(
        id='validation-xmp',
        title='XMP Metadata Validation',
        menu_name='XMP',
        icon='xmp',
        renderer='render_validation_table'
    ),
    'validation-xml': SectionConfig(
        id='validation-xml',
        title='External XML Validation',
        menu_name='XML',
        icon='xml',
        renderer='render_validation_table'
    ),
    'validation-projjson': SectionConfig(
        id='validation-projjson',
        title='PROJJSON Validation',
        menu_name='JSON',
        icon='json',
        renderer='render_validation_table'
    ),
}


# ============================================================================
# Section Presets
# ============================================================================

# Producer preset: Comprehensive view with all technical details (less PAM)
PRODUCER_SECTIONS = [
    'tags', 'gdal-metadata', 'xmp-metadata', 'geokeys', 'georeference',
    'geotransform', 'bbox', 'geoextent', 'statistics', 'histogram',
    'esri', 'wkt', 'json', 'tiling', 'ifd', 'cog',
    'geo-metadata', 'xml-metadata'
]

# Analyst preset: User-friendly view focusing on data quality and coverage
ANALYST_SECTIONS = [
    'tags', 'gdal-metadata', 'xmp-metadata', 'georeference', 'bbox', 'geoextent', 
    'statistics', 'histogram', 'tiling', 'cog', 'geo-metadata', 'xml-metadata'
]

# All available *Read Metadata* report sections (excludes comparison sections)
ALL_SECTIONS = [
    'tags', 'gdal-metadata', 'xmp-metadata', 'geokeys', 'georeference',
    'geotransform', 'bbox', 'geoextent', 'statistics', 'histogram',
    'esri', 'wkt', 'json', 'tiling', 'ifd', 'cog',
    'geo-metadata', 'xml-metadata', 'pam-metadata'
]


# ============================================================================
# Helper Functions
# ============================================================================

def get_config(id: str) -> SectionConfig:
    """
    Get configuration for a section.
    
    Args:
        id: Section identifier (e.g., 'tags', 'geokeys')
        
    Returns:
        SectionConfig for the requested section
        
    Raises:
        KeyError: If id is not in SECTION_CONFIGS
        
    Example:
        >>> config = get_config('tags')
        >>> config.title
        'TIFF Tags'
    """
    return SECTION_CONFIGS[id]


def get_icon(id: str) -> str:
    """
    Get icon name for a section.
    
    Args:
        id: Section identifier
        
    Returns:
        Icon name string
        
    Example:
        >>> get_icon('tags')
        'tag'
    """
    return SECTION_CONFIGS[id].icon


def get_renderer(id: str) -> str:
    """
    Get renderer method name for a section.
    
    Args:
        id: Section identifier
        
    Returns:
        Renderer method name as string
        
    Example:
        >>> get_renderer('tags')
        'render_tags'
    """
    return SECTION_CONFIGS[id].renderer


def validate_section_ids(section_ids: List[str]) -> None:
    """
    Validate that all section IDs exist in the registry.
    
    Args:
        section_ids: List of section identifiers to validate
        
    Raises:
        ValueError: If any section ID is invalid, with list of valid IDs
        
    Example:
        >>> validate_section_ids(['tags', 'geokeys', 'statistics'])   # all valid

        >>> validate_section_ids(['tags', 'invalid-section'])  # doctest: +ELLIPSIS
        Traceback (most recent call last):
        ValueError: Invalid section ID(s): invalid-section
        Valid section IDs are:
        bbox, cog, ...
    """
    invalid = [sid for sid in section_ids if sid not in SECTION_CONFIGS]
    if invalid:
        valid_ids = ', '.join(sorted(SECTION_CONFIGS.keys()))
        raise ValueError(
            f"Invalid section ID(s): {', '.join(invalid)}\n"
            f"Valid section IDs are:\n{valid_ids}"
        )


def get_section_ids_from_args(args) -> List[str]:
    """
    Determine which sections to include based on command-line arguments.
    
    This function examines the parsed arguments and returns a list of section
    IDs to include in the report. It handles:
    - Custom section lists (args.sections)
    - Reader type presets (args.reader_type: 'analyst' or 'producer')
    - Default behavior (producer sections)
    
    Args:
        args: Parsed command-line arguments object with attributes:
            - sections: Optional[List[str]] - Custom section list
            - reader_type: Optional[str] - 'analyst' or 'producer'
            
    Returns:
        List of section IDs to include in report
        
    Example:
        >>> import argparse
        >>> args = argparse.Namespace(sections=None, reader_type='analyst')
        >>> get_section_ids_from_args(args)   # doctest: +ELLIPSIS
        ['tags', 'gdal-metadata', 'xmp-metadata', ...]
    """
    # Priority 1: User provided custom sections
    if hasattr(args, 'sections') and args.sections is not None:
        return args.sections
    
    # Priority 2: Reader type preset
    if hasattr(args, 'reader_type'):
        if args.reader_type == 'analyst':
            return ANALYST_SECTIONS.copy()
        elif args.reader_type == 'producer':
            return PRODUCER_SECTIONS.copy()
    
    # Default: producer sections (most comprehensive)
    return PRODUCER_SECTIONS.copy()


def filter_sections_for_page(section_ids: List[str], page: int, is_geotiff: bool) -> List[str]:
    """
    Filter sections based on page number and GeoTIFF status.
    
    Some sections are only available for:
    - Page 0 (main image)
    - GeoTIFF files
    
    This function filters the section list accordingly.
    
    Args:
        section_ids: List of requested section IDs
        page: IFD page index (0 for main image)
        is_geotiff: Whether file is a valid GeoTIFF
        
    Returns:
        Filtered list of section IDs appropriate for this file/page
        
    Example:
        >>> # geokeys and cog are only available on page 0
        >>> filter_sections_for_page(['tags', 'geokeys', 'cog'], page=1, is_geotiff=True)
        ['tags']
    """
    # Sections requiring GeoTIFF (GeoKeyDirectoryTag)
    geotiff_sections = {
        'geokeys', 'georeference', 'geotransform', 'bbox', 'geoextent',
        'esri', 'wkt', 'json', 'tiling', 'cog'
    }
    
    # Sections only available for page 0 (GeoKeyDirectoryTag is only on page 0)
    page_zero_sections = geotiff_sections
    
    filtered = []
    for section_id in section_ids:
        # Skip GeoTIFF sections if not a GeoTIFF
        if not is_geotiff and section_id in geotiff_sections:
            continue
        
        # Skip page-0-only sections if not on page 0
        if page != 0 and section_id in page_zero_sections:
            continue
        
        filtered.append(section_id)
    
    return filtered