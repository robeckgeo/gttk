# GTTK Validation Package

Comprehensive documentation for the GeoTIFF ToolKit (GTTK) metadata validation system.

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Rule File Structure](#rule-file-structure)
- [Section Types](#section-types)
- [Constraint Types](#constraint-types)
- [Data Types](#data-types)
- [XPath Expressions](#xpath-expressions)
- [JSONPath Expressions](#jsonpath-expressions)
- [Batch Processing](#batch-processing)
- [Creating Custom Rules](#creating-custom-rules)
- [Troubleshooting](#troubleshooting)

---

## Overview

The GTTK validation package enables automated validation of GeoTIFF metadata against user-defined rules. This system supports validation of:

- **TIFF Tags**: Core TIFF metadata fields (tag numbers 254-65535)
- **GeoKeys**: GeoTIFF spatial reference keys (GeoKeyDirectoryTag)
- **GDAL Metadata**: GDAL-specific metadata items (GDAL_METADATA tag) with on-demand statistics
- **GEO Metadata**: ISO 19115/19139 XML embedded in GEO_METADATA tag
- **XMP Metadata**: Dublin Core/XMP metadata in XMLPacket tag
- **External XML**: Sidecar XML files following various schemas
- **PROJJSON**: CRS definitions in PROJ JSON format

### Key Features

- **Product-based organization**: Group related rules by data product or standard
- **Seven constraint types**: exact, enum, regex, range, ranges, exists, forbidden
- **On-demand statistics**: STATISTICS_* keys are computed from raster data, not read from metadata
- **Extended data types**: Basic types plus date, datetime, url, and email validation
- **XPath support**: Full XPath 1.0 for XML-based sections
- **JSONPath support**: Full JSONPath for PROJJSON validation
- **Batch processing**: Validate multiple files with filename pattern filtering
- **Detailed reports**: HTML/Markdown reports with pass/fail/skip status

Each rule evaluation produces one of three statuses:

| Status | Icon | Meaning |
|--------|------|---------|
| **PASS** | ✅ | Value meets all constraint requirements |
| **FAIL** | ❌ | Value does not meet constraint requirements |
| **SKIP** | ⚠️ | Rule was skipped (optional field not present, or section missing) |

---

## Quick Start

### 1. Create a Rules File

Create a TOML file in `gttk/resources/rules/` (e.g., `my_product_rules.toml`):

```toml
[MY-PRODUCT]
title = "My Product Validation Rules"
description = "Validation rules for my GeoTIFF product"
author = "Your Organization"
updated = "2026-01-17"

# Require 32-bit floating point
[[MY-PRODUCT.tag]]
tag = 258
description = "BitsPerSample"
data_type = "integer"
constraint = "exact"
expected = 32

# Require PixelIsPoint raster type
[[MY-PRODUCT.geokey]]
geokey = 1025
description = "GTRasterTypeGeoKey"
data_type = "integer"
constraint = "exact"
expected = 2
comment = "2 = RasterPixelIsPoint"
```

### 2. Run Validation

```bash
# Validate a single file
gttk validate -i input.tif -p MY-PRODUCT

# Validate all files in a directory
gttk validate -i input_directory/ -p MY-PRODUCT

# Filter files by name substring (directory mode only)
gttk validate -i input_directory/ -p MY-PRODUCT --name-string "DEM"

# Use custom rules directory
gttk validate -i input.tif -r /path/to/rules/ -p MY-PRODUCT

# Specify output directory
gttk validate -i input.tif -p MY-PRODUCT -o /output/reports/
```

### 3. Review Results

The validation generates an HTML or Markdown report showing:

- Summary statistics (total rules, passed, failed, skipped)
- Detailed results organized by section
- Descriptive messages explaining each validation outcome

---

## Rule File Structure

Rules files use [TOML](https://toml.io/) format with a hierarchical structure.

### Product Header

Each product begins with a table containing metadata:

```toml
[PRODUCT-NAME]
title = "Human-Readable Product Title"
description = "Detailed description of what this product represents"
author = "Organization or person who created these rules"
updated = "2026-01-17"  # Last modification date
```

### Rule Definitions

Rules are defined as arrays of tables using TOML's `[[...]]` syntax:

```toml
[[PRODUCT-NAME.section]]
key = "identifier"           # Tag number, GeoKey ID, name, xpath, or jsonpath
description = "Field Name"   # Human-readable field name
data_type = "string"         # Data type for validation
constraint = "exists"        # Constraint type
expected = value             # Expected value(s) - depends on constraint
optional = false             # Whether field is optional (default: false)
comment = "Additional notes" # Documentation (optional)
```

### Section-Specific Key Fields

Each section type uses a different field name for the key:

| Section | Key Field | Example |
|---------|-----------|---------|
| `tag` | `tag` | `tag = 258` |
| `geokey` | `geokey` | `geokey = 1025` |
| `gdal` | `name` | `name = "STATISTICS_MINIMUM"` or `name = "COLORINTERP:0"` |
| `geo` | `xpath` | `xpath = "//gmd:fileIdentifier/..."` |
| `xmp` | `xpath` | `xpath = "//dc:title/..."` |
| `xml` | `xpath` | `xpath = "//idinfo/citation/..."` |
| `projjson` | `jsonpath` | `jsonpath = "$.type"` |

---

## Section Types

### TIFF Tags (`tag`)

Validates core TIFF tag values stored in the Image File Directory (IFD).

```toml
[[PRODUCT.tag]]
tag = 258
description = "BitsPerSample"
data_type = "integer"
constraint = "exact"
expected = 32
```

**Common TIFF Tags:**

| Tag | Name | Common Values (not exhaustive) |
|-----|------|----------------|
| 254 | NewSubfileType | 0 (full image), 1 (reduced image) |
| 256 | ImageWidth | Pixel width |
| 257 | ImageLength | Pixel height |
| 258 | BitsPerSample | 8, 16, 32 |
| 259 | Compression | 1 (none), 5 (LZW), 8 (DEFLATE) |
| 262 | PhotometricInterpretation | 1 (BlackIsZero), 2 (RGB), 3 (palette) |
| 269 | DocumentName | String |
| 270 | ImageDescription | String |
| 277 | SamplesPerPixel | Number of bands |
| 306 | DateTime | "YYYY:MM:DD HH:MM:SS" |
| 339 | SampleFormat | 2 (Signed integer), 3 (IEEE floating point) |

### GeoKeys (`geokey`)

Validates GeoTIFF spatial reference parameters from the GeoKeyDirectoryTag (34735).

```toml
[[PRODUCT.geokey]]
geokey = 1024
description = "GTModelTypeGeoKey"
data_type = "integer"
constraint = "exact"
expected = 1
comment = "1 = ModelTypeProjected"
```

**Common GeoKeys:**

| GeoKey | Name | Values |
|--------|------|--------|
| 1024 | GTModelTypeGeoKey | 0 (undefined), 1 (projected), 2 (geographic), 3 (geocentric) |
| 1025 | GTRasterTypeGeoKey | 1 (PixelIsArea), 2 (PixelIsPoint) |
| 2048 | GeodeticCRSGeoKey | EPSG code for geographic CRS |
| 3072 | ProjectedCRSGeoKey | EPSG code for projected CRS |
| 4096 | VerticalGeoKey | EPSG code for vertical CRS |

### GDAL Metadata (`gdal`)

Validates metadata items from the GDAL_METADATA tag (42112), with special support for on-demand statistics calculation and color interpretation queries.

**Important:** Statistics and Color Interpretation rules are validated even if the GDAL_METADATA tag (42112) is missing from the file. These values are computed on-demand directly from the raster data via GDAL, ensuring accurate validation regardless of whether metadata has been pre-computed.

#### On-Demand Statistics

Statistics keys (STATISTICS_*) are **computed on-demand** from the actual raster data, not read from stored metadata. This ensures accurate validation even when GDAL_METADATA is missing or stale.

**Supported statistics keys:**

| Name | Description |
|------|-------------|
| `STATISTICS_MINIMUM` | Minimum pixel value |
| `STATISTICS_MAXIMUM` | Maximum pixel value |
| `STATISTICS_MEAN` | Mean pixel value |
| `STATISTICS_STDDEV` | Standard deviation |
| `STATISTICS_VALID_PERCENT` | Percentage of valid (non-nodata) pixels |

#### Band Suffix Syntax

Use the `name:sample` syntax to specify which band(s) to validate. The sample index is 0-based (band 1 = sample 0).

| Syntax | Behavior |
|--------|----------|
| `KEY` | Validates **ALL** bands. For multi-band images, the constraint must pass for every band. |
| `KEY:0` | Validates band 1 only (sample index 0) |
| `KEY:1` | Validates band 2 only (sample index 1) |
| `KEY:N` | Validates band N+1 only (sample index N) |

**Example: Statistics for all bands vs. specific bands**

```toml
# Validate minimum elevation across ALL bands
# For multi-band images, ALL bands must pass the constraint
[[PRODUCT.gdal]]
name = "STATISTICS_MINIMUM"
description = "Minimum Elevation (all bands)"
data_type = "float"
constraint = "range"
expected = { min = -430.0, max = 8850.0 }
comment = "Catches impossible outliers for elevation data"

# Validate specific band only (band 1 = sample 0)
[[PRODUCT.gdal]]
name = "STATISTICS_MAXIMUM:0"
description = "Maximum Value Band 1"
data_type = "float"
constraint = "range"
expected = { min = 0, max = 255 }

# Validate band 2 only (sample 1)
[[PRODUCT.gdal]]
name = "STATISTICS_MEAN:1"
description = "Mean Value Band 2"
data_type = "float"
constraint = "range"
expected = { min = 0, max = 255 }
```

#### Color Interpretation

`COLORINTERP` keys query the band's color interpretation via GDAL. Like statistics, these are queried on-demand and work even without GDAL_METADATA.

**Supported color interpretation values:**

| Value | Description |
|-------|-------------|
| `Red` | Red band |
| `Green` | Green band |
| `Blue` | Blue band |
| `NIR` | Near-infrared band |
| `Gray` | Grayscale band |
| `Alpha` | Alpha/transparency band |
| `Palette` | Palette/indexed color |
| `Undefined` | No color interpretation set |

**Example: Validate 4-band NAIP imagery**

| name:sample | expected |
|-------------|----------|
| `COLORINTERP:0` | `Red` |
| `COLORINTERP:1` | `Green` |
| `COLORINTERP:2` | `Blue` |
| `COLORINTERP:3` | `NIR` |

```toml
# Validate 4-band NAIP imagery color interpretation
[[PRODUCT.gdal]]
name = "COLORINTERP:0"
description = "Band 1 Color"
data_type = "string"
constraint = "exact"
expected = "Red"

[[PRODUCT.gdal]]
name = "COLORINTERP:1"
description = "Band 2 Color"
data_type = "string"
constraint = "exact"
expected = "Green"

[[PRODUCT.gdal]]
name = "COLORINTERP:2"
description = "Band 3 Color"
data_type = "string"
constraint = "exact"
expected = "Blue"

[[PRODUCT.gdal]]
name = "COLORINTERP:3"
description = "Band 4 Color"
data_type = "string"
constraint = "exact"
expected = "NIR"

# Validate ALL bands have defined color interpretation
# (no band suffix = checks all bands)
[[PRODUCT.gdal]]
name = "COLORINTERP"
description = "All bands must have color interpretation"
data_type = "string"
constraint = "enum"
expected = ["Red", "Green", "Blue", "NIR", "Gray", "Alpha"]
```

#### Standard GDAL Metadata Items

All other keys are looked up in the GDAL_METADATA XML tag. Unlike statistics and color interpretation, these require the GDAL_METADATA tag to be present in the file.

| Name | Description |
|------|-------------|
| `AREA_OR_POINT` | "Area" or "Point" |
| `TIFFTAG_DATETIME` | Creation date |
| Custom items | Any item stored in GDAL_METADATA |

```toml
[[PRODUCT.gdal]]
name = "AREA_OR_POINT"
description = "Raster Type"
data_type = "string"
constraint = "exact"
expected = "Point"
```

### GEO Metadata (`geo`)

Validates ISO 19115/19139 XML metadata embedded in the GEO_METADATA tag (50909).

```toml
[[PRODUCT.geo]]
xpath = "//gmd:fileIdentifier/gco:CharacterString"
description = "File Identifier"
data_type = "string"
constraint = "exists"
```

### XMP Metadata (`xmp`)

Validates XMP/Dublin Core metadata from the XMLPacket tag (700).

```toml
[[PRODUCT.xmp]]
xpath = "//dc:title/rdf:Alt/rdf:li"
description = "Dublin Core Title"
data_type = "string"
constraint = "exists"
```

### External XML (`xml`)

Validates sidecar XML files that accompany GeoTIFF files.

```toml
[[PRODUCT.xml]]
xpath = "//idinfo/citation/citeinfo/title"
description = "Citation Title"
data_type = "string"
constraint = "exists"
```

**Sidecar File Discovery:**
The validator searches for XML files with matching base names:
- `file.tif` → `file.xml`, `file.tif.xml`

### PROJJSON (`projjson`)

Validates coordinate reference system definitions in PROJ JSON format.

```toml
[[PRODUCT.projjson]]
jsonpath = "$.type"
description = "CRS Type"
data_type = "string"
constraint = "enum"
expected = ["ProjectedCRS", "GeographicCRS", "CompoundCRS"]
```

---

## Constraint Types

### `exact`

Value must exactly match the expected value.

```toml
constraint = "exact"
expected = 32         # Numeric
expected = "WGS 84"   # String
expected = [8, 8, 8]  # Array (for multi-valued tags like BitsPerSample)
```

### `enum`

Value must be one of the allowed values in a list.

```toml
constraint = "enum"
expected = [5, 8]                      # Numeric list
expected = ["LZW", "DEFLATE", "ZSTD"]  # String list
```

### `regex`

Value must match the regular expression pattern.

```toml
constraint = "regex"
expected = "^\\d{4}-\\d{2}-\\d{2}$"  # ISO date pattern
expected = "^U_.*_DEM_.*$"           # Filename pattern
expected = ".*USGS.*National.*"      # Contains text
```

**Note:** Backslashes must be escaped in TOML strings (`\\d` instead of `\d`).

### `range`

Numeric value must fall within the specified range (inclusive).

```toml
constraint = "range"
expected = { min = 0, max = 100 }  # Both bounds
expected = { min = 0 }             # Minimum only
expected = { max = 100 }           # Maximum only
```

### `ranges`

Numeric value must fall within any of the specified ranges.

```toml
constraint = "ranges"
expected = [
  { min = 32601, max = 32660 },  # UTM North zones
  { min = 32701, max = 32760 },  # UTM South zones
  { min = 5041, max = 5042 }     # UPS North / South
]
```

### `exists`

Field must be present with a non-null value. The actual value is not checked.

```toml
constraint = "exists"
# No 'expected' value needed
```

### `forbidden`

Field must NOT be present. Fails if the field exists with any value.

```toml
constraint = "forbidden"
# No 'expected' value needed
comment = "This field should not be present in compliant files"
```

---

## Data Types

### Basic Data Types

| Type | Description | Example Values |
|------|-------------|----------------|
| `string` | Text value | `"Hello"`, `"WGS 84"` |
| `integer` | Whole number | `1`, `32`, `4326` |
| `float` | Decimal number | `3.14`, `-430.5` |
| `boolean` | True/false | `true`, `false` |

### Extended Data Types

| Type | Description | Format |
|------|-------------|--------|
| `date` | ISO 8601 date | `YYYY-MM-DD` |
| `datetime` | ISO 8601 datetime | `YYYY-MM-DDThh:mm:ss[.sss][Z\|+hh:mm]` |
| `url` | Valid URL | `http://`, `https://`, `ftp://`, `ftps://`, `sftp://`, `s3://` |
| `email` | Email address | `user@domain.tld` |

**Extended type examples:**

```toml
# Validate creation date format
[[PRODUCT.gdal]]
name = "CREATION_DATE"
description = "File Creation Date"
data_type = "date"
constraint = "exists"

# Validate timestamp
[[PRODUCT.xmp]]
xpath = "//xmp:CreateDate"
description = "XMP Create Date"
data_type = "datetime"
constraint = "exists"

# Validate download URL
[[PRODUCT.xml]]
xpath = "//gmd:linkage/gmd:URL"
description = "Resource URL"
data_type = "url"
constraint = "exists"

# Validate contact email
[[PRODUCT.xml]]
xpath = "//gmd:electronicMailAddress/gco:CharacterString"
description = "Contact Email"
data_type = "email"
constraint = "exists"
```

---

## XPath Expressions

XPath expressions are used for `geo`, `xmp`, and `xml` sections to navigate XML documents.

### Basic XPath Syntax

| Expression | Description |
|------------|-------------|
| `/root/child` | Absolute path from root |
| `//element` | Find element anywhere in document |
| `element/@attribute` | Select attribute value |
| `element/text()` | Select text content |
| `element[1]` | First element (1-indexed) |
| `element[@attr='value']` | Element with specific attribute |

### Namespace Handling

GTTK automatically handles XML namespaces. You can use namespace prefixes in XPath:

```toml
# ISO 19115/19139 namespaces
xpath = "//gmd:fileIdentifier/gco:CharacterString"
xpath = "//gmd:identificationInfo//gmd:title/gco:CharacterString"

# Dublin Core / XMP namespaces
xpath = "//dc:title/rdf:Alt/rdf:li"
xpath = "//xmp:CreateDate"

# No namespace (FGDC)
xpath = "//idinfo/citation/citeinfo/title"
```

**Supported Namespace Prefixes:**

| Prefix | URI | Usage |
|--------|-----|-------|
| `gmd` | `http://www.isotc211.org/2005/gmd` | ISO 19115 |
| `gco` | `http://www.isotc211.org/2005/gco` | ISO 19115 common |
| `gml` | `http://www.opengis.net/gml/3.2` | GML |
| `dc` | `http://purl.org/dc/elements/1.1/` | Dublin Core |
| `xmp` | `http://ns.adobe.com/xap/1.0/` | XMP |
| `rdf` | `http://www.w3.org/1999/02/22-rdf-syntax-ns#` | RDF |
| `photoshop` | `http://ns.adobe.com/photoshop/1.0/` | Photoshop |

### Complex XPath Examples

```toml
# Select attribute value
xpath = "//gmd:MD_ScopeCode/@codeListValue"

# Select with predicate(s)
xpath = "//gmd:CI_ResponsibleParty[gmd:role/gmd:CI_RoleCode/@codeListValue='pointOfContact']/gmd:contactInfo/gmd:CI_Contact/gmd:address/gmd:CI_Address/gmd:city/gco:CharacterString"

# Select from specific position
xpath = "//gmd:keyword[1]/gco:CharacterString"
```

---

## JSONPath Expressions

JSONPath expressions are used for `projjson` sections to navigate PROJJSON structures.

### Basic JSONPath Syntax

| Expression | Description |
|------------|-------------|
| `$.field` | Root-level field |
| `$.parent.child` | Nested field |
| `$.array[0]` | First array element (0-indexed) |
| `$.array[*]` | All array elements |
| `$..field` | Recursive descent (find all) |

### JSONPath Examples

```toml
# Root-level fields
[[PRODUCT.projjson]]
jsonpath = "$.type"
description = "CRS Type"
data_type = "string"
constraint = "enum"
expected = ["ProjectedCRS", "GeographicCRS"]

# Nested object access
[[PRODUCT.projjson]]
jsonpath = "$.base_crs.datum.name"
description = "Datum Name"
data_type = "string"
constraint = "exists"

# Deep nesting
[[PRODUCT.projjson]]
jsonpath = "$.base_crs.datum.ellipsoid.semi_major_axis"
description = "Semi-major Axis"
data_type = "float"
constraint = "range"
expected = { min = 6000000, max = 7000000 }

# Array indexing
[[PRODUCT.projjson]]
jsonpath = "$.coordinate_system.axis[0].name"
description = "First Axis Name"
data_type = "string"
constraint = "exists"

# Array element property
[[PRODUCT.projjson]]
jsonpath = "$.coordinate_system.axis[0].unit"
description = "First Axis Unit"
data_type = "string"
constraint = "enum"
expected = ["metre", "degree", "foot"]
```

### PROJJSON Structure Reference

Typical PROJJSON structure for a Projected CRS:

```json
{
  "type": "ProjectedCRS",
  "name": "WGS 84 / UTM zone 10N",
  "base_crs": {
    "name": "WGS 84",
    "datum": {
      "name": "World Geodetic System 1984",
      "ellipsoid": {
        "name": "WGS 84",
        "semi_major_axis": 6378137,
        "inverse_flattening": 298.257223563
      }
    }
  },
  "coordinate_system": {
    "subtype": "Cartesian",
    "axis": [
      { "name": "Easting", "abbreviation": "E", "direction": "east", "unit": "metre" },
      { "name": "Northing", "abbreviation": "N", "direction": "north", "unit": "metre" }
    ]
  },
  "id": { "authority": "EPSG", "code": 32610 }
}
```

---

## Batch Processing

### Directory Validation

Validate all GeoTIFF files in a directory:

```bash
gttk validate -i /path/to/directory/ -p PRODUCT-NAME
```

### Name String Filtering

Filter files by substring match in the filename:

```bash
# Validate only files containing "DEM" in the name
gttk validate -i /data/ -p DGED5 --name-string "DEM"

# Validate files from specific year
gttk validate -i /data/ -p 3DEP --name-string "2024"

# Validate specific tile naming pattern
gttk validate -i /data/ -p GLO-30 --name-string "N45_E010"
```

### Output Options

```bash
# Generate HTML reports (default)
gttk validate -i input.tif -p PRODUCT

# Generate Markdown reports
gttk validate -i input.tif -p PRODUCT --report-format md

# Skip individual reports (JSON and GeoPackage only)
gttk validate -i input.tif -p PRODUCT --write-reports false

# Custom output directory
gttk validate -i input.tif -p PRODUCT -o /reports/
```

### Output Structure

Validation creates an output folder containing:

```
{input_basename}_validation/
├── {input_basename}_validation_results.json  # Complete results with metadata and rules
├── {input_basename}_validation_map.gpkg      # GeoPackage with file footprints for GIS
└── reports/                                  # Individual reports (if `--write-reports=True`)
    ├── file1_PASS.html  # File passed
    └── file2_FAIL.html  # File failed
```

---

## Creating Custom Rules

To take full advantage of the Validate Metadata tool with your products (whether purchased from a vendor or internally produced), it is recommended to create custom `*_rules.toml` files, starting with the `example_rules.toml` as a template. The custom rules file(s) can be stored in a local directory mapped by the `--rules-dir` flag or in the `gttk/resources/rules` directory with the examples file.

| Pattern | Description |
|---------|-------------|
| `example_rules.toml` | Reference file tracked in Git |
| `*_rules.toml` | Custom rules files (ignored by Git) |

Products must have unique names across all rules files in the `--rules-dir` directory. For example, if the file contains comprehensive 3DEP product rules, you will need to store it in a separate folder or delete that product from the `example_rules.toml` file.

### Step 1: Understand Your Data Product

Before writing rules, document:

1. **Required TIFF structure**: Bit depth, compression, tiling
2. **Coordinate reference requirements**: CRS EPSG codes, raster type
3. **Metadata requirements**: Required fields, formats, controlled vocabularies
4. **Quality constraints**: Valid value ranges, completeness requirements

### Step 2: Start with a Template

Copy and modify the example rules:

```bash
cp gttk/resources/rules/example_rules.toml gttk/resources/rules/my_product_rules.toml
```

### Step 3: Define Product Header

```toml
[MY-ORGANIZATION-PRODUCT-V1]
title = "My Organization Product Version 1"
description = "Validation rules for our standard GeoTIFF product"
author = "My Organization GIS Team"
updated = "2026-01-17"
```

### Step 4: Add Rules by Priority

Start with critical structural requirements:

```toml
# Critical: Data type validation
[[MY-ORGANIZATION-PRODUCT-V1.tag]]
tag = 258
description = "BitsPerSample"
data_type = "integer"
constraint = "exact"
expected = 32
comment = "Must be 32-bit for floating point elevation data"

[[MY-ORGANIZATION-PRODUCT-V1.tag]]
tag = 339
description = "SampleFormat"
data_type = "integer"
constraint = "exact"
expected = 3
comment = "3 = IEEE floating point"
```

Add spatial reference requirements:

```toml
[[MY-ORGANIZATION-PRODUCT-V1.geokey]]
geokey = 1024
description = "GTModelTypeGeoKey"
data_type = "integer"
constraint = "exact"
expected = 1
comment = "1 = Projected CRS required"

[[MY-ORGANIZATION-PRODUCT-V1.geokey]]
geokey = 3072
description = "ProjectedCRSGeoKey"
data_type = "integer"
constraint = "ranges"
expected = [
  { min = 32601, max = 32660 },
  { min = 32701, max = 32760 }
]
comment = "WGS 84 UTM zones only"
```

Add metadata requirements:

```toml
[[MY-ORGANIZATION-PRODUCT-V1.gdal]]
name = "AREA_OR_POINT"
description = "Raster Type"
data_type = "string"
constraint = "exact"
expected = "Point"
comment = "Elevation data must use PixelIsPoint"
```

### Step 5: Test Your Rules

```bash
# Test with a known-compliant file
# (rules file should be in gttk/resources/rules/ directory)
gttk validate -i compliant_file.tif -p MY-ORGANIZATION-PRODUCT-V1

# Test with a known-non-compliant file
gttk validate -i bad_file.tif -p MY-ORGANIZATION-PRODUCT-V1

# Use custom rules directory
gttk validate -i compliant_file.tif -r /path/to/custom/rules/ -p MY-ORGANIZATION-PRODUCT-V1
```

### Step 6: Document Optional vs Required

Use `optional = true` for recommended but not required fields:

```toml
[[MY-ORGANIZATION-PRODUCT-V1.tag]]
tag = 270
description = "ImageDescription"
data_type = "string"
constraint = "exists"
optional = true
comment = "Recommended: Include processing description"
```

---

## Troubleshooting

### Common Issues

**"Section X is not available"**
- The metadata section doesn't exist in the file
- For `geo`: File lacks GEO_METADATA tag (50909)
- For `xmp`: File lacks GDAL_METADATA tag (42112)
- For `xml`: No matching sidecar XML file found

**"XPath returns no results"**
- Check namespace prefixes match the XML schema
- Verify the XPath syntax is correct
- Test XPath expressions with an XML tool first

**"JSONPath returns no results"**
- Verify the PROJJSON structure exists
- Check path matches actual JSON structure
- Ensure array indices are valid (0-indexed)

**"Invalid constraint type"**
- Valid constraints: `exact`, `enum`, `regex`, `range`, `ranges`, `exists`, `forbidden`
- Check spelling and case sensitivity

**"Invalid data type"**
- Valid types: `string`, `integer`, `float`, `boolean`, `date`, `datetime`, `url`, `email`
- Check spelling and case sensitivity

### Debugging Tips

1. **View raw metadata first**:
   ```bash
   gttk read -i file.tif --reader-type producer
   ```

2. **Check specific sections**:
   ```bash
   gttk read -i file.tif --sections tag geokey gdal
   ```

3. **Test XPath with xmllint**:
   ```bash
   xmllint --xpath "//gmd:fileIdentifier" metadata.xml
   ```

4. **Verify PROJJSON structure**:
   ```bash
   gdalinfo -json file.tif | jq '.coordinateSystem'
   ```

### Getting Help

- **GitHub Issues**: Report bugs or request features
- **Example Rules**: See `gttk/resources/rules/example_rules.toml` for comprehensive examples
- **GTTK Documentation**: See main README for general usage
