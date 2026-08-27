#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ******************************************************************************
# Project: GeoTIFF ToolKit
# Author: Eric Robeck <robeckgeo@gmail.com>
#
# Copyright (c) 2026, Eric Robeck
# Licensed under the MIT License
# ******************************************************************************

"""
The ArcGIS optimize path is only ever run from inside ArcGIS Pro, where nothing in
this suite can follow it.  Two of its failure modes were invisible for that reason:
its public entry point named ``gdal_env`` and ``GDAL_OPTIONS_ARC`` without importing
them (a NameError on every toolbox run), and its log lines had no handler to reach
the geoprocessing pane.  These tests pin the wiring that the toolbox depends on.
"""

import inspect
import logging

import pytest

import gttk.tools.optimize_compression_arc as oc
from gttk.utils.gdal_env import gdal_env, GDAL_OPTIONS_ARC
from gttk.utils.log_helpers import ArcpyLogHandler, PACKAGE_LOGGER, setup_logger

pytestmark = pytest.mark.unit


@pytest.fixture
def bare_gttk_logger():
    """The package logger with no handlers, restored afterwards."""
    logger = logging.getLogger(PACKAGE_LOGGER)
    saved_handlers, saved_propagate, saved_level = logger.handlers[:], logger.propagate, logger.level
    for handler in saved_handlers:
        logger.removeHandler(handler)
    yield logger
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    for handler in saved_handlers:
        logger.addHandler(handler)
    logger.propagate, logger.level = saved_propagate, saved_level


class TestArcEntryPoint:
    def test_binds_the_gdal_options_it_applies(self):
        assert oc.gdal_env is gdal_env
        assert oc.GDAL_OPTIONS_ARC is GDAL_OPTIONS_ARC
        # The ARC variant exists to read compound CRSs from WKT; losing it would be silent.
        assert GDAL_OPTIONS_ARC['GTIFF_SRS_SOURCE'] == 'WKT'

    def test_public_entry_point_applies_the_arc_options(self):
        source = inspect.getsource(oc.optimize_compression)
        assert 'gdal_env(GDAL_OPTIONS_ARC)' in source

    def test_arc_mode_routes_logging_to_the_pane(self):
        source = inspect.getsource(oc.optimize_compression)
        assert '_arc_pane_logging(args.arc_mode or False)' in source


class TestArcPaneLogging:
    @staticmethod
    def _arc_handlers(logger):
        return [h for h in logger.handlers if isinstance(h, ArcpyLogHandler)]

    def test_adds_one_handler_for_the_call_only(self, bare_gttk_logger):
        level_before = bare_gttk_logger.level
        with oc._arc_pane_logging(True):
            with oc._arc_pane_logging(True):
                assert len(self._arc_handlers(bare_gttk_logger)) == 1
                assert bare_gttk_logger.getEffectiveLevel() <= logging.INFO
        assert self._arc_handlers(bare_gttk_logger) == []
        assert bare_gttk_logger.level == level_before

    def test_keeps_a_handler_another_tool_installed(self, bare_gttk_logger):
        setup_logger(is_arc_mode=True)
        existing = self._arc_handlers(bare_gttk_logger)[0]
        with oc._arc_pane_logging(True):
            assert self._arc_handlers(bare_gttk_logger) == [existing]
        assert self._arc_handlers(bare_gttk_logger) == [existing]

    def test_disabled_outside_arcgis(self, bare_gttk_logger):
        with oc._arc_pane_logging(False):
            assert self._arc_handlers(bare_gttk_logger) == []
