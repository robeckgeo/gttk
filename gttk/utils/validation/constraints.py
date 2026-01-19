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
Constraint Validation Functions for GTTK Validation Package.

This module provides validation functions for all supported constraint types
used in TOML-based validation rules. Each function evaluates whether a value
meets the specified constraint requirements.

Constraint Types:
    exact: Value must exactly match expected value
    enum: Value must be in a list of allowed values
    regex: Value must match a regular expression pattern
    range: Value must be within a min/max range
    ranges: Value must be within at least one of multiple ranges
    exists: Value must exist (not None or empty)
    forbidden: Value must NOT exist

Extended Data Types (Phase 5):
    date: ISO 8601 date format (YYYY-MM-DD)
    datetime: ISO 8601 datetime format (YYYY-MM-DDThh:mm:ss[.sss][Z|±hh:mm])
    url: Valid URL format (http://, https://, ftp://, s3://)
    email: Valid email address format

Functions:
    validate_exact: Validate exact match constraint
    validate_enum: Validate enum/list membership constraint
    validate_regex: Validate regex pattern match constraint
    validate_range: Validate single range constraint
    validate_ranges: Validate multiple ranges constraint
    validate_exists: Validate existence constraint
    validate_forbidden: Validate forbidden (non-existence) constraint
    validate_date_format: Validate ISO 8601 date format
    validate_datetime_format: Validate ISO 8601 datetime format
    validate_url_format: Validate URL format
    validate_email_format: Validate email address format
"""

import re
from datetime import datetime as dt
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse


def validate_exact(value: Any, expected: Any) -> bool:
    """
    Validate that value exactly matches expected value.

    Performs type-aware comparison, attempting numeric conversion
    when comparing numbers.

    Args:
        value: The actual value to validate
        expected: The expected value to match

    Returns:
        True if values match, False otherwise

    Examples:
        >>> validate_exact(32, 32)
        True
        >>> validate_exact('32', 32)
        True
        >>> validate_exact([8, 8, 8], [8, 8, 8])
        True
        >>> validate_exact('hello', 'world')
        False
    """
    # Direct equality check first
    if value == expected:
        return True

    # Try numeric comparison for int/float/string conversions
    try:
        if isinstance(expected, (int, float)) and not isinstance(expected, bool):
            return float(value) == float(expected)
    except (TypeError, ValueError):
        pass

    # Try list/tuple comparison (e.g., BitsPerSample multi-band)
    if isinstance(expected, (list, tuple)) and isinstance(value, (list, tuple)):
        if len(expected) != len(value):
            return False
        try:
            return all(
                validate_exact(v, e)
                for v, e in zip(value, expected)
            )
        except (TypeError, ValueError):
            return False

    return False


def validate_enum(value: Any, expected: List[Any]) -> bool:
    """
    Validate that value is in the list of allowed values.

    Performs type-aware membership check, attempting numeric conversion
    when comparing numbers.

    Args:
        value: The actual value to validate
        expected: List of allowed values

    Returns:
        True if value is in the list, False otherwise

    Examples:
        >>> validate_enum(5, [5, 8, 50000])
        True
        >>> validate_enum('5', [5, 8, 50000])
        True
        >>> validate_enum(1, [5, 8, 50000])
        False
    """
    if not isinstance(expected, (list, tuple)):
        raise ValueError(f"Enum constraint requires a list, got: {type(expected)}")

    # Direct membership check
    if value in expected:
        return True

    # Try numeric comparison
    try:
        numeric_value = float(value)
        for allowed in expected:
            if isinstance(allowed, (int, float)) and not isinstance(allowed, bool):
                if numeric_value == float(allowed):
                    return True
    except (TypeError, ValueError):
        pass

    return False


def validate_regex(value: Any, pattern: str) -> bool:
    """
    Validate that value matches a regular expression pattern.

    Converts value to string before matching if necessary.

    Args:
        value: The actual value to validate
        pattern: The regex pattern to match against

    Returns:
        True if value matches the pattern, False otherwise

    Examples:
        >>> validate_regex('2025:01:15 12:30:00', r'^\\d{4}:\\d{2}:\\d{2} \\d{2}:\\d{2}:\\d{2}$')
        True
        >>> validate_regex('01/15/2025', r'^\\d{4}-\\d{2}-\\d{2}$')
        False
    """
    if value is None:
        return False

    # Convert to string if not already
    if not isinstance(value, str):
        value = str(value)

    try:
        return bool(re.match(pattern, value))
    except re.error as e:
        raise ValueError(f"Invalid regex pattern '{pattern}': {e}")


def validate_range(value: Any, range_spec: Dict[str, Union[int, float]]) -> bool:
    """
    Validate that value is within a single range.

    If value is a list/tuple (e.g., from multi-band statistics), ALL elements
    must be within range for validation to pass.

    Args:
        value: The actual value to validate (scalar or list)
        range_spec: Dictionary with 'min' and/or 'max' keys

    Returns:
        True if value (or all values in list) is within range, False otherwise

    Examples:
        >>> validate_range(127.5, {'min': 0, 'max': 255})
        True
        >>> validate_range(-9999, {'min': -430, 'max': 8850})
        False
        >>> validate_range(100, {'min': 0})  # No upper bound
        True
        >>> validate_range([100, 200, 150], {'min': 0, 'max': 255})  # List: all pass
        True
        >>> validate_range([100, 300, 150], {'min': 0, 'max': 255})  # List: one fails
        False
    """
    if value is None:
        return False

    # Handle list/tuple values (e.g., multi-band statistics)
    if isinstance(value, (list, tuple)):
        if len(value) == 0:
            return False
        # All values must pass
        return all(_validate_single_range(v, range_spec) for v in value)

    return _validate_single_range(value, range_spec)


def _validate_single_range(value: Any, range_spec: Dict[str, Union[int, float]]) -> bool:
    """
    Validate a single scalar value against a range.

    Args:
        value: The actual value to validate (scalar)
        range_spec: Dictionary with 'min' and/or 'max' keys

    Returns:
        True if value is within range, False otherwise
    """
    if value is None:
        return False

    # Convert value to float for comparison
    try:
        num_value = float(value)
    except (TypeError, ValueError):
        return False

    min_val = range_spec.get('min')
    max_val = range_spec.get('max')

    # Check minimum bound
    if min_val is not None:
        if num_value < float(min_val):
            return False

    # Check maximum bound
    if max_val is not None:
        if num_value > float(max_val):
            return False

    return True


def validate_ranges(value: Any, ranges: List[Dict[str, Union[int, float]]]) -> bool:
    """
    Validate that value is within at least one of multiple ranges.

    If value is a list/tuple (e.g., from multi-band statistics), ALL elements
    must be within at least one of the ranges for validation to pass.

    Args:
        value: The actual value to validate (scalar or list)
        ranges: List of range dictionaries, each with 'min' and/or 'max' keys

    Returns:
        True if value (or all values in list) is within any of the ranges, False otherwise

    Examples:
        >>> validate_ranges(32615, [
        ...     {'min': 32601, 'max': 32660},  # UTM North
        ...     {'min': 32701, 'max': 32760},  # UTM South
        ... ])
        True
        >>> validate_ranges(4326, [
        ...     {'min': 32601, 'max': 32660},
        ...     {'min': 32701, 'max': 32760},
        ... ])
        False
        >>> validate_ranges([32615, 32710], [  # List: each in different range
        ...     {'min': 32601, 'max': 32660},
        ...     {'min': 32701, 'max': 32760},
        ... ])
        True
    """
    if not isinstance(ranges, (list, tuple)):
        raise ValueError(f"Ranges constraint requires a list, got: {type(ranges)}")

    # Handle list/tuple values (e.g., multi-band statistics)
    if isinstance(value, (list, tuple)):
        if len(value) == 0:
            return False
        # All values must be in at least one range
        return all(_validate_single_ranges(v, ranges) for v in value)

    return _validate_single_ranges(value, ranges)


def _validate_single_ranges(value: Any, ranges: List[Dict[str, Union[int, float]]]) -> bool:
    """
    Validate a single scalar value is within at least one of multiple ranges.

    Args:
        value: The actual value to validate (scalar)
        ranges: List of range dictionaries

    Returns:
        True if value is within any of the ranges, False otherwise
    """
    for range_spec in ranges:
        if _validate_single_range(value, range_spec):
            return True
    return False


def validate_exists(value: Any) -> bool:
    """
    Validate that value exists (is not None and not empty).

    Args:
        value: The actual value to validate

    Returns:
        True if value exists and is not empty, False otherwise

    Examples:
        >>> validate_exists('Sample DEM')
        True
        >>> validate_exists('')
        False
        >>> validate_exists(None)
        False
        >>> validate_exists(0)
        True
        >>> validate_exists([])
        False
    """
    if value is None:
        return False

    # Empty string check
    if isinstance(value, str) and value.strip() == '':
        return False

    # Empty collection check
    if isinstance(value, (list, tuple, dict)) and len(value) == 0:
        return False

    return True


def validate_forbidden(value: Any) -> bool:
    """
    Validate that value does NOT exist.

    Used for fields that should not be present in compliant files.

    Args:
        value: The actual value to validate

    Returns:
        True if value is None (forbidden field correctly absent),
        False if value exists (forbidden field incorrectly present)

    Examples:
        >>> validate_forbidden(None)
        True
        >>> validate_forbidden(42)
        False
        >>> validate_forbidden('')
        False
    """
    return value is None


# =============================================================================
# Extended Data Type Validators (Phase 5)
# =============================================================================

# ISO 8601 date pattern: YYYY-MM-DD
DATE_PATTERN = re.compile(
    r'^(\d{4})-(\d{2})-(\d{2})$'
)

# ISO 8601 datetime pattern: YYYY-MM-DDThh:mm:ss[.sss][Z|±hh:mm]
DATETIME_PATTERN = re.compile(
    r'^(\d{4})-(\d{2})-(\d{2})[T ]'  # Date part
    r'(\d{2}):(\d{2}):(\d{2})'  # Time part
    r'(?:\.(\d{1,6}))?'  # Optional microseconds
    r'(Z|[+-]\d{2}:\d{2})?$'  # Optional timezone
)

# Email pattern (simplified but comprehensive)
EMAIL_PATTERN = re.compile(
    r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
)


def validate_date_format(value: Any) -> Tuple[bool, Optional[str]]:
    """
    Validate that value is a valid ISO 8601 date (YYYY-MM-DD).

    Args:
        value: The value to validate

    Returns:
        Tuple of (is_valid, error_message)
        - (True, None) if valid
        - (False, error_message) if invalid

    Examples:
        >>> validate_date_format('2025-01-15')
        (True, None)
        >>> validate_date_format('2025-13-01')
        (False, 'Invalid month: 13')
        >>> validate_date_format('01/15/2025')
        (False, 'Invalid date format...')
    """
    if value is None:
        return False, 'Value is None'

    str_value = str(value)
    match = DATE_PATTERN.match(str_value)

    if not match:
        return False, f"Invalid date format: '{str_value}'. Expected YYYY-MM-DD"

    year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))

    # Validate month
    if month < 1 or month > 12:
        return False, f"Invalid month: {month}"

    # Validate day
    days_in_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

    # Handle leap year for February
    is_leap = (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)
    if is_leap:
        days_in_month[1] = 29

    if day < 1 or day > days_in_month[month - 1]:
        return False, f"Invalid day: {day} for month {month}"

    return True, None


def validate_datetime_format(value: Any) -> Tuple[bool, Optional[str]]:
    """
    Validate that value is a valid ISO 8601 datetime.

    Supports formats:
    - YYYY-MM-DDThh:mm:ss
    - YYYY-MM-DDThh:mm:ssZ
    - YYYY-MM-DDThh:mm:ss.sss
    - YYYY-MM-DDThh:mm:ss+hh:mm
    - YYYY-MM-DDThh:mm:ss.sss-hh:mm

    Args:
        value: The value to validate

    Returns:
        Tuple of (is_valid, error_message)

    Examples:
        >>> validate_datetime_format('2025-01-15T12:30:00')
        (True, None)
        >>> validate_datetime_format('2025-01-15T12:30:00Z')
        (True, None)
        >>> validate_datetime_format('2025-01-15T12:30:00+05:30')
        (True, None)
        >>> validate_datetime_format('2025-01-15 12:30:00')
        (True, None)
    """
    if value is None:
        return False, 'Value is None'

    str_value = str(value)
    match = DATETIME_PATTERN.match(str_value)

    if not match:
        return False, f"Invalid datetime format: '{str_value}'. Expected ISO 8601 datetime"

    year = int(match.group(1))
    month = int(match.group(2))
    day = int(match.group(3))
    hour = int(match.group(4))
    minute = int(match.group(5))
    second = int(match.group(6))

    # Validate date components
    is_valid, error = validate_date_format(f"{year:04d}-{month:02d}-{day:02d}")
    if not is_valid:
        return False, error

    # Validate time components
    if hour < 0 or hour > 23:
        return False, f"Invalid hour: {hour}"
    if minute < 0 or minute > 59:
        return False, f"Invalid minute: {minute}"
    if second < 0 or second > 59:
        return False, f"Invalid second: {second}"

    return True, None


def validate_url_format(value: Any) -> Tuple[bool, Optional[str]]:
    """
    Validate that value is a valid URL.

    Supports http://, https://, ftp:// and s3:// schemes.

    Args:
        value: The value to validate

    Returns:
        Tuple of (is_valid, error_message)

    Examples:
        >>> validate_url_format('https://example.com/path')
        (True, None)
        >>> validate_url_format('ftp://files.example.com/data.zip')
        (True, None)
        >>> validate_url_format('not-a-url')
        (False, 'Invalid URL format...')
    """
    if value is None:
        return False, 'Value is None'

    str_value = str(value)

    try:
        result = urlparse(str_value)

        # Check for valid scheme
        if result.scheme not in ('http', 'https', 'ftp', 'ftps', 'sftp', 's3'):
            return False, f"Invalid URL scheme: '{result.scheme}'. Expected http, https, ftp, ftps, sftp, or s3"

        # Check for netloc (domain)
        if not result.netloc:
            return False, f"Invalid URL: missing domain in '{str_value}'"

        return True, None

    except Exception as e:
        return False, f"Invalid URL format: '{str_value}'. Error: {e}"


def validate_email_format(value: Any) -> Tuple[bool, Optional[str]]:
    """
    Validate that value is a valid email address.

    Args:
        value: The value to validate

    Returns:
        Tuple of (is_valid, error_message)

    Examples:
        >>> validate_email_format('user@example.com')
        (True, None)
        >>> validate_email_format('invalid-email')
        (False, 'Invalid email format...')
    """
    if value is None:
        return False, 'Value is None'

    str_value = str(value)

    if not EMAIL_PATTERN.match(str_value):
        return False, f"Invalid email format: '{str_value}'"

    return True, None


def validate_data_type(value: Any, data_type: str) -> Tuple[bool, Optional[str]]:
    """
    Validate that a value conforms to the specified data type.

    Args:
        value: The value to validate
        data_type: The expected data type ('string', 'integer', 'float',
                   'boolean', 'date', 'datetime', 'url', 'email')

    Returns:
        Tuple of (is_valid, error_message)

    Examples:
        >>> validate_data_type('2025-01-15', 'date')
        (True, None)
        >>> validate_data_type('https://example.com', 'url')
        (True, None)
        >>> validate_data_type(42, 'integer')
        (True, None)
    """
    if value is None:
        return False, 'Value is None'

    # Basic types - just check if conversion is possible
    if data_type == 'string':
        return True, None

    elif data_type == 'integer':
        try:
            int(value)
            return True, None
        except (ValueError, TypeError):
            return False, f"Value '{value}' is not a valid integer"

    elif data_type == 'float':
        try:
            float(value)
            return True, None
        except (ValueError, TypeError):
            return False, f"Value '{value}' is not a valid float"

    elif data_type == 'boolean':
        if isinstance(value, bool):
            return True, None
        if isinstance(value, str):
            if value.lower() in ('true', 'false', 'yes', 'no', '1', '0'):
                return True, None
        return False, f"Value '{value}' is not a valid boolean"

    # Extended types (Phase 5)
    elif data_type == 'date':
        return validate_date_format(value)

    elif data_type == 'datetime':
        return validate_datetime_format(value)

    elif data_type == 'url':
        return validate_url_format(value)

    elif data_type == 'email':
        return validate_email_format(value)

    else:
        # Unknown type - pass through
        return True, None


def apply_constraint(
    value: Any,
    constraint: str,
    expected: Any = None
) -> bool:
    """
    Apply the appropriate constraint validation function.

    Args:
        value: The actual value to validate
        constraint: The constraint type ('exact', 'enum', 'regex', etc.)
        expected: The expected value(s) for the constraint

    Returns:
        True if validation passes, False otherwise

    Raises:
        ValueError: If constraint type is unknown
    """
    constraint_functions = {
        'exact': lambda v, e: validate_exact(v, e),
        'enum': lambda v, e: validate_enum(v, e),
        'regex': lambda v, e: validate_regex(v, e),
        'range': lambda v, e: validate_range(v, e),
        'ranges': lambda v, e: validate_ranges(v, e),
        'exists': lambda v, e: validate_exists(v),
        'forbidden': lambda v, e: validate_forbidden(v),
    }

    if constraint not in constraint_functions:
        raise ValueError(f"Unknown constraint type: '{constraint}'")

    return constraint_functions[constraint](value, expected)
