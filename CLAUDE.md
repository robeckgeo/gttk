# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

GeoTIFF ToolKit (GTTK) is a Python toolkit for analyzing, optimizing, and compressing GeoTIFF files. It provides five CLI tools (`compare`, `optimize`, `test`, `read`, `validate`) and an ArcGIS Pro Python Toolbox.

## Build and Development Commands

```bash
# Environment setup
conda env create -f environment.yml
conda activate gttk
pip install -e ".[dev]"  # Development install, with the test tools

# Run all tests
pytest

# Run fast tests only (skip slow E2E)
pytest -m "not slow"

# Run specific test categories
pytest -m unit
pytest -m integration
pytest -m e2e

# Run specific test file/class/method
pytest tests/unit/test_data_models.py
pytest tests/unit/test_data_models.py::TestTiffTag
pytest tests/unit/test_data_models.py::TestTiffTag::test_instantiation

# Run tests matching pattern
pytest -k "statistics"

# Coverage report (opt-in: a plain `pytest` writes no coverage files)
pytest --cov=gttk --cov-report=html
```

## Architecture

### CLI Entry Point
- `gttk/main.py` - Parses CLI arguments and dispatches to tools
- Entry point: `gttk = "gttk.main:main"` (pyproject.toml)

### Five Core Tools
1. **Compare** (`gttk compare`) - `gttk/tools/compare_compression.py` - Validates compression by comparing files
2. **Optimize** (`gttk optimize`) - `gttk/tools/optimize_compression.py` - Creates Cloud-Optimized GeoTIFFs with intelligent defaults
3. **Test** (`gttk test`) - `gttk/tools/test_compression.py` - Benchmarks compression settings
4. **Read** (`gttk read`) - `gttk/tools/read_metadata.py` - Extracts and reports metadata
5. **Validate** (`gttk validate`) - `gttk/tools/validate_metadata.py` - Validates GeoTIFF metadata against TOML rule files

### Report Generation (Builder Pattern)
The toolkit separates report content from formatting:

1. **Data Models** (`gttk/utils/data_models.py`) - Strongly-typed dataclasses (`FileComparison`, `IfdTableData`, `StatisticsData`, etc.)
2. **Metadata Extractor** (`gttk/utils/metadata_extractor.py`) - Extract data from GeoTIFF files, return dataclass instances
3. **Report Builders** (`gttk/utils/report_builders.py`) - Determine WHAT sections to include (`MetadataReportBuilder`, `ComparisonReportBuilder`)
4. **Section Renderers** (`gttk/utils/section_renderers.py`) - Render individual sections to markdown
5. **Report Formatters** (`gttk/utils/report_formatters.py`) - Format complete reports (HTML or Markdown)

### Statistics Package
Located in `gttk/utils/statistics/`:
- **Dual-path strategy**: Fast (in-memory) vs blocked (chunked) processing based on file size
- **Memory-aware** with configurable thresholds via `config.toml`
- `calculator.py` - Core statistics calculator
- `online_accumulators.py` - Streaming calculations for large files
- `pam_writer.py` - PAM XML statistics file generation

### Validation Package
Located in `gttk/utils/validation/`:
- **TOML-based rules**: Product-specific validation rules with 7 section types (tag, geokey, gdal, geo, xmp, xml, projjson)
- **7 constraint types**: exact, enum, regex, range, ranges, exists, forbidden
- **On-demand statistics**: STATISTICS_* keys computed from raster data, not stored metadata
- **Extended data types**: date, datetime, url, email validation
- `models.py` - ValidationRule, ValidationResult, ValidationSummary dataclasses
- `loader.py` - TOML rule file parser
- `extractors.py` - Value extraction from GeoTIFF sections with XPath/JSONPath support
- `validator.py` - ValidationEngine that applies constraints to extracted values
- `gpkg_writer.py` - GeoPackage output with spatial features

### Key Utilities
- `gttk/utils/metadata_extractor.py` - GeoTIFF metadata extraction
- `gttk/utils/geotiff_processor.py` - GeoTIFF processing logic
- `gttk/utils/srs_logic.py` - Spatial reference system handling (compound CRS, vertical datums)
- `gttk/utils/gdal_runner.py` - GDAL subprocess wrapper for ArcGIS isolation
- `gttk/utils/esri_epsg_lookup.py` - Esri CRS name to EPSG code lookup

### ArcGIS Pro Integration
- `gttk/tools/optimize_compression_arc.py` - Uses OSGeo4W GDAL via subprocess to avoid ArcGIS GDAL conflicts
- `toolbox/GTTK_Toolbox.pyt` - ArcGIS Pro Python Toolbox
- OSGeo4W path configured in `config.toml`
- `gttk/i18n.py` - Toolbox language: detection (`GTTK_LANG` → `config.toml` `[gui] language` → Pro's `ARCGISPRO_UILANGID` registry value → Windows display language), `_()` over TOML catalogs in `gttk/resources/i18n/<lang>.toml` (keyed by the English string), `Picklist` for translated dialog choices that stay codes internally, and `sync_sidecars()` which copies `toolbox/i18n/<lang>/*.pyt.xml` beside the toolbox on load (copies are gitignored). Spanish user docs: `README.es.md`, `toolbox/README.es.md`

## Configuration Files
- `config.toml` - Runtime configuration (OSGeo4W path, toolbox language, statistics tuning). Found by `gttk/utils/config_loader.py`: `GTTK_CONFIG`, then the checkout root, then the packaged default `gttk/resources/config.toml`
- `pyproject.toml` - Package metadata, dependencies, entry point
- `pytest.ini` - Test configuration with markers (`slow`, `unit`, `integration`, `e2e`, `renderer`, `models`); no coverage flags, those live in `pyproject.toml` `[tool.coverage]`
- `.github/workflows/tests.yml` - CI: the fast suite (`-m "not slow"`) on every push and pull request, the full suite on `main`, `coverage.xml` kept as a run artifact
- `.gitattributes` - LF line endings on every checkout, Windows clones included
- `environment.yml` - Conda environment (Python 3.12+, GDAL 3.11+)

## Test Structure
1678 tests total (1424 unit, 80 integration, 58 E2E, 10 benchmark smoke, 106 doctests -- 97 in `gttk/`
and 9 in `tests/`, all run by `--doctest-modules`):
- `tests/unit/` - Isolated component tests including 328 validation tests
- `tests/integration/` - Component interaction tests
- `tests/e2e/` - Full CLI workflow tests
- `tests/benchmarks/` - The statistics benchmarks, hand-run at full size, and a smoke test that runs each at 256×256
- `tests/fixtures/` - Mock GeoTIFF factory (`mock_geotiff_factory.py`) and the fake OSGeo4W tree (`fake_osgeo4w.py`)
- `tests/conftest.py` - Mock GeoTIFF fixtures and assertion formatting
- `conftest.py` (repo root) - `PROJ_LIB` bootstrap, `gdal.UseExceptions()`, and the doctest sandbox

### Doctests

`pytest.ini` passes `--doctest-modules` and lists `gttk` in `testpaths`, so every
`Example:` block in a docstring is executed on every run. An example that stops being
true fails the suite.

A docstring example that needs a file just opens one by name:

```python
>>> with MetadataExtractor('example.tif') as extractor:
```

The root `conftest.py` builds a set of deterministic `MockGeoTIFF` rasters once per
session (`doctest_sample_dir`), and an autouse fixture copies them into a fresh
directory and `chdir`s each doctest into it. So the names are real, writes are
isolated per example, and nothing is left in the working tree. Available:
`example.tif`, `input.tif`, `baseline.tif`, `optimized.tif`, `compressed.tif`,
`image.tif` (3-band), `data.tif`, `dem_with_custom_vertical.tif`, `regular.tif`
(no CRS), `metadata.tif` (GEO_METADATA + XMP + sidecar + a GDAL item), and a
`tiles/` directory. Elevation rasters run 100.0 to 200.0, mean 150.0.

House rules, learned from the 52 examples that had to be repaired:

- **No `Path` reprs in expected output** - it is `PosixPath(...)` on Linux and
  `WindowsPath(...)` on Windows, and this project ships an ArcGIS Pro toolbox.
  Compare `p.name` or `p.as_posix()` instead.
- **No repo-relative paths.** `Path('gttk/resources/rules')` only resolves when
  pytest happens to run from the repo root; use `bundled_rules_dir()`.
- **Format floats explicitly** - `f"{x:.4f}"`, not a bare repr.
- **Sort anything unordered** before printing it.
- **Loop bodies use `...`, not `>>>`.**
- **Method examples need a receiver** - `extractor.extract_gdal(...)`, never a bare
  `extract_gdal(...)`.
- **Assert shape, not counts that churn** - `sorted(rules)` rather than
  `len(rules['tag'])`, which broke the moment a rule was added.
- **`# doctest: +ELLIPSIS` per example, and only when the value is genuinely
  unstable.** Setting `doctest_optionflags` turns off pytest's default of a blanket
  `ELLIPSIS`, on purpose: it lets an example trail off with `...` and pass without
  anyone comparing it to the real output, which is how several of these examples came
  to describe results the code had not produced in releases.
- **Keep a GDAL dataset alive** while you hold a band from it -
  `gdal.Open(f).GetRasterBand(1)` yields a band whose dataset is already collected.

`DEVELOPER.md`'s two worked examples are not reachable by `--doctest-modules`, so
`tests/unit/test_developer_guide.py` extracts and runs them instead.

Validation test coverage:
- `test_validation_models.py` - ValidationRule, ValidationResult, ValidationSummary
- `test_validation_loader.py` - TOML parsing and rule loading
- `test_validation_extractors.py` - Value extraction from all section types
- `test_validation_constraints.py` - All 7 constraint types
- `test_validation_validator.py` - ValidationEngine
- `test_validation_xml.py` - XPath extraction with namespace handling
- `test_validation_phase5.py` - JSONPath, extended data types
- `test_validation_report.py` - Report generation
- `test_validation_output.py` - Output folder, report and input-file path construction
- `test_validation_integration.py` - End-to-end validation workflows

Toolbox language coverage:
- `test_i18n.py` - detection precedence, catalogs, `Picklist`, sidecar sync
- `test_i18n_catalog.py` - every `_()` string in the `.pyt` has a Spanish entry, no orphans, placeholders intact
- `test_toolbox_sidecars.py` - each language's `.pyt.xml` documents exactly the dialog's parameters and labels
- `test_optimize_arc_wiring.py` - the ArcGIS optimize path binds its GDAL options and logs to the GP pane

ArcGIS path coverage (POSIX, through `tests/fixtures/fake_osgeo4w.py`, an OSGeo4W-shaped tree whose
tools are the conda environment's; skipped on Windows, where the real OSGeo4W is the fixture):
- `test_gdal_runner_fake_osgeo4w.py` - the isolated environment, command resolution, the stdin payload protocol and projection extraction, run for real
- `test_optimize_arc_on_linux.py` - `optimize-arc`'s orchestration end to end: a DEM to a COG with a compound CRS and PAM statistics, an RGBA image to an internal mask, an input named like a Python statement

Statistics accuracy:
- `test_statistics_accuracy.py` - `OnlineStatistics` against NumPy, fed block by block
- `test_statistics_phase2_accuracy.py` - the blocked path against NumPy and against the fast path on four rasters

Documentation coverage:
- `test_developer_guide.py` - runs DEVELOPER.md's two worked examples straight out of the markdown

## Key Dependencies
- **GDAL** (>=3.11) - Core geospatial operations
- **tifffile** - Low-level TIFF manipulation
- **lxml** - XML processing (also used for XPath in validation)
- **numpy** - Array operations
- **matplotlib** - Histogram generation
- **mistune** - Markdown to HTML conversion
- **jsonpath-ng** - JSONPath expressions for PROJJSON validation
- **psutil** - Memory monitoring for statistics calculator
- **Pillow** - ICC profile decoding for the InterColourProfile tag

## Data Flow
GeoTIFF file -> Metadata Extractor -> Data Models -> Report Builders -> Section Renderers -> Report Formatters -> Output (HTML/Markdown)
