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
TOML Loader for Validation Rules.

This module handles loading and parsing TOML validation rule files,
including conflict detection for duplicate product names across files.

Functions:
    load_validation_rules: Load rules for a specific product from TOML files
    parse_rule: Parse a rule dictionary from TOML into ValidationRule object
    get_available_products: List all available products in rules directory
"""

import logging
import tomllib
from importlib import resources
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from gttk.utils.validation.models import ValidationRule

logger = logging.getLogger(__name__)

# Mapping from section type to the key field name in TOML
KEY_FIELD_MAP = {
    'tag': 'tag',
    'geokey': 'geokey',
    'gdal': 'name',
    'geo': 'xpath',
    'xmp': 'xpath',
    'xml': 'xpath',
    'projjson': 'jsonpath',
}

# Valid section types
VALID_SECTIONS = list(KEY_FIELD_MAP.keys())


def bundled_rules_dir() -> Path:
    """
    The directory of rule files that ships inside the package.

    This is the default for ``gttk validate --rules-dir`` and for the toolbox's
    Rules Directory parameter. It is located through the package rather than the
    working directory, so the default holds wherever GTTK is run from and
    whether it is a checkout or an installed wheel.

    Example:
        >>> sorted(p.name for p in bundled_rules_dir().glob('*.toml'))
        ['example_rules.toml']
    """
    return Path(str(resources.files('gttk.resources').joinpath('rules')))


def load_validation_rules(
    rules_dir: Path,
    product: str,
    sections: Optional[List[str]] = None
) -> Tuple[Dict[str, List[ValidationRule]], str]:
    """
    Load validation rules for a specific product from TOML files.

    Scans the rules directory for all .toml files, detects conflicts
    (same product defined in multiple files), and returns the rules
    for the requested product.

    Args:
        rules_dir: Directory containing TOML validation rule files
        product: Product name to load rules for (e.g., 'DGED5', 'GLO-30')
        sections: Optional list of section types to load (filters rules)

    Returns:
        Tuple of:
        - Dict mapping section names to lists of ValidationRule objects
        - Name of the TOML file containing the product rules

    Raises:
        ValueError: If product not found or duplicate products detected

    Example:
        >>> rules_dir = bundled_rules_dir()
        >>> rules, filename = load_validation_rules(
        ...     rules_dir,
        ...     'DGED5',
        ...     sections=['tag', 'geokey']
        ... )
        >>> sorted(rules)
        ['geokey', 'tag']
        >>> filename
        'example_rules.toml'
    """
    # 1. Find all TOML files
    toml_files = list(rules_dir.glob('*.toml'))
    logger.debug(f"Found {len(toml_files)} TOML files in {rules_dir}")

    if not toml_files:
        raise ValueError(f"No TOML rule files found in: {rules_dir}")

    # 2. Load and parse all files, checking for conflicts
    all_products: Dict[str, dict] = {}
    product_sources: Dict[str, str] = {}  # Track which file each product came from

    for toml_file in toml_files:
        try:
            with open(toml_file, 'rb') as f:
                data = tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            logger.error(f"Failed to parse TOML file {toml_file.name}: {e}")
            raise ValueError(f"Invalid TOML syntax in {toml_file.name}: {e}")

        # Check each top-level key (product name)
        for prod_name in data.keys():
            if prod_name in all_products:
                # Conflict detected!
                raise ValueError(
                    f"Product '{prod_name}' found in multiple files:\n"
                    f"  - {product_sources[prod_name]}\n"
                    f"  - {toml_file.name}\n"
                    f"Please consolidate rules into a single file."
                )
            all_products[prod_name] = data[prod_name]
            product_sources[prod_name] = toml_file.name

    # 3. Check if requested product exists
    if product not in all_products:
        available = ', '.join(sorted(all_products.keys()))
        raise ValueError(
            f"Product '{product}' not found in rules directory.\n"
            f"Available products: {available}"
        )

    # 4. Parse rules for the requested product
    product_data = all_products[product]
    rules_by_section: Dict[str, List[ValidationRule]] = {}

    for section_name in VALID_SECTIONS:
        if section_name not in product_data:
            continue

        # Apply section filter if provided
        if sections and section_name not in sections:
            continue

        # Parse each rule in this section
        section_rules = []
        for rule_dict in product_data[section_name]:
            try:
                rule = parse_rule(product, section_name, rule_dict)
                section_rules.append(rule)
            except (KeyError, ValueError) as e:
                logger.error(
                    f"Failed to parse rule in [{product}.{section_name}]: {e}"
                )
                raise ValueError(
                    f"Invalid rule in [{product}.{section_name}]: {e}"
                )

        if section_rules:
            rules_by_section[section_name] = section_rules

    # 5. Log summary
    total_rules = sum(len(rules) for rules in rules_by_section.values())
    logger.info(
        f"Loaded {total_rules} rules for product '{product}' "
        f"from {product_sources[product]}"
    )
    for section, rules in rules_by_section.items():
        logger.debug(f"  - {section}: {len(rules)} rules")

    return rules_by_section, product_sources[product]


def parse_rule(product: str, section: str, rule_dict: dict) -> ValidationRule:
    """
    Parse a rule dictionary from TOML into ValidationRule object.

    Converts section-specific key fields (tag, geokey, name, xpath, jsonpath)
    to the generic 'key' field in the ValidationRule model.

    Args:
        product: Product name
        section: Section type (e.g., 'tag', 'geokey', 'gdal')
        rule_dict: Raw dictionary from TOML

    Returns:
        ValidationRule object

    Raises:
        KeyError: If required field is missing from rule_dict
        ValueError: If rule validation fails

    Example:
        >>> rule_dict = {
        ...     'tag': 258,
        ...     'description': 'BitsPerSample',
        ...     'data_type': 'integer',
        ...     'constraint': 'exact',
        ...     'expected': 32
        ... }
        >>> rule = parse_rule('DGED5', 'tag', rule_dict)
        >>> rule.key
        '258'
    """
    # Get the key field name for this section type
    key_field = KEY_FIELD_MAP.get(section)
    if key_field is None:
        raise ValueError(f"Unknown section type: '{section}'")

    # Extract the key value
    if key_field not in rule_dict:
        raise KeyError(
            f"Missing required field '{key_field}' for section '{section}'"
        )
    key_value = str(rule_dict[key_field])  # Convert to string for consistency

    # Extract required fields
    required_fields = ['description', 'data_type', 'constraint']
    for field_name in required_fields:
        if field_name not in rule_dict:
            raise KeyError(f"Missing required field '{field_name}'")

    # Build and return the ValidationRule
    return ValidationRule(
        product=product,
        section=section,
        key=key_value,
        key_type=key_field,
        description=rule_dict['description'],
        data_type=rule_dict['data_type'],
        constraint=rule_dict['constraint'],
        expected=rule_dict.get('expected'),
        optional=rule_dict.get('optional', False),
        comment=rule_dict.get('comment')
    )


def get_available_products(rules_dir: Path) -> Dict[str, str]:
    """
    Get all available products in the rules directory.

    Scans all TOML files and returns a mapping of product names
    to their source files.

    Args:
        rules_dir: Directory containing TOML validation rule files

    Returns:
        Dict mapping product names to source file names

    Raises:
        ValueError: If duplicate products are detected

    Example:
        >>> rules_dir = bundled_rules_dir()
        >>> products = get_available_products(rules_dir)
        >>> products['DGED5']
        'example_rules.toml'
    """
    toml_files = list(rules_dir.glob('*.toml'))

    if not toml_files:
        return {}

    products: Dict[str, str] = {}

    for toml_file in toml_files:
        try:
            with open(toml_file, 'rb') as f:
                data = tomllib.load(f)
        except tomllib.TOMLDecodeError:
            logger.warning(f"Skipping invalid TOML file: {toml_file.name}")
            continue

        for prod_name in data.keys():
            if prod_name in products:
                raise ValueError(
                    f"Product '{prod_name}' found in multiple files:\n"
                    f"  - {products[prod_name]}\n"
                    f"  - {toml_file.name}"
                )
            products[prod_name] = toml_file.name

    return products


def get_product_metadata(rules_dir: Path, product: str) -> dict:
    """
    Get metadata for a specific product (title, description, author, updated).

    Args:
        rules_dir: Directory containing TOML validation rule files
        product: Product name to get metadata for

    Returns:
        Dict with metadata fields (title, description, author, updated)

    Raises:
        ValueError: If product not found
    """
    toml_files = list(rules_dir.glob('*.toml'))

    for toml_file in toml_files:
        try:
            with open(toml_file, 'rb') as f:
                data = tomllib.load(f)
        except tomllib.TOMLDecodeError:
            continue

        if product in data:
            product_data = data[product]
            return {
                'title': product_data.get('title', product),
                'description': product_data.get('description', ''),
                'author': product_data.get('author', ''),
                'updated': product_data.get('updated', ''),
            }

    raise ValueError(f"Product '{product}' not found in rules directory")
