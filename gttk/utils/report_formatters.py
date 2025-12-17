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
Report Formatters for GeoTIFF Metadata.

This module provides classes for formatting complete GeoTIFF metadata reports
in different formats (Markdown, HTML) for the Read Metadata and Compare Compression
reports. Formatters orchestrate data fetching, rendering, and report assembly.

Classes:
    ReportFormatter: Abstract base class for all report formatters
    MarkdownReportFormatter: Formats Markdown reports with table of contents
    HtmlReportFormatter: Formats complete HTML reports with CSS and navigation
"""

import html
import logging
import mistune
import re
from abc import ABC, abstractmethod
from importlib import metadata, resources
from typing import Any, List
from urllib.parse import quote
from gttk.utils.contexts import banner_context, xml_type_context
from gttk.utils.data_models import ReportSection, MenuItem
from gttk.utils.resource_manager import resource_manager
from gttk.utils.section_registry import get_renderer, get_icon
from gttk.utils.section_renderers import MarkdownRenderer, Renderer
from gttk.utils.xml_formatter import xml_to_html, get_theme_colors, pretty_print_xml
from gttk.utils.colors import ColorManager

logger = logging.getLogger(__name__)

try:
    __version__ = metadata.version("geotiff-toolkit")
except metadata.PackageNotFoundError:
    __version__ = "0.0.0-dev"

# ============================================================================
# Report Generator Classes
# ============================================================================

class ReportFormatter(ABC):
    """
    Base class for generating GeoTIFF metadata reports.
    
    Orchestrates report assembly from pre-built sections. Subclasses
    implement format-specific rendering (Markdown, HTML, etc.).
    
    Note: Use ReportBuilder subclasses to build sections, then pass to
    generator for formatting. This separates "what to include" (builder)
    from "how to format" (generator).
    
    Attributes:
        renderer: Renderer instance for formatting sections
        context: Processing context with GeoTIFF metadata (optional, for compatibility)
        sections: List of ReportSection objects to include in report
    
    Example:
        >>> # Build sections using MetadataReportBuilder
        >>> builder = MetadataReportBuilder(context)
        >>> builder.add_standard_sections(['tags', 'statistics'])
        >>>
        >>> # Generate formatted output
        >>> formatter = MarkdownReportFormatter(context)
        >>> formatter.sections = builder.sections
        >>> report = formatter.format()
    """
    
    def __init__(self, renderer: Renderer):
        """
        Initialize generator with a renderer.
        
        Args:
            renderer: Renderer instance (MarkdownRenderer or HtmlRenderer)
        """
        self.renderer = renderer
        self.sections: List[ReportSection] = []
        # Standardized header controls used by all formatters
        # report_title: logical report name shown in headers (e.g., "Metadata Report", "Compression Comparison")
        # include_title: for Markdown header only; HTML header always shows report_title
        self.report_title: str = "Metadata Report"
        self.include_title: bool = False
    
    def add_section(self, section_id: str, title: str, menu_name: str,data: Any) -> None:
        """
        Add a section to the report.
        
        Only adds the section if data is not None. This allows conditional
        section inclusion based on data availability.
        
        Args:
            section_id: Section identifier (e.g., 'tags', 'geokeys')
            title: Human-readable section title
            menu: Short menu title for the HTML navbar
            data: Dataclass instance or list of dataclass instances
        """
        if data is not None:
            self.sections.append(ReportSection(
                id=section_id,
                title=title,
                menu_name=menu_name,
                data=data,
                enabled=True
            ))
            logger.debug(f"Added section '{section_id}' with title '{title}'")
        else:
            logger.debug(f"Skipped section '{section_id}' - no data available")
    
    
    def prepare_rendering(self) -> None:
        """
        Prepare the renderer before rendering sections.
        This allows setting up state like color maps that depend on having all sections loaded.
        """
        # Set sections in renderer so has_section() works correctly
        if self.renderer:
            self.renderer.set_sections([s.id for s in self.sections])

    def format(self) -> str:
        """
        Generate the complete report as a string.
        
        Assembles the report by rendering header, all sections, and footer.
        Empty sections are filtered out.
        
        Returns:
            Complete report as formatted string
        """
        self.prepare_rendering()
        
        parts = []
        parts.append(self._render_header())
        
        for section in self.sections:
            if section.has_data():
                rendered = self._render_section(section)
                if rendered:
                    parts.append(rendered)
        
        parts.append(self._render_footer())
        
        return "\n\n".join(filter(None, parts))
    
    @abstractmethod
    def _render_header(self) -> str:
        """
        Render report header.
        
        Returns:
            Formatted header string
        """
        pass
    
    @abstractmethod
    def _render_section(self, section: ReportSection) -> str:
        """
        Render a single section.
        
        Args:
            section: ReportSection to render
            
        Returns:
            Formatted section string
        """
        pass
    
    @abstractmethod
    def _render_footer(self) -> str:
        """
        Render report footer.
        
        Returns:
            Formatted footer string
        """
        pass


class MarkdownReportFormatter(ReportFormatter):
    """
    Generate Markdown reports with table of contents.
    
    Produces clean, readable markdown suitable for display in terminals,
    conversion to HTML, or saving as .md files. Includes automatic table
    of contents generation with anchor links.
    
    Example:
        >>> context = build_context_from_file('example.tif')
        >>> formatter = MarkdownReportFormatter(context)
        >>> formatter.fetch_and_add_section('tags')
        >>> formatter.fetch_and_add_section('statistics')
        >>> markdown = formatter.format()
        >>> with open('report.md', 'w') as f:
        ...     f.write(markdown)
    """
    
    def __init__(self, filename: str = "Unknown"):
        """
        Initialize Markdown report formatter.
        
        Args:
            filename: The name of the file being reported on.
        """
        super().__init__(MarkdownRenderer())
        self.filename = filename
    
    def _render_header(self) -> str:
        """
        Render markdown header with table of contents.
        
        Returns:
            Formatted header with metadata and TOC
        """
        lines = []
        if getattr(self, "include_title", False) and getattr(self, "report_title", None):
            lines.append(f"# {self.report_title}: {self.filename}\n")

        if self.sections:
            lines.append("## Table of Contents\n")
            for section in self.sections:
                anchor = section.title.lower()
                anchor = anchor.replace(' ', '-')
                anchor = re.sub(r'[^a-z0-9\-_]', '', anchor)
                anchor = anchor.strip('-')
                
                lines.append(f"- [{section.title}](#{anchor})")
        
        return "\n".join(lines)
    
    def _render_section(self, section: ReportSection) -> str:
        """
        Render a markdown section using the appropriate renderer method.
        
        Args:
            section: ReportSection to render
            
        Returns:
            Formatted markdown section
        """
        try:
            renderer_method_name = get_renderer(section.id)
        except KeyError:
            logger.warning(f"No renderer method found for section '{section.id}'")
            return f"## {section.title}\n\n*Renderer not implemented*"

        renderer_method = getattr(self.renderer, renderer_method_name, None)
        if renderer_method is None:
            logger.warning(f"Renderer method '{renderer_method_name}' not found in renderer for section '{section.id}'")
            return f"## {section.title}\n\n*Renderer not implemented*"
        
        try:
            if renderer_method:
                return renderer_method(section.data, title=section.title)
            return ""
        except Exception as e:
            logger.error(f"Error rendering section '{section.id}': {e}")
            return f"## {section.title}\n\n*Error rendering section: {e}*"
    
    def _render_footer(self) -> str:
        """
        Render markdown footer with generation info and classification banner if present.
        
        Returns:
            Formatted footer
        """
        lines = []
        lines.append(f"---\n\n*Report generated by [GeoTIFF ToolKit](https://github.com/robeckgeo/gttk) v{__version__}*")
       
        # Add classification banner at bottom
        banner = banner_context.get()
        if banner:
            lines.append("")
            lines.append(f"<center>{banner}</center>")
       
        return "\n".join(lines)


class HtmlReportFormatter(ReportFormatter):
    """
    Generate complete HTML reports with CSS and navigation.
    
    Self-contained HTML generator that:
    1. Generates markdown content using MarkdownRenderer
    2. Converts markdown to HTML using mistune
    3. Wraps in custom HTML template with CSS and navigation
    
    Example:
        >>> context = build_context_from_file('example.tif')
        >>> formatter = HtmlReportFormatter(context, banner_text="UNCLASSIFIED")
        >>> formatter.fetch_and_add_section('tags')
        >>> formatter.fetch_and_add_section('statistics')
        >>> xml_type = 'table'
        >>> with open('report.html', 'w') as f:
        ...     f.write(html)
    """
    
    def __init__(self, filename: str = "Unknown", theme: str = "material_light"):
        """
        Initialize HTML report formatter.
        
        Uses MarkdownRenderer to generate markdown content, which will then
        be converted to HTML using mistune.
        
        Args:
            filename: The name of the file being reported on.
            theme: Theme name ('material_light' or 'material_dark').
        """
        super().__init__(MarkdownRenderer())
        # Enable HTML styling for renderer (e.g. colored table headers)
        self.renderer.enable_html_styling = True
        
        self.filename = filename
        self.theme = theme
        self.menu_items: List[MenuItem] = []
        self.anchor_map = {}
        
        # Cache for band color mapping
        self._sample_color_map = None
    
    def _render_header(self) -> str:
        """
        For HTML reports, don't render a separate markdown header.
        
        The header will be generated as HTML in the template.
        
        Returns:
            Empty string (header handled by _wrap_in_html_template)
        """
        return ""
    
    def _render_section(self, section: ReportSection) -> str:
        """
        Render a markdown section and track menu items for HTML navigation.
        
        Uses MarkdownRenderer to generate markdown, which will be converted
        to HTML by mistune in the format() method.
        
        Args:
            section: ReportSection to render
            
        Returns:
            Formatted markdown section
        """
        # Dynamically determine renderer method from section ID
        try:
            renderer_method_name = get_renderer(section.id)
        except KeyError:
            logger.warning(f"No renderer method found for section '{section.id}'")
            return f"## {section.title}\n\n*Renderer not implemented*"

        renderer_method = getattr(self.renderer, renderer_method_name, None)
        if renderer_method is None:
            logger.warning(f"Renderer method '{renderer_method_name}' not found in renderer for section '{section.id}'")
            return f"## {section.title}\n\n*Renderer not implemented*"

        # Add to menu items for HTML navigation
        try:
            icon = get_icon(section.id)
        except KeyError:
            logger.warning(f"No icon found for section '{section.id}', using 'unknown'")
            icon = 'unknown'
        
        self.menu_items.append(MenuItem(
            anchor=section.id,
            name=section.menu_name,
            title=section.title,
            icon=icon
        ))
        
        # Store title-to-anchor mapping
        self.anchor_map[section.title] = section.id
        
        try:
            if renderer_method:
                return renderer_method(section.data, title=section.title)
            return ""
        except Exception as e:
            logger.error(f"Error rendering section '{section.id}': {e}")
            return f"## {section.title}\n\n*Error rendering section: {e}*"
    
    def _render_footer(self) -> str:
        """
        For HTML reports, don't render a separate markdown footer.
        
        The footer will be generated as HTML in the template.
        
        Returns:
            Empty string (footer handled by _wrap_in_html_template)
        """
        return ""
    
    def format(self) -> str:
        """
        Generate the complete HTML report.
        
        Overrides parent method to:
        1. Set sections in renderer so has_section() works correctly
        2. Generate markdown content using MarkdownRenderer
        3. Convert markdown to HTML using mistune
        4. Wrap in custom HTML template with CSS and navbar
        
        Returns:
            Complete HTML document as string
        """
        # Generate markdown content by calling parent's format()
        markdown_content = super().format()
        
        # Convert markdown to HTML using mistune
        html_body = self._markdown_to_html(markdown_content)
        
        return self._wrap_in_html_template(html_body)

    def prepare_rendering(self) -> None:
        """Prepare renderer with HTML-specific settings."""
        super().prepare_rendering()
        
        # Set sample color map on renderer for table generation (xml-type=table)
        self.renderer.sample_color_map = self._get_sample_color_map()
    
    def _get_sample_color_map(self) -> dict[str, str]:
        """
        Extract band colors from statistics section if available.
        Returns a map of sample index (str) -> hex color.
        """
        if self._sample_color_map is not None:
            return self._sample_color_map
            
        self._sample_color_map = {}
        
        # Find statistics section (standard or comparison)
        band_names = []
        
        # Check for standard statistics
        stats_section = next((s for s in self.sections if s.id == 'statistics' and s.has_data()), None)
        if stats_section:
            # StatisticsData has headers where [1:] are band names
            band_names = stats_section.data.headers[1:]
        
        # If not found, check for comparison statistics
        if not band_names:
            comp_stats_section = next((s for s in self.sections if s.id == 'comparison-statistics' and s.has_data()), None)
            if comp_stats_section:
                # StatisticsComparison has a list of files, each with StatisticsData
                # We'll use the first file's statistics to determine band names
                try:
                    first_file_stats = comp_stats_section.data.files[0][1]
                    band_names = first_file_stats.headers[1:]
                except (IndexError, AttributeError):
                    pass

        if band_names:
            try:
                color_manager = ColorManager(band_names)
                
                # Create map of string(index) -> color
                # GDAL 'sample' attribute corresponds to 0-based band index
                for i, name in enumerate(band_names):
                    self._sample_color_map[str(i)] = color_manager.get_color(i, name)
            except Exception as e:
                logger.warning(f"Failed to extract band colors from statistics: {e}")
                
        return self._sample_color_map

    def _markdown_to_html(self, markdown: str) -> str:
        """
        Convert markdown to HTML using mistune with custom renderer.
        
        Args:
            markdown: Markdown content string
            
        Returns:
            HTML content string
        """
        renderer = self._create_custom_renderer()
        md_parser = mistune.create_markdown(renderer=renderer, plugins=['table'])
        result = md_parser(markdown)
        result_str = str(result)

        # Remove trailing newlines introduced by mistune
        result_str= re.sub(r'</span>[<span class="space"></span>\r\n]{2,}</div>', r'</span></div>', result_str)

        return result_str
    
    def _create_custom_renderer(self):
        """
        Create custom mistune renderer with syntax highlighting.
        
        Returns:
            CustomRenderer instance
        """
        class CustomRenderer(mistune.HTMLRenderer):
            def __init__(self, anchor_map=None, theme="material_light", **kwargs):
                super().__init__(**kwargs)
                self.anchor_map = anchor_map or {}
                self.xml_type = xml_type_context.get()
                self.theme = theme

            def heading(self, text, level, **attrs) -> str:
                clean_text = re.sub('<[^<]+?>', '', text)
                if clean_text in self.anchor_map:
                    anchor_id = self.anchor_map[clean_text].replace('*', '')
                else:
                    # Fallback: slugify heading text when no anchor_map match
                    fallback = clean_text.lower().replace(' ', '-').replace('_', '-').replace('*', '')
                    anchor_id = fallback
                    # Debug log on anchor miss for diagnosis
                    try:
                        logger.debug(f"Anchor map miss for heading '{clean_text}'. Using fallback id '{anchor_id}'")
                    except Exception:
                        pass
                return f'<h{level} id="{anchor_id}">{text}</h{level}>'

            def block_code(self, code, info=None) -> str:
                if info == 'xml' and self.xml_type == 'text':
                    return self._highlight_xml(code)
                if info == 'wkt':
                    return self._highlight_wkt(code)
                if info == 'json':
                    return self._highlight_json(code)
                # If XML type is table, it will render as markdown table
                return super().block_code(code, info)
            
            def _highlight_xml(self, xml_text: str) -> str:
                """Apply syntax highlighting for XML using the central formatter."""
                if not xml_text or not xml_text.strip():
                    return ""
                
                # Use the theme from the parent class
                is_dark = 'dark' in self.theme if hasattr(self, 'theme') else False
                colors = get_theme_colors(dark_mode=is_dark)
                
                # Generate HTML fragment and wrap it in pre/code tags
                pretty_xml = pretty_print_xml(xml_text)
                html_fragment = xml_to_html(pretty_xml, colors)
                
                # Extract content from within <body> ... </body>
                body_match = re.search(r'<body>(.*)</body>', html_fragment, re.DOTALL)
                if body_match:
                    # Extract the inner HTML between <body>..</body> and
                    # remove only the wrapper's leading indentation/newline
                    # and any trailing whitespace after the last tag.
                    inner_html = body_match.group(1)

                    # Remove any leading characters before the first '<'
                    # (this strips the newline/indent added by the template)
                    first_lt = inner_html.find('<')
                    if first_lt > 0:
                        inner_html = inner_html[first_lt:]

                    # Trim any characters after the last '>' to remove a
                    # stray trailing newline or spaces inserted by generation.
                    last_gt = inner_html.rfind('>')
                    if last_gt != -1 and last_gt < len(inner_html) - 1:
                        inner_html = inner_html[: last_gt + 1]

                    return f'<pre><code>{inner_html}</code></pre>'
                
                # Fallback if body extraction fails
                return f'<pre><code>{html.escape(xml_text)}</code></pre>'
            
            def _highlight_wkt(self, code: str) -> str:
                """Highlights WKT syntax."""
                token_specification = [
                    ('TEXT',       r'"[^"]*"'),
                    ('KEYWORD',    r'[A-Z_a-z][A-Z0-9_]*(?=\s*\[)'),
                    ('ENUMERATION',r'[A-Z_a-z][A-Z0-9_]*'),
                    ('NUMBER',     r'-?\d+\.?\d*'),
                    ('PUNC',       r'[\[\],]'),
                    ('WHITESPACE', r'\s+'),
                ]
                tok_regex = '|'.join('(?P<%s>%s)' % pair for pair in token_specification)
                
                result = []
                for mo in re.finditer(tok_regex, code):
                    kind = mo.lastgroup
                    value = mo.group()
                    
                    if kind == 'KEYWORD':
                        result.append(f'<span class="wkt-keyword">{value}</span>')
                    elif kind == 'TEXT':
                        result.append(f'<span class="wkt-text">{html.escape(value)}</span>')
                    elif kind == 'ENUMERATION':
                        result.append(f'<span class="wkt-enum">{value}</span>')
                    elif kind == 'NUMBER':
                        result.append(f'<span class="wkt-number">{value}</span>')
                    elif kind == 'PUNC':
                        result.append(f'<span class="wkt-punc">{value}</span>')
                    else:
                        result.append(value)
                
                return f'<pre><code>{"".join(result)}</code></pre>'
            
            def _highlight_json(self, code: str) -> str:
                """Highlights PROJJSON syntax."""
                token_specification = [
                    ('MEMBER',     r'"[^"]*"(?=\s*:)'),
                    ('STRING',     r'"[^"]*"'),
                    ('NUMBER',     r'-?\d+\.?\d*'),
                    ('BOOLEAN',    r'true|false'),
                    ('PUNC',       r'[\{\}\[\]:,]'),
                    ('WHITESPACE', r'\s+'),
                ]
                tok_regex = '|'.join('(?P<%s>%s)' % pair for pair in token_specification)
                
                result = []
                for mo in re.finditer(tok_regex, code):
                    kind = mo.lastgroup
                    value = mo.group()
                    
                    if kind == 'MEMBER':
                        result.append(f'<span class="json-member">{html.escape(value)}</span>')
                    elif kind == 'STRING':
                        result.append(f'<span class="json-string">{html.escape(value)}</span>')
                    elif kind == 'NUMBER':
                        result.append(f'<span class="json-number">{value}</span>')
                    elif kind == 'BOOLEAN':
                        result.append(f'<span class="json-bool">{value}</span>')
                    elif kind == 'PUNC':
                        result.append(f'<span class="json-punc">{value}</span>')
                    else:
                        result.append(value)
                
                return f'<pre><code>{"".join(result)}</code></pre>'
        
        return CustomRenderer(
            escape=False,
            anchor_map=self.anchor_map,
            theme=self.theme
        )
    
    def _wrap_in_html_template(self, body_html: str) -> str:
        """
        Wrap HTML body in complete document with CSS, navigation, etc.
        
        Args:
            body_html: HTML content for document body
            
        Returns:
            Complete HTML document string
        """
        # Use the first word of report_title for the HTML document title prefix
        title_prefix = (getattr(self, 'report_title', '') or 'Report').split()[0]
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title_prefix}: {self.filename}</title>
    {self._generate_favicon()}
    {self._generate_css()}
</head>
<body>
    <div class="fixed-header">
        {self._generate_banner('top')}
        <div class="header-content">
            {self._generate_header()}
            {self._generate_navigation()}
        </div>
    </div>
    <div class="container">
        {body_html}
        <div class="report">Report generated by <a href="https://github.com/robeckgeo/gttk" target="_blank">GeoTIFF ToolKit</a> v{__version__}</div>
    </div>
    {self._generate_banner('bottom')}
    {self._generate_javascript()}
</body>
</html>"""
    
    def _generate_header(self) -> str:
        """Generate report header with icon and title."""
        icon_xml = self._get_icon_content('metadata', 'favicon', 'light')
        title_text = html.escape(getattr(self, 'report_title', 'Metadata Report') or 'Metadata Report')
        return f"""
    <div class="report-header">
        <img src="data:image/svg+xml;utf8,{icon_xml}" alt="Metadata Icon" class="header-icon"/>
        <div class="header-text">
            <p class="report-title">{title_text}</p>
            <p class="report-subtitle">{self.filename}</p>
        </div>
    </div>"""
    
    def _generate_navigation(self) -> str:
        """Generate navigation menu from menu_items."""
        if not self.menu_items:
            return ""
        
        items_html = ""
        for item in self.menu_items:
            icon_svg = self._get_icon_content(item.icon, 'menu')
            items_html += f"""
        <li class="menu-item">
            <a href="#{item.anchor}" class="menu-link" title="{item.title}">
                <img src="data:image/svg+xml;utf8,{icon_svg}" alt="{item.title} Icon" class="menu-icon"/>
                <span class="menu-text">{item.name}</span>
            </a>
        </li>"""
        
        return f'<ul class="menu-bar">{items_html}</ul>'
    
    def _generate_banner(self, position: str) -> str:
        """
        Generate classification banner.
        
        Args:
            position: 'top' or 'bottom'
            
        Returns:
            HTML for classification banner
        """
        banner = banner_context.get()
        if not banner:
            return ""

        pos_class = f"banner {position}"
        return f"""
        <div class="{pos_class}" banner-value="{banner}">
            {banner}
        </div>"""
    
    def _generate_favicon(self) -> str:
        """Generate favicon links."""
        icon_light = self._get_icon_content('metadata', 'favicon', 'light')
        icon_dark = self._get_icon_content('metadata', 'favicon', 'dark')
        return f"""
    <link rel="icon" href="data:image/svg+xml;utf8,{icon_light}" media="(prefers-color-scheme: light)">
    <link rel="icon" href="data:image/svg+xml;utf8,{icon_dark}" media="(prefers-color-scheme: dark)">"""
    
    def _get_icon_content(self, icon_name: str, icon_type: str = 'menu', theme: str = 'light') -> str:
        """
        Read an SVG icon file and return its content as a URL-encoded string.
        
        Args:
            icon_name: Name of icon file (without .svg extension)
            icon_type: Type of icon ('menu' or 'favicon')
            theme: 'light' or 'dark'
            
        Returns:
            URL-encoded SVG content
        """
        icon_filename = f'{icon_name}.svg' if theme == 'light' else f'{icon_name}_white.svg'
        resource_dir = resources.files("gttk.resources.icons.svg").joinpath(icon_type)
        icon_file = resource_dir.joinpath(icon_filename)
        
        try:
            with icon_file.open('r', encoding='utf-8') as f:
                return quote(f.read())
        except FileNotFoundError:
            logger.warning(f"Icon not found: {icon_file}")
            return ""
    
    def _generate_css(self) -> str:
        """Generate CSS styles using ResourceManager."""
        banner_text = banner_context.get()
        css = resource_manager.get_css(self.theme, banner_text)
        return f"<style>\n{css}\n</style>"
    
    def _generate_javascript(self) -> str:
        """Generate JavaScript for navigation using ResourceManager."""
        js = resource_manager.get_javascript()
        return f"<script>\n{js}\n</script>"