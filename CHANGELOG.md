# Change Log

All notable changes to this project will be documented in this file.

## [Unreleased]

### Fixed

- **Importing GTTK changed the host process.** GDAL configuration, GDAL's Python
  exception mode and the *root* logger were all set at import time, so an application
  that imported a single GTTK function silently had its GeoTIFF reading, its error
  handling and its logging changed underneath it. Specifically: `OSR_WKT_FORMAT=WKT2_2019`
  reformatted every `ExportToWkt` in the process; `GTIFF_SRS_SOURCE=WKT` (from the ArcGIS
  module) changed how every GeoTIFF was *read*; `gdal.UseExceptions()` changed how every
  GDAL call reported failure; `setup_logger` cleared the root logger's handlers, disabling
  the application's own logging; and importing `gdal_runner` additionally created a
  `logs/` directory and wrote to it. All of it now applies for the duration of a GTTK
  operation and is restored afterwards, via the new `gttk.utils.gdal_env.gdal_env()`
  context manager applied at each tool's public entry point. Importing GTTK is now free
  of side effects, asserted in subprocesses by `tests/unit/test_import_side_effects.py`.
- **Module loggers sat outside any namespace.** `optimize_compression`, `read_metadata`,
  `compare_compression`, `test_compression` and `optimize_compression_arc` logged under
  bare top-level names that collide with any other library using them and cannot be
  configured as a group. Everything now logs under `gttk.*`, and `setup_logger`
  configures the `gttk` logger rather than root, so an application that never calls it
  still receives GTTK's messages by normal propagation.

- **Compound CRS lost its vertical EPSG code.** The resolved SRS was written onto the in-memory
  intermediate and left to reach the output through GeoTIFF keys, which carry a compound CRS only
  partially: the vertical component came back identified by its datum (`VerticalDatumGeoKey`) and
  lost its own code, so an EGM2008 DEM named EGM2008 without ever citing `EPSG:3855`. The target SRS
  is now re-asserted on the final write (`-a_srs`, an assignment -- pixels and the geotransform are
  untouched). Verified on a real TREx cell: the output now reports compound `EPSG:9518` and vertical
  `EPSG:3855`, where before both were absent.
- **Categorical overviews were interpolated.** On the COG path GTTK never emitted
  `OVERVIEW_RESAMPLING`, so the driver fell back to its own default (`CUBIC` for any band without a
  colour table) and blended class codes together in the pyramids of `thematic` products. Measured on
  a real 6-class provenance mask, the overviews contained five codes that were not in the source.
  The kernel is now stated explicitly and comes from `--product-type`.
- **Overviews used a different codec from the main image.** The COG driver defaults
  `OVERVIEW_COMPRESS` to LZW regardless of `COMPRESS`, so a ZSTD COG carried LZW pyramids.
  Overviews now inherit `--algorithm` and `--predictor`.
- **`AREA_OR_POINT` was written in the wrong case.** `--raster-type` is lowercased by the CLI and
  was written verbatim, stamping `point` instead of GDAL's `Point`. Normalised on resolution.
- **`PREDICTOR=NONE` was emitted for thematic products.** `NONE` is not a value GDAL accepts. The
  default is now 1, and `PREDICTOR` is omitted entirely when it is 1: that is already both drivers'
  default, and they spell it differently -- the COG driver's value list is
  `NO/YES/STANDARD/FLOATING_POINT` and it warns on `1`, while GTiff takes an int and errors on `NO`.
- **`PREDICTOR=3` was emitted for integer `scientific` products.** The floating-point predictor is
  invalid on integer samples; it now falls back to `2` with a warning when the source is not float.
- **A failure leaked a read handle on the input file.** `_orchestrate_geotiff_optimization` released
  its datasets only on the success path, so an exception left the source open — which on Windows
  blocks deleting or overwriting it. Release now happens in a `finally`.
- Documentation: the vertical-SRS examples used `-v`, which is `--verbose` (the flag is `-s`), and
  DEVELOPER.md described a `gdal.Warp` reprojection step that does not exist — GTTK is assign-only.

### Added

- `--overview-resampling`, `--overview-compress`, `--overview-predictor` for explicit overview
  control. An interpolating kernel on a `thematic` product is rejected.
- `--num-threads` to cap compression threads per file, for running several `gttk` processes at once.
- `--report` to skip report generation on batch runs. Directory input no longer auto-opens reports.

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
