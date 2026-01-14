# Cross-Platform File Opening Implementation

## Overview

GTTK now has robust cross-platform file opening that handles:
- **Native Windows**: Traditional `os.startfile()` behavior
- **macOS**: Uses `open` command
- **Native Linux**: Uses `xdg-open`
- **WSL (Windows Subsystem for Linux)**: Intelligent file-type-based routing

## Implementation Details

### Location
`gttk/utils/path_helpers.py` - `open_file(filename: str)`

### WSL-Specific Behavior

When running in WSL, `open_file()` detects the file extension and routes accordingly:

| File Type | Opens In | Command Used |
|-----------|----------|--------------|
| `.html` | Windows default browser | `cmd.exe /c start` (via Popen) |
| `.md`, `.markdown` | WSL VS Code | `code` |
| Other files | Windows default application | `cmd.exe /c start` (via Popen) |

### Path Conversion

WSL Linux paths are automatically converted to Windows UNC paths using the `wslpath` utility:
- **Input:** `/home/robeckgeo/dev/gttk/input/report.html`
- **Output:** `\\wsl.localhost\Ubuntu\home\robeckgeo\dev\gttk\input\report.html`

The `wslpath -w` utility handles:
- Automatic distribution detection
- Proper path format conversion
- Both modern (`wsl.localhost`) and legacy (`wsl$`) path formats

## Tools Updated

All four GTTK tools now use the cross-platform `open_file()` helper:

### ✅ `gttk read` (read_metadata.py)
- **Line 28:** `from gttk.utils.path_helpers import open_file`
- **Line 339:** `open_file(output_path)`
- Status: ✅ **Already using helper**

### ✅ `gttk compare` (compare_compression.py)
- **Line 25:** `from gttk.utils.path_helpers import open_file`
- **Line 147:** `open_file(report_path)`
- Status: ✅ **Updated to use helper**

### ✅ `gttk test` (test_compression.py)
- **Line 47:** `from gttk.utils.path_helpers import open_file`
- **Line 1327:** `open_file(args.output_path)`
- Status: ✅ **Updated to use helper**

### ✅ `gttk optimize` (optimize_compression.py)
- Status: ✅ **No report opening (by design)**

## ArcGIS Pro Toolbox Integration

The ArcGIS Pro Python Toolbox (`toolbox/GTTK_Toolbox.pyt`) has full integration:

### All Four Tools Support `open_report` Parameter:
1. **CompareCompression** (Line 193-199)
2. **OptimizeCompression** (Line 513-519)
3. **TestCompression** (Line 934-940)
4. **ReadMetadata** (Line 1152-1158)

### Workflow:
1. User checks "Open Report on Completion" in ArcGIS Pro toolbox
2. Toolbox passes `open_report=True` to the tool's `Arguments` dataclass
3. Tool generates report and calls `open_file(report_path)`
4. Report opens in Windows default application (ArcGIS Pro is Windows-only)

## Usage Examples

### Command Line (WSL)

```bash
# Read metadata - opens HTML in Windows browser
gttk read input/file.tif --report-format html --open-report true

# Read metadata - opens Markdown in WSL VS Code
gttk read input/file.tif --report-format md --open-report true

# Compare files - opens HTML in Windows browser
gttk compare input/baseline.tif input/optimized.tif --open-report true

# Test compression - opens Excel in Windows
gttk test input/file.tif output/test.xlsx --open-report true
```

### Command Line (Native Windows)

```bash
# All commands open reports in Windows default applications
gttk read input\file.tif --open-report true
gttk compare input\baseline.tif input\optimized.tif --open-report true
```

### Python API

```python
from gttk.utils.path_helpers import open_file

# Open any file with appropriate system default
open_file("/home/user/report.html")  # WSL → Windows browser
open_file("/home/user/notes.md")     # WSL → VS Code
open_file("C:\\Users\\user\\report.html")  # Windows → Default browser
```

## Error Handling

The `open_file()` function includes robust error handling:

```python
try:
    open_file(report_path)
    logger.info(f"Opened report: {report_path}")
except Exception as e:
    logger.warning(f"Could not open report: {e}")
```

This ensures that:
- Missing applications don't crash the tool
- Users get clear error messages
- Report generation still succeeds even if opening fails

## Testing

### Manual Testing

```bash
# Test WSL HTML opening
echo "<html><body>Test</body></html>" > /tmp/test.html
python -c "from gttk.utils.path_helpers import open_file; open_file('/tmp/test.html')"
# Should open in Windows browser

# Test WSL Markdown opening
echo "# Test" > /tmp/test.md
python -c "from gttk.utils.path_helpers import open_file; open_file('/tmp/test.md')"
# Should open in WSL VS Code
```

### Automated Testing

The existing E2E tests all use `--open-report false` to avoid opening files during automated tests:

```python
# Example from tests/e2e/test_read_command.py
result = subprocess.run([
    'gttk', 'read', geotiff,
    '--open-report', 'false'  # Prevents file opening during tests
])
```

## Platform Detection

### WSL Detection

```python
def _is_wsl() -> bool:
    """Detect if running in Windows Subsystem for Linux."""
    try:
        with open('/proc/version', 'r') as f:
            return 'microsoft' in f.read().lower()
    except (OSError, IOError):
        return False
```

This checks `/proc/version` for "microsoft" string, which is present in all WSL distributions.

### Distribution Name Detection

```python
def _convert_wsl_path_to_windows(wsl_path: str) -> str:
    """Convert WSL Linux path to Windows UNC path."""
    # Attempts to detect distribution name via wsl.exe
    # Falls back to 'Ubuntu' if detection fails
```

## Known Limitations

### WSL-Specific:
1. **Performance:** File opening may be slightly slower due to cross-system calls
2. **Path Conversion:** Assumes standard WSL distribution names (Ubuntu, Debian, etc.)
3. **VS Code Requirement:** Markdown opening requires `code` command in PATH

### General:
1. **Application Availability:** Requires default applications to be installed
2. **File Type Associations:** Relies on system file associations being configured correctly

## Troubleshooting

### Issue: "command not found: code" in WSL
**Solution:** Install VS Code and enable WSL integration:
```bash
# In VS Code, run: "Remote-WSL: New Window"
# Or install code command manually
```

### Issue: HTML opens in text editor instead of browser
**Solution:** WSL file associations don't apply; the function uses Windows defaults via `cmd.exe`

### Issue: "Could not open report" error
**Solution:** Check the log for specific error details:
```bash
cat gttk.log | grep "Could not open report"
```

### Issue: "embedded null byte" error
**Solution:** This was caused by UTF-16 encoding in `wsl.exe -l -v` output. Fixed by using `wslpath` utility instead.

### Issue: File opening command times out
**Solution:** Use `subprocess.Popen` instead of `subprocess.run` to avoid waiting for the application to close.

## Future Enhancements

Potential improvements for future versions:

1. **Configurable Application Preferences:**
   ```toml
   # In config.toml
   [file_associations]
   html = "C:\\Program Files\\Google\\Chrome\\chrome.exe"
   md = "code"
   ```

2. **Fallback Application Chain:**
   ```python
   # Try multiple applications in order
   browsers = ["firefox", "chrome", "microsoft-edge"]
   ```

3. **User Prompt for Missing Applications:**
   ```python
   if app_not_found:
       print(f"HTML viewer not found. Install a browser or view at: {path}")
   ```

## Related Files

- **Implementation:** `gttk/utils/path_helpers.py:31-100`
- **Usage:**
  - `gttk/tools/read_metadata.py:339`
  - `gttk/tools/compare_compression.py:147`
  - `gttk/tools/test_compression.py:1327`
- **Toolbox Integration:** `toolbox/GTTK_Toolbox.pyt`
- **Tests:** `tests/e2e/*.py` (all use `--open-report false`)

## Summary

The cross-platform file opening implementation provides:
✅ Seamless operation across Windows, macOS, Linux, and WSL
✅ Intelligent file-type routing in WSL
✅ Full ArcGIS Pro toolbox integration
✅ Robust error handling
✅ Consistent API across all GTTK tools
