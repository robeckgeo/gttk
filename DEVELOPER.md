# Developer Guide for GeoTIFF ToolKit (GTTK)

This guide provides in-depth technical information about the architecture and extensibility of the GeoTIFF ToolKit. It is intended for developers who wish to contribute to the project or customize it for specific workflows.

## Report Generation Architecture

The toolkit uses a Builder pattern to separate report content (what to include) from report formatting (how to present).

### Key Components

1. **Data Models** ([`utils/data_models.py`](utils/data_models.py))
    * Strongly-typed dataclasses for all report data
    * Examples: `DifferencesComparison`, `IfdTableData`, `StatisticsData`
    * Ensures type safety and clear contracts between components

2. **Data Fetchers** ([`utils/data_fetchers.py`](utils/data_fetchers.py))
    * Extract data from GeoTIFF files
    * Return dataclass instances
    * Examples: `fetch_tags_data()`, `fetch_statistics_data()`

3. **Report Builders** ([`utils/report_builders.py`](utils/report_builders.py))
    * Determine **WHAT** sections to include in reports
    * Classes: `MetadataReportBuilder`, `ComparisonReportBuilder`
    * Usage: `builder.add_standard_sections(['tags', 'statistics'])`

4. **Section Renderers** ([`utils/section_renderers.py`](utils/section_renderers.py))
    * Render individual sections to markdown
    * Base class: `MarkdownRenderer`
    * Extensible for custom rendering logic

5. **Report Formatters** ([`utils/report_formatters.py`](utils/report_formatters.py))
    * Format complete reports for output (HTML or Markdown)
    * Classes: `HtmlReportFormatter`, `MarkdownReportFormatter`
    * Handle document structure, CSS, navigation, and table of contents

### Example Usage

#### Generating a Metadata Report

```python
from utils.report_context import build_context_from_file
from utils.report_builders import MetadataReportBuilder
from utils.report_formatters import HtmlReportFormatter

# Build context from a GeoTIFF file
context = build_context_from_file('input.tif')

# Build report structure
builder = MetadataReportBuilder(context)
builder.add_standard_sections(['tags', 'statistics', 'cog'])

# Format as HTML
formatter = HtmlReportFormatter(context)
formatter.sections = builder.sections
html_report = formatter.generate()

# Write to file
with open('report.html', 'w') as f:
    f.write(html_report)
```

#### Generating a Comparison Report

```python
from osgeo import gdal
from utils.report_builders import ComparisonReportBuilder
from utils.report_formatters import HtmlReportFormatter
from tools.compare_compression import build_differences_data

# Open datasets
base_ds = gdal.Open('baseline.tif')
comp_ds = gdal.Open('optimized.tif')

# Build differences data
differences = build_differences_data(
    base_ds, comp_ds, args, 'Baseline', 'Optimized'
)

# Build report sections
builder = ComparisonReportBuilder(base_ds, comp_ds, 'Baseline', 'Optimized')
builder.add_differences_section(differences)
builder.add_ifd_sections()
builder.add_statistics_sections()
builder.add_histogram_sections()
builder.add_cog_sections()

# Generate HTML output
context = {'input_filename': 'optimized.tif'}
formatter = HtmlReportFormatter(context)
formatter.sections = builder.sections
html_report = formatter.generate()

# Write report
with open('comparison.html', 'w') as f:
    f.write(html_report)
```

### Adding Custom Sections

To add a new section type:

1. **Create a dataclass** in `data_models.py`:

    ```python
    @dataclass
    class CustomSectionData:
        title: str
        data: Dict[str, Any]
    ```

2. **Add a fetcher function** in `data_fetchers.py`:

    ```python
    def fetch_custom_data(context: Dict[str, Any]) -> Optional[CustomSectionData]:
        # Extract and return data
        return CustomSectionData(title="Custom", data={...})
    ```

3. **Add a renderer method** in `section_renderers.py`:

    ```python
    def render_custom_section(self, data: CustomSectionData) -> str:
        # Generate markdown
        return f"### {data.title}\n..."
    ```

4. **Use the builder** to add your section:

    ```python
    builder.add_section('custom', 'Custom Section', 'Custom', custom_data)
    ```

### Benefits of the Builder Pattern

* **Separation of Concerns**: Content selection, data fetching, rendering, and formatting are independent
* **Extensibility**: Easy to add new report types, output formats, or section types
* **Testability**: Each component can be tested in isolation
* **Reusability**: Builders and formatters can be mixed and matched
* **Type Safety**: Strong typing with dataclasses prevents runtime errors

## Isolated Environment Execution (ArcGIS Pro)

When running within ArcGIS Pro, the toolkit uses an isolation strategy to ensure compatibility and stability.

1. **Challenge**: ArcGIS Pro uses a specific, often older or modified, internal Python environment (`arcpy`) Although its gdal module is up-to-date, many legacy configurations and creation options reside in Esri's `gdal_e.dll`, which notably is NOT kept in sync with GDAL's `gdal.dll` at each release. The outdated settings particularly affect the creation of IFDs, internal masks, metadata, and SRS handling as it lacks PROJ to maintain compliance with the EPSG Registry.
2. **Solution**: The `optimize-arc` tool acts as a bridge.
    * It runs within the ArcGIS Pro Python environment to handle the GUI and argument parsing.
    * It then constructs a payload of GDAL commands.
    * It executes a standalone `gdal_runner.py` script in a separate, fully-featured OSGeo4W environment (configured in `config.toml`).
    * This ensures that the heavy lifting (compression, COG creation) is done by a modern, standard GDAL stack, while the user interface remains integrated with ArcGIS Pro.
3. **Dependencies**: To use the isolated environment capability, **OSGeo4W** must be installed on the system. It is commonly installed alongside QGIS but can also be installed independently.
    * **Download Installer:** [OSGeo4W Network Installer](https://trac.osgeo.org/osgeo4w/)
    * **Required Libraries:**
        * The `gdal_runner.py` script relies on a standard OSGeo4W installation.
        * Ensure the `gdal`, `python3-gdal`, `numpy`, and `python3-numpy` packages are selected during installation (typically included in the "Express Desktop" install).
        * The path to the OSGeo4W root directory (e.g., `C:\OSGeo4W`) must be correctly set in `config.toml`.

## Understanding the Processing Pipeline

`gttk optimize` uses a sophisticated, multi-step pipeline to process your data. All steps are performed in-memory using GDAL's virtual file system, meaning no temporary files are written to disk.

1. **Initial Read & Analysis**: Opens the input file and gathers key metadata (resolution, data type, spatial reference system)
2. **SRS Handling**: Checks for and parses compound SRS; creates new compound SRS if `--vertical-srs` is provided
3. **Resampling/Reprojection** (if needed): Uses `gdal.Warp` to create a new in-memory dataset if resolution or SRS changes
4. **Alpha-to-Mask Conversion** (for images): Converts alpha channel to internal mask for better COG compatibility and compression
5. **Rounding** (for floats): Performs block-based rounding for large floating-point rasters, allowing efficient processing of files too large for RAM
6. **Final Compression and COG Creation**: Processed in-memory dataset is passed to the COG driver for compression and writing. Overviews are generated at this stage.

## Esri CRS Name to EPSG Lookup

The toolkit includes a built-in lookup table that maps Esri-specific CRS names to their corresponding EPSG codes. This feature automatically standardizes GeoTIFFs that are missing an EPSG authority code in their CRS definition, which is common for files generated by Esri software.

### Packaged Data

The lookup table is stored as a JSON file at `resources/esri/esri_epsg_name_lookup.json`. This file is packaged with the toolkit and is used by default for all SRS standardization operations.

### Updating the Lookup Table

The lookup table is generated from Esri's `projection-engine-db-doc` GitHub repository. To update the local version to the latest data, run:

```bash
python tools/build_esri_epsg_lookup.py
```

This will fetch the latest CRS definitions from the repository and overwrite the existing JSON file with the updated data.

## Third-Party Code

This project includes code from the following external source:

* **GDAL: validate_cloud_optimized_geotiff.py**  
  Project: GDAL - Open Source Geospatial Foundation  
  Copyright (c) 2017, Even Rouault  
  Licensed under the MIT License  
  Original source: [validate_cloud_optimized_geotiff.py](https://github.com/OSGeo/gdal/blob/master/swig/python/gdal-utils/osgeo_utils/samples/validate_cloud_optimized_geotiff.py)
  