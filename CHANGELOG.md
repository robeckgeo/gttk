# Change Log

All notable changes to this project will be documented in this file.

## [Unreleased]

## [0.12.0] - 2026-09-03

### Added

- **Optimize benchmarks** (`tests/benchmarks/benchmark_optimize.py`): measures the statistics
  passes a run makes, the pixels they read, and the cost of holding intermediates in memory
  versus on disk

### Changed

- **`VirtualFileManager` is now `Workspace`** (`gttk.utils.preprocessor`), with `plan_for()`,
  `estimated_workspace_bytes()` and `workspace_fits_in_memory()`

### Fixed

- **Intermediate workspace**: intermediates were built in GDAL's `/vsimem` regardless of size.
  `Workspace` now estimates them from the input and writes them beside the output when they
  exceed half the available memory; output is byte-identical either way
- **Duplicate statistics pass**: `preprocess_geotiff` computed band statistics whose metadata
  reached neither the COG nor the GeoTIFF output, duplicating the pass made for the `.aux.xml`.
  `gttk optimize` now reads the raster once for the statistics it writes

## [0.11.0] - 2026-09-02

### Security

- **Generated OSGeo4W scripts**: input, output, mask and XML paths were interpolated into
  script source with only backslashes escaped, so a `"` in a filename terminated the string
  literal and executed the remainder as Python. Paths now travel on `sys.argv` and all other
  values are rendered as Python literals by `gttk.utils.gdal_scripts.literal`
- **`open_file` under WSL**: the report path was interpolated into a double-quoted PowerShell
  command, where `$(...)` and backticks are evaluated. It is now a single-quoted literal
  passed as `-EncodedCommand`
- **XML parsing**: all nine parse sites now use `gttk.utils.xml_safety`, which disables entity
  resolution, DTD loading and network access. Metadata sidecars over 64 MiB are rejected
  rather than read into memory

### Added

- **`gttk.__version__`**, read lazily from the installed package metadata. Report footers, the
  `TIFFTAG_SOFTWARE` stamp, `gttk validate` JSON output and the ArcGIS toolbox label all read
  it from there
- **Continuous integration**: GitHub Actions runs the fast suite on every push and pull request
  and the full suite on `main`, retaining `coverage.xml` as a run artifact
- **`dev` extra**: `pip install -e ".[dev]"` installs `pytest` and `pytest-cov`
- **ArcGIS path test coverage on POSIX**: a fake OSGeo4W tree lets `gdal_runner` and the
  `optimize-arc` orchestration execute under test outside Windows
- **Packaging tests**: the wheel is built and installed into a clean virtual environment, the
  three dependency manifests are checked against the code's imports, and shipped resources are
  held to what the reports reference
- **Statistics accuracy tests**: the accumulator-versus-NumPy and blocked-versus-fast-path
  checks are collected by pytest instead of existing as standalone scripts
- **`.gitattributes`** pins LF line endings for Windows clones

### Changed

- **Docstring examples run as tests**: `--doctest-modules` is enabled and `gttk` is in
  `testpaths`; 52 stale examples across 17 files were corrected
- **README option tables are generated from `build_parser()`** and compared row by row. The
  tables gained the missing `--arc-mode` and `--optimize-script` rows and an `optimize-arc`
  table, and corrected the documented defaults for `--mask-alpha`, `--level` and
  `--show-defaults`
- **Documentation is pinned to the repository**: test counts, marker lists, backticked paths and
  dotted names in `CLAUDE.md`, `DEVELOPER.md`, `README.md` and `tests/README.md` are checked
  against the tree
- **External XML metadata lookup order is documented** in each tool's `--help` and in the README:
  `<stem>.xml`, then `<stem>_meta.xml` beside the raster, then the parent directory, then a
  sibling `metadatos/` directory
- **`gttk test` scratch location**: `--temp-dir` now defaults to `<input stem>_gttk_test/` beside
  the output workbook rather than `./temp`, and the ArcGIS temporary workspace uses the
  platform temporary directory instead of the working directory
- **Coverage is opt-in**: the `--cov` flags moved out of `pytest.ini` `addopts` into an explicit
  invocation, with settings in `pyproject.toml` `[tool.coverage]`
- **`generate_output_paths()`** distinguishes files from directories by suffix when the path does
  not exist, correcting the output folder name for library callers

### Removed

- **Unreferenced code**: `TiffTagParser.get_exif_tags()` and the Pillow dependency it required,
  two `render_statistics` methods, two unused exception classes, four `PerformanceTracker`
  methods, `ColorManager.get_index_color_map()`, `ResourceManager.get_icon_path()` and
  `_read_file()`
- **Unreferenced resources**: twenty icon files that no report can request
- **Eleven unread `config.toml` keys**: `[api]`, `[logging]`, four `[gui]` keys and
  `statistics.alpha_artifact_tolerance`, together with `Config.get_section()`
- **`init_arcpy()` and `gttk/utils/arcgis_proj_config.py`**: neither had a reachable effect
- **`gttk compare --config`**: declared but never read
- **`gttk/utils/xml_helpers.py`**: imported PyQt6, which is not a dependency

### Fixed

- **Import side effects**: importing GTTK no longer forces matplotlib's Agg backend, installs a
  root logger handler, or sets `PROJ_NETWORK` in the environment
- **Installed copies locate `config.toml`**: the loader reads `GTTK_CONFIG`, then a checkout's
  own file, then a packaged default. `gttk test` and `gttk optimize-arc` previously raised
  `FileNotFoundError` at dispatch from a wheel, and other commands printed a warning to stdout
- **`gttk validate` runs from any directory**: `--rules-dir` defaults to the packaged rules
  rather than a repository-relative path
- **`psutil` is a declared dependency**; package data now ships `resources/**/*`, and
  `MANIFEST.in` no longer prunes directories that do not exist
- **Compression efficiency reports unknown values as unknown**: `calculate_compression_efficiency`
  returned `0.0` on failure, which is indistinguishable from an uncompressed file. It returns
  `None` and renders as "n/a"; `get_uncompressed_size` and the per-IFD header estimate follow
- **Alpha band statistics**: the in-memory path masked the alpha band with itself, reporting a
  minimum and mean of 255 with zero standard deviation. Both paths now include the band's own
  pixels; colour bands still exclude transparent pixels
- **Extractor failures are reported rather than rendered as clean results**: COG validation
  errors, unreadable IFD fields, unparsable TIFF tags, a missing tag lookup file, and files a
  batch skips are all surfaced instead of appearing as absent values
- **Fallback failures are reported**: the OSGeo4W projection script lists the failures it
  previously swallowed, an unreadable per-band NoData string is logged rather than used, the
  rules loader names invalid TOML files it skips, and `gttk validate` distinguishes an
  incomparable value from a mismatch
- **Resource cleanup on failure paths**: `MetadataExtractor`, the baseline efficiency
  calculation and `gttk compare` release datasets and scratch directories in `finally` blocks
- **`gttk optimize` refuses to write onto its input**, whether a file or a directory
- **`prepare_output_path` refuses paths outside the input directory**
- **The single-band product check fails loudly**: it re-raises by exception type instead of
  matching on message text, logs inputs it cannot open, and releases the dataset
- **`gttk validate` matches `.TIF` on Linux**: three directory scans used case-sensitive globs
- **Concurrent `gttk test` runs** use per-run scratch directories instead of overwriting each
  other's candidate rasters
- **Library defaults match the CLI**: `TestArguments.delete_test_files`, and `ReadArguments`
  `reader_type`, `xml_type` and `tag_scope`, previously differed from the command line
- **Help text corrections**: `--log-file`, `--delete-test-files`, `--nodata` and `--decimals`
  described behaviour the code does not implement; `validate`'s `--sections`, `--name-filter`
  and `--output-dir` now state their defaults
- **ArcGIS toolbox PROJ configuration**: `PROJ_DATA` and `PROJ_LIB` are both checked and set,
  `GTTK_CONFIG` is honoured, and the `tomli` fallback for unsupported Python versions is gone
- **`optimize-arc` OSGeo4W discovery**: the Python directory is located by pattern rather than
  hard-coded to `apps/Python312`, and `PATH` uses the platform separator
- **WSL path conversion without `wslpath`**: `/mnt/<drive>/` paths map to the drive letter, and
  the UNC fallback uses `WSL_DISTRO_NAME` instead of assuming Ubuntu
- **The `.aux.xml` sidecar is written as bytes**, avoiding CRLF translation on Windows; every
  text read and write in the package names its encoding
- **Rule files are read in name order**, making product resolution and skip reporting
  deterministic across filesystems
- **PAM and validation-summary section icons** are present under the names the section registry
  requests
- **Library code logs instead of printing**: the resource manager wrote failure messages to
  stdout
- **GeoPackage replacement failures** are reported by name rather than raised, and a projection
  request to OSGeo4W that exceeds its timeout terminates the child process
- **`pytest.ini`** no longer carries `[coverage:*]` sections that coverage.py does not read, and
  the resource build scripts call `logging.basicConfig()` in `main()` rather than at import

## [0.10.0] - 2026-09-01

### Added

- **Spanish ArcGIS Pro toolbox**: labels, choices, validation messages, run messages and the
  parameter help panel are localised. Language resolution is `GTTK_LANG`, then `config.toml`
  `[gui] language`, then Pro's display language, then the Windows display language. Strings live
  in a TOML catalog (`gttk/resources/i18n/es.toml`) and help sidecars under `toolbox/i18n/`.
  Dialog choices are codes behind translated labels, so runs saved to History remain portable
  across languages. Spanish guides: `README.es.md`, `toolbox/README.es.md`
- **Resolved-settings logging**: every run logs each setting and its source — profile value,
  codec default, inherited flag, explicit argument, or a clamp forced by the data type
- **`gttk optimize --show-defaults [TYPE]`**: prints the settings that would be used for a
  product type and their sources, then exits. Requires no input file
- **Lossless LERC for `thematic` products**: a non-zero `--max-z-error` is rejected rather than
  clamped, since quantisation merges adjacent class codes. LERC remains unavailable for `image`
- **`--overview-resampling`, `--overview-compress`, `--overview-predictor`** for explicit
  overview control; interpolating kernels are rejected for `thematic` products
- **`--num-threads`** to cap compression threads per file
- **`--report`** to skip report generation on batch runs; directory input no longer auto-opens
  reports

### Changed

- **`--help` no longer prints `(default: None)` for resolved options**: help text that states a
  default is generated from the resolver, conditional defaults are summarised in a table at the
  end of `gttk optimize --help`, and the suffix is suppressed for required and deferred
  arguments. Applies to all subcommands
- **`optimize`'s options are grouped** into `required`, `compression`, `overviews`, `masking and
  nodata`, `georeferencing and metadata`, `output file` and `report`; boolean options render as
  `--cog BOOL`
- **The ArcGIS toolbox reads the shared resolver** instead of duplicating per-product-type
  defaults, and exposes `--overview-resampling`, `--overview-compress`, `--overview-predictor`,
  `--num-threads` and `--report`. `write_pam_xml` now matches the CLI default
- **GDAL is no longer a declared pip dependency** and is available as the `gdal` extra. Importing
  GTTK without GDAL raises an `ImportError` naming the conda-forge command that installs it
- **Bundled example reports regenerated** with NAVD88 height (EPSG:5703); the compound CRS is now
  carried by the GeoKeys without a `COMPOUND_CRS_WKT2` fallback

### Removed

- **Unsupported vertical datums** and the custom-WKT registry that served them. Supply a vertical
  CRS as an EPSG code or a WKT string; a WKT vertical CRS still builds a compound CRS, with its
  full WKT2 stored in the `COMPOUND_CRS_WKT2` metadata item

### Fixed

- **`gdal_runner` stdout protocol**: log records written beneath the text layer could interleave
  with JSON payloads over 8 KiB, so `Optimize Compression` reported "No output captured from
  gdalinfo" and `Read Metadata` lost OSGeo4W projection info. The handler now flushes the text
  layer before writing and each protocol line is committed as it is printed
- **`optimize-arc` raised `NameError: name 'gdal_env' is not defined`** from the ArcGIS toolbox:
  the entry point applied the context manager without importing it. Its log records now reach the
  geoprocessing pane
- **Import side effects**: GDAL configuration options, GDAL's exception mode and root logger
  handlers were set at import. They now apply for the duration of an operation through
  `gttk.utils.gdal_env.gdal_env()` and are restored afterwards
- **Module loggers** are namespaced under `gttk.*`, and `setup_logger` configures the `gttk`
  logger rather than root
- **Compound CRS lost its vertical EPSG code**: the SRS is re-asserted on the final write
  (`-a_srs`), so a vertical component keeps its own code instead of being identified only by its
  datum
- **Categorical overviews were interpolated**: the COG path did not emit `OVERVIEW_RESAMPLING`,
  so the driver's `CUBIC` default blended class codes. The kernel is now stated explicitly and
  derived from `--product-type`
- **Overviews used a different codec from the main image**: the COG driver defaults
  `OVERVIEW_COMPRESS` to LZW. Overviews now inherit `--algorithm` and `--predictor`
- **`PREDICTOR=NONE` was emitted for thematic products**, which GDAL does not accept. The default
  is 1, and `PREDICTOR` is omitted when it is 1
- **`PREDICTOR=3` was emitted for integer `scientific` products**: the floating-point predictor
  is invalid on integer samples and now falls back to 2 with a warning
- **The ArcGIS path did not clamp the floating-point predictor**, unlike the CLI path
- **`LERC_DEFLATE` and `LERC_ZSTD` resolved no compression level**, silently taking GDAL's
  default
- **`--mask-alpha` defaulted to `True` in argparse while the dataclass declared `None`**, so the
  resolver's own branch never ran from the CLI. The resolved result is unchanged
- **Flag-combination validation was skipped when no input file was set**, so five rules did not
  apply to the ArcGIS toolbox or to library callers
- **`compare` had no `--report-format`**: it declared `--report_format`. The hyphenated form is
  primary and the underscore remains as an alias
- **A read handle leaked on failure paths** in `_orchestrate_geotiff_optimization`, blocking
  deletion of the input on Windows
- **A stray root `__init__.py`** made the repository directory importable as `gttk`, shadowing
  the real package
- **`gttk optimize` and `gttk read` could hang at the histogram step** where a display is
  advertised: the generator now selects the Agg backend before pyplot loads
- **`AREA_OR_POINT` was written in the wrong case** and derived by duplicated inline expressions;
  it is normalised on resolution and computed by `default_raster_type_for()`
- **`EPSG:5730` was labelled EVRF2020**, which does not exist; it is EVRF2000 height
- **`AHD`, `NZVD2016` and `JGD2000` were untypeable** as vertical-datum abbreviations: their keys
  carried a stray closing parenthesis
- **The Optimize help side panel documented 23 of 28 parameters** and described the raster-type
  default incorrectly
- **Toolbox dialog corrections**: a missing space in the "Compression Report Format" label, a
  case mismatch in the Read Metadata value list, and a shared product-type list for Optimize and
  Test Compression
- **Documentation corrections**: two help strings with missing spaces, vertical-SRS examples using
  `-v` instead of `-s`, a README example presenting `-a LERC` alone as lossless, and a
  `gdal.Warp` reprojection step in `DEVELOPER.md` that does not exist

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
