# ArcGIS Pro PROJ/GDAL Diagnostic Suite

## Overview

This diagnostic suite investigates why ArcGIS Pro's GDAL fails to recognize EPSG:4979 and other modern CRS codes despite having proj.db in its installation.

## Files Created

### Documentation
- **[`arcgis_proj_diagnosis.md`](arcgis_proj_diagnosis.md)** - Comprehensive investigation plan with decision matrix
- **[`diagnostic_scripts_guide.md`](diagnostic_scripts_guide.md)** - Full guide with embedded scripts
- **[`DIAGNOSIS_SUMMARY.md`](DIAGNOSIS_SUMMARY.md)** - Quick summary and next steps

### Executable Scripts (Run in Order)
1. **[`01_find_proj_db.py`](01_find_proj_db.py)** - Locate proj.db files
2. **[`02_query_proj_db.py`](02_query_proj_db.py)** - Query database for EPSG codes
3. **[`03_check_environment.py`](03_check_environment.py)** - Check environment variables
4. **[`04_test_epsg_recognition.py`](04_test_epsg_recognition.py)** - Test EPSG:4979 recognition
5. **[`05_test_proj_lib_override.py`](05_test_proj_lib_override.py)** - **CRITICAL TEST** - Test PROJ_LIB fix
6. **[`06_compare_databases.py`](06_compare_databases.py)** - Compare database contents

## Quick Start

### 1. Open ArcGIS Pro Python Command Prompt
Start Menu → ArcGIS → Python Command Prompt

### 2. Navigate to This Directory
```powershell
cd c:\code\GeoTiffToolKit\plans
```

### 3. Run Diagnostics
```powershell
# Run all scripts and save output
python 01_find_proj_db.py > results_01.txt
python 02_query_proj_db.py > results_02.txt
python 03_check_environment.py > results_03.txt
python 04_test_epsg_recognition.py > results_04.txt

# IMPORTANT: Start a fresh Python session for script 05
exit
# Then reopen Python Command Prompt and run:
cd c:\code\GeoTiffToolKit\plans
python 05_test_proj_lib_override.py > results_05.txt

python 06_compare_databases.py > results_06.txt
```

### 4. Combine Results
```powershell
# Create a single comprehensive report
type results_*.txt > arcgis_proj_diagnosis_results.txt
```

## Expected Outcome

**Most Likely Result**: Script 05 will show that setting `PROJ_LIB` **fixes** the issue.

This confirms:
- ✓ proj.db exists and contains EPSG:4979
- ✓ GDAL is properly compiled
- ✗ **PROJ_LIB is not set in ArcGIS Pro's Python environment**

**Root Cause**: Configuration problem (easy to fix)

**Recommendation**: Esri should set `PROJ_LIB` in their Python environment startup scripts.

## Decision Matrix

| Scripts 2, 4, 5 Results | Root Cause | Severity | Fix |
|------------------------|------------|----------|-----|
| ✓ ✗ ✓ | **PROJ_LIB not set** | **Medium** | **Add env var** |
| ✗ ✗ N/A | Missing CRS in database | High | Update proj.db |
| ✓ ✗ ✗ | GDAL compilation issue | High | Recompile GDAL |
| ✓ ✓ N/A | File-specific bug | Low | Further investigation |

## Key Script: 05_test_proj_lib_override.py

This is the **critical diagnostic** that determines whether:
- **PASS** → Simple config fix (Esri just needs to set an environment variable)
- **FAIL** → Complex issue requiring GDAL recompilation or deeper investigation

## After Running Diagnostics

1. **Review** [`arcgis_proj_diagnosis_results.txt`](arcgis_proj_diagnosis_results.txt) (will be created)
2. **Determine root cause** using decision matrix in [`arcgis_proj_diagnosis.md`](arcgis_proj_diagnosis.md#decision-matrix)
3. **Prepare GitHub issue** using appropriate template from [`diagnostic_scripts_guide.md`](diagnostic_scripts_guide.md#bug-report-templates)
4. **Attach evidence** - Include all `results_*.txt` files

## Why This Matters

Your existing [`arcgis_proj_config.py`](../gttk/utils/arcgis_proj_config.py) workaround proves this is solvable. These diagnostics provide:
- Concrete evidence for your bug report
- Clear recommendation for Esri developers
- Proof that your workaround is correct
- Severity assessment to help Esri prioritize

## Support

For questions or issues with the diagnostics:
- See detailed explanation in [`arcgis_proj_diagnosis.md`](arcgis_proj_diagnosis.md)
- Review embedded scripts in [`diagnostic_scripts_guide.md`](diagnostic_scripts_guide.md)
- Check summary in [`DIAGNOSIS_SUMMARY.md`](DIAGNOSIS_SUMMARY.md)
