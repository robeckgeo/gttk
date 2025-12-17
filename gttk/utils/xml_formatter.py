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
XML Formatting and Syntax Highlighting Utilities.

This module provides core functionality for pretty-printing XML strings and
converting them into syntax-highlighted HTML. It includes a custom pretty-printer
that intelligently wraps long lines and formats attributes for readability, as well
as a tokenizer to generate styled HTML for clipboard operations or display.
"""
import logging
import re
import textwrap
import lxml.etree as etree
from pathlib import Path
from typing import Optional, Dict

logger = logging.getLogger(__name__)

# HTML escaping utility function
def html_escape(text: str) -> str:
    """Centralized HTML escaping to avoid redundant replace() calls."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

# XML token patterns
XML_PATTERNS = [
    (r'<!--.*?-->', "COMMENT"),         # XML comments (highest priority)
    (r'<[/?]?', "TAG_START"),           # Opening brackets (<, </, or <?)
    (r'[\w:-]+(?=\s|/?>|\?>|$)', "TAG_NAME"),  # Tag names (Unicode-aware with \w)
    (r'\?>', "TAG_END"),                # Processing instruction end (?>)
    (r'/>', "TAG_END"),                 # Self-closing tag end
    (r'>', "TAG_END"),                  # Regular tag end
    (r'([\w:-]+)(?==)', "ATTR_NAME"),  # Attribute names (Unicode-aware with \w)
    (r'=', "EQUALS"),                   # Equal signs
    (r'["\']', "QUOTE"),                # Quote characters (both " and ')
    (r'>[^<]+', "TEXT")                 # Text content after >
]

# Theme colors
def get_theme_colors(dark_mode: bool = False) -> dict[str, str]:
    """Get the colors for the current theme."""
    if dark_mode:
        return {
            'bg_color': "#212121",
            'text_color': "white",
            'tag_name_color': "#F07178",
            'attr_name_color': "#C792EA",
            'attr_value_color': "#C3E88D",
            'comment_color': "#ADADAD",
            'bracket_color': "#89DDFF",
            'equals_color': "#89DDFF",
            'quote_color': "#89DDFF"
        }
    else:
        return {
            'bg_color': "transparent",
            'text_color': "black",
            'tag_name_color': "#E93935",
            'attr_name_color': "#9C3EDA",
            'attr_value_color': "#196B24",
            'comment_color': "#90A4AE",
            'bracket_color': "#39ADB5",
            'equals_color': "#39ADB5",
            'quote_color': "#39ADB5"
        }

# Word wrap handling functions
def add_word_wrap_spaces(text: str) -> str:
    """Add zero-width spaces to enable word wrapping in XML."""
    # Insert a zero-width space before closing tags to cause line breaks after text content
    modified_text = re.sub(r'</', '\u200B</\u2060', text)
    # Insert no-break spaces at the end of self-closing tags to prevent line breaks
    modified_text = re.sub(r'/>', '\u2060/\u2060>', modified_text)
    return modified_text

def remove_word_wrap_spaces(text: str) -> str:
    """Remove zero-width spaces used for word wrapping in XML."""
    # Remove all zero-width spaces in a consistent order
    modified_text = text.replace('\u200B</\u2060', '</')
    modified_text = modified_text.replace('\u2060/\u2060>', '/>')
    modified_text = modified_text.replace('\u200B', '')
    modified_text = modified_text.replace('\u2060', '')
    return modified_text

def xml_to_html(text: str, colors: dict[str, str], for_tables: bool = False, sample_color_map: Optional[Dict[str, str]] = None) -> str:
    """
    Generate HTML with syntax highlighting for clipboard.
    
    Args:
        text: XML string to highlight
        colors: Theme colors dictionary
        for_tables: Boolean flag (unused but kept for API compatibility)
        sample_color_map: Optional mapping of sample index (as string) to hex color.
                         Used to colorize text content of Items with matching sample attribute.
    """
    html = textwrap.dedent(f"""<html>
    <!--StartFragment-->
    <head>
        <meta charset="utf-8">
        <style>
        .xml-content {{
            color: {colors['text_color']};
            background-color: {colors['bg_color']};
            font-family: Consolas, 'Courier New', monospace;
            font-weight: normal;
            font-size: 12pt;
            white-space: pre;
        }}
        .tag-name {{ color: {colors['tag_name_color']}; }}
        .tag-start {{ color: {colors['bracket_color']}; }}
        .tag-end {{ color: {colors['bracket_color']}; }}
        .attr-name {{ color: {colors['attr_name_color']}; }}
        .attr-value {{ color: {colors['attr_value_color']}; }}
        .comment {{ color: {colors['comment_color']}; }}
        .equals {{ color: {colors['equals_color']}; }}
        .quote {{ color: {colors['quote_color']}; }}
        .space {{ color: {colors['text_color']}; }}
        .xml-text {{ color: {colors['text_color']}; }}
        </style>
    </head>
    <body>
    <div class="xml-content">""")
    
    # Compile patterns for efficiency (use Unicode flag for \w to match international characters)
    compiled_patterns = [(re.compile(pattern, re.UNICODE), token_type) for pattern, token_type in XML_PATTERNS]
    
    # Track if we're inside a comment that spans multiple lines
    in_multiline_comment = False
    
    # Track XML element context for multi-line text content
    element_stack = []  # Stack of open elements
    in_tag_declaration = False  # True when we are inside a tag's <>
    
    # Context for sample coloring
    current_sample_attr: Optional[str] = None
    active_sample_color: Optional[str] = None
    last_attr_name: Optional[str] = None
    
    # Process each line separately
    for line in text.split('\n'):
        position = 0
        line_processed = ""
        current_opening_tag = None  # Track current opening tag being processed
        
        # Reset sample attribute tracking for each line if we are not in a multiline tag
        # (Simplified assumption: GDAL Metadata Items are usually single line)
        if not in_tag_declaration:
             current_sample_attr = None
             last_attr_name = None
        
        # Preserve leading whitespace (indentation)
        leading_whitespace_match = re.match(r'^(\s*)', line)
        leading_whitespace = leading_whitespace_match.group(1) if leading_whitespace_match else ""
        
        # Always add the leading whitespace span, even if it's empty, to preserve line structure
        html += f'<span class="space">{leading_whitespace}</span>'
        position += len(leading_whitespace)
        line_processed += leading_whitespace
        
        # Check if this line is pure text content inside an element
        stripped_line = line.strip()
        if (not in_tag_declaration and
            element_stack and
            stripped_line and
            not stripped_line.startswith('<') and
            not stripped_line.startswith('<!--') and
            '<' not in line[position:] and  # Ensure no tags later in the line
            not in_multiline_comment):
            # This is multi-line text content - treat entire remaining line as xml-text
            remaining_content = line[position:]
            if remaining_content:
                escaped_content = html_escape(remaining_content)
                if active_sample_color:
                    html += f'<span class="xml-text" style="color: {active_sample_color}">{escaped_content}</span>'
                else:
                    html += f'<span class="xml-text">{escaped_content}</span>'
            html += "\n"
            continue
        
        # If we're in a multi-line comment, check if it ends on this line
        if in_multiline_comment:
            comment_end = line.find('-->')
            if comment_end >= 0:
                # Comment ends on this line
                comment_part = line[position:comment_end + 3]
                escaped_comment = html_escape(comment_part)
                html += f'<span class="comment">{escaped_comment}</span>'
                position += len(comment_part)
                line_processed += comment_part
                in_multiline_comment = False
            else:
                # Entire line is part of the comment
                comment_part = line[position:]
                escaped_comment = html_escape(comment_part)
                html += f'<span class="comment">{escaped_comment}</span>'
                position = len(line)
                line_processed = line
        
        # Process the line character by character
        while position < len(line):
            match_found = False
            current_text = line[position:]
            
            # Check for comments first (highest priority)
            if current_text.startswith('<!--'):
                comment_end = current_text.find('-->')
                if comment_end >= 0:
                    # Comment ends on this line
                    comment = current_text[:comment_end + 3]
                    escaped_comment = html_escape(comment)
                    html += f'<span class="comment">{escaped_comment}</span>'
                    position += len(comment)
                    line_processed += comment
                else:
                    # Comment continues to next line
                    escaped_comment = html_escape(current_text)
                    html += f'<span class="comment">{escaped_comment}</span>'
                    position = len(line)
                    line_processed = line
                    in_multiline_comment = True
                match_found = True

            # Check for processing instruction start (<?)
            elif current_text.startswith('<?'):
                html += '<span class="tag-start">&lt;?</span>'
                position += 2
                line_processed += '<?'
                in_tag_declaration = True
                
                # Check for tag name immediately after <? (e.g., xml)
                tag_name_match = re.match(r'([A-Za-z0-9_:-]+)(?=\s|/?>|\?>|$)', current_text[2:])
                if tag_name_match:
                    tag_name = tag_name_match.group(1)
                    html += f'<span class="tag-name">{tag_name}</span>'
                    position += len(tag_name)
                    line_processed += tag_name
                match_found = True
                
            # Check for tag start with tag name
            elif current_text.startswith('<') and not current_text.startswith('</'):
                html += '<span class="tag-start">&lt;</span>'
                position += 1
                line_processed += '<'
                in_tag_declaration = True
                
                tag_name_match = re.match(r'([A-Za-z0-9_:-]+)(?=\s|/?>|$)', current_text[1:])
                if tag_name_match:
                    tag_name = tag_name_match.group(1)
                    html += f'<span class="tag-name">{tag_name}</span>'
                    position += len(tag_name)
                    line_processed += tag_name
                    
                    # Track opening tag (will be confirmed when we see > or />)
                    current_opening_tag = tag_name
                    current_sample_attr = None # Reset for new tag
                    last_attr_name = None
                match_found = True
                
            # Check for closing tag with tag name
            elif current_text.startswith('</'):
                html += '<span class="tag-start">&lt;/</span>'
                position += 2
                line_processed += '</'
                
                tag_name_match = re.match(r'([A-Za-z0-9_:-]+)(?=\s|/?>|$)', current_text[2:])
                if tag_name_match:
                    tag_name = tag_name_match.group(1)
                    html += f'<span class="tag-name">{tag_name}</span>'
                    position += len(tag_name)
                    line_processed += tag_name
                    
                    # Pop from element stack when closing tag is complete
                    if element_stack and element_stack[-1] == tag_name:
                        element_stack.pop()
                    
                    # Reset active color when closing a tag
                    active_sample_color = None
                match_found = True
                
            # Check for self-closing tag end (/>)
            elif current_text.startswith('/>'):
                html += '<span class="tag-end">/&gt;</span>'
                position += 2
                line_processed += '/>'
                in_tag_declaration = False
                # Self-closing tags don't create content context
                match_found = True
                
            # Check for tag end (>) and handle text content after it
            elif current_text.startswith('>'):
                html += '<span class="tag-end">&gt;</span>'
                position += 1
                line_processed += '>'
                
                # If this closes an opening tag, enter element content mode
                if current_opening_tag is not None:
                    element_stack.append(current_opening_tag)
                    in_tag_declaration = False
                    current_opening_tag = None
                    
                    # Determine active color if we have a sample map and found a sample attribute
                    if sample_color_map and current_sample_attr is not None:
                        active_sample_color = sample_color_map.get(current_sample_attr)
                    else:
                        active_sample_color = None
                
                # Check if there's text content after the >
                remaining_text = current_text[1:]
                if remaining_text and not remaining_text.startswith('<'):
                    # Find text content until the next < or end of line
                    text_match = re.match(r'([^<]+)', remaining_text)
                    if text_match:
                        text_content = text_match.group(1)
                        escaped_text = html_escape(text_content)
                        
                        if active_sample_color:
                            html += f'<span class="xml-text" style="color: {active_sample_color}">{escaped_text}</span>'
                        else:
                            html += f'<span class="xml-text">{escaped_text}</span>'  # Apply xml-text class
                            
                        position += len(text_content)
                        line_processed += text_content
                
                match_found = True
                
            # Check for equals sign (=)
            elif current_text.startswith('='):
                html += '<span class="equals">=</span>'
                position += 1
                line_processed += '='
                match_found = True

            # Check for text content not starting with > (e.g. text before a closing tag on the same line)
            elif not in_tag_declaration and not in_multiline_comment and not current_text.startswith('<') and re.match(r'([^<]+)', current_text):
                text_match = re.match(r'([^<]+)', current_text)
                if text_match:
                    text_content = text_match.group(1)
                    escaped_text = html_escape(text_content)
                    
                    if active_sample_color:
                        html += f'<span class="xml-text" style="color: {active_sample_color}">{escaped_text}</span>'
                    else:
                        html += f'<span class="xml-text">{escaped_text}</span>'
                        
                    position += len(text_content)
                    line_processed += text_content
                    match_found = True
                
            # Check for attribute names
            elif re.match(r'[A-Za-z0-9_:-]+(?=\s*=)', current_text):
                attr_name_match = re.match(r'([A-Za-z0-9_:-]+)(?=\s*=)', current_text)
                if attr_name_match:
                    attr_name = attr_name_match.group(1)
                    html += f'<span class="attr-name">{attr_name}</span>'
                    
                    # Track if we are processing a "sample" attribute
                    last_attr_name = attr_name
                        
                    position += len(attr_name)
                    line_processed += attr_name
                    match_found = True
                
            # Check for quotes to handle attribute values
            elif current_text.startswith('"') or current_text.startswith("'"):
                quote = current_text[0]
                html += f'<span class="quote">{quote}</span>'
                position += 1
                line_processed += quote
                
                remaining_text = current_text[1:]
                end_quote_pos = remaining_text.find(quote)
                
                if end_quote_pos >= 0:
                    attr_value = remaining_text[:end_quote_pos]
                    
                    # Capture sample attribute value if relevant
                    if last_attr_name == 'sample':
                        # Strip whitespace from attribute value to ensure matching against map keys
                        current_sample_attr = attr_value.strip()

                    escaped_value = html_escape(attr_value)
                    html += f'<span class="attr-value">{escaped_value}</span>'
                    position += len(attr_value)
                    line_processed += attr_value
                    
                    html += f'<span class="quote">{quote}</span>'
                    position += 1
                    line_processed += quote
                else:
                    attr_value = remaining_text
                    escaped_value = html_escape(attr_value)
                    html += f'<span class="attr-value">{escaped_value}</span>'
                    position += len(attr_value)
                    line_processed += attr_value
                match_found = True
                
            else:
                # Try the regular patterns
                for pattern, token_type in compiled_patterns:
                    match = pattern.match(current_text)
                    if match:
                        matched_text = match.group(0)
                        
                        # Special case for attribute names which use a capture group
                        if token_type == "ATTR_NAME" and match.groups():
                            matched_text = match.group(1)
                            position += match.start(1)
                            line_processed += current_text[:match.start(1)]
                        else:
                            position += match.start()
                            if match.start() > 0:
                                skipped = current_text[:match.start()]
                                escaped_skipped = html_escape(skipped)
                                html += escaped_skipped
                                line_processed += skipped
                        
                        escaped_text = html_escape(matched_text)
                        
                        # Add the token with appropriate inline style
                        if token_type == "TAG_START":
                            html += f'<span class="tag-start">{escaped_text}</span>'
                        elif token_type == "TAG_NAME":
                            html += f'<span class="tag-name">{escaped_text}</span>'
                        elif token_type == "TAG_END":
                            html += f'<span class="tag-end">{escaped_text}</span>'
                        elif token_type == "ATTR_NAME":
                            html += f'<span class="attr-name">{escaped_text}</span>'
                        elif token_type == "EQUALS":
                            html += f'<span class="equals">{escaped_text}</span>'
                        elif token_type == "COMMENT":
                            html += f'<span class="comment">{escaped_text}</span>'
                        elif token_type == "TEXT":
                            html += f'<span class="xml-text">{escaped_text}</span>'
                        else:
                            html += escaped_text
                        
                        position += len(matched_text)
                        line_processed += matched_text
                        match_found = True
                        break
            
            # If no pattern matched, check if it's whitespace
            if not match_found:
                whitespace_match = re.match(r'(\s+)', current_text)
                if whitespace_match:
                    whitespace = whitespace_match.group(1)
                    html += f'<span class="space">{whitespace}</span>'
                    position += len(whitespace)
                    line_processed += whitespace
                else:
                    char = line[position]
                    escaped_char = html_escape(char)
                    html += escaped_char
                    position += 1
                    line_processed += char
        
        # Ensure we've processed the entire line
        if len(line_processed) < len(line):
            remaining = line[len(line_processed):]
            escaped_remaining = html_escape(remaining)
            html += escaped_remaining

        html += "\n"
    
    html += "</div></body>\n<!--EndFragment-->\n</html>"
    return html

def pretty_print_xml(xml_string: str, flatten: bool = False, indent: str = '  ') -> str:
    """Custom XML pretty printer with special attribute formatting."""
    try:
        # For comments preservation, we need to avoid using lxml parser
        # which strips comments. Instead, work directly with the string
        if flatten:
            # Just return the compact XML without processing
            try:
                # Remove extra whitespace but preserve structure
                lines = xml_string.split('\n')
                compact_lines = []
                for line in lines:
                    stripped = line.strip()
                    if stripped:
                        compact_lines.append(stripped)
                return ' '.join(compact_lines)
            except Exception as e:
                return f"Error flattening XML: {e}\nOriginal XML:\n{xml_string}" if xml_string else xml_string
        
        # For pretty printing, first try to use lxml for basic formatting
        # but fall back to string processing if comments are lost
        try:
            # Test if we can preserve comments with lxml
            # Use remove_blank_text=True to force re-indentation of "flat" XML files
            parser = etree.XMLParser(strip_cdata=False, remove_comments=False, remove_blank_text=True)
            
            # Ensure the XML declaration matches the UTF-8 encoding we are about to use.
            # If the original string had encoding="ISO-8859-1", lxml would misinterpret
            # our UTF-8 bytes as Latin-1, causing mojibake.
            if '<?xml' in xml_string[:100]:
                # Update regex to handle spaces around '=' (e.g. encoding = "ISO-8859-1")
                xml_string_for_parsing = re.sub(
                    r'(<\?xml[^>]+encoding\s*=\s*["\'])([^"\']+)(["\'][^>]*\?>)',
                    r'\g<1>utf-8\g<3>',
                    xml_string,
                    count=1,
                    flags=re.IGNORECASE
                )
            else:
                xml_string_for_parsing = xml_string

            tree = etree.fromstring(xml_string_for_parsing.encode('utf-8'), parser)
            
            # Use UTF-8 to ensure XML declaration is preserved if possible, then decode
            # Only include declaration if the original string had one
            include_decl = '<?xml' in xml_string[:100]
            
            xml_bytes = etree.tostring(tree, encoding='utf-8', pretty_print=True, xml_declaration=include_decl)
            formatted_xml = xml_bytes.decode('utf-8')
            
            # Check if comments were preserved
            if '<!--' in xml_string and '<!--' not in formatted_xml:
                # Comments were lost, use string-based approach
                formatted_xml = xml_string
            
        except etree.XMLSyntaxError:
            # If parsing fails, use the original string
            formatted_xml = xml_string
        
        # Post-processing cleanup
        # Replace tabs with 2 spaces
        formatted_xml = formatted_xml.replace('\t', '  ')
        
        # Replace encoded newlines with actual newlines for readability
        # lxml may output &#xA; for newlines in some contexts (e.g. attribute normalization or specific parser settings)
        formatted_xml = formatted_xml.replace('&#xA;', '\n').replace('&#10;', '\n')
        
        # Now process it line by line to handle attributes specially
        lines = formatted_xml.split('\n')
        result_lines = []
        
        i = 0
        current_indent_len = 0 # Track indentation for attribute alignment
        
        while i < len(lines):
            line = lines[i]

            # Check if this is a line with attributes that should be reformatted
            should_reformat = (
                (len(line) > 100 and line.count('="') > 1) or  # Long lines with multiple attributes
                (line.count('="') >= 1 and any(p in line for p in ['xmlns:', 'ism:', 'xsi:', 'ntk:', 'rr:'])) or  # Specific attribute prefixes
                (re.match(r'^\s+[a-zA-Z][^<]*="', line) and line.count('="') >= 1)  # Any line starting with whitespace + attribute
            )
            
            if should_reformat:
                element_match = re.match(r'(\s*<[^\s>]+)\s+(.*)', line)
                attr_only_match = re.match(r'(\s*)([^<]\S.*)', line) if not element_match else None
                leading_whitespace = ""

                if element_match:
                    element_start = element_match.group(1)  # The element tag
                    rest = element_match.group(2)           # Rest of the line (attributes and closing)
                    
                    # Calculate indent for subsequent attributes (length of tag + 1 for space)
                    current_indent_len = len(element_start) + 1
                    
                elif attr_only_match:
                    # This is a line with just attributes (like the nas:MD_Metadata case)
                    leading_whitespace = attr_only_match.group(1)
                    rest = attr_only_match.group(2)
                    element_start = leading_whitespace  # Just the whitespace
                else:
                    result_lines.append(line)
                    current_indent_len = 0 # Reset if we hit a line we don't handle special
                    i += 1
                    continue

                is_self_closing = rest.strip().endswith('/>')

                # Extract all attributes more comprehensively to handle complex attribute patterns
                attrs = re.findall(r'([^\s=]+="[^"]*")', rest)
                
                if attrs:
                    # For attribute-only lines, we need to handle them differently
                    if attr_only_match:
                        # Calculate proper indentation: should align with first attribute after element name
                        if current_indent_len > 0:
                            indentation = ' ' * current_indent_len
                        else:
                            # Fallback if we don't have context (e.g. first line was not caught)
                            indentation = leading_whitespace + '    '

                        # Put each attribute on its own line with proper indentation
                        for j, attr in enumerate(attrs):
                            line_end = ""
                            if j == len(attrs) - 1:
                                if is_self_closing:
                                    line_end = "/>"
                                else:
                                    # Check if we need to close the tag
                                    has_closer = '>' in rest
                                    text_content = ""
                                    if has_closer:
                                        text_start = rest.find('>') + 1
                                        text_content = rest[text_start:].strip()
                                        line_end = f">{text_content}"
                                    elif text_content: # Should be empty if no closer found usually
                                        line_end = f">{text_content}"
                                        
                            result_lines.append(f"{indentation}{attr}{line_end}")
                    else:
                        # Add first attribute on the opening tag line
                        result_lines.append(f"{element_start} {attrs[0]}")
                        original_indent = len(line) - len(line.lstrip())
                        element_tag_only = element_start.strip()
                        indentation = ' ' * (original_indent + len(element_tag_only) + 1)
                        
                        # If there's only one attribute, add closing bracket to that line
                        if len(attrs) == 1:
                            if is_self_closing:
                                result_lines[-1] += "/>"
                            else:
                                text_content = ""
                                has_closer = '>' in rest
                                if has_closer:
                                    text_start = rest.find('>') + 1
                                    text_content = rest[text_start:].strip()
                                
                                # Only add closing bracket if it was present in the input or we have content
                                if has_closer:
                                    result_lines[-1] += f">{text_content}"
                                elif text_content:
                                    result_lines[-1] += f">{text_content}"
                                # If no closer and no content, we assume it continues on next line, so add nothing
                        else:
                            # Multiple attributes - process remaining ones
                            for j, attr in enumerate(attrs[1:], 1):
                                line_end = ""
                                if j == len(attrs) - 1:
                                    if is_self_closing:
                                        line_end = "/>"
                                    else:
                                        text_content = ""
                                        if '>' in rest:
                                            text_start = rest.find('>') + 1
                                            text_content = rest[text_start:].strip()
                                        line_end = f">{text_content}" if text_content else ">"
                                result_lines.append(f"{indentation}{attr}{line_end}")
                else:
                    # No attributes found, keep line as is
                    result_lines.append(line)
            else:
                # Line is short enough or doesn't have multiple attributes
                result_lines.append(line)
                
                # Still try to detect if this is an opening tag to set context for next lines
                # This handles cases where lxml splits attributes but we didn't reformat the first line
                element_match = re.match(r'(\s*<[^\s>/!]+)', line)
                if element_match and not line.strip().startswith('</'):
                     current_indent_len = len(element_match.group(1)) + 1
                else:
                     current_indent_len = 0
            
            i += 1

        return '\n'.join(result_lines)
    except Exception as e:
        # If custom formatting fails, return the original string
        print(f"Error in custom XML formatting: {e}")
        return xml_string
    
def read_xml_with_encoding_detection(xml_path: Path) -> Optional[bytes]:
    """
    Reads an XML file and returns the raw bytes.
    
    This allows XML parsers like lxml to handle encoding detection automatically
    by reading the XML declaration, which is more reliable than manual detection.
    
    Args:
        xml_path: Path to the XML file
        
    Returns:
        The XML content as bytes, or None if reading failed
    """
    try:
        # Read file in binary mode and return raw bytes
        # Let the XML parser handle encoding detection from the XML declaration
        with open(xml_path, 'rb') as f:
            xml_bytes = f.read()
        
        logger.debug(f"Successfully read XML file {xml_path.name} ({len(xml_bytes)} bytes).")
        return xml_bytes
        
    except Exception as e:
        logger.warning(f"Could not read XML file {xml_path}: {e}")
        return None

def decode_xml_bytes(xml_bytes: bytes) -> Optional[str]:
    """
    Decodes XML bytes into a string using a fallback mechanism.
    
    Args:
        xml_bytes: The XML content as bytes.
        
    Returns:
        The decoded XML content as a string, or None if decoding fails.
    """
    if not xml_bytes:
        return None
    
    encodings_to_try = ['utf-8', 'iso-8859-1', 'windows-1252', 'latin-1']
    
    for encoding in encodings_to_try:
        try:
            decoded_string = xml_bytes.decode(encoding)
            if encoding != 'utf-8':
                logger.warning(f"UTF-8 decoding failed, successfully decoded using '{encoding}'.")
            return decoded_string
        except UnicodeDecodeError:
            continue
            
    logger.error(f"Failed to decode XML bytes with any of the attempted encodings: {', '.join(encodings_to_try)}")
    return None