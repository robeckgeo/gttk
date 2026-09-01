# Doctest Enablement - Implementation Plan

## Background

Every `Example:` block in a GTTK docstring is written in doctest form (`>>> ...`),
but `pytest.ini` has never passed `--doctest-modules`, so none of them has ever
been executed. They are documentation that nothing checks.

The cost of that showed up in v0.10.0. `DEVELOPER.md` and seven docstrings in
`report_builders.py` / `report_formatters.py` described an API that had been gone
for several releases: a `utils.report_context` module, a
`build_context_from_file()` function, `add_standard_sections()`,
`fetch_and_add_section()` and an `HtmlReportGenerator` class -- none of which
exist. One example called `f.write(html)` where `html` was never assigned. Those
were corrected by hand and the two `DEVELOPER.md` blocks are now extracted from
the markdown and executed as part of review, but the rest of the codebase has no
such guard.

## Problem Statement

Running `pytest --doctest-modules gttk/` today gives **52 failures across 17
files**, plus three structural blockers that stop collection before the failures
are even reached. Until that is zero, `--doctest-modules` cannot be turned on,
and docstring examples will keep drifting silently.

Note that these are *not* failures in the test suite. `pytest` as configured
reports 1279 passed / 1 skipped / 40 deselected. The 52 appear only when
`--doctest-modules` is passed explicitly.

## Constraints

- **The payoff is all-or-nothing.** The value of this work is `--doctest-modules`
  running in CI. A partial fix leaves the flag off, so the remaining examples rot
  anyway. Do not land this half-done.
- Examples must stay readable as *documentation* first. A doctest that passes but
  reads like test scaffolding is a worse docstring than the one it replaced.
- No behaviour changes. `pytest -m "not slow"` must still report 1279 passed.
- Anything needing a raster should use the existing
  `tests/fixtures/mock_geotiff_factory.MockGeoTIFF`, not a checked-in binary.

## Structural blockers

These stop collection outright and must be cleared first.

1. **`gttk/utils/xml_helpers.py` imports PyQt6 at module scope** (line 26,
   `from PyQt6.QtCore import QMimeData`). PyQt6 is not a declared dependency, so
   `--doctest-modules` aborts the whole run with a collection error. The module
   is at 0% coverage. Either make the import lazy inside the function that needs
   it, declare PyQt6 as an optional extra, or add the file to `--ignore`.
2. **`gttk/tools/test_compression.py::test_compression` is collected as a test.**
   `python_functions = test_*` in `pytest.ini` matches the tool's own
   `test_compression()` entry point once `--doctest-modules` starts walking
   source modules. Needs a `collect_ignore` entry, a rename, or a narrower
   `python_functions`.
3. **`--maxfail=10` in `addopts`** halts the run long before the full picture is
   visible. Raise or override it while working through this.

## Failure inventory

Counts from `pytest --doctest-modules gttk/ --ignore=gttk/utils/xml_helpers.py --maxfail=1000`.

| File | Failures | Classes |
|------|----------|---------|
| `gttk/utils/data_models.py` | 10 | 4×placeholder, 3×wrong-api, 1×malformed, 1×output, 1×fixture |
| `gttk/utils/validation/extractors.py` | 8 | 7×other, 1×placeholder |
| `gttk/utils/report_builders.py` | 4 | 2×fixture, 1×malformed, 1×placeholder |
| `gttk/utils/section_registry.py` | 4 | 3×output, 1×placeholder |
| `gttk/utils/report_formatters.py` | 3 | 2×placeholder, 1×import |
| `gttk/utils/statistics/helpers.py` | 3 | 2×placeholder, 1×other |
| `gttk/utils/statistics/online_accumulators.py` | 3 | 3×other |
| `gttk/utils/validation/constraints.py` | 3 | 3×output |
| `gttk/utils/validation/output.py` | 3 | 3×output |
| `gttk/utils/geokey_parser.py` | 2 | 1×other, 1×output |
| `gttk/utils/validation/models.py` | 2 | 2×placeholder |
| `gttk/utils/validation/validator.py` | 2 | 1×import, 1×other |
| `gttk/utils/geotiff_processor.py` | 1 | 1×output |
| `gttk/utils/preprocessor.py` | 1 | 1×fixture |
| `gttk/utils/statistics/__init__.py` | 1 | 1×fixture |
| `gttk/utils/statistics/calculator.py` | 1 | 1×placeholder |
| `gttk/utils/validation/loader.py` | 1 | 1×output |

### What the classes mean

- **placeholder** (13) -- the example references a name that was never defined:
  `baseline_stats`, `baseline_cog`, `baseline_tiles`, `dataset`, `rule`,
  `builder`. These were written as sketches. Each needs a real object built in
  the example, or a `doctest_namespace` entry.
- **output** (13) -- the example runs but prints something other than what is
  written beneath it. Each expected block must be re-derived from an actual run,
  not guessed.
- **fixture** (5) -- opens a file such as `'example.tif'`. Needs a shared raster.
- **wrong-api** (3) -- calls a signature that no longer exists. These are real
  documentation bugs of the same kind found in v0.10.0 and are worth fixing on
  their own merit.
- **import** (3) -- the name is correct but never imported into the example.
- **malformed** (2) -- the doctest block itself is not valid syntax.
- **other** (~10) -- mostly unqualified method calls in method docstrings
  (`>>> extract_xpath(...)` where it should be `>>> extractor.extract_xpath(...)`).

## Detailed Implementation Steps

### Step 1: Clear the structural blockers

Make PyQt6 lazy in `xml_helpers.py`, stop `test_compression()` being collected,
and confirm `pytest --doctest-modules gttk/ --maxfail=1000` reaches the end of
collection without error. Nothing else can be measured until this holds.

### Step 2: Add a doctest fixture surface

In `tests/conftest.py` (or a new `gttk/conftest.py`), provide an autouse
`doctest_namespace` fixture supplying the names examples legitimately share:

```python
@pytest.fixture(autouse=True)
def _doctest_env(doctest_namespace, tmp_path_factory):
    from gttk.utils.metadata_extractor import MetadataExtractor
    d = tmp_path_factory.mktemp('doctest')
    sample = d / 'example.tif'
    MockGeoTIFF(width=64, height=64).save_to_file(sample)
    doctest_namespace['MetadataExtractor'] = MetadataExtractor
    doctest_namespace['example_tif'] = str(sample)
```

This clears the 5 *fixture* and 3 *import* failures at once, and is the
foundation for the placeholder work. Prefer injecting a real `example_tif` path
over rewriting every example to build its own raster.

### Step 3: Fix the cheap classes

*wrong-api* (3), *import* (3), *malformed* (2) and the unqualified-method
subset of *other*. These are straightforward corrections against the real
signatures and improve the docstrings whether or not doctests are ever enabled.

### Step 4: Re-derive the output mismatches

For each of the 13 *output* failures, run the example and paste the true result.
Watch for values that are not stable across runs or platforms -- dict ordering,
float formatting, absolute paths. Use `# doctest: +ELLIPSIS` or
`+NORMALIZE_WHITESPACE` where the output is legitimately variable rather than
freezing a brittle string.

### Step 5: Rewrite the placeholder sketches

The 13 *placeholder* examples are the real work: each needs its stand-in
(`baseline_stats` and friends) replaced by an object the reader can actually
construct. Where a faithful example would be longer than the docstring deserves,
it is better to shorten the example to something true than to keep a long one
that lies.

### Step 6: Enable and lock it in

Add `--doctest-modules` to `addopts` in `pytest.ini`, together with whatever
`--ignore` the blockers still need. Confirm both:

```bash
pytest -m "not slow"          # still 1279 passed, 1 skipped
pytest --doctest-modules gttk/   # 0 failed
```

### Step 7: Extend the DEVELOPER.md guard

`DEVELOPER.md`'s two worked examples are currently verified by extracting their
fenced Python blocks from the markdown and executing them. Fold that into the
suite as a real test so the guide cannot drift either.

## Out of scope

- Adding examples to docstrings that have none.
- `draft/` -- untracked and ignored.
- The `s3://` reference link in `README.md`, which renders as a link that does
  nothing in a browser. Cosmetic, decide separately.
