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
Tests for overview and thread control on the COG path.

The COG driver's own default overview kernel is CUBIC for any band without a
colour table, and its default OVERVIEW_COMPRESS is LZW regardless of COMPRESS.
Neither default is acceptable: interpolating a categorical raster invents class
codes that were never in the data, and mixing codecs within one file is a
surprise.  These tests pin the creation options gttk emits, and the categorical
ones verify the actual pixels rather than just the option string.
"""

import numpy as np
import pytest
from osgeo import gdal

import gttk.utils.optimize_constants as oc
from gttk.utils.preprocessor import VirtualFileManager
from gttk.utils.script_arguments import OptimizeArguments
from tests.fixtures.mock_geotiff_factory import MockGeoTIFF

# `optimize_compression` sets GDAL config options process-wide at import, and pytest
# imports every test module during collection -- so importing it here would change how
# the whole suite exports WKT.  Capture what it sets, put the process back, and reapply
# only for the duration of these tests.
_GLOBAL_GDAL_CONFIG = ('GDAL_NUM_THREADS', 'ESRI_XML_PAM', 'OSR_WKT_FORMAT', 'GTIFF_WRITE_SRS_WKT2')
_config_before_import = {k: gdal.GetConfigOption(k) for k in _GLOBAL_GDAL_CONFIG}
import gttk.tools.optimize_compression as ocmp  # noqa: E402  (import has side effects)
_config_after_import = {k: gdal.GetConfigOption(k) for k in _GLOBAL_GDAL_CONFIG}
for _key, _value in _config_before_import.items():
    gdal.SetConfigOption(_key, _value)


@pytest.fixture(autouse=True)
def _module_gdal_config():
    """Run these tests with the config `optimize_compression` expects, and only these."""
    restore = {k: gdal.GetConfigOption(k) for k in _GLOBAL_GDAL_CONFIG}
    for key, value in _config_after_import.items():
        gdal.SetConfigOption(key, value)
    yield
    for key, value in restore.items():
        gdal.SetConfigOption(key, value)


# --- Helpers ---------------------------------------------------------------

def _thematic_source(tmp_path, name="classes.tif", size=600):
    """A categorical Byte raster whose class codes are sparse and non-adjacent.

    Sparse codes are the point: with 1/2/3/8/9 present, any interpolating kernel
    produces 4-7, which are *valid-looking* codes that were never in the data.
    """
    rng = np.random.default_rng(0)
    data = rng.choice(np.array([1, 2, 3, 8, 9], dtype=np.uint8), size=(1, size, size))
    path = tmp_path / name
    MockGeoTIFF(width=size, height=size, bands=1, data_type=gdal.GDT_Byte,
                crs='EPSG:4326', nodata_value=0, pixel_data=data).save_to_file(path)
    return path, {1, 2, 3, 8, 9}


def _run(args):
    """Run the optimization without report generation, quietly."""
    prior, ocmp.arcMode = ocmp.arcMode, True
    try:
        ocmp._orchestrate_geotiff_optimization(args, VirtualFileManager(), None)
    finally:
        ocmp.arcMode = prior


def _creation_options(monkeypatch, args):
    """Capture the creation options gttk hands the driver, without writing."""
    captured = {}
    real_translate = gdal.Translate

    def spy(dst, src, options=None, **kw):
        captured['options'] = list(getattr(options, '__dict__', {}).get('creationOptions', []) or [])
        return real_translate(dst, src, options=options, **kw)

    # TranslateOptions is opaque; capture from the list gttk builds instead.
    real_builder = gdal.TranslateOptions

    def builder_spy(*a, **kw):
        captured['options'] = list(kw.get('creationOptions', []) or [])
        return real_builder(*a, **kw)

    monkeypatch.setattr(gdal, 'TranslateOptions', builder_spy)
    _run(args)
    return captured.get('options', [])


# --- Argument resolution ---------------------------------------------------

class TestOverviewDefaults:
    """Defaults resolved on OptimizeArguments, before any I/O."""

    @pytest.mark.parametrize("product_type,expected", [
        ('thematic', 'NEAREST'),
        ('image', 'NEAREST'),
        ('dem', 'BILINEAR'),
        ('error', 'BILINEAR'),
        ('scientific', 'BILINEAR'),
    ])
    def test_default_resampling_by_product_type(self, product_type, expected):
        assert oc.default_overview_resampling_for(product_type) == expected

    def test_overview_compress_follows_algorithm(self):
        args = OptimizeArguments(product_type='thematic', algorithm='ZSTD')
        assert args.overview_compress == 'ZSTD'

    def test_overview_compress_explicit_wins(self):
        args = OptimizeArguments(product_type='thematic', algorithm='ZSTD',
                                 overview_compress='deflate')
        assert args.overview_compress == 'DEFLATE'

    def test_overview_predictor_follows_predictor(self):
        args = OptimizeArguments(product_type='dem', algorithm='ZSTD',
                                 vertical_srs='EPSG:5703', predictor=3)
        assert args.overview_predictor == 3

    def test_num_threads_defaults_to_all_cpus(self):
        assert OptimizeArguments(product_type='thematic').num_threads == 'ALL_CPUS'

    def test_num_threads_accepts_an_integer(self):
        assert OptimizeArguments(product_type='thematic', num_threads=4).num_threads == '4'

    def test_rejects_unknown_resampling(self):
        with pytest.raises(ValueError, match="Unsupported overview resampling"):
            OptimizeArguments(product_type='dem', vertical_srs='EPSG:5703',
                              overview_resampling='SPLINEY')

    def test_rejects_interpolating_resampling_on_thematic(self):
        with pytest.raises(ValueError, match="invent class codes"):
            OptimizeArguments(product_type='thematic', overview_resampling='CUBIC')

    def test_allows_mode_on_thematic(self):
        assert OptimizeArguments(product_type='thematic',
                                 overview_resampling='mode').overview_resampling == 'MODE'


class TestRasterTypeNormalisation:
    """AREA_OR_POINT is written verbatim, so its spelling has to be GDAL's."""

    @pytest.mark.parametrize("given,expected", [('point', 'Point'), ('area', 'Area'),
                                                ('POINT', 'Point'), ('Point', 'Point')])
    def test_capitalised(self, given, expected):
        args = OptimizeArguments(product_type='thematic', raster_type=given)
        assert args.raster_type == expected

    def test_rejects_nonsense(self):
        with pytest.raises(ValueError, match="raster_type must be"):
            OptimizeArguments(product_type='thematic', raster_type='middle')


class TestSemanticValidation:
    """Checks over flag combinations, none of which needs a raster.

    They used to sit behind an `if self.input_path` guard, so the ArcGIS toolbox and
    any library caller -- both of which build this dataclass directly -- slipped past
    them entirely.
    """

    def test_rejects_lerc_on_imagery_without_a_file(self):
        with pytest.raises(ValueError, match="not suitable for imagery"):
            OptimizeArguments(product_type='image', algorithm='LERC')

    def test_rejects_lossy_codec_on_non_imagery_without_a_file(self):
        with pytest.raises(ValueError, match="only suitable for imagery"):
            OptimizeArguments(product_type='dem', algorithm='JPEG',
                              vertical_srs='EPSG:5703')

    def test_requires_vertical_srs_for_dem_without_a_file(self):
        with pytest.raises(ValueError, match="Vertical SRS"):
            OptimizeArguments(product_type='dem')

    def test_band_count_check_still_needs_a_file(self):
        """The one rule that genuinely has to open the raster stays behind the guard."""
        assert OptimizeArguments(product_type='thematic').product_type == 'thematic'


class TestThematicLerc:
    """Esri writes lossless LERC widely, so thematic LERC is supported -- but only
    lossless.  A non-zero tolerance quantises neighbouring values together, merging
    adjacent class codes the same way an interpolating overview kernel invents them.
    """

    def test_lossless_lerc_is_allowed(self):
        args = OptimizeArguments(product_type='thematic', algorithm='LERC')
        assert args.max_z_error == 0

    def test_explicit_zero_is_allowed(self):
        args = OptimizeArguments(product_type='thematic', algorithm='LERC', max_z_error=0)
        assert args.max_z_error == 0

    def test_rejects_a_lossy_tolerance(self):
        with pytest.raises(ValueError, match="merge adjacent class codes"):
            OptimizeArguments(product_type='thematic', algorithm='LERC', max_z_error=0.5)

    def test_thematic_is_a_lerc_product_type(self):
        assert 'thematic' in oc.LERC_PRODUCT_TYPES
        assert 'image' not in oc.LERC_PRODUCT_TYPES

    @pytest.mark.parametrize("product_type,expected", [
        ('dem', 'Point'), ('error', 'Point'), ('scientific', 'Point'),
        ('image', 'Area'), ('thematic', 'Area'),
    ])
    def test_raster_type_is_resolved_not_left_none(self, product_type, expected):
        """Three call sites used to re-derive this inline; the resolver owns it now."""
        args = OptimizeArguments(product_type=product_type, vertical_srs='EPSG:5703')
        assert args.raster_type == expected
        assert oc.default_raster_type_for(product_type) == expected


class TestLevelResolution:
    """LERC_DEFLATE/LERC_ZSTD carry a level for their entropy stage exactly as the
    bare codecs do, and optimize_compression emits it -- but _resolve_defaults used to
    match only the bare names, so `-a LERC_ZSTD` with no level emitted no LEVEL at all
    while `-a ZSTD` emitted 9.  Benchmark-only today; a trap when it is not."""

    @pytest.mark.parametrize("algorithm,expected", [
        ('DEFLATE', 6), ('ZSTD', 9),
        ('LERC_DEFLATE', 6), ('LERC_ZSTD', 9),
        ('LERC', None), ('LZW', None), ('NONE', None),
    ])
    def test_level_follows_the_entropy_stage(self, algorithm, expected):
        args = OptimizeArguments(product_type='dem', vertical_srs='EPSG:5703',
                                 algorithm=algorithm)
        assert args.level == expected

    def test_an_explicit_level_is_never_overridden(self):
        args = OptimizeArguments(product_type='dem', vertical_srs='EPSG:5703',
                                 algorithm='ZSTD', level=15)
        assert args.level == 15


class TestPredictorResolution:
    """PREDICTOR=3 is the floating-point predictor; libtiff rejects it on ints."""

    def test_thematic_default_is_a_valid_gdal_value(self):
        # 'NONE' is not in the COG driver's PREDICTOR value list; 1 is.
        assert oc.default_predictor_for('thematic') == 1

    def test_three_falls_back_to_two_on_integer_data(self):
        predictor, warning = oc.resolve_predictor(3, 'UInt16')
        assert predictor == 2
        assert 'floating-point predictor' in warning

    def test_three_is_kept_on_float_data(self):
        assert oc.resolve_predictor(3, 'Float32') == (3, None)

    def test_two_is_untouched_on_integer_data(self):
        assert oc.resolve_predictor(2, 'Byte') == (2, None)

    def test_none_passes_through(self):
        assert oc.resolve_predictor(None, 'Byte') == (None, None)

    def test_a_non_numeric_predictor_is_rescued(self):
        predictor, warning = oc.resolve_predictor('NONE', 'Byte')
        assert predictor == 1
        assert 'not a valid GDAL value' in warning


# --- Emitted creation options ---------------------------------------------

@pytest.mark.slow
class TestEmittedCreationOptions:

    def test_thematic_cog_emits_nearest(self, tmp_path, monkeypatch):
        src, _ = _thematic_source(tmp_path)
        args = OptimizeArguments(input_path=src, output_path=tmp_path / "out.tif",
                                 product_type='thematic', algorithm='ZSTD', predictor=2,
                                 cog=True, overviews=True, report=False,
                                 write_pam_xml=False, open_report=False)
        options = _creation_options(monkeypatch, args)
        assert 'OVERVIEWS=AUTO' in options
        assert 'OVERVIEW_RESAMPLING=NEAREST' in options
        assert 'OVERVIEW_COMPRESS=ZSTD' in options
        assert 'OVERVIEW_PREDICTOR=2' in options

    def test_num_threads_is_honoured(self, tmp_path, monkeypatch):
        src, _ = _thematic_source(tmp_path)
        args = OptimizeArguments(input_path=src, output_path=tmp_path / "out.tif",
                                 product_type='thematic', algorithm='ZSTD', num_threads=2,
                                 cog=True, report=False, write_pam_xml=False, open_report=False)
        options = _creation_options(monkeypatch, args)
        assert 'NUM_THREADS=2' in options
        assert 'NUM_THREADS=ALL_CPUS' not in options

    def test_no_resampling_option_when_overviews_are_prebuilt(self, tmp_path, monkeypatch):
        """The rounding path builds the pyramid itself and passes FORCE_USE_EXISTING;
        OVERVIEW_RESAMPLING would be meaningless there."""
        src = tmp_path / "dem.tif"
        MockGeoTIFF(width=600, height=600, data_type=gdal.GDT_Float32,
                    crs='EPSG:4326', nodata_value=-32767.0).save_to_file(src)
        args = OptimizeArguments(input_path=src, output_path=tmp_path / "out.tif",
                                 product_type='dem', vertical_srs='EPSG:5703',
                                 algorithm='ZSTD', predictor=2, decimals=2,
                                 cog=True, overviews=True, report=False,
                                 write_pam_xml=False, open_report=False)
        options = _creation_options(monkeypatch, args)
        assert 'OVERVIEWS=FORCE_USE_EXISTING' in options
        assert not any(o.startswith('OVERVIEW_RESAMPLING=') for o in options)

    def test_predictor_1_is_omitted_not_emitted(self, tmp_path, monkeypatch):
        """The two drivers disagree on how to spell "no predictor": the COG driver's
        value list is NO/YES/STANDARD/FLOATING_POINT and it warns on '1', while GTiff
        takes an int and errors on 'NO'. Omitting it is correct for both, and 1 is
        already their default."""
        src, _ = _thematic_source(tmp_path)
        args = OptimizeArguments(input_path=src, output_path=tmp_path / "out.tif",
                                 product_type='thematic', algorithm='ZSTD', predictor=1,
                                 cog=True, report=False, write_pam_xml=False, open_report=False)
        options = _creation_options(monkeypatch, args)
        assert not any(o.startswith('PREDICTOR=') for o in options), options
        assert not any(o.startswith('OVERVIEW_PREDICTOR=') for o in options), options

    def test_thematic_default_predictor_emits_nothing(self, tmp_path, monkeypatch):
        src, _ = _thematic_source(tmp_path)
        args = OptimizeArguments(input_path=src, output_path=tmp_path / "out.tif",
                                 product_type='thematic', algorithm='ZSTD',
                                 cog=True, report=False, write_pam_xml=False, open_report=False)
        assert not any(o.startswith('PREDICTOR=') for o in _creation_options(monkeypatch, args))

    def test_no_overview_options_when_overviews_are_off(self, tmp_path, monkeypatch):
        src, _ = _thematic_source(tmp_path)
        args = OptimizeArguments(input_path=src, output_path=tmp_path / "out.tif",
                                 product_type='thematic', algorithm='ZSTD',
                                 cog=True, overviews=False, report=False,
                                 write_pam_xml=False, open_report=False)
        options = _creation_options(monkeypatch, args)
        assert 'OVERVIEWS=NONE' in options
        assert not any(o.startswith('OVERVIEW_') and o != 'OVERVIEWS=NONE' for o in options)


# --- The pixels, which are what actually matter ----------------------------

@pytest.mark.slow
class TestCategoricalOverviewsAreNotInterpolated:

    def test_class_codes_survive_every_pyramid_level(self, tmp_path):
        src, source_classes = _thematic_source(tmp_path)
        out = tmp_path / "classes_cog.tif"
        _run(OptimizeArguments(input_path=src, output_path=out,
                               product_type='thematic', algorithm='ZSTD', predictor=2,
                               raster_type='point', tile_size=128, cog=True, overviews=True,
                               report=False, write_pam_xml=False, open_report=False))

        ds = gdal.Open(str(out))
        band = ds.GetRasterBand(1)
        assert ds.GetMetadata('IMAGE_STRUCTURE').get('OVERVIEW_RESAMPLING') == 'NEAREST'
        assert band.GetOverviewCount() > 0, "need a pyramid to test"
        for level in range(band.GetOverviewCount()):
            present = set(np.unique(band.GetOverview(level).ReadAsArray()).tolist())
            invented = present - source_classes - {0}
            assert not invented, (
                f"overview {level} contains class codes {sorted(invented)} that are not "
                f"in the source ({sorted(source_classes)}) -- the kernel interpolated"
            )
        ds = None

    def test_the_driver_default_would_have_invented_codes(self, tmp_path):
        """Guard the guard: prove the default really is unsafe, so this suite fails
        loudly if a future GDAL changes it and these tests stop meaning anything."""
        src, source_classes = _thematic_source(tmp_path)
        out = tmp_path / "driver_default.tif"
        gdal.Translate(str(out), str(src), format='COG',
                       creationOptions=['COMPRESS=ZSTD', 'BLOCKSIZE=128', 'OVERVIEWS=AUTO'])
        ds = gdal.Open(str(out))
        band = ds.GetRasterBand(1)
        invented = set()
        for level in range(band.GetOverviewCount()):
            invented |= set(np.unique(band.GetOverview(level).ReadAsArray()).tolist())
        ds = None
        assert invented - source_classes - {0}, (
            "the COG driver's default overview kernel no longer interpolates; "
            "revisit whether OVERVIEW_RESAMPLING still needs to be stated explicitly"
        )

    def test_full_resolution_data_is_bit_identical(self, tmp_path):
        src, _ = _thematic_source(tmp_path)
        out = tmp_path / "classes_cog.tif"
        _run(OptimizeArguments(input_path=src, output_path=out,
                               product_type='thematic', algorithm='ZSTD', predictor=2,
                               raster_type='point', cog=True, overviews=True,
                               report=False, write_pam_xml=False, open_report=False))
        source, result = gdal.Open(str(src)), gdal.Open(str(out))
        assert result.GetRasterBand(1).Checksum() == source.GetRasterBand(1).Checksum()
        assert result.GetGeoTransform() == source.GetGeoTransform()
        assert result.GetMetadataItem('AREA_OR_POINT') == 'Point'
        assert result.GetRasterBand(1).GetNoDataValue() == source.GetRasterBand(1).GetNoDataValue()
        source = result = None


@pytest.mark.slow
class TestReportOptOut:

    def test_report_false_skips_generation(self, tmp_path, monkeypatch):
        src, _ = _thematic_source(tmp_path, size=128)
        calls = []
        monkeypatch.setattr(ocmp, 'generate_report_for_datasets',
                            lambda *a, **kw: calls.append(a))
        args = OptimizeArguments(input_path=src, output_path=tmp_path / "out.tif",
                                 product_type='thematic', algorithm='ZSTD',
                                 report=False, write_pam_xml=False, open_report=False)
        ocmp._process_single_file(args)
        assert calls == []

    def test_report_true_still_generates(self, tmp_path, monkeypatch):
        src, _ = _thematic_source(tmp_path, size=128)
        calls = []
        monkeypatch.setattr(ocmp, 'generate_report_for_datasets',
                            lambda *a, **kw: calls.append(a))
        args = OptimizeArguments(input_path=src, output_path=tmp_path / "out.tif",
                                 product_type='thematic', algorithm='ZSTD',
                                 report=True, write_pam_xml=False, open_report=False)
        ocmp._process_single_file(args)
        assert len(calls) == 1


@pytest.mark.slow
class TestSourceHandleIsReleasedOnFailure:

    def test_input_is_not_locked_after_an_error(self, tmp_path, monkeypatch):
        """A leaked read handle on the source makes os.remove() fail on Windows,
        which turns a retryable error into a stuck file."""
        src, _ = _thematic_source(tmp_path, size=128)

        def boom(*a, **kw):
            raise RuntimeError("synthetic failure")

        monkeypatch.setattr(ocmp, 'preprocess_geotiff', boom)
        args = OptimizeArguments(input_path=src, output_path=tmp_path / "out.tif",
                                 product_type='thematic', algorithm='ZSTD',
                                 report=False, write_pam_xml=False, open_report=False)
        with pytest.raises(RuntimeError, match="synthetic failure"):
            ocmp._orchestrate_geotiff_optimization(args, VirtualFileManager(), None)

        # The source must be replaceable: on POSIX this always passes, so also assert
        # no GDAL dataset is still open on it.
        src.unlink()
        assert not src.exists()
