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
Unit tests for validation constraint functions.

This module tests all constraint validation functions defined in
gttk.utils.validation.constraints, including exact, enum, regex,
range, ranges, exists, and forbidden.

Test coverage target: 95%+

Organization:
- Each constraint function gets its own test class
- Tests verify pass/fail cases
- Edge cases and type conversions are tested
"""

import pytest
from gttk.utils.validation.constraints import (
    validate_exact,
    validate_enum,
    validate_regex,
    validate_range,
    validate_ranges,
    validate_exists,
    validate_forbidden,
    apply_constraint,
)


# =============================================================================
# validate_exact Tests
# =============================================================================

@pytest.mark.unit
class TestValidateExact:
    """Test validate_exact constraint function."""

    def test_exact_match_integer(self):
        """Test exact match with integers."""
        assert validate_exact(32, 32) is True
        assert validate_exact(32, 64) is False

    def test_exact_match_string(self):
        """Test exact match with strings."""
        assert validate_exact('hello', 'hello') is True
        assert validate_exact('hello', 'world') is False

    def test_exact_match_float(self):
        """Test exact match with floats."""
        assert validate_exact(3.14, 3.14) is True
        assert validate_exact(3.14, 3.15) is False

    def test_exact_match_boolean(self):
        """Test exact match with booleans."""
        assert validate_exact(True, True) is True
        assert validate_exact(False, False) is True
        assert validate_exact(True, False) is False

    def test_exact_match_list(self):
        """Test exact match with lists (e.g., BitsPerSample for multi-band)."""
        assert validate_exact([8, 8, 8], [8, 8, 8]) is True
        assert validate_exact([8, 8, 8, 8], [8, 8, 8, 8]) is True
        assert validate_exact([8, 8, 8], [8, 8, 16]) is False
        assert validate_exact([8, 8, 8], [8, 8]) is False

    def test_exact_match_numeric_conversion(self):
        """Test exact match with numeric type conversion."""
        # String to int comparison
        assert validate_exact('32', 32) is True
        # Int to float comparison
        assert validate_exact(32, 32.0) is True
        # String to float comparison
        assert validate_exact('3.14', 3.14) is True

    def test_exact_match_none(self):
        """Test exact match with None values."""
        assert validate_exact(None, None) is True
        assert validate_exact(None, 32) is False
        assert validate_exact(32, None) is False


# =============================================================================
# validate_enum Tests
# =============================================================================

@pytest.mark.unit
class TestValidateEnum:
    """Test validate_enum constraint function."""

    def test_enum_integer_in_list(self):
        """Test enum with integer in list."""
        assert validate_enum(5, [5, 8, 50000]) is True
        assert validate_enum(8, [5, 8, 50000]) is True
        assert validate_enum(1, [5, 8, 50000]) is False

    def test_enum_string_in_list(self):
        """Test enum with string in list."""
        assert validate_enum('DEFLATE', ['LZW', 'DEFLATE', 'ZSTD']) is True
        assert validate_enum('JPEG', ['LZW', 'DEFLATE', 'ZSTD']) is False

    def test_enum_numeric_conversion(self):
        """Test enum with numeric type conversion."""
        # String matches numeric in list
        assert validate_enum('5', [5, 8, 50000]) is True
        # Float matches int in list
        assert validate_enum(5.0, [5, 8, 50000]) is True

    def test_enum_invalid_expected_type(self):
        """Test enum with invalid expected type raises error."""
        with pytest.raises(ValueError) as excinfo:
            validate_enum(5, 'not a list')
        assert 'requires a list' in str(excinfo.value)

    def test_enum_empty_list(self):
        """Test enum with empty list."""
        assert validate_enum(5, []) is False

    def test_enum_tuple_expected(self):
        """Test enum with tuple instead of list."""
        assert validate_enum(5, (5, 8, 50000)) is True


# =============================================================================
# validate_regex Tests
# =============================================================================

@pytest.mark.unit
class TestValidateRegex:
    """Test validate_regex constraint function."""

    def test_regex_datetime_pattern(self):
        """Test regex with TIFF DateTime pattern."""
        pattern = r'^\d{4}:\d{2}:\d{2} \d{2}:\d{2}:\d{2}$'
        assert validate_regex('2025:01:15 12:30:00', pattern) is True
        assert validate_regex('01/15/2025', pattern) is False
        assert validate_regex('2025-01-15T12:30:00', pattern) is False

    def test_regex_iso_date_pattern(self):
        """Test regex with ISO 8601 date pattern."""
        pattern = r'^\d{4}-\d{2}-\d{2}$'
        assert validate_regex('2025-01-15', pattern) is True
        assert validate_regex('01/15/2025', pattern) is False

    def test_regex_filename_pattern(self):
        """Test regex with DGED5 filename pattern."""
        pattern = r'^U_.*_20km_.*_GeoData_.*(?:DSM|DTM).*_\d{2}$'
        assert validate_regex('U_N32E112_20km_E112N32_GeoData_DSM_01', pattern) is True
        assert validate_regex('random_filename', pattern) is False

    def test_regex_naip_attribution(self):
        """Test regex with NAIP attribution pattern."""
        pattern = r'.*USDA Farm Service Agency.*National Agriculture Imagery Program.*NAIP.*'
        valid_desc = 'Image created by USDA Farm Service Agency under the National Agriculture Imagery Program (NAIP)'
        assert validate_regex(valid_desc, pattern) is True
        assert validate_regex('Some other description', pattern) is False

    def test_regex_none_value(self):
        """Test regex with None value."""
        assert validate_regex(None, r'.*') is False

    def test_regex_numeric_value_converted(self):
        """Test regex with numeric value (converted to string)."""
        assert validate_regex(12345, r'^\d+$') is True

    def test_regex_invalid_pattern(self):
        """Test regex with invalid pattern raises error."""
        with pytest.raises(ValueError) as excinfo:
            validate_regex('test', r'[invalid(regex')
        assert 'Invalid regex pattern' in str(excinfo.value)


# =============================================================================
# validate_range Tests
# =============================================================================

@pytest.mark.unit
class TestValidateRange:
    """Test validate_range constraint function."""

    def test_range_within_bounds(self):
        """Test range with value within bounds."""
        assert validate_range(127.5, {'min': 0, 'max': 255}) is True
        assert validate_range(0, {'min': 0, 'max': 255}) is True
        assert validate_range(255, {'min': 0, 'max': 255}) is True

    def test_range_outside_bounds(self):
        """Test range with value outside bounds."""
        assert validate_range(-1, {'min': 0, 'max': 255}) is False
        assert validate_range(256, {'min': 0, 'max': 255}) is False

    def test_range_elevation_bounds(self):
        """Test range with elevation bounds."""
        spec = {'min': -430.0, 'max': 8850.0}
        assert validate_range(127.5, spec) is True
        assert validate_range(-430.0, spec) is True
        assert validate_range(8850.0, spec) is True
        assert validate_range(-9999, spec) is False  # Below Dead Sea
        assert validate_range(9000, spec) is False  # Above Everest

    def test_range_min_only(self):
        """Test range with only min bound."""
        assert validate_range(100, {'min': 0}) is True
        assert validate_range(-1, {'min': 0}) is False

    def test_range_max_only(self):
        """Test range with only max bound."""
        assert validate_range(50, {'max': 100}) is True
        assert validate_range(101, {'max': 100}) is False

    def test_range_none_value(self):
        """Test range with None value."""
        assert validate_range(None, {'min': 0, 'max': 100}) is False

    def test_range_string_number(self):
        """Test range with string numeric value."""
        assert validate_range('50', {'min': 0, 'max': 100}) is True

    def test_range_non_numeric_value(self):
        """Test range with non-numeric value."""
        assert validate_range('not a number', {'min': 0, 'max': 100}) is False


# =============================================================================
# validate_ranges Tests
# =============================================================================

@pytest.mark.unit
class TestValidateRanges:
    """Test validate_ranges constraint function."""

    def test_ranges_utm_north(self):
        """Test ranges with UTM North zone EPSG codes."""
        utm_ranges = [
            {'min': 32601, 'max': 32660},  # UTM North
            {'min': 32701, 'max': 32760},  # UTM South
        ]
        assert validate_ranges(32615, utm_ranges) is True  # UTM 15N
        assert validate_ranges(32601, utm_ranges) is True  # UTM 1N

    def test_ranges_utm_south(self):
        """Test ranges with UTM South zone EPSG codes."""
        utm_ranges = [
            {'min': 32601, 'max': 32660},
            {'min': 32701, 'max': 32760},
        ]
        assert validate_ranges(32755, utm_ranges) is True  # UTM 55S
        assert validate_ranges(32701, utm_ranges) is True  # UTM 1S

    def test_ranges_not_in_any(self):
        """Test ranges with value not in any range."""
        utm_ranges = [
            {'min': 32601, 'max': 32660},
            {'min': 32701, 'max': 32760},
        ]
        assert validate_ranges(4326, utm_ranges) is False  # WGS84 Geographic
        assert validate_ranges(32661, utm_ranges) is False  # Between ranges

    def test_ranges_dged5_epsg(self):
        """Test ranges with DGED5 EPSG code ranges (UTM + UPS)."""
        dged5_ranges = [
            {'min': 32601, 'max': 32660},  # UTM North
            {'min': 32701, 'max': 32760},  # UTM South
            {'min': 5041, 'max': 5042},    # UPS North/South
        ]
        assert validate_ranges(32615, dged5_ranges) is True  # UTM 15N
        assert validate_ranges(5041, dged5_ranges) is True   # UPS North
        assert validate_ranges(5042, dged5_ranges) is True   # UPS South

    def test_ranges_invalid_expected_type(self):
        """Test ranges with invalid expected type."""
        with pytest.raises(ValueError) as excinfo:
            validate_ranges(32615, 'not a list')
        assert 'requires a list' in str(excinfo.value)


# =============================================================================
# validate_exists Tests
# =============================================================================

@pytest.mark.unit
class TestValidateExists:
    """Test validate_exists constraint function."""

    def test_exists_with_string(self):
        """Test exists with non-empty string."""
        assert validate_exists('Sample DEM') is True
        assert validate_exists('') is False
        assert validate_exists('   ') is False  # Whitespace only

    def test_exists_with_numeric(self):
        """Test exists with numeric values."""
        assert validate_exists(42) is True
        assert validate_exists(0) is True  # Zero is valid
        assert validate_exists(3.14) is True
        assert validate_exists(0.0) is True

    def test_exists_with_none(self):
        """Test exists with None."""
        assert validate_exists(None) is False

    def test_exists_with_collections(self):
        """Test exists with collections."""
        assert validate_exists([1, 2, 3]) is True
        assert validate_exists([]) is False
        assert validate_exists({'key': 'value'}) is True
        assert validate_exists({}) is False

    def test_exists_with_boolean(self):
        """Test exists with boolean values."""
        assert validate_exists(True) is True
        assert validate_exists(False) is True  # False exists


# =============================================================================
# validate_forbidden Tests
# =============================================================================

@pytest.mark.unit
class TestValidateForbidden:
    """Test validate_forbidden constraint function."""

    def test_forbidden_none(self):
        """Test forbidden with None (correct - not present)."""
        assert validate_forbidden(None) is True

    def test_forbidden_with_value(self):
        """Test forbidden with actual value (incorrect - present)."""
        assert validate_forbidden(42) is False
        assert validate_forbidden('value') is False
        assert validate_forbidden(0) is False
        assert validate_forbidden('') is False  # Empty string still exists

    def test_forbidden_with_collections(self):
        """Test forbidden with collections."""
        assert validate_forbidden([]) is False  # Empty list still exists
        assert validate_forbidden({}) is False  # Empty dict still exists


# =============================================================================
# apply_constraint Tests
# =============================================================================

@pytest.mark.unit
class TestApplyConstraint:
    """Test apply_constraint dispatcher function."""

    def test_apply_exact(self):
        """Test apply_constraint with exact."""
        assert apply_constraint(32, 'exact', 32) is True
        assert apply_constraint(32, 'exact', 64) is False

    def test_apply_enum(self):
        """Test apply_constraint with enum."""
        assert apply_constraint(5, 'enum', [5, 8]) is True
        assert apply_constraint(1, 'enum', [5, 8]) is False

    def test_apply_regex(self):
        """Test apply_constraint with regex."""
        assert apply_constraint('abc123', 'regex', r'^[a-z]+\d+$') is True
        assert apply_constraint('123abc', 'regex', r'^[a-z]+\d+$') is False

    def test_apply_range(self):
        """Test apply_constraint with range."""
        assert apply_constraint(50, 'range', {'min': 0, 'max': 100}) is True
        assert apply_constraint(150, 'range', {'min': 0, 'max': 100}) is False

    def test_apply_ranges(self):
        """Test apply_constraint with ranges."""
        ranges = [{'min': 0, 'max': 10}, {'min': 20, 'max': 30}]
        assert apply_constraint(5, 'ranges', ranges) is True
        assert apply_constraint(25, 'ranges', ranges) is True
        assert apply_constraint(15, 'ranges', ranges) is False

    def test_apply_exists(self):
        """Test apply_constraint with exists."""
        assert apply_constraint('value', 'exists', None) is True
        assert apply_constraint(None, 'exists', None) is False

    def test_apply_forbidden(self):
        """Test apply_constraint with forbidden."""
        assert apply_constraint(None, 'forbidden', None) is True
        assert apply_constraint('value', 'forbidden', None) is False

    def test_apply_unknown_constraint(self):
        """Test apply_constraint with unknown constraint raises error."""
        with pytest.raises(ValueError) as excinfo:
            apply_constraint(32, 'unknown_constraint', 32)
        assert 'Unknown constraint type' in str(excinfo.value)
