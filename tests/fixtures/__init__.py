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
Test fixtures and mock data factories for GTTK tests.

This package contains:
- MockGeoTIFF: Factory for creating in-memory test GeoTIFF files
- Data generators: Functions to create synthetic test data
- Fixture utilities: Helper functions for test setup
"""

from tests.fixtures.mock_geotiff_factory import MockGeoTIFF

__all__ = ['MockGeoTIFF']