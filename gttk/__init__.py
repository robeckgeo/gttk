"""GeoTIFF ToolKit (GTTK).

Importing this package is deliberately free of side effects. GTTK's GDAL settings --
including ``gdal.UseExceptions()`` -- are applied for the duration of an operation by
``gttk.utils.gdal_env.gdal_env`` and restored afterwards, so importing GTTK never
changes how GDAL behaves for the rest of the host process.

Callers reaching past the tool entry points into the utility layer, and relying on GDAL
raising rather than returning None, should wrap their own work in ``gdal_env()`` or call
``gdal.UseExceptions()`` themselves.
"""
