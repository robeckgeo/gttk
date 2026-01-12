# ArcGIS Pro PROJ Database Fix - Implementation Plan

## Problem Summary

In ArcGIS Pro's Python environment, `GetSpatialRef()` succeeds but subsequent `osr.SpatialReference` method calls fail silently due to missing `PROJ_LIB` environment variable. This creates incomplete `projection_info` dictionaries that cascade failures to multiple report sections.

### Affected Sections

- **BoundingBox**: Missing `horizontal_unit` (shows blank instead of "degree" or "metre")
- **Tiling**: Shows "units" instead of proper unit names ("arc seconds", "metre", etc.)
- **Georeference**: Missing EPSG codes for datum, missing unit names
- **GeoExtent**: Wrong coordinates (shows full globe -180/180, -90/90 instead of actual extent)

### Root Cause

```python
# In ArcGIS Pro (without PROJ_LIB set):
srs = ds.GetSpatialRef()  # ✓ Succeeds, returns SRS object
srs.GetLinearUnitsName()  # ✗ Returns None (should return "metre")
srs.GetAuthorityCode('DATUM')  # ✗ Returns None (should return "6326")
```

## Solution Design

### Detection Strategy

Check if `projection_info` is incomplete after calling `_retrieve_projection_info()`:

- For projected CRS: missing `linear_unit_name`
- For geographic CRS: missing `angular_unit_name`

### Fallback Strategy

When incomplete projection_info is detected:

1. Call `get_json_info_from_osgeo4w()` to get full gdalinfo JSON
2. Parse JSON using `_parse_json_projection_info()`
3. Replace incomplete projection_info with complete data from JSON

### Implementation Changes

#### File: `gttk/utils/geotiff_processor.py`

**Modify [`read_geotiff()`](gttk/utils/geotiff_processor.py:1158) function (lines 1173-1232):**

Current logic:

```python
srs = ds.GetSpatialRef()
projection_info = {}

if not srs:
    # Fallback: Try OSGeo4W
    json_info = get_json_info_from_osgeo4w(filepath)
    if json_info:
        wkt_from_json = json_info.get('coordinateSystem', {}).get('wkt')
        if wkt_from_json:
            srs = osr.SpatialReference()
            srs.ImportFromWkt(wkt_from_json)
        projection_info = _parse_json_projection_info(json_info)

vert_srs = get_vertical_srs(ds)
vert_srs_name = vert_srs.GetName() if vert_srs else None

# Only retrieve from SRS object if we didn't already populate it from JSON fallback
if srs and not projection_info:
    projection_info = _retrieve_projection_info(ds, srs)

native_bbox = _calculate_native_bbox(ds, gt, projection_info) if gt else None
geographic_corners = _calculate_geographic_corners(ds, srs, gt, projection_info) if gt and srs else None
```

New logic:

```python
srs = ds.GetSpatialRef()
projection_info = {}
used_json_fallback = False

# Fallback #1: If GetSpatialRef() returns None
if not srs:
    logger.info("GetSpatialRef() returned None, attempting OSGeo4W fallback...")
    try:
        json_info = get_json_info_from_osgeo4w(str(filepath))
        if json_info:
            logger.info("Successfully retrieved SRS info using OSGeo4W gdalinfo")
            wkt_from_json = json_info.get('coordinateSystem', {}).get('wkt')
            if wkt_from_json:
                srs = osr.SpatialReference()
                srs.ImportFromWkt(wkt_from_json)
            projection_info = _parse_json_projection_info(json_info)
            used_json_fallback = True
    except Exception as e:
        logger.warning(f"OSGeo4W fallback failed: {e}")

# Try standard extraction if we haven't used JSON yet
if srs and not used_json_fallback:
    projection_info = _retrieve_projection_info(ds, srs)
    
    # Fallback #2: If projection_info is incomplete (ArcGIS Pro without PROJ_LIB)
    # Check for missing unit names as indicator
    is_incomplete = False
    if srs.IsProjected() and not projection_info.get('linear_unit_name'):
        is_incomplete = True
        logger.info("Projected CRS detected but linear_unit_name missing")
    elif srs.IsGeographic() and not projection_info.get('angular_unit_name'):
        is_incomplete = True
        logger.info("Geographic CRS detected but angular_unit_name missing")
    
    if is_incomplete:
        logger.info("projection_info incomplete, attempting OSGeo4W JSON fallback...")
        try:
            json_info = get_json_info_from_osgeo4w(str(filepath))
            if json_info:
                logger.info("Successfully retrieved complete projection info via OSGeo4W JSON")
                # Parse and replace with complete info from JSON
                projection_info = _parse_json_projection_info(json_info)
                used_json_fallback = True
        except Exception as e:
            logger.warning(f"OSGeo4W JSON fallback failed: {e}")

vert_srs = get_vertical_srs(ds)
vert_srs_name = vert_srs.GetName() if vert_srs else None

native_bbox = _calculate_native_bbox(ds, gt, projection_info) if gt else None
geographic_corners = _calculate_geographic_corners(ds, srs, gt, projection_info) if gt and srs else None
```

#### File: `gttk/utils/gdal_runner.py`

**Remove old function:**

- Delete `get_srs_from_osgeo4w()` function (no longer needed)
- Keep `get_json_info_from_osgeo4w()` function

**Update imports in other files:**

- Remove `get_srs_from_osgeo4w` from import statements
- Keep only `get_json_info_from_osgeo4w`

## Testing Requirements

### Test Case 1: EPSG:4979 in ArcGIS Pro

**File**: Any GeoTIFF with EPSG:4979 (WGS 84 3D)

**Expected Results**:

- BoundingBox horizontal_unit: "degree"
- Tiling resolution units: "arc seconds" (not "units")
- Georeference datum_code: "6326"
- Georeference angular_unit: "degree"
- GeoExtent: Actual file extent (not -180/180, -90/90)

### Test Case 2: Projected CRS (e.g., UTM) in ArcGIS Pro

**File**: Any GeoTIFF with projected CRS (e.g., EPSG:32632)

**Expected Results**:

- BoundingBox horizontal_unit: "metre"
- Tiling resolution units: "m" (not "units")
- Georeference linear_unit: "metre"
- Georeference projected_cs_code: "32632"

### Test Case 3: CLI Mode (Non-ArcGIS)

**File**: Any GeoTIFF

**Expected Results**:

- All sections work correctly WITHOUT triggering JSON fallback
- No performance degradation from subprocess calls

## Implementation Notes

### Why This Approach Works

1. **Minimal changes**: Only modifies `geotiff_processor.py` and `gdal_runner.py`
2. **No breaking changes**: CLI mode continues working normally
3. **Automatic detection**: No need to pass `arc_mode` flag through call chain
4. **Graceful degradation**: Falls back to incomplete info if JSON approach also fails
5. **Preserves WKT/PROJJSON**: SRS object still available for export functions

### Why We Don't Need `arc_mode` Flag

The incomplete projection_info is a symptom that's detectable directly:

- Missing unit names = broken PROJ environment
- This only happens in ArcGIS Pro without PROJ_LIB
- Automatically triggers fallback without explicit mode flag

### Performance Considerations

- JSON fallback only triggers when needed (ArcGIS Pro with problematic CRS)
- CLI users never experience subprocess overhead
- Subprocess call is already fast (~200ms) and only happens once per file

## Rollback Plan

If this fix causes issues:

1. Revert changes to `geotiff_processor.py` lines 1173-1232
2. Restore previous fallback logic (only when `srs` is None)
3. Keep diagnostic scripts for manual investigation

## Related Files

- [`gttk/utils/geotiff_processor.py`](gttk/utils/geotiff_processor.py) - Primary fix location
- [`gttk/utils/gdal_runner.py`](gttk/utils/gdal_runner.py) - Remove old function
- [`gttk/utils/metadata_extractor.py`](gttk/utils/metadata_extractor.py) - Update imports
- [`plans/diagnostic_scripts_guide.md`](plans/diagnostic_scripts_guide.md) - Diagnostic reference
- [`plans/arcgis_proj_diagnosis.md`](plans/arcgis_proj_diagnosis.md) - Problem documentation
