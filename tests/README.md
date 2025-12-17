# GeoTIFF Toolkit - Testing Guide

**Status**: ✅ **246 tests passing** | **Phase 5 Complete** | **Production Ready**

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

- **Total Tests**: 246
- **Success Rate**: 100%
- **Test Categories**:
  - Unit Tests: ~170 tests (data models, mock factory, formatters)
  - Integration Tests: 13 tests (metadata workflows)
  - E2E Tests: 63 tests (CLI commands)

### Coverage Targets

| Module Type | Target | Current | Status |
|-------------|--------|---------|--------|
| Core Tools (CLI) | 85%+ | TBD | 🟢 Target |
| Data Models | 95%+ | TBD | 🟢 Target |
| Metadata Extraction | 90%+ | TBD | 🟢 Target |
| Report Formatters | 85%+ | TBD | 🟢 Target |
| Utility Modules | 75%+ | TBD | 🟢 Target |

### Directory Structure

```
tests/
├── __init__.py                    # Test package initialization
├── conftest.py                    # Shared fixtures & pytest configuration
├── README.md                      # Detailed test documentation
├── fixtures/                      # Mock data factories
│   ├── __init__.py
│   └── mock_geotiff_factory.py   # MockGeoTIFF generator
├── unit/                          # Unit tests (70% of suite)
│   ├── __init__.py
│   ├── test_data_models.py       # Data class tests (~48 tests)
│   ├── test_mock_factory.py      # Mock factory validation (~60 tests)
│   └── test_report_formatters.py # Report generation tests (~63 tests)
├── integration/                   # Integration tests (20% of suite)
│   ├── __init__.py
│   └── test_metadata_workflow.py # End-to-end workflows (13 tests)
└── e2e/                          # End-to-end CLI tests (10% of suite)
    ├── __init__.py
    ├── test_read_command.py      # `gttk read` tests (22 tests)
    ├── test_compare_command.py   # `gttk compare` tests (19 tests)
    ├── test_optimize_command.py  # `gttk optimize` tests (14 tests)
    └── test_test_command.py      # `gttk test` tests (8 tests)
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

```
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

```
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

**Last Updated**: December 2025
**Phase**: Phase 4 Complete (Integration & E2E Tests)
**Status**: ✅ Production Ready
**Total Tests**: 246
**Pass Rate**: 100%

---

For questions about testing or to report issues, please refer to the test files themselves or the comprehensive testing plan in `plans/TESTING_PLAN.md`.
