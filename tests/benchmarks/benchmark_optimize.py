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
What one `gttk optimize` run costs: the passes it makes and where it holds its intermediates.

Both questions came from a 91,445 x 53,704 orthophoto that took over an hour. The two
things that made it that slow are measured here, at whatever size the caller can afford:

- how many times the raster is read to compute statistics, and how many band-equivalents
  that is. A raster too large for memory costs one full read per pass, so the count is
  the number that matters;
- what it costs to hold the intermediates on disk rather than in memory. On a raster that
  fits in memory this is the price of the safety margin; on one that does not, memory is
  the pagefile and this comparison no longer applies.

Run with: python -m tests.benchmarks.benchmark_optimize

The sizes below are what a workstation can do in a couple of minutes. Every function takes
its own, so `tests/benchmarks/test_benchmarks_smoke.py` can run each at 256x256.
"""

import shutil
import tempfile
import time
from pathlib import Path

import numpy as np
from osgeo import gdal, osr

import gttk.tools.optimize_compression as ocmp
import gttk.utils.preprocessor as preprocessor
from gttk.utils.preprocessor import estimated_workspace_bytes
from gttk.utils.script_arguments import OptimizeArguments


def _build_rgba(path: Path, size: int) -> None:
    """A tiled RGBA raster with a transparent margin, smooth enough that LZW behaves as it
    does on real imagery rather than on noise."""
    ds = gdal.GetDriverByName('GTiff').Create(
        str(path), size, size, 4, gdal.GDT_Byte,
        options=['TILED=YES', 'BLOCKXSIZE=512', 'BLOCKYSIZE=512', 'COMPRESS=DEFLATE', 'BIGTIFF=YES'])
    ds.SetGeoTransform((500000, 1, 0, 4000000, 0, -1))
    srs = osr.SpatialReference(); srs.ImportFromEPSG(32610)
    ds.SetProjection(srs.ExportToWkt())
    rng = np.random.default_rng(42)
    chunk = min(1024, size)
    for band_index in range(1, 5):
        band = ds.GetRasterBand(band_index)
        band.SetColorInterpretation(gdal.GCI_RedBand + band_index - 1 if band_index < 4 else gdal.GCI_AlphaBand)
        for y in range(0, size, chunk):
            height = min(chunk, size - y)
            if band_index == 4:
                data = np.full((height, size), 255, np.uint8)
                if y < size // 5:
                    data[:] = 0
            else:
                rows = np.arange(y, y + height)[:, None]
                columns = np.arange(size)[None, :]
                smooth = (np.sin(columns / 90.0) + np.cos(rows / 70.0) + 2) * 60
                data = np.clip(smooth + band_index * 12 + rng.integers(-6, 6, (height, size)), 0, 255).astype(np.uint8)
            band.WriteArray(data, 0, y)
    ds.FlushCache()


class _ReadCounter:
    """Counts the band pixels Python reads, so a pass over the raster is visible as one."""

    def __init__(self):
        self.pixels = 0
        self._real = gdal.Band.ReadAsArray

    def __enter__(self):
        counter = self

        def counted(band, *args, **kwargs):
            out = counter._real(band, *args, **kwargs)
            if out is not None:
                counter.pixels += int(np.prod(out.shape))
            return out

        gdal.Band.ReadAsArray = counted
        return self

    def __exit__(self, *exc):
        gdal.Band.ReadAsArray = self._real
        return False


def _run(source: Path, output: Path, **overrides) -> None:
    kwargs = dict(input_path=source, output_path=output, product_type='image', algorithm='JPEG',
                  quality=90, report=False, open_report=False, arc_mode=True)
    kwargs.update(overrides)
    ocmp.optimize_compression(OptimizeArguments(**kwargs))


def benchmark_statistics_passes(size=8192):
    """One optimize run: how many statistics passes, how much read, how long.

    The write needs one pass. `--report` adds two more, on the input and on the output --
    different pixels from the write's pass, so they can be declined but not shared.

    Returns {'write': (passes, band_equivalents, seconds), 'with_report': (...)}.
    """
    print("\n" + "=" * 80)
    print(f"Statistics passes, {size}x{size} RGBA")
    print("=" * 80)

    import gttk.utils.statistics.calculator as calculator
    results = {}
    workdir = Path(tempfile.mkdtemp(prefix='gttk_bench_'))
    try:
        source = workdir / 'source.tif'
        _build_rgba(source, size)
        band_pixels = size * size
        print(f"\n{'run':<14} {'passes':<8} {'x one band':<12} {'seconds':<10}")
        print("-" * 80)
        for label, report in (('write only', False), ('with report', True)):
            passes = []
            originals = {name: getattr(calculator, name)
                         for name in ('_calculate_statistics_full', '_calculate_statistics_blocked')}
            for name, real in originals.items():
                setattr(calculator, name, lambda *a, _real=real, **kw: (passes.append(1), _real(*a, **kw))[1])
            try:
                with _ReadCounter() as counter:
                    start = time.perf_counter()
                    _run(source, workdir / f'out_{report}.tif', report=report, open_report=False)
                    elapsed = time.perf_counter() - start
            finally:
                for name, real in originals.items():
                    setattr(calculator, name, real)
            results[label] = (len(passes), counter.pixels / band_pixels, elapsed)
            print(f"{label:<14} {len(passes):<8} {counter.pixels / band_pixels:<12.1f} {elapsed:<10.1f}")
        print("\n✓ The write takes one pass; the report is what adds the rest")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    return results


def benchmark_workspace_location(size=8192):
    """The same raster with the intermediates in memory and on disk.

    On a raster that fits in memory, memory wins and the difference is what the safety
    margin costs when the estimate sends a borderline file to disk. On one that does not
    fit, the memory run is paging and this comparison stops meaning anything -- which is
    the case the choice exists for.

    Returns {'memory': seconds, 'disk': seconds, 'estimated_gb': float}.
    """
    print("\n" + "=" * 80)
    print(f"Workspace location, {size}x{size} RGBA")
    print("=" * 80)

    workdir = Path(tempfile.mkdtemp(prefix='gttk_bench_'))
    results = {}
    try:
        source = workdir / 'source.tif'
        _build_rgba(source, size)
        estimated = estimated_workspace_bytes(size, size, 4, 'Byte')
        results['estimated_gb'] = estimated / 1024 ** 3
        print(f"\nintermediates estimated at {results['estimated_gb']:.2f} GB")
        print(f"\n{'location':<10} {'seconds':<10} {'Mpixels/sec':<14}")
        print("-" * 80)
        real = preprocessor.workspace_fits_in_memory
        for label, fits in (('memory', True), ('disk', False)):
            preprocessor.workspace_fits_in_memory = lambda *a, **kw: fits
            try:
                start = time.perf_counter()
                _run(source, workdir / f'out_{label}.tif')
                elapsed = time.perf_counter() - start
            finally:
                preprocessor.workspace_fits_in_memory = real
            results[label] = elapsed
            print(f"{label:<10} {elapsed:<10.1f} {size * size / elapsed / 1e6:<14.1f}")
        print(f"\n✓ Disk costs {results['disk'] / results['memory']:.2f}x memory at this size, "
              f"and is the only one that finishes when the intermediates exceed RAM")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    return results


def benchmark_end_to_end(size=8192):
    """Whole-run throughput, for comparison against a bare gdal_translate.

    Returns Mpixels/sec over the source's pixels.
    """
    print("\n" + "=" * 80)
    print(f"End to end, {size}x{size} RGBA to a JPEG COG")
    print("=" * 80)

    workdir = Path(tempfile.mkdtemp(prefix='gttk_bench_'))
    try:
        source = workdir / 'source.tif'
        _build_rgba(source, size)
        start = time.perf_counter()
        _run(source, workdir / 'out.tif')
        elapsed = time.perf_counter() - start
        rate = size * size / elapsed / 1e6
        print(f"\nTime: {elapsed:.1f}s   Throughput: {rate:.1f} Mpixels/sec (source pixels)")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    return rate


def run_all_benchmarks():
    """Run every optimize benchmark at its default size."""
    print("\n" + "=" * 80)
    print("GTTK OPTIMIZE BENCHMARKS")
    print("=" * 80)
    benchmark_statistics_passes()
    benchmark_workspace_location()
    benchmark_end_to_end()


if __name__ == "__main__":
    run_all_benchmarks()
