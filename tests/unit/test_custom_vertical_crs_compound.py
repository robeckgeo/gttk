import re
from osgeo import osr
from gttk.utils.srs_logic import get_srs_from_user_input, create_compound_srs

# This test validates that a custom vertical CRS WKT (GGM10) is preserved when building a COMPOUNDCRS
# and that GDAL/OSR does not downgrade the vertical datum to "unknown" in WKT2_2019 output.


def test_compound_with_custom_vertical_preserves_vdatum_and_units():
    # Horizontal: Mexico ITRF2008 / UTM zone 13N (EPSG:6368)
    horiz = osr.SpatialReference()
    assert horiz.ImportFromEPSG(6368) == 0

    # Vertical: custom registry entry "GGM10" provided by get_srs_from_user_input()
    vert = get_srs_from_user_input("GGM10")
    assert vert is not None, "Failed to parse custom vertical CRS 'GGM10' from registry"
    assert vert.IsVertical(), "Custom vertical CRS 'GGM10' should be recognized as vertical"

    # Check vertical WKT2 (standalone) preserves datum name and unit at CS level
    wkt2_vert = vert.ExportToWkt(["FORMAT=WKT2_2019"])
    assert 'VDATUM["Geoide Gravimétrico Mexicano 2010"]' in wkt2_vert, \
        f"Expected VDATUM name in vertical WKT2, got: {wkt2_vert}"
    assert 'LENGTHUNIT["metre",1]' in wkt2_vert, \
        f"Expected LENGTHUNIT at CS level in vertical WKT2, got: {wkt2_vert}"
    # Axis name is likely preserved in WKT2 (allow any whitespace variants)
    assert "gravity-related height (H)" in wkt2_vert

    # Build compound using the library helper (which now prefers manual WKT2 for custom vertical CRS)
    compound = create_compound_srs(horiz, vert)

    # Validate the compound WKT2_2019 keeps the VERTCRS with VDATUM and unit
    wkt2_compound = compound.ExportToWkt(["FORMAT=WKT2_2019"])

    assert wkt2_compound.startswith("COMPOUNDCRS["), \
        f"Expected WKT2 COMPOUNDCRS, got: {wkt2_compound[:80]}..."

    # Confirm vertical branch name and datum are preserved
    assert 'VERTCRS["GGM10 height"' in wkt2_compound, \
        "Expected VERTCRS name 'GGM10 height' in compound WKT2"
    assert 'VDATUM["Geoide Gravimétrico Mexicano 2010"]' in wkt2_compound, \
        "Expected VDATUM name to be preserved in compound WKT2"

    # Confirm CS-level LENGTHUNIT survives
    assert 'LENGTHUNIT["metre",1]' in wkt2_compound, \
        "Expected LENGTHUNIT metre to be present in compound WKT2"

    # Ensure OSR has not downgraded to unknown vertical datums (WKT1-style artifacts)
    assert 'VERT_DATUM["unknown"' not in wkt2_compound
    assert 'VDATUM["unknown"' not in wkt2_compound

    # Axis naming may be normalized, but the custom label should survive in WKT2
    assert "gravity-related height (H)" in wkt2_compound


def test_compound_manual_contains_vertical_wkt2_when_custom_crs():
    # Additional guard: for custom vertical CRS with no authority codes, the compound should
    # still be importable and exportable as valid WKT2_2019.
    horiz = osr.SpatialReference()
    assert horiz.ImportFromEPSG(6368) == 0

    vert = get_srs_from_user_input("GGM10")
    assert vert is not None and vert.IsVertical()

    compound = create_compound_srs(horiz, vert)
    wkt2 = compound.ExportToWkt(["FORMAT=WKT2_2019"])

    # Basic structure checks
    assert "COMPOUNDCRS[" in wkt2
    assert "PROJCRS[" in wkt2 or "GEOGCRS[" in wkt2
    assert "VERTCRS[" in wkt2

    # No generic/unknown vertical datum fallback in WKT2
    assert "unknown" not in wkt2.lower()