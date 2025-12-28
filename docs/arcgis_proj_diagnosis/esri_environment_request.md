# Request: PROJ_LIB Environment Variable for ArcGIS Pro Python Environment

## Summary

This document requests a simple enhancement to the ArcGIS Pro Python environment configuration that would significantly improve compatibility for developers building GDAL-based tools within the ArcGIS ecosystem.

**The Request:** Set the `PROJ_LIB` environment variable to point to ArcGIS Pro's bundled `proj.db` location when the Python environment activates.

**The Benefit:** This would enable GDAL/OGR methods that rely on the PROJ coordinate system database to function correctly for third-party tools built on ArcGIS Pro's Python environment.

---

## Background

ArcGIS Pro bundles a complete PROJ database (`proj.db`) containing modern EPSG coordinate system definitions, including newer codes like EPSG:4979 (WGS 84 3D). This database is located at `C:\Program Files\ArcGIS\Pro\Resources\pedata\gdaldata\proj.db`.

However, when developers create Python tools using the ArcGIS Pro Python environment (via `arcpy` or standalone scripts), GDAL/OGR methods cannot access this database because the `PROJ_LIB` environment variable is not set.

---

## Impact on Third-Party Development

While this does not affect ArcGIS Pro's core functionality, it creates challenges for developers building GDAL-based geospatial tools in the ArcGIS Pro Python environment:

### Current Behavior

When using GDAL's Python bindings (`from osgeo import gdal, osr`) in ArcGIS Pro Python:

- `GetSpatialRef()` succeeds and returns an `osr.SpatialReference` object
- **But** subsequent method calls fail silently:
  - `GetLinearUnitsName()` → returns `None` (should return "metre", "foot", etc.)
  - `GetAngularUnitsName()` → returns `None` (should return "degree", etc.)
  - `GetAuthorityCode('DATUM')` → returns `None` (should return EPSG code)
  - Modern EPSG codes (4979, 6319, etc.) cannot be resolved

### Example Use Case

A developer building a metadata extraction tool needs to report coordinate system units and EPSG codes. Without `PROJ_LIB` set, these fields are blank or show placeholder values like "units" instead of "arc seconds" or "metres", reducing the utility of the tool for end users.

---

## Proposed Solution

**Add this line to ArcGIS Pro's Python environment activation script** (similar to how `GDAL_DATA` is already set):

```python
PROJ_LIB = Path(arcpy.GetInstallInfo()['InstallDir']) / 'Resources' / 'pedata' / 'gdaldata'
os.environ['PROJ_LIB'] = str(PROJ_LIB)
```

This would be added to:

- `C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\etc\conda\activate.d\activate_gdal.bat`

---

## Validation

We have confirmed this fix works via diagnostic testing:

**Test 1:** Default ArcGIS Pro environment (PROJ_LIB not set)

```python
from osgeo import gdal, osr
srs = osr.SpatialReference()
srs.ImportFromEPSG(4979)  # WGS 84 3D
print(srs.GetAngularUnitsName())  # Prints: None ❌
```

**Test 2:** After setting PROJ_LIB before importing GDAL

```python
import os
os.environ['PROJ_LIB'] = r'C:\Program Files\ArcGIS\Pro\Resources\pedata\gdaldata'
from osgeo import gdal, osr
srs = osr.SpatialReference()
srs.ImportFromEPSG(4979)
print(srs.GetAngularUnitsName())  # Prints: degree ✅
```

The database contains the required definitions (verified via SQLite query):

```sql
SELECT auth_name, code, name FROM crs_view WHERE code = '4979';
-- Returns: EPSG | 4979 | WGS 84
```

---

## Why This Matters for the ArcGIS Ecosystem

Many developers choose to build their geospatial tools within the ArcGIS Pro Python environment because it provides:

- Access to `arcpy` for Esri-specific workflows
- Integration with ArcGIS Pro toolboxes
- A familiar environment for ArcGIS users

By setting `PROJ_LIB`, Esri would make it easier for these developers to create high-quality tools that leverage the full capabilities of GDAL while remaining compatible with the ArcGIS ecosystem. This benefits both the developer community and ArcGIS Pro users who rely on these third-party tools.

---

## Request

We kindly request that the Esri development team consider adding the `PROJ_LIB` environment variable to the ArcGIS Pro Python environment activation process in a future update. This simple change would remove a significant hurdle for developers building GDAL-based tools in the ArcGIS Pro ecosystem.

Thank you for considering this enhancement!

---

## Additional Information

If Esri developers would like to reproduce the issue or need more technical details about the specific GDAL methods affected, we can provide:

- Complete diagnostic scripts
- List of affected GDAL/OGR methods
- Example use cases from real-world tool development

Please feel free to reach out for any clarification or additional testing.
