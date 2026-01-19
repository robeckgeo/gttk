# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

GeoTIFF ToolKit (GTTK) is a Python toolkit for analyzing, optimizing, and compressing GeoTIFF files. It provides five CLI tools (`compare`, `optimize`, `test`, `read`, `validate`) and an ArcGIS Pro Python Toolbox.

## Build and Development Commands

```bash
# Environment setup
conda env create -f environment.yml
conda activate gttk
pip install -e .  # Development install

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

# Coverage report
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
2. **Data Fetchers** (`gttk/utils/data_fetchers.py`) - Extract data from GeoTIFF files, return dataclass instances
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

## Configuration Files
- `config.toml` - Runtime configuration (OSGeo4W path, logging, statistics tuning)
- `pyproject.toml` - Package metadata, dependencies, entry point
- `pytest.ini` - Test configuration with markers (`slow`, `unit`, `integration`, `e2e`, `models`)
- `environment.yml` - Conda environment (Python 3.12+, GDAL 3.11+)

## Test Structure
936 tests total (832 unit, 51 integration, 53 E2E):
- `tests/unit/` - Isolated component tests including 298 validation tests
- `tests/integration/` - Component interaction tests
- `tests/e2e/` - Full CLI workflow tests
- `tests/fixtures/` - Mock GeoTIFF factory (`mock_geotiff_factory.py`)
- `tests/conftest.py` - Shared fixtures and pytest configuration

Validation test coverage:
- `test_validation_models.py` - ValidationRule, ValidationResult, ValidationSummary
- `test_validation_loader.py` - TOML parsing and rule loading
- `test_validation_extractors.py` - Value extraction from all section types
- `test_validation_constraints.py` - All 7 constraint types
- `test_validation_validator.py` - ValidationEngine
- `test_validation_xml.py` - XPath extraction with namespace handling
- `test_validation_phase5.py` - JSONPath, extended data types
- `test_validation_report.py` - Report generation
- `test_validation_integration.py` - End-to-end validation workflows

## Key Dependencies
- **GDAL** (>=3.11) - Core geospatial operations
- **tifffile** - Low-level TIFF manipulation
- **lxml** - XML processing (also used for XPath in validation)
- **numpy** - Array operations
- **matplotlib** - Histogram generation
- **mistune** - Markdown to HTML conversion
- **jsonpath-ng** - JSONPath expressions for PROJJSON validation
- **psutil** - Memory monitoring for statistics calculator

## Data Flow
GeoTIFF file -> Metadata Extractor -> Data Fetchers -> Data Models -> Report Builders -> Section Renderers -> Report Formatters -> Output (HTML/Markdown)
