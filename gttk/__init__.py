"""GeoTIFF ToolKit (GTTK).

Importing this package is deliberately free of side effects. GTTK's GDAL settings --
including ``gdal.UseExceptions()`` -- are applied for the duration of an operation by
``gttk.utils.gdal_env.gdal_env`` and restored afterwards, so importing GTTK never
changes how GDAL behaves for the rest of the host process.

Callers reaching past the tool entry points into the utility layer, and relying on GDAL
raising rather than returning None, should wrap their own work in ``gdal_env()`` or call
``gdal.UseExceptions()`` themselves.
"""

_GDAL_MISSING = """\
GTTK requires GDAL's Python bindings (the `osgeo` package), which are not installed.

pip cannot install them on its own: the `gdal` package on PyPI is a source distribution
that compiles against an existing GDAL C++ library, so `pip install gdal` on a machine
without one fails with "Cannot open include file: 'gdal.h'". GDAL is therefore not a
declared dependency of GTTK. Install it from conda-forge:

    conda env create -f environment.yml
    conda activate gttk

or, into an environment you already have:

    conda install -c conda-forge "gdal>=3.11"

On Windows, OSGeo4W works too. If the GDAL library *and* its development headers are
already present, `pip install "geotiff-toolkit[gdal]"` will build the bindings.
"""

try:  # noqa: SIM105 -- the message is the point
    from osgeo import gdal as _gdal  # noqa: F401  (imported for the check only)
except ImportError as _exc:  # pragma: no cover -- needs an env without GDAL
    raise ImportError(_GDAL_MISSING) from _exc
