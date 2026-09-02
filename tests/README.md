# GeoTIFF Toolkit - Testing Guide

**Status**: ✅ **1,445 tests passing** | **Doctests enabled** | **Production Ready**

This guide provides comprehensive information about testing GTTK (GeoTIFF ToolKit).

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Test Suite Overview](#test-suite-overview)
3. [Running Tests](#running-tests)
4. [Test Organization](#test-organization)
5. [Writing Tests](#writing-tests)
6. [Testing Fixtures](#testing-fixtures)
7. [Coverage Reports](#coverage-reports)
8. [Troubleshooting](#troubleshooting)
9. [Contributing](#contributing)

---

## Quick Start

```bash
# Install test dependencies
pip install -e .
pip install pytest pytest-cov

# Run all tests
pytest

# Run with coverage report
pytest --cov=gttk --cov-report=html

# Run fast tests only (skip slow E2E tests)
pytest -m "not slow"

# View coverage report
start htmlcov/index.html  # Windows
open htmlcov/index.html   # macOS/Linux
```

---

## Test Suite Overview

### Statistics

- **Total Tests**: 1,713
- **Success Rate**: 100%
- **Test Categories**:
  - Unit Tests: 1,459 tests (models, processors, extractors, formatters, utilities)
  - Doctests: 106 (97 in `gttk/`, 9 in `tests/`)
  - Integration Tests: 80 tests (metadata workflows, statistics validation)
  - E2E Tests: 58 tests (CLI commands)
  - Benchmark smoke tests: 10 tests (every statistics benchmark, once at 256×256)

Counts here and in the tree below are from `pytest --collect-only`; doctests
live in the source modules and are not listed per file.

### Doctests

`pytest.ini` passes `--doctest-modules` and lists `gttk` in `testpaths`, so every
`Example:` block in a docstring runs as part of the suite -- a docstring that stops
matching the code fails the build.

An example that needs a raster opens one by name:

```python
>>> with MetadataExtractor('example.tif') as extractor:
...     builder = MetadataReportBuilder(extractor)
...     builder.build(['tags', 'statistics'])
```

The repository-root `conftest.py` builds deterministic `MockGeoTIFF` rasters once per
session and gives each doctest its own copy of them as the working directory, so the
names resolve, writes stay isolated, and nothing is left behind. `DEVELOPER.md`'s two
worked examples are run the same way, by `tests/unit/test_developer_guide.py`.

The house rules for writing one -- `Path` reprs, `ELLIPSIS`, float formatting, keeping
a GDAL dataset alive -- are in the **Doctests** section of `CLAUDE.md`.

### Coverage Targets

| Module Type | Target | Current | Status |
| ----------- | ------ | ------- | ------ |
| Core Tools (CLI) | 85%+ | TBD | 🟢 Target |
| Data Models | 95%+ | TBD | 🟢 Target |
| Metadata Extraction | 90%+ | TBD | 🟢 Target |
| Report Formatters | 85%+ | TBD | 🟢 Target |
| Utility Modules | 75%+ | TBD | 🟢 Target |

### Directory Structure

```text
conftest.py                                      # (repo root) PROJ_LIB, gdal.UseExceptions,
                                                 # and the doctest sandbox
tests/
├── __init__.py
├── conftest.py                                  # Mock GeoTIFF fixtures & assertion formatting
├── README.md                                    # This guide
├── fixtures/                                    # Mock data factories
│   ├── custom_vertical_crs.py                   # A vertical CRS with no EPSG code
│   ├── fake_osgeo4w.py                          # An OSGeo4W-shaped tree over the conda tools (POSIX)
│   ├── mock_geotiff_factory.py                  # MockGeoTIFF generator
│   └── statistics_helpers.py                    # Statistics test utilities
├── unit/                                        # Unit tests (1,459)
│   ├── test_data_models.py                      # Data classes (129)
│   ├── test_cli_help.py                         # Rendered command-line help (99)
│   ├── test_readme_option_tables.py             # README option tables pinned to the parser (14)
│   ├── test_geotiff_processor.py                # GeoTIFF processing (71)
│   ├── test_i18n.py                             # Toolbox language detection & catalogs (67)
│   ├── test_overview_control.py                 # Overview & thread control on the COG path (61)
│   ├── test_gdal_scripts.py                     # Scripts run under OSGeo4W take paths from argv (59)
│   ├── test_srs_logic.py                        # SRS/CRS logic (58)
│   ├── test_validation_extractors.py            # Validation value extraction (58)
│   ├── test_toolbox_sidecars.py                 # .pyt.xml help sidecars pinned to the dialog (51)
│   ├── test_validation_constraints.py           # All 7 constraint types (52)
│   ├── test_metadata_extractor.py               # Metadata extraction (52)
│   ├── test_xml_formatter.py                    # XML formatting (44)
│   ├── test_validation_models.py                # Validation data models (42)
│   ├── test_validation_xml.py                   # XPath extraction with namespaces (38)
│   ├── test_validation_phase5.py                # JSONPath & extended data types (36)
│   ├── test_validation_validator.py             # ValidationEngine (35)
│   ├── test_statistics_type_utilities.py        # Native dtype utilities (32)
│   ├── test_import_side_effects.py              # Importing GTTK leaves the host process alone (36)
│   ├── test_discard_lsb.py                      # DISCARD_LSB decimals-to-bits helper (30)
│   ├── test_report_formatters.py                # Report formatting (30)
│   ├── test_validation_loader.py                # TOML rule loading, in name order (30)
│   ├── test_mock_factory.py                     # MockGeoTIFF factory itself (27)
│   ├── test_preprocessor.py                     # Data preprocessing (25)
│   ├── test_xml_safety.py                       # XML from rasters and sidecars never reads a file (25)
│   ├── test_statistics_vectorized.py            # Vectorized statistics (24)
│   ├── test_validation_report.py                # Validation report generation (19)
│   ├── test_statistics_block_infrastructure.py  # Block processing (17)
│   ├── test_statistics_strategy_selection.py    # Fast vs blocked strategy selection (16)
│   ├── test_validation_output.py                # Output folder & report path construction (16)
│   ├── test_statistics_phase2.py                # Phase 2 statistics optimizations (13)
│   ├── test_compression_efficiency.py           # An error is not 0.0 (15)
│   ├── test_path_helpers.py                     # Report opening on every platform, output tree, sidecar search order (21)
│   ├── test_config_loader.py                    # Where config.toml comes from, quietly, and only live keys (12)
│   ├── test_cli_defaults.py                     # One default per option: command line, dataclass, dialog (9)
│   ├── test_section_renderers.py                # Section rendering (11)
│   ├── test_log_helpers.py                      # Logging helpers, startup env checks, no arcpy initialiser (10)
│   ├── test_i18n_catalog.py                     # Spanish catalog pinned to the toolbox (8)
│   ├── test_script_arguments.py                 # optimize's guards: no in-place writes, band check (8)
│   ├── test_custom_vertical_crs_compound.py     # Custom vertical CRS into a compound CRS (7)
│   ├── test_dependency_manifests.py             # The three manifests agree with the imports (6)
│   ├── test_optimize_arc_wiring.py              # ArcGIS optimize path wiring (6)
│   ├── test_pytest_config.py                    # Coverage opt-in & the CI policy pinned (6)
│   ├── test_toolbox_load.py                     # Loading the .pyt the way ArcGIS Pro does (6)
│   ├── test_scratch_locations.py                # Scratch files never land in the working directory (4)
│   ├── test_statistics_accuracy.py              # OnlineStatistics against NumPy, block by block (4)
│   ├── test_tiff_tag_parser.py                  # Unparsable tags stay, a missing lookup says so (4)
│   ├── test_developer_guide.py                  # DEVELOPER.md's worked examples, executed (3)
│   ├── test_gdal_runner.py                      # gdal_runner's stdout protocol and its timeout (4)
│   ├── test_histogram_generator.py              # Histograms render headless and pick no backend (2)
│   ├── test_logging_hygiene.py                  # Nothing logs through the root logger (2)
│   ├── test_custom_vertical_datum_storage.py    # Vertical datum without an EPSG code (1)
│   ├── test_compare_compression.py              # compare releases both datasets on every path (1)
│   └── test_statistics_nodata_warnings.py       # An unreadable per-band NoData is reported (1)
├── integration/                                 # Integration tests (80)
│   ├── test_validation_integration.py           # End-to-end validation workflows (20)
│   ├── test_installed_wheel.py                  # GTTK works from an installed wheel (6)
│   ├── test_metadata_workflow.py                # Metadata extraction workflows (13)
│   ├── test_statistics_phase2_accuracy.py       # Blocked path against NumPy and the fast path (12)
│   ├── test_gdal_runner_fake_osgeo4w.py         # gdal_runner run for real through a fake OSGeo4W (8)
│   ├── test_optimize_arc_on_linux.py            # optimize-arc's orchestration, end to end, on Linux (3)
│   ├── test_statistics_blocked_path.py          # Block-based statistics (9)
│   └── test_statistics_native_dtype.py          # Native dtype statistics (9)
├── e2e/                                         # End-to-end CLI tests (58)
│   ├── test_read_command.py                     # `gttk read` (17)
│   ├── test_compare_command.py                  # `gttk compare` (15)
│   ├── test_optimize_command.py                 # `gttk optimize` (14)
│   ├── test_test_command.py                     # `gttk test` (8)
│   └── test_validate_command.py                 # `gttk validate`, run from outside the repo (4)
└── benchmarks/                                  # Statistics benchmarks and their smoke test (10)
    ├── benchmark_statistics.py                  # Hand-run: python -m tests.benchmarks.benchmark_statistics
    └── test_benchmarks_smoke.py                 # Every benchmark once at 256×256 (10)
```

---

## Running Tests

### Basic Commands

```bash
# Run all tests with verbose output
pytest -v

# Run specific test file
pytest tests/unit/test_data_models.py

# Run specific test class
pytest tests/unit/test_data_models.py::TestTiffTag

# Run specific test method
pytest tests/unit/test_data_models.py::TestTiffTag::test_instantiation

# Run tests matching pattern
pytest -k "test_markdown"
```

### Test Markers

Tests are categorized using pytest markers for easy filtering:

```bash
# Run only unit tests (fast)
pytest -m unit

# Run only integration tests
pytest -m integration

# Run only E2E tests
pytest -m e2e

# Run only model tests
pytest -m models

# Exclude slow tests
pytest -m "not slow"

# Run multiple markers
pytest -m "unit or integration"
```

### Available Markers

- `unit` - Fast unit tests (isolated components)
- `integration` - Integration tests (component interactions)
- `e2e` - End-to-end tests (full CLI workflows)
- `models` - Data model tests
- `slow` - Tests that take >5 seconds

### Coverage Reports

```bash
# Generate HTML coverage report
pytest --cov=gttk --cov-report=html --cov-report=term

# Generate XML coverage report (for CI)
pytest --cov=gttk --cov-report=xml

# Show missing lines in terminal
pytest --cov=gttk --cov-report=term-missing

# Fail if coverage below threshold
pytest --cov=gttk --cov-fail-under=80
```

### Parallel Execution

```bash
# Install pytest-xdist
pip install pytest-xdist

# Run tests in parallel (faster)
pytest -n auto

# Run with specific number of workers
pytest -n 4
```

### Stop on First Failure

```bash
# Stop after first failure (useful for debugging)
pytest -x

# Stop after 3 failures
pytest --maxfail=3
```

---

## Test Organization

### Testing Pyramid

GTTK follows the testing pyramid pattern:

```text
        E2E Tests (10%)
       /              \
      Integration (20%)
     /                  \
    Unit Tests (70%)
```

### Unit Tests

**Purpose**: Test individual functions and classes in isolation

**Location**: `tests/unit/`

**Examples**:

- Data model instantiation and methods
- Mock GeoTIFF factory validation
- Report formatter output verification
- Utility function behavior

**Characteristics**:

- Fast (<1 second per test)
- No external dependencies
- Use mocks/stubs for isolation
- Test single responsibility

### Integration Tests

**Purpose**: Test how components work together

**Location**: `tests/integration/`

**Examples**:

- Metadata extraction from mock GeoTIFFs
- Report generation from extracted data
- Complete workflow validation
- Component interaction verification

**Characteristics**:

- Medium speed (1-5 seconds per test)
- Test multiple components
- Use in-memory mock data
- Verify data flow

### End-to-End Tests

**Purpose**: Test complete workflows from CLI to output

**Location**: `tests/e2e/`

**Examples**:

- `gttk read` command execution
- `gttk compare` workflow
- `gttk optimize` COG creation
- `gttk test` benchmarking

**Characteristics**:

- Slower (5-30 seconds per test)
- Test full user workflows
- Create temporary files
- Verify CLI argument parsing
- Check output file creation

---

## Writing Tests

### Test Naming Conventions

```python
def test_<function_name>_<scenario>_<expected_result>():
    """Test that <function> <does what> when <scenario>."""
```

**Examples**:

```python
def test_tiff_tag_instantiation_with_valid_data():
    """Test TiffTag instantiation with complete valid data."""

def test_markdown_formatter_handles_special_characters():
    """Test that MarkdownFormatter escapes special characters correctly."""

def test_read_command_generates_html_report():
    """Test that gttk read creates HTML output file."""
```

### Test Structure (AAA Pattern)

```python
def test_example():
    """Test that example function works correctly."""
    # Arrange: Set up test data and conditions
    mock_data = MockGeoTIFF(width=256, height=256)
    
    # Act: Execute the function being tested
    result = process_data(mock_data)
    
    # Assert: Verify the expected outcome
    assert result.success is True
    assert result.width == 256
```

### Using Fixtures

```python
def test_with_fixture(mock_geotiff_basic):
    """Test using shared fixture."""
    # Fixture automatically provides mock_geotiff_basic
    ds = mock_geotiff_basic.to_gdal_dataset()
    
    assert ds.RasterXSize == 256
    assert ds.RasterYSize == 256
```

### Parametrized Tests

```python
@pytest.mark.parametrize("width,height,expected_pixels", [
    (256, 256, 65536),
    (512, 512, 262144),
    (1024, 1024, 1048576),
])
def test_pixel_count_calculation(width, height, expected_pixels):
    """Test pixel count with various dimensions."""
    mock = MockGeoTIFF(width=width, height=height)
    assert mock.get_pixel_count() == expected_pixels
```

### Testing Exceptions

```python
def test_function_raises_exception_on_invalid_input():
    """Test that function raises ValueError for invalid input."""
    with pytest.raises(ValueError, match="Invalid width"):
        MockGeoTIFF(width=-1, height=256)
```

### E2E Test Template

```python
@pytest.mark.e2e
@pytest.mark.slow
def test_command_basic_workflow(tmp_path):
    """Test basic workflow of command."""
    # Arrange: Create input file
    input_path = tmp_path / "input.tif"
    output_path = tmp_path / "output.tif"
    
    mock_data = MockGeoTIFF(width=512, height=512)
    mock_data.save_to_file(input_path)
    
    # Act: Run CLI command
    result = subprocess.run([
        'gttk', 'command',
        '-i', str(input_path),
        '-o', str(output_path)
    ], capture_output=True, text=True)
    
    # Assert: Verify success
    assert result.returncode == 0
    assert output_path.exists()
    
    # Verify output properties
    with gdal.Open(str(output_path)) as ds:
        assert ds.RasterXSize == 512
        assert ds.RasterYSize == 512
```

---

## Testing Fixtures

### Shared Fixtures (conftest.py)

There are two. `tests/conftest.py` holds the mock GeoTIFF fixtures below and the
assertion formatting that keeps base64 histograms out of failure output. The
repository-root `conftest.py` holds what has to run above everything else: the
`PROJ_LIB` bootstrap (before the first `osgeo` import), `gdal.UseExceptions()`, and
the doctest sandbox -- which only a root conftest can supply, since a conftest reaches
only items at or below its own directory and the doctests live under `gttk/`.

**Mock GeoTIFF Fixtures**:

```python
@pytest.fixture
def mock_geotiff_basic():
    """256x256, 1-band Float32, WGS84, no compression."""
    return MockGeoTIFF(width=256, height=256, bands=1)

@pytest.fixture
def mock_geotiff_multiband():
    """512x512, 3-band Byte, UTM Zone 10N, RGB."""
    return MockGeoTIFF(
        width=512, height=512, bands=3,
        data_type='Byte', crs='EPSG:32610'
    )

@pytest.fixture
def mock_geotiff_with_nodata():
    """100x100 with NoData pixels."""
    return MockGeoTIFF(
        width=100, height=100,
        nodata_value=-9999.0,
        nodata_pixel_count=42
    )

@pytest.fixture
def mock_geotiff_compressed():
    """512x512 DEFLATE compressed, tiled."""
    return MockGeoTIFF(
        width=512, height=512,
        compression='DEFLATE',
        predictor=2,
        tile_size=256
    )

@pytest.fixture
def mock_geotiff_dem():
    """1024x1024 DEM with compound CRS."""
    return MockGeoTIFF(
        width=1024, height=1024,
        bands=1, data_type='Float32',
        crs='EPSG:32610+5703'  # UTM + vertical
    )
```

**Sample Data Fixtures**:

```python
@pytest.fixture
def sample_tiff_tags():
    """List of common TIFF tags for testing."""
    return [
        TiffTag(code=256, name="ImageWidth", value=1024),
        TiffTag(code=257, name="ImageLength", value=1024),
        # ... more tags
    ]

@pytest.fixture
def sample_statistics():
    """List of StatisticsBand objects."""
    return [
        StatisticsBand(
            band_name="Gray",
            minimum=0.0,
            maximum=255.0,
            mean=127.5,
            # ... more fields
        )
    ]
```

### Temporary Directory Fixture

```python
def test_with_temp_dir(tmp_path):
    """Test using pytest's tmp_path fixture."""
    # tmp_path is automatically created and cleaned up
    test_file = tmp_path / "test.tif"
    
    # Create file in temp directory
    create_test_file(test_file)
    
    assert test_file.exists()
    # Cleanup happens automatically
```

---

### The fake OSGeo4W tree (`tests/fixtures/fake_osgeo4w.py`)

The ArcGIS Pro path runs GDAL in a separate OSGeo4W interpreter: `gdal_runner`
launches `<OSGeo4W>/bin/python.exe` on itself with a JSON payload of commands and
resolves each command against `<OSGeo4W>/bin`. On Linux none of that could run, so it
was tested through stubs that replaced the functions under test. `build_fake_osgeo4w(root)`
lays out the directories the code looks for -- `bin/python.exe`, `bin/gdal_translate`,
`apps/Python312/Scripts/gdal_calc.py`, `share/gdal`, `share/proj` -- as shell shims that
`exec` the conda environment's interpreter and tools, and symlinks to its data
directories. Point `paths.osgeo4w` at it (the tests monkeypatch `config.get`) and the real
runner, the real payload protocol and the real GDAL do the work. POSIX only: on Windows
the real OSGeo4W is the fixture, and these tests skip.

## Coverage Reports

### Generating Reports

```bash
# HTML report (most detailed)
pytest --cov=gttk --cov-report=html

# Terminal report with missing lines
pytest --cov=gttk --cov-report=term-missing

# XML report (for CI/CD)
pytest --cov=gttk --cov-report=xml

# Combined reports
pytest --cov=gttk --cov-report=html --cov-report=term-missing
```

### Reading Coverage Reports

**HTML Report** (`htmlcov/index.html`):

- File-by-file coverage breakdown
- Line-by-line highlighting
- Missing coverage identification
- Coverage trends

**Terminal Report**:

```text
Name                          Stmts   Miss  Cover   Missing
-----------------------------------------------------------
gttk/__init__.py                  5      0   100%
gttk/compare_compression.py     234     23    90%   45-47, 89-92
gttk/read_metadata.py           189     15    92%   123-125, 201
-----------------------------------------------------------
TOTAL                          2341    187    92%
```

### Coverage Goals

- **Critical Modules**: >90% coverage (CLI tools, core processing)
- **Important Modules**: >85% coverage (data models, formatters)
- **Supporting Modules**: >75% coverage (utilities, helpers)

---

## Troubleshooting

### Common Issues

#### ImportError: No module named 'gttk'

**Solution**:

```bash
# Install package in editable mode
pip install -e .
```

#### GDAL-related test failures

**Solution**:

```bash
# Ensure GDAL is properly installed
conda install -c conda-forge gdal

# Or with OSGeo4W (Windows)
# Add OSGeo4W bin to PATH
```

#### Tests pass individually but fail when run together

**Cause**: Shared state between tests

**Solution**:

- Ensure tests are independent
- Use fixtures for setup/teardown
- Clean up resources properly
- Avoid global state

#### Slow test execution

**Solution**:

```bash
# Run in parallel
pytest -n auto

# Skip slow tests during development
pytest -m "not slow"

# Use specific test selection
pytest tests/unit/  # Skip integration and E2E
```

#### Base64 data flooding terminal output

**Status**: ✅ **FIXED** - Custom pytest hook in conftest.py

The test suite automatically truncates long base64 strings in assertion output.

#### pytest markers not recognized

**Cause**: Invalid pytest.ini configuration

**Solution**: Ensure pytest.ini has correct marker definitions:

```ini
[pytest]
markers =
    unit: Unit tests (fast, isolated)
    integration: Integration tests
    e2e: End-to-end tests
    slow: Slow-running tests
    models: Data model tests
```

### Debugging Failed Tests

```bash
# Show print statements
pytest -s

# Show locals in traceback
pytest -l

# Enter debugger on failure
pytest --pdb

# Stop on first failure
pytest -x

# Verbose output
pytest -vv
```

### Test Isolation Issues

If tests fail when run together but pass individually:

1. Check for shared fixtures
2. Look for global state modifications
3. Ensure proper cleanup in teardown
4. Use `pytest --lf` to run only last failed tests
5. Use `pytest --ff` to run failed tests first

---

## Contributing

### Before Submitting Tests

1. **Run full test suite**:

   ```bash
   pytest -v
   ```

2. **Check coverage**:

   ```bash
   pytest --cov=gttk --cov-report=term-missing
   ```

3. **Run linting** (if configured):

   ```bash
   flake8 tests/
   black tests/ --check
   ```

4. **Ensure tests are documented**:

   - Clear docstrings
   - Descriptive test names
   - Comments for complex logic

### Test Development Workflow

1. **Write failing test** (TDD approach)
2. **Implement feature** to make test pass
3. **Run tests** to verify
4. **Check coverage** for new code
5. **Refactor** if needed
6. **Document** test purpose

### Pull Request Checklist

- [ ] All tests pass locally
- [ ] New tests added for new features
- [ ] Coverage maintained or improved
- [ ] Tests properly documented
- [ ] No skipped tests without good reason
- [ ] Test names follow conventions
- [ ] Fixtures used appropriately

### Best Practices

1. **Test Independence**: Each test should run successfully in isolation
2. **Fast Execution**: Unit tests should complete in <1 second
3. **Clear Assertions**: One logical assertion per test
4. **Descriptive Names**: Test names explain what is being tested
5. **Minimal Mocking**: Only mock external dependencies
6. **Comprehensive Coverage**: Test happy paths, edge cases, and errors
7. **Documentation**: Every test has a clear docstring

---

## Additional Resources

- **pytest Documentation**: [https://docs.pytest.org/](https://docs.pytest.org/)
- **pytest-cov Documentation**: [https://pytest-cov.readthedocs.io/](https://pytest-cov.readthedocs.io/)
- **GDAL Python API**: [https://gdal.org/api/python.html](https://gdal.org/api/python.html)

---

## Test Suite Status

**Last Updated**: January 2026
**Phase**: Phase 1 Expansion Complete (Priority 1 Modules)
**Status**: ✅ Production Ready
**Total Tests/Functions**: 638 (623 pytest tests + 15 benchmark/validation functions)
**Pass Rate**: 100%

### Recent Updates ⭐

- ✅ **Statistics Benchmarks Consolidated**: Phase 1/2 merged into unified suite (10 functions)
- ✅ **GeoTIFF Processor**: 82 comprehensive tests added
- ✅ **XML Formatter**: 44 comprehensive tests added
- ✅ **SRS Logic**: 42 comprehensive tests added
- ✅ **Metadata Extractor**: 35 comprehensive tests added
- ✅ **Preprocessor**: 27 comprehensive tests added

### Test Growth

- **Initial**: 386 tests (pre-expansion)
- **Current**: 638 tests/functions (+252, 65% increase)
  - 623 pytest-collected tests (516 unit + 31 integration + 76 e2e)
  - 10 benchmark functions (not collected by pytest)
  - 5 validation functions (not collected by pytest)
- **Target**: 720-750 tests (with Phase 2 & 3 complete)

---

For questions about testing or to report issues, please refer to:

- Test files themselves for implementation details
- [`plans/testing_expansion_plan.md`](../plans/testing_expansion_plan.md) for comprehensive testing roadmap
- Individual test plan documents in `plans/` for module-specific details
