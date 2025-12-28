#!/usr/bin/env python3
"""
Test EPSG:4979 recognition in ArcGIS Pro's GDAL.
Run this from ArcGIS Pro's Python environment.
"""
import os
import sys

def test_epsg_recognition():
    """Test if GDAL can recognize EPSG:4979."""
    print("=" * 70)
    print("DIAGNOSTIC 4: Test EPSG:4979 Recognition")
    print("=" * 70)
    
    try:
        from osgeo import osr
    except ImportError as e:
        print(f"\n[ERROR] ERROR: Cannot import osgeo.osr: {e}")
        return False
    
    # Test EPSG codes
    test_codes = [
        (4326, "WGS 84 2D", "Should work - common 2D CRS"),
        (4979, "WGS 84 3D", "PROBLEMATIC - 3D geographic CRS"),
        (3857, "Web Mercator", "Should work - common projected CRS"),
        (4936, "ETRS89 3D", "Likely to fail - another 3D CRS"),
    ]
    
    results = []
    
    for code, name, note in test_codes:
        print(f"\n[TEST] EPSG:{code} - {name}")
        print(f"       ({note})")
        print("-" * 70)
        
        srs = osr.SpatialReference()
        result = srs.ImportFromEPSG(code)
        
        if result == 0:  # Success
            print(f"[OK] SUCCESS: ImportFromEPSG({code}) returned 0")
            print(f"  Authority: {srs.GetAuthorityName(None)}")
            print(f"  Code: {srs.GetAuthorityCode(None)}")
            print(f"  Name: {srs.GetAttrValue('GEOGCS') or srs.GetAttrValue('PROJCS')}")
            
            # Validate the SRS
            validation = srs.Validate()
            print(f"  Validation: {'OK' if validation == 0 else f'FAILED (code {validation})'}")
            
            results.append((code, True, "Recognized"))
        else:
            print(f"[ERROR] FAILURE: ImportFromEPSG({code}) returned {result}")
            print(f"  GDAL could not recognize this EPSG code")
            results.append((code, False, f"Error code {result}"))
    
    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    success_count = sum(1 for _, success, _ in results if success)
    print(f"\nPassed: {success_count}/{len(test_codes)}")
    
    for code, success, message in results:
        status = "[OK]" if success else "[ERROR]"
        print(f"  {status} EPSG:{code}: {message}")
    
    # Diagnosis
    print("\n" + "=" * 70)
    print("DIAGNOSIS")
    print("=" * 70)
    
    if results[1][1]:  # EPSG:4979 succeeded
        print("\n[OK] EPSG:4979 is recognized!")
        print("  Your ArcGIS Pro GDAL is working correctly.")
        print("  The issue may be specific to certain files or operations.")
    else:
        print("\n[ERROR] EPSG:4979 is NOT recognized!")
        print("  This confirms the bug:")
        print("  - ArcGIS Pro's GDAL cannot import modern 3D geographic CRS")
        print("  - Likely cause: PROJ_LIB not set or proj.db not accessible")
        print("\n  Next step: Run script 05 to test PROJ_LIB override")
    
    return results

def main():
    results = test_epsg_recognition()
    
    if not results:
        sys.exit(1)
    
    # Exit with error if EPSG:4979 failed
    epsg_4979_success = results[1][1] if len(results) > 1 else False
    sys.exit(0 if epsg_4979_success else 1)

if __name__ == "__main__":
    main()
