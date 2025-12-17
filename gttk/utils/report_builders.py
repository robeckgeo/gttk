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
Report Builders for GTTK Tools.

Builders determine which sections to include in reports for different tools.
They work with ReportGenerators which handle output formatting.

This module implements the Builder pattern to separate report content (what sections
to include) from report format (how to render). This architecture makes it easy to:
- Add new tools without modifying generators
- Add new output formats without modifying builders
- Test section selection independently from rendering

Classes:
    ReportBuilder: Abstract base class for all report builders
    MetadataReportBuilder: Builds sections for read_metadata.py
    ComparisonReportBuilder: Builds sections for compare_compression.py
"""

import os
from abc import ABC
from typing import Any, List, Optional
from gttk.utils.data_models import (
    TiffTag,
    ReportSection,
    StatisticsBand,
    HistogramImage,
    IfdInfo,
    CogValidation,
    TiffTagsData,
    StatisticsData,
    IfdInfoData,
    DifferencesComparison,
    StatisticsComparison,
    HistogramComparison,
    IfdInfoComparison,
    CogValidationComparison,
)
from gttk.utils.geotiff_processor import (
    read_geotiff,
    get_lerc_max_z_error,
    calculate_compression_efficiency,
    determine_decimal_precision,
    estimate_image_quality,
    get_transparency_str,
)
from gttk.utils.histogram_generator import generate_histogram_base64
from gttk.utils.markdown_formatter import format_value
from gttk.utils.metadata_extractor import MetadataExtractor, PREDICTOR_ABBREV_MAP
from gttk.utils.script_arguments import OptimizeArguments
from gttk.utils.section_registry import get_config
from gttk.utils.tiff_tag_parser import TiffTagParser
from gttk.utils.validate_cloud_optimized_geotiff import validate as validate_cog

class ReportBuilder(ABC):
    """
    Base class for building report sections.
    
    Builders determine which sections should be included in a report
    based on available data and tool requirements. They work independently
    of output format (Markdown/HTML).
    
    The Builder pattern separates concerns:
      - Builder: Decides WHAT sections to include
      - Generator: Decides HOW to format the output
      - Renderer: Handles individual section rendering
    
    Attributes:
        sections: List of ReportSection objects to include in report
    
    Example:
        >>> builder = MetadataReportBuilder(context)
        >>> builder.add_standard_sections(['tags', 'statistics'])
        >>> # Pass sections to generator for formatting
        >>> generator = HtmlReportGenerator(context)
        >>> generator.sections = builder.sections
        >>> html = generator.generate()
    """
    
    def __init__(self):
        """Initialize builder with empty sections list."""
        self.sections: List[ReportSection] = []
    
    def add_section(self, section_id: str, data: Any, title_override: Optional[str] = None) -> None:
        """
        Add a section to the report using config from registry.
        
        Only adds the section if data is not None. This allows conditional
        section inclusion based on data availability.
        
        Args:
            section_id: Section identifier (e.g., 'tags', 'geokeys')
            data: Dataclass instance or list of dataclass instances
            title_override: Optional title override for dynamic titles
        """
        if data is not None:
            config = get_config(section_id)
            self.sections.append(ReportSection(
                id=config.id,
                title=title_override or config.title,
                menu_name=config.menu_name,
                data=data,
                enabled=True,
                icon=config.icon
            ))
    
    @staticmethod
    def _build_statistics_table(stats: List[StatisticsBand], title: str = "Statistics", footnote: Optional[str] = None) -> Optional[StatisticsData]:
        """
        Build statistics presentation data from domain objects.
        
        Shared helper method used by both MetadataReportBuilder and ComparisonReportBuilder
        to transform StatisticsBand domain objects into StatisticsData presentation objects.
        
        Args:
            stats: List of StatisticsBand domain objects
            title: Table title
            footnote: Optional footnote text
            
        Returns:
            StatisticsData presentation object or None if no stats
        """
        if not stats:
            return None
        
        # Use class method for field definitions
        display_fields = StatisticsBand.get_display_fields()
        
        # Build headers
        band_names = [s.band_name for s in stats]
        headers = ["Statistic"] + band_names
        
        # Check which conditional fields are present
        has_mask = any(band.mask_count for band in stats)
        has_alpha = any(band.alpha_0_count for band in stats)
        has_nodata = any(band.nodata_count for band in stats)
        
        present_conditionals = set()
        if has_mask:
            present_conditionals.add('mask_count')
        if has_alpha:
            present_conditionals.add('alpha_0_count')
        if has_nodata:
            present_conditionals.add('nodata_count')
        
        # Build data rows
        data = []
        for display_name, field_name, always_show in display_fields:
            if not always_show and field_name not in present_conditionals:
                continue
            
            row = {"Statistic": display_name}
            for band in stats:
                val = getattr(band, field_name, None)
                row[band.band_name] = format_value(val) if val is not None else ""
            data.append(row)
        
        return StatisticsData(
            title=title,
            headers=headers,
            data=data,
            footnote=footnote
        )


class MetadataReportBuilder(ReportBuilder):
    """
    Builds sections for metadata reports (read_metadata.py tool).
    
    Fetches and assembles standard GeoTIFF metadata sections based on
    user-selected section IDs. This builder is used for single-file
    metadata extraction and reporting.
    
    The builder uses SECTION_CONFIGS to look up fetchers for each section,
    calls the fetcher to get data, and adds the section if data is available.
    
    Example:
        >>> context = build_context_from_file('example.tif')
        >>> builder = MetadataReportBuilder(context)
        >>> builder.add_standard_sections(['tags', 'statistics', 'cog'])
        >>> # builder.sections now contains these sections with their data
        >>> print(len(builder.sections))  # 3 (assuming all sections had data)
    """
    
    def __init__(self, extractor: MetadataExtractor, page: int = 0, tag_scope: str = 'complete'):
        """
        Initialize metadata report builder.
        
        Args:
            extractor: MetadataExtractor instance for the file.
            page: The IFD page to report on.
            tag_scope: The scope of tags to include ('complete' or 'compact').
        """
        super().__init__()
        self.extractor = extractor
        self.page = page
        self.tag_scope = tag_scope
        self._cached_statistics = None  # Cache to avoid re-extracting
    
    def _build_statistics_data(self, stats: List[StatisticsBand]) -> Optional[StatisticsData]:
        """Transform domain objects to presentation format."""
        if not stats:
            return None
        
        # Use class method for field definitions
        display_fields = StatisticsBand.get_display_fields()
        
        # Build headers
        band_names = [s.band_name for s in stats]
        headers = ["Statistic"] + band_names
        
        # Check which conditional fields are present
        has_nodata = any(band.nodata_count for band in stats)
        has_mask = any(band.mask_count for band in stats)
        has_alpha = any(band.alpha_0_count for band in stats)
        
        present_conditionals = set()
        if has_mask:
            present_conditionals.add('mask_count')
        if has_alpha:
            present_conditionals.add('alpha_0_count')
        if has_nodata:
            present_conditionals.add('nodata_count')
        
        data = []
        for display_name, field_name, always_show in display_fields:
            if not always_show and field_name not in present_conditionals:
                continue
            
            row = {"Statistic": display_name}
            for band in stats:
                val = getattr(band, field_name, None)
                row[band.band_name] = format_value(val) if val is not None else ""
            data.append(row)
        
        return StatisticsData(title="Statistics", headers=headers, data=data)
    
    def _build_ifd_data(self, ifds: List[IfdInfo]) -> Optional[IfdInfoData]:
        """Transform domain objects to presentation format."""
        if not ifds:
            return None

        # Determine which columns to include based on data
        has_decimals = any(ifd.decimals for ifd in ifds)
        has_photometric = any(ifd.photometric for ifd in ifds)
        has_predictor = any(ifd.predictor for ifd in ifds)
        has_lerc = any(ifd.lerc_max_z_error for ifd in ifds)

        # Build headers
        headers = ["IFD", "Description", "Dimensions", "Block Size", "Type", "Bands", "Bits", ]
        if has_decimals:
            headers.append("Decimals")
        if has_photometric:
            headers.append("Photometric")
        headers.append("Algorithm")
        if has_predictor:
            headers.append("Predictor")
        if has_lerc:
            headers.append("Max Z Error")
        headers.append("Space Savings")
        headers.append("Ratio")

        # Build rows with lowercase keys matching IfdInfo attributes
        rows = []
        for ifd in ifds:
            row = {
                "ifd": ifd.ifd,
                "ifd_type": ifd.ifd_type,
                "dimensions": ifd.dimensions,
                "block_size": ifd.block_size,
                "data_type": ifd.data_type,
                "bands": ifd.bands,
                "bits_per_sample": ifd.bits_per_sample,

            }
            if has_decimals:
                row["decimals"] = ifd.decimals or ""
            if has_photometric:
                row["photometric"] = ifd.photometric or ""
            row["compression_algorithm"] = ifd.compression_algorithm or ""
            if has_predictor:
                row["predictor"] = ifd.predictor or ""
            if has_lerc:
                row["lerc_max_z_error"] = ifd.lerc_max_z_error or ""
            row["space_saving"] = ifd.space_saving or ""
            row["ratio"] = ifd.ratio

            rows.append(row)

        return IfdInfoData(
            headers=headers,
            rows=rows,
            title="Image File Directory (IFD) List"
        )
    
    def build(self, section_ids: List[str]) -> None:
        """
        Build report sections dynamically based on section IDs.
        
        Args:
            section_ids: List of section IDs to include in the report.
        """
        # The section_map routes section IDs to their corresponding adder methods.
        section_map = {
            'tags': self._add_tags_section,
            'gdal-metadata': self._add_gdal_metadata_section,
            'xmp-metadata': self._add_xmp_metadata_section,
            'geokeys': self._add_geokeys_section,
            'georeference': self._add_georeference_section,
            'bbox': self._add_bbox_section,
            'geoextent': self._add_geoextent_section,
            'geotransform': self._add_geotransform_section,
            'statistics': self._add_statistics_section,
            'histogram': self._add_histogram_section,
            'tiling': self._add_tiling_section,
            'ifd': self._add_ifd_section,
            'esri': self._add_esri_pe_section,
            'wkt': self._add_wkt_section,
            'json': self._add_projjson_section,
            'cog': self._add_cog_section,
            'geo-metadata': self._add_geo_metadata_section,
            'xml-metadata': self._add_xml_metadata_section,
            'pam-metadata': self._add_pam_metadata_section,
        }

        for section_id in section_ids:
            adder_method = section_map.get(section_id)
            if adder_method and callable(adder_method):
                adder_method()

    def _add_tags_section(self):
        tags = self.extractor.extract_tags(self.page, self.tag_scope)
        if tags:
            # Simplified title and footer logic
            ifd_type = "Main Image" if self.page == 0 else "Overview" # Basic logic
            base_title = f"TIFF Tags (IFD {self.page} – {ifd_type})"
            title = f"Compact* {base_title}" if self.tag_scope == 'compact' else f"Complete* {base_title}"
            footer = "\\* *Some tags are excluded in compact view.*" if self.tag_scope == 'compact' else "\\* *All TIFF tags are included in the report.*"
            
            presentation_data = TiffTagsData(tags=tags, title=title, footer=footer)
            self.add_section('tags', presentation_data, title)

    def _add_gdal_metadata_section(self):
        gdal_metadata = self.extractor.extract_gdal_metadata()
        self.add_section('gdal-metadata', gdal_metadata)

    def _add_xmp_metadata_section(self):
        xmp_metadata = self.extractor.extract_xmp_metadata()
        self.add_section('xmp-metadata', xmp_metadata)

    def _add_geokeys_section(self):
        geokeys = self.extractor.extract_geokeys()
        gtiff_version = self.extractor.extract_geotiff_version()
        title = f"GeoKey Directory (Version {gtiff_version})" if gtiff_version else "GeoKey Directory"
        self.add_section('geokeys', geokeys, title)

    def _add_georeference_section(self):
        georef = self.extractor.extract_georeference()
        self.add_section('georeference', georef)

    def _add_geotransform_section(self):
        geotransform = self.extractor.extract_geotransform()
        self.add_section('geotransform', geotransform)

    def _add_bbox_section(self):
        bbox = self.extractor.extract_bounding_box()
        georef = self.extractor.extract_georeference()
        
        # Determine CRS name with proper fallback chain
        if georef:
            srs = (georef.compound_cs or
                   georef.projected_cs or
                   georef.geographic_cs or
                   "Native Coordinate System")
        else:
            srs = "Native Coordinate System"
        
        title = f"Bounding Box – {srs}"
        self.add_section('bbox', bbox, title)

    def _add_geoextent_section(self):
        geoextents = self.extractor.extract_geo_extents()
        self.add_section('geoextent', geoextents)

    def _add_statistics_section(self):
        stats = self.extractor.extract_statistics(self.page)
        if stats:
            self._cached_statistics = stats  # Cache for histogram use
            presentation_data = self._build_statistics_data(stats)
            self.add_section('statistics', presentation_data)

    def _add_histogram_section(self):
        """Add histogram section using pre-computed histogram bins and counts."""
        # Use cached statistics if available, otherwise extract
        stats = self._cached_statistics if self._cached_statistics else self.extractor.extract_statistics(self.page)
        
        if stats:
            # Filter bands that have histogram data
            bands_with_histograms = [
                band for band in stats
                if band.histogram_counts and band.histogram_bins
            ]
            
            if not bands_with_histograms:
                return
            
            # Pass pre-computed histogram data to generator
            stats_dict = {
                "band_histogram_counts": [band.histogram_counts for band in bands_with_histograms],
                "band_histogram_bins": [band.histogram_bins for band in bands_with_histograms],
                "band_names": [band.band_name for band in bands_with_histograms],
            }
            
            # Generate histogram
            hist_base64 = generate_histogram_base64(stats_dict, self.extractor.filepath.name)
            
            if hist_base64:
                hist_data = HistogramImage(
                    base64_image=hist_base64,
                    bands=[b.band_name for b in bands_with_histograms],
                    title='Histogram'
                )
                self.add_section('histogram', hist_data)

    def _add_esri_pe_section(self):
        wkt = self.extractor.extract_esri_pe_string()
        self.add_section('esri', wkt)

    def _add_wkt_section(self):
        wkt = self.extractor.extract_wkt_string()
        self.add_section('wkt', wkt)

    def _add_projjson_section(self):
        projjson = self.extractor.extract_projjson_string()
        self.add_section('json', projjson)

    def _add_ifd_section(self):
        ifds = self.extractor.extract_ifd_info()
        if ifds:
            presentation_data = self._build_ifd_data(ifds)
            self.add_section('ifd', presentation_data)

    def _add_tiling_section(self):
        tiling = self.extractor.extract_tile_info()
        self.add_section('tiling', tiling)

    def _add_cog_section(self):
        cog = self.extractor.validate_cog()
        self.add_section('cog', cog)

    def _add_geo_metadata_section(self):
        geo_metadata = self.extractor.extract_geo_metadata()
        self.add_section('geo-metadata', geo_metadata)

    def _add_xml_metadata_section(self):
        xml_metadata = self.extractor.extract_xml_metadata()
        self.add_section('xml-metadata', xml_metadata)

    def _add_pam_metadata_section(self):
        pam_metadata = self.extractor.extract_pam_metadata()
        self.add_section('pam-metadata', pam_metadata)


class ComparisonReportBuilder(ReportBuilder):
    """
    Builds sections for comparison reports (compare_compression.py tool).
    
    Fetches and assembles compression comparison sections, including
    differences table, IFDs, statistics, histograms, and COG validation
    for both baseline and comparison files.
    
    This builder creates paired sections (one for each file) for most
    section types, making it easy to compare side-by-side.
    
    Example:
        >>> builder = ComparisonReportBuilder(base_ds, comp_ds)
        >>> builder.add_differences_section(differences_data)
        >>> builder.add_ifd_sections()
        >>> builder.add_statistics_sections()
        >>> # builder.sections now contains comparison sections
        >>> for section in builder.sections:
        ...     print(f"{section.id}: {section.title}")
        differences: Differences
        ifd-input file: Input File IFDs
        ifd-output file: Output File IFDs
        ...
    """
    
    def __init__(self, base_extractor: MetadataExtractor, comp_extractor: MetadataExtractor,
                 base_name: str = 'Baseline', comp_name: str = 'Comparison', args: Optional[Any] = None):
        """
        Initialize comparison report builder.
        
        Args:
            base_extractor: MetadataExtractor for the baseline file
            comp_extractor: MetadataExtractor for the comparison file
            base_name: Label for baseline file (default: 'Baseline')
            comp_name: Label for comparison file (default: 'Comparison')
            args: Command-line arguments for the tool.
        """
        super().__init__()
        self.base_extractor = base_extractor
        self.comp_extractor = comp_extractor
        self.base_name = base_name
        self.comp_name = comp_name
        self.args = args
        
        # Cached statistics to avoid recomputation across sections
        self._base_stats_bands = None
        self._comp_stats_bands = None
        self._base_stats_data = None
        self._comp_stats_data = None

    def add_all_sections(self, differences: Optional[DifferencesComparison] = None) -> None:
        """
        Builds all sections for the comparison report.

        Args:
            differences: Optional precomputed DifferencesComparison. If provided,
                        it will be used directly; otherwise the builder will
                        compute the differences internally.
        """
        if differences is not None:
            # Backward-compatible path if caller supplies precomputed differences
            self.add_section('differences', differences)
        else:
            # Standard path: compute differences from datasets
            self.add_differences_section()

        # Remaining comparison sections
        self.add_ifd_sections()
        self.add_statistics_sections()
        self.add_histogram_sections()
        self.add_cog_sections()

    def add_differences_section(self) -> None:
        """Build and add the main differences table section."""
        base_ds = self.base_extractor.gdal_ds
        comp_ds = self.comp_extractor.gdal_ds

        if not base_ds or not comp_ds:
            return

        base_info = read_geotiff(base_ds)
        comp_info = read_geotiff(comp_ds)

        base_path = base_ds.GetDescription()
        comp_path = comp_ds.GetDescription()
        base_size = os.path.getsize(base_path)
        comp_size = os.path.getsize(comp_path)
        base_size_mb = base_size / (1024 * 1024)
        comp_size_mb = comp_size / (1024 * 1024)

        base_efficiency = calculate_compression_efficiency(base_path, tiff=self.base_extractor.tiff)
        comp_efficiency = calculate_compression_efficiency(comp_path, tiff=self.comp_extractor.tiff)

        base_compression = base_ds.GetMetadataItem('COMPRESSION', 'IMAGE_STRUCTURE') or 'NONE'
        comp_compression = comp_ds.GetMetadataItem('COMPRESSION', 'IMAGE_STRUCTURE') or 'NONE'

        base_decimals = determine_decimal_precision(base_ds)
        comp_decimals = determine_decimal_precision(comp_ds)

        _, in_err, _ = validate_cog(base_ds, full_check=True)
        is_base_cog_str = "Yes" if not in_err else "No"

        out_warn, out_err, _ = validate_cog(comp_ds, full_check=True)
        is_comparison_cog_str = "Yes" if not out_err else "No"

        cog_requested = getattr(self.args, 'cog', False)
        cog_creation_failed = False
        if cog_requested and out_err:
            is_comparison_cog_str += "*"
            cog_creation_failed = True

        headers = ['File', 'Type', 'COG', 'Algorithm']
        base_row = [self.base_name, base_info.data_type, is_base_cog_str, base_compression]
        comp_row = [self.comp_name, comp_info.data_type, is_comparison_cog_str, comp_compression]

        headers.extend(['Bands', 'Transparency'])
        base_row.extend([base_info.bands, get_transparency_str(base_info)])
        comp_row.extend([comp_info.bands, get_transparency_str(comp_info)])
        
        if any(c in ['JPEG', 'YCbCr JPEG', 'JXL'] for c in [comp_compression, base_compression]):
            headers.append('Quality')
            
            # --- BASELINE QUALITY LOGIC ---
            # Existing file, so we must estimate if JXL, or return N/A if JPEG
            base_quality = estimate_image_quality(base_ds, base_compression)
            base_row.append(base_quality)

            # --- COMPARISON QUALITY LOGIC ---
            # If we just created this file (optimize mode), use the known args.quality
            if isinstance(self.args, OptimizeArguments) and self.args.quality is not None and comp_compression in ['JPEG', 'JXL']:
                comp_quality = self.args.quality
            else:
                # Otherwise (compare mode), estimate it from the file
                comp_quality = estimate_image_quality(comp_ds, comp_compression)
            
            comp_row.append(comp_quality)

        if 'Float' in str(comp_info.data_type):
            headers.append('Decimals')
            
            # Helper to format decimals (int or list of ints)
            def fmt_decimals(val):
                if isinstance(val, list):
                    return str(val)
                return str(val)
                
            base_row.append(fmt_decimals(base_decimals))
            comp_row.append(fmt_decimals(comp_decimals))

        if any(c in ['LZW', 'DEFLATE', 'ZSTD'] for c in [base_compression, comp_compression]):
            headers.append('Predictor')
            with TiffTagParser(base_path, tiff_file=self.base_extractor.tiff) as base_parser:
                base_tags = base_parser.get_tags()
            with TiffTagParser(comp_path, tiff_file=self.comp_extractor.tiff) as comp_parser:
                comp_tags = comp_parser.get_tags()

            def get_predictor_val(tags: List[TiffTag]) -> int:
                for tag in tags:
                    if tag.code == 317:
                        return tag.value if isinstance(tag.value, int) else 1
                return 1

            base_pred_val = get_predictor_val(base_tags)
            if base_compression in ['LZW', 'DEFLATE', 'ZSTD']:
                base_predictor = PREDICTOR_ABBREV_MAP.get(base_pred_val, "")
            else:
                base_predictor = ""
            
            comp_pred_val = get_predictor_val(comp_tags)
            if comp_compression in ['LZW', 'DEFLATE', 'ZSTD']:
                comp_predictor = PREDICTOR_ABBREV_MAP.get(comp_pred_val, "")
            else:
                comp_predictor = ""
                
            base_row.append(base_predictor)
            comp_row.append(comp_predictor)

        if 'LERC' in [comp_compression, base_compression]:
            headers.append('Max Z Error')
            base_row.append(get_lerc_max_z_error(base_ds))
            comp_row.append(get_lerc_max_z_error(comp_ds))

        headers.extend(['Size (MB)', 'Space Savings', 'Ratio'])
        base_ratio = 100 / (100 - base_efficiency)
        comp_ratio = 100 / (100 - comp_efficiency)
        base_row.extend([f"{base_size_mb:,.2f}", f"{base_efficiency:.2f}%", f"{base_ratio:.2f}x"])
        comp_row.extend([f"{comp_size_mb:,.2f}", f"{comp_efficiency:.2f}%", f"{comp_ratio:.2f}x"])

        size_difference_mb = comp_size_mb - base_size_mb
        size_difference_pct = (size_difference_mb / base_size_mb * 100) if base_size_mb > 0 else 0
        efficiency_difference = comp_efficiency - base_efficiency

        differences_data = DifferencesComparison(
            headers=headers,
            base_row=base_row,
            comp_row=comp_row,
            base_name=self.base_name,
            comp_name=self.comp_name,
            base_size_mb=base_size_mb,
            comp_size_mb=comp_size_mb,
            size_difference_mb=size_difference_mb,
            size_difference_pct=size_difference_pct,
            efficiency_difference=efficiency_difference,
            cog_creation_failed=cog_creation_failed,
            cog_errors=out_err if cog_creation_failed else None,
            cog_warnings=out_warn if cog_creation_failed else None
        )
        self.add_section('differences', differences_data)
    
    def _ensure_stats_cached(self) -> None:
        """
        Compute statistics once per file and cache both the raw band stats and
        their presentation form for reuse across sections.
        """
        if getattr(self, "_base_stats_bands", None) is None:
            self._base_stats_bands = self.base_extractor.extract_statistics()
        if getattr(self, "_comp_stats_bands", None) is None:
            self._comp_stats_bands = self.comp_extractor.extract_statistics()

    def add_ifd_sections(self) -> None:
        """
        Add grouped IFD (Image File Directory) section for both files.
        
        Creates a single section with IFD tables for both baseline and
        comparison files, grouped under h4 subheaders.
        """
        # Get IFD domain objects for both files
        base_ifds = self.base_extractor.extract_ifd_info()
        comp_ifds = self.comp_extractor.extract_ifd_info()
        
        # Create grouped data if at least one file has IFD data
        if base_ifds or comp_ifds:
            files = []
            
            # Transform base IFDs to presentation format
            if base_ifds:
                base_ifd_data = self._build_ifd_data_for_file(base_ifds)
                if base_ifd_data:
                    files.append((self.base_name, base_ifd_data))
            
            # Transform comparison IFDs to presentation format
            if comp_ifds:
                comp_ifd_data = self._build_ifd_data_for_file(comp_ifds)
                if comp_ifd_data:
                    files.append((self.comp_name, comp_ifd_data))
            
            if files:
                grouped_data = IfdInfoComparison(
                    title='IFDs',
                    files=files
                )
                self.add_section('comparison-ifd', grouped_data)
    
    def _build_ifd_data_for_file(self, ifds: List[IfdInfo]) -> Optional[IfdInfoData]:
        """Transform IFD domain objects to presentation format for a single file."""
        if not ifds:
            return None
        
        # Determine which columns to include based on data
        has_photometric = any(ifd.photometric for ifd in ifds)
        has_predictor = any(ifd.predictor for ifd in ifds)
        has_lerc = any(ifd.lerc_max_z_error for ifd in ifds)
        has_decimals = any(ifd.decimals for ifd in ifds)
        
        # Build headers
        headers = ["IFD", "Description", "Dimensions", "Block Size", "Type", "Bands", "Bits"]
        if has_decimals:
            headers.append("Decimals")
        if has_photometric:
            headers.append("Photometric")
        headers.append("Algorithm")
        if has_predictor:
            headers.append("Predictor")
        if has_lerc:
            headers.append("Max Z Error")
        headers.append("Space Savings")
        headers.append("Ratio")
        
        # Build rows with header names as keys for table rendering
        rows = []
        for ifd in ifds:
            row = {
                "IFD": ifd.ifd,
                "Description": ifd.ifd_type,
                "Dimensions": ifd.dimensions,
                "Block Size": ifd.block_size,
                "Type": ifd.data_type,
                "Bands": ifd.bands,
                "Bits": ifd.bits_per_sample,
            }
            if has_decimals:
                row["Decimals"] = ifd.decimals or ""
            if has_photometric:
                row["Photometric"] = ifd.photometric or ""
            row["Algorithm"] = ifd.compression_algorithm or ""
            if has_predictor:
                row["Predictor"] = ifd.predictor or ""
            if has_lerc:
                row["Max Z Error"] = ifd.lerc_max_z_error or ""
            row["Space Savings"] = ifd.space_saving or ""
            row["Ratio"] = ifd.ratio
            
            rows.append(row)
        
        return IfdInfoData(
            headers=headers,
            rows=rows,
            title="Image File Directory (IFD) List"
        )
    
    def add_statistics_sections(self) -> None:
        """
        Add grouped statistics section for both files.

        Computes statistics once per file and caches both the raw band stats
        and the formatted StatisticsData for reuse by other sections.
        """
        # Ensure cached statistics are available
        self._ensure_stats_cached()

        base_stats_bands = self._base_stats_bands or []
        comp_stats_bands = self._comp_stats_bands or []

        # Build presentation data (and cache it) only once
        self._base_stats_data = self._build_statistics_table(base_stats_bands) if base_stats_bands else None
        self._comp_stats_data = self._build_statistics_table(comp_stats_bands) if comp_stats_bands else None

        base_stats = self._base_stats_data
        comp_stats = self._comp_stats_data

        # Create grouped data if at least one file has statistics
        if base_stats or comp_stats:
            files = []
            if base_stats:
                files.append((self.base_name, base_stats))
            if comp_stats:
                files.append((self.comp_name, comp_stats))

            grouped_data = StatisticsComparison(
                title='Statistics',
                files=files
            )
            self.add_section('comparison-statistics', grouped_data)

    def add_histogram_sections(self) -> None:
        """
        Add grouped histogram section for both files using pre-computed histogram data.

        Reuses the cached per-file statistics to avoid recomputation.
        """
        files = []

        # Ensure cached statistics are available
        self._ensure_stats_cached()

        # Add baseline histogram if available
        base_stats_bands = self._base_stats_bands or []
        if base_stats_bands:
            # Filter bands with histogram data
            bands_with_histograms = [
                band for band in base_stats_bands
                if band.histogram_counts and band.histogram_bins
            ]
            
            if bands_with_histograms:
                stats_dict = {
                    "band_histogram_counts": [band.histogram_counts for band in bands_with_histograms],
                    "band_histogram_bins": [band.histogram_bins for band in bands_with_histograms],
                    "band_names": [band.band_name for band in bands_with_histograms],
                }
                base_hist = generate_histogram_base64(stats_dict, self.base_extractor.filepath.name)
                if base_hist:
                    hist_data = HistogramImage(
                        base64_image=base_hist,
                        bands=[b.band_name for b in bands_with_histograms],
                        title=f'{self.base_name} Histogram'
                    )
                    files.append((self.base_name, hist_data))

        # Add comparison histogram if available
        comp_stats_bands = self._comp_stats_bands or []
        if comp_stats_bands:
            # Filter bands with histogram data
            bands_with_histograms = [
                band for band in comp_stats_bands
                if band.histogram_counts and band.histogram_bins
            ]
            
            if bands_with_histograms:
                stats_dict = {
                    "band_histogram_counts": [band.histogram_counts for band in bands_with_histograms],
                    "band_histogram_bins": [band.histogram_bins for band in bands_with_histograms],
                    "band_names": [band.band_name for band in bands_with_histograms],
                }
                comp_hist = generate_histogram_base64(stats_dict, self.comp_extractor.filepath.name)
                if comp_hist:
                    hist_data = HistogramImage(
                        base64_image=comp_hist,
                        bands=[b.band_name for b in bands_with_histograms],
                        title=f'{self.comp_name} Histogram'
                    )
                    files.append((self.comp_name, hist_data))

        # Create grouped data if at least one histogram was generated
        if files:
            grouped_data = HistogramComparison(
                title='Histograms',
                files=files
            )
            self.add_section('comparison-histogram', grouped_data)
    
    def add_cog_sections(self) -> None:
        """
        Add grouped COG validation section for both files.
        
        Creates a single section with COG validation results for both baseline
        and comparison files, grouped under h4 subheaders.
        """
        # Validate both files
        base_cog = self.base_extractor.validate_cog()
        comp_cog = self.comp_extractor.validate_cog()

        # Ensure we have objects to work with
        if not base_cog:
            base_cog = CogValidation(errors=["Could not analyze baseline file."])
        if not comp_cog:
            comp_cog = CogValidation(errors=["Could not analyze comparison file."])

        # Wrap them in CogValidationComparison
        grouped_data = CogValidationComparison(
            title='COG Validation',
            files=[
                (self.base_name, base_cog),
                (self.comp_name, comp_cog)
            ]
        )
        
        self.add_section('comparison-cog', grouped_data)