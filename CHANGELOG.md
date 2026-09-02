# Change Log

All notable changes to this project will be documented in this file.

## [Unreleased]

### Security

- **File paths no longer reach the Python scripts GTTK runs under OSGeo4W.** Six generated
  scripts -- the projection reader `gttk read` uses inside ArcGIS Pro, and the five that
  `optimize-arc` writes for NoData remapping, mask attachment, rounding and translation --
  embedded the input, output, mask and XML paths in their source with only the backslashes
  escaped. A `"` in a filename ended the string literal and the rest of the name ran as
  Python in the OSGeo4W interpreter, on every toolbox Optimize Compression run: a raster
  named `x"; open("MARKER", "w").close() #.tif` created the marker and produced no output.
  Paths now travel on the script's argv, and every other value (NoData numbers, decimals,
  translate options) is rendered by `gttk.utils.gdal_scripts.literal`, which produces a
  Python literal by construction. `tests/unit/test_gdal_scripts.py` runs the real scripts
  against that filename.
- **Opening a report from WSL no longer hands its path to PowerShell unquoted.** `open_file`
  built `Start-Process "<path>"` with an f-string; inside PowerShell's double quotes `$(...)`
  is evaluated, a backtick escapes and a `"` ends the string, and the path comes from the
  input raster's name. The path is now a single-quoted PowerShell literal carried as
  `-EncodedCommand`, so neither PowerShell nor the Windows command line ever parses it.
- **Every parser that reads XML out of a GeoTIFF or a sidecar now refuses entities, DTDs
  and the network.** Nine sites -- the validation extractors, the report builder's
  statistics filter, the GEO_METADATA writer, the XML pretty-printer, the markdown renderer
  and the tag parser -- used lxml's default parser, so whether
  `<!ENTITY x SYSTEM "file:///...">` read a local file depended on the installed libxml2.
  `gttk.utils.xml_safety` fixes the answer for all of them; internal entities are not
  substituted either, which is what a test can observe on any libxml2. A metadata sidecar
  over 64 MiB is refused rather than read into memory, and `decode_xml_bytes` no longer
  carries a failure branch that `latin-1` made unreachable.

### Added

- **The ArcGIS Pro path runs on Linux, against a fake OSGeo4W.** `gdal_runner` launches
  OSGeo4W's Python on a JSON payload of GDAL commands and resolves each one against
  `<OSGeo4W>/bin`, so outside Windows none of it ran, and its tests stubbed the functions
  under test. `tests/fixtures/fake_osgeo4w.py` lays that directory tree out over the conda
  environment's interpreter and tools, and `tests/integration/test_gdal_runner_fake_osgeo4w.py`
  drives the real runner through it: the isolated environment, `gdalinfo` and `gdal_calc.py`
  resolved by name, the script launched by path with a payload on stdin, and the projection
  reader on a raster whose name is a Python statement.
- **A `dev` extra, and a test that installs the wheel.** `pip install -e ".[dev]"` brings
  `pytest` and `pytest-cov`, which only `environment.yml` and `requirements.txt` listed
  before. `tests/integration/test_installed_wheel.py` builds the wheel from what git would
  ship, installs it into a throwaway virtual environment and runs `gttk read`, `gttk test`
  and `gttk validate` from a scratch directory -- the arrangement none of the other 1,500
  tests ever sees, since they all run against the editable checkout.
- **The test suite runs in GitHub Actions.** There was no CI at all, so every guard in the
  repository -- the executed doctests, the import-side-effect checks, the README tables
  pinned to the resolver -- held only while someone remembered to run `pytest`.
  `.github/workflows/tests.yml` builds the conda environment from `environment.yml`, runs
  `pytest -m "not slow"` for every push and pull request and the full suite for a push to
  `main`, and keeps `coverage.xml` as a run artifact so a coverage number can be traced to
  the run that produced it.
- **`.gitattributes` pins LF line endings.** GTTK ships an ArcGIS Pro toolbox, so Windows
  clones are expected; without the rule, a clone made with `core.autocrlf=true` rewrites
  every text file on checkout and shows the whole tree as modified.

### Changed

- **The external XML metadata lookup is documented where it is used.** `gttk read`,
  `gttk validate`, `gttk optimize` and `gttk optimize-arc` look for `<stem>.xml`, then
  `<stem>_meta.xml`, beside the raster, then in its parent directory, then in a sibling
  `metadatos/` directory (INEGI's delivery layout) -- so a batch run reads XML from one
  level above the directory it was pointed at, on purpose. The order is now in each tool's
  `--help`, in the README, and pinned by a test.
- **`gttk test` keeps its scratch rasters beside the output workbook.** `--temp-dir`
  defaulted to `./temp`, relative to wherever the command was run from, so multi-gigabyte
  candidate rasters piled up in the current directory -- 5.7 GB of them in a checkout root,
  and 39 files per test-suite run. The default is now `<input stem>_gttk_test/` next to the
  workbook, and a scratch directory that ends up inside a directory input is skipped when
  the candidates are collected, so a rerun cannot test its own leftovers. The ArcGIS
  optimize path's temporary workspace likewise moves under the platform's temporary
  directory instead of falling back to the working directory when `TEMP` is unset.
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

- `gttk compare --config`. Declared with a cwd-relative default, stored on the arguments
  and read by nothing.
- `gttk/utils/xml_helpers.py`, a leftover from a Qt GUI this repository does not contain.
  It imported PyQt6 at module scope, which was declared in neither `pyproject.toml`,
  `environment.yml` nor `requirements.txt` and installed nowhere, so the module could not
  be imported at all -- it had no references, no tests, and 0% coverage. Its sibling
  `xml_formatter.py` is unaffected and still used.

### Fixed

- **`optimize-arc` no longer assumes OSGeo4W's Python is 3.12.** `gdal_runner` hard-coded
  `apps/Python312`, both for `PYTHONHOME` and for the `Scripts` directory that holds
  `gdal_calc.py`, so an OSGeo4W that ships a newer Python pointed the isolated interpreter at
  a directory that does not exist. The runner now discovers `apps/Python3*` and takes the
  newest. It also joins and splits `PATH` with the platform's separator instead of a
  literal `;`.
- **What a fallback could not read is said, not skipped.** The projection script run under
  OSGeo4W for ArcGIS Pro swallowed seven kinds of failure with `pass` and still exited 0
  with valid JSON; it now lists each one and the parent logs them by file. A per-band NoData
  string the statistics calculator cannot read as a number is reported instead of being
  used as it came. The rules loader's product-metadata lookup names an invalid TOML file it
  skips, as the product listing already did. And a `gttk validate` result whose value could
  not be compared at all -- text against a numeric range, or against an exact number -- says
  "could not be compared: not a number" in its message instead of reading like a plain
  mismatch.
- **Failures inside the extractors are reported, not rendered as clean results.** A crash
  in the COG validator came back as no validation at all, which the report showed as a
  file without issues; it is now an error entry, "Validation could not run". An IFD field
  that could not be read (block size, byte counts, dimensions, band count, compressed
  size) showed a blank cell indistinguishable from a file that has no such value; the
  cells stay blank and one warning per IFD names the fields and why. A TIFF tag that could
  not be parsed vanished from the Tags table with a debug line; it stays, valued
  "(unparsed)" with the reason. When the tag lookup file itself is missing, every unnamed
  tag now says "tag lookup unavailable" instead of presenting a broken installation as a
  file full of unknown tags. A file a batch drops because GDAL cannot open it, or because
  the georeferencing check raised, is logged at warning rather than debug. And
  `gttk validate` records the compression algorithm as "unknown", not "NONE", when it has
  no dataset to ask.
- **Handles and scratch files are released on the failure paths too.** `MetadataExtractor`
  opened the GDAL dataset and then the TIFF; if the second raised, the context manager never
  exited and the dataset -- a lock on the file, on Windows -- outlived the failure. The
  dev-only baseline mode of the efficiency calculation left its scratch directory behind,
  with a partial uncompressed raster in it, on every path but success. `gttk compare` held
  its baseline open until the frame was collected if the comparison would not open. All
  three release in a `finally`.
- **The output tree of a batch run never reaches above the output directory.**
  `prepare_output_path` joined a relative path with nothing stopping `../`; it now refuses
  a file that is not under the input directory.
- **`gttk optimize` refuses to write onto its input.** Nothing stopped `-o` from naming the
  input file or the input directory; the run exited 0 and the data survived only because
  the pipeline stages through `/vsimem/`. Both are now refused before any work starts, and
  the unreachable branch that set the output to the input for a list of files is gone.
- **The single-band check for DEM, error and thematic products fails loudly.** It caught its
  own error and re-raised it only when the message contained the words "Multi-band
  rasters", so any other failure of `gdal.Open` -- an unreadable input included -- passed
  validation without a word; it also skipped releasing the dataset on the path that
  raised. It now re-raises by type, logs an input it cannot open, and releases the handle.
- **`gttk validate` finds `.TIF` files on Linux.** Three directory scans used
  `glob('*.tif')`, which is case-sensitive on Linux and not on Windows, so a directory of
  upper-case extensions validated completely on one platform and reported "no GeoTIFF
  files" on the other. All three match by lower-cased suffix.
- **Two `gttk test` runs sharing a scratch directory no longer delete each other's
  candidates.** Candidate names are deterministic, so concurrent runs on one input used
  to unlink and overwrite each other's files mid-benchmark; each run now works in its own
  `run_*` directory under the scratch root.
- A GeoPackage that cannot be replaced (Windows refuses the unlink while ArcGIS Pro has it
  open) is reported by name instead of raising, and a projection-info request to OSGeo4W
  that does not answer within 30 s now kills the interpreter it started instead of leaving
  it running.
- **A compression efficiency that could not be computed is reported as unknown, not as
  0.0.** `calculate_compression_efficiency` returned 0.0 for any exception, at debug level,
  and 0.0 is also the honest answer for an uncompressed file; nothing downstream could tell
  the two apart. `gttk read` printed 0.00% and a 1.00x ratio, `gttk validate` recorded no
  savings, the comparison report showed both files as equally efficient, and `gttk test`
  subtracted the figure from every candidate's improvement column. The function now returns
  `None` when a file cannot be opened, an IFD cannot be read or carries no byte counts, or
  nothing could be sized, and logs why at warning; every renderer shows "n/a". A genuinely
  uncompressed file is still 0.0, and `gttk validate` now records its 0.0 savings and 1.0
  ratio instead of nothing. `get_uncompressed_size` follows suit, the per-IFD header
  estimate no longer answers "1024 bytes" for an IFD it could not read, and
  `TiffTagParser.close()` leaves a `TiffFile` the caller lent in open, as its context
  manager already did.
- **`pip install geotiff-toolkit` brings everything the code imports.** `psutil` was in
  `environment.yml` and `requirements.txt` but not in `pyproject.toml`, so a pip install ran
  without it and the statistics calculator silently used a fixed fast-path threshold
  instead of sizing it from the available RAM; Pillow, which decodes the InterColourProfile
  tag, was declared nowhere and present only because matplotlib happens to need it. Both
  are dependencies now, and `tests/unit/test_dependency_manifests.py` keeps the three
  manifests and the code's imports in agreement. The wheel's package-data rule now says
  what ships (`resources/**/*`, minus the build caches and bytecode); the old list of
  extensions covered none of the JavaScript, CSV, XLSX or theme files that reports and
  `gttk test` read, and `MANIFEST.in` no longer prunes five directories that do not exist.
- **An installed copy finds its configuration.** `config.toml` lives outside the package,
  and three modules looked for it three directories above their own file -- the checkout
  root in a checkout, `site-packages` in a wheel, where nothing is. `gttk test` and
  `gttk optimize-arc` crashed at dispatch with `FileNotFoundError`, and every other command
  began its stdout with `Warning: config.toml not found`. The loader now reads `GTTK_CONFIG`
  if it is set, then a checkout's own `config.toml`, then a packaged default that ships in
  the wheel; it reads nothing until a value is asked for and never prints. The OSGeo4W-side
  runner takes the OSGeo4W root from the payload its parent sends instead of reading any
  file, writes its debug log under the temporary directory rather than inside the package,
  and no longer prepends the checkout root to the importing process's `sys.path`.
- **Importing GTTK no longer changes the host's matplotlib backend, its root logger or
  PROJ's network setting.** The histogram module forced the Agg backend at import (the
  cure for a headless stall under WSLg), which replaced whatever backend an application
  had chosen; it now draws on a figure with its own Agg canvas and never imports pyplot.
  `gdal_runner`, `geokey_parser` and `tiff_tag_parser` logged through the root logger's
  `logging.debug()` functions, which install a handler on it the first time they run --
  inside ArcGIS Pro, or on any malformed tag during `gttk read`; they log through their
  own module loggers now. `geokey_parser` wrote `PROJ_NETWORK=OFF` into the environment at
  import; `gdal_env()` turns the network off for the duration of an operation instead and
  restores the host's setting.

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
