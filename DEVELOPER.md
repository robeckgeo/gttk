# Developer Guide for GeoTIFF ToolKit (GTTK)

This guide provides in-depth technical information about the architecture and extensibility of the GeoTIFF ToolKit. It is intended for developers who wish to contribute to the project or customize it for specific workflows.

## Report Generation Architecture

The toolkit uses a Builder pattern to separate report content (what to include) from report formatting (how to present).

### Key Components

1. **Data Models** ([`gttk/utils/data_models.py`](gttk/utils/data_models.py))
    * Strongly-typed dataclasses for all report data
    * Examples: `FileComparison`, `IfdTableData`, `StatisticsData`
    * Ensures type safety and clear contracts between components

2. **Metadata Extractor** ([`gttk/utils/metadata_extractor.py`](gttk/utils/metadata_extractor.py))
    * Extract data from GeoTIFF files
    * Return dataclass instances
    * Examples: `extract_tags()`, `extract_statistics()`

3. **Report Builders** ([`gttk/utils/report_builders.py`](gttk/utils/report_builders.py))
    * Determine **WHAT** sections to include in reports
    * Classes: `MetadataReportBuilder`, `ComparisonReportBuilder`
    * Usage: `builder.build(['tags', 'statistics'])`

4. **Section Renderers** ([`gttk/utils/section_renderers.py`](gttk/utils/section_renderers.py))
    * Render individual sections to markdown
    * Base class: `MarkdownRenderer`
    * Extensible for custom rendering logic

5. **Report Formatters** ([`gttk/utils/report_formatters.py`](gttk/utils/report_formatters.py))
    * Format complete reports for output (HTML or Markdown)
    * Classes: `HtmlReportFormatter`, `MarkdownReportFormatter`
    * Handle document structure, CSS, navigation, and table of contents

### Example Usage

The two blocks below are not illustrations: `tests/unit/test_developer_guide.py`
extracts them from this file and runs them, against rasters named `input.tif`,
`baseline.tif` and `optimized.tif`. If you edit them, they have to keep working.
Adding or removing a block under this heading fails that test until it is updated.

#### Generating a Metadata Report

```python
from gttk.utils.metadata_extractor import MetadataExtractor
from gttk.utils.report_builders import MetadataReportBuilder
from gttk.utils.report_formatters import HtmlReportFormatter

# Open the file; the extractor is the data-access layer
with MetadataExtractor('input.tif') as extractor:

    # The builder decides WHAT sections to include
    builder = MetadataReportBuilder(extractor, page=0, tag_scope='compact')
    builder.build(['tags', 'statistics', 'cog'])

    # The formatter decides HOW they are presented
    formatter = HtmlReportFormatter(filename=extractor.filepath.name)
    formatter.report_title = "Metadata Content"
    formatter.sections = builder.sections
    html_report = formatter.format()

# Write to file
with open('report.html', 'w', encoding='utf-8') as f:
    f.write(html_report)
```

`format()` calls `prepare_rendering()` for you, renders every section that
`has_data()`, converts the markdown to HTML and wraps it in the report template.
Swap in `MarkdownReportFormatter(filename=...)` for markdown output; set
`include_title = True` on it if you want the title and table of contents.

#### Generating a Comparison Report

```python
from gttk.utils.metadata_extractor import MetadataExtractor
from gttk.utils.report_builders import ComparisonReportBuilder
from gttk.utils.report_formatters import HtmlReportFormatter

# Both files stay open for the life of the builder
with MetadataExtractor('baseline.tif') as base_extractor, \
     MetadataExtractor('optimized.tif') as comp_extractor:

    # add_all_sections() computes the differences itself and adds every paired
    # section: IFDs, tiling, statistics, histograms and COG validation
    builder = ComparisonReportBuilder(
        base_extractor, comp_extractor, 'Baseline', 'Optimized'
    )
    builder.add_all_sections()

    formatter = HtmlReportFormatter(
        filename='optimized.tif', report_type='comparison'
    )
    formatter.report_title = "Compression Comparison"
    formatter.sections = builder.sections
    html_report = formatter.format()

# Write report
with open('comparison.html', 'w', encoding='utf-8') as f:
    f.write(html_report)
```

The CLI tools take a longer route than this: they assemble the markdown by hand
so a report summary can be injected above the first section. `format()` is the
short path when you do not need that.

### Adding Custom Sections

To add a new section type:

1. **Create a dataclass** in `data_models.py`:

    ```python
    @dataclass
    class CustomSectionData:
        title: str
        data: Dict[str, Any]
    ```

2. **Add an extractor method** in `metadata_extractor.py`:

    ```python
    def extract_custom_data(self) -> Optional[CustomSectionData]:
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
    builder.add_section('custom', custom_data, title_override='Custom Section')
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
    * It executes a standalone `gdal_runner.py` script in a separate, fully-featured OSGeo4W environment (configured in `config.toml`). The payload names the OSGeo4W root, so the runner reads no configuration of its own.
    * This ensures that the heavy lifting (compression, COG creation) is done by a modern, standard GDAL stack, while the user interface remains integrated with ArcGIS Pro.
3. **Dependencies**: To use the isolated environment capability, **OSGeo4W** must be installed on the system. It is commonly installed alongside QGIS but can also be installed independently.
    * **Download Installer:** [OSGeo4W Network Installer](https://trac.osgeo.org/osgeo4w/)
    * **Required Libraries:**
        * The `gdal_runner.py` script relies on a standard OSGeo4W installation.
        * Ensure the `gdal`, `python3-gdal`, `numpy`, and `python3-numpy` packages are selected during installation (typically included in the "Express Desktop" install).
        * The path to the OSGeo4W root directory (e.g., `C:\OSGeo4W`) must be correctly set in `config.toml`.
4. **Generated scripts**: the Python scripts GTTK writes for that interpreter follow two rules, kept in
   `gttk/utils/gdal_scripts.py`. A script takes its file paths from `sys.argv` and never carries one in
   its source, and every other value is rendered by `literal()`, which produces a Python literal by
   construction. `tests/unit/test_gdal_scripts.py` runs each script on a raster whose name is a Python
   statement.
5. **Running it without Windows**: `tests/fixtures/fake_osgeo4w.py` builds a directory shaped like an
   OSGeo4W installation -- `bin/python.exe`, the GDAL tools, `apps/Python3xx/Scripts/gdal_calc.py`,
   `share/gdal`, `share/proj` -- out of shell shims that run the conda environment's interpreter and
   tools. With `paths.osgeo4w` pointed at it, `gdal_runner` and the `optimize-arc` orchestration run for
   real on Linux (`tests/integration/test_gdal_runner_fake_osgeo4w.py`,
   `tests/integration/test_optimize_arc_on_linux.py`). The runner discovers whichever
   `apps/Python3*` the installation has, so an OSGeo4W that moves its Python needs no change here.

## GTTK as a Library: No Import Side Effects

Importing GTTK does not change the process it is imported into. GDAL configuration and
GDAL's Python exception mode are applied for the duration of an operation by
`gttk.utils.gdal_env.gdal_env()` and restored afterwards, so a host application keeps its
own settings.

Each tool's **public** entry point (`optimize_compression`, `compare_compression`,
`read_metadata`, `test_compression`, `validate_metadata`, and the ArcGIS variant) opens
that context and delegates to a `_*_inner` function holding the real work. When adding a
tool, follow the same shape; when calling into the utility layer directly, open
`gdal_env()` yourself:

```python
from gttk.utils.gdal_env import gdal_env

with gdal_env():
    ...  # GDAL sees GTTK's settings here, and only here
```

`gdal_env()` nests safely, so an entry point and a helper may both use it. It also turns
PROJ's network access off for the duration (`osr.SetPROJEnableNetwork`) and restores the
host's setting afterwards; `geokey_parser` used to force `PROJ_NETWORK=OFF` into the
environment at import, for the whole process.

**Applications choose the exception mode.** `gdal.UseExceptions()` is process-global, so
GTTK does not call it at import. The CLI (`gttk/main.py`), the ArcGIS toolbox and the
test suite each call it for themselves; a library consumer should do the same, or rely on
`gdal_env()` around the calls it makes.

**Logging goes to the `gttk` logger, never root.** Every module uses
`logging.getLogger(__name__)`, which places it under `gttk.*`, and logs through that
logger -- never through `logging.debug()` and its siblings, which are the root logger's
functions and install a handler on it the first time they run
(`tests/unit/test_logging_hygiene.py` scans for them). `setup_logger()`
configures that logger and sets `propagate = False`, so GTTK owns its output once you opt
in; an application that never calls it receives GTTK's messages through its own root
handlers by normal propagation. Clearing root's handlers -- which `setup_logger` used to
do -- silently disabled the logging of anything that imported GTTK.

**Rendering never selects a matplotlib backend.** `histogram_generator` draws on a
`Figure` with its own Agg canvas and does not import `pyplot`, so an application that chose
a backend keeps it and a headless run never touches a GUI one.

## XML That GTTK Did Not Write

Tags 700 (XMP), 42112 (GDAL_METADATA) and 50909 (GEO_METADATA), and the `.xml` and
`.aux.xml` sidecars, are parsed through `gttk.utils.xml_safety` -- never with a bare
`etree.fromstring` or a parser a site builds for itself. `untrusted_parser()` never
substitutes an entity, loads a DTD or touches the network, and the four options that make
it so cannot be passed to it. `tests/unit/test_xml_safety.py` feeds an entity that names a
local file through every entry point: a tag written into a raster, a sidecar beside it, and
the formatters that render them.

## Understanding the Processing Pipeline

`gttk optimize` uses a sophisticated, multi-step pipeline to process your data. All steps are performed in-memory using GDAL's virtual file system, meaning no temporary files are written to disk.

1. **Initial Read & Analysis**: Opens the input file and gathers key metadata (resolution, data type, spatial reference system)
2. **SRS Handling**: Checks for and parses compound SRS; creates new compound SRS if `--vertical-srs` is provided
3. **SRS Assignment**: Writes the resolved SRS as WKT2. This is an assignment, not a warp -- pixels and the geotransform are never touched, so a file's georeferencing cannot shift. GTTK does not reproject; use `gdalwarp` first if you need a different CRS
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

## Where the `optimize` Defaults Live

Most `gttk optimize` options are declared with `default=None`. That `None` is a sentinel,
not a value: `OptimizeArguments._resolve_defaults` (`gttk/utils/script_arguments.py`)
turns it into a real setting using `--product-type` and the codec that ends up selected.
`_resolve_defaults` opens no files, so a throwaway `OptimizeArguments(product_type=...)`
is a complete, always-current answer to "what would GTTK choose here?".

That property is what everything else hangs off. `gttk/utils/cli_help.py` exposes it as
`probe_defaults()`, and three consumers call it rather than restating the rules:

| Consumer | Uses it for |
|---|---|
| `gttk/main.py` | the `Default: ...` clause in each option's help, and the profile table in `optimize`'s epilog |
| `--show-defaults` | the resolved settings block, including where each value came from |
| `toolbox/GTTK_Toolbox.pyt` | pre-filling the ArcGIS dialog in `_reset_all_dependents` |

**When you change a default, change it in `optimize_constants.py` or `_resolve_defaults`
and nowhere else.** Help text, the epilog table, the ArcGIS dialog and
`--show-defaults` all follow. `tests/unit/test_cli_help.py` pins the epilog table and the
README table to the resolver, so a hand-edit that disagrees fails the suite.

### Known ArcGIS toolbox divergences

The toolbox deliberately differs from the CLI in three places, all in the **Read
Metadata** tool. These serve the dialog's audience rather than a script's, and are left
as they are on purpose:

| Parameter | Toolbox | CLI | Why |
|---|---|---|---|
| `reader_type` | `analyst` | `producer` | someone opening a GUI is usually reading, not producing |
| `tag_scope` | `compact` | `complete` | the full tag dump overwhelms a dialog-driven review |
| `write_pam_xml` | `True` | `False` | ArcGIS wants the `.aux.xml` alongside the raster |

`OptimizeCompression.write_pam_xml` used to diverge too (`False` against the CLI's
`True`); that one was a plain bug and now matches.

## Translating the toolbox

The ArcGIS toolbox chooses its language when ArcGIS Pro loads it
(`gttk/i18n.py`, `detect_language()`): `GTTK_LANG`, then `config.toml`
`[gui] language`, then the `ARCGISPRO_UILANGID` registry value Pro writes when a display
language is chosen in its Options, then the Windows display language. `arcpy` exposes no
language API, and Python's `locale` reflects the Windows *region format* rather than the
display language, so it is only a last resort off Windows. Esri's documented alternative
-- shipping the toolbox as an installed Python module with an `esri/help/<lang>/gp` tree
-- was not used: the toolbox is delivered by cloning the repository, and that route still
leaves the `.pyt` labels in English.

Three surfaces carry the strings:

| Surface | Where it lives | Pinned by |
|---|---|---|
| labels, choices and messages in `toolbox/GTTK_Toolbox.pyt` | `gttk/resources/i18n/<lang>.toml`, keyed by the English string | `tests/unit/test_i18n_catalog.py` |
| the parameter help panel (`.pyt.xml` sidecars) | `toolbox/i18n/<lang>/`, copied beside the `.pyt` when it loads (the copies are gitignored) | `tests/unit/test_toolbox_sidecars.py` |
| detection, catalogs and `Picklist` | `gttk/i18n.py` | `tests/unit/test_i18n.py` |

Rules that keep it honest:

- Wrap every user-visible literal in `_()`. Use named placeholders and `.format()` after
  translating -- never an f-string inside `_()`.
- Dialog choices are `Picklist`s: the toolbox compares *codes*, `N_()` marks the English
  label, and `Picklist.code()` accepts the label in any language, so a run saved to History
  or copied as a Python command under one language still runs under another.
- A new string needs an entry in every catalog and a removed one must leave them; a
  sidecar must document exactly the dialog's parameters under that language's labels. The
  tests above fail otherwise.
- A sidecar's `dialogReference` must be rich text (`<DIV><DIV><P><SPAN>…`), the form
  Esri's metadata editor writes: Pro's item-description stylesheet drops plain text and
  shows "no reference for this parameter" instead. The sidecar test enforces it.
- After editing anything -- a catalog, a sidecar, `gttk/i18n.py` or any other `gttk`
  module -- right-click the toolbox in the Catalog pane and **Refresh**. Pro re-executes
  only the `.pyt`, so the toolbox re-imports the whole `gttk` package itself on every
  load; only packages outside `gttk` still need a Pro restart.
- To add a language, add its code to `SUPPORTED`, a `<code>.toml` catalog and a
  `toolbox/i18n/<code>/` directory of sidecars; the tests parametrise over every
  language they find there.

## Examples That Run

`pytest.ini` passes `--doctest-modules` and lists `gttk` in `testpaths`, so every
`Example:` block in a docstring is executed on every test run. An example that stops
matching the code fails the suite. This is not decoration: v0.10.0 shipped seven
docstrings describing a `utils.report_context` module, a `build_context_from_file()`
function and an `HtmlReportGenerator` class, none of which had existed for several
releases, because nothing had ever run them.

Write examples that open files by name:

```python
>>> with MetadataExtractor('example.tif') as extractor:
...     builder = MetadataReportBuilder(extractor)
...     builder.build(['tags', 'statistics'])
```

The repository-root `conftest.py` builds a set of deterministic `MockGeoTIFF` rasters
once per session and gives each doctest a fresh copy of them as its working directory,
so the filenames are real, one example's writes cannot reach the next, and nothing is
left in the working tree. `example.tif`, `input.tif`, `baseline.tif`, `optimized.tif`,
`compressed.tif`, `image.tif` (3-band), `data.tif`, `dem_with_custom_vertical.tif`,
`regular.tif` (no CRS), `metadata.tif` (GEO_METADATA + XMP + sidecar) and a `tiles/`
directory are available. Elevation rasters run 100.0 to 200.0 with a mean of 150.0.

Two rules are worth repeating here because breaking them produces examples that pass on
one machine and fail on another. Never put a `Path` repr in expected output -- it is
`PosixPath(...)` on Linux and `WindowsPath(...)` on Windows, and this project ships an
ArcGIS Pro toolbox; compare `p.name` or `p.as_posix()`. And `ELLIPSIS` is off (pytest
enables it by default; `doctest_optionflags` in `pytest.ini` overrides that), so an
example that truncates its expected output with `...` has to opt in per-example with
`# doctest: +ELLIPSIS` and be able to say why. The full list is in CLAUDE.md.

## Third-Party Code

This project includes code from the following external source:

* **GDAL: validate_cloud_optimized_geotiff.py**  
  Project: GDAL - Open Source Geospatial Foundation  
  Copyright (c) 2017, Even Rouault  
  Licensed under the MIT License  
  Original source: [validate_cloud_optimized_geotiff.py](https://github.com/OSGeo/gdal/blob/master/swig/python/gdal-utils/osgeo_utils/samples/validate_cloud_optimized_geotiff.py)
  