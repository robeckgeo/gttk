# Git Workflow Coordination: WSL ↔ Windows

This guide explains how to coordinate Git operations between WSL (development) and Windows (testing/deployment) for the GTTK project.

## Problem Statement

When developing in WSL but targeting Windows users (ArcGIS Pro), you need to:
1. Develop and commit changes in WSL
2. Test changes in native Windows (ArcGIS Pro)
3. Avoid manual file transfers for large GeoTIFF files
4. Keep both environments synchronized

## Recommended Approach

### Option 1: Direct Windows Repository Access from WSL (Recommended)

**Pros:** Simple, no redundant repositories, instant sync
**Cons:** Slower Git operations due to cross-filesystem overhead

#### Setup:
```bash
# In WSL, clone the repo to a Windows-accessible location
cd /mnt/c/Users/YourName/Documents/
git clone https://github.com/robeckgeo/gttk.git

# Create symbolic link from WSL home for convenience
ln -s /mnt/c/Users/YourName/Documents/gttk ~/gttk-windows

# Always work in the /mnt/c location to ensure Windows can access it
cd /mnt/c/Users/YourName/Documents/gttk
```

#### Workflow:
1. **Develop in WSL:** `cd /mnt/c/Users/YourName/Documents/gttk`
2. **Commit & Push:** `git add . && git commit -m "message" && git push`
3. **Test in Windows:** Files are immediately available in `C:\Users\YourName\Documents\gttk`
4. **No sync needed:** Both environments share the same files

---

### Option 2: Separate WSL + Windows Repositories with Auto-Sync

**Pros:** Better Git performance in WSL
**Cons:** Requires sync mechanism, potential for conflicts

#### Setup:
```bash
# WSL repository (development)
cd ~/dev
git clone https://github.com/robeckgeo/gttk.git

# Windows repository (testing)
# In Windows PowerShell or Command Prompt:
cd C:\Users\YourName\Documents
git clone https://github.com/robeckgeo/gttk.git
```

#### Manual Sync Workflow:
```bash
# In WSL (after development)
git add .
git commit -m "Your commit message"
git push

# In Windows (before testing)
git pull
```

#### Automated Sync (PowerShell Script)

Create `C:\Users\YourName\Documents\gttk\sync-from-git.ps1`:

```powershell
# Automated Git Pull Script for Windows
$repoPath = "C:\Users\YourName\Documents\gttk"
$logFile = "$repoPath\sync-log.txt"

Set-Location $repoPath
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

Write-Output "[$timestamp] Starting Git pull..." | Out-File -Append $logFile

try {
    $output = git pull 2>&1
    Write-Output "[$timestamp] $output" | Out-File -Append $logFile

    if ($LASTEXITCODE -eq 0) {
        Write-Output "[$timestamp] Pull successful" | Out-File -Append $logFile
    } else {
        Write-Output "[$timestamp] Pull failed with exit code $LASTEXITCODE" | Out-File -Append $logFile
    }
} catch {
    Write-Output "[$timestamp] Error: $_" | Out-File -Append $logFile
}
```

Schedule this script using Windows Task Scheduler:
- Trigger: On workstation unlock (or every 5 minutes)
- Action: `powershell.exe -ExecutionPolicy Bypass -File "C:\Users\YourName\Documents\gttk\sync-from-git.ps1"`

---

### Option 3: Claude Code Automated Sync (Advanced)

You can use Git hooks to trigger Windows pulls automatically.

#### Setup Git Hook in WSL:

Create `.git/hooks/post-push` in your WSL repository:

```bash
#!/bin/bash
# Post-push hook to notify Windows to pull changes

WINDOWS_REPO="/mnt/c/Users/YourName/Documents/gttk"

if [ -d "$WINDOWS_REPO" ]; then
    echo "Triggering Windows repository sync..."
    cd "$WINDOWS_REPO" && git pull
    echo "Windows repository synced!"
else
    echo "Warning: Windows repository not found at $WINDOWS_REPO"
fi
```

Make it executable:
```bash
chmod +x .git/hooks/post-push
```

**Note:** This requires Git operations in the Windows repository to work from WSL (via `/mnt/c`).

---

## Best Practices for Claude Code and Git

### General Git Workflow with Claude

#### When Claude Should Commit:
- **User explicitly requests it:** "Create a commit with these changes"
- **After major feature completion:** When the user asks to commit
- **Before creating a PR:** Always commit staged work first

#### When Claude Should NOT Commit:
- **During active development:** Don't commit after every file edit
- **Without explicit request:** Never auto-commit without asking
- **With unreviewed changes:** Let the user review before committing

### Recommended Claude Prompts for Git Operations

#### Committing Changes:
```
"Review the changes I've made and create a commit with an appropriate message"
```

#### Creating Pull Requests:
```
"Create a pull request for the current branch against main"
```

#### Viewing Git Status:
```
"Show me the current git status and uncommitted changes"
```

#### Branch Management:
```
"Create a new feature branch called <branch-name> and switch to it"
```

---

## Global Claude Settings (~/.config/claude-code/CLAUDE.md)

Create `~/.config/claude-code/CLAUDE.md` for cross-project guidance:

```markdown
# Global Claude Code Guidance

## Git Workflow Preferences

### Commit Behavior
- NEVER commit changes unless explicitly requested
- Always show `git status` and `git diff` before committing
- Use conventional commit format: `<type>: <description>`
  - Types: feat, fix, docs, style, refactor, test, chore
- Always include Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>

### Commit Message Style
- Start with lowercase verb (add, fix, update, remove, refactor)
- Be concise (50 chars max for subject)
- Focus on "why" not "what"
- Example: "fix: resolve WSL file opening for HTML reports"

### Before Committing (Required Steps)
1. Run `git status` to see all changes
2. Run `git diff` to review changes
3. Draft commit message showing user
4. Ask user: "Should I commit with this message?"
5. Only commit after user approval

### Branch Management
- Always check current branch before committing: `git branch --show-current`
- Never force push to main/master
- Create feature branches for new work: `git checkout -b feature/<name>`

### Pull Request Creation
1. Ensure all work is committed
2. Push branch to remote: `git push -u origin <branch>`
3. Review all commits that will be in PR: `git log main..HEAD`
4. Create PR with: `gh pr create --title "..." --body "..."`
5. Include test plan in PR description

## WSL-Specific Guidance

### File Paths
- HTML files should open in Windows default browser
- Markdown files should open in WSL VS Code
- Use `/mnt/c/...` for Windows filesystem access

### Cross-Platform Development
- Always test platform-specific code on both WSL and Windows
- Use `sys.platform` and WSL detection for conditional behavior
- Avoid Windows-only APIs (like `os.startfile`) without fallbacks

## Testing Before Commits
- Run relevant tests before committing: `pytest -m unit`
- Run fast tests by default: `pytest -m "not slow"`
- Only run E2E tests when explicitly requested
- Include test results in commit message if test-related changes
```

---

## Setting Up Global Claude Guidance

### Create the global configuration:

```bash
# Create Claude Code config directory
mkdir -p ~/.config/claude-code

# Create global CLAUDE.md
nano ~/.config/claude-code/CLAUDE.md
```

Paste the content from the "Global Claude Settings" section above.

### Claude Code will automatically:
- Read project-level `CLAUDE.md` (in your repo)
- Read global `~/.config/claude-code/CLAUDE.md`
- Merge both sets of instructions
- Prioritize project-level instructions over global ones

---

## Coordinating Claude for Git Operations

### Example 1: Making Changes and Committing

**User:** "Fix the bug in metadata extraction and commit it"

**Claude's Process:**
1. Fix the bug
2. Run tests
3. Run `git status`
4. Run `git diff`
5. Draft commit message
6. Show message to user
7. Ask: "Should I commit with this message?"
8. After approval: `git add . && git commit -m "..."`

### Example 2: Creating a Feature Branch

**User:** "Create a feature branch for adding export functionality"

**Claude's Process:**
1. `git checkout -b feature/export-functionality`
2. Confirm: "Created and switched to branch feature/export-functionality"

### Example 3: Syncing Windows Repo

**User:** "I've pushed changes, sync the Windows repo"

**Claude's Process:**
1. Detect approach (Option 1, 2, or 3)
2. If Option 1: "Windows repo is already synced (same filesystem)"
3. If Option 2: Run `cd /mnt/c/Users/.../gttk && git pull`
4. Confirm: "Windows repository synced with latest changes"

---

## Testing the Setup

### Test WSL → Windows File Access:
```bash
# In WSL
echo "test" > /mnt/c/Users/YourName/test.txt

# In Windows
type C:\Users\YourName\test.txt
```

### Test Git Operations:
```bash
# In WSL
cd ~/dev/gttk
git status
git log --oneline -5

# In Windows (if using Option 2)
cd C:\Users\YourName\Documents\gttk
git status
git log --oneline -5
```

### Test File Opening:
```bash
# In WSL
cd ~/dev/gttk
gttk read input/test.tif --open-report true
# HTML should open in Windows browser
```

---

## Troubleshooting

### Issue: "Permission denied" when accessing `/mnt/c/...`
**Solution:** Check Windows file permissions, ensure WSL has read/write access

### Issue: Git commands slow in `/mnt/c/...`
**Solution:** This is expected due to cross-filesystem overhead. Consider Option 2 if speed is critical.

### Issue: Line ending conflicts (CRLF vs LF)
**Solution:** Configure Git to handle line endings:
```bash
# In WSL
git config --global core.autocrlf input

# In Windows
git config --global core.autocrlf true
```

### Issue: Windows repo not auto-syncing
**Solution:** Check Task Scheduler is running the PowerShell script, review `sync-log.txt`

---

## Summary

**Recommended Approach:** Option 1 (Direct Windows Access from WSL)
- Simplest setup
- No sync needed
- Both environments access same files
- Slight performance overhead acceptable for most workflows

**When to Use Option 2:**
- Git performance critical
- Large repositories
- Frequent Git operations

**When to Use Option 3:**
- Advanced users
- Automated workflows
- CI/CD integration
