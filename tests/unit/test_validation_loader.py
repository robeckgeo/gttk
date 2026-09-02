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
Unit tests for validation TOML loader.

This module tests the TOML loading and parsing functions defined in
gttk.utils.validation.loader, including conflict detection and rule parsing.

Test coverage target: 95%+

Organization:
- Tests use temporary directories with test TOML files
- Tests verify loading, parsing, and error handling
- Conflict detection is thoroughly tested
"""

import dataclasses
import pytest
from pathlib import Path
import tempfile
import shutil

from gttk.utils.validation.loader import (
    load_validation_rules,
    parse_rule,
    get_available_products,
    get_product_metadata,
    KEY_FIELD_MAP,
    bundled_rules_dir,
)
from gttk.utils.validation.models import ValidationRule


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def temp_rules_dir():
    """Create a temporary directory for test rule files."""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir)


@pytest.fixture
def sample_toml_content():
    """Sample TOML content for testing."""
    return '''
[TestProduct]
title = "Test Product"
description = "Test product for unit testing"
author = "Test Author"
updated = "2026-01-15"

[[TestProduct.tag]]
tag = 258
description = "BitsPerSample"
data_type = "integer"
constraint = "exact"
expected = 32
comment = "Must be 32-bit"

[[TestProduct.tag]]
tag = 259
description = "Compression"
data_type = "integer"
constraint = "enum"
expected = [5, 8]

[[TestProduct.geokey]]
geokey = 1024
description = "GTModelTypeGeoKey"
data_type = "integer"
constraint = "exact"
expected = 1

[[TestProduct.gdal]]
name = "STATISTICS_MINIMUM"
description = "Minimum Value"
data_type = "float"
constraint = "range"
expected = { min = -430.0, max = 8850.0 }
'''


@pytest.fixture
def create_test_rules(temp_rules_dir, sample_toml_content):
    """Create test rule files in temporary directory."""
    rules_file = temp_rules_dir / 'test_rules.toml'
    rules_file.write_text(sample_toml_content)
    return temp_rules_dir


# =============================================================================
# load_validation_rules Tests
# =============================================================================

@pytest.mark.unit
class TestLoadValidationRules:
    """Test load_validation_rules function."""

    def test_load_rules_success(self, create_test_rules):
        """Test successful loading of validation rules."""
        rules, filename = load_validation_rules(
            create_test_rules,
            'TestProduct'
        )

        assert filename == 'test_rules.toml'
        assert 'tag' in rules
        assert 'geokey' in rules
        assert 'gdal' in rules
        assert len(rules['tag']) == 2
        assert len(rules['geokey']) == 1
        assert len(rules['gdal']) == 1

    def test_load_rules_section_filter(self, create_test_rules):
        """Test loading rules with section filter."""
        rules, _ = load_validation_rules(
            create_test_rules,
            'TestProduct',
            sections=['tag']
        )

        assert 'tag' in rules
        assert 'geokey' not in rules
        assert 'gdal' not in rules

    def test_load_rules_product_not_found(self, create_test_rules):
        """Test error when product not found."""
        with pytest.raises(ValueError) as excinfo:
            load_validation_rules(
                create_test_rules,
                'NonExistentProduct'
            )
        assert 'not found' in str(excinfo.value)
        assert 'TestProduct' in str(excinfo.value)  # Shows available

    def test_load_rules_no_toml_files(self, temp_rules_dir):
        """Test error when no TOML files exist."""
        with pytest.raises(ValueError) as excinfo:
            load_validation_rules(temp_rules_dir, 'TestProduct')
        assert 'No TOML rule files found' in str(excinfo.value)

    def test_load_rules_conflict_detection(self, temp_rules_dir):
        """Test detection of duplicate product names."""
        # Create two files with the same product
        file1 = temp_rules_dir / 'rules1.toml'
        file1.write_text('''
[DuplicateProduct]
title = "First"
[[DuplicateProduct.tag]]
tag = 258
description = "Test"
data_type = "integer"
constraint = "exact"
expected = 32
''')

        file2 = temp_rules_dir / 'rules2.toml'
        file2.write_text('''
[DuplicateProduct]
title = "Second"
[[DuplicateProduct.tag]]
tag = 259
description = "Test"
data_type = "integer"
constraint = "exact"
expected = 8
''')

        with pytest.raises(ValueError) as excinfo:
            load_validation_rules(temp_rules_dir, 'DuplicateProduct')
        assert 'found in multiple files' in str(excinfo.value)

    def test_load_rules_invalid_toml(self, temp_rules_dir):
        """Test error handling for invalid TOML syntax."""
        bad_file = temp_rules_dir / 'bad.toml'
        bad_file.write_text('this is not valid toml [[[')

        with pytest.raises(ValueError) as excinfo:
            load_validation_rules(temp_rules_dir, 'TestProduct')
        assert 'Invalid TOML syntax' in str(excinfo.value)

    def test_load_rules_validates_rule_content(self, temp_rules_dir):
        """Test that rules are validated during loading."""
        bad_rules = temp_rules_dir / 'bad_rules.toml'
        bad_rules.write_text('''
[BadProduct]
title = "Bad"
[[BadProduct.tag]]
tag = 258
description = "Test"
data_type = "invalid_type"
constraint = "exact"
expected = 32
''')

        with pytest.raises(ValueError) as excinfo:
            load_validation_rules(temp_rules_dir, 'BadProduct')
        assert 'Invalid rule' in str(excinfo.value)


# =============================================================================
# parse_rule Tests
# =============================================================================

@pytest.mark.unit
class TestParseRule:
    """Test parse_rule function."""

    def test_parse_tag_rule(self):
        """Test parsing a TIFF tag rule."""
        rule_dict = {
            'tag': 258,
            'description': 'BitsPerSample',
            'data_type': 'integer',
            'constraint': 'exact',
            'expected': 32,
            'comment': 'Must be 32-bit'
        }

        rule = parse_rule('TestProduct', 'tag', rule_dict)

        assert isinstance(rule, ValidationRule)
        assert rule.product == 'TestProduct'
        assert rule.section == 'tag'
        assert rule.key == '258'
        assert rule.key_type == 'tag'
        assert rule.description == 'BitsPerSample'
        assert rule.data_type == 'integer'
        assert rule.constraint == 'exact'
        assert rule.expected == 32
        assert rule.comment == 'Must be 32-bit'
        assert rule.optional is False

    def test_parse_geokey_rule(self):
        """Test parsing a GeoKey rule."""
        rule_dict = {
            'geokey': 3072,
            'description': 'ProjectedCRSGeoKey',
            'data_type': 'integer',
            'constraint': 'ranges',
            'expected': [
                {'min': 32601, 'max': 32660},
                {'min': 32701, 'max': 32760}
            ]
        }

        rule = parse_rule('TestProduct', 'geokey', rule_dict)

        assert rule.section == 'geokey'
        assert rule.key == '3072'
        assert rule.key_type == 'geokey'
        assert rule.constraint == 'ranges'
        assert len(rule.expected) == 2

    def test_parse_gdal_rule(self):
        """Test parsing a GDAL metadata rule."""
        rule_dict = {
            'name': 'STATISTICS_MINIMUM',
            'description': 'Minimum Elevation',
            'data_type': 'float',
            'constraint': 'range',
            'expected': {'min': -430.0, 'max': 8850.0}
        }

        rule = parse_rule('TestProduct', 'gdal', rule_dict)

        assert rule.section == 'gdal'
        assert rule.key == 'STATISTICS_MINIMUM'
        assert rule.key_type == 'name'

    def test_parse_xml_rule(self):
        """Test parsing an XML (XPath) rule."""
        rule_dict = {
            'xpath': '/mdb:MD_Metadata/mdb:contact',
            'description': 'Metadata Contact',
            'data_type': 'string',
            'constraint': 'exists'
        }

        rule = parse_rule('TestProduct', 'xml', rule_dict)

        assert rule.section == 'xml'
        assert rule.key == '/mdb:MD_Metadata/mdb:contact'
        assert rule.key_type == 'xpath'

    def test_parse_projjson_rule(self):
        """Test parsing a PROJJSON (JSONPath) rule."""
        rule_dict = {
            'jsonpath': '$.type',
            'description': 'CRS Type',
            'data_type': 'string',
            'constraint': 'exact',
            'expected': 'CompoundCRS'
        }

        rule = parse_rule('TestProduct', 'projjson', rule_dict)

        assert rule.section == 'projjson'
        assert rule.key == '$.type'
        assert rule.key_type == 'jsonpath'

    def test_parse_optional_rule(self):
        """Test parsing an optional rule."""
        rule_dict = {
            'tag': 305,
            'description': 'Software',
            'data_type': 'string',
            'constraint': 'exists',
            'optional': True
        }

        rule = parse_rule('TestProduct', 'tag', rule_dict)

        assert rule.optional is True

    def test_parse_rule_missing_key_field(self):
        """Test error when key field is missing."""
        rule_dict = {
            # Missing 'tag' field
            'description': 'Test',
            'data_type': 'integer',
            'constraint': 'exact',
            'expected': 32
        }

        with pytest.raises(KeyError) as excinfo:
            parse_rule('TestProduct', 'tag', rule_dict)
        assert 'tag' in str(excinfo.value)

    def test_parse_rule_missing_required_field(self):
        """Test error when required field is missing."""
        rule_dict = {
            'tag': 258,
            # Missing 'description'
            'data_type': 'integer',
            'constraint': 'exact',
            'expected': 32
        }

        with pytest.raises(KeyError) as excinfo:
            parse_rule('TestProduct', 'tag', rule_dict)
        assert 'description' in str(excinfo.value)

    def test_parse_rule_unknown_section(self):
        """Test error for unknown section type."""
        rule_dict = {
            'unknown_key': 123,
            'description': 'Test',
            'data_type': 'integer',
            'constraint': 'exact',
            'expected': 32
        }

        with pytest.raises(ValueError) as excinfo:
            parse_rule('TestProduct', 'unknown_section', rule_dict)
        assert 'Unknown section type' in str(excinfo.value)


# =============================================================================
# get_available_products Tests
# =============================================================================

@pytest.mark.unit
class TestGetAvailableProducts:
    """Test get_available_products function."""

    def test_get_products_multiple_files(self, temp_rules_dir):
        """Test getting products from multiple files."""
        file1 = temp_rules_dir / 'prod1.toml'
        file1.write_text('''
[Product1]
title = "Product One"
[[Product1.tag]]
tag = 1
description = "Test"
data_type = "integer"
constraint = "exists"
''')

        file2 = temp_rules_dir / 'prod2.toml'
        file2.write_text('''
[Product2]
title = "Product Two"
[[Product2.tag]]
tag = 2
description = "Test"
data_type = "integer"
constraint = "exists"

[Product3]
title = "Product Three"
[[Product3.tag]]
tag = 3
description = "Test"
data_type = "integer"
constraint = "exists"
''')

        products = get_available_products(temp_rules_dir)

        assert len(products) == 3
        assert 'Product1' in products
        assert 'Product2' in products
        assert 'Product3' in products
        assert products['Product1'] == 'prod1.toml'

    def test_get_products_empty_dir(self, temp_rules_dir):
        """Test getting products from empty directory."""
        products = get_available_products(temp_rules_dir)
        assert products == {}

    def test_get_products_conflict_raises_error(self, temp_rules_dir):
        """Test that product conflicts raise error."""
        file1 = temp_rules_dir / 'a.toml'
        file1.write_text('''
[Conflict]
title = "A"
[[Conflict.tag]]
tag = 1
description = "Test"
data_type = "integer"
constraint = "exists"
''')

        file2 = temp_rules_dir / 'b.toml'
        file2.write_text('''
[Conflict]
title = "B"
[[Conflict.tag]]
tag = 2
description = "Test"
data_type = "integer"
constraint = "exists"
''')

        with pytest.raises(ValueError) as excinfo:
            get_available_products(temp_rules_dir)
        assert 'found in multiple files' in str(excinfo.value)


# =============================================================================
# get_product_metadata Tests
# =============================================================================

@pytest.mark.unit
class TestGetProductMetadata:
    """Test get_product_metadata function."""

    def test_get_metadata_success(self, create_test_rules):
        """Test successful metadata retrieval."""
        metadata = get_product_metadata(create_test_rules, 'TestProduct')

        assert metadata['title'] == 'Test Product'
        assert metadata['description'] == 'Test product for unit testing'
        assert metadata['author'] == 'Test Author'
        assert metadata['updated'] == '2026-01-15'

    def test_get_metadata_product_not_found(self, create_test_rules):
        """Test error when product not found."""
        with pytest.raises(ValueError) as excinfo:
            get_product_metadata(create_test_rules, 'NonExistent')
        assert 'not found' in str(excinfo.value)

    def test_get_metadata_missing_fields(self, temp_rules_dir):
        """Test metadata with missing optional fields."""
        rules_file = temp_rules_dir / 'minimal.toml'
        rules_file.write_text('''
[MinimalProduct]
[[MinimalProduct.tag]]
tag = 1
description = "Test"
data_type = "integer"
constraint = "exists"
''')

        metadata = get_product_metadata(temp_rules_dir, 'MinimalProduct')

        assert metadata['title'] == 'MinimalProduct'  # Falls back to product name
        assert metadata['description'] == ''
        assert metadata['author'] == ''
        assert metadata['updated'] == ''


# =============================================================================
# KEY_FIELD_MAP Tests
# =============================================================================

@pytest.mark.unit
class TestKeyFieldMap:
    """Test KEY_FIELD_MAP constant."""

    def test_all_sections_have_mappings(self):
        """Test that all section types have key field mappings."""
        from gttk.utils.validation.models import SectionType

        for section in SectionType:
            assert section.value in KEY_FIELD_MAP, f"Missing mapping for {section.value}"

    def test_mapping_values(self):
        """Test specific mapping values."""
        assert KEY_FIELD_MAP['tag'] == 'tag'
        assert KEY_FIELD_MAP['geokey'] == 'geokey'
        assert KEY_FIELD_MAP['gdal'] == 'name'
        assert KEY_FIELD_MAP['geo'] == 'xpath'
        assert KEY_FIELD_MAP['xmp'] == 'xpath'
        assert KEY_FIELD_MAP['xml'] == 'xpath'
        assert KEY_FIELD_MAP['projjson'] == 'jsonpath'


class TestBundledRulesDir:
    """The default rules directory is located through the package, not the cwd."""

    def test_is_the_packaged_rules_directory(self):
        import gttk
        assert bundled_rules_dir() == Path(gttk.__file__).parent / 'resources' / 'rules'

    def test_is_absolute_and_holds_the_shipped_rules(self):
        rules_dir = bundled_rules_dir()
        assert rules_dir.is_absolute()
        assert rules_dir.is_dir()
        assert 'example_rules.toml' in {p.name for p in rules_dir.glob('*.toml')}

    def test_does_not_depend_on_the_working_directory(self, tmp_path, monkeypatch):
        before = bundled_rules_dir()
        monkeypatch.chdir(tmp_path)
        assert bundled_rules_dir() == before

    def test_validate_arguments_default_to_it(self):
        """
        Read off the dataclass field rather than constructing ValidateArguments,
        whose __post_init__ demands a real input file.
        """
        from gttk.utils.script_arguments import ValidateArguments
        field = {f.name: f for f in dataclasses.fields(ValidateArguments)}['rules_dir']
        assert field.default_factory() == bundled_rules_dir()


class TestInvalidRuleFilesAreNamedWhenSkipped:

    def test_get_product_metadata_names_a_file_it_skips(self, tmp_path, caplog):
        """The product listing already said which file it skipped; the metadata lookup
        skipped the same file in silence."""
        import logging
        from gttk.utils.validation.loader import get_product_metadata
        (tmp_path / 'good.toml').write_text('[X]\ntitle = "X"\n', encoding='utf-8')
        (tmp_path / 'bad.toml').write_text('this is not = toml [', encoding='utf-8')
        with caplog.at_level(logging.WARNING):
            assert get_product_metadata(tmp_path, 'X')['title'] == 'X'
        assert 'Skipping invalid TOML file: bad.toml' in caplog.text
