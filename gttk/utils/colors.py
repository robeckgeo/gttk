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
Color Constants and Logic.

This module provides a centralized source for band coloring logic used in
histograms, statistics tables, and metadata highlighting.
"""

from typing import List, Dict, Optional

# Default colors for visualization (histograms, statistics tables, GDAL_METADATA samples)
DEFAULT_COLORS = [
    "#ce0000", "#077000", '#0000ce', "#ce00ce", '#ce5500', 
    '#750000', '#008080', '#3e3e3e', '#808080']

# Specific map for known band names
BAND_COLOR_MAP = {
    'Red': '#ce0000',
    'Green': '#077000',
    'Blue': '#0000ce',
    'NIR': '#ce00ce',
    'SWIR': "#ce5500",
    'TIR': '#750000',
    "Palette": "#008080",
    'Gray': "#3e3e3e",
    'Alpha': '#808080',
    'Undefined': '#3e3e3e',
}

class ColorManager:
    """Manages color assignment for bands."""

    def __init__(self, band_names: List[str]):
        """
        Initialize with the list of band names to be colored.
        
        Args:
            band_names: List of all band names in order.
        """
        self.band_names = band_names
        self.has_duplicate_types = self._check_duplicates(band_names)

    def _check_duplicates(self, band_names: List[str]) -> bool:
        """Check if any band type appears multiple times (excluding alpha)."""
        band_type_counts = {}
        for name in band_names:
            if 'alpha' not in name.lower():
                band_type_counts[name] = band_type_counts.get(name, 0) + 1
        return any(count > 1 for count in band_type_counts.values())

    def get_color(self, index: int, band_name: Optional[str] = None) -> str:
        """
        Get color for a specific band index/name.
        
        Args:
            index: The 0-based index of the band.
            band_name: The name of the band (optional, but recommended).
            
        Returns:
            Hex color string (e.g., '#ff0000').
        """
        if band_name is None:
            if 0 <= index < len(self.band_names):
                band_name = self.band_names[index]
            else:
                band_name = f"Band {index+1}"

        # Logic matching histogram_generator.py
        if self.has_duplicate_types:
            resolved_color = DEFAULT_COLORS[index % len(DEFAULT_COLORS)]
        else:
            resolved_color = BAND_COLOR_MAP.get(band_name)
            if resolved_color is None:
                resolved_color = DEFAULT_COLORS[index % len(DEFAULT_COLORS)]
        
        return resolved_color

    def get_color_map(self) -> Dict[str, str]:
        """Get a map of band_name -> color."""
        return {name: self.get_color(i, name) for i, name in enumerate(self.band_names)}

    def get_index_color_map(self) -> Dict[int, str]:
        """Get a map of band_index -> color."""
        return {i: self.get_color(i, name) for i, name in enumerate(self.band_names)}