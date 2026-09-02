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
Session-wide pytest configuration for GTTK.

This file sits at the repository root rather than inside a package because two of
its jobs have to happen above everything else:

1. **PROJ_LIB.** It must be set before the first `osgeo` import anywhere in the
   session. The root conftest is loaded before `tests/conftest.py`, so this is the
   only place that can guarantee it -- including for a bare
   `pytest --doctest-modules gttk/` that never touches `tests/`.

2. **The doctest sandbox.** `pytest.ini` runs doctests out of `gttk/`, and a
   conftest only supplies fixtures to items at or below its own directory: a
   fixture in `tests/conftest.py` would never reach them. Keeping it out of
   `gttk/` also keeps it out of the wheel and out of the blast radius of
   `tests/unit/test_import_side_effects.py`.

Everything else -- the mock GeoTIFF fixtures, the assertion formatting -- stays in
`tests/conftest.py`.
"""

import os
import shutil
import sys
from pathlib import Path

import numpy as np
import pytest
from _pytest.doctest import DoctestItem

# ==============================================================================
# CRITICAL: Set PROJ_LIB before importing GDAL/OSR
# ==============================================================================
# GDAL/OSR needs PROJ_LIB to locate proj.db for EPSG code resolution.
# In conda environments, this should point to the 'share/proj' directory.
# This must be done BEFORE the first import of osgeo.gdal or osgeo.osr.

if 'PROJ_LIB' not in os.environ and 'PROJ_DATA' not in os.environ:
    # Try to find PROJ database in conda environment
    if 'CONDA_PREFIX' in os.environ:
        conda_prefix = Path(os.environ['CONDA_PREFIX'])
        # Try Windows path first (Library/share/proj)
        proj_path = conda_prefix / 'Library' / 'share' / 'proj'
        if not proj_path.exists():
            # Try Unix path (share/proj)
            proj_path = conda_prefix / 'share' / 'proj'

        if proj_path.exists() and (proj_path / 'proj.db').exists():
            os.environ['PROJ_LIB'] = str(proj_path)
            print(f"[conftest.py] Set PROJ_LIB={proj_path}")
        else:
            print("[conftest.py] WARNING: Could not find proj.db in conda environment")

    # Fallback: Try to find it relative to Python executable
    if 'PROJ_LIB' not in os.environ:
        python_path = Path(sys.executable).parent.parent
        proj_path = python_path / 'Library' / 'share' / 'proj'
        if not proj_path.exists():
            proj_path = python_path / 'share' / 'proj'

        if proj_path.exists() and (proj_path / 'proj.db').exists():
            os.environ['PROJ_LIB'] = str(proj_path)
            print(f"[conftest.py] Set PROJ_LIB={proj_path}")

# NOW it's safe to import GDAL/OSR
from osgeo import gdal  # noqa: E402

# pythonpath is configured in pytest.ini to include the project root
from tests.fixtures.mock_geotiff_factory import MockGeoTIFF  # noqa: E402


def pytest_configure(config):
    # GTTK applies GDAL's exception mode per operation rather than at import, so
    # the test session -- an application like any other -- makes the choice for
    # itself. Import cleanliness is asserted separately, in subprocesses, by
    # tests/unit/test_import_side_effects.py.
    gdal.UseExceptions()


# =============================================================================
# Doctest sandbox
# =============================================================================
# Docstring examples read best when they open a plausible filename:
#
#     >>> with MetadataExtractor('example.tif') as extractor:
#
# Rather than rewrite every example around an injected path variable the reader
# cannot resolve, each doctest is given a working directory in which those names
# are real. The rasters are built once per session and copied per example, so an
# example that mutates its input (round_overviews) or writes a report cannot
# affect the next one -- or leave anything in the repository.

# 64x64 keeps the whole set instant to build. Every raster gets explicit pixel
# data: MockGeoTIFF's own generator is unseeded, and an example that prints a
# minimum or a mean has to be reproducible.
_SIZE = 64
_ELEVATION = np.linspace(100.0, 200.0, _SIZE * _SIZE, dtype=np.float32).reshape(1, _SIZE, _SIZE)
_IMAGERY = np.tile(
    np.arange(_SIZE * _SIZE, dtype=np.uint8).reshape(_SIZE, _SIZE), (3, 1, 1)
)


@pytest.fixture(scope='session')
def doctest_sample_dir(tmp_path_factory) -> Path:
    """
    The master copy of the rasters that docstring examples open, built once.

    Do not hand this directory to a test that writes: use it through
    `_doctest_sandbox`, or copy it yourself.
    """
    master = tmp_path_factory.mktemp('doctest_samples')

    def elevation(**kwargs) -> MockGeoTIFF:
        params = dict(
            width=_SIZE, height=_SIZE, bands=1,
            data_type=gdal.GDT_Float32, crs='EPSG:4326',
            pixel_data=_ELEVATION,
        )
        params.update(kwargs)
        return MockGeoTIFF(**params)

    # The general-purpose subject of most examples: 100.0 to 200.0 metres,
    # mean 150.0.
    elevation().save_to_file(master / 'example.tif')
    elevation().save_to_file(master / 'input.tif')
    elevation().save_to_file(master / 'baseline.tif')

    # A compressed counterpart, so comparison and efficiency examples have two
    # genuinely different files to talk about.
    elevation(compression='DEFLATE', predictor=3, tiled=True, tile_size=64).save_to_file(
        master / 'optimized.tif'
    )
    elevation(compression='DEFLATE', predictor=3).save_to_file(master / 'compressed.tif')

    # Three-band Byte imagery for the statistics package example.
    MockGeoTIFF(
        width=_SIZE, height=_SIZE, bands=3,
        data_type=gdal.GDT_Byte, crs='EPSG:32610',
        pixel_data=_IMAGERY,
    ).save_to_file(master / 'image.tif')

    # is_geotiff()'s three cases: projected, compound vertical, and none.
    elevation(crs='EPSG:32610').save_to_file(master / 'data.tif')
    elevation(crs='EPSG:32610+5703').save_to_file(master / 'dem_with_custom_vertical.tif')
    _write_ungeoreferenced_tiff(master / 'regular.tif')

    # A raster carrying the metadata the validation extractors read: the
    # GEO_METADATA tag, the XMP tag, an external sidecar and a GDAL metadata item.
    elevation(crs='EPSG:32610').save_to_file(master / 'metadata.tif')
    _attach_metadata(master / 'metadata.tif', tmp_path_factory.mktemp('doctest_xml'))

    # A directory of tiles, for the examples that take one instead of a file.
    tiles = master / 'tiles'
    tiles.mkdir()
    for name in ('tile_001_DSM.tif', 'tile_002_DSM.tif', 'tile_003_DTM.tif'):
        elevation(crs='EPSG:32610').save_to_file(tiles / name)

    return master


# ISO 19115 in the GEO_METADATA tag (50909).
_ISO_METADATA = '''<?xml version="1.0" encoding="UTF-8"?>
<gmd:MD_Metadata xmlns:gmd="http://www.isotc211.org/2005/gmd"
                 xmlns:gco="http://www.isotc211.org/2005/gco">
  <gmd:fileIdentifier>
    <gco:CharacterString>abc123-uuid</gco:CharacterString>
  </gmd:fileIdentifier>
</gmd:MD_Metadata>
'''

# XMP in tag 700.
_XMP_METADATA = '''<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
          xmlns:dc="http://purl.org/dc/elements/1.1/">
  <rdf:Description rdf:about="">
   <dc:description>
    <rdf:Alt><rdf:li xml:lang="x-default">Example elevation tile</rdf:li></rdf:Alt>
   </dc:description>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>'''

# FGDC in the external sidecar, found by its matching base name.
_SIDECAR_METADATA = '''<?xml version="1.0" encoding="UTF-8"?>
<metadata>
  <idinfo>
    <citation>
      <citeinfo>
        <title>Example Elevation Tile</title>
      </citeinfo>
    </citation>
  </idinfo>
</metadata>
'''


def _attach_metadata(filepath: Path, scratch: Path) -> None:
    """
    Give `filepath` a GEO_METADATA tag, an XMP tag, an XML sidecar and a GDAL metadata item.

    MockGeoTIFF writes pixels and georeferencing only, and the validation
    extractors read all of these. The GEO_METADATA tag goes through GTTK's own
    writer so the example exercises the same path the tool does; the sidecar is
    written next to the raster, where `find_xml_metadata_file` looks first.
    """
    from gttk.utils.geo_metadata_writer import write_geo_metadata

    iso_path = scratch / 'iso_19115.xml'
    iso_path.write_text(_ISO_METADATA, encoding='utf-8')

    ds = gdal.Open(str(filepath), gdal.GA_Update)
    write_geo_metadata(ds, iso_path)
    ds.SetMetadata([_XMP_METADATA], 'xml:XMP')
    # A plain GDAL metadata item, which GDAL stores in the GDAL_METADATA tag
    # (42112) -- the only place ValueExtractor.extract_gdal() looks for one.
    # AREA_OR_POINT would not do: GDAL encodes that as GTRasterTypeGeoKey instead.
    ds.SetMetadataItem('PRODUCT', 'DGED5')
    ds.FlushCache()
    ds = None

    filepath.with_suffix('.xml').write_text(_SIDECAR_METADATA, encoding='utf-8')


def _write_ungeoreferenced_tiff(filepath: Path) -> None:
    """
    Write a plain TIFF with neither a CRS nor a geotransform.

    MockGeoTIFF always sets a geotransform, and GDAL then emits a GeoKey
    directory -- which is exactly what `is_geotiff()` looks for. The one example
    that needs a *negative* answer therefore has to bypass the factory.
    """
    driver = gdal.GetDriverByName('GTiff')
    ds = driver.Create(str(filepath), _SIZE, _SIZE, 1, gdal.GDT_Float32)
    ds.GetRasterBand(1).WriteArray(_ELEVATION[0])
    ds.FlushCache()
    ds = None


@pytest.fixture(autouse=True)
def _doctest_sandbox(request):
    """
    Run each doctest in a private copy of `doctest_sample_dir`.

    A no-op for everything that is not a doctest, and the sample rasters are
    never built at all on a run that collects none -- the fixtures are resolved
    inside the branch, not in the signature.
    """
    if not isinstance(request.node, DoctestItem):
        return

    sandbox = request.getfixturevalue('tmp_path') / 'doctest'
    shutil.copytree(request.getfixturevalue('doctest_sample_dir'), sandbox)
    request.getfixturevalue('monkeypatch').chdir(sandbox)
