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
Importing GTTK must not change the host process.

GTTK used to set GDAL configuration, enable GDAL's Python exceptions, and reconfigure
the root logger at *import* time. All three are process-global, so an application that
imported one GTTK function silently had its GeoTIFF reading, its error handling and its
logging changed underneath it. The settings now apply for the duration of an operation
and are restored afterwards.

The import checks run in a subprocess: once a module is imported into the test session
its side effects have already happened, so asserting on them in-process proves nothing.
"""

import logging
import subprocess
import sys
import textwrap

import pytest
from osgeo import gdal

from gttk.utils.gdal_env import GDAL_OPTIONS, GDAL_OPTIONS_ARC, gdal_env
from gttk.utils.log_helpers import PACKAGE_LOGGER, setup_logger, shutdown_logger

GTTK_MODULES = [
    "gttk",
    "gttk.tools.optimize_compression",
    "gttk.tools.optimize_compression_arc",
    "gttk.tools.compare_compression",
    "gttk.tools.read_metadata",
    "gttk.tools.test_compression",
    "gttk.tools.validate_metadata",
    "gttk.utils.gdal_runner",
    "gttk.utils.validation.gpkg_writer",
]

WATCHED_OPTIONS = sorted(set(GDAL_OPTIONS) | set(GDAL_OPTIONS_ARC))


def _in_subprocess(body: str) -> str:
    """Run `body` in a clean interpreter and return its stdout."""
    result = subprocess.run([sys.executable, "-c", textwrap.dedent(body)],
                            capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, f"subprocess failed:\n{result.stdout}\n{result.stderr}"
    return result.stdout.strip()


class TestImportLeavesGdalAlone:

    def test_import_does_not_set_gdal_config(self):
        out = _in_subprocess(f"""
            from osgeo import gdal
            watched = {WATCHED_OPTIONS!r}
            before = {{k: gdal.GetConfigOption(k) for k in watched}}
            for m in {GTTK_MODULES!r}:
                __import__(m)
            after = {{k: gdal.GetConfigOption(k) for k in watched}}
            print("SAME" if after == before else f"CHANGED {{before}} -> {{after}}")
        """)
        assert out == "SAME", out

    def test_import_does_not_enable_gdal_exceptions(self):
        """gdal.UseExceptions() is process-global and changes how every GDAL call in the
        application reports failure. That is the application's decision, not ours."""
        out = _in_subprocess(f"""
            from osgeo import gdal
            before = gdal.GetUseExceptions()
            for m in {GTTK_MODULES!r}:
                __import__(m)
            print("SAME" if gdal.GetUseExceptions() == before else
                  f"CHANGED {{before}} -> {{gdal.GetUseExceptions()}}")
        """)
        assert out == "SAME", out

    def test_import_does_not_create_directories(self):
        out = _in_subprocess(f"""
            import pathlib
            for m in {GTTK_MODULES!r}:
                __import__(m)
            import gttk
            print((pathlib.Path(gttk.__file__).parent / 'logs').exists())
        """)
        assert out == "False", "importing GTTK created a logs/ directory"


class TestImportLeavesLoggingAlone:

    def test_import_does_not_touch_the_root_logger(self):
        out = _in_subprocess(f"""
            import logging, sys
            root = logging.getLogger()
            root.addHandler(logging.StreamHandler(sys.stderr))
            root.setLevel(logging.INFO)
            handlers, level = list(root.handlers), root.level
            for m in {GTTK_MODULES!r}:
                __import__(m)
            print(root.handlers == handlers and root.level == level)
        """)
        assert out == "True", "importing GTTK reconfigured the root logger"

    def test_import_does_not_quiet_matplotlib(self):
        out = _in_subprocess(f"""
            import logging
            before = logging.getLogger('matplotlib').level
            for m in {GTTK_MODULES!r}:
                __import__(m)
            print(logging.getLogger('matplotlib').level == before)
        """)
        assert out == "True", "importing GTTK changed matplotlib's log level"

    @pytest.mark.parametrize("module", [m for m in GTTK_MODULES if m != "gttk"])
    def test_every_module_logs_under_the_package_name(self, module):
        """A logger named e.g. 'optimize_compression' sits outside any namespace, so it
        collides with other libraries and cannot be configured as a unit."""
        mod = __import__(module, fromlist=["x"])
        logger = getattr(mod, "logger", None)
        if logger is None:
            pytest.skip(f"{module} has no module-level logger")
        assert logger.name.startswith(PACKAGE_LOGGER + "."), logger.name


class TestSetupLogger:

    def test_configures_the_package_logger_not_root(self):
        root = logging.getLogger()
        before = list(root.handlers)
        gttk_logger = setup_logger()
        try:
            assert gttk_logger.name == PACKAGE_LOGGER
            assert root.handlers == before, "setup_logger() disturbed the root logger"
            assert gttk_logger.handlers, "setup_logger() installed no handler"
        finally:
            shutdown_logger(gttk_logger)

    def test_does_not_double_print_into_the_application(self):
        """With a handler of its own, GTTK must stop propagating, or an application with
        a root handler sees every message twice."""
        seen = []

        class Spy(logging.Handler):
            def emit(self, record):
                seen.append(record.getMessage())

        root, spy = logging.getLogger(), Spy()
        root.addHandler(spy)
        old_level, root.level = root.level, logging.INFO
        gttk_logger = setup_logger()
        try:
            logging.getLogger("gttk.tools.optimize_compression").info("gttk message")
            logging.getLogger("someapp").info("app message")
            assert "gttk message" not in seen
            assert "app message" in seen, "the application's own logging stopped working"
        finally:
            shutdown_logger(gttk_logger)
            root.removeHandler(spy)
            root.level = old_level

    def test_shutdown_restores_propagation(self):
        gttk_logger = setup_logger()
        assert gttk_logger.propagate is False
        shutdown_logger(gttk_logger)
        assert gttk_logger.propagate is True

    def test_can_leave_matplotlib_alone(self):
        mpl = logging.getLogger("matplotlib")
        before = mpl.level
        try:
            mpl.setLevel(logging.DEBUG)
            gttk_logger = setup_logger(quiet_matplotlib=False)
            assert mpl.level == logging.DEBUG
            shutdown_logger(gttk_logger)
        finally:
            mpl.setLevel(before)


class TestGdalEnv:

    def test_applies_and_restores(self):
        before = {k: gdal.GetConfigOption(k) for k in GDAL_OPTIONS}
        with gdal_env():
            assert all(gdal.GetConfigOption(k) == v for k, v in GDAL_OPTIONS.items())
        assert {k: gdal.GetConfigOption(k) for k in GDAL_OPTIONS} == before

    def test_restores_an_option_that_was_unset(self):
        gdal.SetConfigOption("OSR_WKT_FORMAT", None)
        with gdal_env():
            assert gdal.GetConfigOption("OSR_WKT_FORMAT") == "WKT2_2019"
        assert gdal.GetConfigOption("OSR_WKT_FORMAT") is None

    def test_restores_a_pre_existing_value(self):
        gdal.SetConfigOption("GDAL_NUM_THREADS", "3")
        try:
            with gdal_env():
                assert gdal.GetConfigOption("GDAL_NUM_THREADS") == "ALL_CPUS"
            assert gdal.GetConfigOption("GDAL_NUM_THREADS") == "3"
        finally:
            gdal.SetConfigOption("GDAL_NUM_THREADS", None)

    def test_nests(self):
        with gdal_env():
            with gdal_env({"OSR_WKT_FORMAT": "WKT1_GDAL"}):
                assert gdal.GetConfigOption("OSR_WKT_FORMAT") == "WKT1_GDAL"
            assert gdal.GetConfigOption("OSR_WKT_FORMAT") == "WKT2_2019"

    def test_restores_the_exception_mode(self):
        before = gdal.GetUseExceptions()
        with gdal_env(use_exceptions=True):
            assert gdal.GetUseExceptions()
        assert gdal.GetUseExceptions() == before

    def test_arc_options_add_the_read_side_override(self):
        assert GDAL_OPTIONS_ARC["GTIFF_SRS_SOURCE"] == "WKT"
        assert "GTIFF_SRS_SOURCE" not in GDAL_OPTIONS, (
            "GTIFF_SRS_SOURCE changes how every GeoTIFF in the process is read; it "
            "belongs only to the ArcGIS path that needs it")


@pytest.mark.slow
class TestOperationsStillGetTheSettings:
    """Scoping the settings must not amount to removing them."""

    def test_optimize_applies_them_and_restores_them(self, tmp_path):
        import numpy as np
        import gttk.tools.optimize_compression as ocmp
        from gttk.utils.preprocessor import VirtualFileManager
        from gttk.utils.script_arguments import OptimizeArguments
        from tests.fixtures.mock_geotiff_factory import MockGeoTIFF

        src = tmp_path / "dem.tif"
        MockGeoTIFF(width=64, height=64, data_type=gdal.GDT_Float32,
                    crs="EPSG:4326", nodata_value=-32767.0).save_to_file(src)

        seen = {}
        real = ocmp.preprocess_geotiff

        def spy(**kwargs):
            seen.update({k: gdal.GetConfigOption(k) for k in GDAL_OPTIONS})
            return real(**kwargs)

        before = {k: gdal.GetConfigOption(k) for k in GDAL_OPTIONS}
        ocmp.preprocess_geotiff = spy
        prior, ocmp.arcMode = ocmp.arcMode, True
        try:
            ocmp._orchestrate_geotiff_optimization(
                OptimizeArguments(input_path=src, output_path=tmp_path / "out.tif",
                                  product_type="dem", vertical_srs="EPSG:4326+3855",
                                  algorithm="ZSTD", report=False, write_pam_xml=False,
                                  open_report=False),
                VirtualFileManager(), None)
        finally:
            ocmp.preprocess_geotiff = real
            ocmp.arcMode = prior

        assert seen == GDAL_OPTIONS, "the settings were not in force during the operation"
        assert {k: gdal.GetConfigOption(k) for k in GDAL_OPTIONS} == before
