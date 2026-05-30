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
Raster accuracy metrics.

Compares a (lossily) compressed raster against its original and reports the
numerical error introduced. Kept as a standalone, lightweight utility (only GDAL
and NumPy) so it can be imported without pulling in the optimize tool chain and
its import-time GDAL config side effects.
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
from osgeo import gdal

logger = logging.getLogger(__name__)


def compute_error_metrics(original_path: Path, compressed_path: Path, block: int = 2048) -> Optional[Dict[str, Any]]:
    """Compare a compressed output against the original raster, returning accuracy
    metrics: max absolute error, RMSE, percent of valid pixels changed, and the count
    of distinct values in the compressed raster. Reads in blocks (memory-safe) and
    masks NoData/NaN. Returns None when the rasters are not comparable."""
    orig = comp = None
    try:
        orig = gdal.Open(str(original_path), gdal.GA_ReadOnly)
        comp = gdal.Open(str(compressed_path), gdal.GA_ReadOnly)
        if orig is None or comp is None:
            return None
        if (orig.RasterCount != comp.RasterCount or orig.RasterXSize != comp.RasterXSize
                or orig.RasterYSize != comp.RasterYSize):
            return None
        nx, ny = orig.RasterXSize, orig.RasterYSize
        max_abs = 0.0
        sq_sum = 0.0
        changed = 0
        valid_count = 0
        distinct: set = set()
        distinct_capped = False
        DISTINCT_CAP = 2_000_000
        for b in range(1, orig.RasterCount + 1):
            ob = orig.GetRasterBand(b)
            cb = comp.GetRasterBand(b)
            o_nd = ob.GetNoDataValue()
            c_nd = cb.GetNoDataValue()
            for yoff in range(0, ny, block):
                ysize = min(block, ny - yoff)
                for xoff in range(0, nx, block):
                    xsize = min(block, nx - xoff)
                    oa = ob.ReadAsArray(xoff, yoff, xsize, ysize)
                    ca = cb.ReadAsArray(xoff, yoff, xsize, ysize)
                    if oa is None or ca is None:
                        continue
                    oa = oa.astype(np.float64)
                    ca = ca.astype(np.float64)
                    mask = np.isfinite(oa) & np.isfinite(ca)
                    if o_nd is not None and not np.isnan(o_nd):
                        mask &= (oa != o_nd)
                    if c_nd is not None and not np.isnan(c_nd):
                        mask &= (ca != c_nd)
                    if not mask.any():
                        continue
                    od = oa[mask]
                    cd = ca[mask]
                    diff = np.abs(od - cd)
                    m = float(diff.max())
                    if m > max_abs:
                        max_abs = m
                    sq_sum += float(np.dot(diff, diff))
                    changed += int(np.count_nonzero(diff))
                    valid_count += int(diff.size)
                    if not distinct_capped:
                        distinct.update(cd.tolist())
                        if len(distinct) > DISTINCT_CAP:
                            distinct_capped = True
        if valid_count == 0:
            return None
        return {
            'max_abs_error': max_abs,
            'rmse': (sq_sum / valid_count) ** 0.5,
            'pct_changed': 100.0 * changed / valid_count,
            'distinct_count': (f">{DISTINCT_CAP}" if distinct_capped else len(distinct)),
        }
    except Exception as e:
        logger.warning(f"compute_error_metrics failed for {compressed_path}: {e}")
        return None
    finally:
        orig = None
        comp = None
