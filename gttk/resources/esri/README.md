# ESRI Projection Engine EPSG lookup

This directory contains the runtime lookup table consumed by GTTK to map ESRI Projection Engine (PE) spatial references to EPSG codes. The generator script is also included, which may be used to update it to a future ArcGIS PE version.

## Artifacts

- Generated table: [resources/esri/esri_cs_epsg_lookup.json](esri_cs_epsg_lookup.json)
- Generator script: [resources/esri/build_esri_cs_epsg_lookup.py](build_esri_cs_epsg_lookup.py)

## Source data

- Upstream ESRI repository: [https://github.com/Esri/projection-engine-db-doc](https://github.com/Esri/projection-engine-db-doc)
- PE factory objects in JSON format:
  - Projected CRS: [json/pe_list_projcs.json](https://github.com/Esri/projection-engine-db-doc/blob/main/json/pe_list_projcs.json)
  - Geographic CRS: [json/pe_list_geogcs.json](https://github.com/Esri/projection-engine-db-doc/blob/main/json/pe_list_geogcs.json)
  - Vertical CRS: [json/pe_list_vertjcs.json](https://github.com/Esri/projection-engine-db-doc/blob/main/json/pe_list_vertcs.json).

## Regenerating the lookup table

The script is designed to be safe by default. It relies on a local cache of the source JSON files to avoid accidental data loss if the upstream repository is unavailable.

- **To run from cache**:

  ```powershell
  python resources/esri/build_esri_cs_epsg_lookup.py
  ```
  
  This will use the cached JSON files in the `resources/esri/cache/` directory.

- **To force a fresh download**:

  ```powershell
  python resources/esri/build_esri_cs_epsg_lookup.py --force-online
  ```

  This will fetch the latest data from the Esri repository, update the local cache, and then regenerate the JSON lookup.

## Notes

- The generator is a maintenance/internal script, intentionally kept outside [tools/](tools/) to avoid confusion with user-facing commands.
- If the upstream Esri JSON schema changes, update both the generator and the runtime reader.
