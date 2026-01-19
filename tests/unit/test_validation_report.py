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
Unit tests for validation report generation.

This module tests the ValidationReportBuilder and related report
generation functionality.

Test coverage:
- ValidationReportBuilder section building
- Report generation for HTML and Markdown formats
- File naming with PASS/FAIL suffix
- Section rendering for validation tables
"""

import pytest
from pathlib import Path

from gttk.utils.validation.models import (
    ValidationRule,
    ValidationResult,
    ValidationSummary,
    ValidationTableData,
    ValidationStatus,
)
from gttk.utils.report_builders import ValidationReportBuilder
from gttk.utils.report_formatters import HtmlReportFormatter, MarkdownReportFormatter
from gttk.utils.validation.output import generate_report_path


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def sample_rule():
    """Create a sample validation rule."""
    return ValidationRule(
        product='Test',
        section='tag',
        key='259',
        key_type='tag',
        description='Compression',
        data_type='integer',
        constraint='exact',
        expected=8
    )


@pytest.fixture
def sample_result(sample_rule):
    """Create a sample validation result."""
    return ValidationResult(
        rule=sample_rule,
        value=8,
        status=ValidationStatus.PASS.value,
        message='Tag 259 (Compression) matches expected value: 8'
    )


@pytest.fixture
def sample_failed_result(sample_rule):
    """Create a sample failed validation result."""
    return ValidationResult(
        rule=sample_rule,
        value=5,
        status=ValidationStatus.FAIL.value,
        message='Tag 259 (Compression) expected 8, got 5'
    )


@pytest.fixture
def sample_summary(sample_result):
    """Create a sample validation summary with passing results."""
    return ValidationSummary(
        product='TestProduct',
        input_file='test_file.tif',
        rules_file='test_rules.toml',
        report_date='2026-01-15',
        total_rules=1,
        passed=1,
        failed=0,
        skipped=0,
        results_by_section={'tag': [sample_result]}
    )


@pytest.fixture
def sample_failed_summary(sample_failed_result):
    """Create a sample validation summary with failing results."""
    return ValidationSummary(
        product='TestProduct',
        input_file='test_file.tif',
        rules_file='test_rules.toml',
        report_date='2026-01-15',
        total_rules=1,
        passed=0,
        failed=1,
        skipped=0,
        results_by_section={'tag': [sample_failed_result]}
    )


@pytest.fixture
def multi_section_summary():
    """Create a summary with multiple sections."""
    tag_rule = ValidationRule(
        product='Test',
        section='tag',
        key='259',
        key_type='tag',
        description='Compression',
        data_type='integer',
        constraint='exact',
        expected=8
    )
    geokey_rule = ValidationRule(
        product='Test',
        section='geokey',
        key='1024',
        key_type='geokey',
        description='GTModelTypeGeoKey',
        data_type='integer',
        constraint='exact',
        expected=1
    )

    tag_result = ValidationResult(
        rule=tag_rule,
        value=8,
        status=ValidationStatus.PASS.value,
        message='Tag 259 matches'
    )
    geokey_result = ValidationResult(
        rule=geokey_rule,
        value=1,
        status=ValidationStatus.PASS.value,
        message='GeoKey 1024 matches'
    )

    return ValidationSummary(
        product='TestProduct',
        input_file='test_file.tif',
        rules_file='test_rules.toml',
        report_date='2026-01-15',
        total_rules=2,
        passed=2,
        failed=0,
        skipped=0,
        results_by_section={
            'tag': [tag_result],
            'geokey': [geokey_result]
        }
    )


# =============================================================================
# ValidationReportBuilder Tests
# =============================================================================

@pytest.mark.unit
class TestValidationReportBuilder:
    """Test ValidationReportBuilder class."""

    def test_init(self, sample_summary):
        """Test builder initialization."""
        builder = ValidationReportBuilder(sample_summary)

        assert builder.summary is sample_summary
        assert builder.sections == []

    def test_build_creates_sections(self, sample_summary):
        """Test that build creates expected sections."""
        builder = ValidationReportBuilder(sample_summary)
        builder.build()

        # Should have summary section and tag section
        assert len(builder.sections) == 2

        section_ids = [s.id for s in builder.sections]
        assert 'validation-summary' in section_ids
        assert 'validation-tag' in section_ids

    def test_build_multi_section(self, multi_section_summary):
        """Test building with multiple sections."""
        builder = ValidationReportBuilder(multi_section_summary)
        builder.build()

        # Should have summary, tag, and geokey sections
        assert len(builder.sections) == 3

        section_ids = [s.id for s in builder.sections]
        assert 'validation-summary' in section_ids
        assert 'validation-tag' in section_ids
        assert 'validation-geokey' in section_ids

    def test_summary_section_data(self, sample_summary):
        """Test that summary section contains correct data."""
        builder = ValidationReportBuilder(sample_summary)
        builder.build()

        summary_section = next(
            s for s in builder.sections if s.id == 'validation-summary'
        )

        assert summary_section.data is sample_summary
        assert summary_section.data.product == 'TestProduct'
        assert summary_section.data.passed == 1

    def test_validation_table_data(self, sample_summary):
        """Test that validation table section contains correct data."""
        builder = ValidationReportBuilder(sample_summary)
        builder.build()

        tag_section = next(
            s for s in builder.sections if s.id == 'validation-tag'
        )

        assert isinstance(tag_section.data, ValidationTableData)
        assert tag_section.data.section_name == 'TIFF Tags'
        assert tag_section.data.section_type == 'tag'
        assert len(tag_section.data.results) == 1


# =============================================================================
# Report Path Generation Tests
# =============================================================================

@pytest.mark.unit
class TestReportPathGeneration:
    """Test report path generation with PASS/FAIL suffix."""

    def test_pass_suffix_html(self, tmp_path):
        """Test PASS suffix for HTML reports in reports subfolder."""
        input_file = Path('/data/test_file.tif')
        output_folder = tmp_path

        path = generate_report_path(input_file, output_folder, 'PASS', 'html')

        assert path.name == 'test_file_PASS.html'
        assert path.parent == output_folder / 'reports'

    def test_fail_suffix_html(self, tmp_path):
        """Test FAIL suffix for HTML reports."""
        input_file = Path('/data/test_file.tif')
        output_folder = tmp_path

        path = generate_report_path(input_file, output_folder, 'FAIL', 'html')

        assert path.name == 'test_file_FAIL.html'

    def test_skip_suffix_md(self, tmp_path):
        """Test SKIP suffix for Markdown reports."""
        input_file = Path('/data/test_file.tif')
        output_folder = tmp_path

        path = generate_report_path(input_file, output_folder, 'SKIP', 'md')

        assert path.name == 'test_file_SKIP.md'

    def test_preserves_stem(self, tmp_path):
        """Test that original filename stem is preserved."""
        input_file = Path('/data/complex_file_name_001.tif')
        output_folder = tmp_path

        path = generate_report_path(input_file, output_folder, 'PASS', 'html')

        assert path.name == 'complex_file_name_001_PASS.html'


# =============================================================================
# Report Formatter Integration Tests
# =============================================================================

@pytest.mark.unit
class TestReportFormatterIntegration:
    """Test integration with report formatters."""

    def test_html_formatter_with_validation_sections(self, sample_summary):
        """Test HtmlReportFormatter works with validation sections."""
        builder = ValidationReportBuilder(sample_summary)
        builder.build()

        formatter = HtmlReportFormatter(
            filename='test_file.tif',
            report_type='validation'
        )
        formatter.report_title = 'Validation Report: TestProduct'
        formatter.include_title = True
        formatter.sections = builder.sections

        html_output = formatter.format()

        assert '<!DOCTYPE html>' in html_output
        assert 'test_file.tif' in html_output
        assert 'TestProduct' in html_output

    def test_markdown_formatter_with_validation_sections(self, sample_summary):
        """Test MarkdownReportFormatter works with validation sections."""
        builder = ValidationReportBuilder(sample_summary)
        builder.build()

        formatter = MarkdownReportFormatter(filename='test_file.tif')
        formatter.report_title = 'Validation Report: TestProduct'
        formatter.include_title = True
        formatter.sections = builder.sections

        md_output = formatter.format()

        assert '# Validation Report: TestProduct' in md_output
        assert 'test_file.tif' in md_output


# =============================================================================
# ValidationTableData Tests
# =============================================================================

@pytest.mark.unit
class TestValidationTableData:
    """Test ValidationTableData dataclass."""

    def test_passed_count(self, sample_result, sample_failed_result):
        """Test passed_count property."""
        table = ValidationTableData(
            section_name='Test',
            section_type='tag',
            results=[sample_result, sample_failed_result]
        )

        assert table.passed_count == 1
        assert table.failed_count == 1
        assert table.skipped_count == 0

    def test_all_passed(self, sample_result):
        """Test with all passing results."""
        table = ValidationTableData(
            section_name='Test',
            section_type='tag',
            results=[sample_result, sample_result]
        )

        assert table.passed_count == 2
        assert table.failed_count == 0

    def test_all_failed(self, sample_failed_result):
        """Test with all failing results."""
        table = ValidationTableData(
            section_name='Test',
            section_type='tag',
            results=[sample_failed_result]
        )

        assert table.passed_count == 0
        assert table.failed_count == 1


# =============================================================================
# ValidationSummary Overall Status Tests
# =============================================================================

@pytest.mark.unit
class TestValidationSummaryStatus:
    """Test ValidationSummary overall_status property."""

    def test_overall_status_pass(self, sample_summary):
        """Test overall status is PASS when all pass."""
        assert sample_summary.overall_status == 'PASS'

    def test_overall_status_fail(self, sample_failed_summary):
        """Test overall status is FAIL when any fail."""
        assert sample_failed_summary.overall_status == 'FAIL'

    def test_overall_status_skip(self):
        """Test overall status is SKIP when all skipped."""
        summary = ValidationSummary(
            product='Test',
            input_file='test.tif',
            rules_file='rules.toml',
            report_date='2026-01-15',
            total_rules=1,
            passed=0,
            failed=0,
            skipped=1,
            results_by_section={}
        )

        assert summary.overall_status == 'SKIP'

    def test_pass_rate(self, sample_summary):
        """Test pass_rate calculation."""
        assert sample_summary.pass_rate == 100.0

    def test_fail_rate(self, sample_failed_summary):
        """Test fail_rate calculation."""
        assert sample_failed_summary.fail_rate == 100.0
