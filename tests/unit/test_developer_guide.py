#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ******************************************************************************
# Project: GeoTIFF ToolKit (GTTK)
# Author: Eric Robeck <robeckgeo@gmail.com>
#
# Copyright (c) 2026, Eric Robeck
# Licensed under the MIT License
# ******************************************************************************

"""
Runs the two worked examples in DEVELOPER.md.

Docstring examples are checked by --doctest-modules, but the guide's fenced code
blocks are not reachable that way, and in v0.10.0 they were the ones that had
drifted furthest: they described a `utils.report_context` module and an
`HtmlReportGenerator` class that had not existed for several releases. So the
blocks are extracted from the markdown and executed against real rasters.

Only the two blocks under "### Example Usage" are runnable. The rest of the file
is deliberately fragmentary -- `{...}`, `...`, names defined nowhere -- and stays
out of scope. The count is asserted so that adding or moving a block under that
heading fails here rather than quietly going unchecked.
"""

import re
import shutil
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DEVELOPER_MD = REPO_ROOT / 'DEVELOPER.md'

START_HEADING = '### Example Usage'
END_HEADING = '### Adding Custom Sections'

FENCE = re.compile(r'^```python\n(.*?)^```', re.MULTILINE | re.DOTALL)


def extract_worked_examples() -> list:
    """
    Return the fenced Python blocks between the two headings, in file order.

    Raises:
        AssertionError: If either heading is missing, or they are out of order.
    """
    text = DEVELOPER_MD.read_text(encoding='utf-8')

    start = text.find(START_HEADING)
    end = text.find(END_HEADING)
    assert start != -1, f"DEVELOPER.md no longer has a '{START_HEADING}' heading"
    assert end != -1, f"DEVELOPER.md no longer has an '{END_HEADING}' heading"
    assert start < end, f"'{START_HEADING}' now follows '{END_HEADING}'"

    return [block for block in FENCE.findall(text[start:end])]


@pytest.fixture
def guide_workspace(tmp_path, doctest_sample_dir, monkeypatch) -> Path:
    """
    A directory holding the rasters the guide opens by name, made current.

    The blocks say `MetadataExtractor('input.tif')` and write `report.html`
    beside it, so they are run in a throwaway copy of the doctest samples rather
    than edited to fit the test.
    """
    workspace = tmp_path / 'guide'
    shutil.copytree(doctest_sample_dir, workspace)
    monkeypatch.chdir(workspace)
    return workspace


@pytest.mark.unit
class TestDeveloperGuideExamples:
    """The guide's worked examples have to run as written."""

    def test_exactly_two_blocks_are_extracted(self):
        """
        Guards the extraction itself.

        Without this the suite would pass on an empty list if the headings were
        renamed -- the failure mode the guide already suffered once.
        """
        blocks = extract_worked_examples()

        assert len(blocks) == 2, (
            f"Expected 2 runnable blocks between '{START_HEADING}' and "
            f"'{END_HEADING}', found {len(blocks)}. If the guide gained or lost "
            f"one, update this test to match."
        )

    def test_metadata_report_example_runs(self, guide_workspace):
        """The first block reads input.tif and writes report.html."""
        block = extract_worked_examples()[0]
        assert "MetadataReportBuilder" in block, "First block is no longer the metadata example"

        exec(compile(block, 'DEVELOPER.md:metadata-example', 'exec'), {})

        report = guide_workspace / 'report.html'
        assert report.is_file(), "The example did not write report.html"
        assert report.read_text(encoding='utf-8').startswith('<!DOCTYPE html>')

    def test_comparison_report_example_runs(self, guide_workspace):
        """The second block reads baseline.tif and optimized.tif."""
        block = extract_worked_examples()[1]
        assert "ComparisonReportBuilder" in block, "Second block is no longer the comparison example"

        exec(compile(block, 'DEVELOPER.md:comparison-example', 'exec'), {})

        report = guide_workspace / 'comparison.html'
        assert report.is_file(), "The example did not write comparison.html"
        assert report.read_text(encoding='utf-8').startswith('<!DOCTYPE html>')
