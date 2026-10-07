<#
.SYNOPSIS
  LinkedIn Brand Agents - installer for Windows PowerShell.

.DESCRIPTION
  Installs the agents and slash commands for Claude Code.
  Safe to re-run. Agents/commands are updated in place (a timestamped .bak copy
  is kept if you edited them). Your own files (CLAUDE.md, docs\, memory\) are
  never overwritten.

.PARAMETER Project
  Install into <Project>\.claude and create <Project>\CLAUDE.md,
  <Project>\docs\brand-profile.md and <Project>\memory\ (existing files kept).
  Recommended.

.PARAMETER Global
  Install into $HOME\.claude (or $env:CLAUDE_CONFIG_DIR). This is the default
  if -Project is not given.

.PARAMETER Tool
  claude (default), codex, or all. Codex skills always go to $env:CODEX_HOME\skills
  (default $HOME\.codex\skills); with -Project a Codex workspace also gets an AGENTS.md.

.PARAMETER Check
  Verify an existing install and report problems. Changes nothing.

.PARAMETER DryRun
  Show what would happen without changing anything.

.PARAMETER Wizard
  With -Project: run the setup questions after installing (language, posting days and
  times, image provider, notifications). In a console the installer offers this by itself.

.PARAMETER NoWizard
  Never run or offer the setup questions.

.PARAMETER Auto
  Unattended install for AI assistants ("install <URL>"): workspace $env:LBA_WORKSPACE or $HOME\linkedin, both
  tools unless -Tool is given, no questions, and a short machine-readable result at the end.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\install.ps1 -Project C:\Users\you\linkedin

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\install.ps1 -Project C:\Users\you\linkedin -Tool all
#>
[CmdletBinding()]
param(
  [switch]$Global,
  [string]$Project = "",
  [ValidateSet('claude','codex','all')][string]$Tool = 'claude',
  [switch]$Check,
  [switch]$DryRun,
  [switch]$Wizard,
  [switch]$NoWizard,
  [switch]$Auto
)

$ErrorActionPreference = 'Stop'
$Src = Split-Path -Parent $MyInvocation.MyCommand.Path

if ($Auto) {
  $NoWizard = $true
  if (-not $Project -and -not $Global) { $Project = if ($env:LBA_WORKSPACE) { $env:LBA_WORKSPACE } else { Join-Path $HOME 'linkedin' } }
  if (-not $PSBoundParameters.ContainsKey('Tool')) { $Tool = 'all' }
}

$DoClaude = ($Tool -eq 'claude' -or $Tool -eq 'all')
$DoCodex  = ($Tool -eq 'codex'  -or $Tool -eq 'all')
if ($DoClaude -and (-not (Test-Path (Join-Path $Src '.claude\agents')) -or -not (Test-Path (Join-Path $Src '.claude\commands')))) {
  Write-Error "Run this script from inside a full clone/unzip of the repo (.claude\ not found next to it)."
  exit 1
}
if ($DoCodex -and -not (Test-Path (Join-Path $Src 'codex\skills'))) {
  Write-Error "codex\skills not found next to this script. Use a full clone/unzip of the repo."
  exit 1
}
if ($env:CODEX_HOME) { $CodexHome = $env:CODEX_HOME } else { $CodexHome = Join-Path $HOME '.codex' }
$CodexDest = Join-Path $CodexHome 'skills'
$LegacyNames = @('linkedin-content-planner','linkedin-idea-lock','linkedin-evidence-research','linkedin-post-drafter','linkedin-humanizer','linkedin-visual-producer','linkedin-strategy-audit','linkedin-publishing-package','linkedin-performance-review','linkedin-memory-manager','linkedin-strategy-review','linkedin-governance','linkedin-brand-intelligence','linkedin-content-intelligence','linkedin-anti-repetition','linkedin-idea-generation','linkedin-idea-selection','linkedin-research','linkedin-writing','linkedin-humanization','linkedin-visual-strategy','linkedin-visual-production','linkedin-visual-qa','linkedin-publishing','linkedin-measurement','linkedin-experiment','linkedin-learning','linkedin-strategy-learning','linkedin-orchestrator')

if ($Global -and $Project) { Write-Error "Use either -Global or -Project, not both."; exit 2 }

if ($Project) {
  $Mode = 'project'
  if (-not $DryRun -and -not $Check) { New-Item -ItemType Directory -Force -Path $Project | Out-Null }
  if (Test-Path $Project) { $WorkDir = (Resolve-Path $Project).Path } else { $WorkDir = $Project }
  $DestClaude = Join-Path $WorkDir '.claude'
} else {
  $Mode = 'global'
  if ($env:CLAUDE_CONFIG_DIR) { $DestClaude = $env:CLAUDE_CONFIG_DIR } else { $DestClaude = Join-Path $HOME '.claude' }
  $WorkDir = ''
}

$script:Installed = 0; $script:Updated = 0; $script:Unchanged = 0
$script:Kept = 0; $script:Missing = 0; $script:Differs = 0
$Stamp = Get-Date -Format 'yyyyMMddHHmmss'

function Same-Content($a, $b) {
  return ((Get-FileHash -Algorithm SHA256 -LiteralPath $a).Hash -eq (Get-FileHash -Algorithm SHA256 -LiteralPath $b).Hash)
}

function Do-Copy($from, $to) {
  if ($DryRun) { return }
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $to) | Out-Null
  Copy-Item -LiteralPath $from -Destination $to -Force
}

# Files this project owns: installed, and updated on re-run (with a backup).
function Install-Managed($from, $to, $label) {
  if ($Check) {
    if (-not (Test-Path -LiteralPath $to)) { Write-Host "  MISSING   $label"; $script:Missing++ }
    elseif (-not (Same-Content $from $to)) { Write-Host "  modified  $label (differs from repo version)"; $script:Differs++ }
    else { $script:Unchanged++ }
    return
  }
  if (-not (Test-Path -LiteralPath $to)) {
    Write-Host "  install   $label"; Do-Copy $from $to; $script:Installed++
  } elseif (Same-Content $from $to) {
    $script:Unchanged++
  } else {
    $bak = "$to.bak.$Stamp"
    Write-Host "  update    $label (backup: $(Split-Path -Leaf $bak))"
    if (-not $DryRun) { Copy-Item -LiteralPath $to -Destination $bak -Force }
    Do-Copy $from $to; $script:Updated++
  }
}

# Files that belong to the user: created once, never overwritten.
function Install-UserFile($from, $to, $label) {
  if ($Check) {
    if (-not (Test-Path -LiteralPath $to)) { Write-Host "  MISSING   $label"; $script:Missing++ }
    return
  }
  if (Test-Path -LiteralPath $to) {
    Write-Host "  keep      $label (already exists, not touched)"; $script:Kept++
  } else {
    Write-Host "  create    $label"; Do-Copy $from $to; $script:Installed++
  }
}

if ($Check) { Write-Host "Checking install" } else { Write-Host "Installing" }
if ($DryRun) { Write-Host "(dry run - nothing will be changed)" }

# Remove agents from earlier versions of this project so nothing is duplicated.
if (-not $Check) {
  foreach ($n in $LegacyNames) {
    $la = Join-Path $DestClaude "agents\$n.md"
    if ($DoClaude -and (Test-Path -LiteralPath $la)) {
      Write-Host "  remove    legacy agents/$n.md"; if (-not $DryRun) { Remove-Item -LiteralPath $la -Force }
    }
    $ls = Join-Path $CodexDest $n
    if ($DoCodex -and (Test-Path -LiteralPath $ls)) {
      Write-Host "  remove    legacy skills/$n"; if (-not $DryRun) { Remove-Item -LiteralPath $ls -Recurse -Force }
    }
  }
}

if ($DoClaude) {
  Write-Host "Claude Code -> $DestClaude"
  Write-Host "Agents:"
  Get-ChildItem -LiteralPath (Join-Path $Src '.claude\agents') -Filter *.md | ForEach-Object {
    Install-Managed $_.FullName (Join-Path $DestClaude "agents\$($_.Name)") "agents/$($_.Name)"
  }
  Write-Host "Commands:"
  Get-ChildItem -LiteralPath (Join-Path $Src '.claude\commands') -Filter *.md | ForEach-Object {
    Install-Managed $_.FullName (Join-Path $DestClaude "commands\$($_.Name)") "commands/$($_.Name)"
  }
}

if ($DoCodex) {
  Write-Host "Codex -> $CodexDest"
  $SkillsRoot = (Resolve-Path (Join-Path $Src 'codex\skills')).Path
  Get-ChildItem -LiteralPath $SkillsRoot -Recurse -File | Sort-Object FullName | ForEach-Object {
    $rel = $_.FullName.Substring($SkillsRoot.Length).TrimStart('\', '/')
    Install-Managed $_.FullName (Join-Path $CodexDest $rel) "skills/$($rel -replace '\\','/')"
  }
}

if ($Mode -eq 'project') {
  Write-Host "Workspace files in ${WorkDir}:"
  if ($DoClaude) { Install-UserFile (Join-Path $Src 'CLAUDE.md') (Join-Path $WorkDir 'CLAUDE.md') 'CLAUDE.md' }
  if ($DoCodex)  { Install-UserFile (Join-Path $Src 'AGENTS.md') (Join-Path $WorkDir 'AGENTS.md') 'AGENTS.md' }
  foreach ($f in 'brand-profile.md', 'schedule.json', 'schedule.example.json', 'settings.json', 'metrics-columns.json') {
    Install-UserFile (Join-Path $Src "docs\$f") (Join-Path $WorkDir "docs\$f") "docs/$f"
  }
  foreach ($f in 'FLOWCHART.md', 'CHANGES-FROM-MASTER.md', 'USER-GUIDE.md', 'TROUBLESHOOTING.md', 'SECURITY-AND-PRIVACY.md', 'VISUALS.md') {
    if (Test-Path -LiteralPath (Join-Path $Src "docs\$f")) { Install-Managed (Join-Path $Src "docs\$f") (Join-Path $WorkDir "docs\$f") "docs/$f" }
  }
  if (Test-Path -LiteralPath (Join-Path $Src 'VERSION')) { Install-Managed (Join-Path $Src 'VERSION') (Join-Path $WorkDir 'VERSION') 'VERSION' }
  Write-Host "Prompts for the apps and for any AI chat:"
  Get-ChildItem -LiteralPath (Join-Path $Src 'prompts') -Filter '*.md' -File | ForEach-Object {
    Install-Managed $_.FullName (Join-Path $WorkDir "prompts\$($_.Name)") "prompts/$($_.Name)"
  }
  Get-ChildItem -LiteralPath (Join-Path $Src 'memory') -File | ForEach-Object {
    Install-UserFile $_.FullName (Join-Path $WorkDir "memory\$($_.Name)") "memory/$($_.Name)"
  }
  foreach ($d in 'runs', 'drafts', 'inbox', 'reports') {
    Install-UserFile (Join-Path $Src "$d\README.md") (Join-Path $WorkDir "$d\README.md") "$d/README.md"
  }
  Write-Host "Automation scripts:"
  $RuntimeRoot = (Resolve-Path (Join-Path $Src 'runtime')).Path
  Get-ChildItem -LiteralPath $RuntimeRoot -Recurse -File | Where-Object { $_.FullName -notmatch '__pycache__' -and $_.Extension -ne '.pyc' } | Sort-Object FullName | ForEach-Object {
    $rel = $_.FullName.Substring($RuntimeRoot.Length).TrimStart('\', '/')
    Install-Managed $_.FullName (Join-Path $WorkDir "scripts\$rel") "scripts/$($rel -replace '\\','/')"
  }
}

$ClaudeOk = (-not $DoClaude) -or [bool](Get-Command claude -ErrorAction SilentlyContinue)
$CodexOk  = (-not $DoCodex)  -or [bool](Get-Command codex  -ErrorAction SilentlyContinue)
Write-Host ""

if ($Check) {
  Write-Host "Result: $script:Unchanged ok, $script:Differs modified, $script:Missing missing."
  if (-not $ClaudeOk) { Write-Host "Warning: the 'claude' command was not found on PATH (Claude Code not installed?)." }
  if (-not $CodexOk)  { Write-Host "Warning: the 'codex' command was not found on PATH (Codex not installed?)." }
  if ($script:Missing -eq 0) { Write-Host "OK"; exit 0 } else { Write-Host "Problems found. Re-run the installer to fix."; exit 1 }
}

Write-Host "Done: $script:Installed installed, $script:Updated updated, $script:Unchanged unchanged, $script:Kept kept."
if (-not $ClaudeOk) { Write-Host "Note: the 'claude' command was not found on PATH. Install Claude Code first: https://docs.claude.com" }
if (-not $CodexOk)  { Write-Host "Note: the 'codex' command was not found on PATH. Install Codex first." }

# --- setup questions (language, days and times, notifications) ----------------
if ($Mode -eq 'project' -and -not $NoWizard -and -not $DryRun) {
  $RunWizard = $false
  if ($Wizard) {
    $RunWizard = $true
  } elseif ([Environment]::UserInteractive -and -not [Console]::IsInputRedirected -and -not (Select-String -LiteralPath (Join-Path $WorkDir 'docs\settings.json') -Pattern '"setup_completed": true' -Quiet -ErrorAction SilentlyContinue)) {
    Write-Host ""
    $ans = Read-Host 'Answer a few setup questions now (language, posting days and times, notifications)? [Y/n]'
    if ($ans -notmatch '^(n|no)$') { $RunWizard = $true }
  }
  if ($RunWizard) {
    $py = Get-Command python, python3, py -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($py) {
      & $py.Source (Join-Path $WorkDir 'scripts\setup_wizard.py') --workspace $WorkDir
      if ($LASTEXITCODE -ne 0) { Write-Host "Setup was not completed. Run it any time:  python scripts\setup_wizard.py" }
    } else {
      Write-Host "Python was not found, so the setup questions were skipped. Install Python 3, then run:  python scripts\setup_wizard.py"
    }
  }
}

Write-Host ""
Write-Host "Next steps:"
if ($Mode -eq 'project') {
  if (Select-String -LiteralPath (Join-Path $WorkDir 'docs\settings.json') -Pattern '"setup_completed": true' -Quiet -ErrorAction SilentlyContinue) {
    Write-Host "  1. Fill in $WorkDir\docs\brand-profile.md.  (Change your setup any time:  python scripts\setup_wizard.py)"
  } else {
    Write-Host "  1. Run the setup questions:  python scripts\setup_wizard.py   then fill in $WorkDir\docs\brand-profile.md"
  }
  Write-Host "  2. cd `"$WorkDir`""
  if ($DoClaude) { Write-Host "  3. Run: claude    then type /auto  (or /scheduled, or /next one stage at a time)" }
  if ($DoCodex)  { Write-Host "  3. Run: codex     then ask: Use `$linkedin-orchestrator to run my next post" }
  Write-Host "  4. Optional automatic weekly preparation (after step 1):"
  Write-Host "       powershell -ExecutionPolicy Bypass -File scripts\register-schedule.ps1 -LeadHours N"
} else {
  Write-Host "  1. Create a workspace too:  .\install.ps1 -Project `$HOME\linkedin -Tool $Tool"
  Write-Host "  2. Fill in its docs\brand-profile.md and docs\schedule.json, then start your tool inside it."
}
Write-Host "Try it without an AI account:  python scripts\demo.py     Start the app:  python scripts\chat_app.py"
Write-Host "Nothing is ever posted automatically: no agent has a tool that can publish to LinkedIn."
if ($Auto) {
  $DocState = 'skipped'
  $DoctorPath = Join-Path $WorkDir 'scripts\doctor.py'
  if (-not $DryRun -and (Test-Path -LiteralPath $DoctorPath)) {
    Write-Host ""
    Write-Host "Doctor (checks your setup; it never changes anything):"
    $pyd = Get-Command python, python3, py -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($pyd) {
      $env:PYTHONDONTWRITEBYTECODE = '1'
      $docOut = & $pyd.Source $DoctorPath --workspace $WorkDir 2>&1 | Out-String
      $docRc = $LASTEXITCODE
      Write-Host $docOut.TrimEnd()
      if ($docRc -ne 0) { $DocState = 'problems' } elseif ($docOut -match '(?m)^WARN') { $DocState = 'attention' } else { $DocState = 'ok' }
    } else { Write-Host "Python was not found, so the doctor could not run."; $DocState = 'skipped' }
  }
  Write-Host ""
  Write-Host "AUTO-INSTALL-RESULT"
  Write-Host "status: ok"
  Write-Host "workspace: $WorkDir"
  Write-Host "tools: $Tool"
  if ($DoCodex) { Write-Host "codex_skills: $CodexDest" }
  Write-Host ("claude_found: " + $(if ($ClaudeOk) { 'yes' } else { 'no' }))
  Write-Host ("codex_found: " + $(if ($CodexOk) { 'yes' } else { 'no' }))
  Write-Host "doctor: $DocState"
  Write-Host "next: ask the owner the setup questions (INSTALL.md step 4), save answers.json, then run: python `"$WorkDir\scripts\setup_wizard.py`" --workspace `"$WorkDir`" --answers answers.json"
}
