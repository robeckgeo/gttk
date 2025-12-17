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
GUI-specific XML and Clipboard Helper Functions.

This module contains utilities that depend on PyQt6 and are specifically designed
for the GUI components of the GeoTIFF ToolKit. It provides the `XmlHighlighter`
class for real-time syntax highlighting in a QTextEdit widget and functions to
copy richly formatted HTML to the system clipboard.

Classes:
    XmlHighlighter: A QSyntaxHighlighter for styling XML content.
"""
import re
import subprocess
import tempfile
import os
from PyQt6.QtCore import QMimeData
from PyQt6.QtGui import QGuiApplication, QTextCharFormat, QColor, QSyntaxHighlighter
from .xml_formatter import get_theme_colors, xml_to_html

def copy_to_clipboard(text, colors):
    """Copy text to clipboard with HTML formatting."""
    # Set plain text to clipboard using Qt
    clipboard = QGuiApplication.clipboard()
    clipboard.setText(text)
    
    # Generate HTML with syntax highlighting
    html = xml_to_html(text, colors)
    
    # Create the CF_HTML format with proper headers
    header = "Version:0.9\r\n"
    header += "StartHTML:AAAAAAAA\r\n"
    header += "EndHTML:BBBBBBBB\r\n"
    header += "StartFragment:CCCCCCCC\r\n"
    header += "EndFragment:DDDDDDDD\r\n"
    
    # Ensure consistent line endings in the HTML content
    html = html.replace('\n', '\r\n')
    
    # Combine header and HTML
    html_with_headers = header + html
    
    # Calculate the offsets
    start_html = len(header)
    start_fragment = html_with_headers.find('<!--StartFragment-->') + len('<!--StartFragment-->')
    end_fragment = html_with_headers.find('<!--EndFragment-->')
    end_html = len(html_with_headers)
    
    # Update the header values with the correct offsets
    html_with_headers = html_with_headers.replace("StartHTML:AAAAAAAA", f"StartHTML:{start_html:08d}")
    html_with_headers = html_with_headers.replace("EndHTML:BBBBBBBB", f"EndHTML:{end_html:08d}")
    html_with_headers = html_with_headers.replace("StartFragment:CCCCCCCC", f"StartFragment:{start_fragment:08d}")
    html_with_headers = html_with_headers.replace("EndFragment:DDDDDDDD", f"EndFragment:{end_fragment:08d}")
    
    try:
        # Create temporary files for HTML and plain text
        with tempfile.NamedTemporaryFile(delete=False, suffix='.html', mode='wb') as f:
            f.write(html_with_headers.encode('utf-8'))
            html_file = f.name
            
        with tempfile.NamedTemporaryFile(delete=False, suffix='.txt', mode='wb') as f:
            f.write(text.encode('utf-8'))
            text_file = f.name
        
        # Use PowerShell to set both formats to the clipboard
        ps_script = f"""
        Add-Type -AssemblyName System.Windows.Forms
        
        # Create a data object
        $dataObject = New-Object System.Windows.Forms.DataObject
        
        # Add plain text format
        $plainText = [System.IO.File]::ReadAllText("{text_file}", [System.Text.Encoding]::UTF8)
        $dataObject.SetData([System.Windows.Forms.DataFormats]::Text, $plainText)
        $dataObject.SetData([System.Windows.Forms.DataFormats]::UnicodeText, $plainText)
        
        # Add HTML format
        $htmlFormat = [System.Windows.Forms.DataFormats]::Html
        $htmlData = [System.IO.File]::ReadAllText("{html_file}", [System.Text.Encoding]::UTF8)
        $dataObject.SetData($htmlFormat, $htmlData)
        
        # Set the clipboard data with all formats
        [System.Windows.Forms.Clipboard]::SetDataObject($dataObject, $true)
        """
        
        # Execute the PowerShell script
        subprocess.run(['powershell', '-Command', ps_script], check=True)
        
        # Clean up the temporary files
        os.unlink(html_file)
        os.unlink(text_file)
        
        return True
    except Exception:
        # Fall back to Qt's clipboard system
        mime_data = QMimeData()
        mime_data.setText(text)
        mime_data.setHtml(html)
        clipboard = QGuiApplication.clipboard()
        clipboard.setMimeData(mime_data)
        return False

# XML Highlighter class
class XmlHighlighter(QSyntaxHighlighter):
    """XML syntax highlighter with Material Theme Light/Dark colors."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.highlighting_rules = []
        self.dark_mode = False
        
        # Initialize with light mode colors
        self.setup_highlighting_rules()
    
    def set_dark_mode(self, enabled):
        """Switch between light and dark mode colors."""
        self.dark_mode = enabled
        self.setup_highlighting_rules()
        self.rehighlight()
    
    def setup_highlighting_rules(self):
        """Set up the highlighting rules based on current mode."""
        self.highlighting_rules = []
        
        colors = get_theme_colors(self.dark_mode)
        
        # 1. Tag brackets (all brackets including < > and />)
        tag_bracket_format = QTextCharFormat()
        tag_bracket_format.setForeground(QColor(colors['bracket_color']))
        self.highlighting_rules.append((r'<', tag_bracket_format))       # Opening bracket
        self.highlighting_rules.append((r'>', tag_bracket_format))       # Closing bracket
        self.highlighting_rules.append((r'/', tag_bracket_format))       # Forward slash in tags
        
        # 2. XML comments (highest priority - applied last to override other formatting)
        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor(colors['comment_color']))
        # Use a non-greedy pattern that captures the entire comment including < and >
        self.highlighting_rules.append((r'<!--.*?-->', comment_format))
        
        # 3. Tag names - must come after brackets
        tag_name_format = QTextCharFormat()
        tag_name_format.setForeground(QColor(colors['tag_name_color']))
        # Match tag names directly without using lookbehind
        # We'll use a custom approach in the highlightBlock method
        
        # 5. Attribute names
        attr_name_format = QTextCharFormat()
        attr_name_format.setForeground(QColor(colors['attr_name_color']))
        self.highlighting_rules.append((r'[A-Za-z0-9_][A-Za-z0-9_:-]*(?=\s*=)', attr_name_format))
        
        # 6. Equal signs
        equals_format = QTextCharFormat()
        equals_format.setForeground(QColor(colors['equals_color']))
        self.highlighting_rules.append((r'=', equals_format))
        
        # 7. Attribute values - content between quotes (must come before quotes)
        attr_value_format = QTextCharFormat()
        attr_value_format.setForeground(QColor(colors['attr_value_color']))
        # Use a simpler approach for attribute values
        
        self.highlighting_rules.append((r'"[^"]*"', attr_value_format))  # Double quotes
        self.highlighting_rules.append((r"'[^']*'", attr_value_format))  # Single quotes
        
        # 8. Quote characters (must come after attribute values)
        quote_format = QTextCharFormat()
        quote_format.setForeground(QColor(colors['quote_color']))
        # We need to be careful with the order here to avoid overriding attribute values
        # First highlight the opening and closing quotes
        self.highlighting_rules.append((r'"', quote_format))  # Double quotes
        self.highlighting_rules.append((r"'", quote_format))  # Single quotes
        
        # 9. Text content between tags
        text_format = QTextCharFormat()
        text_format.setForeground(QColor(colors['text_color']))
        self.highlighting_rules.append((r'(?<=>)[^<]+', text_format))  # Text after > (using positive lookbehind)
        
        # 10. XML declarations
        declaration_format = QTextCharFormat()
        declaration_format.setForeground(QColor(colors['tag_name_color']))
        self.highlighting_rules.append((r'<\?.*?\?>', declaration_format))
    
    def highlightBlock(self, text):
        """Apply syntax highlighting to the given block of text."""
        # First apply the standard rules
        for pattern, format in self.highlighting_rules:
            for match in re.finditer(pattern, text):
                start = match.start()
                length = match.end() - match.start()
                self.setFormat(start, length, format)
        
        # Custom handling for tag names
        colors = get_theme_colors(self.dark_mode)
        tag_name_format = QTextCharFormat()
        tag_name_format.setForeground(QColor(colors['tag_name_color']))
        
        # Find opening tag names
        for match in re.finditer(r'<([A-Za-z0-9_][A-Za-z0-9_:-]*)', text):
            # The tag name starts at position 1 (after the '<')
            # We need to calculate the absolute position by adding match.start() to the relative position
            start = match.start() + 1  # +1 to skip the '<' character
            length = len(match.group(1))
            self.setFormat(start, length, tag_name_format)
        
        # Find all closing tags and highlight the tag names
        closing_tag_pattern = re.compile(r'</([^>\s]+)')
        for match in closing_tag_pattern.finditer(text):
            tag_name = match.group(1)
            start = match.start() + 2  # +2 to skip the '</' characters
            length = len(tag_name)
            self.setFormat(start, length, tag_name_format)
