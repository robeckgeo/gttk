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
Scoped GDAL environment for GTTK operations.

GTTK depends on a handful of GDAL configuration options, and on GDAL's Python
exceptions being enabled.  Both used to be switched on at *import* time, which made
them process-global for anything that so much as imported a GTTK module:

- ``OSR_WKT_FORMAT=WKT2_2019`` changes how every ``ExportToWkt`` in the process is
  formatted.
- ``GTIFF_SRS_SOURCE=WKT`` changes how every GeoTIFF in the process is *read*.
- ``gdal.UseExceptions()`` changes how every GDAL call in the process reports failure.

None of that is GTTK's to decide for an application that only wanted to call one
function.  The options now apply for the duration of a GTTK operation and are restored
afterwards, so importing ``gttk`` changes nothing about the host process.

Functions:
    gdal_env: Context manager applying GTTK's GDAL settings for one operation.
"""

from contextlib import ExitStack, contextmanager
from typing import Mapping, Optional

from osgeo import gdal

#: Configuration GTTK's in-process read/write paths depend on.
GDAL_OPTIONS: dict[str, str] = {
    'GDAL_NUM_THREADS': 'ALL_CPUS',
    'ESRI_XML_PAM': 'TRUE',
    # Force WKT2_2019 formatting and encourage the GTiff driver to preserve the SRS as
    # WKT2 where it can.
    'OSR_WKT_FORMAT': 'WKT2_2019',
    'GTIFF_WRITE_SRS_WKT2': 'YES',
}

#: The ArcGIS/OSGeo4W path additionally prefers the stored WKT when reading, so a
#: compound CRS survives the round-trip through gdal_translate rather than being
#: rebuilt from the GeoTIFF keys.
GDAL_OPTIONS_ARC: dict[str, str] = {**GDAL_OPTIONS, 'GTIFF_SRS_SOURCE': 'WKT'}


@contextmanager
def gdal_env(options: Optional[Mapping[str, str]] = None, use_exceptions: bool = True):
    """Apply GTTK's GDAL settings for the duration of one operation.

    Args:
        options: Configuration to apply. Defaults to :data:`GDAL_OPTIONS`.
        use_exceptions: Enable GDAL's Python exceptions for the duration.

    Nesting is safe and cheap -- an inner call restores the outer call's values, not the
    process defaults -- so an entry point and the helper it delegates to may both use
    this without coordinating.

    The options are set process-wide rather than thread-locally, which is what GTTK did
    before and what its GDAL calls expect; GTTK is not thread-safe regardless (it keeps
    per-run state in module globals). Parallel callers should use processes.
    """
    with ExitStack() as stack:
        stack.enter_context(gdal.config_options(dict(GDAL_OPTIONS if options is None else options),
                                                thread_local=False))
        if use_exceptions:
            stack.enter_context(gdal.ExceptionMgr(useExceptions=True))
        yield
