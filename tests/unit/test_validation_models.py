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
Unit tests for validation data models.

This module tests all dataclasses defined in gttk.utils.validation.models,
including ValidationRule, ValidationResult, ValidationSummary, and
ValidationTableData.

Test coverage target: 95%+

Organization:
- Each dataclass gets its own test class
- Tests verify instantiation, field assignments, and helper methods
- Edge cases and validation are tested
- Clear docstrings explain what each test verifies
"""

import pytest
from gttk.utils.validation.models import (
    ValidationStatus,
    ConstraintType,
    SectionType,
    ValidationRule,
    ValidationResult,
    ValidationSummary,
    ValidationTableData,
    get_missing_key_message,
    get_section_missing_message,
    get_section_display_name,
    get_section_icon,
)


# =============================================================================
# Enum Tests
# =============================================================================

@pytest.mark.unit
class TestValidationStatusEnum:
    """Test ValidationStatus enum."""

    def test_pass_value(self):
        """Test PASS enum value."""
        assert ValidationStatus.PASS.value == 'PASS'

    def test_fail_value(self):
        """Test FAIL enum value."""
        assert ValidationStatus.FAIL.value == 'FAIL'

    def test_skip_value(self):
        """Test SKIP enum value."""
        assert ValidationStatus.SKIP.value == 'SKIP'

    def test_all_statuses(self):
        """Test all status values exist."""
        statuses = [s.value for s in ValidationStatus]
        assert 'PASS' in statuses
        assert 'FAIL' in statuses
        assert 'SKIP' in statuses
        assert len(statuses) == 3


@pytest.mark.unit
class TestConstraintTypeEnum:
    """Test ConstraintType enum."""

    def test_all_constraint_types(self):
        """Test all constraint types exist."""
        constraints = [c.value for c in ConstraintType]
        assert 'exact' in constraints
        assert 'enum' in constraints
        assert 'regex' in constraints
        assert 'range' in constraints
        assert 'ranges' in constraints
        assert 'exists' in constraints
        assert 'forbidden' in constraints
        assert len(constraints) == 7


@pytest.mark.unit
class TestSectionTypeEnum:
    """Test SectionType enum."""

    def test_all_section_types(self):
        """Test all section types exist."""
        sections = [s.value for s in SectionType]
        assert 'tag' in sections
        assert 'geokey' in sections
        assert 'gdal' in sections
        assert 'geo' in sections
        assert 'xmp' in sections
        assert 'xml' in sections
        assert 'projjson' in sections
        assert len(sections) == 7


# =============================================================================
# ValidationRule Tests
# =============================================================================

@pytest.mark.unit
class TestValidationRule:
    """Test ValidationRule data model."""

    def test_instantiation_with_required_fields(self):
        """Test creating ValidationRule with required fields."""
        rule = ValidationRule(
            product='DGED5',
            section='tag',
            key='258',
            key_type='tag',
            description='BitsPerSample',
            data_type='integer',
            constraint='exact',
            expected=32
        )

        assert rule.product == 'DGED5'
        assert rule.section == 'tag'
        assert rule.key == '258'
        assert rule.key_type == 'tag'
        assert rule.description == 'BitsPerSample'
        assert rule.data_type == 'integer'
        assert rule.constraint == 'exact'
        assert rule.expected == 32
        assert rule.optional is False  # Default
        assert rule.comment is None  # Default

    def test_instantiation_with_optional_fields(self):
        """Test creating ValidationRule with all fields."""
        rule = ValidationRule(
            product='DGED5',
            section='tag',
            key='305',
            key_type='tag',
            description='Software',
            data_type='string',
            constraint='exists',
            optional=True,
            comment='Optional software tag'
        )

        assert rule.optional is True
        assert rule.comment == 'Optional software tag'

    def test_invalid_section_type_raises_error(self):
        """Test that invalid section type raises ValueError."""
        with pytest.raises(ValueError) as excinfo:
            ValidationRule(
                product='DGED5',
                section='invalid_section',
                key='258',
                key_type='tag',
                description='Test',
                data_type='integer',
                constraint='exact',
                expected=32
            )
        assert 'Invalid section' in str(excinfo.value)

    def test_invalid_constraint_type_raises_error(self):
        """Test that invalid constraint type raises ValueError."""
        with pytest.raises(ValueError) as excinfo:
            ValidationRule(
                product='DGED5',
                section='tag',
                key='258',
                key_type='tag',
                description='Test',
                data_type='integer',
                constraint='invalid_constraint',
                expected=32
            )
        assert 'Invalid constraint' in str(excinfo.value)

    def test_exact_constraint_requires_expected(self):
        """Test that exact constraint requires expected value."""
        with pytest.raises(ValueError) as excinfo:
            ValidationRule(
                product='DGED5',
                section='tag',
                key='258',
                key_type='tag',
                description='Test',
                data_type='integer',
                constraint='exact',
                expected=None  # Missing required expected
            )
        assert "requires 'expected' value" in str(excinfo.value)

    def test_exists_constraint_no_expected_required(self):
        """Test that exists constraint doesn't require expected value."""
        rule = ValidationRule(
            product='DGED5',
            section='tag',
            key='270',
            key_type='tag',
            description='ImageDescription',
            data_type='string',
            constraint='exists',
            expected=None  # OK for exists
        )
        assert rule.constraint == 'exists'

    def test_forbidden_constraint_no_expected_required(self):
        """Test that forbidden constraint doesn't require expected value."""
        rule = ValidationRule(
            product='DGED5',
            section='tag',
            key='296',
            key_type='tag',
            description='ResolutionUnit',
            data_type='integer',
            constraint='forbidden',
            expected=None  # OK for forbidden
        )
        assert rule.constraint == 'forbidden'

    def test_invalid_data_type_raises_error(self):
        """Test that invalid data type raises ValueError."""
        with pytest.raises(ValueError) as excinfo:
            ValidationRule(
                product='DGED5',
                section='tag',
                key='258',
                key_type='tag',
                description='Test',
                data_type='invalid_type',
                constraint='exact',
                expected=32
            )
        assert 'Invalid data_type' in str(excinfo.value)

    def test_all_valid_data_types(self):
        """Test all valid data types."""
        for data_type in ['string', 'integer', 'float', 'boolean']:
            rule = ValidationRule(
                product='TEST',
                section='tag',
                key='1',
                key_type='tag',
                description='Test',
                data_type=data_type,
                constraint='exists'
            )
            assert rule.data_type == data_type

    def test_all_valid_sections(self):
        """Test all valid section types."""
        key_type_map = {
            'tag': 'tag',
            'geokey': 'geokey',
            'gdal': 'name',
            'geo': 'xpath',
            'xmp': 'xpath',
            'xml': 'xpath',
            'projjson': 'jsonpath'
        }
        for section in ['tag', 'geokey', 'gdal', 'geo', 'xmp', 'xml', 'projjson']:
            rule = ValidationRule(
                product='TEST',
                section=section,
                key='1',
                key_type=key_type_map[section],
                description='Test',
                data_type='string',
                constraint='exists'
            )
            assert rule.section == section


# =============================================================================
# ValidationResult Tests
# =============================================================================

@pytest.mark.unit
class TestValidationResult:
    """Test ValidationResult data model."""

    @pytest.fixture
    def sample_rule(self):
        """Create a sample ValidationRule for testing."""
        return ValidationRule(
            product='DGED5',
            section='tag',
            key='258',
            key_type='tag',
            description='BitsPerSample',
            data_type='integer',
            constraint='exact',
            expected=32
        )

    def test_instantiation_with_pass_status(self, sample_rule):
        """Test creating ValidationResult with PASS status."""
        result = ValidationResult(
            rule=sample_rule,
            value=32,
            status='PASS',
            message='Tag 258 value matches expected value: 32'
        )

        assert result.rule == sample_rule
        assert result.value == 32
        assert result.status == 'PASS'
        assert result.message == 'Tag 258 value matches expected value: 32'

    def test_instantiation_with_fail_status(self, sample_rule):
        """Test creating ValidationResult with FAIL status."""
        result = ValidationResult(
            rule=sample_rule,
            value=16,
            status='FAIL',
            message='Tag 258 value 16 does not match expected value 32'
        )

        assert result.status == 'FAIL'
        assert result.value == 16

    def test_default_status_is_skip(self, sample_rule):
        """Test that default status is SKIP."""
        result = ValidationResult(rule=sample_rule)
        assert result.status == 'SKIP'

    def test_invalid_status_raises_error(self, sample_rule):
        """Test that invalid status raises ValueError."""
        with pytest.raises(ValueError) as excinfo:
            ValidationResult(
                rule=sample_rule,
                status='INVALID'
            )
        assert 'Invalid status' in str(excinfo.value)

    def test_passed_property(self, sample_rule):
        """Test passed property."""
        pass_result = ValidationResult(rule=sample_rule, status='PASS')
        fail_result = ValidationResult(rule=sample_rule, status='FAIL')
        skip_result = ValidationResult(rule=sample_rule, status='SKIP')

        assert pass_result.passed is True
        assert fail_result.passed is False
        assert skip_result.passed is False

    def test_failed_property(self, sample_rule):
        """Test failed property."""
        pass_result = ValidationResult(rule=sample_rule, status='PASS')
        fail_result = ValidationResult(rule=sample_rule, status='FAIL')
        skip_result = ValidationResult(rule=sample_rule, status='SKIP')

        assert pass_result.failed is False
        assert fail_result.failed is True
        assert skip_result.failed is False

    def test_skipped_property(self, sample_rule):
        """Test skipped property."""
        pass_result = ValidationResult(rule=sample_rule, status='PASS')
        fail_result = ValidationResult(rule=sample_rule, status='FAIL')
        skip_result = ValidationResult(rule=sample_rule, status='SKIP')

        assert pass_result.skipped is False
        assert fail_result.skipped is False
        assert skip_result.skipped is True

    def test_get_icon(self, sample_rule):
        """Test get_icon method."""
        pass_result = ValidationResult(rule=sample_rule, status='PASS')
        fail_result = ValidationResult(rule=sample_rule, status='FAIL')
        skip_result = ValidationResult(rule=sample_rule, status='SKIP')

        assert pass_result.get_icon() == '\u2705'  # ✅
        assert fail_result.get_icon() == '\u274c'  # ❌
        assert skip_result.get_icon() == '\u26a0\ufe0f'  # ⚠️


# =============================================================================
# ValidationSummary Tests
# =============================================================================

@pytest.mark.unit
class TestValidationSummary:
    """Test ValidationSummary data model."""

    def test_instantiation_with_required_fields(self):
        """Test creating ValidationSummary with required fields."""
        summary = ValidationSummary(
            product='DGED5',
            input_file='example.tif',
            rules_file='example_rules.toml',
            report_date='2026-01-15'
        )

        assert summary.product == 'DGED5'
        assert summary.input_file == 'example.tif'
        assert summary.rules_file == 'example_rules.toml'
        assert summary.report_date == '2026-01-15'
        assert summary.total_rules == 0  # Default
        assert summary.passed == 0  # Default
        assert summary.failed == 0  # Default
        assert summary.skipped == 0  # Default

    def test_pass_rate_with_results(self):
        """Test pass_rate calculation."""
        summary = ValidationSummary(
            product='DGED5',
            input_file='test.tif',
            rules_file='test.toml',
            report_date='2026-01-15',
            total_rules=10,
            passed=8,
            failed=2
        )

        assert summary.pass_rate == 80.0

    def test_pass_rate_zero_rules(self):
        """Test pass_rate with zero rules."""
        summary = ValidationSummary(
            product='DGED5',
            input_file='test.tif',
            rules_file='test.toml',
            report_date='2026-01-15',
            total_rules=0
        )

        assert summary.pass_rate == 0.0

    def test_fail_rate_with_results(self):
        """Test fail_rate calculation."""
        summary = ValidationSummary(
            product='DGED5',
            input_file='test.tif',
            rules_file='test.toml',
            report_date='2026-01-15',
            total_rules=10,
            passed=7,
            failed=3
        )

        assert summary.fail_rate == 30.0

    def test_overall_status_fail(self):
        """Test overall_status when failures exist."""
        summary = ValidationSummary(
            product='DGED5',
            input_file='test.tif',
            rules_file='test.toml',
            report_date='2026-01-15',
            total_rules=10,
            passed=8,
            failed=2
        )

        assert summary.overall_status == 'FAIL'

    def test_overall_status_pass(self):
        """Test overall_status when all pass."""
        summary = ValidationSummary(
            product='DGED5',
            input_file='test.tif',
            rules_file='test.toml',
            report_date='2026-01-15',
            total_rules=10,
            passed=10,
            failed=0
        )

        assert summary.overall_status == 'PASS'

    def test_overall_status_skip(self):
        """Test overall_status when all skipped."""
        summary = ValidationSummary(
            product='DGED5',
            input_file='test.tif',
            rules_file='test.toml',
            report_date='2026-01-15',
            total_rules=5,
            passed=0,
            failed=0,
            skipped=5
        )

        assert summary.overall_status == 'SKIP'


# =============================================================================
# ValidationTableData Tests
# =============================================================================

@pytest.mark.unit
class TestValidationTableData:
    """Test ValidationTableData data model."""

    @pytest.fixture
    def sample_results(self):
        """Create sample ValidationResults for testing."""
        rule = ValidationRule(
            product='DGED5',
            section='tag',
            key='258',
            key_type='tag',
            description='BitsPerSample',
            data_type='integer',
            constraint='exact',
            expected=32
        )

        return [
            ValidationResult(rule=rule, status='PASS', value=32),
            ValidationResult(rule=rule, status='PASS', value=32),
            ValidationResult(rule=rule, status='FAIL', value=16),
            ValidationResult(rule=rule, status='SKIP'),
        ]

    def test_instantiation(self, sample_results):
        """Test creating ValidationTableData."""
        table = ValidationTableData(
            section_name='TIFF Tags',
            section_type='tag',
            results=sample_results
        )

        assert table.section_name == 'TIFF Tags'
        assert table.section_type == 'tag'
        assert len(table.results) == 4
        assert table.icon == 'checkbox'  # Default

    def test_passed_count(self, sample_results):
        """Test passed_count property."""
        table = ValidationTableData(
            section_name='Test',
            section_type='tag',
            results=sample_results
        )

        assert table.passed_count == 2

    def test_failed_count(self, sample_results):
        """Test failed_count property."""
        table = ValidationTableData(
            section_name='Test',
            section_type='tag',
            results=sample_results
        )

        assert table.failed_count == 1

    def test_skipped_count(self, sample_results):
        """Test skipped_count property."""
        table = ValidationTableData(
            section_name='Test',
            section_type='tag',
            results=sample_results
        )

        assert table.skipped_count == 1


# =============================================================================
# Message Function Tests
# =============================================================================

@pytest.mark.unit
class TestMessageFunctions:
    """Test message generation functions."""

    def test_get_missing_key_message_tag(self):
        """Test missing key message for tag section."""
        rule = ValidationRule(
            product='DGED5',
            section='tag',
            key='258',
            key_type='tag',
            description='BitsPerSample',
            data_type='integer',
            constraint='exact',
            expected=32
        )

        message = get_missing_key_message(rule)
        assert 'Tag 258' in message
        assert 'BitsPerSample' in message
        assert 'required' in message

    def test_get_missing_key_message_geokey(self):
        """Test missing key message for geokey section."""
        rule = ValidationRule(
            product='DGED5',
            section='geokey',
            key='3072',
            key_type='geokey',
            description='ProjectedCRSGeoKey',
            data_type='integer',
            constraint='exact',
            expected=32615
        )

        message = get_missing_key_message(rule)
        assert 'GeoKey 3072' in message
        assert 'required' in message

    def test_get_missing_key_message_gdal(self):
        """Test missing key message for gdal section."""
        rule = ValidationRule(
            product='DGED5',
            section='gdal',
            key='STATISTICS_MINIMUM',
            key_type='name',
            description='Minimum Elevation',
            data_type='float',
            constraint='range',
            expected={'min': -430, 'max': 8850}
        )

        message = get_missing_key_message(rule)
        assert 'STATISTICS_MINIMUM' in message
        assert 'required' in message

    def test_get_missing_key_message_xml(self):
        """Test missing key message for xml section."""
        rule = ValidationRule(
            product='DGED5',
            section='xml',
            key='/mdb:MD_Metadata/mdb:contact',
            key_type='xpath',
            description='Metadata Contact',
            data_type='string',
            constraint='exists'
        )

        message = get_missing_key_message(rule)
        assert 'XPath' in message
        assert 'required' in message

    def test_get_section_missing_message(self):
        """Test section missing messages."""
        assert 'not a TIFF' in get_section_missing_message('tag')
        assert 'not a GeoTIFF' in get_section_missing_message('geokey')
        assert '42112' in get_section_missing_message('gdal')
        assert '50909' in get_section_missing_message('geo')
        assert '700' in get_section_missing_message('xmp')
        assert 'external XML' in get_section_missing_message('xml')
        assert 'PROJJSON' in get_section_missing_message('projjson')

    def test_get_section_display_name(self):
        """Test section display names."""
        assert get_section_display_name('tag') == 'TIFF Tags'
        assert get_section_display_name('geokey') == 'GeoKeys'
        assert get_section_display_name('gdal') == 'GDAL Metadata'
        assert get_section_display_name('unknown') == 'UNKNOWN'

    def test_get_section_icon(self):
        """Test section icons."""
        assert get_section_icon('tag') == 'tag'
        assert get_section_icon('geokey') == 'key'
        assert get_section_icon('gdal') == 'earth'
        assert get_section_icon('unknown') == 'checkbox'
