#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit Tests for xml_formatter.py

Comprehensive test coverage for XML formatting and syntax highlighting including:
- HTML escaping and character safety
- Theme color management
- Word wrap utility functions
- XML to HTML syntax highlighting conversion
- XML pretty printing with attribute formatting
- XML file reading with encoding detection
- Bytes decoding with encoding fallback

Target: 44 tests with 80%+ code coverage
"""

import pytest

from gttk.utils.xml_formatter import (
    html_escape,
    get_theme_colors,
    add_word_wrap_spaces,
    remove_word_wrap_spaces,
    xml_to_html,
    pretty_print_xml,
    read_xml_with_encoding_detection,
    decode_xml_bytes
)

# ==============================================================================
# FIXTURES
# ==============================================================================

@pytest.fixture
def light_theme_colors():
    """Light mode theme colors fixture."""
    return get_theme_colors(dark_mode=False)

@pytest.fixture
def dark_theme_colors():
    """Dark mode theme colors fixture."""
    return get_theme_colors(dark_mode=True)

@pytest.fixture
def sample_xml():
    """Sample XML for testing."""
    return '''<?xml version="1.0" encoding="UTF-8"?>
<root>
  <element attr="value">text</element>
  <!-- Comment -->
  <self-closing/>
</root>'''

# ==============================================================================
# CATEGORY 1: HTML ESCAPING TESTS (5 TESTS)
# ==============================================================================

class TestHtmlEscape:
    """Test HTML character escaping."""
    
    def test_escape_ampersand(self):
        """Ampersand (&) should become &amp;"""
        assert html_escape("A & B") == "A &amp; B"
    
    def test_escape_less_than(self):
        """Less-than (<) should become &lt;"""
        assert html_escape("A < B") == "A &lt; B"
    
    def test_escape_greater_than(self):
        """Greater-than (>) should become &gt;"""
        assert html_escape("A > B") == "A &gt; B"
    
    def test_escape_all_special_chars(self):
        """All special characters escaped in combination."""
        assert html_escape('<tag attr="value">text & more</tag>') == \
               '&lt;tag attr="value"&gt;text &amp; more&lt;/tag&gt;'
    
    def test_escape_empty_string(self):
        """Empty string returns empty string."""
        assert html_escape("") == ""

# ==============================================================================
# CATEGORY 2: THEME COLOR TESTS (3 TESTS)
# ==============================================================================

class TestThemeColors:
    """Test theme color dictionary retrieval."""
    
    def test_light_mode_colors(self):
        """Light mode returns correct color palette."""
        colors = get_theme_colors(dark_mode=False)
        
        assert colors['bg_color'] == "transparent"
        assert colors['text_color'] == "black"
        assert colors['tag_name_color'] == "#E93935"
        assert colors['attr_name_color'] == "#9C3EDA"
        assert colors['bracket_color'] == "#39ADB5"
        # Verify all required keys present
        assert all(key in colors for key in [
            'bg_color', 'text_color', 'tag_name_color', 'attr_name_color',
            'attr_value_color', 'comment_color', 'bracket_color', 'equals_color', 'quote_color'
        ])
    
    def test_dark_mode_colors(self):
        """Dark mode returns correct color palette."""
        colors = get_theme_colors(dark_mode=True)
        
        assert colors['bg_color'] == "#212121"
        assert colors['text_color'] == "white"
        assert colors['tag_name_color'] == "#F07178"
        assert colors['attr_name_color'] == "#C792EA"
        assert colors['bracket_color'] == "#89DDFF"
    
    def test_default_is_light_mode(self):
        """Default (no argument) returns light mode colors."""
        colors_default = get_theme_colors()
        colors_light = get_theme_colors(dark_mode=False)
        
        assert colors_default == colors_light

# ==============================================================================
# CATEGORY 3: WORD WRAP UTILITIES TESTS (4 TESTS)
# ==============================================================================

class TestWordWrapUtilities:
    """Test zero-width space insertion/removal for word wrapping."""
    
    def test_add_word_wrap_spaces_closing_tags(self):
        """Insert zero-width spaces before closing tags."""
        xml = "<tag>content</tag>"
        result = add_word_wrap_spaces(xml)
        
        # Should insert \u200B before </ and \u2060 after <
        assert '\u200B' in result
        assert result == "<tag>content\u200B</\u2060tag>"
    
    def test_add_word_wrap_spaces_self_closing_tags(self):
        """Insert no-break spaces in self-closing tags."""
        xml = '<tag attr="value"/>'
        result = add_word_wrap_spaces(xml)
        
        # Should insert no-break spaces around /> to prevent breaking
        assert '\u2060' in result
        assert result == '<tag attr="value"\u2060/\u2060>'
    
    def test_remove_word_wrap_spaces_reverses_add(self):
        """remove_word_wrap_spaces should reverse add_word_wrap_spaces."""
        xml = "<root><child attr=\"val\"/>text</child></root>"
        
        modified = add_word_wrap_spaces(xml)
        restored = remove_word_wrap_spaces(modified)
        
        assert restored == xml
    
    def test_remove_word_wrap_spaces_all_variants(self):
        """Remove all zero-width character variants."""
        # Manually insert various zero-width chars
        text_with_spaces = "text\u200Bmore\u2060end"
        result = remove_word_wrap_spaces(text_with_spaces)
        
        assert result == "textmoreend"
        assert '\u200B' not in result
        assert '\u2060' not in result

# ==============================================================================
# CATEGORY 4: XML TO HTML CONVERSION TESTS (12 TESTS)
# ==============================================================================

class TestXmlToHtml:
    """Test XML to HTML syntax highlighting conversion."""
    
    def test_basic_element_highlighting(self, light_theme_colors):
        """Simple element gets proper tag/text highlighting."""
        xml = "<root>text content</root>"
        html = xml_to_html(xml, light_theme_colors)
        
        # Verify HTML structure
        assert '<html>' in html
        assert '<!--StartFragment-->' in html
        assert '<div class="xml-content">' in html
        assert '</div></body>' in html
        
        # Verify tag highlighting
        assert 'class="tag-start"' in html
        assert 'class="tag-name"' in html
        assert 'class="tag-end"' in html
        assert 'class="xml-text"' in html
        
        # Verify proper escaping
        assert '&lt;' in html  # <
        assert '&gt;' in html  # >
    
    def test_xml_declaration_highlighting(self, light_theme_colors):
        """XML declaration (<?xml ... ?>) highlighted correctly."""
        xml = '<?xml version="1.0" encoding="UTF-8"?>\n<root/>'
        html = xml_to_html(xml, light_theme_colors)
        
        # Verify processing instruction highlighting
        assert '&lt;?' in html  # <?
        assert '?&gt;' in html  # ?>
        assert 'xml' in html  # tag name
    
    def test_attributes_highlighting(self, light_theme_colors):
        """Element attributes highlighted with proper colors."""
        xml = '<element attr1="value1" attr2="value2"/>'
        html = xml_to_html(xml, light_theme_colors)
        
        # Verify attribute highlighting
        assert 'class="attr-name"' in html
        assert 'class="attr-value"' in html
        assert 'class="equals"' in html
        assert 'class="quote"' in html
    
    def test_comment_highlighting(self, light_theme_colors):
        """XML comments highlighted correctly."""
        xml = '<!-- This is a comment -->\n<root/>'
        html = xml_to_html(xml, light_theme_colors)
        
        assert 'class="comment"' in html
        assert 'This is a comment' in html
    
    def test_multiline_comment_handling(self, light_theme_colors):
        """Multi-line comments handled correctly."""
        xml = '''<!--
        Multi-line
        comment
        -->
        <root/>'''
        html = xml_to_html(xml, light_theme_colors)
        
        assert 'class="comment"' in html
        assert 'Multi-line' in html
    
    def test_text_content_with_special_chars(self, light_theme_colors):
        """Text content with special characters escaped properly."""
        xml = '<tag>Text with &amp; &lt; &gt; symbols</tag>'
        html = xml_to_html(xml, light_theme_colors)
        
        # Should double-escape for HTML display
        assert '&amp;amp;' in html  # & -> &amp; -> &amp;amp;
        assert '&amp;lt;' in html   # < already escaped in XML
    
    def test_self_closing_tags(self, light_theme_colors):
        """Self-closing tags (<tag/>) highlighted correctly."""
        xml = '<element attr="value"/>'
        html = xml_to_html(xml, light_theme_colors)
        
        assert '/&gt;' in html  # /> escaped
        assert 'class="tag-end"' in html
    
    def test_nested_elements(self, light_theme_colors):
        """Nested XML elements maintain proper highlighting."""
        xml = '''<root>
  <parent>
    <child>text</child>
  </parent>
</root>'''
        html = xml_to_html(xml, light_theme_colors)
        
        # All element names should be highlighted
        assert html.count('class="tag-name"') >= 6  # 3 tags × 2 (open/close)
        assert 'root' in html
        assert 'parent' in html
        assert 'child' in html
    
    def test_indentation_preservation(self, light_theme_colors):
        """Leading whitespace/indentation preserved in HTML."""
        xml = '''<root>
  <child/>
    <nested/>
</root>'''
        html = xml_to_html(xml, light_theme_colors)
        
        # Indentation should be wrapped in space spans
        assert 'class="space"' in html
    
    def test_sample_color_map_integration(self, light_theme_colors):
        """Sample color map applies custom colors to matching items."""
        xml = '<Item sample="0">Band 1</Item><Item sample="1">Band 2</Item>'
        sample_colors = {'0': '#FF0000', '1': '#00FF00'}
        
        html = xml_to_html(xml, light_theme_colors, sample_color_map=sample_colors)
        
        # Text content should have inline color styles
        assert 'style="color: #FF0000"' in html
        assert 'style="color: #00FF00"' in html
    
    def test_empty_xml_string(self, light_theme_colors):
        """Empty XML string produces valid HTML structure."""
        html = xml_to_html("", light_theme_colors)
        
        assert '<html>' in html
        assert '</html>' in html
        assert '<div class="xml-content">' in html
    
    def test_malformed_xml_no_crash(self, light_theme_colors):
        """Malformed XML doesn't crash, attempts highlighting anyway."""
        xml = "<unclosed><tag>content"
        
        # Should not raise exception
        html = xml_to_html(xml, light_theme_colors)
        
        assert '<html>' in html
        assert 'unclosed' in html

# ==============================================================================
# CATEGORY 5: XML PRETTY PRINTING TESTS (12 TESTS)
# ==============================================================================

class TestPrettyPrintXml:
    """Test XML pretty printing and formatting."""
    
    def test_basic_formatting(self):
        """Simple XML formatted with proper indentation."""
        xml = "<root><child>text</child></root>"
        formatted = pretty_print_xml(xml)
        
        # Should have newlines and indentation
        assert '\n' in formatted
        assert '<root>' in formatted
        assert '  <child>' in formatted  # 2-space indent
        assert '</root>' in formatted
    
    def test_flatten_mode(self):
        """Flatten mode removes extra whitespace."""
        xml = """<root>
          <child>text</child>
        </root>"""
        
        flattened = pretty_print_xml(xml, flatten=True)
        
        # Should be single line (or minimal whitespace)
        assert flattened.count('\n') <= 1
        assert '<root>' in flattened
        assert '<child>text</child>' in flattened
    
    def test_attribute_wrapping_long_line(self):
        """Long lines with multiple attributes wrapped properly."""
        xml = '<element attr1="value1" attr2="value2" attr3="value3" attr4="very_long_value_that_makes_line_exceed_100_chars"/>'
        formatted = pretty_print_xml(xml)
        
        # Attributes should be on separate lines
        assert formatted.count('\n') > 1
        assert 'attr1=' in formatted
        assert 'attr2=' in formatted
    
    def test_namespace_attribute_formatting(self):
        """Namespace attributes (xmlns:) formatted on separate lines."""
        xml = '<root xmlns:gml="http://www.opengis.net/gml" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"/>'
        formatted = pretty_print_xml(xml)
        
        # Namespace attrs should trigger line wrapping
        assert 'xmlns:gml=' in formatted
        assert 'xmlns:xsi=' in formatted
    
    def test_comment_preservation(self):
        """XML comments preserved during formatting."""
        xml = '<!-- Important comment --><root>text</root>'
        formatted = pretty_print_xml(xml)
        
        assert '<!-- Important comment -->' in formatted
    
    def test_xml_declaration_preservation(self):
        """XML declaration preserved when present."""
        xml = '<?xml version="1.0" encoding="UTF-8"?>\n<root/>'
        formatted = pretty_print_xml(xml)
        
        # lxml may use single or double quotes
        assert '<?xml version' in formatted
        assert 'encoding' in formatted
        assert '<root' in formatted
    
    def test_encoding_conversion_iso_to_utf8(self):
        """ISO-8859-1 encoding converted to UTF-8 for parsing."""
        xml = '<?xml version="1.0" encoding="ISO-8859-1"?>\n<root/>'
        formatted = pretty_print_xml(xml)
        
        # lxml should handle encoding correctly
        assert '<root' in formatted
    
    def test_encoding_with_spaces(self):
        """Encoding attribute with spaces around = handled."""
        xml = '<?xml version="1.0" encoding = "ISO-8859-1" ?>\n<root/>'
        formatted = pretty_print_xml(xml)
        
        # Should parse without error
        assert '<root' in formatted
    
    def test_cdata_preservation(self):
        """CDATA sections preserved during formatting."""
        xml = '<root><![CDATA[Special content with <tags>]]></root>'
        formatted = pretty_print_xml(xml)
        
        # CDATA should be preserved (lxml with strip_cdata=False)
        # Note: lxml may or may not preserve CDATA depending on parser settings
        assert 'Special content' in formatted
    
    def test_empty_xml_string(self):
        """Empty XML string handled gracefully."""
        formatted = pretty_print_xml("")
        assert formatted == ""
    
    def test_malformed_xml_fallback(self):
        """Malformed XML returns original string."""
        xml = "<unclosed><tag>content"
        formatted = pretty_print_xml(xml)
        
        # Should return original since parsing fails
        assert formatted == xml
    
    def test_self_closing_tag_formatting(self):
        """Self-closing tags formatted correctly."""
        xml = '<root attr="value"/>'
        formatted = pretty_print_xml(xml)
        
        assert '/>' in formatted
        assert 'attr="value"' in formatted

# ==============================================================================
# CATEGORY 6: FILE READING & DECODING TESTS (8 TESTS)
# ==============================================================================

class TestXmlFileReading:
    """Test XML file reading with encoding detection."""
    
    def test_read_utf8_xml(self, tmp_path):
        """Read UTF-8 encoded XML file."""
        xml_file = tmp_path / "test_utf8.xml"
        xml_content = '<?xml version="1.0" encoding="UTF-8"?>\n<root>Test</root>'
        xml_file.write_bytes(xml_content.encode('utf-8'))
        
        result = read_xml_with_encoding_detection(xml_file)
        
        assert result is not None
        assert isinstance(result, bytes)
        assert b'<root>Test</root>' in result
    
    def test_read_iso_8859_1_xml(self, tmp_path):
        """Read ISO-8859-1 encoded XML file."""
        xml_file = tmp_path / "test_latin1.xml"
        xml_content = '<?xml version="1.0" encoding="ISO-8859-1"?>\n<root>Tëst</root>'
        xml_file.write_bytes(xml_content.encode('iso-8859-1'))
        
        result = read_xml_with_encoding_detection(xml_file)
        
        assert result is not None
        assert isinstance(result, bytes)
    
    def test_read_nonexistent_file(self, tmp_path):
        """Nonexistent file returns None with warning."""
        nonexistent = tmp_path / "nonexistent.xml"
        
        result = read_xml_with_encoding_detection(nonexistent)
        
        assert result is None
    
    def test_read_binary_file(self, tmp_path):
        """Binary (non-XML) file read as bytes."""
        binary_file = tmp_path / "test.bin"
        binary_file.write_bytes(b'\x00\x01\x02\x03')
        
        result = read_xml_with_encoding_detection(binary_file)
        
        # Should still read bytes (caller handles validation)
        assert result == b'\x00\x01\x02\x03'


class TestXmlBytesDecoding:
    """Test XML bytes decoding with encoding fallback."""
    
    def test_decode_utf8_bytes(self):
        """UTF-8 bytes decoded successfully."""
        xml_bytes = '<?xml version="1.0"?>\n<root>Test</root>'.encode('utf-8')
        
        result = decode_xml_bytes(xml_bytes)
        
        assert result is not None
        assert '<root>Test</root>' in result
    
    def test_decode_iso_8859_1_bytes(self):
        """ISO-8859-1 bytes decoded with fallback."""
        # Create bytes that are invalid UTF-8 but valid Latin-1
        xml_bytes = '<?xml version="1.0"?>\n<root>Tëst</root>'.encode('iso-8859-1')
        
        result = decode_xml_bytes(xml_bytes)
        
        assert result is not None
        assert 'Tëst' in result or 'Test' in result  # Depending on encoding detection
    
    def test_decode_windows_1252_bytes(self):
        """Windows-1252 bytes decoded with fallback."""
        xml_bytes = '<?xml version="1.0"?>\n<root>Test™</root>'.encode('windows-1252')
        
        result = decode_xml_bytes(xml_bytes)
        
        assert result is not None
        assert 'Test' in result
    
    def test_decode_empty_bytes(self):
        """Empty bytes returns None."""
        result = decode_xml_bytes(b'')
        
        assert result is None

# ==============================================================================
# RUN TESTS
# ==============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
