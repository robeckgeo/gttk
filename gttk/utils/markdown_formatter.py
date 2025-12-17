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
XML to Markdown and HTML Table Conversion Utilities.

This module specializes in converting hierarchical XML structures into human-readable,
flat tables, formatted as either Markdown or HTML. It mimics the visual style of
Microsoft XML Notepad, using icons and indentation to represent the XML tree
structure in a tabular format.
"""
from typing import List, Set, Dict, Any, Optional
import lxml.etree as etree
from lxml.etree import ElementBase
from gttk.utils.contexts import output_format_context
import re

SIMPLIFIABLE_CHILD_TAGS: Set[str] = {'characterstring', 'boolean', 'real', 'decimal', 'integer'}

ICONS: Dict[str, str] = {
    "attr": "＠",
    "number": "🔢",
    "date": "📅",
    "coord": "📍",
    "text": "📝",
    "uom": "📏",
    "bool": "☑️",
    "constraints": "⚠️",
    "code": "🔖",
    "url": "🔗",
    "parent": "📂",
    "default": "📝"
}

def get_icon_for_tag(tag_name: str) -> str:
    """
    Determines the icon based on the element or attribute tag name.
    """
    tag_lower = tag_name.lower()
    
    if 'date' in tag_lower or 'time' in tag_lower:
        return ICONS["date"]
    if tag_lower in ['integer', 'real', 'decimal']:
        return ICONS["number"]
    if tag_lower == 'pos':
        return ICONS["coord"]
    if tag_lower in ['uom', 'measure', 'distance']:
        return ICONS["uom"]
    if tag_lower == 'boolean':
        return ICONS["bool"]
    if 'constraints' in tag_lower or 'classification' in tag_lower:
        return ICONS["constraints"]
    if tag_lower.endswith('code') and not (tag_lower.endswith('zipcode') or tag_lower.endswith('postalcode')):
        return ICONS["code"]
    if tag_lower in ['link', 'linkage', 'url']:
        return ICONS["url"]
    if 'characterstring' in tag_lower or 'text' in tag_lower:
        return ICONS["text"]
        
    return ICONS["default"]

def format_tag_for_markdown(tag: str) -> str:
    """
    Removes the namespace from the tag for cleaner output.
    """
    return tag.rsplit('}', 1)[-1] if '}' in tag else tag

def _create_attribute_rows(attributes: Dict[str, str], indent: str, is_html: bool) -> List[str]:
    """Creates a list of markdown table rows for an element's attributes."""
    rows: List[str] = []
    attr_indent = "&nbsp;&nbsp;&nbsp;&nbsp;" if is_html else "  "
    for attr, value in attributes.items():
        attr_name = format_tag_for_markdown(attr)
        rows.append(f"| {indent}{attr_indent}{ICONS['attr']} {attr_name} | {value.replace('|', ', ')} |")
    return rows

def traverse_and_print(element: ElementBase, level: int = 0, is_html: bool = False) -> List[str]:
    """
    Recursively traverses the XML tree and returns a list of table rows.
    """
    rows: List[str] = []
    indent = "&nbsp;&nbsp;&nbsp;&nbsp;" * level if is_html else "  " * level
    tag = format_tag_for_markdown(element.tag)
    
    # Handle text with newlines properly - convert to <br> for HTML tables
    if element.text and element.text.strip():
        text = element.text.strip().replace("|", ", ")
        # Convert newlines to <br> to keep table structure intact
        text = text.replace('\n', '<br>')
    else:
        text = ""

    # Simplification for code attributes
    is_code_simplifiable = (
        tag.lower().endswith('code') and
        'codeListValue' in element.attrib
    )

    # Check for simplification: element with a single child of a specific type and no attributes on the child
    is_child_simplifiable = (
        len(element) == 1 and
        format_tag_for_markdown(element[0].tag).lower() in SIMPLIFIABLE_CHILD_TAGS and
        not element[0].attrib and not list(element[0])
    )

    if is_code_simplifiable:
        text = element.attrib['codeListValue']
        icon = get_icon_for_tag(tag)
        rows.append(f"| {indent}{icon} {tag} | {text} |")

    elif is_child_simplifiable:
        # Treat as a leaf node with the child's text
        child = element[0]
        child_tag = format_tag_for_markdown(child.tag)
        if child.text and child.text.strip():
            text = child.text.strip().replace("|", ", ")
            # Convert newlines to <br> to keep table structure intact
            text = text.replace('\n', '<br>')
        else:
            text = ""
        icon = get_icon_for_tag(child_tag) # Use child's tag for the icon
        if 'link' in tag or 'url' in tag or 'href' in tag:
            icon = ICONS['url']
        rows.append(f"| {indent}{icon} {tag} | {text} |")
        rows.extend(_create_attribute_rows(element.attrib, indent, is_html))

    elif len(element):
        # Element with children (parent node)
        rows.append(f"| {indent}{ICONS['parent']} {tag} | |")
        rows.extend(_create_attribute_rows(element.attrib, indent, is_html))

        # Recursively process children
        for child in element:
            rows.extend(traverse_and_print(child, level + 1, is_html))
            
    else:
        # Element with no children (leaf node)
        icon = get_icon_for_tag(tag)
        rows.append(f"| {indent}{icon} {tag} | {text} |")
        rows.extend(_create_attribute_rows(element.attrib, indent, is_html))

    return rows

def format_value(value: Any) -> str:
    """Formats a value for table output, applying numeric formatting where appropriate."""
    if isinstance(value, int) :
        return f"{value:,}"
    if isinstance(value, float):
        return f"{value:z,.7g}"
    val_str = str(value)
    # Prevents newlines and pipe characters from breaking the table
    val_str = val_str.replace('|', '<br>').replace('\n', '<br>')
    return val_str

def format_citation(text: Any) -> str:
    """Formats a citation tag for in-table display."""
    if not isinstance(text, str):
        return str(text)
    # Normalize surrounding whitespace and consecutive pipes to a single pipe,
    # then convert to a single <br> per separator so fields stack cleanly.
    cit_str = text.strip()
    # Remove leading/trailing pipes
    cit_str = cit_str.strip('|')
    # Collapse any runs of pipes and optional surrounding whitespace to a single pipe
    cit_str = re.sub(r"\s*\|+\s*", "|", cit_str)
    # Finally replace pipe separators with HTML line breaks for table cells
    cit_str = cit_str.replace('|', '<br>')
    return cit_str

def gdal_metadata_to_markdown_table(root: ElementBase, sample_color_map: Optional[Dict[str, str]] = None, enable_styling: bool = False) -> str:
    """
    Converts a GDALMetadata XML element into a flat Markdown table.
    """
    items_data: List[Dict[str, Any]] = []
    all_attrs: Set[str] = set()
    for item in root.findall('Item'):
        attrs = dict(item.attrib)
        all_attrs.update(attrs.keys())
        items_data.append({'attrs': attrs, 'value': item.text.strip() if item.text else ''})

    if not items_data:
        return ""

    # Define header order: 'name' first, then other attributes alphabetically, then 'value'
    other_attrs = sorted([attr for attr in all_attrs if attr != 'name'])
    headers: List[str] = []
    if 'name' in all_attrs:
        headers.append('name')
    headers.extend(other_attrs)
    headers.append('value')

    # Build table header and separator
    header_line = f"| {' | '.join(headers)} |"
    separator_line = f"|{'|'.join(['---'] * len(headers))}|"
    
    # Build table rows
    table_rows: List[str] = [header_line, separator_line]
    for item in items_data:
        # Get raw values for attributes
        raw_row_values = [item['attrs'].get(h, '') for h in headers if h != 'value']
        value_str = format_value(item.get('value', ''))
        
        # Check for color application
        sample_val = item['attrs'].get('sample')
        color = None
        if sample_val and sample_color_map and enable_styling:
            sample_val = sample_val.strip()
            color = sample_color_map.get(sample_val)

        # Build final row values with optional coloring
        final_row_values = []
        
        # Process attribute columns
        for val in raw_row_values:
            if color and val:
                final_row_values.append(f'<span style="color: {color}">{val}</span>')
            else:
                final_row_values.append(val)
        
        # Process value column
        if color and value_str:
            final_row_values.append(f'<span style="color: {color}">{value_str}</span>')
        else:
            final_row_values.append(value_str)

        table_rows.append(f"| {' | '.join(final_row_values)} |")
        
    return "\n".join(table_rows) + "\n"

def xml_to_markdown(xml_content: bytes | str, sample_color_map: Optional[Dict[str, str]] = None, enable_styling: bool = False) -> str:
    """
    Converts XML content (bytes or string) to a Markdown table.
    """
    try:
        # Determine output format from context
        is_html = output_format_context.get() == 'html'
        
        # Handle both bytes and string input
        parser = etree.XMLParser(recover=True, remove_comments=False, remove_pis=False)
        if isinstance(xml_content, str):
            # If string, let lxml handle encoding
            
            # Ensure the XML declaration matches the UTF-8 encoding we are about to use.
            # If the original string had encoding="ISO-8859-1", lxml would misinterpret
            # our UTF-8 bytes as Latin-1, causing mojibake.
            if '<?xml' in xml_content[:100]:
                import re
                xml_string_for_parsing = re.sub(
                    r'(<\?xml[^>]+encoding\s*=\s*["\'])([^"\']+)(["\'][^>]*\?>)',
                    r'\g<1>utf-8\g<3>',
                    xml_content,
                    count=1,
                    flags=re.IGNORECASE
                )
            else:
                xml_string_for_parsing = xml_content

            root = etree.fromstring(xml_string_for_parsing.encode('utf-8'), parser=parser)
        else:
            # If bytes, lxml will detect encoding from XML declaration
            root = etree.fromstring(xml_content, parser=parser)

        if format_tag_for_markdown(root.tag) == 'GDALMetadata':
            return gdal_metadata_to_markdown_table(root, sample_color_map, enable_styling)

        header = "| Name | Value |\n|---|---|"
        table_rows = traverse_and_print(root, 0, is_html)
        
        return f"{header}\n" + "\n".join(table_rows) + "\n"

    except etree.XMLSyntaxError as e:
        return f"Error parsing XML string: {e}"
    except Exception as e:
        return f"An unexpected error occurred: {e}"
