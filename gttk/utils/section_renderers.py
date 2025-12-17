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
Renderers for GeoTIFF Metadata Reports.

This module provides abstract base class and concrete implementations for rendering
GeoTIFF metadata in different formats (currently just Markdown and HTML).

The HTML report uses mistune to generate HTML from the MarkdownRenderer output.
Future renderers may be added, such as JSON for the GUI or a REST API.

Classes:
    Renderer: Abstract base class for all renderers
    MarkdownRenderer: Renders metadata sections as Markdown
"""
import json
import re
from abc import ABC, abstractmethod
from typing import List, Optional
from gttk.utils.colors import ColorManager
from gttk.utils.markdown_formatter import format_value, format_citation, xml_to_markdown
from gttk.utils.xml_formatter import pretty_print_xml
from gttk.utils.data_models import (
    GeoKey, GeoReference, GeoExtents, GeoTransform,
    BoundingBox, StatisticsBand, HistogramImage, TileInfo, IfdInfo,
    WktString, JsonString, CogValidation, XmlMetadata,
    TiffTagsData, StatisticsData, IfdInfoData,
    DifferencesComparison, IfdInfoComparison, StatisticsComparison,
    HistogramComparison, CogValidationComparison
)

XMP_TAG = 700
GEO_ASCII_PARAMS_TAG = 34737
GDAL_METADATA_TAG = 42112
GEO_METADATA_TAG = 50909

XML_TAGS = {
    XMP_TAG,
    GDAL_METADATA_TAG,
    GEO_METADATA_TAG
}
 
class Renderer(ABC):
    """
    Abstract base class for all report renderers.
    
    Renderers take structured dataclass objects and convert them into
    formatted strings suitable for display or saving to files.
    """
 
    def __init__(self):
        """
        Initialize the Renderer.
        """
        self.requested_sections: set[str] = set()
        self.enable_html_styling: bool = False
        self.sample_color_map: Optional[dict] = None
 
    def set_sections(self, sections: Optional[list] = None) -> None:
        """
        Provide the renderer with the list/set of section identifiers that
        will be included in the report. This is intended to be called once by
        the report builder prior to rendering.
 
        Args:
            sections: Iterable of section id strings (e.g. 'xmp-metadata')
        """
        if sections is None:
            self.requested_sections = set()
        else:
            try:
                self.requested_sections = set(sections)
            except Exception:
                self.requested_sections = set()

    def has_section(self, section_id: str) -> bool:
        """Return True if the given section id is in the requested sections."""
        return section_id in getattr(self, 'requested_sections', set())

    @abstractmethod
    def render_tags(self, data: TiffTagsData, title: Optional[str] = None) -> str:
        """
        Render TIFF tags section.
        
        Args:
            data: TiffTagsData object with tags, title, and optional footer
            title: Optional title override (uses data.title if not provided)
            
        Returns:
            Formatted string representation
        """
        pass
    
    @abstractmethod
    def render_geokeys(self, geokeys: List[GeoKey], title: str = "GeoKeys Directory") -> str:
        """
        Render GeoKeys section.
        
        Args:
            geokeys: List of GeoKey objects
            title: Section title
            
        Returns:
            Formatted string representation
        """
        pass
    
    @abstractmethod
    def render_statistics(self, stats: List[StatisticsBand], title: str = "Statistics", footer: Optional[str] = None) -> str:
        """
        Render statistics section.
        
        Args:
            stats: List of StatisticsBand objects
            title: Section title
            footer: Optional footer text
            
        Returns:
            Formatted string representation
        """
        pass
    
    @abstractmethod
    def render_georeference(self, georef: GeoReference, title: str = "Georeference") -> str:
        """
        Render georeference information.
        
        Args:
            georef: GeoReference object
            title: Section title
            
        Returns:
            Formatted string representation
        """
        pass
    
    @abstractmethod
    def render_geoextent(self, extents: GeoExtents, title: str = "Geographic Extent") -> str:
        """
        Render geographic extents.
        
        Args:
            extents: GeoExtents object
            title: Section title
            
        Returns:
            Formatted string representation
        """
        pass
    
    @abstractmethod
    def render_geotransform(self, gt: GeoTransform, title: str = "GeoTransform") -> str:
        """
        Render geotransform information.
        
        Args:
            gt: GeoTransform object
            title: Section title
            
        Returns:
            Formatted string representation
        """
        pass
    
    @abstractmethod
    def render_bbox(self, bbox: BoundingBox, title: str = "Bounding Box") -> str:
        """
        Render bounding box information.
        
        Args:
            bbox: BoundingBox object
            title: Section title
            
        Returns:
            Formatted string representation
        """
        pass

    @abstractmethod
    def render_tiling_table(self, tiles: List[TileInfo], title: str = "Tiling and Overviews") -> str:
        """
        Render tiling and overview information.
        
        Args:
            tiles: List of TileInfo objects
            title: Section title
            
        Returns:
            Formatted string representation
        """
        pass
    
    @abstractmethod
    def render_ifd(self, ifds: List[IfdInfo], title: str = "Image File Directory (IFD) List") -> str:
        """
        Render IFD information.
        
        Args:
            ifds: List of IfdInfo objects
            title: Section title
            
        Returns:
            Formatted string representation
        """
        pass
    
    @abstractmethod
    def render_wkt_string(self, data: WktString, title: Optional[str] = None) -> str:
        """
        Render WKT2 or ESRI PE String section.
        
        Args:
            data: WktString object containing WKT or PE String
            title: Optional override for section title
            
        Returns:
            Formatted string representation
        """
        pass
    
    @abstractmethod
    def render_json_string(self, data: JsonString, title: Optional[str] = None) -> str:
        """
        Render PROJJSON section.
        
        Args:
            data: JsonString object containing PROJJSON
            title: Optional override for section title
            
        Returns:
            Formatted string representation
        """
        pass

    @abstractmethod
    def render_cog_validation(self, cog: CogValidation, title: str = "COG Compliance") -> str:
        """
        Render COG validation results.
        
        Args:
            cog: CogValidation object
            title: Section title
            
        Returns:
            Formatted string representation
        """
        pass

    
    @abstractmethod
    def render_gdal_metadata(self, data: XmlMetadata, title: Optional[str] = None) -> str:
        """
        Render GDAL_METADATA TIFF Tag (#42112) section.
        
        Args:
            data: XmlMetadata object containing GDAL_METADATA content
            title: Optional override for section title
            
        Returns:
            Formatted string representation
        """
        pass

    
    @abstractmethod
    def render_geo_metadata(self, data: XmlMetadata, title: Optional[str] = None) -> str:
        """
        Render GEO_METADATA TIFF Tag (#50909) section.
        
        Args:
            data: XmlMetadata object containing GEO_METADATA content
            title: Optional override for section title
            
        Returns:
            Formatted string representation
        """
        pass

    
    @abstractmethod
    def render_xmp_metadata(self, data: XmlMetadata, title: Optional[str] = None) -> str:
        """
        Render Extensible Metadata Platform (XMP) TIFF Tag (#700) section.
        
        Args:
            data: XmlMetadata object containing XMLPacket XMP content
            title: Optional override for section title
            
        Returns:
            Formatted string representation
        """
        pass

    
    @abstractmethod
    def render_xml_metadata(self, data: XmlMetadata, title: Optional[str] = None) -> str:
        """
        Render external XML metadata section.
        
        Args:
            data: XmlMetadata object containing XML content
            title: Optional override for section title
            
        Returns:
            Formatted string representation
        """
        pass

    
    @abstractmethod
    def render_pam_metadata(self, data: XmlMetadata, title: Optional[str] = None) -> str:
        """
        Render Precision Auxiliary Metadata (PAM) section.
        
        Args:
            data: XmlMetadata object containing PAM content
            title: Optional override for section title
            
        Returns:
            Formatted string representation
        """
        pass

    @abstractmethod
    def render_differences(self, data: DifferencesComparison, title: str = "Differences") -> str:
        """
        Render differences comparison table.
        
        Args:
            data: DifferencesComparison dataclass
            title: Section title
            
        Returns:
            Formatted string representation
        """
        pass
    
    @abstractmethod
    def render_ifd_table(self, data: IfdInfoData, title: Optional[str] = None) -> str:
        """
        Render IFD table.
        
        Args:
            data: IfdInfoData dataclass
            title: Optional override title
            
        Returns:
            Formatted string representation
        """
        pass
    
    @abstractmethod
    def render_statistics_data(self, data: StatisticsData, title: Optional[str] = None) -> str:
        """
        Render statistics data table.
        
        Args:
            data: StatisticsData dataclass
            title: Optional override title
            
        Returns:
            Formatted string representation
        """
        pass
    
    @abstractmethod
    def render_histogram_image(self, data: HistogramImage, title: Optional[str] = None) -> str:
        """
        Render histogram data.
        
        Args:
            data: HistogramImage dataclass
            title: Optional override title
            
        Returns:
            Formatted string representation
        """
        pass
    
    @abstractmethod
    def render_comparison_ifd(self, data: IfdInfoComparison, title: Optional[str] = None) -> str:
        """
        Render grouped IFD comparison data.
        
        Args:
            data: IfdInfoComparison with multiple file IFD tables
            title: Optional override title
            
        Returns:
            Formatted string representation
        """
        pass
    
    @abstractmethod
    def render_comparison_statistics(self, data: StatisticsComparison, title: Optional[str] = None) -> str:
        """
        Render grouped statistics comparison data.
        
        Args:
            data: StatisticsComparison with multiple file statistics
            title: Optional override title
            
        Returns:
            Formatted string representation
        """
        pass
    
    @abstractmethod
    def render_comparison_histogram(self, data: HistogramComparison, title: Optional[str] = None) -> str:
        """
        Render grouped histogram comparison data.
        
        Args:
            data: HistogramComparison with multiple file histograms
            title: Optional override title
            
        Returns:
            Formatted string representation
        """
        pass
    
    @abstractmethod
    def render_comparison_cog(self, data: CogValidationComparison, title: Optional[str] = None) -> str:
        """
        Render grouped COG validation comparison data.
        
        Args:
            data: CogValidationComparison with multiple file COG validations
            title: Optional override title
            
        Returns:
            Formatted string representation
        """
        pass


class MarkdownRenderer(Renderer):
    """
    Renders report sections as Markdown.
    
    Produces clean, readable markdown suitable for display in terminals,
    conversion to HTML, or saving as .md files.
    """

    def __init__(self):
        """
        Initialize the MarkdownRenderer.
        """
        super().__init__()

    def render_tags(self, data: TiffTagsData, title: Optional[str] = None) -> str:
        """Render TIFF tags as a markdown table with dynamic title and footer."""
        section_title = title or data.title
        
        lines = [f"## {section_title}", ""]
        lines.append("| Number | Name | Value |")
        lines.append("|---|---|---|")
        
        for tag in data.tags:
            # Format value based on type
            value_str = ""
            if tag.code == GEO_ASCII_PARAMS_TAG:
                # Handle Esri PE String specially to avoid massive text blocks
                value_str = tag.value
                if 'esri pe string' in value_str.lower():
                    # Case-insensitive replacement (ESRI, Esri)
                    pattern = re.compile(r'(ESRI PE String\s*=\s*)(.*?)(\||$)', re.IGNORECASE | re.DOTALL)
                    
                    def replacement(match):
                        prefix = match.group(1)
                        # Check if the 'esri' section is actually requested in the report
                        if self.has_section('esri'):
                            content = "[*see below*](#esri)"
                        else:
                            content = "*present but not reported*"
                        suffix = match.group(3)
                        return f"{prefix}{content}{suffix}"
                    
                    value_str = pattern.sub(replacement, value_str)
                
                value_str = format_citation(value_str)
            elif tag.code in XML_TAGS:
                section_map = {
                    XMP_TAG: "xmp-metadata",
                    GEO_METADATA_TAG: "geo-metadata",
                    GDAL_METADATA_TAG: "gdal-metadata"
                }
                section_id = section_map.get(tag.code)
                if section_id:
                    value_str = f"[*see below*](#{section_id})" if self.has_section(section_id) else "*present but not reported*"
                else:
                    # Fallback for safety, though every tag in XML_TAGS should be in section_map
                    value_str = format_value(tag.value)
            elif tag.interpretation:
                value_str = f"{tag.value}: {tag.interpretation}"
            else:
                value_str = format_value(tag.value)

            
            lines.append(f"| {tag.code} | {tag.name} | {value_str} |")
        
        if data.has_footer() and data.footer:
            lines.append("")
            lines.append(data.footer)
        
        return "\n".join(lines)
    
    def render_geokeys(self, geokeys: List[GeoKey], title: str = "GeoKey Directory") -> str:
        """Render GeoKeys as a markdown table."""
        lines = [f"## {title}", ""]
        lines.append("| Number | Name | Value |")
        lines.append("|---|---|---|")
        
        for key in geokeys:
            value_text = key.value_text
            # Format value_text for citations and interpreted values
            if key.is_citation:
                # Citations may need special formatting
                value_text = format_value(value_text)
            elif isinstance(value_text, str) and '(' in value_text and value_text.endswith(')'):
                # Convert "value (interpretation)" to "value: interpretation"
                parts = value_text.split('(', 1)
                value_text = f"{parts[0].strip()}: {parts[1].strip(')')}"
            
            lines.append(f"| {key.id} | {key.name} | {value_text} |")
        
        return "\n".join(lines)
    
    def render_statistics(self, stats: List[StatisticsBand], title: str = "Statistics", footer: Optional[str] = None) -> str:
        """Render statistics as a markdown table."""
        if not stats:
            return f"## {title}\n\nNo statistics available."
        
        lines = [f"## {title}", ""]
        
        # Use class method for field definitions
        display_fields = StatisticsBand.get_display_fields()
        
        # Initialize color manager if styling is enabled
        color_map = {}
        if self.enable_html_styling:
            band_names_only = [s.band_name for s in stats]
            color_manager = ColorManager(band_names_only)
            color_map = color_manager.get_color_map()
        
        # Build headers
        headers = ["Statistic"]
        for s in stats:
            name = s.band_name
            if self.enable_html_styling and name in color_map:
                color = color_map[name]
                headers.append(f'<span style="color: {color}">{name}</span>')
            else:
                headers.append(name)
        
        lines.append(f"| {' | '.join(headers)} |")
        lines.append(f"| {' | '.join(['---'] * len(headers))} |")
        
        # Build rows - render all fields that have data in at least one band
        for display_name, field_name, always_show in display_fields:
            # Skip fields that have no data in any band (None for all bands)
            if not always_show and not any(getattr(band, field_name, None) is not None for band in stats):
                continue
            
            values = [display_name]
            for band in stats:
                val = getattr(band, field_name, None)
                val_str = format_value(val) if val is not None else ""
                
                if self.enable_html_styling and val_str:
                     # Get color for this band column
                    color = color_map.get(band.band_name)
                    if color:
                        val_str = f'<span style="color: {color}">{val_str}</span>'
                
                values.append(val_str)
            lines.append(f"| {' | '.join(values)} |")
        
        if footer:
            lines.append("")
            lines.append(footer)
        
        return "\n".join(lines)
    
    def render_georeference(self, georef: GeoReference, title: str = "Georeference") -> str:
        """
        Render georeference information as a two-column table.
        
        This now uses the formatting methods from GeoReference to combine
        names and codes (e.g., "WGS 84 (EPSG:4326)") instead of receiving
        pre-formatted strings from geokey_parser.
        """
        lines = [f"## {title}", ""]
        lines.append("| Attribute | Value |")
        lines.append("|---|---|")
        
        # Add standard fields with formatting
        if georef.raster_type:
            lines.append(f"| Raster Type | {georef.raster_type} |")
        
        # Use formatting methods that combine name + code
        formatted_geo_cs = georef.get_formatted_geographic_cs()
        if formatted_geo_cs:
            lines.append(f"| Geographic CS | {formatted_geo_cs} |")
        
        formatted_proj_cs = georef.get_formatted_projected_cs()
        if formatted_proj_cs:
            lines.append(f"| Projected CS | {formatted_proj_cs} |")
        
        if georef.compound_cs:
            lines.append(f"| Compound CS | {georef.compound_cs} |")
        
        formatted_datum = georef.get_formatted_datum()
        if formatted_datum:
            lines.append(f"| Datum | {formatted_datum} |")
        
        if georef.ellipsoid:
            lines.append(f"| Ellipsoid | {georef.ellipsoid} |")
        
        if georef.linear_unit:
            lines.append(f"| Linear Unit | {georef.linear_unit} |")
        
        if georef.angular_unit:
            lines.append(f"| Angular Unit | {georef.angular_unit} |")
        
        formatted_vert_cs = georef.get_formatted_vertical_cs()
        if formatted_vert_cs:
            lines.append(f"| Vertical CS | {formatted_vert_cs} |")
        
        formatted_vert_datum = georef.get_formatted_vertical_datum()
        if formatted_vert_datum:
            lines.append(f"| Vertical Datum | {formatted_vert_datum} |")
        
        if georef.vertical_unit:
            lines.append(f"| Vertical Unit | {georef.vertical_unit} |")
        
        # Add additional parameters
        for key, value in georef.additional_params.items():
            lines.append(f"| {key} | {value} |")
        
        return "\n".join(lines)
    
    def render_bbox(self, bbox: BoundingBox, title: str = "Bounding Box") -> str:
        """Render bounding box as a table."""
        lines = [f"## {title}", ""]
        lines.append("| Edge | Value | Unit |")
        lines.append("|---|---|---|")

        unit = bbox.horizontal_unit or ""
        west = f"{bbox.west:,.8f}" if "deg" in unit.lower() else f"{bbox.west:,.4f}"
        east = f"{bbox.east:,.8f}" if "deg" in unit.lower() else f"{bbox.east:,.4f}"
        south = f"{bbox.south:,.8f}" if "deg" in unit.lower() else f"{bbox.south:,.4f}"
        north = f"{bbox.north:,.8f}" if "deg" in unit.lower() else f"{bbox.north:,.4f}"
        
        lines.append(f"| West | {west} | {unit} |")
        lines.append(f"| East | {east} | {unit} |")
        lines.append(f"| South | {south} | {unit} |")
        lines.append(f"| North | {north} | {unit} |")
        
        if bbox.is_3d():
            vert_unit = bbox.vertical_unit or ""
            lines.append(f"| Bottom | {bbox.bottom:,.7g} | {vert_unit} |")
            lines.append(f"| Top | {bbox.top:,.7g} | {vert_unit} |")
        
        return "\n".join(lines)
    
    def render_geoextent(self, extents: GeoExtents, title: str = "Geographic Extent") -> str:
        """Render geographic extents as a table with DMS coordinates."""
        def dms_from_decimal(dd: float, direction: str) -> str:
            """Convert decimal degrees to DMS format."""
            if direction not in ['lat', 'lon']:
                return str(dd)
            
            is_positive = dd >= 0
            dd = abs(dd)
            minutes, seconds = divmod(dd * 3600, 60)
            degrees, minutes = divmod(minutes, 60)
            
            if direction == 'lat':
                hemisphere = 'N' if is_positive else 'S'
            else:
                hemisphere = 'E' if is_positive else 'W'
            
            return f"{int(degrees)}° {int(minutes)}' {seconds:.2f}\" {hemisphere}"
        
        lines = [f"## {title}", ""]
        lines.append("| Corner | Longitude | Latitude |")
        lines.append("|---|---|---|")
        
        corners = [
            ("Upper Left", extents.upper_left),
            ("Lower Left", extents.lower_left),
            ("Upper Right", extents.upper_right),
            ("Lower Right", extents.lower_right),
            ("Center", extents.center)
        ]
        
        for name, (lon, lat) in corners:
            lon_dms = dms_from_decimal(lon, 'lon')
            lat_dms = dms_from_decimal(lat, 'lat')
            lines.append(f"| {name} | {lon_dms} | {lat_dms} |")
        
        return "\n".join(lines)
    
    def render_geotransform(self, gt: GeoTransform, title: str = "GeoTransform") -> str:
        """Render geotransform with explanation."""
        lines = [f"## {title}\\*", ""]
        lines.append("| Index | Coefficient | Value |")
        lines.append("|---|---|---|")
        
        coeffs = [
            ("0", "X Origin", gt.x_origin),
            ("1", "Pixel Width", gt.pixel_width),
            ("2", "X Skew", gt.x_skew),
            ("3", "Y Origin", gt.y_origin),
            ("4", "Y Skew", gt.y_skew),
            ("5", "Pixel Height", gt.pixel_height)
        ]
        
        for idx, name, value in coeffs:
            lines.append(f"| {idx} | {name} | {value} |")
        
        # Add explanation
        lines.append("")
        lines.append("\\* *The GeoTransform is an affine transformation that maps pixel/line coordinates (P, L)*")
        lines.append("*to geographic coordinates (X, Y). The transformation is:*\n")
        lines.append("```")
        lines.append("X = GT[0] + P × GT[1] + L × GT[2]")
        lines.append("Y = GT[3] + P × GT[4] + L × GT[5]")
        lines.append("```")
        lines.append("\n*or in matrix form:*\n")
        lines.append("```")
        lines.append("| GT[1]  GT[2]  GT[0] |   | P |   | X |")
        lines.append("| GT[4]  GT[5]  GT[3] | × | L | = | Y |")
        lines.append("|   0      0      1   |   | 1 |   | 1 |")
        lines.append("```")
        
        return "\n".join(lines)
    
    def render_tiling_table(self, tiles: List[TileInfo], title: str = "Tiling and Overviews") -> str:
        """Render tiling information as a table."""
        lines = [f"## {title}", ""]
        lines.append("| Level | Tile Count | Tile Size | Tile Dimensions | Total Pixels | Resolution |")
        lines.append("|---|---|---|---|---|---|")
        
        for tile in tiles:
            lines.append(f"| {tile.level} | {tile.tile_count} | {tile.block_size} | "
                        f"{tile.tile_dimensions} | {tile.total_pixels} | {tile.resolution} |")
        
        return "\n".join(lines)
    
    def render_ifd(self, ifds: List[IfdInfo], title: str = "Image File Directory (IFD) List") -> str:
        """Render IFD information as a table."""
        if not ifds:
            return f"## {title}\n\nNo IFD information available."
        
        lines = [f"## {title}", ""]
        
        # Determine which columns to include based on data
        has_decimals = any(ifd.decimals for ifd in ifds)
        has_photometric = any(ifd.photometric for ifd in ifds)
        has_predictor = any(ifd.predictor for ifd in ifds)
        has_lerc = any(ifd.lerc_max_z_error for ifd in ifds)
        
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
        
        lines.append(f"| {' | '.join(headers)} |")
        lines.append(f"| {' | '.join(['---'] * len(headers))} |")
        
        # Build rows
        for ifd in ifds:
            row = [
                str(ifd.ifd),
                ifd.ifd_type,
                ifd.dimensions,
                ifd.block_size,
                ifd.data_type,
                str(ifd.bands),
                str(ifd.bits_per_sample)
            ]
            if has_decimals:
                row.append(str(ifd.decimals))
            if has_photometric:
                row.append(ifd.photometric or "")
            row.append(ifd.compression_algorithm or "")
            if has_predictor:
                row.append(ifd.predictor or "")
            if has_lerc:
                row.append(ifd.lerc_max_z_error or "")
            row.append(ifd.space_saving or "")
            row.append(ifd.ratio or "")
            
            lines.append(f"| {' | '.join(row)} |")
        
        return "\n".join(lines)
    
    def render_wkt_string(self, data: WktString, title: Optional[str] = None) -> str:
        """
        Render WKT2 or ESRI PE String section.
        
        Args:
            data: WktString object containing WKT or PE String
            title: Optional override for section title
            
        Returns:
            Formatted markdown string
        """
        # Respect provided title to keep anchors consistent with HtmlReportFormatter.anchor_map
        if title:
            section_title = title
        else:
            # Fall back to registry-standard labels when no override provided
            if data.format_version == "WKT_ESRI":
                section_title = "ESRI Projection Engine (PE) String"
            else:
                section_title = f"Well Known Text 2 ({data.format_version}) String"

        
        if not data.has_content():
            return f"## {section_title}\n\nNo data available."
        
        lines = [f"## {section_title}", ""]
        lines.append("```wkt")
        lines.append(data.wkt_string)
        lines.append("```")
        
        return "\n".join(lines)
    
    def render_json_string(self, data: JsonString, title: Optional[str] = None) -> str:
        """
        Render PROJJSON section.
        
        Args:
            data: JsonString object containing PROJJSON
            title: Optional override for section title
            
        Returns:
            Formatted markdown string
        """
        section_title = title or "PROJJSON String"
        
        if not data.has_content():
            return f"## {section_title}\n\nNo data available."
        
        lines = [f"## {section_title}", ""]
        
        # Pretty print JSON if it's valid
        if data.is_valid_json():
            try:
                formatted_json = json.dumps(json.loads(data.json_string), indent=2)
                lines.append("```json")
                lines.append(formatted_json)
                lines.append("```")
            except json.JSONDecodeError:
                # Fallback to raw string if pretty print fails
                lines.append("```json")
                lines.append(data.json_string)
                lines.append("```")
        else:
            lines.append("```json")
            lines.append(data.json_string)
            lines.append("```")
        
        return "\n".join(lines)

    def _render_cog_status(self, 
                         is_valid: bool,
                         errors: Optional[List[str]], 
                         warnings: Optional[List[str]], 
                         headers_size: Optional[int] = None,
                         success_label: Optional[str] = "✅ This is a valid Cloud Optimized GeoTIFF.",
                         failure_label: str = "❌ This is **not** a valid Cloud Optimized GeoTIFF.") -> List[str]:
        """
        Helper to render COG validation results consistently.
        
        Args:
            is_valid: Boolean indicating if the COG is valid.
            errors: List of validation errors.
            warnings: List of validation warnings.
            headers_size: Optional size of IFD headers (only shown on success).
            success_label: Message to show if valid. If None, shows nothing on success.
            failure_label: Message to show if invalid.
            
        Returns:
            List of markdown lines.
        """
        lines = []
        
        if is_valid:
            if success_label:
                lines.append(success_label)
                if headers_size:
                    lines.append(f"- Size of all Image File Directory (IFD) headers: {headers_size} bytes")
        else:
            lines.append(failure_label)
            if errors:
                lines.append("- **Errors:**")
                lines.extend([f"   - {error}" for error in errors])
        
        if warnings:
            lines.append("- **Warnings:**")
            lines.extend([f"   - {warning}" for warning in warnings])
            
        return lines

    def render_cog_validation(self, cog: CogValidation, title: str = "COG Compliance") -> str:
        """
        Render COG Validation section.
        
        Args:
            cog: CogValidation object containing validation results
            title: Optional override for section title
            
        Returns:
            Formatted markdown string
        """
        lines = [f"## {title}", ""]
        
        status_lines = self._render_cog_status(
            is_valid=cog.is_valid(),
            errors=cog.errors,
            warnings=cog.warnings,
            headers_size=cog.headers_size
        )
        lines.extend(status_lines)
        
        return "\n".join(lines)

    def _render_xml_content(self, data: XmlMetadata, default_title: str, title: Optional[str] = None) -> str:
        """
        Private helper to render any XML metadata section.
        
        Args:
            data: XmlMetadata object containing XML content.
            default_title: Default title if no other is provided.
            title: Optional override for section title.
            
        Returns:
            Formatted markdown string.
        """
        section_title = title or data.title or default_title
        
        if not data.has_content():
            return f"## {section_title}\n\nNo data available."
        
        lines = [f"## {section_title}", ""]
        
        from gttk.utils.contexts import xml_type_context
        xml_type = xml_type_context.get()
        
        # The rendering format is now determined by the `format_type` of the renderer instance
        if xml_type == 'table':
            lines.append(xml_to_markdown(
                data.content,
                sample_color_map=self.sample_color_map,
                enable_styling=self.enable_html_styling
            ))
        else:
            # For HTML, embed as a code block and let mistune handle it
            # Prettify here so that raw Markdown output is also readable
            pretty_content = pretty_print_xml(data.content)
            lines.append("```xml")
            lines.append(pretty_content)
            lines.append("```")
            
        return "\n".join(lines)

    def render_gdal_metadata(self, data: XmlMetadata, title: Optional[str] = None) -> str:
        """Render GDAL_METADATA TIFF Tag (#42112) section."""
        return self._render_xml_content(data, "GDAL_METADATA (TIFF Tag #42112)", title)

    def render_geo_metadata(self, data: XmlMetadata, title: Optional[str] = None) -> str:
        """Render GEO_METADATA TIFF Tag (#50909) section."""
        return self._render_xml_content(data, "GEO_METADATA (TIFF Tag #50909)", title)

    def render_xmp_metadata(self, data: XmlMetadata, title: Optional[str] = None) -> str:
        """Render Extensible Metadata Platform (XMP) TIFF Tag (#700) section."""
        return self._render_xml_content(data, "Extensible Metadata Platform (XMP)", title)

    def render_xml_metadata(self, data: XmlMetadata, title: Optional[str] = None) -> str:
        """Render external XML file metadata section."""
        return self._render_xml_content(data, "XML Metadata", title)

    def render_pam_metadata(self, data: XmlMetadata, title: Optional[str] = None) -> str:
        """Render Precision Auxiliary Metadata (PAM) section."""
        return self._render_xml_content(data, "Precision Auxiliary Metadata (PAM)", title)

    def render_differences(self, data: DifferencesComparison, title: str = "Differences") -> str:
        """
        Render differences comparison table.
        
        Creates a comparison table showing the differences between two files,
        including file format, COG status, compression algorithm, and size metrics.
        
        Args:
            data: DifferencesComparison dataclass with comparison metrics
            title: Section title
            
        Returns:
            Markdown formatted table with result summary
        """
        lines = [f"## {title}", ""]
        
        # Build comparison table
        lines.append(f"| {' | '.join(data.headers)} |")
        lines.append(f"| {' | '.join(['---'] * len(data.headers))} |")
        lines.append(f"| {' | '.join([str(v) for v in data.base_row])} |")
        lines.append(f"| {' | '.join([str(v) for v in data.comp_row])} |")
        lines.append("")
        
        # Add result summary
        lines.append(f"**Result**: *{data.get_result_text()}*")
        
        # Use the helper only if attempt to create COG failed
        if data.cog_creation_failed:
            status_lines = self._render_cog_status(
                is_valid=False,
                errors=data.cog_errors,
                warnings=data.cog_warnings,
                success_label=None, # Don't print anything if it passed
                failure_label="\n\\* The request to make a COG failed."
            )
            lines.extend(status_lines)
        
        return "\n".join(lines)
    
    def render_ifd_table(self, data: IfdInfoData, title: Optional[str] = None) -> str:
        """
        Render IFD table.
        
        Creates a formatted table showing Image File Directory (IFD) information
        for all IFDs in the TIFF file.
        
        Args:
            data: IfdInfoData dataclass
            title: Optional override title
            
        Returns:
            Markdown formatted IFD table
        """
        ifds = [IfdInfo(**row) for row in data.rows]
        return self.render_ifd(ifds, title or data.title)

    def render_statistics_data(self, data: StatisticsData, title: Optional[str] = None) -> str:
        """
        Render statistics data table.
        
        Args:
            data: StatisticsData dataclass
            title: Optional override title
            
        Returns:
            Markdown formatted statistics table
        """
        title = title or data.title
        lines = [f"## {title}", ""]
        
        if not data.headers or not data.data:
            lines.append("*No statistics available*")
            return "\n".join(lines)
        
        # Determine colors if enabled
        # Note: StatisticsData loses the direct connection to band objects,
        # so infer from headers (headers[0] is 'Statistic', rest are band names)
        band_names = data.headers[1:]
        color_map = {}
        index_map = {} # Maps header index to color
        
        if self.enable_html_styling:
            color_manager = ColorManager(band_names)
            # Map by name and by column index (shifted by 1 because of 'Statistic' col)
            for i, name in enumerate(band_names):
                color = color_manager.get_color(i, name)
                color_map[name] = color
                index_map[i+1] = color

        # Build headers
        processed_headers = []
        for i, h in enumerate(data.headers):
            if self.enable_html_styling and i in index_map:
                color = index_map[i]
                processed_headers.append(f'<span style="color: {color}">{h}</span>')
            else:
                processed_headers.append(h)

        lines.append(f"| {' | '.join(processed_headers)} |")
        lines.append(f"| {' | '.join(['---'] * len(processed_headers))} |")
        
        for row in data.data:
            row_values = []
            for i, h in enumerate(data.headers):
                val = str(row.get(h, ''))
                if self.enable_html_styling and i in index_map and val:
                    color = index_map[i]
                    val = f'<span style="color: {color}">{val}</span>'
                row_values.append(val)
            lines.append(f"| {' | '.join(row_values)} |")
        
        if data.footnote:
            lines.append("")
            lines.append(data.footnote)
        
        return "\n".join(lines)

    def render_histogram_image(self, data: HistogramImage, title: Optional[str] = None) -> str:
        """
        Render histogram image with embedded base64 data.
        
        Args:
            data: HistogramImage dataclass
            title: Optional override title
            
        Returns:
            Markdown formatted histogram with embedded image
        """
        title = title or data.title or "Histogram"
        lines = [f"## {title}"]
        
        if not data.base64_image:
            lines.append("*No histogram available*")
            return "\n".join(lines)
        
        # Embed the image using markdown image syntax with data URI
        lines.append(f'<img src="data:image/png;base64,{data.base64_image}" alt="{data.title} Histogram" width="600px"/>')
        return "\n".join(lines)
    
    
    def render_comparison_ifd(self, data: IfdInfoComparison, title: Optional[str] = None) -> str:
        """
        Render grouped IFD comparison data with subheaders for each file.
        
        Args:
            data: IfdInfoComparison with multiple file IFD tables
            title: Optional override title
            
        Returns:
            Markdown formatted grouped IFD comparison
        """
        title = title or data.title
        lines = [f"## {title}", ""]
        
        for file_label, ifd_data in data.files:
            # Add subheader for each file
            lines.append(f"### {file_label}")
            lines.append("")
            
            if not ifd_data.headers or not ifd_data.rows:
                lines.append("*No IFD information available*")
                lines.append("")
                continue
            
            # Build table for this file
            lines.append(f"| {' | '.join(ifd_data.headers)} |")
            lines.append(f"| {' | '.join(['---'] * len(ifd_data.headers))} |")
            for row in ifd_data.rows:
                row_values = [str(row.get(h, '')) for h in ifd_data.headers]
                lines.append(f"| {' | '.join(row_values)} |")
            lines.append("")
        
        return "\n".join(lines)
    
    def render_comparison_statistics(self, data: StatisticsComparison, title: Optional[str] = None) -> str:
        """
        Render grouped statistics comparison data with subheaders for each file.
        
        Args:
            data: StatisticsComparison with multiple file statistics
            title: Optional override title
            
        Returns:
            Markdown formatted grouped statistics comparison
        """
        title = title or data.title
        lines = [f"## {title}", ""]
        
        for file_label, stats_data in data.files:
            # Add subheader for each file
            lines.append(f"### {file_label}")
            lines.append("")
            
            if not stats_data.headers or not stats_data.data:
                lines.append("*No statistics available*")
                lines.append("")
                continue
            
            # Determine colors if enabled
            band_names = stats_data.headers[1:]
            color_map = {}
            index_map = {} # Maps header index to color
            
            if self.enable_html_styling:
                color_manager = ColorManager(band_names)
                for i, name in enumerate(band_names):
                    color = color_manager.get_color(i, name)
                    color_map[name] = color
                    index_map[i+1] = color

            # Build headers
            processed_headers = []
            for i, h in enumerate(stats_data.headers):
                if self.enable_html_styling and i in index_map:
                    color = index_map[i]
                    processed_headers.append(f'<span style="color: {color}">{h}</span>')
                else:
                    processed_headers.append(h)

            lines.append(f"| {' | '.join(processed_headers)} |")
            lines.append(f"| {' | '.join(['---'] * len(processed_headers))} |")
            
            for row in stats_data.data:
                row_values = []
                for i, h in enumerate(stats_data.headers):
                    val = str(row.get(h, ''))
                    if self.enable_html_styling and i in index_map and val:
                        color = index_map[i]
                        val = f'<span style="color: {color}">{val}</span>'
                    row_values.append(val)
                lines.append(f"| {' | '.join(row_values)} |")
            
            if stats_data.footnote:
                lines.append("")
                lines.append(stats_data.footnote)
            lines.append("")
        
        return "\n".join(lines)
    
    def render_comparison_histogram(self, data: HistogramComparison, title: Optional[str] = None) -> str:
        """
        Render grouped histogram comparison data with subheaders for each file.
        
        Args:
            data: HistogramComparison with multiple file histograms
            title: Optional override title
            
        Returns:
            Markdown formatted grouped histogram comparison
        """
        title = title or data.title
        lines = [f"## {title}", ""]
        
        for file_label, hist_data in data.files:
            # Add subheader for each file
            lines.append(f"### {file_label}")
            lines.append("")
            
            if not hist_data.base64_image:
                lines.append("*No histogram available*")
                lines.append("")
                continue
            
            # Embed the image using HTML img tag so alt and width attributes are explicit
            lines.append(f'<img src="data:image/png;base64,{hist_data.base64_image}" alt="{hist_data.title} Histogram" width="600px"/>')
            lines.append("")
        
        return "\n".join(lines)
    
    def render_comparison_cog(self, data: CogValidationComparison, title: Optional[str] = None) -> str:
        """
        Render grouped COG validation comparison data with subheaders for each file.
        
        Args:
            data: CogValidationComparison with multiple file COG validations
            title: Optional override title
            
        Returns:
            Markdown formatted grouped COG validation comparison
        """
        title = title or data.title
        lines = [f"## {title}", ""]
        
        for file_label, cog in data.files:
            # Add subheader for each file
            lines.append(f"### {file_label}")
            lines.append("")
            
            status_lines = self._render_cog_status(
                is_valid=cog.is_valid(),
                errors=cog.errors,
                warnings=cog.warnings,
                headers_size=cog.headers_size
            )
            lines.extend(status_lines)
            lines.append("")
        
        return "\n".join(lines)
