<#
.SYNOPSIS
  LinkedIn Brand Agents - uninstaller for Windows PowerShell.

.DESCRIPTION
  Removes ONLY the agent and command files that this repo ships.
  Your CLAUDE.md, docs\ and memory\ (brand profile and post history) are never deleted.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\uninstall.ps1 -Global

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\uninstall.ps1 -Project C:\Users\you\linkedin
#>
[CmdletBinding()]
param(
  [switch]$Global,
  [string]$Project = "",
  [ValidateSet('claude','codex','all')][string]$Tool = 'claude',
  [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$Src = Split-Path -Parent $MyInvocation.MyCommand.Path

if (-not $Global -and -not $Project) { Write-Error "Specify -Global or -Project <dir>."; exit 2 }
if ($Global -and $Project) { Write-Error "Use either -Global or -Project, not both."; exit 2 }
if (-not (Test-Path (Join-Path $Src '.claude\agents')) -and -not (Test-Path (Join-Path $Src 'codex\skills'))) {
  Write-Error "Run this from inside a full copy of the repo (needed to know which files to remove)."
  exit 1
}
$DoClaude = ($Tool -eq 'claude' -or $Tool -eq 'all')
$DoCodex  = ($Tool -eq 'codex'  -or $Tool -eq 'all')

if ($Project) {
  $DestClaude = Join-Path $Project '.claude'
} elseif ($env:CLAUDE_CONFIG_DIR) {
  $DestClaude = $env:CLAUDE_CONFIG_DIR
} else {
  $DestClaude = Join-Path $HOME '.claude'
}

$Removed = 0
$LegacyNames = @('linkedin-content-planner','linkedin-idea-lock','linkedin-evidence-research','linkedin-post-drafter','linkedin-humanizer','linkedin-visual-producer','linkedin-strategy-audit','linkedin-publishing-package','linkedin-performance-review','linkedin-memory-manager','linkedin-strategy-review','linkedin-governance','linkedin-brand-intelligence','linkedin-content-intelligence','linkedin-anti-repetition','linkedin-idea-generation','linkedin-idea-selection','linkedin-research','linkedin-writing','linkedin-humanization','linkedin-visual-strategy','linkedin-visual-production','linkedin-visual-qa','linkedin-publishing','linkedin-measurement','linkedin-experiment','linkedin-learning','linkedin-strategy-learning','linkedin-orchestrator')
if ($DryRun) { Write-Host "(dry run - nothing will be deleted)" }

if ($DoClaude) {
  Write-Host "Removing Claude Code files from: $DestClaude"
  foreach ($kind in 'agents', 'commands') {
    Get-ChildItem -LiteralPath (Join-Path $Src ".claude\$kind") -Filter *.md | ForEach-Object {
      $dst = Join-Path $DestClaude "$kind\$($_.Name)"
      if (Test-Path -LiteralPath $dst) {
        Write-Host "  remove    $kind/$($_.Name)"
        if (-not $DryRun) { Remove-Item -LiteralPath $dst -Force }
        $Removed++
      }
    }
  }
}

if ($DoCodex) {
  if ($env:CODEX_HOME) { $CodexHome = $env:CODEX_HOME } else { $CodexHome = Join-Path $HOME '.codex' }
  $CodexDest = Join-Path $CodexHome 'skills'
  Write-Host "Removing Codex skills from: $CodexDest"
  $SkillsRoot = (Resolve-Path (Join-Path $Src 'codex\skills')).Path
  Get-ChildItem -LiteralPath $SkillsRoot -Recurse -File | Sort-Object FullName | ForEach-Object {
    $rel = $_.FullName.Substring($SkillsRoot.Length).TrimStart('\', '/')
    $dst = Join-Path $CodexDest $rel
    if (Test-Path -LiteralPath $dst) {
      Write-Host "  remove    skills/$($rel -replace '\\','/')"
      if (-not $DryRun) { Remove-Item -LiteralPath $dst -Force }
      $Removed++
    }
  }
  if (-not $DryRun) {
    Get-ChildItem -LiteralPath $SkillsRoot -Directory | ForEach-Object {
      foreach ($d in (Join-Path $CodexDest "$($_.Name)\agents"), (Join-Path $CodexDest $_.Name)) {
        if ((Test-Path -LiteralPath $d) -and -not (Get-ChildItem -LiteralPath $d -Force)) { Remove-Item -LiteralPath $d }
      }
    }
  }
}

# also remove agents from earlier versions of this project
if ($env:CODEX_HOME) { $LCodexHome = $env:CODEX_HOME } else { $LCodexHome = Join-Path $HOME '.codex' }
foreach ($n in $LegacyNames) {
  $la = Join-Path $DestClaude "agents\$n.md"
  if ($DoClaude -and (Test-Path -LiteralPath $la)) {
    Write-Host "  remove    legacy agents/$n.md"; if (-not $DryRun) { Remove-Item -LiteralPath $la -Force }; $Removed++
  }
  $ls = Join-Path (Join-Path $LCodexHome 'skills') $n
  if ($DoCodex -and (Test-Path -LiteralPath $ls)) {
    Write-Host "  remove    legacy skills/$n"; if (-not $DryRun) { Remove-Item -LiteralPath $ls -Recurse -Force }; $Removed++
  }
}

Write-Host "Done: $Removed file(s) removed. Your CLAUDE.md, AGENTS.md, docs\, memory\ and runs\ were not touched."
Write-Host "Automation scripts in your workspace scripts\ folder were left in place. To stop automatic runs first run: scripts\register-schedule.ps1 -Remove, then delete scripts\ yourself if you like."
