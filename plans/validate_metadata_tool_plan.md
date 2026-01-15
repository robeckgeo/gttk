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
- **Multi-source validation** (TIFF tags, GeoKeys, GDAL metadata, XML, XMP, PROJJSON)
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

- **Program** = Organizational entity that produces data (e.g., USGS 3DEP, Copernicus, NGA DGED)
- **Product** = Specific deliverable with distinct validation requirements (e.g., DSM, DTM, Orthoimagery)

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
- **`3DEP-DSM`** (Digital Surface Model)
  - Includes vegetation, buildings, other features
  - 32-bit float, PixelIsPoint
  - General elevation accuracy requirements
  
- **`3DEP-DTM`** (Digital Terrain Model)
  - Bare earth only
  - 32-bit float, PixelIsPoint
  - **Stricter vertical accuracy requirements** (≤15cm vs ≤30cm)
  
- **`3DEP-Ortho`** (Orthoimagery)
  - 8-bit unsigned integer
  - 3-4 bands (RGB or RGBA)
  - PixelIsArea
  - **Completely different validation rules**

#### Example 2: Copernicus Land Monitoring Service

**Program:** Copernicus  
**Products:**
- **`COPDEM-30`** (30m DEM) - Higher accuracy requirements
- **`COPDEM-90`** (90m DEM) - Relaxed accuracy requirements
- **`Corine-LandCover`** (Land classification) - Different data types entirely

### 1.4 Implementation Impact

All variable names, arguments, and documentation use **product** terminology:

```python
# CLI Argument
validate_parser.add_argument('-p', '--product', dest='product', ...)

# Data Models
class ValidationRule:
    product: str  # e.g., '3DEP-DSM', 'COPDEM-30', 'DGED5'
    
# TOML Structure
[3DEP-DSM]  # Product name as top-level key
title = "USGS 3DEP Digital Surface Model"
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
    section: str  # 'tiff_tag', 'geokey', 'gdal_metadata', etc.
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
[[DGED5.tiff_tag]]
tag = 258  # Section-specific

[[DGED5.geokey]]
geokey = 3072  # Section-specific

[[DGED5.gdal_metadata]]
name = "AREA_OR_POINT"  # Section-specific

# Loader converts to generic model
rule = ValidationRule(
    section='tiff_tag',
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
              [-o OUTPUT_DIR] [-f FORMAT] [--open-report] [-v]
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
         'Example: DGED5, 3DEP-DSM, COPDEM-30'
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
    help='Specific sections to validate (e.g., tiff_tag geokey gdal_metadata). '
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
    default=Path('validation'),
    dest='output_dir',
    help='Directory for validation reports. '
         'Default: validation/ (created if it does not exist)'
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
    help='Automatically open the report after generation. '
         'For batch processing, only the first report is opened.'
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
    output_dir: Path = Path('validation')
    report_format: str = 'html'
    
    def __post_init__(self):
        """Validation for validate_metadata arguments."""
        super().__post_init__()
        try:
            self._validate_arguments()
            self._setup_output_dir()
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
    
    def _setup_output_dir(self):
        """Create output directory if it doesn't exist."""
        if not self.output_dir.exists():
            self.output_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created output directory: {self.output_dir}")
```

### 3.4 Argument Summary Table

| Argument | Required | Type | Validation | Default |
| -------- | -------- | ---- | ---------- | ------- |
| `--input` | Yes | Path | File or directory must exist | - |
| `--product` | Yes | str | Must match a product in TOML rules | - |
| `--rules-dir` | No | Path | Must be valid directory with .toml files | `gttk/resources/rules` |
| `--sections` | No | List[str] | Section names from TOML schema | All sections |
| `--name-string` | No | str | Used only if input is directory | `''` (no filter) |
| `--output-dir` | No | Path | Created if doesn't exist | `validation/` |
| `--report-format` | No | str | `html` or `md` | `html` |
| `--open-report` | No | bool | - | `True` |
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
    """Metadata section types."""
    TIFF_TAG = 'tiff_tag'
    GEOKEY = 'geokey'
    GDAL_METADATA = 'gdal_metadata'
    XML_METADATA = 'xml_metadata'
    XMP_METADATA = 'xmp_metadata'
    GEO_METADATA = 'geo_metadata'
    PROJJSON = 'projjson'

@dataclass
class ValidationRule:
    """
    Represents a single validation rule from TOML configuration.
    
    Attributes:
        product: Name of the validation product (e.g., 'DGED5', '3DEP-DSM')
        section: Metadata section type (e.g., 'tiff_tag', 'geokey')
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
        product: Validation product name (e.g., 'DGED5', '3DEP-DSM')
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
        section_type: Section type identifier (e.g., 'tiff_tag')
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
# Example: "Tag 277 value 3 is not in allowed list: [3, 4]"

# FAIL - Regex constraint
f"Tag {rule.key} value '{value}' does not match pattern '{rule.expected}'"
# Example: "Tag 306 value '01/15/2025' does not match pattern '^\\d{4}-\\d{2}-\\d{2}'"

# FAIL - Range constraint
f"Metadata '{rule.key}' value {value} is outside range {rule.expected['min']} to {rule.expected['max']}"
# Example: "Metadata 'STATISTICS_MEAN' value 300 is outside range 0 to 255"

# FAIL - Forbidden constraint
f"Tag {rule.key} ({rule.description}) must not be present but was found with value: {value}"
# Example: "Tag 339 (Sample Format) must not be present but was found with value: 3"
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
# FAIL - No external XML file
f"Section is missing: No matching external XML metadata file was found"

# FAIL - GDAL_METADATA tag absent
f"Section is missing: GDAL_METADATA tag (42112) is not present"

# FAIL - GeoKey directory missing
f"Section is missing: GeoKey directory is missing (no GeoKeys found)"

# FAIL - XMP metadata tag absent
f"Section is missing: XMP metadata tag (700) is not present"

# FAIL - TIFF tag section empty
f"Section is missing: TIFF tag section is empty (no tags found)"

# FAIL - PROJJSON unavailable
f"Section is missing: PROJJSON coordinate system data is not available"
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
# Example: "Tag 270 (Image Description) is present with value: 'Sample dataset'"

# PASS - Forbidden
f"Tag {rule.key} ({rule.description}) is correctly absent"
# Example: "Tag 339 (Sample Format) is correctly absent"
```

### 5.3 Message Generation Implementation

```python
def get_missing_key_message(rule: ValidationRule) -> str:
    """Generate appropriate message for missing key based on section type."""
    if rule.section in ['xml_metadata', 'xmp_metadata', 'geo_metadata']:
        # XPath-based sections
        return f"XPath '{rule.key}' is required but not present in the file"
    elif rule.section == 'projjson':
        # JSONPath-based section
        return f"JSONPath '{rule.key}' is required but not present"
    elif rule.section == 'tiff_tag':
        return f"Tag {rule.key} ({rule.description}) is required but not present in the file"
    elif rule.section == 'geokey':
        return f"GeoKey {rule.key} ({rule.description}) is required but not found"
    elif rule.section == 'gdal_metadata':
        return f"Metadata item '{rule.key}' ({rule.description}) is required but not present"
    else:
        return f"{rule.key_type.capitalize()} {rule.key} is required but not found"

def get_section_missing_message(section_type: str) -> str:
    """Get appropriate message for missing section."""
    messages = {
        'tiff_tag': 'TIFF tag section is empty (no tags found)',
        'geokey': 'GeoKey directory is missing (no GeoKeys found)',
        'gdal_metadata': 'GDAL_METADATA tag (42112) is not present',
        'xml_metadata': 'No matching external XML metadata file was found',
        'xmp_metadata': 'XMP metadata tag (700) is not present',
        'geo_metadata': 'GEO_METADATA tag (50909) is not present',
        'projjson': 'PROJJSON coordinate system data is not available',
    }
    return messages.get(section_type, f'{section_type} section is not available')
```

---

## 6. Batch Processing with Name Filtering

### 6.1 Core Feature: Selective Batch Processing

**Problem:** Data deliveries often contain multiple product types in a single directory:
- DSMs, DTMs, and orthoimagery from 3DEP
- 30m and 90m resolution DEMs from Copernicus
- Multispectral and panchromatic satellite imagery

**Solution:** The `--name-string` argument enables selective validation by filename substring matching.

### 6.2 Use Cases

#### Use Case 1: Mixed Product Directory

**Scenario:**
```
data/
├── tile_001_DSM.tif          # Digital Surface Model
├── tile_001_DTM.tif          # Digital Terrain Model  
├── tile_001_ortho.tif        # Orthoimagery
├── tile_002_DSM.tif
├── tile_002_DTM.tif
├── tile_002_ortho.tif
└── ...
```

**Solution - Run three passes with different product rules:**
```bash
# Validate only DSMs against DSM specification
gttk validate -i data/ -p 3DEP-DSM -n DSM -o validation/dsm/

# Validate only DTMs against DTM specification  
gttk validate -i data/ -p 3DEP-DTM -n DTM -o validation/dtm/

# Validate only orthoimagery against ortho specification
gttk validate -i data/ -p 3DEP-Ortho -n ortho -o validation/ortho/
```

#### Use Case 2: Resolution-Based Product Variants

**Scenario:**
```
dems/
├── copdem_30m_tile_N40W105.tif
├── copdem_30m_tile_N40W106.tif
├── copdem_90m_tile_N40W105.tif
├── copdem_90m_tile_N40W106.tif
└── ...
```

**Solution:**
```bash
# Validate 30m products (stricter accuracy requirements)
gttk validate -i dems/ -p COPDEM-30 -n 30m

# Validate 90m products (different accuracy requirements)
gttk validate -i dems/ -p COPDEM-90 -n 90m
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

If TOML has rules for `xml_metadata` but no external XML file exists:

```markdown
## External XML Metadata

| Result | Description | Value | Message |
| ------ | ----------- | ----- | ------- |
| ❌ FAIL | ISO 19115 Abstract | - | Section is missing: No matching external XML metadata file was found. |
| ❌ FAIL | ISO 19115 Date | - | Section is missing: No matching external XML metadata file was found. |
| ❌ FAIL | Authority | - | Section is missing: No matching external XML metadata file was found. |
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
                message=f"Section is missing: {section_missing_msg}"
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

### 8.1 Default Location

**Output files default to a `validation/` folder**, not the source data directory.

**Rationale:**
- Avoids cluttering source data directories with validation reports
- Centralizes validation results for easier management
- Matches pattern of `test` tool which uses a `temp/` directory
- Users can easily delete/archive all validation results at once
- Better organization for batch validation workflows

### 8.2 Directory Creation

```python
def _setup_output_dir(self):
    """Create output directory if it doesn't exist."""
    if not self.output_dir.exists():
        self.output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created output directory: {self.output_dir}")
```

### 8.3 File Naming Logic

```python
def generate_output_path(input_file: Path, output_dir: Path, 
                        overall_status: str, report_format: str) -> Path:
    """
    Generate output file path for validation report.
    
    Args:
        input_file: Input GeoTIFF file
        output_dir: Directory to place report (default: validation/)
        overall_status: 'PASS', 'FAIL', or 'SKIP'
        report_format: 'html' or 'md'
    
    Returns:
        Full path to output report file
    
    Example:
        input: "/data/dems/example.tif"
        output_dir: "validation/"
        status: "FAIL"
        format: "html"
        result: "validation/example_FAIL.html"
    """
    stem = input_file.stem
    
    # Determine suffix based on overall status
    if overall_status == 'FAIL':
        suffix = '_FAIL'
    elif overall_status == 'PASS':
        suffix = '_PASS'
    else:
        suffix = '_SKIP'
    
    # Build filename
    filename = f"{stem}{suffix}.{report_format}"
    
    # Combine with output directory
    output_path = output_dir / filename
    
    return output_path
```

**File Naming Rationale:**
- Enables automated workflows to identify failures via filesystem scan
- Clear and unambiguous naming
- No custom suffix option (unlike other tools) - keeps naming consistent
- Users can rename afterward if needed for custom workflows

### 8.4 Usage Examples

```bash
# Default: Reports go to validation/ folder
gttk validate -i data/example.tif -p DGED5
# Creates: validation/example_PASS.html or validation/example_FAIL.html

# Custom output directory
gttk validate -i data/example.tif -p DGED5 -o reports/
# Creates: reports/example_PASS.html or reports/example_FAIL.html

# Batch processing with default output
gttk validate -i data/dems/ -p DGED5
# Creates: validation/dem1_PASS.html, validation/dem2_FAIL.html, etc.

# Batch with custom output + filtering
gttk validate -i data/dems/ -p 3DEP-DSM -n DSM -o results/dsm/
# Creates: results/dsm/tile_001_DSM_PASS.html, results/dsm/tile_002_DSM_FAIL.html
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
    
    for section_name in ['tiff_tag', 'geokey', 'gdal_metadata', 
                         'xml_metadata', 'xmp_metadata', 'geo_metadata', 'projjson']:
        
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
        section: Section type (e.g., 'tiff_tag')
        rule_dict: Raw dictionary from TOML
    
    Returns:
        ValidationRule object
    """
    # Determine key and key_type from section-specific field
    key_field_map = {
        'tiff_tag': 'tag',
        'geokey': 'geokey',
        'gdal_metadata': 'name',
        'xml_metadata': 'xpath',
        'xmp_metadata': 'xpath',
        'geo_metadata': 'xpath',
        'projjson': 'jsonpath'
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
    
    def extract_tiff_tag(self, key: str) -> Optional[Any]:
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
    
    def extract_gdal_metadata(self, key: str) -> Optional[Any]:
        """Extract GDAL metadata item by name."""
        gdal_md = self.extractor.extract_gdal_metadata()
        if not gdal_md or not gdal_md.has_content():
            return None
        
        # Parse XML to extract specific item
        from lxml import etree
        root = etree.fromstring(gdal_md.content.encode('utf-8'))
        items = root.xpath(f".//Item[@name='{key}']")
        if items:
            return items[0].text
        return None
    
    def extract_xml_xpath(self, xpath: str, xml_content: str) -> Optional[Any]:
        """Extract value from XML using XPath with namespace discovery."""
        from lxml import etree
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
                    message=f"Section is missing: {section_missing_msg}"
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
        if section_type == 'tiff_tag':
            tags = self.extractor.extract_tags(page=0, scope='complete')
            return tags if tags else None
        
        elif section_type == 'geokey':
            geokeys = self.extractor.extract_geokeys()
            return geokeys if geokeys else None
        
        elif section_type == 'gdal_metadata':
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
        if rule.section == 'tiff_tag':
            return self.value_extractor.extract_tiff_tag(rule.key)
        elif rule.section == 'geokey':
            return self.value_extractor.extract_geokey(rule.key)
        elif rule.section == 'gdal_metadata':
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
        if rule.section == 'tiff_tag':
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
| ❌ FAIL | Compression | 1 (Uncompressed) | Tag 259 value 1 (Uncompressed) is not in allowed list: [5 (LZW), 8 (DEFLATE), 50000 (ZSTD)] |
| ✅ PASS | ImageDescription | "Sample DEM" | Tag 270 (Image Description) is present with value: 'Sample DEM' |
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
    'tiff_tag': 'tag',        # Same as current TIFF Tags section
    'geokey': 'key',          # Same as current GeoKeys section
    'gdal_metadata': 'earth', # Same as GDAL_METADATA section
    'xml_metadata': 'xml',    # Same as XML metadata section
    'xmp_metadata': 'xmp',    # Same as XMP section
    'geo_metadata': 'geo',    # Same as GEO_METADATA section
    'projjson': 'json',       # Same as PROJJSON section
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
description = "Validation rules for DGED5 GeoTIFF products"
author = "National Geospatial-Intelligence Agency (NGA)"
updated = "2026-01-03"

# ------------------------------------------------------------------------------
# TIFF Tags
# ------------------------------------------------------------------------------

[[DGED5.tiff_tag]]
tag = 258
description = "BitsPerSample"
data_type = "integer"
constraint = "exact"
expected = 32
comment = "Must be 32-bit floating point"

[[DGED5.tiff_tag]]
tag = 259
description = "Compression"
data_type = "integer"
constraint = "enum"
expected = [5, 8, 50000]
comment = "5=LZW, 8=DEFLATE, 50000=ZSTD - all acceptable"

[[DGED5.tiff_tag]]
tag = 270
description = "ImageDescription"
data_type = "string"
constraint = "exists"
comment = "Description required but content not validated"

[[DGED5.tiff_tag]]
tag = 306
description = "DateTime"
data_type = "string"
constraint = "regex"
expected = "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z$"
comment = "ISO 8601 format: YYYY-MM-DDThh:mm:ssZ"

[[DGED5.tiff_tag]]
tag = 339
description = "SampleFormat"
data_type = "integer"
constraint = "forbidden"
comment = "Should not be present - BitsPerSample defines format"

[[DGED5.tiff_tag]]
tag = 305
description = "Software"
data_type = "string"
constraint = "regex"
expected = "GDAL \\d+\\.\\d+\\.\\d+"
optional = true
comment = "Optional but must match GDAL version pattern if present"

# ------------------------------------------------------------------------------
# GeoKeys
# ------------------------------------------------------------------------------

[[DGED5.geokey]]
geokey = 1024
description = "GTModelTypeGeoKey"
data_type = "integer"
constraint = "exact"
expected = 1
comment = "1 = ModelTypeProjected"

[[DGED5.geokey]]
geokey = 1025
description = "GTRasterTypeGeoKey"
data_type = "integer"
constraint = "exact"
expected = 2
comment = "2 = RasterPixelIsPoint"

[[DGED5.geokey]]
geokey = 3072
description = "ProjectedCRSGeoKey"
data_type = "integer"
constraint = "ranges"
expected = [
  { min = 32601, max = 32660 },  # UTM Northern hemisphere
  { min = 32701, max = 32760 }   # UTM Southern hemisphere
]
comment = "Valid UTM zone EPSG codes"

[[DGED5.geokey]]
geokey = 4096
description = "VerticalGeoKey"
data_type = "integer"
constraint = "exact"
expected = 3855
comment = "3855 = EGM2008 geoid height"

[[DGED5.geokey]]
geokey = 2048
description = "GeographicTypeGeoKey"
data_type = "integer"
constraint = "forbidden"
comment = "Must not be present in projected CRS files"

# ------------------------------------------------------------------------------
# GDAL Metadata
# ------------------------------------------------------------------------------

[[DGED5.gdal_metadata]]
name = "STATISTICS_MINIMUM"
description = "Min Elevation"
data_type = "float"
constraint = "range"
expected = { min = -430.0, max = 8850.0 }
comment = "Min elevation must be within valid dry land range"

[[DGED5.gdal_metadata]]
name = "STATISTICS_MAXIMUM"
description = "Max Elevation"
data_type = "float"
constraint = "range"
expected = { min = -430.0, max = 8850.0 }
comment = "Max elevation must be within valid dry land range"

# ==============================================================================
# USGS 3DEP Products - Separate validation requirements per product type
# ==============================================================================

[3DEP-DSM]
title = "USGS 3DEP Digital Surface Model"
description = "Validation rules for 3DEP DSM products"
author = "United States Geological Survey"
updated = "2026-01-03"

[[3DEP-DSM.tiff_tag]]
tag = 258
description = "Bits Per Sample"
data_type = "integer"
constraint = "exact"
expected = 32
comment = "32-bit float required for elevation data"

[[3DEP-DSM.geokey]]
geokey = 1025
description = "GT Raster Type GeoKey"
data_type = "integer"
constraint = "exact"
expected = 2
comment = "DSM products use PixelIsPoint"

[[3DEP-DSM.gdal_metadata]]
name = "AREA_OR_POINT"
description = "Pixel Interpretation"
data_type = "string"
constraint = "exact"
expected = "Point"
comment = "DSM products use PixelIsPoint"

# ==============================================================================

[3DEP-DTM]
title = "USGS 3DEP Digital Terrain Model"
description = "Validation rules for 3DEP DTM products (bare earth)"
author = "United States Geological Survey"
updated = "2026-01-03"

[[3DEP-DTM.tiff_tag]]
tag = 258
description = "Bits Per Sample"
data_type = "integer"
constraint = "exact"
expected = 32
comment = "32-bit float required"

[[3DEP-DTM.geokey]]
geokey = 1025
description = "GT Raster Type GeoKey"
data_type = "integer"
constraint = "exact"
expected = 2
comment = "DTM products use PixelIsPoint"

[[3DEP-DTM.gdal_metadata]]
name = "AREA_OR_POINT"
description = "Pixel Interpretation"
data_type = "string"
constraint = "exact"
expected = "Point"
comment = "DTM products use PixelIsPoint"

# DTMs may have stricter accuracy requirements than DSMs
[[3DEP-DTM.gdal_metadata]]
name = "VERTICAL_ACCURACY_CE90"
description = "Vertical Accuracy (CE90)"
data_type = "float"
constraint = "range"
expected = { min = 0.0, max = 0.15 }
comment = "DTM must have ≤15cm vertical accuracy"

# ==============================================================================

[3DEP-Ortho]
title = "USGS 3DEP Orthoimagery"
description = "Validation rules for 3DEP orthoimagery products"
author = "United States Geological Survey"
updated = "2026-01-03"

[[3DEP-Ortho.tiff_tag]]
tag = 258
description = "Bits Per Sample"
data_type = "integer"
constraint = "exact"
expected = 8
comment = "8-bit unsigned integer for RGB imagery"

[[3DEP-Ortho.tiff_tag]]
tag = 277
description = "Samples Per Pixel"
data_type = "integer"
constraint = "enum"
expected = [3, 4]
comment = "3 (RGB) or 4 (RGBA) bands"

[[3DEP-Ortho.geokey]]
geokey = 1025
description = "GT Raster Type GeoKey"
data_type = "integer"
constraint = "exact"
expected = 1
comment = "Orthoimagery uses PixelIsArea"

[[3DEP-Ortho.gdal_metadata]]
name = "AREA_OR_POINT"
description = "Pixel Interpretation"
data_type = "string"
constraint = "exact"
expected = "Area"
comment = "Orthoimagery uses PixelIsArea"

# ==============================================================================
# Copernicus DEM - Resolution-based product variants
# ==============================================================================

[COPDEM-30]
title = "Copernicus DEM 30m Resolution"
description = "Validation rules for 30m Copernicus DEM products"
author = "European Space Agency (ESA)"
updated = "2026-01-03"

[[COPDEM-30.tiff_tag]]
tag = 258
description = "Bits Per Sample"
data_type = "integer"
constraint = "exact"
expected = 32
comment = "32-bit float required"

[[COPDEM-30.geokey]]
geokey = 1025
description = "GT Raster Type GeoKey"
data_type = "integer"
constraint = "exact"
expected = 1
comment = "30m product uses PixelIsArea"

[[COPDEM-30.geokey]]
geokey = 4096
description = "Vertical Datum"
data_type = "integer"
constraint = "exact"
expected = 5773
comment = "5773 = EGM2008 geoid (EPSG:5773)"

# ==============================================================================

[COPDEM-90]
title = "Copernicus DEM 90m Resolution"
description = "Validation rules for 90m Copernicus DEM products"
author = "European Space Agency (ESA)"
updated = "2026-01-03"

[[COPDEM-90.tiff_tag]]
tag = 258
description = "Bits Per Sample"
data_type = "integer"
constraint = "exact"
expected = 32
comment = "32-bit float required"

[[COPDEM-90.geokey]]
geokey = 1025
description = "GT Raster Type GeoKey"
data_type = "integer"
constraint = "exact"
expected = 1
comment = "90m product uses PixelIsArea"

[[COPDEM-90.geokey]]
geokey = 4096
description = "Vertical Datum"
data_type = "integer"
constraint = "exact"
expected = 5773
comment = "5773 = EGM2008 geoid (EPSG:5773)"
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
1. [ ] XML metadata validation (XPath-based)
2. [ ] XMP metadata validation
3. [ ] GEO_METADATA validation
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
│   ├── test_product.toml       # Simple test rules
│   ├── conflicting_prod_a.toml # For conflict detection tests
│   └── conflicting_prod_b.toml
└── geotiffs/
    ├── valid_dged5.tif         # Passes all DGED5 rules
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

1. **No External XML** - xml_metadata rules, no `.xml` file → All rules FAIL with "Section is missing"
2. **Missing GDAL_METADATA Tag** - gdal_metadata rules, Tag 42112 not present → All rules FAIL
3. **Partial GeoKeys** - 10 geokey rules, only 3 present → 3 results based on values, 7 FAIL for missing keys

#### C. Message Differentiation Tests

1. **Wrong Value** - Tag exists but value wrong → "Tag X value Y does not match..."
2. **Missing Key** - Section exists but key missing → "Tag X is required but not present..."
3. **Missing Section** - Entire section absent → "Section is missing: ..."

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

# Generate Markdown report
gttk validate -i example.tif -p COPDEM-30 -f md
```

#### Batch Validation

```bash
# Validate all GeoTIFFs in a directory
gttk validate -i data/tiles/ -p DGED5

# Validate only files matching a name pattern
gttk validate -i data/mixed/ -p 3DEP-DSM -n DSM
```

#### Multi-Product Workflows

When a directory contains multiple product types, use `--name-string` to process each product separately:

```bash
# Validate DSM products
gttk validate -i delivery/ -p 3DEP-DSM -n DSM -o validation/dsm/

# Validate DTM products
gttk validate -i delivery/ -p 3DEP-DTM -n DTM -o validation/dtm/

# Validate orthoimagery
gttk validate -i delivery/ -p 3DEP-Ortho -n ortho -o validation/ortho/
```

This approach ensures that each product type is validated against its appropriate specification without requiring file reorganization.

#### Output

Validation reports are generated in the `validation/` directory (or custom location specified with `-o`). Files are automatically named with `_PASS` or `_FAIL` suffixes based on validation results:

```
validation/
├── example_PASS.html    # All validations passed
├── tile_001_FAIL.html   # One or more validations failed
└── tile_002_PASS.html
```

This naming convention enables automated workflows to identify non-compliant products through filesystem scanning or regex pattern matching.
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

**Example: USGS 3DEP Program**
- **3DEP-DSM**: Digital Surface Models (32-bit float, PixelIsPoint, general accuracy)
- **3DEP-DTM**: Digital Terrain Models (32-bit float, PixelIsPoint, stricter accuracy ≤15cm)
- **3DEP-Ortho**: Orthoimagery (8-bit unsigned int, 3-4 bands, PixelIsArea)

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
gttk validate -i delivery/ -p 3DEP-DSM -n DSM -o validation/dsm/
gttk validate -i delivery/ -p 3DEP-DTM -n DTM -o validation/dtm/
gttk validate -i delivery/ -p 3DEP-Ortho -n ortho -o validation/ortho/
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

- Successfully validate real DGED5, 3DEP-DSM, 3DEP-DTM, and COPDEM files
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
**Last Updated:** 2026-01-03  
**Status:** Ready for Phase 1 Implementation  
**Next Review:** After Phase 1 completion
