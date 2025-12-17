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
Histogram Generator for Raster Statistics.

This utility generates elegant multi-band histograms from comprehensive raster statistics data.
It is designed to be called separately from the main statistics calculation
to isolate the matplotlib dependency, which can cause issues in specific
environments like ArcGIS Pro.
"""
import base64
import io
import logging
from matplotlib.axes import Axes
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
from typing import Dict, Any, Optional, cast
from gttk.utils.colors import ColorManager

# Configure logging
logger = logging.getLogger(__name__)

def generate_histogram_base64(stats_data: Dict[str, Any], file_name: str, figure_size: tuple = (8, 6)) -> Optional[str]:
    """
    Generates an elegant multi-band histogram with dual Y-axes for alpha bands.
    
    Alpha bands are plotted on a separate Y-axis to prevent their extreme values
    from suppressing RGB band visibility.
    
    Args:
        stats_data: Dictionary with keys:
            - band_histogram_counts: List of count arrays per band
            - band_histogram_bins: List of bin edge arrays per band
            - band_names: List of band names
        file_name: Name of file for plot title
        figure_size: Figure size as (width, height) tuple
        
    Returns:
        Base64-encoded PNG image string, or None on error
    """
    band_counts = stats_data.get("band_histogram_counts")
    band_bins = stats_data.get("band_histogram_bins")
    band_names = stats_data.get("band_names")
    
    if not band_counts or not band_bins or not band_names:
        logger.warning("Missing histogram data for generation.")
        return None
    
    if len(band_counts) != len(band_bins) or len(band_counts) != len(band_names):
        logger.warning("Mismatched histogram data lengths.")
        return None

    # Initialize Color Manager
    color_manager = ColorManager(band_names)

    fig = None
    try:
        fig, ax1 = plt.subplots(figsize=figure_size)
        ax2 = None  # Second axis for alpha (created if needed)
        
        # Separate alpha from other bands
        alpha_bands = []
        rgb_bands = []
        
        for i, (counts, bins, name) in enumerate(zip(band_counts, band_bins, band_names)):
            if 'alpha' in name.lower():
                alpha_bands.append((i, counts, bins, name))
            else:
                rgb_bands.append((i, counts, bins, name))
        
        # Determine if byte data for x-axis limits (check RGB bands only)
        is_byte_data = False
        if rgb_bands:
            is_byte_data = all(
                bins[0] == 0 and bins[-1] == 256
                for _, _, bins, _ in rgb_bands if len(bins) > 0
            )

        if alpha_bands:
            ax2 = cast(Axes, ax1.twinx())  # Create second Y-axis
            
            max_alpha_density = 0  # Track max for scaling
            max_alpha_density = 0  # Track max for scaling
            
            for i, counts, bin_edges, band_name in alpha_bands:
                if len(counts) == 0 or len(bin_edges) == 0:
                    continue
                
                counts = np.array(counts)
                bin_edges = np.array(bin_edges)
                
                color = '#808080'  # Gray for alpha
                
                # Convert to density
                bin_widths = np.diff(bin_edges)
                total_area = np.sum(counts * bin_widths)
                density = counts / total_area if total_area > 0 else counts
                
                max_alpha_density = max(max_alpha_density, np.max(density) if len(density) > 0 else 0)
                
                # Plot on RIGHT axis (ax2)
                ax2.bar(bin_edges[:-1], density, width=bin_widths,
                       color=color + '44',  # More transparent
                       label=band_name, align='edge',
                       edgecolor=None, linewidth=0,
                       zorder=1)  # Low z-order (behind)
                
                # Outline
                x_line = np.repeat(bin_edges, 2)
                y_line = np.maximum(np.hstack(([0], np.repeat(density, 2), [0])), 1e-9)
                ax2.plot(x_line, y_line, color=color, linewidth=1.5, zorder=1)
            
            # Style right axis with appropriate limits
            ax2.set_ylabel('Probability Density (Alpha Band)', color='#808080')
            ax2.tick_params(axis='y', labelcolor='#808080')
            ax2.grid(False)  # No grid for alpha axis
            
            # Set reasonable y-axis limits for alpha (prevent extreme values)
            if max_alpha_density > 0:
                ax2.set_ylim(0, max_alpha_density * 1.1)
            
            # Limit the number of ticks to avoid clutter
            ax2.yaxis.set_major_locator(mticker.MaxNLocator(nbins=5))
        
        # PLOT RGB BANDS (on top of alpha)
        for idx, (i, counts, bin_edges, band_name) in enumerate(rgb_bands):
            if len(counts) == 0 or len(bin_edges) == 0:
                continue
            
            # Convert to numpy arrays for calculations
            counts = np.array(counts)
            bin_edges = np.array(bin_edges)
                
            # Safely resolve color using ColorManager
            color = color_manager.get_color(i, band_name)
            
            # Convert counts to probability density
            bin_widths = np.diff(bin_edges)
            total_area = np.sum(counts * bin_widths)
            density = counts / total_area if total_area > 0 else counts

            # Plot on LEFT axis (ax1)
            ax1.bar(bin_edges[:-1], density, width=bin_widths,
                   color=color + '44',
                   label=band_name, align='edge',
                   edgecolor=None, linewidth=0,
                   zorder=2)  # High z-order (on top)

            # Create the exterior line of the histogram by tracing the bin edges
            x_line = np.repeat(bin_edges, 2)
            y_line = np.maximum(np.hstack(([0], np.repeat(density, 2), [0])), 1e-9)
            ax1.plot(x_line, y_line, color=color, linewidth=1.5, zorder=2)

        # Style left axis
        ax1.set_xlabel('Pixel Value')
        ax1.set_ylabel('Probability Density')
        ax1.grid(True, which='both', linestyle='--', linewidth=0.5, zorder=0)
        
        # Combined legend
        lines1, labels1 = ax1.get_legend_handles_labels()
        if ax2:
            lines2, labels2 = ax2.get_legend_handles_labels()
            legend = ax1.legend(lines1 + lines2, labels1 + labels2,
                              loc='upper right', frameon=True)
        else:
            legend = ax1.legend(loc='upper right', frameon=True)
        
        # Style legend patches
        for patch in legend.get_patches():
            # Get the facecolor, set alpha to 1.0 for a solid edge
            face_color = patch.get_facecolor()
            edge_color = mcolors.to_rgba(face_color[:3], 1.0)
            patch.set_edgecolor(edge_color)
            patch.set_linewidth(1.5)
        
        # Set x-axis limits for byte data
        if is_byte_data:
            ax1.set_xlim(0, 256)
            if ax2:
                ax2.set_xlim(0, 256)
        
        fig.tight_layout()
        plt.title(file_name, fontsize=10, weight='bold')
        plt.subplots_adjust(top=0.95)  # remove whitespace above chart

        buf = io.BytesIO()
        fig.savefig(buf, format='png')
        plt.close(fig)
        buf.seek(0)
        hist_base64 = base64.b64encode(buf.read()).decode('utf-8')
        
        return hist_base64

    except Exception as e:
        logger.error(f"An error occurred during histogram generation: {e}", exc_info=True)
        if fig is not None:
            try:
                plt.close(fig)
            except Exception as e:
                logger.error(f"An error occurred while closing the figure: {e}", exc_info=True)
        return None