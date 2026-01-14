# Setting Up Global Claude Code Settings

## Quick Setup

Run these commands in WSL to set up global Claude Code guidance:

```bash
# Create Claude Code config directory
mkdir -p ~/.config/claude-code

# Create global CLAUDE.md with Git workflow preferences
cat > ~/.config/claude-code/CLAUDE.md << 'EOF'
# Global Claude Code Guidance

## Git Workflow Preferences

### Commit Behavior
- NEVER commit changes unless explicitly requested by the user
- Always show `git status` and `git diff` before committing
- Use conventional commit format: `<type>: <description>`
  - Types: feat, fix, docs, style, refactor, test, chore
- Always include: `Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>`

### Commit Message Style
- Start with lowercase verb (add, fix, update, remove, refactor)
- Be concise (50 chars max for subject line)
- Focus on "why" not "what"
- Example: "fix: resolve WSL file opening for HTML reports"

### Before Committing (Required Steps)
1. Run `git status -uall` to see all changes (including untracked files)
2. Run `git diff` to review staged changes
3. Run `git diff HEAD` to review all uncommitted changes
4. Draft commit message and show to user
5. Ask user: "Should I commit with this message?"
6. Only proceed after explicit user approval

### Branch Management
- Always check current branch: `git branch --show-current`
- Never force push to main/master without explicit user request
- Create feature branches for new work: `git checkout -b feature/<name>`
- Use descriptive branch names: `feature/export-functionality`, `fix/metadata-bug`

### Pull Request Creation
1. Ensure all work is committed
2. Run `git status` to confirm clean working tree
3. Push branch: `git push -u origin <branch>`
4. Review commits in PR: `git log main..HEAD --oneline`
5. Create PR: `gh pr create --title "..." --body "..."`
6. Include comprehensive test plan in PR description

### Viewing Changes
When user asks to "review changes" or "show changes":
```bash
# Show status
git status

# Show staged changes
git diff --cached

# Show all uncommitted changes
git diff HEAD

# Show recent commits
git log --oneline -10

# Show specific commit
git show <commit-hash>
```

## WSL-Specific Guidance

### File Operations
- HTML reports should open in Windows default browser
- Markdown files should open in WSL VS Code
- Use `/mnt/c/...` paths for Windows filesystem access
- Be aware of performance differences when accessing Windows filesystem

### Cross-Platform Code
- Always consider Windows, macOS, Linux, and WSL environments
- Use `sys.platform` for platform detection
- Use WSL detection when needed (check `/proc/version` for "microsoft")
- Test platform-specific code paths when possible
- Avoid platform-exclusive APIs without fallbacks

### Path Handling
- Prefer `pathlib.Path` over `os.path` for cross-platform compatibility
- Use forward slashes in paths (pathlib handles conversion)
- Be mindful of case sensitivity (Linux/WSL vs Windows)

## Testing Preferences

### Default Test Behavior
- Run fast tests by default: `pytest -m "not slow"`
- Only run E2E tests when explicitly requested
- Run full test suite before major commits/PRs

### Test Commands
```bash
# Fast tests only (recommended default)
pytest -m "not slow"

# Unit tests only
pytest -m unit

# Integration tests
pytest -m integration

# E2E tests (slow)
pytest -m e2e

# Specific test file
pytest tests/unit/test_data_models.py

# Specific test
pytest tests/unit/test_data_models.py::TestTiffTag::test_instantiation

# With coverage
pytest --cov=gttk --cov-report=html
```

### Before Committing Code
- Run relevant tests based on changes made
- Include test results summary if tests were added/modified
- Never commit broken tests

## Code Style Preferences

### Python
- Follow PEP 8 conventions
- Use type hints for function signatures
- Prefer explicit over implicit
- Keep functions focused and small
- Use meaningful variable names (avoid single letters except loop indices)

### Documentation
- Update docstrings when changing function signatures
- Keep comments concise and relevant
- Prefer self-documenting code over excessive comments
- Update README/docs when adding features

### Error Handling
- Use specific exception types
- Log errors with context
- Provide helpful error messages
- Fail fast for critical errors

## Communication Preferences

### Status Updates
- Provide brief status updates for long-running operations
- Explain what you're doing before doing it
- Show command output for important operations
- Ask for confirmation before destructive actions

### Asking Questions
- Ask clarifying questions when requirements are ambiguous
- Present options when multiple approaches are viable
- Explain trade-offs when recommending an approach

### Reporting Results
- Summarize test results clearly
- Show relevant log excerpts for errors
- Provide file paths with line numbers when referencing code
- Use markdown formatting for readability

## File System Operations

### Creating Files
- Ask before creating new files unless clearly necessary
- Never create files in system directories without explicit request
- Verify parent directory exists before creating files
- Use appropriate file permissions

### Modifying Files
- Show diffs for significant changes
- Back up critical files if making risky changes
- Validate file syntax after editing (e.g., JSON, TOML, YAML)

### Deleting Files
- Always ask for confirmation before deleting files
- Explain what will be deleted and why
- Suggest `git` operations instead of direct deletion when applicable

## Security Considerations

### Credentials & Secrets
- Never commit credentials, API keys, or secrets
- Warn if detecting potential secrets in files
- Suggest using environment variables or config files
- Recommend `.gitignore` patterns for sensitive files

### File Permissions
- Use appropriate permissions (0o644 for files, 0o755 for executables)
- Warn about overly permissive permissions (0o777)

## Performance Considerations

### Long-Running Operations
- Provide progress updates for operations > 5 seconds
- Suggest alternatives if operation will be very slow
- Offer to run in background for very long operations

### Large Files
- Warn before processing very large files (> 1GB)
- Suggest chunked processing for large datasets
- Consider memory constraints

## Debugging Assistance

### Error Investigation
When user reports an error:
1. Ask for full error message and stack trace
2. Check recent code changes
3. Review relevant log files
4. Suggest debugging steps
5. Propose fixes with explanation

### Log Analysis
- Know where log files are located (project-specific)
- Use `grep`/`tail` for efficient log searching
- Suggest increasing log verbosity when needed

## Workspace Management

### Organization
- Keep workspace clean (no temporary files in repo)
- Suggest `.gitignore` additions when appropriate
- Organize related files in directories

### WSL ↔ Windows Coordination
- Understand when files need to be on Windows filesystem
- Suggest using `/mnt/c/...` for Windows-accessible files
- Coordinate Git operations between WSL and Windows repos

## Project-Specific Overrides

Note: Project-specific `CLAUDE.md` files will override these global settings.
Always prioritize project-level instructions when they conflict with global guidance.
EOF

# Display confirmation
cat ~/.config/claude-code/CLAUDE.md
```

## Verification

After setup, verify Claude Code can read the configuration:

```bash
# Check the file exists and is readable
ls -la ~/.config/claude-code/CLAUDE.md

# View the contents
cat ~/.config/claude-code/CLAUDE.md
```

## How It Works

### Configuration Hierarchy

1. **Global Config** (`~/.config/claude-code/CLAUDE.md`)
   - Applies to all projects
   - General preferences and workflows
   - Cross-cutting concerns (Git, testing, style)

2. **Project Config** (repo-level `CLAUDE.md`)
   - Project-specific instructions
   - Architecture details
   - Build/test commands
   - **Takes precedence over global config**

3. **Merged Context**
   - Claude Code reads both files
   - Project config overrides global config when conflicts exist
   - Complementary settings are merged

### Example Scenario

**Global Config Says:**
```markdown
- Run fast tests by default: `pytest -m "not slow"`
```

**Project Config Says:**
```markdown
- Always run full test suite before commits
```

**Result:** Project config takes precedence; full test suite runs before commits.

## Customization

Edit the global config to match your preferences:

```bash
# Edit global Claude Code config
nano ~/.config/claude-code/CLAUDE.md

# Or use VS Code
code ~/.config/claude-code/CLAUDE.md
```

### Common Customizations

#### Change Commit Message Format

```markdown
### Commit Message Style
- Use present tense (e.g., "Add feature" not "Added feature")
- Capitalize first letter
- No period at end of subject line
- Include ticket number: "[PROJ-123] Add new feature"
```

#### Add Custom Test Preferences

```markdown
### Test Commands
```bash
# Always run linting before tests
ruff check . && pytest

# Run tests with verbose output
pytest -v
```
```

#### Add Repository-Specific Paths

```markdown
### WSL Repository Locations
- Development: `~/dev/gttk`
- Windows Testing: `/mnt/c/Users/YourName/Documents/gttk`
- Sync command: `cd /mnt/c/Users/YourName/Documents/gttk && git pull`
```

## Sharing Configurations

### Team Sync

If working in a team, consider syncing global configurations:

```bash
# Export your config
cp ~/.config/claude-code/CLAUDE.md ~/gttk-claude-config.md

# Commit to shared team repo
git add gttk-claude-config.md
git commit -m "docs: add shared Claude Code config"
git push

# Team members can import
cp ~/shared-repo/gttk-claude-config.md ~/.config/claude-code/CLAUDE.md
```

### Version Control

Consider versioning your personal Claude config:

```bash
# Create a dotfiles repo
mkdir -p ~/dotfiles/.config/claude-code
cp ~/.config/claude-code/CLAUDE.md ~/dotfiles/.config/claude-code/

cd ~/dotfiles
git init
git add .
git commit -m "init: add Claude Code config"
git remote add origin <your-dotfiles-repo>
git push -u origin main
```

## Troubleshooting

### Claude Not Reading Config

**Issue:** Claude doesn't seem to follow global settings

**Solutions:**
1. Verify file location: `ls ~/.config/claude-code/CLAUDE.md`
2. Check file permissions: `chmod 644 ~/.config/claude-code/CLAUDE.md`
3. Verify syntax (valid Markdown)
4. Restart Claude Code session

### Conflicts Between Global and Project Config

**Issue:** Unclear which config is being used

**Solution:** Add explicit instructions in project `CLAUDE.md`:
```markdown
## Configuration Note
This project overrides the following global Claude settings:
- Test strategy: Always run full suite (global says "fast only")
- Commit style: Use ticket numbers (global doesn't specify)
```

### Config Not Working in Specific Project

**Issue:** Global config works elsewhere but not in one project

**Possible Causes:**
1. Project has its own `CLAUDE.md` that conflicts
2. Project is outside typical workspace
3. Permissions issue in project directory

**Solution:** Check project-level `CLAUDE.md`:
```bash
cat /path/to/project/CLAUDE.md
```

## Best Practices

### Keep It Focused
- Focus on workflow and preferences, not code
- Avoid overly prescriptive rules
- Allow flexibility for different projects

### Update Regularly
- Review and update quarterly
- Add lessons learned from common issues
- Remove outdated or unused guidance

### Document Exceptions
- Note when you deviate from global config in project configs
- Explain why different approach is needed
- Helps maintain consistency across projects

## Related Documentation

- **Git Workflow Guide:** `docs/GIT_WORKFLOW_WSL_WINDOWS.md`
- **Cross-Platform File Opening:** `docs/CROSS_PLATFORM_FILE_OPENING.md`
- **Project-Level Claude Config:** `CLAUDE.md` (repo root)

## Support

For issues or questions about Claude Code configuration:
- **Claude Code Docs:** https://claude.com/docs/code
- **GitHub Issues:** https://github.com/anthropics/claude-code/issues
- **Example Configs:** https://github.com/anthropics/claude-code/tree/main/examples
