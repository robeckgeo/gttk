# Compression Efficiency Calculation - Implementation Plan

## Executive Summary

Refine [`calculate_compression_efficiency()`](gttk/utils/geotiff_processor.py:801) to provide accurate estimates without generating temporary baseline files by properly accounting for fixed overhead components (masks, headers) that remain constant regardless of compression algorithm choice.

## Problem Analysis

### Current State

[`calculate_compression_efficiency()`](gttk/utils/geotiff_processor.py:801) significantly **overestimates** compression efficiency:

- **User Report**: 50.39% (estimated) vs. 47.20% (actual)
- **Reproduction**: 3.67% (estimated) vs. 0.00% (actual)

### Root Causes

1. **Mask Compression Inflation**
   - GDAL **always** compresses transparency masks (IFD 1) using DEFLATE, even with `COMPRESSION=NONE`
   - Current calculation includes mask's raw uncompressed size (~125KB for 1000×1000 1-bit mask)
   - But the "baseline" file actually contains the mask **compressed** (~2-3KB)
   - Result: Theoretical uncompressed size is artificially inflated

2. **Header/Metadata Overhead**
   - Current calculation only sums pixel data sizes
   - Ignores TIFF/IFD headers, tag directories, GeoKeys, XML/JSON metadata
   - These components exist in both compressed and uncompressed files
   - Should be treated as **invariant overhead** not affected by compression algorithm

### Formula Issue

```text
Current: Efficiency = (1 - CompressedFile / TheoreticalUncompressed) × 100
where:
  TheoreticalUncompressed = Sum(RawPixelData) for ALL IFDs
  CompressedFile = Actual file size
```

**Problem**: `TheoreticalUncompressed` excludes overhead but `CompressedFile` includes it.

## Proposed Solution: Refined Estimation Algorithm

### Approach A: Improved Estimation (DEFAULT)

Calculate efficiency by properly accounting for invariant overhead components.

#### Conceptual Model

```text
FileSize = CompressibleData + InvariantOverhead

where:
  CompressibleData = Pixel data that varies with compression choice
  InvariantOverhead = Components unchanged by compression algorithm:
    - IFD headers (all IFDs)
    - TIFF file headers
    - Tag directories and GeoKeys
    - Transparency mask (always DEFLATE-compressed)
    - Metadata (XML/JSON/PAM)
```

#### Calculation Steps

**Step 1: Identify Invariant Overhead**

For each IFD:

```python
# Check if this is a transparency mask (1-bit, photometric=4)
is_mask = (bits_per_pixel == 1 and photometric == 4)

if is_mask:
    # Mask is ALWAYS compressed with DEFLATE - treat as overhead
    mask_overhead += actual_compressed_byte_count
    # DO NOT include mask in theoretical uncompressed calculation
else:
    # This is compressible image data
    theoretical_uncompressed += width × height × bits_per_pixel / 8
    actual_compressed += actual_compressed_byte_count
```

**Step 2: Estimate IFD Header Sizes**

Current approach mixes headers with pixel data. Need to separate:

```python
# For each IFD:
ifd_header_size = (
    actual_file_offset_of_next_ifd 
    - actual_file_offset_of_this_ifd 
    - sum_of_strip_or_tile_byte_counts
)

total_overhead += ifd_header_size
```

This captures:

- IFD tag entries (each ~12 bytes × number of tags)
- Tag value data (strings, arrays stored outside IFD structure)
- Strip/Tile offset arrays
- GeoKey directory structures

**Step 3: Estimate File-Level Headers**

```python
# TIFF file header (8 bytes for classic TIFF, 16 for BigTIFF)
file_header_size = 8 or 16

# First IFD starts after file header
# Can detect BigTIFF by reading first bytes of file
total_overhead += file_header_size
```

**Step 4: Calculate Adjusted Efficiency**

```python
# Invariant overhead (appears in all compression scenarios)
total_overhead = (
    file_header_size +
    sum(ifd_header_sizes) +
    mask_compressed_size
)

# Compressible data
compressible_uncompressed = theoretical_uncompressed  # Excludes masks
compressible_compressed = actual_compressed  # Excludes masks

# Efficiency calculation (comparing only compressible portions)
efficiency = (1 - (compressible_compressed / compressible_uncompressed)) × 100
```

**Key Insight**: Overhead is "constant noise" across compression scenarios. Exclude it from both numerator and denominator to get true compression efficiency.

### Approach B: Baseline File Generation (OPTIONAL)

Keep as an **optional** feature for maximum accuracy. Given the I/O cost and API complexity, a `--generate-baseline` flag is not planned for `gttk optimize` or `gttk compare`, although it remains an option if there is demand. When running `gttk test`, a baseline is *always* generated and that baseline size is used for all "space savings" calculations.

#### When to Use

- Developer testing
- High-accuracy requirements
- One-time analysis where speed is not critical

#### Implementation Strategy

```python
def calculate_compression_efficiency_with_baseline(
    filepath: str,
    generate_baseline: bool = False,
    baseline_file: Optional[str] = None
) -> float:
    """
    Calculate compression efficiency.
    
    Args:
        filepath: Compressed file to analyze
        generate_baseline: If True, generate temp baseline file
        baseline_file: Pre-existing baseline file (optimization)
    
    Returns:
        Compression efficiency percentage
    """
    if generate_baseline or baseline_file:
        # Use baseline file approach (100% accurate)
        if not baseline_file:
            baseline_file = _generate_temp_baseline(filepath)
            cleanup_baseline = True
        else:
            cleanup_baseline = False
        
        baseline_size = Path(baseline_file).stat().st_size
        compressed_size = Path(filepath).stat().st_size
        efficiency = (1 - compressed_size / baseline_size) × 100
        
        if cleanup_baseline:
            Path(baseline_file).unlink()
        
        return efficiency
    else:
        # Use refined estimation approach (fast)
        return _calculate_efficiency_refined_estimation(filepath)
```

#### Integration with `gttk optimize`

Smart baseline reuse to minimize temp file generation:

```python
# In optimize_compression workflow:
if needs_compression_efficiency:
    if input_is_uncompressed:
        # Input IS the baseline - zero temp files needed
        baseline_file = input_path
        efficiency = calculate_efficiency_with_baseline(
            output_path, 
            baseline_file=baseline_file
        )
    elif output_is_uncompressed:
        # Output IS the baseline (reverse calculation)
        baseline_file = output_path
        efficiency = calculate_efficiency_with_baseline(
            input_path,
            baseline_file=baseline_file
        )
    else:
        # Both compressed - need ONE temp baseline
        baseline_file = None  # Will generate
        efficiency = calculate_efficiency_with_baseline(
            output_path,
            generate_baseline=True
        )
```

#### Integration with `gttk compare`

When comparing two compressed files:

```python
# compare_compression workflow:
if both_files_compressed:
    # SAFETY CHECK: Verify files are comparable
    if not _files_have_matching_structure(file1, file2):
        # Files have different dimensions/bands - cannot share baseline
        # Fall back to separate calculations using refined estimation
        efficiency1 = calculate_compression_efficiency(file1)
        efficiency2 = calculate_compression_efficiency(file2)
    else:
        # Files match - can share a single baseline (if using baseline generation)
        baseline_temp = generate_baseline_from(file1 or file2)
        
        efficiency1 = calc_efficiency(file1, baseline_file=baseline_temp)
        efficiency2 = calc_efficiency(file2, baseline_file=baseline_temp)
        
        cleanup(baseline_temp)

def _files_have_matching_structure(file1: str, file2: str) -> bool:
    """
    Verify two files have matching structure for shared baseline.
    
    Checks:
    - Image dimensions (width, height)
    - Band count and data types
    - Bit depth
    - Presence/absence of transparency mask
    """
    ds1 = gdal.Open(file1, gdal.GA_ReadOnly)
    ds2 = gdal.Open(file2, gdal.GA_ReadOnly)
    
    if not ds1 or not ds2:
        return False
    
    try:
        # Dimensions
        if ds1.RasterXSize != ds2.RasterXSize or ds1.RasterYSize != ds2.RasterYSize:
            return False
        
        # Band count
        if ds1.RasterCount != ds2.RasterCount:
            return False
        
        # Data types for all bands
        for i in range(1, ds1.RasterCount + 1):
            band1 = ds1.GetRasterBand(i)
            band2 = ds2.GetRasterBand(i)
            if band1.DataType != band2.DataType:
                return False
        
        # Mask presence (check IFD count via tifffile)
        with tifffile.TiffFile(file1) as tif1, tifffile.TiffFile(file2) as tif2:
            if len(tif1.pages) != len(tif2.pages):
                return False
        
        return True
    finally:
        ds1 = None
        ds2 = None
```

**Result**: Maximum 1 temp file for compare (only when safe), 0-1 for optimize.

**Note**: In practice, `gttk compare` will primarily use **refined estimation** (fast, no temp files), with baseline generation reserved as a dev-only option for validation.

## Implementation Plan

### Phase 1: Refine Estimation Algorithm

**Goal**: Improve accuracy of fast estimation method

**Tasks**:

1. **Identify Mask IFDs** (Priority: HIGH)

   ```python
   def _is_transparency_mask_ifd(tags: Dict[int, Tag]) -> bool:
       """Detect if IFD is a transparency mask."""
       photometric = tags.get(262)  # Photometric Interpretation
       bits_per_sample = tags.get(258)  # BitsPerSample
       subfile_type = tags.get(254)  # NewSubfileType
       
       # Mask: 1-bit, photometric=4 (transparency mask)
       is_mask = (
           photometric and photometric.value == 4 and
           bits_per_sample and bits_per_sample.value == 1
       )
       
       return is_mask
   ```

2. **Calculate IFD Header Sizes** (Priority: HIGH)

   ```python
   def _estimate_ifd_header_size(
       page_index: int,
       tiff_file: tifffile.TiffFile
   ) -> int:
       """
       Estimate IFD header size by analyzing TIFF structure.
       
       Includes:
       - IFD directory entries
       - Tag value data stored outside IFD
       - Offset/byte count arrays
       - GeoKey structures
       """
       # Access raw TIFF structure
       page = tiff_file.pages[page_index]
       
       # IFD directory: 2 bytes (entry count) + 
       #                 12 bytes per tag + 
       #                 4/8 bytes (next IFD offset)
       num_tags = len(page.tags)
       ifd_dir_size = 2 + (12 * num_tags) + (8 if is_bigtiff else 4)
       
       # Tag value data: Values > 4 bytes stored separately
       tag_value_data_size = 0
       for tag in page.tags.values():
           if tag.valueoffset != tag.offset:
               # Value stored separately
               tag_value_data_size += len(tag.value_bytes)
       
       return ifd_dir_size + tag_value_data_size
   ```

3. **Refactor `calculate_compression_efficiency()`** (Priority: HIGH)

    Update function to separate overhead from compressible data:

   ```python
   def calculate_compression_efficiency(
       filepath: str,
       tiff: Optional[tifffile.TiffFile] = None,
       debug: bool = False
   ) -> float:
       """
       Calculate compression efficiency with accurate overhead accounting.
       
       Changes from current implementation:
       1. Exclude transparency masks from uncompressed calculation
       2. Track mask compressed sizes as overhead
       3. Estimate IFD header sizes as overhead
       4. Calculate efficiency on compressible data only
       """
       try:
           tiff_parser = TiffTagParser(str(filepath), tiff_file=tiff)
           
           # Accumulators
           compressible_compressed_size = 0
           compressible_uncompressed_size = 0
           overhead_size = 0
           
           # File header overhead
           is_bigtiff = tiff_parser.tif.is_bigtiff
           overhead_size += 16 if is_bigtiff else 8
           
           for page_index in range(len(tiff_parser.tif.pages)):
               tags_list = tiff_parser.get_tags(page_index=page_index)
               if not tags_list:
                   continue
               tags = {tag.code: tag for tag in tags_list}
               
               # Get IFD properties
               width = tags.get(256).value if tags.get(256) else None
               height = tags.get(257).value if tags.get(257) else None
               
               if not width or not height:
                   continue
               
               # Check if this is a transparency mask
               is_mask = _is_transparency_mask_ifd(tags)
               
               # Get actual byte counts
               byte_counts = _get_byte_counts(tags, page_index, tiff_parser)
               if not byte_counts:
                   continue
               
               actual_bytes = sum(byte_counts) if isinstance(byte_counts, list) else byte_counts
               
               if is_mask:
                   # Mask is invariant overhead (always DEFLATE compressed)
                   overhead_size += actual_bytes
                   if debug:
                       logger.debug(f"  IFD {page_index} (Mask): {actual_bytes:,} bytes → overhead")
               else:
                   # Compressible image data
                   bits_per_pixel = _calculate_bits_per_pixel(tags)
                   theoretical_size = width * height * bits_per_pixel / 8
                   
                   compressible_compressed_size += actual_bytes
                   compressible_uncompressed_size += theoretical_size
                   
                   if debug:
                       logger.debug(
                           f"  IFD {page_index} (Image): "
                           f"{actual_bytes:,} compressed / "
                           f"{theoretical_size:,} uncompressed"
                       )
               
               # Add IFD header size to overhead
               header_size = _estimate_ifd_header_size(page_index, tiff_parser.tif)
               overhead_size += header_size
               if debug:
                   logger.debug(f"    IFD {page_index} header: {header_size:,} bytes → overhead")
           
           tiff_parser.close()
           
           # Calculate efficiency on compressible data only
           if compressible_uncompressed_size > 0:
               efficiency = (
                   1 - (compressible_compressed_size / compressible_uncompressed_size)
               ) * 100
               
               if debug:
                   logger.debug(f"\n  Summary:")
                   logger.debug(f"    Compressible data: {compressible_compressed_size:,} / "
                              f"{compressible_uncompressed_size:,} bytes")
                   logger.debug(f"    Overhead (invariant): {overhead_size:,} bytes")
                   logger.debug(f"    Efficiency: {efficiency:.2f}%")
               
               return max(0.0, efficiency)  # Clamp to 0% minimum
           else:
               return 0.0
               
       except Exception as e:
           if debug:
               logger.debug(f"Error calculating efficiency: {e}")
           return 0.0
   ```

4. **Add Unit Tests** (Priority: MEDIUM)

   Test cases:
   - File with transparency mask
   - File without mask
   - Multi-IFD files (with overviews)
   - Different compression algorithms
   - Comparison against baseline-generated files

### Phase 2: Add Baseline Generation Option

**Goal**: Provide optional baseline generation for maximum accuracy

**Tasks**:

1. **Add `generate_baseline` parameter** (Priority: MEDIUM)

   ```python
   def calculate_compression_efficiency(
       filepath: str,
       tiff: Optional[tifffile.TiffFile] = None,
       debug: bool = False,
       generate_baseline: bool = False  # NEW
   ) -> float:
   ```

2. **Implement baseline file generation** (Priority: MEDIUM)

   ```python
   def _generate_temp_baseline(source_file: str) -> str:
       """Generate temporary uncompressed baseline file."""
       import tempfile
       from gttk.tools.optimize_compression import optimize_compression
       from gttk.utils.script_arguments import OptimizeArguments
       
       temp_dir = Path(tempfile.mkdtemp(prefix="gttk_baseline_"))
       baseline_path = temp_dir / "baseline_uncompressed.tif"
       
       args = OptimizeArguments(
           input_path=Path(source_file),
           output_path=baseline_path,
           algorithm='NONE',
           cog=False,
           overviews=False,
           # ... other required args
       )
       
       optimize_compression(args)
       
       return str(baseline_path)
   ```

3. **Update `compare_compression.py`** (Priority: LOW)

   Add option to use baseline generation for comparison reports:

   ```python
   # In CompareArguments:
   use_baseline_generation: bool = False  # CLI flag
   ```

4. **Update `optimize_compression.py`** (Priority: LOW)

   Smart baseline reuse when calculating efficiency in reports.

### Phase 3: Documentation and Testing

**Tasks**:

1. **Update docstrings** (Priority: HIGH)
2. **Add user documentation** (Priority: MEDIUM)
   - Explain improved accuracy
   - Document `--generate-baseline` flag
3. **Performance benchmarking** (Priority: MEDIUM)
   - Compare estimation vs. baseline generation speeds
   - Accuracy comparison
4. **Integration testing** (Priority: HIGH)
   - Test with `gttk optimize`
   - Test with `gttk compare`

## Trade-offs Analysis

| Aspect | Refined Estimation | Baseline Generation |
| ------ | ------------------ | ------------------- |
| **Accuracy** | ~98% (good enough for most cases) | 100% (perfect) |
| **Speed** | Instant (<1ms) | Slow (requires file write) |
| **Disk I/O** | Read-only | Read + Write + Delete |
| **Disk Space** | None | Temporary file size |
| **Complexity** | Moderate (IFD parsing) | Simple (file size comparison) |
| **Dependencies** | tifffile library | optimize_compression script |

## Recommendations

### Primary Strategy: Refined Estimation (Phase 1)

**Rationale**:

- Fast and requires no disk I/O
- Addresses the core issue (mask inflation, header overhead)
- Provides "good enough" accuracy for typical use cases
- No breaking changes to existing workflows

**Expected Accuracy Improvement**:

- Current: 50.49% estimated vs. 47.20% actual = 7% error
- Improved: 48-49% estimated vs. 47.20% actual = <2% error

### Secondary Strategy: Optional Baseline (Phase 2)

**Use Cases**:

- Research/scientific applications requiring exact measurements
- Validation/verification of estimation algorithm
- User explicitly requests maximum accuracy

**Implementation**:

- Default: OFF (use fast estimation)
- When enabled: Use baseline generation
- Maybe: Add `--generate-baseline` flag to CLI commands in the future?

### Smart Defaults

```python
# Pseudocode for decision logic
if user_requests_baseline:
    use_baseline_generation = True
elif file_is_already_uncompressed(input_file):
    # Input is baseline - zero overhead
    use_baseline_generation = True
    baseline_file = input_file
elif file_is_already_uncompressed(output_file):
    # Output is baseline - zero overhead  
    use_baseline_generation = True
    baseline_file = output_file
else:
    # Use fast estimation (no temp files)
    use_baseline_generation = False
```

## Migration Strategy

### Backward Compatibility

Current function signature:

```python
def calculate_compression_efficiency(
    filepath: str,
    tiff: Optional[tifffile.TiffFile] = None,
    debug: bool = False
) -> float:
```

Enhanced signature (backward compatible):

```python
def calculate_compression_efficiency(
    filepath: str,
    tiff: Optional[tifffile.TiffFile] = None,
    debug: bool = False,
    generate_baseline: bool = False  # NEW, optional
) -> float:
```

**Impact**: Zero breaking changes. All existing code continues to work.

### Testing Strategy

1. **Regression Tests**: Ensure existing behavior unchanged when `generate_baseline=False`
2. **Accuracy Tests**: Compare refined estimation vs. baseline generation
3. **Integration Tests**: Test with CLI commands (`optimize`, `compare`)
4. **Performance Tests**: Measure speed impact

## Success Criteria

1. ✅ Refined estimation accuracy within ±2% of baseline generation
2. ✅ No performance degradation (estimation remains <1ms)
3. ✅ Baseline generation option available for users needing 100% accuracy
4. ✅ Zero breaking changes to existing API
5. ✅ All existing tests pass
6. ✅ New tests achieve >90% code coverage

**Date**: 2025-12-26  
**Related Files**:

- [`gttk/utils/geotiff_processor.py`](gttk/utils/geotiff_processor.py:801) - Main implementation
- [`gttk/tools/compare_compression.py`](gttk/tools/compare_compression.py) - Integration point
- [`gttk/tools/test_compression.py`](gttk/tools/test_compression.py:840) - Uses baseline generation already!
- [`plans/compression_efficiency_diagnosis.md`](plans/compression_efficiency_diagnosis.md) - Original analysis
