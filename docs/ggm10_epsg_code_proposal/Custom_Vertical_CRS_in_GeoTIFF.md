# Custom Vertical CRS in GeoTIFF: A Case Study

**Date:** December 2025  
**Subject:** Documentation of custom vertical datum storage limitations in GeoTIFF format  
**Example:** Geoide Gravimétrico Mexicano 2010 (GGM10)

## Executive Summary

This document describes the behavior of custom (non-EPSG) vertical coordinate reference systems in the GeoTIFF format. It demonstrates how datum information is transformed during the write/read cycle and explores the implications for organizations using custom vertical datums.

## Background

Mexico's national mapping agency (INEGI) uses the Geoide Gravimétrico Mexicano 2010 (GGM10) as their official vertical datum. This datum does not currently have an EPSG code, necessitating the use of custom WKT definitions when working with elevation data.

## The Custom Vertical CRS Definition

### Complete WKT2_2019 Definition

The GGM10 vertical datum can be fully described using WKT2 format:

```wkt
VERTCRS["GGM10 height",
    VDATUM["Geoide Gravimétrico Mexicano 2010"],
    CS[vertical,1],
        AXIS["gravity-related height (H)",up,
            LENGTHUNIT["metre",1]],
    USAGE[
        SCOPE["Geodesy, engineering survey, topographic mapping."],
        AREA["Mexico - onshore and offshore."],
        BBOX[14.02,-118.98,32.98,-86.02]],
    ID["PROJ","GGM2010"]]
```

### Compound CRS with Horizontal Component

When combined with a horizontal CRS (e.g., Mexico ITRF2008 / UTM zone 13N), the complete definition becomes:

```wkt
COMPOUNDCRS["Mexico ITRF2008 / UTM zone 13N + GGM10 height",
    PROJCRS["Mexico ITRF2008 / UTM zone 13N",
        BASEGEOGCRS["Mexico ITRF2008",
            DATUM["Mexico ITRF2008",
                ELLIPSOID["GRS 1980",6378137,298.257222101,
                    LENGTHUNIT["metre",1]]],
            PRIMEM["Greenwich",0,
                ANGLEUNIT["degree",0.0174532925199433]],
            ID["EPSG",6365]],
        CONVERSION["UTM zone 13N",
            METHOD["Transverse Mercator",
                ID["EPSG",9807]],
            PARAMETER["Latitude of natural origin",0,
                ANGLEUNIT["degree",0.0174532925199433],
                ID["EPSG",8801]],
            PARAMETER["Longitude of natural origin",-105,
                ANGLEUNIT["degree",0.0174532925199433],
                ID["EPSG",8802]],
            PARAMETER["Scale factor at natural origin",0.9996,
                SCALEUNIT["unity",1],
                ID["EPSG",8805]],
            PARAMETER["False easting",500000,
                LENGTHUNIT["metre",1],
                ID["EPSG",8806]],
            PARAMETER["False northing",0,
                LENGTHUNIT["metre",1],
                ID["EPSG",8807]]],
        CS[Cartesian,2],
            AXIS["(E)",east,
                ORDER[1],
                LENGTHUNIT["metre",1]],
            AXIS["(N)",north,
                ORDER[2],
                LENGTHUNIT["metre",1]],
        USAGE[
            SCOPE["Engineering survey, topographic mapping."],
            AREA["Mexico between 108°W and 102°W, onshore and offshore."],
            BBOX[14.05,-108,31.79,-102]],
        ID["EPSG",6368]],
    VERTCRS["GGM10 height",
        VDATUM["Geoide Gravimétrico Mexicano 2010"],
        CS[vertical,1],
            AXIS["gravity-related height (H)",up,
                LENGTHUNIT["metre",1]],
        USAGE[
            SCOPE["Geodesy, engineering survey, topographic mapping."],
            AREA["Mexico - onshore and offshore."],
            BBOX[14.02,-118.98,32.98,-86.02]],
        ID["PROJ","GGM2010"]]]
```

## Observed Behavior in GeoTIFF

### What Gets Written

Using GDAL's Python API, the complete WKT2 definition can be successfully parsed and written to a GeoTIFF file:

```python
from osgeo import osr, gdal

# Parse custom vertical CRS
vert_srs = osr.SpatialReference()
vert_srs.ImportFromWkt(custom_ggm10_wkt)

# Verify parsing was successful
print(vert_srs.GetName())  # Output: "GGM10 height"
print(vert_srs.GetAttrValue("VERT_DATUM"))  # Output: "Geoide Gravimétrico Mexicano 2010"

# Create compound CRS and write to GeoTIFF
compound_srs = osr.SpatialReference()
compound_srs.SetCompoundCS(name, horizontal_srs, vert_srs)
ds.SetProjection(compound_srs.ExportToWkt(['FORMAT=WKT2_2019']))
```

At this stage, all datum information is preserved in memory.

### What Gets Read Back

When the same file is read using `gdalinfo` or GDAL's API:

```bash
$ gdalinfo -wkt_format WKT2_2019 elevation.tif
```

The vertical component is returned as:

```wkt
VERTCRS["GGM10 height",
    VDATUM["unknown"],
    CS[vertical,1],
        AXIS["up",up,
            LENGTHUNIT["metre",1,
                ID["EPSG",9001]]]]
```

**Key differences:**

- `VDATUM["Geoide Gravimétrico Mexicano 2010"]` → `VDATUM["unknown"]`
- `AXIS["gravity-related height (H)",up]` → `AXIS["up",up]`
- USAGE, SCOPE, AREA, and BBOX metadata are lost
- The custom ID["PROJ","GGM2010"] is lost

### WKT1 Output

When querying with WKT1 format:

```bash
$ gdalinfo elevation.tif
```

The output shows:

```wkt
VERT_CS["GGM10 height",
    VERT_DATUM["unknown",2005],
    UNIT["metre",1,
        AUTHORITY["EPSG","9001"]],
    AXIS["Up",UP]]
```

The numeric code `2005` is the GeoKey value for "other/orthometric vertical datum" - a generic fallback.

## Technical Explanation

### GeoKey Storage Mechanism

GeoTIFF stores coordinate reference system information using numeric GeoKeys (TIFF tags 34735-34737). This system was designed to encode EPSG-defined coordinate systems efficiently:

- Each datum, ellipsoid, and coordinate system component has a numeric identifier
- Text descriptions are stored separately in tag 34737 (GeoAsciiParamsTag)
- The system works excellently for EPSG-registered components

### Limitation for Custom Datums

For custom vertical datums without EPSG codes:

1. There is no numeric GeoKey to represent "Geoide Gravimétrico Mexicano 2010"
2. GDAL uses generic fallback codes (e.g., VerticalDatumGeoKey = 32767 for "user-defined")
3. The VerticalCSTypeGeoKey defaults to 2005 ("other")
4. Detailed information (datum name, axis description, usage area) cannot be encoded

This is a **format limitation**, not a software bug. The GeoTIFF specification was designed around EPSG codes.

## Comparison with EPSG-Coded Datum

For comparison, here's how NAVD88 (EPSG:5703) behaves:

### Input WKT2

```wkt
VERTCRS["NAVD88 height",
    VDATUM["North American Vertical Datum 1988"],
    CS[vertical,1],
        AXIS["gravity-related height (H)",up,
            LENGTHUNIT["metre",1]],
    ID["EPSG",5703]]
```

### Output from GeoTIFF

```wkt
VERTCRS["NAVD88 height",
    VDATUM["North American Vertical Datum 1988"],
    CS[vertical,1],
        AXIS["gravity-related height (H)",up,
            LENGTHUNIT["metre",1]],
    USAGE[
        SCOPE["Geodesy, engineering survey, topographic mapping."],
        AREA["Mexico - onshore. United States (USA) - CONUS and Alaska - onshore - Alabama; Alaska; Arizona; Arkansas; California; Colorado; Connecticut; Delaware; Florida; Georgia; Idaho; Illinois; Indiana; Iowa; Kansas; Kentucky; Louisiana; Maine; Maryland; Massachusetts; Michigan; Minnesota; Mississippi; Missouri; Montana; Nebraska; Nevada; New Hampshire; New Jersey; New Mexico; New York; North Carolina; North Dakota; Ohio; Oklahoma; Oregon; Pennsylvania; Rhode Island; South Carolina; South Dakota; Tennessee; Texas; Utah; Vermont; Virginia; Washington; West Virginia; Wisconsin; Wyoming."],
        BBOX[14.51,172.42,71.4,-66.91]],
    ID["EPSG",5703]]
```

All information is preserved (with added USAGE information) because EPSG:5703 has defined GeoKey mappings.

## Current Workarounds

### 1. Metadata Storage

Software can store the complete WKT2 definition in a custom GDAL metadata item:

```python
ds.SetMetadataItem('COMPOUND_CRS_WKT2', full_wkt2_string)
```

This preserves the information but requires applications to explicitly retrieve it:

```python
full_wkt = ds.GetMetadataItem('COMPOUND_CRS_WKT2')
```

The metadata is visible in `gdalinfo` output under GDAL_METADATA (tag 42112).

### 2. External Sidecar Files

GDAL's Persistent Auxiliary Metadata (PAM) `.aux.xml` files can store additional CRS information, though this requires managing separate files.

### 3. Alternative Formats

Formats like GeoPackage support full WKT strings directly and are not limited by GeoKey encoding. However, this requires moving away from GeoTIFF.

## Implications

### For Data Producers (INEGI)

Mexican elevation data distributed with GGM10 vertical datum faces interoperability challenges:

- International users may not understand "VERT_DATUM[unknown]"
- Software may not recognize the vertical datum
- Automated processing pipelines may fail or produce incorrect results
- Metadata richness (USAGE, SCOPE, AREA) is lost in distribution

### For Software Developers

Applications working with custom vertical datums must:

- Implement special handling for non-EPSG vertical systems
- Consider storing complete WKT in custom metadata fields
- Document limitations clearly for end users
- Potentially offer alternative file formats

### For End Users

Users working with custom vertical datum data should:

- Be aware that datum information may be incomplete in GeoTIFF headers
- Check for custom metadata tags or auxiliary files
- Consider the datum documentation provided by data producers
- Understand that coordinate transformations may not work automatically

## Path Forward

### Short-term: Documentation and Metadata

The demonstrated metadata workaround (`COMPOUND_CRS_WKT2`) provides a practical solution within current GeoTIFF constraints. Data producers can adopt this approach to preserve datum information.

### Long-term: EPSG Registration

The most robust solution is EPSG registration of custom datums. For GGM10, this would involve:

1. Formal submission to EPSG Geodetic Parameter Dataset
2. Assignment of official EPSG code(s) for:
   - GGM10 vertical datum
   - GGM10 vertical CRS
   - Transformation parameters between GGM10 and other vertical datums
3. Universal recognition by all GDAL-based software

EPSG registration provides:

- International standardization and recognition
- Automatic software support without custom code
- Preservation of all metadata through GeoKey encoding
- Simplified data distribution and use

### Future GeoTIFF Versions

The GeoTIFF community may wish to consider enhanced vertical datum support in future specification versions. Potential approaches could include:

- Extended GeoKey ranges for custom datums
- Optional WKT string storage as primary CRS source
- Hybrid approaches that maintain backward compatibility

However, any changes would need careful consideration of backward compatibility and ecosystem impact.

## Conclusion

The transformation of custom vertical datum information in GeoTIFF files results from the format's reliance on numeric GeoKey encoding. While workarounds exist, the most effective long-term solution is formal EPSG registration of custom datums like GGM10.

This case study demonstrates the value of international geodetic standardization and the practical benefits of EPSG registration for national mapping agencies worldwide.

## Appendix: Test Commands

### Creating a GeoTIFF with GGM10 using the GeoTIFF ToolKit (GTTK)

```bash
python gttk optimize \
    -i input_dem.tif \
    -o output_dem.tif \
    -t dem \
    -s GGM10 \
    --verbose
```

### Inspecting the Result

```bash
# View WKT2 format
gdalinfo -wkt_format WKT2_2019 output_dem.tif

# View WKT1 format (default)
gdalinfo output_dem.tif

# View all metadata including custom fields
gdalinfo -mdd all output_dem.tif | grep COMPOUND_CRS_WKT2
gdalinfo -mdd all output_dem.tif | findstr /I CUSTOM_CRS_WKT2  # Windows cmd
```

### Retrieving Full WKT Programmatically

```python
from osgeo import gdal

ds = gdal.Open('output_dem.tif')

# Standard CRS (limited by GeoKey encoding)
standard_wkt = ds.GetSpatialRef().ExportToWkt(['FORMAT=WKT2_2019'])

# Full CRS from custom metadata (if stored)
full_wkt = ds.GetMetadataItem('COMPOUND_CRS_WKT2')

if full_wkt:
    print("Complete vertical datum information available in metadata")
```

---

*This document was prepared to facilitate discussion within the geospatial community about custom vertical datum support in GeoTIFF. Questions and feedback are welcome.*
