# Validate Metadata Tool - Implementation Plan (Final)

**Tool Name:** `gttk validate`  
**Primary Script:** `gttk/tools/validate_metadata.py`  
**Report Type:** Validation Summary  
**Plan Version:** 2.0 (Consolidated Final)  
**Status:** Architecture & Planning Complete - Ready for Implementation  
**Date:** 2026-01-03

---

## Executive Summary

The Validate Metadata tool is a critical component of the GeoTIFF ToolKit, enabling data producers and consumers to validate GeoTIFF files against specified standards, product specifications, and delivery requirements. Unlike existing tools (read, compare, optimize, test) which focus on discovery and optimization, this tool focuses on **verification and compliance**.

### Key Features

- **Product-level validation** with TOML-based rules (flexible, distributable schemas)
- **Multi-source validation** (TIFF tags including XMP/GDAL_METADATA/GEO_METADATA, GeoKeys, XML metadata, and PROJJSON string)
- **Batch processing** with selective filename filtering
- **Pass/fail reporting** with descriptive, actionable messages
- **Automated file naming** (`_PASS` or `_FAIL` suffix) for workflow integration
- **Complete audit trails** - all rules listed even when sections missing
- **Message differentiation** - wrong value vs. missing key vs. missing section

### Core Use Case

This tool enables validation workflows where:
1. **Data producers** validate products before delivery
2. **Data consumers** verify received products meet specifications
3. **Quality assurance** teams audit compliance at scale
4. **Program managers** distribute validation rules to ensure consistency

---

## Table of Contents

1. [Terminology: Product vs Program](#1-terminology-product-vs-program)
2. [Architecture Decisions](#2-architecture-decisions)
3. [CLI Arguments](#3-cli-arguments)
4. [Data Models](#4-data-models)
5. [Validation Messages](#5-validation-messages)
6. [Batch Processing with Name Filtering](#6-batch-processing-with-name-filtering)
7. [Missing Section Handling](#7-missing-section-handling)
8. [Output Directory Management](#8-output-directory-management)
9. [Technical Specifications](#9-technical-specifications)
10. [Report Structure](#10-report-structure)
11. [Example TOML Rules File](#11-example-toml-rules-file)
12. [Implementation Phases](#12-implementation-phases)
13. [Testing Strategy](#13-testing-strategy)
14. [Documentation Updates](#14-documentation-updates)
15. [Dependencies](#15-dependencies)
16. [Success Criteria](#16-success-criteria)
17. [Timeline](#17-timeline)
18. [Appendices](#appendices)

---

## 1. Terminology: Product vs Program

### 1.1 Core Concept

**Critical Distinction:** Validation rules are organized by **product**, not program.

- **Program** = Organizational entity that produces data (e.g., USGS 3DEP, ESA Copernicus, NGA DGED)
- **Product** = Specific deliverable with distinct validation requirements (e.g., GLO-30, NAIP, DGED5)

### 1.2 Rationale

**Why Product-Level Validation?**

1. **Specification Granularity**: Product specifications define deliverable requirements more precisely than program-level guidelines
2. **Different Requirements**: A single program may produce multiple products with vastly different technical requirements
3. **Industry Alignment**: Matches geospatial data delivery nomenclature and contract structures
4. **Workflow Efficiency**: Enables selective validation of mixed-product directories

### 1.3 Real-World Examples

#### Example 1: USGS 3D Elevation Program (3DEP)

**Program:** USGS 3DEP
**Products:**
- **`3DEP`** (Digital Elevation Model)
  - Bare earth elevation (technically a DTM, marketed as "DEM")
  - 32-bit float
  - single band
  - PixelIsPoint (elevation, continuous surface)
  - NAD83 UTM projections
  - 100% valid pixels (no nodata, even if GDAL_NODATA has a default value)

#### Example 2: USDA National Agriculture Imagery Program (NAIP)

**Program:** USDA FSA
**Products:**
- **`NAIP`** (4-band Orthoimagery)
  - Orthorectified submeter aerial imagery
  - 8-bit unsigned integer
  - 4 bands (R, G, B, NIR)
  - PixelIsArea (imagery, discrete pixel spectral properties)
  - NAD83 UTM projections
  - 100% valid pixels (no nodata)

#### Example 3: Copernicus Land Monitoring Service

**Program:** Copernicus
**Products:**
- **`GLO-30`** (30m global DEM) - Higher resolution
- **`GLO-90`** (90m global DEM) - Lower resolution
- Both use PixelIsPoint, EGM2008 vertical datum (EPSG:3855)

### 1.4 Implementation Impact

All variable names, arguments, and documentation use **product** terminology:

```python
# CLI Argument
validate_parser.add_argument('-p', '--product', dest='product', ...)

# Data Models
class ValidationRule:
    product: str  # e.g., '3DEP', 'GLO-30', 'DGED5', 'NAIP'

# TOML Structure
[3DEP]  # Product name as top-level key
title = "USGS 3DEP Digital Elevation Model"
...
```

---

## 2. Architecture Decisions

### 2.1 Data Model Structure

**Decision:** Use **separate classes** for rules and results to maintain clean separation of concerns.

```python
@dataclass
class ValidationRule:
    """Represents a single validation rule from TOML (immutable configuration)."""
    product: str
    section: str  # 'tag', 'geokey', 'gdal', 'geo', 'xmp', 'xml', 'projjson'
    key: str  # Generic key field (tag/geokey/name/path)
    key_type: str  # 'tag', 'geokey', 'name', 'xpath', 'jsonpath'
    description: str
    data_type: str  # 'string', 'integer', 'float', 'boolean'
    constraint: str  # 'exact', 'enum', 'regex', 'range', 'ranges', 'exists', 'forbidden'
    expected: Optional[Any] = None
    optional: bool = False
    comment: Optional[str] = None

@dataclass
class ValidationResult:
    """Represents the result of validating a single rule (runtime outcome)."""
    rule: ValidationRule
    value: Optional[Any] = None
    status: str = 'SKIP'  # 'PASS', 'FAIL', 'SKIP'
    message: str = ''
    
    @property
    def passed(self) -> bool:
        return self.status == 'PASS'
    
    @property
    def failed(self) -> bool:
        return self.status == 'FAIL'
```

**Rationale:**
- `ValidationRule` stores "what to check" (immutable, reusable across files)
- `ValidationResult` stores "what we found" (runtime validation outcome)
- Clear separation enables caching rules for batch processing
- Results reference rules without duplicating rule data

### 2.2 Identifier Field Strategy

**Decision:** Use **generic `key` field with `key_type` metadata** in the data model.

**Implementation:**
```python
# TOML uses section-specific identifiers
[[DGED5.tag]]
tag = 258  # Section-specific

[[DGED5.geokey]]
geokey = 3072  # Section-specific

# Loader converts to generic model
rule = ValidationRule(
    section='tag',
    key='258',           # Stored as string
    key_type='tag',      # Type metadata
    ...
)
```

**Rationale:**
- TOML schema remains self-documenting with section-specific fields
- Internal model is simpler with generic `key` field
- `key_type` preserves semantic meaning for rendering
- Easier to extend to new section types without model changes

### 2.3 File Organization

**Decision:** Create **separate validation modules** in `gttk/utils/validation/`

**Structure:**
```
gttk/utils/validation/
├── __init__.py
├── models.py           # ValidationRule, ValidationResult, ValidationSummary
├── loader.py           # TOML loading and parsing
├── constraints.py      # Constraint validation functions
├── validator.py        # Core validation engine
└── extractors.py       # Section-specific value extraction
```

**Rationale:**
- [`gttk/utils/data_models.py`](gttk/utils/data_models.py:1) is already 1562 lines
- Validation is a distinct domain with multiple supporting modules
- Easier to test validation logic in isolation
- Follows existing pattern (statistics calculator has separate modules)
- Can be reused by future GUI or API

### 2.4 Data Types

**Decision:** Start with **basic types only** (Phase 1), add extended types later (Phase 2+)

**Phase 1 - Basic Types:**
- `string` - any text value
- `integer` - whole numbers
- `float` - decimal numbers
- `boolean` - true/false values

**Future - Extended Types:**
- `date` - ISO 8601 dates (YYYY-MM-DD)
- `datetime` - ISO 8601 datetime (YYYY-MM-DDThh:mm:ssZ)
- `url` - Valid URLs
- `email` - Valid email addresses

**Rationale:**
- Basic types cover 95% of current use cases
- Extended types can be validated with regex initially
- Keeps initial implementation focused and testable

---

## 3. CLI Arguments

### 3.1 Command Signature

```bash
gttk validate -i INPUT -p PRODUCT [-n NAME_STRING] [-r RULES_DIR] [-s SECTIONS...]
              [-o OUTPUT_DIR] [-w WRITE_REPORTS] [-f FORMAT] [--open-report] [-v]
```

### 3.2 Complete Argument Specification

Add to [`gttk/main.py`](gttk/main.py:140-159):

```python
# --- Validate Metadata Tool ---
validate_parser = subparsers.add_parser(
    'validate',
    help='Validate GeoTIFF metadata against product-specific requirements.',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter
)
validate_parser.add_argument(
    '-i', '--input', 
    required=True, 
    type=Path, 
    dest='input_path', 
    help='Path to GeoTIFF file or directory to validate. '
         'If directory, all .tif/.tiff files will be processed (optionally filtered by --name-string).'
)
validate_parser.add_argument(
    '-p', '--product', 
    required=True, 
    type=str, 
    dest='product', 
    help='Validation product name (must match a profile in the rules file). '
         'Example: DGED5, 3DEP, NAIP, GLO-30'
)
validate_parser.add_argument(
    '-r', '--rules-dir', 
    type=Path, 
    default=Path('gttk/resources/rules'), 
    dest='rules_dir',
    help='Directory containing TOML validation rule files. '
         'Default: gttk/resources/rules'
)
validate_parser.add_argument(
    '-s', '--sections',
    type=str,
    nargs='*',
    dest='sections',
    help='Specific sections to validate (e.g., tag geokey gdal xml). '
         'If not provided, all sections with rules will be validated.'
)
validate_parser.add_argument(
    '-n', '--name-string', 
    type=str, 
    default='',
    dest='name_string',
    help='Filter files by name substring when processing directories. '
         'Only files containing this string will be validated. '
         'Example: --name-string DSM processes only files with "DSM" in the name. '
         'Only applicable when --input is a directory.'
)
validate_parser.add_argument(
    '-o', '--output-dir',
    type=Path,
    default=None,
    dest='output_dir',
    help='Parent directory for validation output folder. '
         'If not specified, creates {basename}_validation/ alongside input. '
         'Output folder contains JSON results and optional HTML/MD reports.'
)
validate_parser.add_argument(
    '-w', '--write-reports',
    type=str2bool,
    default=True,
    dest='write_reports',
    help='Write individual HTML/MD validation reports for each file. '
         'Reports include _PASS or _FAIL suffix. Default: True.'
)
validate_parser.add_argument(
    '-f', '--report-format', 
    type=str.lower, 
    default='html', 
    choices=['html', 'md'], 
    dest='report_format',
    help='Output format for validation reports (html or md).'
)
validate_parser.add_argument(
    '--open-report',
    type=str2bool,
    default=True,
    dest='open_report',
    help='Automatically open the JSON results file after generation.'
)
validate_parser.add_argument(
    '-v', '--verbose', 
    action='store_true', 
    dest='verbose',
    help='Enable verbose logging for detailed debugging information.'
)
```

### 3.3 Arguments Dataclass

Add to [`gttk/utils/script_arguments.py`](gttk/utils/script_arguments.py:214-225):

```python
@dataclass
class ValidateArguments(BaseArguments):
    """Arguments for the validate_metadata tool."""
    product: str = None
    rules_dir: Path = Path('gttk/resources/rules')
    sections: Optional[List[str]] = None
    name_string: str = ''
    output_dir: Optional[Path] = None  # None = create alongside input
    write_reports: bool = True         # Write individual HTML/MD reports
    report_format: str = 'html'

    # Computed paths (set in __post_init__)
    output_folder: Optional[Path] = field(default=None, init=False)
    json_output_path: Optional[Path] = field(default=None, init=False)
    
    def __post_init__(self):
        """Validation for validate_metadata arguments."""
        super().__post_init__()
        try:
            self._validate_arguments()
            self._setup_output_paths()
        except ValueError as e:
            self.handle_error(str(e))
    
    def _validate_arguments(self):
        """Perform validation checks."""
        if not self.input_path.exists():
            raise ValueError(f"Input path not found: {self.input_path}")
        
        # Accept both files and directories
        if self.input_path.is_file():
            # Single file mode
            if self.input_path.suffix.lower() not in ['.tif', '.tiff']:
                raise ValueError(f"Input file must be a GeoTIFF (.tif or .tiff)")
            
            # Warn if name_string provided for single file (ignored)
            if self.name_string:
                logger.warning(
                    f"--name-string '{self.name_string}' is only applicable when "
                    f"--input is a directory. Ignoring for single file validation."
                )
                
        elif self.input_path.is_dir():
            # Directory/batch mode
            geotiffs = list(self.input_path.glob('*.tif')) + list(self.input_path.glob('*.tiff'))
            
            if not geotiffs:
                raise ValueError(f"No GeoTIFF files found in directory: {self.input_path}")
            
            # Apply name filter if provided
            if self.name_string:
                filtered = [f for f in geotiffs if self.name_string in f.name]
                if not filtered:
                    raise ValueError(
                        f"No GeoTIFF files matching name string '{self.name_string}' "
                        f"found in directory: {self.input_path}"
                    )
                logger.info(
                    f"Name filter '{self.name_string}': {len(filtered)} of {len(geotiffs)} files match"
                )
        else:
            raise ValueError(f"Input path must be a file or directory: {self.input_path}")
        
        # Validate rules directory
        if not self.rules_dir.exists():
            raise ValueError(f"Rules directory not found: {self.rules_dir}")
        
        if not self.rules_dir.is_dir():
            raise ValueError(f"Rules path is not a directory: {self.rules_dir}")
        
        # Check for at least one .toml file
        toml_files = list(self.rules_dir.glob('*.toml'))
        if not toml_files:
            raise ValueError(f"No TOML rule files found in: {self.rules_dir}")
    
    def _setup_output_paths(self):
        """Setup output folder and JSON file paths."""
        from gttk.utils.validation.output import generate_output_paths

        self.output_folder, self.json_output_path = generate_output_paths(
            self.input_path,
            self.output_dir
        )

        # Create output folder
        if not self.output_folder.exists():
            self.output_folder.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created output directory: {self.output_folder}")
```

### 3.4 Argument Summary Table

| Argument | Required | Type | Validation | Default |
| -------- | -------- | ---- | ---------- | ------- |
| `--input` | Yes | Path | File or directory must exist | - |
| `--product` | Yes | str | Must match a product in TOML rules | - |
| `--rules-dir` | No | Path | Must be valid directory with .toml files | `gttk/resources/rules` |
| `--sections` | No | List[str] | Section names: tag, geokey, gdal, geo, xmp, xml, projjson | All sections |
| `--name-string` | No | str | Used only if input is directory | `''` (no filter) |
| `--output-dir` | No | Path | Parent directory for output folder | Alongside input |
| `--write-reports` | No | bool | Write individual HTML/MD reports | `True` |
| `--report-format` | No | str | `html` or `md` | `html` |
| `--open-report` | No | bool | Opens JSON results file | `True` |
| `--verbose` | No | bool | - | `False` |

---

## 4. Data Models

### 4.1 Core Models

Create [`gttk/utils/validation/models.py`](gttk/utils/validation/models.py):

```python
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum
from pathlib import Path

class ValidationStatus(Enum):
    """Validation result status."""
    PASS = 'PASS'
    FAIL = 'FAIL'
    SKIP = 'SKIP'

class ConstraintType(Enum):
    """Supported constraint types."""
    EXACT = 'exact'
    ENUM = 'enum'
    REGEX = 'regex'
    RANGE = 'range'
    RANGES = 'ranges'
    EXISTS = 'exists'
    FORBIDDEN = 'forbidden'

class SectionType(Enum):
    """Metadata section types (simplified names for readability)."""
    TAG = 'tag'
    GEOKEY = 'geokey'
    GDAL = 'gdal'
    GEO = 'geo'
    XMP = 'xmp'
    XML = 'xml'
    PROJJSON = 'projjson'

@dataclass
class ValidationRule:
    """
    Represents a single validation rule from TOML configuration.

    Attributes:
        product: Name of the validation product (e.g., 'DGED5', '3DEP', 'GLO-30')
        section: Metadata section type (e.g., 'tag', 'geokey', 'gdal', 'xml')
        key: The identifier (tag number, GeoKey ID, GDAL Metadata name, XPath, JSONPath)
        key_type: Type of key ('tag', 'geokey', 'name', 'xpath', 'jsonpath')
        description: Human-readable description of what's being validated
        data_type: Expected data type ('string', 'integer', 'float', 'boolean')
        constraint: Validation method ('exact', 'enum', 'regex', 'range', etc.)
        expected: Expected value(s) for validation (varies by constraint type)
        optional: Whether the field is optional (default: False)
        comment: Additional notes/documentation about the rule
    """
    product: str
    section: str
    key: str
    key_type: str
    description: str
    data_type: str
    constraint: str
    expected: Optional[Any] = None
    optional: bool = False
    comment: Optional[str] = None
    
    def __post_init__(self):
        """Validate rule configuration."""
        # Validate section type
        valid_sections = [s.value for s in SectionType]
        if self.section not in valid_sections:
            raise ValueError(f"Invalid section: {self.section}")
        
        # Validate constraint type
        valid_constraints = [c.value for c in ConstraintType]
        if self.constraint not in valid_constraints:
            raise ValueError(f"Invalid constraint: {self.constraint}")
        
        # Validate that expected is provided when required
        requires_expected = [
            ConstraintType.EXACT.value,
            ConstraintType.ENUM.value,
            ConstraintType.REGEX.value,
            ConstraintType.RANGE.value,
            ConstraintType.RANGES.value
        ]
        if self.constraint in requires_expected and self.expected is None:
            raise ValueError(f"Constraint '{self.constraint}' requires 'expected' value")

@dataclass
class ValidationResult:
    """
    Represents the result of validating a single rule against actual metadata.
    
    Attributes:
        rule: The ValidationRule that was evaluated
        value: The actual value retrieved from the GeoTIFF (None if not found)
        status: Validation outcome ('PASS', 'FAIL', 'SKIP')
        message: Human-readable message explaining the result
    """
    rule: ValidationRule
    value: Optional[Any] = None
    status: str = field(default=ValidationStatus.SKIP.value)
    message: str = ''
    
    def __post_init__(self):
        """Validate status value."""
        valid_statuses = [s.value for s in ValidationStatus]
        if self.status not in valid_statuses:
            raise ValueError(f"Invalid status: {self.status}")
    
    @property
    def passed(self) -> bool:
        """Check if validation passed."""
        return self.status == ValidationStatus.PASS.value
    
    @property
    def failed(self) -> bool:
        """Check if validation failed."""
        return self.status == ValidationStatus.FAIL.value
    
    @property
    def skipped(self) -> bool:
        """Check if validation was skipped."""
        return self.status == ValidationStatus.SKIP.value
    
    def get_icon(self) -> str:
        """Get status icon for display."""
        icons = {
            ValidationStatus.PASS.value: '✅',
            ValidationStatus.FAIL.value: '❌',
            ValidationStatus.SKIP.value: '⚠️'
        }
        return icons.get(self.status, '❓')

@dataclass
class ValidationSummary:
    """
    Summary statistics for a validation report.
    
    Attributes:
        product: Validation product name (e.g., 'DGED5', '3DEP', 'GLO-30')
        input_file: Name of the validated GeoTIFF file
        rules_file: Name of the TOML rules file used
        report_date: ISO 8601 date of report generation
        total_rules: Total number of rules evaluated
        passed: Number of rules that passed
        failed: Number of rules that failed
        skipped: Number of rules that were skipped
        results_by_section: Dict mapping section names to lists of ValidationResult
        report_path: Path to generated report file
    """
    product: str
    input_file: str
    rules_file: str
    report_date: str
    total_rules: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    results_by_section: Dict[str, List[ValidationResult]] = field(default_factory=dict)
    report_path: Optional[Path] = None
    
    @property
    def pass_rate(self) -> float:
        """Calculate pass rate percentage."""
        if self.total_rules == 0:
            return 0.0
        return (self.passed / self.total_rules) * 100
    
    @property
    def fail_rate(self) -> float:
        """Calculate fail rate percentage."""
        if self.total_rules == 0:
            return 0.0
        return (self.failed / self.total_rules) * 100
    
    @property
    def overall_status(self) -> str:
        """Get overall validation status."""
        if self.failed > 0:
            return 'FAIL'
        elif self.passed > 0:
            return 'PASS'
        else:
            return 'SKIP'

@dataclass
class ValidationTableData:
    """
    Presentation data for validation results table.
    
    Used by section renderers to format validation results consistently.
    
    Attributes:
        section_name: Display name for this section
        section_type: Section type identifier (e.g., 'tag')
        results: List of ValidationResult objects for this section
        icon: Icon name for the section menu
    """
    section_name: str
    section_type: str
    results: List[ValidationResult]
    icon: str = 'checkbox'
    
    @property
    def passed_count(self) -> int:
        """Count of passed validations."""
        return sum(1 for r in self.results if r.passed)
    
    @property
    def failed_count(self) -> int:
        """Count of failed validations."""
        return sum(1 for r in self.results if r.failed)
    
    @property
    def skipped_count(self) -> int:
        """Count of skipped validations."""
        return sum(1 for r in self.results if r.skipped)
```

### 4.2 JSON Output Models

The primary output is a JSON file containing comprehensive validation results. These dataclasses support JSON serialization.

```python
import json
from dataclasses import asdict

class JsonSerializable:
    """Mixin providing JSON serialization capabilities."""

    def to_dict(self) -> Dict[str, Any]:
        """Convert dataclass to dictionary, handling nested objects."""
        def serialize_value(val: Any) -> Any:
            if hasattr(val, 'to_dict'):
                return val.to_dict()
            elif isinstance(val, (list, tuple)):
                return [serialize_value(v) for v in val]
            elif isinstance(val, dict):
                return {k: serialize_value(v) for k, v in val.items()}
            elif isinstance(val, Path):
                return str(val)
            elif hasattr(val, '__dict__'):
                return asdict(val)
            else:
                return val
        return {k: serialize_value(v) for k, v in asdict(self).items()}

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)


@dataclass
class FileProperties(JsonSerializable):
    """File system properties for a validated GeoTIFF."""
    size_mb: float
    created: Optional[str] = None   # ISO 8601 datetime
    modified: Optional[str] = None  # ISO 8601 datetime


@dataclass
class FileStructure(JsonSerializable):
    """GeoTIFF structural information."""
    is_geotiff: bool
    is_bigtiff: bool
    is_cog: bool
    has_overviews: bool
    has_mask: bool
    has_alpha: bool
    has_external_xml: bool
    has_external_ovr: bool
    version: Optional[str] = None  # GeoTIFF version (e.g., "1.1")


@dataclass
class CompressionInfo(JsonSerializable):
    """Compression characteristics of the file."""
    algorithm: str                    # e.g., "DEFLATE", "LZW", "ZSTD", "NONE"
    savings: Optional[float] = None   # Compression savings (0-1)
    ratio: Optional[float] = None     # uncompressed_size / compressed_size (e.g., 2.86)


@dataclass
class GeometryInfo(JsonSerializable):
    """Spatial geometry and coordinate reference system information."""
    area_sq_km: Optional[float] = None
    hsrs_epsg: Optional[int] = None
    hsrs_name: Optional[str] = None
    vsrs_epsg: Optional[int] = None
    vsrs_name: Optional[str] = None
    horizontal_unit: Optional[str] = None
    vertical_unit: Optional[str] = None
    wgs84_coordinates: Optional[List[List[List[float]]]] = None  # GeoJSON polygon
    native_bbox: Optional[Dict[str, float]] = None  # {west, east, south, north}


@dataclass
class ValidationResultJson(JsonSerializable):
    """
    Flattened validation result for JSON output.

    Uses a flattened structure (not nested ValidationRule) for readability.
    """
    key: str                          # Tag number, GeoKey ID, metadata name, etc.
    description: str                  # Human-readable description
    constraint: str                   # exact, enum, regex, range, etc.
    expected: Optional[Any] = None    # Expected value(s)
    actual: Optional[Any] = None      # Actual value found
    status: str = 'SKIP'              # PASS, FAIL, SKIP
    message: str = ''                 # Human-readable message


@dataclass
class SectionValidation(JsonSerializable):
    """Validation results grouped by section type."""
    tag: List[ValidationResultJson] = field(default_factory=list)
    geokey: List[ValidationResultJson] = field(default_factory=list)
    gdal: List[ValidationResultJson] = field(default_factory=list)
    geo: List[ValidationResultJson] = field(default_factory=list)
    xmp: List[ValidationResultJson] = field(default_factory=list)
    xml: List[ValidationResultJson] = field(default_factory=list)
    projjson: List[ValidationResultJson] = field(default_factory=list)


@dataclass
class FileValidationResult(JsonSerializable):
    """
    Complete validation result for a single GeoTIFF file.

    This is the per-file JSON object containing all extracted
    metadata and validation results.
    """
    name: str                                        # Filename
    path: str                                        # Full path
    properties: FileProperties
    structure: FileStructure
    compression: CompressionInfo
    geometry: GeometryInfo
    statistics: List[Dict[str, Any]] = field(default_factory=list)  # StatisticsBand data
    tiling: List[Dict[str, Any]] = field(default_factory=list)      # TileInfo data
    ifd: List[Dict[str, Any]] = field(default_factory=list)         # IfdInfo data
    validation: SectionValidation = field(default_factory=SectionValidation)
    total_rules: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0

    @property
    def overall_status(self) -> str:
        """Determine overall PASS/FAIL/SKIP status."""
        if self.failed > 0:
            return 'FAIL'
        elif self.passed > 0:
            return 'PASS'
        else:
            return 'SKIP'


@dataclass
class ValidationReport(JsonSerializable):
    """
    Top-level container for validation results (JSON output).

    This is the root JSON object written to the output file,
    containing metadata about the validation run and results
    for all validated files.
    """
    product: str                                     # Product name (e.g., "GLO-30")
    rules_file: str                                  # Rules file used
    report_date: str                                 # ISO 8601 datetime
    gttk_version: str                                # GTTK version
    total_files: int = 0
    files_passed: int = 0
    files_failed: int = 0
    files_skipped: int = 0
    files: List[FileValidationResult] = field(default_factory=list)

    def save(self, output_path: Path) -> None:
        """Write report to JSON file."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(self.to_json(indent=2))
```

### 4.3 JSON Output Structure

**Output directory naming:**
```
# Single file input: /data/example.tif
/data/example_validation/
    example_validation.json      # Primary JSON output
    example_PASS.html            # Optional (if --write-reports)

# Directory input: /data/tiles/
/data/tiles_validation/
    tiles_validation.json        # Primary JSON with all files
    tile_001_PASS.html           # Optional per-file reports
    tile_002_FAIL.html
```

**JSON structure:**
```json
{
  "product": "GLO-30",
  "rules_file": "example_rules.toml",
  "report_date": "2026-01-15T10:30:00Z",
  "gttk_version": "0.9.0",
  "total_files": 2,
  "files_passed": 1,
  "files_failed": 1,
  "files": [
    {
      "name": "tile_001.tif",
      "path": "/data/tile_001.tif",
      "properties": { "size_mb": 125.5, "created": "...", "modified": "..." },
      "structure": { "is_geotiff": true, "is_bigtiff": false, "is_cog": true, ... },
      "compression": { "algorithm": "DEFLATE", "savings": 0.65, "ratio": 2.86 },
      "geometry": { "area_sq_km": 1250.5, "hsrs_epsg": 32615, "vsrs_epsg": 3855, ... },
      "statistics": [...],
      "tiling": [...],
      "ifd": [...],
      "validation": {
        "tag": [...],
        "geokey": [...],
        "gdal": [...],
        "geo": [...],
        "xmp": [...],
        "xml": [...],
        "projjson": [...]
      },
      "total_rules": 25,
      "passed": 23,
      "failed": 2,
      "skipped": 0
    }
  ]
}
```

---

## 5. Validation Messages

### 5.1 Message Format Guidelines

Messages must be:
1. **Descriptive** - Include the actual value found
2. **Specific** - Reference the key (tag/geokey/name/path) for lookup
3. **Clear** - Explain what was expected vs. what was found
4. **Actionable** - Help users understand how to fix failures
5. **Differentiated** - Distinguish between wrong value, missing key, and missing section

### 5.2 Message Types

#### Type 1: Wrong Value (Section exists, key exists, value wrong)

```python
# FAIL - Exact constraint
f"Tag {rule.key} value {value} does not match expected value {rule.expected}"
# Example: "Tag 258 value 16 does not match expected value 32"

# FAIL - Enum constraint (with interpretation values from lookup)
f"Tag {rule.key} value {value} ({value_interpretation}) is not in allowed list: {formatted_expected_with_interpretations}"
# Example: "Tag 259 value 1 (Uncompressed) is not in allowed list: [5 (LZW), 8 (DEFLATE), 50000 (ZSTD)]"

# FAIL - Enum constraint (without interpretation values)
f"Tag {rule.key} value {value} is not in allowed list: {rule.expected}"
# Example: "Tag 277 value 1 is not in allowed list: [3, 4]"

# FAIL - Regex constraint
f"Tag {rule.key} value '{value}' does not match pattern '{rule.expected}'"
# Example: "Tag 306 value '01/15/2025' does not match pattern '^\\d{4}-\\d{2}-\\d{2}'"

# FAIL - Range constraint
f"Metadata '{rule.key}' value {value} is outside range {rule.expected['min']} to {rule.expected['max']}"
# Example: "Metadata 'STATISTICS_MINIMUM' value -9999 is outside range -430.0 to 8850.0"

# FAIL - Forbidden constraint
f"Tag {rule.key} ({rule.description}) must not be present but was found with value: {value}"
# Example: "Tag 278 (RowsPerStrip) must not be present but was found with value: 1"
```

#### Type 2: Missing Key (Section exists, specific key missing)

```python
# FAIL - Required field missing (TIFF tag)
f"Tag {rule.key} ({rule.description}) is required but not present in the file"
# Example: "Tag 270 (Image Description) is required but not present in the file"

# FAIL - Required field missing (GeoKey)
f"GeoKey {rule.key} ({rule.description}) is required but not found"
# Example: "GeoKey 3072 (Projected CRS) is required but not found"

# FAIL - Required field missing (GDAL Metadata)
f"Metadata item '{rule.key}' ({rule.description}) is required but not present"
# Example: "Metadata item 'AREA_OR_POINT' (Pixel Interpretation) is required but not present"

# FAIL - Required field missing (XPath)
f"XPath '{rule.key}' is required but not present in the file"
# Example: "XPath '/mdb:MD_Metadata/mdb:contact' is required but not present in the file"

# SKIP - Optional field missing (not a failure)
f"Optional {rule.key_type} {rule.key} ({rule.description}) is not present"
# Example: "Optional tag 305 (Software) is not present"
```

#### Type 3: Missing Section (Entire section absent)

```python
# FAIL - TIFF tag section empty
f"TIFF tags are missing - file is not a TIFF"

# FAIL - GeoKey directory missing
f"GeoKeyDirectoryTag (34735) is missing - file is not a GeoTIFF"

# FAIL - PROJJSON unavailable
f"PROJJSON string could not be generated - file is not a GeoTIFF"

# FAIL - No external XML file
f"No matching external XML metadata file was found"

# FAIL - GDAL_METADATA tag absent
f"GDAL_METADATA tag (42112) is not present"

# FAIL - GEO_METADATA tag absent
f"GEO_METADATA tag (50909) is not present"

# FAIL - XMP metadata absent
f"XMLPacket tag (700) is not present"
```

#### Type 4: Pass Messages

```python
# PASS - Exact match
f"Tag {rule.key} value matches expected value: {value}"
# Example: "Tag 258 value matches expected value: 32"

# PASS - Enum (with interpretation values)
f"{rule.key_type.capitalize()} {rule.key} value {value} ({value_interpretation}) is in allowed list"
# Example: "Tag 259 value 5 (LZW) is in allowed list"

# PASS - Enum (without interpretation values)
f"{rule.key_type.capitalize()} {rule.key} value {value} is in allowed list"
# Example: "Tag 277 value 3 is in allowed list"

# PASS - Regex
f"Tag {rule.key} value '{value}' matches expected pattern"
# Example: "Tag 306 value '2025-01-15T12:30:00Z' matches expected pattern"

# PASS - Range
f"Metadata '{rule.key}' value {value} is within range {rule.expected['min']} to {rule.expected['max']}"
# Example: "Metadata 'STATISTICS_MEAN' value 127.5 is within range 0 to 255"

# PASS - Exists
f"Tag {rule.key} ({rule.description}) is present with value: {value}"
# Example: "Tag 270 (ImageDescription) is present with value: 'Sample dataset'"

# PASS - Forbidden
f"Tag {rule.key} ({rule.description}) is correctly absent"
# Example: "Tag 278 (RowsPerStrip) is correctly absent"
```

### 5.3 Message Generation Implementation

```python
def get_missing_key_message(rule: ValidationRule) -> str:
    """Generate appropriate message for missing key based on section type."""
    if rule.section in ['geo', 'xmp', 'xml']:
        # XPath-based sections
        return f"XPath '{rule.key}' is required but not present in the file"
    elif rule.section == 'projjson':
        # JSONPath-based section
        return f"JSONPath '{rule.key}' is required but not present"
    elif rule.section == 'tag':
        return f"Tag {rule.key} ({rule.description}) is required but not present in the file"
    elif rule.section == 'geokey':
        return f"GeoKey {rule.key} ({rule.description}) is required but not found"
    elif rule.section == 'gdal':
        return f"Metadata item '{rule.key}' ({rule.description}) is required but not present"
    else:
        return f"{rule.key_type.capitalize()} {rule.key} is required but not found"

def get_section_missing_message(section_type: str) -> str:
    """Get appropriate message for missing section."""
    messages = {
        'tag': 'TIFF tags are missing - file is not a TIFF',
        'geokey': 'GeoKeyDirectoryTag (34735) is missing - file is not a GeoTIFF',
        'gdal': 'GDAL_METADATA tag (42112) is not present',
        'geo': 'GEO_METADATA tag (50909) is not present',
        'xmp': 'XMLPacket tag (700) is not present',
        'xml': 'No matching external XML metadata file was found',
        'projjson': 'PROJJSON string could not be generated - file is not a GeoTIFF',
    }
    return messages.get(section_type, f'{section_type} section is not available')
```

---

## 6. Batch Processing with Name Filtering

### 6.1 Core Feature: Selective Batch Processing

**Problem:** Data deliveries often contain multiple product types in a single directory:
- Elevation DEMs and orthoimagery from various programs
- 30m and 90m resolution DEMs from Copernicus GLO-30/GLO-90
- Multispectral and panchromatic satellite imagery

**Solution:** The `--name-string` argument enables selective validation by filename substring matching.

### 6.2 Use Cases

#### Use Case 1: Mixed Product Directory

**Scenario:**
```
data/
├── tile_001_dem.tif          # 3DEP Elevation DEM
├── tile_001_ortho.tif        # NAIP Orthoimagery
├── tile_002_dem.tif
├── tile_002_ortho.tif
└── ...
```

**Solution - Run two passes with different product rules:**
```bash
# Validate only DEMs against 3DEP specification
gttk validate -i data/ -p 3DEP -n dem

# Validate only orthoimagery against NAIP specification
gttk validate -i data/ -p NAIP -n ortho
```

#### Use Case 2: Resolution-Based Product Variants

**Scenario:**
```
dems/
├── Copernicus_DSM_COG_10_N06_00_E126_00_DEM.tif
├── Copernicus_DSM_COG_10_N07_00_E126_00_DEM.tif
├── Copernicus_DSM_COG_30_N06_00_E126_00_DEM.tif
├── Copernicus_DSM_COG_30_N07_00_E126_00_DEM.tif
└── ...
```

**Solution:**
```bash
# Validate 30m products
gttk validate -i dems/ -p GLO-30 -n _10_  # '_10_' = 1.0 arc seconds (~30m)

# Validate 90m products
gttk validate -i dems/ -p GLO-90 -n _30_  # '_30_' = 3.0 arc seconds (~90m)
```

### 6.3 Implementation

```python
def get_input_files(input_path: Path, name_string: str = '') -> List[Path]:
    """
    Get list of GeoTIFF files to process, applying name filter if provided.
    
    Args:
        input_path: File or directory path
        name_string: Optional substring to filter filenames (directory mode only)
    
    Returns:
        List of Path objects for files to validate
    
    Examples:
        >>> get_input_files(Path('data/example.tif'))
        [Path('data/example.tif')]
        
        >>> get_input_files(Path('data/'), name_string='DSM')
        [Path('data/tile_001_DSM.tif'), Path('data/tile_002_DSM.tif')]
    """
    if input_path.is_file():
        return [input_path]
    
    # Collect all GeoTIFF files
    geotiffs = sorted(input_path.glob('*.tif')) + sorted(input_path.glob('*.tiff'))
    
    # Apply name filter if provided
    if name_string:
        filtered = [f for f in geotiffs if name_string in f.name]
        return filtered
    
    return geotiffs
```

### 6.4 Logging Enhancements

```python
def validate_metadata(args: ValidateArguments):
    """
    Main validation function supporting single-file and filtered batch processing.
    """
    logger = logging.getLogger(__name__)
    
    # Get list of files to process
    input_files = get_input_files(args.input_path, args.name_string)
    
    # Log processing mode
    if args.input_path.is_file():
        logger.info(f"Single file validation: {args.input_path.name}")
    else:
        total_in_dir = len(list(args.input_path.glob('*.tif')) + 
                           list(args.input_path.glob('*.tiff')))
        
        if args.name_string:
            logger.info(
                f"Batch validation with name filter '{args.name_string}': "
                f"{len(input_files)} of {total_in_dir} files in {args.input_path}"
            )
        else:
            logger.info(
                f"Batch validation: {len(input_files)} files in {args.input_path}"
            )
    
    # Load validation rules once (reuse for all files)
    logger.info(f"Loading validation rules for product '{args.product}'...")
    rules_by_section, rules_file = load_validation_rules(
        args.rules_dir, 
        args.product, 
        args.sections
    )
    
    # Process each file
    # ... (implementation continues)
```

---

## 7. Missing Section Handling

### 7.1 Core Requirement

**All rules shall be listed in the report, even if the entire section is missing from the GeoTIFF.**

**Rationale:**
- Users need to see what was checked, not just what was found
- Missing sections may indicate specification violations
- Complete audit trail for compliance documentation
- Transparency in validation process

### 7.2 Example Scenario

If TOML has rules for `xml` but no external XML file exists:

```markdown
## External XML Metadata

| Result | Description | Value | Message |
| ------ | ----------- | ----- | ------- |
| ❌ FAIL | Abstract | - | No matching external XML metadata file was found. |
| ❌ FAIL | Creation Date | - | No matching external XML metadata file was found. |
| ❌ FAIL | Access Constraints | - | No matching external XML metadata file was found. |
```

### 7.3 Implementation

```python
def validate_section(self, section_type: str, rules: List[ValidationRule]) -> List[ValidationResult]:
    """
    Validate a section's rules.
    
    Returns results for ALL rules, even if the entire section is missing.
    """
    results = []
    
    # Try to extract section content
    section_content = self.extract_section_content(section_type)
    
    if section_content is None:
        # Entire section is missing - fail all required rules with section-level message
        section_missing_msg = get_section_missing_message(section_type)
        
        for rule in rules:
            result = ValidationResult(
                rule=rule,
                value=None,
                status='FAIL' if not rule.optional else 'SKIP',
                message=section_missing_msg
            )
            results.append(result)
        
        return results
    
    # Section exists - validate each rule individually
    for rule in rules:
        result = self.validate_rule(rule, section_content)
        results.append(result)
    
    return results
```

---

## 8. Output Directory Management

### 8.1 Primary Output: JSON File

**The primary output is a single JSON file** containing validation results for all processed files. Optional HTML/MD reports can be generated with the `--write-reports` flag.

**Output folder naming:**
- Single file input (`/data/example.tif`): Creates `/data/example_validation/`
- Directory input (`/data/tiles/`): Creates `/data/tiles_validation/`
- Single file input (`/data/example.tif`) with `-o /reports/`: Creates `/reports/example_validation/`

**Rationale:**
- JSON enables programmatic processing and integration with other tools
- Single file contains all results (efficient for batch workflows)
- Optional HTML/MD reports for human review
- Clear folder structure keeps outputs organized

### 8.2 Output Path Generation

```python
def generate_output_paths(
    input_path: Path,
    output_dir: Optional[Path] = None
) -> Tuple[Path, Path]:
    """
    Generate output folder and JSON file paths.

    Args:
        input_path: Input file or directory path
        output_dir: Optional parent directory for output folder

    Returns:
        Tuple of (output_folder_path, json_file_path)

    Examples:
        >>> generate_output_paths(Path('/data/example.tif'))
        (Path('/data/example_validation'), Path('/data/example_validation/example_validation.json'))

        >>> generate_output_paths(Path('/data/tiles/'))
        (Path('/data/tiles_validation'), Path('/data/tiles_validation/tiles_validation.json'))

        >>> generate_output_paths(Path('/data/example.tif'), Path('/reports'))
        (Path('/reports/example_validation'), Path('/reports/example_validation/example_validation.json'))
    """
    # Determine basename
    if input_path.is_file():
        basename = input_path.stem
        parent = input_path.parent
    else:
        basename = input_path.name
        parent = input_path.parent

    # Determine output parent directory
    if output_dir is not None:
        parent = output_dir

    # Build paths
    folder_name = f"{basename}_validation"
    output_folder = parent / folder_name
    json_file = output_folder / f"{folder_name}.json"

    return output_folder, json_file


def generate_report_path(
    input_file: Path,
    output_folder: Path,
    overall_status: str,
    report_format: str
) -> Path:
    """
    Generate per-file report path with PASS/FAIL suffix.

    Example:
        >>> generate_report_path(Path('/data/tile_001.tif'), Path('/data/tile_001_validation'), 'FAIL', 'html')
        Path('/data/tile_01_validation/tile_001_FAIL.html')
    """
    stem = input_file.stem
    suffix = f"_{overall_status}"
    filename = f"{stem}{suffix}.{report_format}"
    return output_folder / filename
```

### 8.3 Usage Examples

```bash
# Default: JSON output alongside input file
gttk validate -i data/example.tif -p DGED5
# Creates: data/example_validation/example_validation.json
#          data/example_validation/example_PASS.html (if --write-reports)

# Custom parent directory
gttk validate -i data/example.tif -p DGED5 -o /reports
# Creates: /reports/example_validation/example_validation.json

# Batch processing
gttk validate -i data/tiles/ -p GLO-30
# Creates: data/tiles_validation/tiles_validation.json (contains all files)
#          data/tiles_validation/tile_001_PASS.html
#          data/tiles_validation/tile_002_FAIL.html

# JSON only (no HTML/MD reports)
gttk validate -i data/tiles/ -p GLO-30 -w false
# Creates: data/tiles_validation/tiles_validation.json (only)

# Open JSON results after completion
gttk validate -i data/example.tif -p DGED5 --open-report
# Opens example_validation.json in default application
```

---

## 9. Technical Specifications

### 9.1 TOML Rule Loading

**Runtime Behavior:**

1. **Discovery**: Scan `rules_dir` for all `.toml` files
2. **Loading**: Parse each TOML file using the built-in `tomlib` library (Python 3.11+)
3. **Conflict Detection**: Check for duplicate product names across files
4. **Validation**: Validate rule schema before proceeding
5. **Filtering**: Extract only rules for the requested product
6. **Section Filtering**: Apply `--sections` filter if provided

**Implementation:**

```python
def load_validation_rules(rules_dir: Path, product: str, 
                         sections: Optional[List[str]] = None) -> Tuple[Dict[str, List[ValidationRule]], str]:
    """
    Load validation rules for a specific product from TOML files.
    
    Returns:
        Tuple of:
        - Dict mapping section names to lists of ValidationRule objects
        - Name of the TOML file containing the product rules
    
    Raises:
        ValueError: If product not found or duplicate products detected
    """
    import tomllib
    
    # 1. Find all TOML files
    toml_files = list(rules_dir.glob('*.toml'))
    logger.debug(f"Found {len(toml_files)} TOML files in {rules_dir}")
    
    # 2. Load and parse all files
    all_products = {}
    product_sources = {}  # Track which file each product came from
    
    for toml_file in toml_files:
        with open(toml_file, 'rb') as f:
            data = tomllib.load(f)
        
        # Check each top-level key (product name)
        for prod_name in data.keys():
            if prod_name in all_products:
                # Conflict detected!
                raise ValueError(
                    f"Product '{prod_name}' found in multiple files:\n"
                    f"  - {product_sources[prod_name]}\n"
                    f"  - {toml_file.name}\n"
                    f"Please consolidate rules into a single file."
                )
            all_products[prod_name] = data[prod_name]
            product_sources[prod_name] = toml_file.name
    
    # 3. Check if requested product exists
    if product not in all_products:
        available = ', '.join(sorted(all_products.keys()))
        raise ValueError(
            f"Product '{product}' not found in rules directory.\n"
            f"Available products: {available}"
        )
    
    # 4. Parse rules for the requested product
    product_data = all_products[product]
    rules_by_section = {}
    
    for section_name in ['tag', 'geokey', 'gdal', 'geo', 'xmp', 'xml', 'projjson']:
        
        if section_name not in product_data:
            continue
        
        # Apply section filter if provided
        if sections and section_name not in sections:
            continue
        
        # Parse each rule in this section
        section_rules = []
        for rule_dict in product_data[section_name]:
            rule = parse_rule(product, section_name, rule_dict)
            section_rules.append(rule)
        
        if section_rules:
            rules_by_section[section_name] = section_rules
    
    # 5. Log summary
    logger.info(f"Loaded rules for product '{product}' from {product_sources[product]}")
    for section, rules in rules_by_section.items():
        logger.info(f"  - {section}: {len(rules)} rules")
    
    return rules_by_section, product_sources[product]

def parse_rule(product: str, section: str, rule_dict: dict) -> ValidationRule:
    """
    Parse a rule dictionary from TOML into ValidationRule object.

    Args:
        product: Product name
        section: Section type (e.g., 'tag', 'geokey', 'gdal')
        rule_dict: Raw dictionary from TOML

    Returns:
        ValidationRule object
    """
    # Determine key and key_type from section-specific field
    key_field_map = {
        'tag': 'Tag',
        'geokey': 'GeoKey',
        'gdal': 'Name',
        'geo': 'XPath',
        'xmp': 'XPath',
        'xml': 'XPath',
        'projjson': 'JSONPath'
    }
    
    key_field = key_field_map[section]
    key_value = str(rule_dict[key_field])  # Convert to string for consistency
    
    return ValidationRule(
        product=product,
        section=section,
        key=key_value,
        key_type=key_field,
        description=rule_dict['description'],
        data_type=rule_dict['data_type'],
        constraint=rule_dict['constraint'],
        expected=rule_dict.get('expected'),
        optional=rule_dict.get('optional', False),
        comment=rule_dict.get('comment')
    )
```

### 9.2 Value Extraction Strategy

Create [`gttk/utils/validation/extractors.py`](gttk/utils/validation/extractors.py):

```python
class ValueExtractor:
    """Extract values from GeoTIFF for validation."""

    def __init__(self, extractor: MetadataExtractor):
        self.extractor = extractor

    def extract_tag(self, key: str) -> Optional[Any]:
        """Extract TIFF tag value by tag number."""
        tags = self.extractor.extract_tags(page=0, scope='complete')
        tag_num = int(key)
        for tag in tags:
            if tag.code == tag_num:
                return tag.value
        return None

    def extract_geokey(self, key: str) -> Optional[Any]:
        """Extract GeoKey value by GeoKey ID."""
        geokeys = self.extractor.extract_geokeys()
        geokey_id = int(key)
        for geokey in geokeys:
            if geokey.id == geokey_id:
                return geokey.value
        return None

    def extract_gdal(self, key: str) -> Optional[Any]:
        """Extract GDAL metadata item by name."""
        gdal_md = self.extractor.extract_gdal_metadata()
        if not gdal_md or not gdal_md.has_content():
            return None

        # Parse XML to extract specific item
        import lxml.etree as etree
        root = etree.fromstring(gdal_md.content.encode('utf-8'))
        items = root.xpath(f".//Item[@name='{key}']")
        if items:
            return items[0].text
        return None
    
    def extract_xml_xpath(self, xpath: str, xml_content: str) -> Optional[Any]:
        """Extract value from XML using XPath with namespace discovery."""
        import lxml.etree as etree
        root = etree.fromstring(xml_content.encode('utf-8'))
        
        # Discover namespaces from document
        namespaces = root.nsmap
        if None in namespaces:
            namespaces['default'] = namespaces.pop(None)
        
        # Evaluate XPath
        results = root.xpath(xpath, namespaces=namespaces)
        if results:
            # Return text content or attribute value
            if hasattr(results[0], 'text'):
                return results[0].text
            else:
                return results[0]
        return None
    
    def extract_projjson_path(self, jsonpath: str) -> Optional[Any]:
        """Extract value from PROJJSON using JSONPath."""
        import json
        from jsonpath_ng import parse
        
        projjson_data = self.extractor.extract_projjson_string()
        if not projjson_data or not projjson_data.has_content():
            return None
        
        # Parse JSON
        json_obj = json.loads(projjson_data.json_string)
        
        # Evaluate JSONPath
        expr = parse(jsonpath)
        matches = expr.find(json_obj)
        
        if matches:
            return matches[0].value
        return None
```

### 9.3 Constraint Validation

Create [`gttk/utils/validation/constraints.py`](gttk/utils/validation/constraints.py):

```python
import re
from typing import Any, List, Dict

def validate_exact(value: Any, expected: Any) -> bool:
    """Validate exact match."""
    return value == expected

def validate_enum(value: Any, expected: List[Any]) -> bool:
    """Validate value is in allowed list."""
    return value in expected

def validate_regex(value: Any, pattern: str) -> bool:
    """Validate value matches regex pattern."""
    if not isinstance(value, str):
        value = str(value)
    return bool(re.match(pattern, value))

def validate_range(value: Any, range_spec: Dict[str, float]) -> bool:
    """Validate value is within single range."""
    min_val = range_spec.get('min')
    max_val = range_spec.get('max')
    
    # Convert value to float for comparison
    try:
        num_value = float(value)
    except (TypeError, ValueError):
        return False
    
    if min_val is not None and num_value < min_val:
        return False
    if max_val is not None and num_value > max_val:
        return False
    
    return True

def validate_ranges(value: Any, ranges: List[Dict[str, float]]) -> bool:
    """Validate value is within at least one of multiple ranges."""
    for range_spec in ranges:
        if validate_range(value, range_spec):
            return True
    return False

def validate_exists(value: Any) -> bool:
    """Validate that value exists (is not None and not empty)."""
    if value is None:
        return False
    if isinstance(value, str) and value.strip() == '':
        return False
    return True

def validate_forbidden(value: Any) -> bool:
    """Validate that value does NOT exist."""
    return value is None
```

### 9.4 Core Validation Engine

Create [`gttk/utils/validation/validator.py`](gttk/utils/validation/validator.py):

```python
from typing import Dict, List, Any
from gttk.utils.validation.models import ValidationRule, ValidationResult
from gttk.utils.validation.extractors import ValueExtractor
from gttk.utils.validation.constraints import (
    validate_exact, validate_enum, validate_regex,
    validate_range, validate_ranges, validate_exists, validate_forbidden
)

class ValidationEngine:
    """Core validation engine that evaluates rules against GeoTIFF metadata."""
    
    def __init__(self, extractor: MetadataExtractor):
        self.extractor = extractor
        self.value_extractor = ValueExtractor(extractor)
    
    def validate_all_sections(self, rules_by_section: Dict[str, List[ValidationRule]]) -> Dict[str, List[ValidationResult]]:
        """
        Validate all sections with rules.
        
        Args:
            rules_by_section: Dict mapping section names to rule lists
        
        Returns:
            Dict mapping section names to ValidationResult lists
        """
        results_by_section = {}
        
        for section, rules in rules_by_section.items():
            section_results = self.validate_section(section, rules)
            results_by_section[section] = section_results
        
        return results_by_section
    
    def validate_section(self, section_type: str, rules: List[ValidationRule]) -> List[ValidationResult]:
        """
        Validate a section's rules.
        
        Returns results for ALL rules, even if the entire section is missing.
        """
        results = []
        
        # Try to extract section content
        section_content = self.extract_section_content(section_type)
        
        if section_content is None:
            # Entire section is missing
            from gttk.utils.validation.models import get_section_missing_message
            section_missing_msg = get_section_missing_message(section_type)
            
            for rule in rules:
                result = ValidationResult(
                    rule=rule,
                    value=None,
                    status='FAIL' if not rule.optional else 'SKIP',
                    message=section_missing_msg
                )
                results.append(result)
            
            return results
        
        # Section exists - validate each rule individually
        for rule in rules:
            result = self.validate_rule(rule, section_content)
            results.append(result)
        
        return results
    
    def extract_section_content(self, section_type: str) -> Optional[Any]:
        """
        Extract section content if available.
        
        Returns None if the entire section is missing.
        """
        if section_type == 'tag':
            tags = self.extractor.extract_tags(page=0, scope='complete')
            return tags if tags else None
        
        elif section_type == 'geokey':
            geokeys = self.extractor.extract_geokeys()
            return geokeys if geokeys else None
        
        elif section_type == 'gdal':
            gdal_md = self.extractor.extract_gdal_metadata()
            return gdal_md if gdal_md and gdal_md.has_content() else None
        
        # Additional sections handled in Phase 4-5
        return None
    
    def validate_rule(self, rule: ValidationRule, section_content: Any) -> ValidationResult:
        """
        Validate a single rule against section content.
        
        Returns ValidationResult with appropriate message based on outcome.
        """
        # Extract value for this specific rule
        value = self.extract_value(rule)
        
        # Check if key exists
        if value is None:
            # Key is missing from section
            if rule.constraint == 'forbidden':
                # Missing is good for forbidden fields!
                return ValidationResult(
                    rule=rule,
                    value=None,
                    status='PASS',
                    message=f"{rule.key_type.capitalize()} {rule.key} ({rule.description}) is correctly absent"
                )
            elif rule.optional:
                # Missing is OK for optional fields
                return ValidationResult(
                    rule=rule,
                    value=None,
                    status='SKIP',
                    message=f"Optional {rule.key_type} {rule.key} ({rule.description}) is not present"
                )
            else:
                # Missing is FAIL for required fields
                from gttk.utils.validation.models import get_missing_key_message
                return ValidationResult(
                    rule=rule,
                    value=None,
                    status='FAIL',
                    message=get_missing_key_message(rule)
                )
        
        # Key exists - validate the value
        passed, message = self.apply_constraint(value, rule)
        
        return ValidationResult(
            rule=rule,
            value=value,
            status='PASS' if passed else 'FAIL',
            message=message
        )
    
    def extract_value(self, rule: ValidationRule) -> Optional[Any]:
        """Extract value for a specific rule."""
        if rule.section == 'tag':
            return self.value_extractor.extract_tiff_tag(rule.key)
        elif rule.section == 'geokey':
            return self.value_extractor.extract_geokey(rule.key)
        elif rule.section == 'gdal':
            # Special handling for STATISTICS_* fields
            if rule.key.startswith('STATISTICS_'):
                self.ensure_statistics_current()
            return self.value_extractor.extract_gdal_metadata(rule.key)
        # Additional sections in Phase 4-5
        return None
    
    def apply_constraint(self, value: Any, rule: ValidationRule) -> Tuple[bool, str]:
        """
        Apply constraint validation and generate message.
        
        Returns:
            Tuple of (passed: bool, message: str)
        """
        constraint = rule.constraint
        
        if constraint == 'exact':
            passed = validate_exact(value, rule.expected)
            if passed:
                message = f"{rule.key_type.capitalize()} {rule.key} value matches expected value: {value}"
            else:
                message = f"{rule.key_type.capitalize()} {rule.key} value {value} does not match expected value {rule.expected}"
        
        elif constraint == 'enum':
            passed = validate_enum(value, rule.expected)
            
            # Try to get interpretation values for more informative messages
            value_with_interp = self._format_value_with_interpretation(value, rule)
            expected_with_interp = self._format_expected_enum_with_interpretations(rule.expected, rule)
            
            if passed:
                if value_with_interp != str(value):
                    # Interpretation available
                    message = f"{rule.key_type.capitalize()} {rule.key} value {value_with_interp} is in allowed list"
                else:
                    # No interpretation available
                    message = f"{rule.key_type.capitalize()} {rule.key} value {value} is in allowed list"
            else:
                if value_with_interp != str(value) or expected_with_interp != str(rule.expected):
                    # At least some interpretations available
                    message = f"{rule.key_type.capitalize()} {rule.key} value {value_with_interp} is not in allowed list: {expected_with_interp}"
                else:
                    # No interpretations available
                    message = f"{rule.key_type.capitalize()} {rule.key} value {value} is not in allowed list: {rule.expected}"
        
        elif constraint == 'regex':
            passed = validate_regex(value, rule.expected)
            if passed:
                message = f"{rule.key_type.capitalize()} {rule.key} value '{value}' matches expected pattern"
            else:
                message = f"{rule.key_type.capitalize()} {rule.key} value '{value}' does not match pattern '{rule.expected}'"
        
        elif constraint == 'range':
            passed = validate_range(value, rule.expected)
            if passed:
                message = f"Metadata '{rule.key}' value {value} is within range {rule.expected['min']} to {rule.expected['max']}"
            else:
                message = f"Metadata '{rule.key}' value {value} is outside range {rule.expected['min']} to {rule.expected['max']}"
        
        elif constraint == 'ranges':
            passed = validate_ranges(value, rule.expected)
            if passed:
                message = f"{rule.key_type.capitalize()} {rule.key} value {value} is within expected ranges"
            else:
                # Format ranges for display
                formatted_ranges = []
                for r in rule.expected:
                    formatted_ranges.append(f"{r['min']}-{r['max']}")
                message = f"{rule.key_type.capitalize()} {rule.key} value {value} is not in any of the expected ranges: [{', '.join(formatted_ranges)}]"
        
        elif constraint == 'exists':
            passed = validate_exists(value)
            if passed:
                message = f"{rule.key_type.capitalize()} {rule.key} ({rule.description}) is present with value: {value}"
            else:
                message = f"{rule.key_type.capitalize()} {rule.key} ({rule.description}) must be present but was not found"
        
        elif constraint == 'forbidden':
            passed = validate_forbidden(value)
            if passed:
                message = f"{rule.key_type.capitalize()} {rule.key} ({rule.description}) is correctly absent"
            else:
                message = f"{rule.key_type.capitalize()} {rule.key} ({rule.description}) must not be present but was found with value: {value}"
        
        else:
            passed = False
            message = f"Unknown constraint type: {constraint}"
        
        return passed, message
    
    def ensure_statistics_current(self):
        """
        Ensure statistics are current before validating STATISTICS_* metadata.
        
        Forces recomputation to ensure accuracy (stats may be stale after processing).
        """
        logger.info("Validating STATISTICS_* field - forcing statistics recomputation")
        
        from gttk.utils.statistics_calculator import StatisticsCalculator
        
        calc = StatisticsCalculator(self.extractor.gdal_ds)
        calc.compute_statistics(approx_ok=False)  # Force exact computation
        
        # Refresh extractor's cached metadata
        if hasattr(self.extractor, '_reset_cached_gdal_metadata'):
            self.extractor._reset_cached_gdal_metadata()
    
    def _format_value_with_interpretation(self, value: Any, rule: ValidationRule) -> str:
        """
        Format a value with its interpretation if available (for enum constraints).
        
        Args:
            value: The actual value
            rule: The validation rule
        
        Returns:
            Formatted string like "5 (LZW)" or just "5" if no interpretation
        
        Examples:
            For TIFF Tag 259 (Compression) value 5: returns "5 (LZW)"
            For TIFF Tag 277 (SamplesPerPixel) value 3: returns "3"
        """
        interpretation = self._get_value_interpretation(value, rule)
        if interpretation:
            return f"{value} ({interpretation})"
        return str(value)
    
    def _format_expected_enum_with_interpretations(self, expected_list: List[Any], rule: ValidationRule) -> str:
        """
        Format expected enum list with interpretations if available.
        
        Args:
            expected_list: List of expected values
            rule: The validation rule
        
        Returns:
            Formatted string like "[5 (LZW), 8 (DEFLATE), 50000 (ZSTD)]" or "[3, 4]"
        """
        formatted_values = []
        has_interpretations = False
        
        for val in expected_list:
            interp = self._get_value_interpretation(val, rule)
            if interp:
                formatted_values.append(f"{val} ({interp})")
                has_interpretations = True
            else:
                formatted_values.append(str(val))
        
        # Only use formatted version if at least one interpretation was found
        if has_interpretations:
            return f"[{', '.join(formatted_values)}]"
        else:
            return str(expected_list)
    
    def _get_value_interpretation(self, value: Any, rule: ValidationRule) -> Optional[str]:
        """
        Get the interpretation/meaning of a value for a specific rule.
        
        Args:
            value: The value to interpret
            rule: The validation rule providing context
        
        Returns:
            Interpretation string or None if not available
        
        Implementation:
            - For TIFF tags: Use TiffTagParser's lookup dictionaries
            - For GeoKeys: Use GeoKeyParser's lookup dictionaries
            - For other sections: Return None (no interpretation available)
        """
        if rule.section == 'tag':
            # Use TiffTagParser to get tag value interpretations
            from gttk.utils.tiff_tag_parser import TiffTagParser
            
            tag_num = int(rule.key)
            # TiffTagParser has lookup methods for specific tags
            # This will need to be implemented to match the existing pattern
            # Example: TiffTagParser.get_tag_value_interpretation(tag_num, value)
            return None  # Placeholder - implement during Phase 2
        
        elif rule.section == 'geokey':
            # Use GeoKeyParser to get geokey value interpretations
            from gttk.utils.geokey_parser import GeoKeyParser
            
            geokey_id = int(rule.key)
            # Similar pattern to TiffTagParser
            return None  # Placeholder - implement during Phase 2
        
        # No interpretation available for other sections
        return None
```

---

## 10. Report Structure

### 10.1 Report Header (Summary Section)

**Content:**
```markdown
# Validation Summary

**Report Date:** 2026-01-15  
**Test File:** example.tif  
**Rules File:** DGED5_rules.toml  
**Product:** DGED5  

**✅ PASSED:** 45 of 50 rules (90%)  
**❌ FAILED:** 3 of 50 rules (6%)  
**⚠️ SKIPPED:** 2 of 50 rules (4%)  
```

**Implementation Notes:**
- No anchor link in navbar (like existing summary sections)
- Not in Markdown ToC
- Always first section in report
- Status counts only shown if > 0
- Overall file status shown prominently

### 10.2 Section Tables

**Per-Section Table:**

```markdown
## TIFF Tags

| Result | Description | Value | Message |
| ------ | ----------- | ----- | ------- |
| ✅ PASS | BitsPerSample | 32 | Tag 258 value matches expected value: 32 |
| ❌ FAIL | Compression | 1 (Uncompressed) | Tag 259 value 1 (Uncompressed) is not in allowed list: [5 (LZW), 8 (DEFLATE)] |
| ✅ PASS | ImageDescription | "Sample DEM" | Tag 270 (ImageDescription) is present with value: 'Co' |
| ⚠️ SKIP | Software | - | Optional field tag 305 (Software) is not present |
```

**Column Definitions:**
1. **Result** - Icon + status text (✅ PASS, ❌ FAIL, ⚠️ SKIP)
2. **Description** - Human-readable description from rule
3. **Value** - Actual value retrieved from file (or `-` if not found)
4. **Message** - Detailed validation message

**HTML Styling:**
- `result`, `value`, and `message` cells: red text (#c00000) for FAIL, green text (#196B24) for PASS
- Description column: always black text
- Use existing CSS classes from current reports

### 10.3 Section Icons

Use these icons in the HTML navbar menu:

```python
SECTION_ICONS = {
    'tag': 'tag',        # Same as current TIFF Tags section
    'geokey': 'key',     # Same as current GeoKeys section
    'gdal': 'earth',     # Same as GDAL_METADATA section
    'geo': 'geo',        # Same as GEO_METADATA section
    'xmp': 'xmp',        # Same as XMP section
    'xml': 'xml',        # Same as XML metadata section
    'projjson': 'json',  # Same as PROJJSON section
}
```

### 10.4 Report Icons

Use the following icons:
- Report header icon: [`gttk/resources/icons/svg/favicon/validation.svg`](gttk/resources/icons/svg/favicon/validation.svg)
- Report header icon (dark mode): [`gttk/resources/icons/svg/favicon/validation_white.svg`](gttk/resources/icons/svg/favicon/validation_white.svg)

---

## 11. Example TOML Rules File

Create [`gttk/resources/rules/example_rules.toml`](gttk/resources/rules/example_rules.toml):

```toml
# ==============================================================================
# Example Validation Rules for GeoTIFF ToolKit
# ==============================================================================
# This file demonstrates the validation rule schema with product-level organization.
# Users can create their own rules files following this format.
# 
# File naming conventions:
# - example_rules.toml (this file) - tracked in Git as reference
# - *_rules.toml - ignored by Git (for custom product rules)
#
# Products can be defined across multiple files, but each product name
# must be unique across all files in the rules directory.
# ==============================================================================

# ==============================================================================
# DGED5 - Defense Gridded Elevation Data Level 5
# ==============================================================================
[DGED5]
title = "Defense Gridded Elevation Data Level 5"
description = "Validation rules for DGED5 DSM/DTM elevation products"
author = "National Geospatial-Intelligence Agency (NGA)"
updated = "2026-01-15"

# ------------------------------------------------------------------------------
# TIFF Tags (section: tag)
# ------------------------------------------------------------------------------

[[DGED5.tag]]
tag = 258
description = "BitsPerSample"
data_type = "integer"
constraint = "exact"
expected = 32
comment = "Must be 32-bit floating point"

[[DGED5.tag]]
tag = 259
description = "Compression"
data_type = "integer"
constraint = "enum"
expected = [5, 8]
comment = "Either 5=LZW (legacy) or 8=DEFLATE (new) is acceptable"

[[DGED5.tag]]
tag = 270
description = "ImageDescription"
data_type = "string"
constraint = "exists"
comment = "Description required but content not validated"

[[DGED5.tag]]
tag = 306
description = "DateTime"
data_type = "string"
constraint = "regex"
expected = "^\\d{4}:\\d{2}:\\d{2} \\d{2}:\\d{2}:\\d{2}$"
comment = "TIFF DateTime does not follow ISO 8601, only 20 chars including terminating NUL"

[[DGED5.tag]]
tag = 296
description = "ResolutionUnit"
data_type = "integer"
constraint = "forbidden"
comment = "Should not be present - only supports Inch or Centimeter for documents"

[[DGED5.tag]]
tag = 269
description = "DocumentName"
data_type = "string"
constraint = "regex"
expected = "^U_.*_20km_.*_GeoData_.*(?:DSM|DTM).*_\d{2}$"
optional = true
comment = "Optional but must match file name sans suffix if present"

# ------------------------------------------------------------------------------
# GeoKeys (section: geokey)
# ------------------------------------------------------------------------------

[[DGED5.geokey]]
geokey = 1024
description = "GTModelTypeGeoKey"
data_type = "integer"
constraint = "exact"
expected = 1
comment = "1 = ModelTypeProjected (UTM or UPS)"

[[DGED5.geokey]]
geokey = 1025
description = "GTRasterTypeGeoKey"
data_type = "integer"
constraint = "exact"
expected = 2
comment = "2 = RasterPixelIsPoint for elevation"

[[DGED5.geokey]]
geokey = 3072
description = "ProjectedCRSGeoKey"
data_type = "integer"
constraint = "ranges"
expected = [
  { min = 32601, max = 32660 },  # UTM Northern Hemisphere
  { min = 32701, max = 32760 },  # UTM Southern Hemisphere
  { min = 5041, max = 5042 }     # UPS North / South Pole
]
comment = "Valid UTM/UPS zone EPSG codes"

[[DGED5.geokey]]
geokey = 4096
description = "VerticalGeoKey"
data_type = "integer"
constraint = "exact"
expected = 3855
comment = "EPSG:3855 = EGM2008 geoid height"

[[DGED5.geokey]]
geokey = 2048
description = "GeodeticCRSGeoKey"
data_type = "integer"
constraint = "forbidden"
comment = "Must not be present in projected CRS files"

# ------------------------------------------------------------------------------
# GDAL Metadata (section: gdal)
# ------------------------------------------------------------------------------

[[DGED5.gdal]]
name = "STATISTICS_MINIMUM"
description = "Minimum Elevation"
data_type = "float"
constraint = "range"
expected = { min = -430.0, max = 8850.0 }
comment = "Minimum elevation must be within valid dry land range"

[[DGED5.gdal]]
name = "STATISTICS_MAXIMUM"
description = "Maximum Elevation"
data_type = "float"
constraint = "range"
expected = { min = -430.0, max = 8850.0 }
comment = "Maximum elevation must be within valid dry land range"

# ==============================================================================
# USGS 3D Elevation Program (3DEP)
# ==============================================================================
# Note: 3DEP produces DEMs (technically DTMs showing bare earth).

[3DEP]
title = "USGS 3DEP Digital Elevation Model"
description = "Validation rules for USGS 3DEP DEM products"
author = "United States Geological Survey"
updated = "2026-01-16"

[[3DEP.tag]]
tag = 258
description = "BitsPerSample"
data_type = "integer"
constraint = "exact"
expected = 32
comment = "32-bit float required for elevation data"

[[3DEP.tag]]
tag = 339
description = "SampleFormat"
data_type = "integer"
constraint = "exact"
expected = 3
comment = "3 = IEEE floating point"

[[3DEP.geokey]]
geokey = 1025
description = "GTRasterTypeGeoKey"
data_type = "integer"
constraint = "exact"
expected = 2
comment = "2 = RasterPixelIsPoint for elevation"

[[3DEP.geokey]]
geokey = 3072
description = "ProjectedCRSGeoKey"
data_type = "integer"
constraint = "ranges"
expected = [
  { min = 26901, max = 26920 },  # NAD83 UTM zones 1-20 (CONUS)
  { min = 26955, max = 26955 }   # NAD83 UTM zone 55 (Guam)
]
comment = "Valid NAD83 or WGS84 UTM zone EPSG codes"

[[3DEP.gdal]]
name = "STATISTICS_MINIMUM"
description = "Minimum Elevation"
data_type = "float"
constraint = "range"
expected = { min = -90.0, max = 6200.0 }
comment = "Minimum elevation must be within valid U.S. dry land range"

# ==============================================================================
# USDA NAIP Orthoimagery (National Agriculture Imagery Program)
# ==============================================================================

[NAIP]
title = "USDA NAIP Orthoimagery"
description = "Validation rules for NAIP 4-band orthoimagery products"
author = "USDA Farm Service Agency"
updated = "2026-01-15"

[[NAIP.tag]]
tag = 258
description = "BitsPerSample"
data_type = "integer"
constraint = "exact"
expected = [8, 8, 8, 8]
comment = "8-bit image depth"

[[NAIP.tag]]
tag = 262
description = "PhotometricInterpretation"
data_type = "integer"
constraint = "exact"
expected = 2
comment = "2 = RGB"

[[NAIP.tag]]
tag = 270
description = "ImageDescription"
data_type = "string"
constraint = "regex"
expected = ".*USDA Farm Service Agency.*National Agriculture Imagery Program.*NAIP.*"
comment = "Must contain NAIP attribution text"

[[NAIP.tag]]
tag = 277
description = "SamplesPerPixel"
data_type = "integer"
constraint = "exact"
expected = 4
comment = "4 bands (R, G, B, NIR) - No alpha band"

[[NAIP.geokey]]
geokey = 1025
description = "GTRasterTypeGeoKey"
data_type = "integer"
constraint = "exact"
expected = 1
comment = "1 = RasterPixelIsArea for orthoimagery"

[[NAIP.geokey]]
geokey = 3072
description = "ProjectedCRSGeoKey"
data_type = "integer"
constraint = "ranges"
expected = [
  { min = 26901, max = 26920 },  # NAD83 UTM zones 1-20 (CONUS)
  { min = 26955, max = 26955 }   # NAD83 UTM zone 55 (Guam)
]
comment = "NAD83 UTM zones for CONUS and Guam"

[[NAIP.gdal]]
name = "STATISTICS_VALID_PERCENT"
description = "Valid Pixel Percentage"
data_type = "float"
constraint = "exact"
expected = 100.0
comment = "NAIP tiles must have 100% valid pixels"

# ==============================================================================
# Copernicus GLO-30 and GLO-90 DEM Products
# ==============================================================================

[GLO-30]
title = "Copernicus GLO-30 Digital Elevation Model"
description = "Validation rules for 30m global Copernicus DEM products"
author = "European Space Agency (ESA)"
updated = "2026-01-16"

[[GLO-30.tag]]
tag = 258
description = "BitsPerSample"
data_type = "integer"
constraint = "exact"
expected = 32
comment = "32-bit float required"

[[GLO-30.geokey]]
geokey = 1025
description = "GTRasterTypeGeoKey"
data_type = "integer"
constraint = "exact"
expected = 2
comment = "2 = RasterPixelIsPoint for elevation"

[[GLO-30.geokey]]
geokey = 4096
description = "VerticalGeoKey"
data_type = "integer"
constraint = "exact"
expected = 3855
comment = "EPSG:3855 = EGM2008 geoid height"

[[GLO-30.gdal]]
name = "STATISTICS_MINIMUM"
description = "Minimum Elevation"
data_type = "float"
constraint = "range"
expected = { min = -430.0, max = 8850.0 }
comment = "Minimum elevation must be within valid dry land range"

# ==============================================================================

[GLO-90]
title = "Copernicus GLO-90 Digital Elevation Model"
description = "Validation rules for 90m global Copernicus DEM products"
author = "European Space Agency (ESA)"
updated = "2026-01-15"

[[GLO-90.tag]]
tag = 258
description = "BitsPerSample"
data_type = "integer"
constraint = "exact"
expected = 32
comment = "32-bit float required"

[[GLO-90.geokey]]
geokey = 1025
description = "GTRasterTypeGeoKey"
data_type = "integer"
constraint = "exact"
expected = 2
comment = "2 = RasterPixelIsPoint for elevation"

[[GLO-90.geokey]]
geokey = 4096
description = "VerticalGeoKey"
data_type = "integer"
constraint = "exact"
expected = 3855
comment = "EPSG:3855 = EGM2008 geoid height"
```

---

## 12. Implementation Phases

### Phase 1: Core Infrastructure (Week 1-2)

**Status:** [ ] Not Started

#### Deliverables:
1. ✅ Schema design review and finalization
2. [ ] Data models ([`gttk/utils/validation/models.py`](gttk/utils/validation/models.py))
3. [ ] TOML loader ([`gttk/utils/validation/loader.py`](gttk/utils/validation/loader.py))
4. [ ] Basic constraint validators ([`gttk/utils/validation/constraints.py`](gttk/utils/validation/constraints.py))
5. [ ] CLI argument integration ([`gttk/main.py`](gttk/main.py), [`gttk/utils/script_arguments.py`](gttk/utils/script_arguments.py))
6. [ ] Unit tests for models and loader

#### Key Tasks:
- Implement `ValidationRule`, `ValidationResult`, and `ValidationSummary` dataclasses
- Create TOML parser that loads all `.toml` files in rules directory
- Implement conflict detection (same product in multiple files)
- Build constraint validation functions for all 7 types
- Write comprehensive unit tests

### Phase 2: Core Sections (Week 3-4)

**Status:** [ ] Not Started

#### Deliverables:
1. [ ] Value extractors for core sections ([`gttk/utils/validation/extractors.py`](gttk/utils/validation/extractors.py))
2. [ ] Validation engine ([`gttk/utils/validation/validator.py`](gttk/utils/validation/validator.py))
3. [ ] TIFF tag validation
4. [ ] GeoKey validation
5. [ ] GDAL metadata validation
6. [ ] Unit and integration tests

#### Key Tasks:
- Implement extractors for TIFF tags using existing [`TiffTagParser`](gttk/utils/tiff_tag_parser.py)
- Implement extractors for GeoKeys using existing geokey parser
- Implement extractors for GDAL metadata using existing [`MetadataExtractor`](gttk/utils/metadata_extractor.py)
- Create core validation engine that ties rules to extractors
- Handle STATISTICS_* special case (run `ComputeStatistics` if needed)
- Write integration tests with sample GeoTIFF files

### Phase 3: Report Generation (Week 5)

**Status:** [ ] Not Started

#### Deliverables:
1. [ ] Validation report builder ([`gttk/tools/validate_metadata.py`](gttk/tools/validate_metadata.py) main script)
2. [ ] Section renderers for validation tables ([`gttk/utils/section_renderers.py`](gttk/utils/section_renderers.py))
3. [ ] Report formatters for validation summary ([`gttk/utils/report_builders.py`](gttk/utils/report_builders.py))
4. [ ] File naming logic (`_PASS` / `_FAIL` suffix)
5. [ ] Example rules file ([`gttk/resources/rules/example_rules.toml`](gttk/resources/rules/example_rules.toml))

#### Key Tasks:
- Implement `ValidationReportBuilder` in [`report_builders.py`](gttk/utils/report_builders.py)
- Add validation table renderer to [`section_renderers.py`](gttk/utils/section_renderers.py)
- Create validation summary header with statistics
- Implement file naming convention based on overall status
- Create comprehensive `example_rules.toml` with multiple products
- Test HTML and Markdown report generation
- Implement batch processing with name filtering

**MVP Complete at end of Phase 3**

### Phase 4: XML & Extended Sections (Week 6-7)

**Status:** [ ] Future

#### Deliverables:
3. [ ] GEO_METADATA validation (XPath-based)
2. [ ] XMP metadata validation (XPath-based)
1. [ ] XML metadata validation (XPath-based)
4. [ ] External XML file validation
5. [ ] Namespace-agnostic XPath handling

#### Key Tasks:
- Implement XPath extraction with namespace discovery
- Handle ISO 19115/19139 metadata standards
- Support Dublin Core XMP elements
- Test with various XML namespace versions

### Phase 5: PROJJSON & Advanced Features (Week 8+)

**Status:** [ ] Future

#### Deliverables:
1. [ ] PROJJSON validation (jsonpath-based)
2. [ ] Extended data types (date, datetime, URL)
3. [ ] ArcGIS toolbox tool
4. [ ] GUI support (if applicable)
5. [ ] Migration tool (CSV → TOML)

#### Key Tasks:
- Implement JSONPath validation for PROJJSON
- Add CRS component validation
- Create extended type validators
- Build migration utilities for legacy rule formats

---

## 13. Testing Strategy

### 13.1 Unit Tests

**Test Files:**
- `tests/unit/test_validation_models.py`
- `tests/unit/test_validation_loader.py`
- `tests/unit/test_validation_constraints.py`
- `tests/unit/test_validation_messages.py`

**Coverage:**
- ValidationRule validation and errors
- ValidationResult status logic
- TOML parsing and conflict detection
- All constraint type validators
- Message formatting for each constraint type
- Edge cases (None values, empty strings, type mismatches)

### 13.2 Integration Tests

**Test Files:**
- `tests/integration/test_validation_tiff_tags.py`
- `tests/integration/test_validation_geokeys.py`
- `tests/integration/test_validation_gdal_metadata.py`
- `tests/integration/test_validation_geo_metadata.py`
- `tests/integration/test_validation_xmp_metadata.py`
- `tests/integration/test_validation_xml_metadata.py`
- `tests/integration/test_validation_projjson.py`
- `tests/integration/test_validation_workflow.py`
- `tests/integration/test_validation_batch_processing.py`

**Coverage:**
- End-to-end validation with real GeoTIFF files
- PASS, FAIL, and SKIP scenarios
- Optional field handling
- Missing section handling (all rules listed)
- Multiple sections in one report
- File naming convention (`_PASS` / `_FAIL`)
- Batch processing with name filtering

### 13.3 Test Data

Create test fixtures:
```
tests/fixtures/validation/
├── rules/
│   ├── test_product.toml        # Simple test rules
│   ├── conflicting_prod_a.toml  # For conflict detection tests
│   └── conflicting_prod_b.toml
└── geotiffs/
    ├── valid_glo30.tif          # Passes all GLO-30 rules
    ├── invalid_compression.tif  # Fails compression rule
    ├── missing_tags.tif         # Missing required tags
    ├── mixed_products/          # For batch testing
    │   ├── tile_001_DSM.tif
    │   ├── tile_001_DTM.tif
    │   └── tile_001_ortho.tif
    └── ...
```

### 13.4 Test Scenarios

#### A. Batch Processing Tests

1. **Valid Batch** - Directory with 10 valid GeoTIFFs → 10 `_PASS.html` files
2. **Mixed Results Batch** - Directory with 5 valid, 3 invalid, 2 incomplete → 5 `_PASS.html`, 5 `_FAIL.html`
3. **Empty Directory** - Directory with no `.tif` files → Error message
4. **Name Filtering** - Mixed products with `--name-string DSM` → Only DSM files processed
5. **Custom Output Directory** - Batch with custom output path → Reports in custom directory

#### B. Missing Section Tests

1. **No External XML** - `xml` rules, no `.xml` file → All rules FAIL with a `section_missing_msg`
2. **Missing GDAL_METADATA Tag** - `gdal` rules, Tag 42112 not present → All rules FAIL with a `section_missing_msg`
3. **Partial GeoKeys** - 10 geokey rules, only 3 present → 3 results based on values, 7 FAIL for missing keys

#### C. Message Differentiation Tests

1. **Wrong Value** - Tag exists but value wrong → "Tag X value Y does not match..."
2. **Missing Key** - Section exists but key missing → "Tag X is required but not present..."
3. **Missing Section** - Entire section absent → e.g., "GDAL_METADATA tag (42112) is not present"

---

## 14. Documentation Updates

### 14.1 Main README.md

Add validation tool to the tools table:

```markdown
| Tool | Command | Purpose |
| ---- | ------- | ------- |
| Read Metadata | `gttk read` | Extract and report GeoTIFF metadata |
| Compare Compression | `gttk compare` | Compare two GeoTIFFs side-by-side |
| Optimize Compression | `gttk optimize` | Create optimized Cloud-Optimized GeoTIFFs |
| Test Compression | `gttk test` | Test multiple compression settings |
| **Validate Metadata** | **`gttk validate`** | **Validate GeoTIFF against product requirements** |
```

Add usage examples:

```markdown
### Validate Metadata

Validate GeoTIFF files against product-specific requirements using TOML-based rule definitions.

#### Single File Validation

```bash
# Validate a single file
gttk validate -i example.tif -p DGED5

# Validate with custom rules directory
gttk validate -i example.tif -p CustomProduct -r /path/to/rules

# Generate Markdown report (in addition to JSON)
gttk validate -i example.tif -p GLO-30 -f md
```

#### Batch Validation

```bash
# Validate all GeoTIFFs in a directory
gttk validate -i data/tiles/ -p DGED5

# Validate only files matching a name pattern
gttk validate -i data/mixed/ -p 3DEP -n dem
```

#### Multi-Product Workflows

When a directory contains multiple product types, use `--name-string` to process each product separately:

```bash
# Validate DEM products
gttk validate -i delivery/ -p 3DEP -n dem

# Validate orthoimagery
# NAIP name begins with 'm_' for "multispectral", includes lat/lon of center, UTM zone and resolution in meters
gttk validate -i delivery/ -p NAIP -n '(?i)^m_\d{7}(?:ne|nw|se|sw)(?:\d{2})_(?:\d{1,3})'
```

This approach ensures that each product type is validated against its appropriate specification without requiring file reorganization.

#### Output

Validation results are saved to a `{basename}_validation/` folder containing:
- **JSON file**: Primary output with all validation results
- **HTML/MD reports**: Optional per-file reports (if `--write-reports` is true)

```
example_validation/
├── example_validation.json  # Primary JSON output
├── tile_001_PASS.html       # Optional per-file report
├── tile_002_FAIL.html
└── tile_003_PASS.html
```

This structure enables both programmatic access (JSON) and human review (HTML/MD).
```

### 14.2 gttk/resources/rules/README.md

Create comprehensive documentation for the rules system:

```markdown
# GeoTIFF Validation Rules - User Guide

This directory contains TOML-based validation rule files for the `gttk validate` command.

## Overview

Validation rules define requirements that GeoTIFF files must meet for specific
products, standards, or specifications. Rules are organized by product
and can validate multiple metadata sources (TIFF tags, GeoKeys, XML, etc.).

## Product vs Program Terminology

**Important:** Validation rules are organized by **product**, not program.

### What's the Difference?

- **Program** = Organizational entity that produces data (e.g., USGS 3DEP, Copernicus)
- **Product** = Specific deliverable with distinct validation requirements (e.g., DSM, DTM, Orthoimagery)

### Why Product-Level Organization?

A single program may produce multiple products with vastly different technical requirements:

**Example: USGS Programs**
- **3DEP**: Digital Elevation Models (32-bit float, PixelIsPoint, NAVD88 + GEOID18)
- **NAIP**: Orthoimagery from USDA (8-bit unsigned int, 4 bands RGBN, PixelIsArea)

**Example: Copernicus DEM Program**
- **GLO-30**: 30-meter global DEM (1.0 arc seconds, 32-bit float, PixelIsPoint, EGM2008)
- **GLO-90**: 90-meter global DEM (3.0 arc seconds, 32-bit float, PixelIsPoint, EGM2008)

Each product requires separate validation rules.

## File Organization

- **`example_rules.toml`** - Example rules tracked in Git (reference implementation)
- **`*_rules.toml`** - Custom rules (ignored by Git via `.gitignore`)

Users can create their own `*_rules.toml` files for custom products without
affecting the tracked example file.

## Rule Schema

See [`SCHEMA_DESIGN_SUMMARY.md`](SCHEMA_DESIGN_SUMMARY.md) for complete schema documentation.

### Basic Structure

```toml
[ProductName]
title = "Product Display Title"
description = "Product description"
author = "Organization"
updated = "YYYY-MM-DD"

[[ProductName.section_type]]
# Section-specific key (tag, geokey, name, xpath, jsonpath)
tag = 258  # or geokey, name, xpath, jsonpath
description = "Human-readable description"
data_type = "integer"  # or string, float, boolean
constraint = "exact"   # or enum, regex, range, ranges, exists, forbidden
expected = 32
optional = false
comment = "Additional notes"
```

## Creating Custom Rules

1. Create a new TOML file: `my_product_rules.toml`
2. Define your product with a unique name
3. Add validation rules organized by section
4. Place file in `gttk/resources/rules/` directory
5. Run validation: `gttk validate -i file.tif -p MyProduct`

## Distribution

Program managers can distribute `.toml` files to data producers and consumers
to ensure consistent validation across the supply chain.

## Multi-Product Workflows

When validating deliveries containing multiple products:

```bash
# Process each product type separately with name filtering
gttk validate -i delivery/ -p 3DEP -n USGS_1M_ -o validation/dem/
gttk validate -i delivery/ -p NAIP -n '(?i)^m_\d{7}(?:ne|nw|se|sw)(?:\d{2})_(?:\d{1,3})' -o validation/ortho/
gttk validate -i delivery/ -p GLO-30 -n _10_ -o validation/glo30/
```

This ensures each file is validated against its correct specification.
```

---

## 15. Dependencies

### 15.1 Required Python Packages

Add to [`requirements.txt`](requirements.txt):

```
jsonpath-ng>=1.5.3     # JSONPath for PROJJSON validation (Phase 5)
```

**Note:** TOML parsing uses Python's built-in `tomllib` module (available in Python 3.11+, which is enforced by the project's `requirements.txt` and `environment.yml`).

### 15.2 Existing GTTK Dependencies

The tool leverages existing infrastructure:
- [`MetadataExtractor`](gttk/utils/metadata_extractor.py) - For extracting GeoTIFF metadata
- [`TiffTagParser`](gttk/utils/tiff_tag_parser.py) - For TIFF tag extraction
- [`GeoKeyParser`](gttk/utils/geokey_parser.py) - For GeoKey extraction (ensure naming consistency with TiffTagParser)
- [`report_builders`](gttk/utils/report_builders.py) - For report construction
- [`section_renderers`](gttk/utils/section_renderers.py) - For rendering validation tables
- [`report_formatters`](gttk/utils/report_formatters.py) - For HTML/Markdown generation

---

## 16. Success Criteria

### 16.1 Functional Requirements

- ✅ Support both single-file and batch (directory) processing
- ✅ Filter batch processing by filename substring (--name-string)
- ✅ Use product-level terminology for validation operations
- ✅ List all rules in report, even when sections are missing
- ✅ Differentiate between wrong values, missing keys, and missing sections in messages
- ✅ Default output to `validation/` directory with option to customize
- ✅ Load validation rules from multiple TOML files organized by product
- ✅ Detect and report product name conflicts across files
- ✅ Validate TIFF tags, GeoKeys, and GDAL metadata (Phase 1-3)
- ✅ Support all 7 constraint types
- ✅ Generate HTML and Markdown reports with `_PASS`/`_FAIL` naming
- ✅ Handle optional fields correctly
- ✅ Provide descriptive, actionable messages for all validation outcomes

### 16.2 Quality Requirements

- Unit test coverage ≥ 90%
- Integration tests for all validation paths
- Clear, actionable error messages
- Performance: Validate typical file (<1GB) in < 10 seconds
- Documentation: Complete user guide and API docs

### 16.3 Acceptance Criteria

- Successfully validate real DGED5, 3DEP, NAIP, GLO-30, and GLO-90 files
- Process mixed-product directories with appropriate filtering
- Generate reports matching specification
- Users can create custom rules without code changes
- Tool handles edge cases gracefully (missing files, invalid TOML, etc.)
- Clear documentation explaining product vs program distinction

---

## 17. Timeline

| Phase | Duration | Completion Target |
| ----- | -------- | ---------------- |
| Phase 1: Core Infrastructure | 2 weeks | Week 2 |
| Phase 2: Core Sections | 2 weeks | Week 4 |
| Phase 3: Report Generation | 1 week | Week 5 |
| Phase 4: XML & Extended Sections | 2 weeks | Week 7 |
| Phase 5: PROJJSON & Advanced | 1+ weeks | Week 8+ |

**Total Estimated Duration:** 8+ weeks for full implementation

**MVP (Minimum Viable Product):** End of Phase 3 (Week 5)
- TIFF tags, GeoKeys, and GDAL metadata validation
- HTML and Markdown reports
- Batch processing with name filtering
- All constraint types working
- Product-level organization

---

## Appendices

### A. Terminology Migration Summary

| Old Term | New Term | Context |
| -------- | -------- | ------- |
| `program` | `product` | Validation-level operations |
| `--program` | `--product` | CLI argument |
| `args.program` | `args.product` | Python code |
| `rule.program` | `rule.product` | Data models |
| `[PROGRAM_NAME]` | `[PRODUCT_NAME]` | TOML top-level keys |

**Note:** "Program" may still be used in documentation when referring to organizational entities (e.g., "The USGS 3DEP program produces multiple products"), but validation operations always refer to specific products.

### B. Files to Create vs Update

#### New Files (To Be Created)

```text
gttk/utils/validation/__init__.py
gttk/utils/validation/models.py
gttk/utils/validation/loader.py
gttk/utils/validation/constraints.py
gttk/utils/validation/validator.py
gttk/utils/validation/extractors.py
gttk/tools/validate_metadata.py
gttk/resources/rules/example_rules.toml
gttk/resources/rules/README.md
tests/unit/test_validation_models.py
tests/unit/test_validation_loader.py
tests/unit/test_validation_constraints.py
tests/unit/test_validation_messages.py
tests/integration/test_validation_tiff_tags.py
tests/integration/test_validation_geokeys.py
tests/integration/test_validation_gdal_metadata.py
tests/integration/test_validation_geo_metadata.py
tests/integration/test_validation_xmp_metadata.py
tests/integration/test_validation_xml_metadata.py
tests/integration/test_validation_projjson.py
tests/integration/test_validation_workflow.py
tests/integration/test_validation_batch_processing.py
tests/fixtures/validation/ (directory with test data)
```

#### Existing Files (To Update)

```text
gttk/main.py - Add validate_parser
gttk/utils/script_arguments.py - Add ValidateArguments class
gttk/utils/report_builders.py - Add ValidationReportBuilder
gttk/utils/section_renderers.py - Add validation table renderer
README.md - Add validate tool documentation
```

### C. Code Style Guidelines

Following existing GTTK patterns:

- Use dataclasses for data models
- Type hints on all function signatures
- Comprehensive docstrings (Google style)
- Logging at INFO level for user actions
- Logging at DEBUG level for internal operations
- Raise ValueError for user input errors
- Raise RuntimeError for internal errors

### D. Git Workflow

1. Create feature branch: `feature/validate-metadata`
2. Implement in phases with separate commits per phase
3. Write tests alongside implementation
4. Update documentation as features complete
5. Create pull request with comprehensive description
6. Address code review feedback
7. Merge to main after approval

### E. Risk Assessment

#### Technical Risks

| Risk | Likelihood | Impact | Mitigation |
| ---- | --------- | ------ | ---------- |
| TOML parsing conflicts | Medium | High | Implement robust conflict detection with clear error messages |
| Complex rule validation | Low | Medium | Comprehensive unit tests for all constraint types |
| Performance with large files | Low | Medium | Lazy loading and caching strategies |
| Namespace handling in XML | Medium | Medium | Use lxml's robust namespace discovery |

#### Usability Risks

| Risk | Likelihood | Impact | Mitigation |
| ---- | --------- | ------ | ---------- |
| Complex TOML syntax | Medium | High | Provide excellent example_rules.toml and documentation |
| Unclear error messages | Medium | High | Design descriptive, actionable validation messages |
| Rule file management | Low | Medium | Clear documentation on Git ignore patterns |
| Product vs program confusion | Medium | Medium | Comprehensive documentation with real-world examples |

---

**Document Version:** 2.0 (Final Consolidated)  
**Last Updated:** 2026-01-16
**Status:** Ready for Phase 1 Implementation  
**Next Review:** After Phase 1 completion
