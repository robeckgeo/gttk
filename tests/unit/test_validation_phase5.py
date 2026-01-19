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
Unit tests for Phase 5 validation features.

This module tests:
- PROJJSON extraction with jsonpath-ng library
- Extended data types (date, datetime, url, email)
- Advanced JSONPath expressions

Test coverage:
- Full JSONPath support with jsonpath-ng
- Date format validation (ISO 8601)
- Datetime format validation (ISO 8601)
- URL format validation
- Email format validation
- Integration with validation engine
"""

import pytest
from unittest.mock import MagicMock, patch
import json

from gttk.utils.validation.constraints import (
    validate_date_format,
    validate_datetime_format,
    validate_url_format,
    validate_email_format,
    validate_data_type,
)
from gttk.utils.validation.extractors import ValueExtractor
from gttk.utils.validation.models import ValidationRule


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def sample_projjson():
    """Sample PROJJSON for testing."""
    return json.dumps({
        "type": "ProjectedCRS",
        "name": "NAD83 / UTM zone 10N",
        "base_crs": {
            "name": "NAD83",
            "datum": {
                "type": "GeodeticReferenceFrame",
                "name": "North American Datum 1983",
                "ellipsoid": {
                    "name": "GRS 1980",
                    "semi_major_axis": 6378137,
                    "inverse_flattening": 298.257222101
                }
            }
        },
        "conversion": {
            "name": "UTM zone 10N",
            "method": {
                "name": "Transverse Mercator",
                "id": {"authority": "EPSG", "code": 9807}
            },
            "parameters": [
                {"name": "Latitude of natural origin", "value": 0},
                {"name": "Longitude of natural origin", "value": -123},
                {"name": "Scale factor", "value": 0.9996}
            ]
        },
        "coordinate_system": {
            "subtype": "Cartesian",
            "axis": [
                {"name": "Easting", "abbreviation": "E", "direction": "east", "unit": "metre"},
                {"name": "Northing", "abbreviation": "N", "direction": "north", "unit": "metre"}
            ]
        },
        "id": {"authority": "EPSG", "code": 26910}
    })


@pytest.fixture
def mock_extractor(sample_projjson):
    """Create a mock MetadataExtractor with PROJJSON."""
    extractor = MagicMock()

    projjson_mock = MagicMock()
    projjson_mock.json_string = sample_projjson
    extractor.extract_projjson_string.return_value = projjson_mock

    return extractor


# =============================================================================
# PROJJSON Extraction Tests with jsonpath-ng
# =============================================================================

@pytest.mark.unit
class TestProjjsonExtraction:
    """Test PROJJSON extraction with full JSONPath support."""

    def test_simple_path(self, mock_extractor):
        """Test simple path extraction."""
        ve = ValueExtractor(mock_extractor)

        assert ve.extract_projjson('$.name') == 'NAD83 / UTM zone 10N'
        assert ve.extract_projjson('$.type') == 'ProjectedCRS'

    def test_nested_path(self, mock_extractor):
        """Test nested path extraction."""
        ve = ValueExtractor(mock_extractor)

        assert ve.extract_projjson('$.id.authority') == 'EPSG'
        assert ve.extract_projjson('$.id.code') == 26910
        assert ve.extract_projjson('$.base_crs.name') == 'NAD83'

    def test_deeply_nested_path(self, mock_extractor):
        """Test deeply nested path extraction."""
        ve = ValueExtractor(mock_extractor)

        assert ve.extract_projjson('$.base_crs.datum.ellipsoid.name') == 'GRS 1980'
        assert ve.extract_projjson('$.base_crs.datum.ellipsoid.semi_major_axis') == 6378137

    def test_array_index(self, mock_extractor):
        """Test array index extraction."""
        ve = ValueExtractor(mock_extractor)

        # First axis
        axis_name = ve.extract_projjson('$.coordinate_system.axis[0].name')
        assert axis_name == 'Easting'

        # Second axis
        axis_name = ve.extract_projjson('$.coordinate_system.axis[1].name')
        assert axis_name == 'Northing'

    def test_array_wildcard(self, mock_extractor):
        """Test array wildcard extraction (all elements)."""
        ve = ValueExtractor(mock_extractor)

        # Get all axis names
        names = ve.extract_projjson('$.coordinate_system.axis[*].name')
        assert isinstance(names, list)
        assert names == ['Easting', 'Northing']

    def test_recursive_descent(self, mock_extractor):
        """Test recursive descent operator (..)."""
        ve = ValueExtractor(mock_extractor)

        # Find all 'name' fields anywhere in the document
        names = ve.extract_projjson('$..name')
        assert isinstance(names, list)
        assert 'NAD83 / UTM zone 10N' in names
        assert 'NAD83' in names
        assert 'GRS 1980' in names

    def test_conversion_parameters(self, mock_extractor):
        """Test extracting conversion parameters."""
        ve = ValueExtractor(mock_extractor)

        # First parameter
        param_value = ve.extract_projjson('$.conversion.parameters[0].value')
        assert param_value == 0

        # Scale factor (third parameter)
        scale = ve.extract_projjson('$.conversion.parameters[2].value')
        assert scale == 0.9996

    def test_missing_path_returns_none(self, mock_extractor):
        """Test that missing paths return None."""
        ve = ValueExtractor(mock_extractor)

        assert ve.extract_projjson('$.nonexistent') is None
        assert ve.extract_projjson('$.id.nonexistent') is None
        assert ve.extract_projjson('$.coordinate_system.axis[99].name') is None

    def test_no_projjson_content(self):
        """Test extraction when PROJJSON is not available."""
        extractor = MagicMock()
        extractor.extract_projjson_string.return_value = None

        ve = ValueExtractor(extractor)
        assert ve.extract_projjson('$.name') is None

    def test_path_without_dollar_prefix(self, mock_extractor):
        """Test paths without $ prefix."""
        ve = ValueExtractor(mock_extractor)

        # Should work with or without $ prefix
        assert ve.extract_projjson('name') == 'NAD83 / UTM zone 10N'
        assert ve.extract_projjson('id.authority') == 'EPSG'


# =============================================================================
# Extended Data Type Tests - Date
# =============================================================================

@pytest.mark.unit
class TestDateValidation:
    """Test date format validation."""

    def test_valid_dates(self):
        """Test valid ISO 8601 dates."""
        valid_dates = [
            '2025-01-15',
            '2024-02-29',  # Leap year
            '2000-12-31',
            '1999-01-01',
        ]
        for date_str in valid_dates:
            is_valid, error = validate_date_format(date_str)
            assert is_valid, f"Expected '{date_str}' to be valid, got error: {error}"

    def test_invalid_date_format(self):
        """Test invalid date formats."""
        invalid_dates = [
            '01/15/2025',  # Wrong format
            '2025-1-15',   # Single digit month
            '2025-01-5',   # Single digit day
            '25-01-15',    # Two digit year
            'not-a-date',
        ]
        for date_str in invalid_dates:
            is_valid, error = validate_date_format(date_str)
            assert not is_valid, f"Expected '{date_str}' to be invalid"

    def test_invalid_month(self):
        """Test invalid month values."""
        is_valid, error = validate_date_format('2025-13-01')
        assert not is_valid
        assert 'Invalid month' in error

        is_valid, error = validate_date_format('2025-00-15')
        assert not is_valid
        assert 'Invalid month' in error

    def test_invalid_day(self):
        """Test invalid day values."""
        is_valid, error = validate_date_format('2025-01-32')
        assert not is_valid
        assert 'Invalid day' in error

        is_valid, error = validate_date_format('2025-02-30')
        assert not is_valid
        assert 'Invalid day' in error

    def test_leap_year_handling(self):
        """Test leap year date validation."""
        # Valid leap year date
        is_valid, _ = validate_date_format('2024-02-29')
        assert is_valid

        # Invalid non-leap year date
        is_valid, error = validate_date_format('2025-02-29')
        assert not is_valid
        assert 'Invalid day' in error

    def test_none_value(self):
        """Test None value returns error."""
        is_valid, error = validate_date_format(None)
        assert not is_valid
        assert 'None' in error


# =============================================================================
# Extended Data Type Tests - Datetime
# =============================================================================

@pytest.mark.unit
class TestDatetimeValidation:
    """Test datetime format validation."""

    def test_valid_datetimes(self):
        """Test valid ISO 8601 datetimes."""
        valid_datetimes = [
            '2025-01-15T12:30:00',
            '2025-01-15T12:30:00Z',
            '2025-01-15T12:30:00+05:30',
            '2025-01-15T12:30:00-08:00',
            '2025-01-15T12:30:00.123',
            '2025-01-15T12:30:00.123456Z',
            '2025-01-15 12:30:00',  # Space separator also allowed
        ]
        for dt_str in valid_datetimes:
            is_valid, error = validate_datetime_format(dt_str)
            assert is_valid, f"Expected '{dt_str}' to be valid, got error: {error}"

    def test_invalid_datetime_format(self):
        """Test invalid datetime formats."""
        invalid_datetimes = [
            '2025-01-15',          # Date only
            '12:30:00',            # Time only
            '01/15/2025 12:30:00', # Wrong date format
            'not-a-datetime',
        ]
        for dt_str in invalid_datetimes:
            is_valid, error = validate_datetime_format(dt_str)
            assert not is_valid, f"Expected '{dt_str}' to be invalid"

    def test_invalid_time_components(self):
        """Test invalid time component values."""
        # Invalid hour
        is_valid, error = validate_datetime_format('2025-01-15T25:30:00')
        assert not is_valid
        assert 'Invalid hour' in error

        # Invalid minute
        is_valid, error = validate_datetime_format('2025-01-15T12:61:00')
        assert not is_valid
        assert 'Invalid minute' in error

        # Invalid second
        is_valid, error = validate_datetime_format('2025-01-15T12:30:61')
        assert not is_valid
        assert 'Invalid second' in error


# =============================================================================
# Extended Data Type Tests - URL
# =============================================================================

@pytest.mark.unit
class TestUrlValidation:
    """Test URL format validation."""

    def test_valid_urls(self):
        """Test valid URL formats."""
        valid_urls = [
            'https://example.com',
            'https://example.com/path/to/resource',
            'https://example.com/path?query=value',
            'http://example.com',
            'ftp://files.example.com/data.zip',
            'https://subdomain.example.co.uk/path',
        ]
        for url in valid_urls:
            is_valid, error = validate_url_format(url)
            assert is_valid, f"Expected '{url}' to be valid, got error: {error}"

    def test_invalid_urls(self):
        """Test invalid URL formats."""
        invalid_urls = [
            'not-a-url',
            'example.com',  # Missing scheme
            'file:///path/to/file',  # Unsupported scheme
            'mailto:user@example.com',  # Unsupported scheme
        ]
        for url in invalid_urls:
            is_valid, error = validate_url_format(url)
            assert not is_valid, f"Expected '{url}' to be invalid"

    def test_missing_domain(self):
        """Test URL with missing domain."""
        is_valid, error = validate_url_format('https://')
        assert not is_valid
        assert 'missing domain' in error.lower()


# =============================================================================
# Extended Data Type Tests - Email
# =============================================================================

@pytest.mark.unit
class TestEmailValidation:
    """Test email format validation."""

    def test_valid_emails(self):
        """Test valid email formats."""
        valid_emails = [
            'user@example.com',
            'user.name@example.com',
            'user+tag@example.com',
            'user@subdomain.example.com',
            'user123@example.co.uk',
        ]
        for email in valid_emails:
            is_valid, error = validate_email_format(email)
            assert is_valid, f"Expected '{email}' to be valid, got error: {error}"

    def test_invalid_emails(self):
        """Test invalid email formats."""
        invalid_emails = [
            'not-an-email',
            '@example.com',  # Missing local part
            'user@',  # Missing domain
            'user@.com',  # Invalid domain
            'user@example',  # No TLD
        ]
        for email in invalid_emails:
            is_valid, error = validate_email_format(email)
            assert not is_valid, f"Expected '{email}' to be invalid"


# =============================================================================
# validate_data_type Integration Tests
# =============================================================================

@pytest.mark.unit
class TestValidateDataType:
    """Test the unified validate_data_type function."""

    def test_basic_types(self):
        """Test basic type validation."""
        # String
        is_valid, _ = validate_data_type('hello', 'string')
        assert is_valid

        # Integer
        is_valid, _ = validate_data_type(42, 'integer')
        assert is_valid
        is_valid, _ = validate_data_type('42', 'integer')
        assert is_valid

        # Float
        is_valid, _ = validate_data_type(3.14, 'float')
        assert is_valid
        is_valid, _ = validate_data_type('3.14', 'float')
        assert is_valid

        # Boolean
        is_valid, _ = validate_data_type(True, 'boolean')
        assert is_valid
        is_valid, _ = validate_data_type('true', 'boolean')
        assert is_valid

    def test_extended_types(self):
        """Test extended type validation."""
        # Date
        is_valid, _ = validate_data_type('2025-01-15', 'date')
        assert is_valid

        # Datetime
        is_valid, _ = validate_data_type('2025-01-15T12:30:00Z', 'datetime')
        assert is_valid

        # URL
        is_valid, _ = validate_data_type('https://example.com', 'url')
        assert is_valid

        # Email
        is_valid, _ = validate_data_type('user@example.com', 'email')
        assert is_valid

    def test_invalid_values(self):
        """Test invalid value detection."""
        is_valid, error = validate_data_type('not-a-number', 'integer')
        assert not is_valid

        is_valid, error = validate_data_type('not-a-date', 'date')
        assert not is_valid

        is_valid, error = validate_data_type('not-a-url', 'url')
        assert not is_valid


# =============================================================================
# ValidationRule Extended Data Type Tests
# =============================================================================

@pytest.mark.unit
class TestValidationRuleExtendedTypes:
    """Test ValidationRule with extended data types."""

    def test_date_data_type_accepted(self):
        """Test that date data type is accepted in rules."""
        rule = ValidationRule(
            product='TEST',
            section='tag',
            key='306',
            key_type='tag',
            description='DateTime',
            data_type='date',
            constraint='exists'
        )
        assert rule.data_type == 'date'

    def test_datetime_data_type_accepted(self):
        """Test that datetime data type is accepted in rules."""
        rule = ValidationRule(
            product='TEST',
            section='gdal',
            key='CREATION_DATE',
            key_type='name',
            description='Creation Date',
            data_type='datetime',
            constraint='exists'
        )
        assert rule.data_type == 'datetime'

    def test_url_data_type_accepted(self):
        """Test that url data type is accepted in rules."""
        rule = ValidationRule(
            product='TEST',
            section='xmp',
            key='//dc:source',
            key_type='xpath',
            description='Source URL',
            data_type='url',
            constraint='exists'
        )
        assert rule.data_type == 'url'

    def test_email_data_type_accepted(self):
        """Test that email data type is accepted in rules."""
        rule = ValidationRule(
            product='TEST',
            section='xmp',
            key='//dc:creator',
            key_type='xpath',
            description='Creator Email',
            data_type='email',
            constraint='exists'
        )
        assert rule.data_type == 'email'

    def test_invalid_data_type_rejected(self):
        """Test that invalid data types are rejected."""
        with pytest.raises(ValueError, match="Invalid data_type"):
            ValidationRule(
                product='TEST',
                section='tag',
                key='258',
                key_type='tag',
                description='BitsPerSample',
                data_type='invalid_type',
                constraint='exact',
                expected=32
            )


# =============================================================================
# Value Extractor Type Conversion Tests
# =============================================================================

@pytest.mark.unit
class TestValueExtractorTypeConversion:
    """Test ValueExtractor type conversion for extended types."""

    def test_date_conversion(self):
        """Test date type conversion returns string."""
        result = ValueExtractor.convert_value('2025-01-15', 'date')
        assert result == '2025-01-15'
        assert isinstance(result, str)

    def test_datetime_conversion(self):
        """Test datetime type conversion returns string."""
        result = ValueExtractor.convert_value('2025-01-15T12:30:00Z', 'datetime')
        assert result == '2025-01-15T12:30:00Z'
        assert isinstance(result, str)

    def test_url_conversion(self):
        """Test URL type conversion returns string."""
        result = ValueExtractor.convert_value('https://example.com', 'url')
        assert result == 'https://example.com'
        assert isinstance(result, str)

    def test_email_conversion(self):
        """Test email type conversion returns string."""
        result = ValueExtractor.convert_value('user@example.com', 'email')
        assert result == 'user@example.com'
        assert isinstance(result, str)
