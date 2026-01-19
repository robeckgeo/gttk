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
Validation Package for GeoTIFF ToolKit.

This package provides validation functionality for verifying GeoTIFF files
against product-specific requirements using TOML-based rule definitions.

Modules:
    models: Data models for validation rules and results
    loader: TOML file loading and parsing
    constraints: Constraint validation functions
    output: Output path generation utilities
"""

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
from gttk.utils.validation.loader import load_validation_rules, parse_rule, get_available_products
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
from gttk.utils.validation.output import generate_output_paths, generate_report_path, get_input_files
from gttk.utils.validation.extractors import ValueExtractor
from gttk.utils.validation.validator import ValidationEngine, validate_file
from gttk.utils.validation.gpkg_models import GeoPackageFeature
from gttk.utils.validation.gpkg_writer import write_validation_gpkg

__all__ = [
    # Enums
    'ValidationStatus',
    'ConstraintType',
    'SectionType',
    # Models
    'ValidationRule',
    'ValidationResult',
    'ValidationSummary',
    'ValidationTableData',
    # Message helpers
    'get_missing_key_message',
    'get_section_missing_message',
    'get_section_display_name',
    'get_section_icon',
    # Loader
    'load_validation_rules',
    'parse_rule',
    'get_available_products',
    # Constraints
    'validate_exact',
    'validate_enum',
    'validate_regex',
    'validate_range',
    'validate_ranges',
    'validate_exists',
    'validate_forbidden',
    'apply_constraint',
    # Output
    'generate_output_paths',
    'generate_report_path',
    'get_input_files',
    # Extractors and Engine
    'ValueExtractor',
    'ValidationEngine',
    'validate_file',
    # GeoPackage
    'GeoPackageFeature',
    'write_validation_gpkg',
]
