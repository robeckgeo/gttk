# Change Log

All notable changes to this project will be documented in this file.

## [0.9.0] - 2026-01-19

### Added

- **Validate Metadata tool** (`gttk validate`): New command-line tool for validating GeoTIFF files against product-specific requirements defined in TOML rule files
- **Validation engine**: Comprehensive validation system supporting 7 section types (tag, geokey, gdal, geo, xmp, xml, projjson) and 7 constraint types (exact, enum, regex, range, ranges, exists, forbidden)
- **On-demand statistics validation**: STATISTICS_* keys computed directly from raster data, working even without GDAL_METADATA tag
- **Color interpretation validation**: COLORINTERP keys queried via GDAL for all bands or specific bands using `name:sample` syntax
- **Batch validation**: Directory processing with name substring filtering and JSON/GeoPackage output
- **ArcGIS Validate Metadata tool**: GUI interface in the Python Toolbox with dynamic product selection and multi-select section filtering
- **Extended data types**: Added support for date, datetime, url, and email validation with format checking
- **XPath and JSONPath support**: Full XPath 1.0 for XML sections and JSONPath for PROJJSON validation
- **Table of Contents**: Added comprehensive navigation to README.md and validation/README.md

### Changed

- Updated documentation to reflect 5 tools (added Validate Metadata alongside existing Compare, Optimize, Test, Read)
- Corrected CLI argument names in documentation: `--rules-dir`, `--output-dir`, `--name-filter` (previously documented as `--rules`, `--output`, `--name-filter`)
- Enhanced GDAL Metadata documentation with clear band suffix syntax and examples
- Reorganized validation output structure to use folders with JSON summary, GeoPackage map, and optional individual reports

### Documentation

- Added "Available Toolbox Tools" section documenting all 5 ArcGIS tools
- Added detailed Validate Metadata tool parameter documentation
- Added comprehensive GDAL Metadata validation examples with band-specific and all-bands syntax
- Updated all example commands to use correct argument names

## [0.8.2] - 2026-01-11

### Added

- Large GeoTIFF block-based statistics processing for arbitrarily large files. See [plans/statistics_optimization_plan.md](plans/statistics_optimization_plan.md).
- Expanded the test structure to cover more critical utilies and benchmarks, expanding the test suite from 386 to 638 tests. See [plans/testing_expansion_plan.md](plans/testing_expansion_plan.md).

### Performance

- Sped up blocked statistics calculation >40x by replacing Python loops with vectorized NumPy using Chan's parallel variance algorithm, and reducing the number of passes from 3 to 2 using intelligent alpha band and transparency mask detection.

### Changed

- The monolithic `statistics_calculator.py` and `histogram_generator.py` scripts were restructured into the `gttk.utils.statistics` package with 6 focused modules.

### Fixed

- PAM histogram generation caused a critical memory issue by storing full pixel arrays instead of lightweight histogram metadata (dict).

## [0.8.1] - 2025-12-27

### Fixed

- Read Metadata tool excluded sections for GeoTIFFs with modern EPSG codes (Issue [#1]).
- Improved compression efficiency calculation accuracy and added dev-only `generate_baseline` option (Issue [#4]).

### Added

- Updated algorithm to extend rounding to overviews, improving 1 cm DEM compression by an additional 3-6% (Issue [#2]).
- Created new icon for Compression Comparison HTML reports.
- Inserted new Tiling and Overviews section in the Compression Comparison report.
- Simplified `--reader-type=analyst` reports to exclude `STATISTICS_*` GDAL_METADATA items (repeated in Statistics table).

## [0.8.0] - 2025-12-16

### Added

- Initial public beta release.
- Core tools: `compare`, `optimize`, `test`, `read`.
- ArcGIS Python toolbox.

[#1]: https://github.com/robeckgeo/gttk/issues/1
[#2]: https://github.com/robeckgeo/gttk/issues/2
[#4]: https://github.com/robeckgeo/gttk/issues/4
