# TIFF Tag Lookup

This directory contains the runtime lookup table consumed by GTTK to map TIFF tag IDs to their corresponding names, descriptions, and sources. The generator script is also included, which may be used to update it by fetching the latest data from the Library of Congress.

## Artifacts

- Generated table: [resources/tiff/tiff_tag_lookup.json](tiff_tag_lookup.json)
- Generator script: [resources/tiff/build_tiff_tag_lookup.py](build_tiff_tag_lookup.py)

## Source Data

- Upstream source: [Library of Congress - TIFF Tags](https://www.loc.gov/preservation/digital/formats/content/tiff_tags.shtml)

## Regenerating the lookup table

The script is designed to be safe by default. It relies on a local cache of the source HTML to avoid accidental data loss if the upstream website is unavailable.

- **To run from cache**:

  ```powershell
  python resources/tiff/build_tiff_tag_lookup.py
  ```

  This will use the `loc_tiff_tags.shtml` file in the `resources/tiff/cache` directory.

- **To force a fresh download**:

  ```powershell
  python resources/tiff/build_tiff_tag_lookup.py --force-online
  ```
  
  This will fetch the latest data from the Library of Congress, update the local cache, and then regenerate the JSON lookup.

## Notes

- The generator is a maintenance/internal script, intentionally kept outside the user-facing `tools/` directory.
- If the upstream HTML table structure changes, the parsing logic in the generator script may need to be updated.
- Manual corrections for specific tags are applied within the script to handle errors or add tags missing from the older TIFF 6.0 source. Currently, these include:
  - Tag 700 is renamed from `XMP` in the LOC to the correct `XMLPacket`.
  - Tag 50674 (`LercParameters`) is added.
  - Tag 50909 (`GEO_METADATA`) is added.
