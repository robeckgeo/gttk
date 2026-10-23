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
The CLI passes a tool's status on, and an artifact that was asked for is not optional.

``gttk.main.main()`` used to discard what a tool returned and the process exited 0
whatever had happened: a batch with failed files, an output that was never written, a
report or an .aux.xml that was requested and not produced, all looked like success to the
shell and to the pipeline scripts that call ``python -m gttk``. ``main()`` now returns an
exit status that ``python -m gttk`` hands to ``sys.exit``, and ``gttk optimize`` raises
``ProcessingStepFailedError`` when something it was asked for did not get made, finishing
the rest of a batch before it says so.

These pin both halves in process. The subprocess tests in
tests/e2e/test_optimize_exit_codes.py prove the exit status end to end.
"""

import logging
import struct
import sys
from pathlib import Path

import numpy as np
import pytest
from osgeo import gdal

import gttk
import gttk.main
import gttk.tools.optimize_compression as ocmp
from gttk.main import exit_status, main
from gttk.utils.exceptions import ProcessingStepFailedError
from gttk.utils.preprocessor import Workspace
from gttk.utils.script_arguments import OptimizeArguments
from tests.fixtures.mock_geotiff_factory import MockGeoTIFF

pytestmark = pytest.mark.unit


def _dem(path: Path, size: int = 64, seed: int = 3) -> Path:
    """A small Float32 DEM with a few NoData pixels, deterministic for a seed."""
    rng = np.random.default_rng(seed)
    data = rng.uniform(100.0, 500.0, size=(1, size, size)).astype(np.float32)
    data[0, 0, :4] = -32767.0
    MockGeoTIFF(width=size, height=size, bands=1, data_type=gdal.GDT_Float32,
                crs='EPSG:4326', nodata_value=-32767.0, pixel_data=data).save_to_file(path)
    return path


def _truncated_dem(path: Path) -> Path:
    """A GeoTIFF the batch walker accepts and the pipeline cannot read: an interrupted copy.

    GDAL writes the directory at the front of a file it creates and the pixels after it,
    as long as nothing in the directory changes once the first pixels are written; so this
    one carries no NoData value (MockGeoTIFF sets that after the pixels, and the grown
    directory is rewritten at the end of the file, where the cut would take it). The header
    and the GeoKey directory survive the cut, so ``is_geotiff`` says yes; half of the
    strips are gone, so the first read of them fails inside the run.

    A text file named .tif is not the same thing: GDAL cannot open it at all, the walker
    skips it with a warning, and the batch never sees it. Nor is a 3-band Byte raster: the
    batch builds each file's arguments while ``input_path`` is still the directory, so the
    single-band rule for 'dem' is never applied to it and it is written as a 3-band COG.
    """
    rng = np.random.default_rng(9)
    data = rng.uniform(100.0, 500.0, size=(1, 256, 256)).astype(np.float32)
    MockGeoTIFF(width=256, height=256, bands=1, data_type=gdal.GDT_Float32,
                crs='EPSG:4326', pixel_data=data).save_to_file(path)
    size = path.stat().st_size
    header = path.read_bytes()[:8]
    first_ifd = struct.unpack('<I' if header[:2] == b'II' else '>I', header[4:8])[0]
    assert first_ifd < size // 2, f'the directory of {path.name} is at {first_ifd}, past the cut'
    with path.open('r+b') as handle:
        handle.truncate(size // 2)
    return path


def _arguments(source: Path, output: Path, **overrides) -> OptimizeArguments:
    kwargs = dict(input_path=source, output_path=output, product_type='dem', vertical_srs='EPSG:5703',
                  algorithm='DEFLATE', report=False, write_pam_xml=False, open_report=False, arc_mode=True)
    kwargs.update(overrides)
    return OptimizeArguments(**kwargs)


class TestExitStatus:

    @pytest.mark.parametrize('result, status', [
        (None, 0),
        (0, 0),
        (1, 1),
        (False, 1),
        (True, 0),
        ('report.html', 0),
    ])
    def test_a_tool_result_as_a_process_status(self, result, status):
        """None is success, a bool is 0/1, an int is itself, anything else (a report path) is 0."""
        assert exit_status(result) == status


class TestMainPassesTheStatusOn:
    """main() parses real arguments and dispatches to a stand-in for the optimize tool."""

    @pytest.fixture(autouse=True)
    def _restore_gttk_logger(self):
        """main() calls setup_logger, which rebinds the 'gttk' logger to this test's captured
        stdout and stops its propagation; put it back for the tests that run after."""
        log = logging.getLogger('gttk')
        saved = (log.level, log.propagate, list(log.handlers))
        yield
        for handler in log.handlers[:]:
            log.removeHandler(handler)
        log.setLevel(saved[0])
        log.propagate = saved[1]
        for handler in saved[2]:
            log.addHandler(handler)

    @pytest.fixture
    def argv(self, tmp_path, monkeypatch):
        """A command line that validates: OptimizeArguments checks that the input exists."""
        source = _dem(tmp_path / 'dem_tile.tif')
        monkeypatch.setattr(sys, 'argv', [
            'gttk', 'optimize', '-i', str(source), '-o', str(tmp_path / 'out.tif'),
            '-t', 'dem', '-s', 'EPSG:5703', '--open-report', 'false',
        ])

    def test_a_tool_that_returns_1_exits_1(self, argv, monkeypatch):
        monkeypatch.setattr(ocmp, 'optimize_compression', lambda args, tracker=None: 1)
        assert main() == 1

    def test_a_tool_that_returns_none_exits_0(self, argv, monkeypatch):
        monkeypatch.setattr(ocmp, 'optimize_compression', lambda args, tracker=None: None)
        assert main() == 0

    def test_a_tool_that_raises_exits_1_and_says_why(self, argv, monkeypatch, capsys):
        """The message reaches the user. setup_logger gives the 'gttk' logger its own stdout
        handler and stops propagation, so caplog's root handler never sees the record;
        the captured stdout is where it lands."""
        def raising(args, tracker=None):
            raise RuntimeError('the codec went away')

        monkeypatch.setattr(ocmp, 'optimize_compression', raising)
        assert main() == 1
        assert 'the codec went away' in capsys.readouterr().out


class TestPythonDashMEntryPoint:
    """Structural pins; tests/e2e/test_optimize_exit_codes.py proves them in a subprocess."""

    def test_python_m_gttk_exits_with_the_status_main_returns(self):
        text = (Path(gttk.__file__).parent / '__main__.py').read_text(encoding='utf-8')
        assert 'sys.exit(main())' in text

    def test_the_script_guard_does_too(self):
        text = Path(gttk.main.__file__).read_text(encoding='utf-8')
        assert 'sys.exit(main())' in text


class TestRequestedArtifactsAreNotOptional:
    """A run that was asked for something and did not produce it is a failed run."""

    @pytest.fixture
    def source(self, tmp_path):
        return _dem(tmp_path / 'dem_tile.tif')

    @pytest.fixture
    def malformed_record(self, tmp_path):
        record = tmp_path / 'SRC_N00E000_01.xml'
        record.write_text('not xml\n', encoding='utf-8')
        return record

    def test_a_report_that_was_not_generated_fails_the_run(self, source, tmp_path, monkeypatch):
        """--report True and nothing comes back from the report generator: the output
        itself was written, and the run still raises."""
        monkeypatch.setattr(ocmp, 'generate_report_for_datasets', lambda *args, **kwargs: None)
        output = tmp_path / 'out.tif'
        with pytest.raises(ProcessingStepFailedError, match='report'):
            ocmp._process_single_file(_arguments(source, output, report=True))
        assert output.is_file()

    def test_a_sidecar_without_statistics_fails_the_run(self, source, tmp_path, monkeypatch):
        """--write-pam-xml True and no statistics to put in it: the output is written,
        no .aux.xml appears beside it, and the run raises."""
        monkeypatch.setattr(ocmp, 'calculate_statistics', lambda *args, **kwargs: None)
        output = tmp_path / 'out.tif'
        with pytest.raises(ProcessingStepFailedError, match=r'aux\.xml'):
            ocmp._process_single_file(_arguments(source, output, write_pam_xml=True))
        assert output.is_file()
        assert not (tmp_path / 'out.tif.aux.xml').exists()

    def test_a_malformed_record_fails_the_orchestration(self, source, tmp_path, malformed_record):
        """An explicit --geo-metadata record that is not XML stops the run before the
        write; the argument check only sees that the file exists."""
        output = tmp_path / 'out.tif'
        args = _arguments(source, output, geo_metadata=malformed_record)
        with Workspace() as workspace:
            with pytest.raises(ProcessingStepFailedError, match='well-formed'):
                ocmp._orchestrate_geotiff_optimization(args, workspace, None)
        assert not output.exists()

    def test_a_malformed_record_makes_the_entry_point_return_1(self, source, tmp_path, malformed_record):
        """The single-file path catches the failure and reports it as a status."""
        output = tmp_path / 'out.tif'
        assert ocmp.optimize_compression(_arguments(source, output, geo_metadata=malformed_record)) == 1
        assert not output.exists()

    def test_a_batch_finishes_the_other_files_and_returns_1(self, tmp_path):
        """One of three files cannot be read (see _truncated_dem for why that one): the
        other two are still written, and the batch returns 1."""
        folder = tmp_path / 'tiles'
        folder.mkdir()
        _dem(folder / 'dem_tile_01.tif', seed=1)
        _dem(folder / 'dem_tile_02.tif', seed=2)
        _truncated_dem(folder / 'bad.tif')
        optimized = tmp_path / 'optimized'

        status = ocmp.optimize_compression(OptimizeArguments(
            input_path=folder, output_path=optimized, product_type='dem', vertical_srs='EPSG:5703',
            report=False, write_pam_xml=False, open_report=False, arc_mode=True))

        assert status == 1
        assert (optimized / 'dem_tile_01.tif').is_file()
        assert (optimized / 'dem_tile_02.tif').is_file()
        assert not (optimized / 'bad.tif').exists()
