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
A vertical CRS with no EPSG code, for exercising GTTK's generic custom-datum path.

GTTK accepts a vertical SRS as WKT so that a datum the EPSG registry does not know
can still be written into a compound CRS.  The GeoTIFF GeoKeys cannot carry such a
datum (VerticalDatumGeoKey becomes 32767, "user-defined", and it reads back as
VDATUM["unknown"]), so the writers store the full WKT2 in the COMPOUND_CRS_WKT2
metadata item and the reader recovers it from there.

The tests for that path used to drive it with "GGM10", a Mexican geoid model that
GTTK once shipped as an invented vertical CRS.  A geoid model is the transformation
between ellipsoidal and orthometric heights, not a datum -- Mexico's datum is NAVD88
(EPSG:5703), and GGM10 is how you get onto it -- so that entry is gone, and the tests
need a stand-in that makes no claim about the real world.

``CUSTOM_VERTICAL_WKT`` is that stand-in: a deliberately fictional local datum under
an authority ("GTTK-TEST") no registry will ever resolve, which is the property under
test.  Assertions look for "Test Local" in names and WKT; it is distinctive enough not
to collide with anything GDAL or PROJ emit on their own.

``CUSTOM_VERTICAL_WKT_NO_AUTHORITY`` is the same CRS without the ``ID[]``.  The two
differ in one way that matters to ``create_compound_srs``: a vertical CRS that carries
*any* authority code goes through ``SetCompoundCS``, while one with none is stitched
into a WKT2 ``COMPOUNDCRS`` by hand, because ``SetCompoundCS`` can downgrade such a
datum to "unknown".  Both branches deserve a test.
"""

CUSTOM_VERTICAL_WKT = '''VERTCRS["Test Local height", VDATUM["Test Local Vertical Datum 2000"], CS[vertical,1], AXIS["gravity-related height (H)",up, LENGTHUNIT["metre",1]], ID["GTTK-TEST","LOCAL2000"]]'''

CUSTOM_VERTICAL_WKT_NO_AUTHORITY = CUSTOM_VERTICAL_WKT.replace(
    ', ID["GTTK-TEST","LOCAL2000"]', '')
assert CUSTOM_VERTICAL_WKT_NO_AUTHORITY != CUSTOM_VERTICAL_WKT, "the ID[] clause moved"

# The names the WKT declares, for assertions that want the exact string.
CUSTOM_VERTICAL_CRS_NAME = "Test Local height"
CUSTOM_VERTICAL_DATUM_NAME = "Test Local Vertical Datum 2000"
