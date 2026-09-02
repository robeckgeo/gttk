# Change Log

All notable changes to this project will be documented in this file.

## [Unreleased]

### Changed

- **Coverage is opt-in.** The `--cov` flags sat in `pytest.ini`'s `addopts`, so every
  invocation -- one test file, `pytest --collect-only`, a subprocess run of a single module --
  rewrote `.coverage`, `coverage.xml` and `htmlcov/`, and the table on disk described whatever
  had run last rather than the suite. That is how a wrong claim about an `omit` pattern hiding
  a 1,400-line module survived two reports. `pytest --cov=gttk --cov-report=html` produces the
  same report on request, with the settings in `pyproject.toml` `[tool.coverage]` where
  coverage.py reads them, and `tests/unit/test_pytest_config.py` keeps the flags out of
  `addopts`.

- **Every `Example:` block in a docstring now runs as part of the test suite.** They were
  all written in doctest form, but `--doctest-modules` had never been passed, so none of
  them had ever been executed -- which is how v0.10.0 came to ship seven docstrings
  describing a `report_context` module and an `HtmlReportGenerator` class that had not
  existed for several releases. Turning the flag on surfaced 52 broken examples across 17
  files: dataclass calls missing required fields, methods documented as free functions,
  loop bodies written with `>>>` instead of `...`, expected output that was a comment,
  and truncated strings that had never been compared against the real message. All are
  fixed, and `gttk` now sits in `testpaths` so the flag cannot be quietly dropped.

  An example that needs a raster opens one by name -- `MetadataExtractor('example.tif')`
  -- because the root `conftest.py` builds a set of deterministic `MockGeoTIFF` files once
  per session and runs each example in its own copy of them. Examples stay readable as
  documentation, writes cannot leak between them, and nothing lands in the working tree.
  The house rules are in CLAUDE.md; the two worked examples in `DEVELOPER.md` are
  extracted from the markdown and executed by `tests/unit/test_developer_guide.py`.

- **`gttk validate` now names its output folder correctly for a file that does not exist
  yet.** `generate_output_paths()` decided between a file and a directory with
  `is_file()`, so a caller asking where results *would* go for `/data/tile.tif` got
  `tile.tif_validation/tile.tif_validation_results.json`. It now falls back to the path's
  suffix when the path is not on disk. The CLI never reached this -- it rejects a missing
  input first -- so no run changes; a library caller's would. The function had no unit
  tests at all; it has `tests/unit/test_validation_output.py` now.

### Removed

- `gttk/utils/xml_helpers.py`, a leftover from a Qt GUI this repository does not contain.
  It imported PyQt6 at module scope, which was declared in neither `pyproject.toml`,
  `environment.yml` nor `requirements.txt` and installed nowhere, so the module could not
  be imported at all -- it had no references, no tests, and 0% coverage. Its sibling
  `xml_formatter.py` is unaffected and still used.

### Fixed

- **`gttk validate` now works from any directory.** Its default `--rules-dir` was the
  repo-relative `gttk/resources/rules`, so the command worked from a checkout's root and
  nowhere else: an installed copy run from a data directory failed with "Rules directory
  not found" unless `--rules-dir` was passed. The default is now `bundled_rules_dir()`,
  which locates the rule files inside the package wherever it was imported from. The
  ArcGIS toolbox's Rules Directory parameter and its fallback used the same relative
  path and use the same function now. `--help` says "the rules bundled with GTTK" rather
  than printing an absolute path into site-packages.

- `pytest.ini` carried `[coverage:run]`, `[coverage:report]` and `[coverage:html]` sections
  that coverage.py has never read -- it looks in `.coveragerc`, `setup.cfg`, `tox.ini` and
  `pyproject.toml`, not `pytest.ini` -- so `precision = 2` never showed and the `omit`
  patterns never omitted anything. Removed, with a note where the real settings live: the
  `--cov*` flags in `addopts`. Reports are unchanged, because nothing in that block was ever
  in effect. `gttk/resources/tiff/` also gained the `__init__.py` its sibling `esri/`
  already had, so pytest imports its build script under its package name.

- The two lookup-table build scripts under `gttk/resources/` called
  `logging.basicConfig()` at module scope, claiming the root logger of any process that
  imported them -- which `--doctest-modules gttk/` now does. Moved into `main()`, where a
  script's own logging belongs.

  The existing import-side-effect guard could not have caught this: it installs a root
  handler before importing, and `basicConfig()` is a no-op once root has one. It now also
  checks the case that matters -- an application that has not configured logging yet, and
  so starts with no root handler at all -- and both scripts were added to the list of
  modules it imports.

## [0.10.0] - 2026-09-01

### Added

- **The ArcGIS Pro toolbox now speaks Spanish.** When Pro loads it, the toolbox picks
  its language -- `GTTK_LANG`, then `config.toml` `[gui] language`, then the display
  language chosen in Pro's Options, then the Windows display language -- and shows its
  labels, choices, validation messages, run messages and the parameter help panel in that
  language. Strings live in a reviewable TOML catalog keyed by the English text
  (`gttk/resources/i18n/es.toml`); the help sidecars live per language under
  `toolbox/i18n/` and are copied beside the toolbox on load. Dialog choices are now codes
  behind translated labels, so a run saved to History under one language still runs under
  another. A Spanish guide (`README.es.md`) and setup guide (`toolbox/README.es.md`)
  accompany it, and tests pin the catalog and every sidecar to the dialog.

- **Every run now logs the settings it resolved, and where each one came from** --
  a profile value, a codec default, an inherited flag, a caller's explicit choice, or a
  clamp forced by the raster's data type. It replaces a single-line dump of the
  dataclass `repr`, and is logged *after* the integer-data predictor clamp rather than
  before it, so it can no longer report a predictor the run does not use. The
  comparison report is deliberately untouched: it characterises the two files
  independently of what was asked for, which is what makes it a check rather than an
  echo.

- **`gttk optimize --show-defaults [TYPE]`** prints every setting that would be used for
  a product type, and where each one came from -- a profile value, a codec default, an
  inherited flag, or unused by the selected codec -- then exits. It needs no input file.

- **Lossless LERC for `thematic` products.** Esri writes lossless LERC widely, so
  refusing it outright was a needless incompatibility; class codes with a small local
  range are also what LERC's per-block bit-packing is best at. A non-zero
  `--max-z-error` is rejected rather than clamped: quantising neighbouring values
  together merges adjacent class codes, the same failure mode as an interpolating
  overview kernel. LERC remains unavailable for `image`, where its bit-packing buys
  little on 8-bit RGB and its lossy mode is beaten by JPEG/JXL at every quality. The
  `thematic` benchmark preset already carried a `LERC` row at `max_z_error=0`; until now
  that row could never run.

- `--overview-resampling`, `--overview-compress`, `--overview-predictor` for explicit overview
  control. An interpolating kernel on a `thematic` product is rejected.
- `--num-threads` to cap compression threads per file, for running several `gttk` processes at once.
- `--report` to skip report generation on batch runs. Directory input no longer auto-opens reports.

### Changed

- **`gttk --help` no longer claims `(default: None)` for options that do have a
  default.** Fourteen `optimize` options are resolved later from `--product-type` and the
  selected codec, and argparse's stock `ArgumentDefaultsHelpFormatter` printed `None` for
  every one of them -- while eleven help strings hand-wrote a `Default: ...` sentence that
  argparse then contradicted on the same line (`--mask-nodata` said both
  "True for images, False for all others" and "(default: None)"). Help text that states a
  default is now generated by calling the resolver, so it cannot drift; the conditional
  defaults are summarised in a table at the end of `gttk optimize --help`; and the
  formatter suppresses the suffix for required arguments and deferred values while
  keeping it for genuine static defaults. Applies to all five subcommands.

- **`optimize`'s 28 options are grouped** into `required`, `compression`, `overviews`,
  `masking and nodata`, `georeferencing and metadata`, `output file` and `report`, and
  the boolean options render as `--cog BOOL` rather than `--cog COG`. The usage block now
  fits an 80-column terminal.

- **The ArcGIS toolbox reads the same resolver** instead of keeping a second copy of the
  per-product-type branching, and exposes the five options it had fallen behind on:
  `--overview-resampling`, `--overview-compress`, `--overview-predictor`, `--num-threads`
  and `--report`. `Optimize`'s `write_pam_xml` default now matches the CLI's `True`.

- **GDAL is no longer a declared pip dependency**, and is available as the `gdal` extra
  instead. The PyPI `gdal` package is a source distribution of the Python bindings that
  compiles against a GDAL C++ library pip cannot install, so listing it meant a
  forgotten `conda activate` produced a multi-minute build ending in
  `fatal error C1083: Cannot open include file: 'gdal.h'` rather than an immediate,
  legible failure. Importing GTTK without GDAL now raises an `ImportError` naming that
  exact error and the conda-forge command that fixes it. Use `pip install ".[gdal]"`
  only where the GDAL library and its headers are already present.

- **The INEGI example reports were regenerated with NAVD88 height (EPSG:5703)**, the
  vertical datum INEGI's Norma Técnica defines for Mexico, in place of the invented GGM10
  vertical CRS they used to show. The NEW report now carries a compound CRS that the
  GeoKeys hold on their own (`ProjectedCRSGeoKey` 6368, `VerticalGeoKey` 5703) and no
  `COMPOUND_CRS_WKT2` fallback; the README's description of the example changes with it.

### Removed

- **The "Geoide Gravimétrico Mexicano 2010 (GGM10)" vertical datum.** A geoid model is
  the *transformation* between ellipsoidal heights (h) and orthometric heights (H); it is
  not a datum, and offering it as one was the wrong tool. GTTK shipped GGM10 as a
  hand-written vertical CRS with no EPSG code, and that cost twice over: the name did
  not survive the GeoTIFF GeoKeys (`VerticalDatumGeoKey` 32767, `VDATUM["unknown"]`),
  and no software can transform *from* an invented datum -- PROJ falls back to a
  "ballpark" `+proj=noop`, a silent zero. Mexico's vertical datum is NAVD88 (INEGI,
  Norma Técnica para el Sistema Geodésico Nacional, DOF 23-Dec-2010, art. 15), and both
  Esri (WKID 110232, `Mexico_ITRF2008_To_NAVD88_Height_GGM10`) and PROJ
  (`PROJ:EPSG_6364_TO_EPSG_5703`, via the grid `mx_inegi_ggm10.tif`) already model GGM10
  as the transformation onto it. Choose `NAVD88` / `EPSG:5703` instead; the ArcGIS
  dropdown loses the entry with it, and the custom-WKT registry that existed only to
  serve it is gone. What remains is the generic path: a vertical CRS supplied as a WKT
  string still builds a compound CRS, and because the GeoKeys cannot carry a datum
  without an EPSG code, its full WKT2 is still stored in the `COMPOUND_CRS_WKT2`
  metadata item and read back from there.

### Fixed

- **`Optimize Compression` in ArcGIS Pro failed with "No output captured from gdalinfo"
  on any real file, and `Read Metadata` silently lost the OSGeo4W projection info.**
  `gdal_runner.py` hands its results to the parent as JSON lines on stdout, and its own
  log records go down the same pipe -- but the log handler writes bytes beneath the text
  layer while the JSON goes through it. A payload over 8 KiB (every `gdalinfo -json` of
  a DEM) left its newline pending, the next record landed between the JSON and that
  newline, and the parent found no line it could parse. The handler now flushes the text
  layer before writing, and the runner commits each protocol line as it prints it.
  Broken since the cp1252 console fix of 2026-04-19 and unnoticed because the test
  suite cannot reach the ArcGIS path; a test now drives the runner through a pipe-like
  stdout with an oversized payload.
- **`Optimize Compression` from the ArcGIS toolbox failed on every run** with
  `NameError: name 'gdal_env' is not defined`: the entry point applied
  `gdal_env(GDAL_OPTIONS_ARC)` without importing either name. Its log lines -- the
  resolved-settings block included -- also had no handler when called from the toolbox,
  so they never reached the geoprocessing pane; they do now, for the duration of the call.
- **The Optimize help side panel documented 23 of the dialog's 28 parameters** and
  described the raster-type default backwards. It now covers every parameter, and a test
  keeps each language's sidecar in step with the dialog.
- The toolbox's "CompressionReport Format" label gets its missing space; Read Metadata no
  longer pre-fills `Text`/`Table` into a lowercase value list; Optimize and Test
  Compression share one product-type list (`Error Model`, with the old
  `Generic Point-cloud Model` still accepted).

- **`gttk optimize` and `gttk read` could hang at the histogram step wherever a display
  is advertised.** The histogram generator imported pyplot without choosing a backend, so
  matplotlib took a GUI one (QtAgg under WSLg, which sets `DISPLAY` for every shell) and
  then blocked on the compositor socket; a headless run sat at 1% CPU until its timeout.
  The module now selects the Agg backend before pyplot loads -- the histogram is a PNG for
  the report, never a window -- and a test imports it with a display advertised and checks
  the backend it got.
- **The vertical-datum list offered "European Vertical Reference Frame 2020 (EVRF2020)"
  for `EPSG:5730`, which is EVRF2000 height** -- no EVRF2020 exists. The entry and its
  `EVRF2020` abbreviation now say EVRF2000, and a test pins every name in both maps to
  the name PROJ returns for its code, so a label can no longer drift from what it writes.

- **Flag-combination checks were skipped whenever no input file was set.** The rules
  rejecting LERC on imagery, JPEG/JXL on non-imagery, `discard_lsb` on the wrong codec,
  a `dem` without `--vertical-srs`, and a masked `thematic` all sat behind an
  `if self.input_path` guard in `OptimizeArguments._validate_optimize`. None of them
  needs to open a raster, and both the ArcGIS toolbox and any library caller build the
  dataclass directly -- so all five silently passed on those paths. Only the band-count
  probe, which genuinely does need the file, remains behind the guard.

- **`compare` had no `--report-format` flag.** It declared `--report_format` with an
  underscore while every other subcommand and the README use the hyphen, so the
  documented spelling did not exist. The hyphenated form is now primary and the
  underscore remains as an alias.

- **The README showed `-a LERC` alone as "lossless".** Selecting LERC without
  `--max-z-error` resolves to the product type's default tolerance -- `0.01` for `dem` --
  so that example produced near-lossless output, contradicting the hydro-conditioned DEM
  guidance further down the same file that tells you to pass `--max-z-error=0`.

- **`AREA_OR_POINT` was derived by the same inline expression in three places**
  (`preprocessor.py` and twice in `optimize_compression_arc.py`). It is now
  `default_raster_type_for()` in `optimize_constants.py`, and `_resolve_defaults`
  populates `raster_type` so `--show-defaults` can report it.

- **Two help strings had missing spaces** (`internal mask(e.g. RGB+mask)` and
  `syntax-highlightedtext`).

- **The ArcGIS path never clamped the floating-point predictor.** PREDICTOR=3 is the
  TIFF floating-point predictor and libtiff rejects it on integer samples; the CLI
  path has always clamped it once the source data type is known, but
  `optimize_compression_arc` did not, so a `scientific` integer raster driven from the
  toolbox resolved PREDICTOR=3 and handed GDAL an option it cannot honour. It now
  clamps through the same helper, and both orchestrators log their resolved settings.

- **`LERC_DEFLATE` and `LERC_ZSTD` resolved no compression level.** `_resolve_defaults`
  matched only the bare `DEFLATE`/`ZSTD` names, so `args.level` stayed `None` and the
  `if args.level:` guard downstream emitted no `LEVEL=` at all -- silently taking GDAL's
  default where `-a ZSTD` would have used GTTK's 9. Latent, since these are
  benchmark-only and the presets that use them supply a level explicitly.

- **`--mask-alpha` defaulted to `True` in argparse while the dataclass declared `None`**,
  so `_resolve_defaults`' own `mask_alpha` branch never ran from the CLI and every run
  looked as though the caller had asked for the value. The resolved result is unchanged.

- **A stray empty `__init__.py` at the repository root** made the repo directory
  importable as a package named `gttk`, shadowing the real `gttk/` package whenever the
  repo's parent directory reached `sys.path` -- which pytest does, because that file is
  what makes the root look like a package. Present since the initial commit; removed.

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
- **`AHD`, `NZVD2016` and `JGD2000` could not be typed as vertical-datum abbreviations.**
  Their keys in the abbreviation map carried a stray closing parenthesis (`"AHD)"`), which
  no upper-cased input could ever match, so the three were reachable only by their full
  dropdown name or by EPSG code. A test now checks that every key is typeable and that
  every value is an EPSG code the PROJ database resolves.
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
