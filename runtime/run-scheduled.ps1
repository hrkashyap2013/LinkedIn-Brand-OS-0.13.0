<#
.SYNOPSIS
  Scheduled preparation runner (Windows PowerShell).
.DESCRIPTION
  Prepares 3 ideas for a slot and saves them to runs\YYYY-MM-DD-<slot>.md. Never publishes.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\run-scheduled.ps1 -Slot Mon
#>
[CmdletBinding()]
param(
  [string]$Slot = "",
  [ValidateSet('claude','codex')][string]$Tool = 'claude',
  [string]$Workspace = "",
  [switch]$Force
)
$ErrorActionPreference = 'Stop'
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Workspace) { $Workspace = Split-Path -Parent $Here }
Set-Location $Workspace
New-Item -ItemType Directory -Force -Path 'runs' | Out-Null
$Log = Join-Path 'runs' 'scheduler.log'
function Write-Log($m) { Add-Content -LiteralPath $Log -Value ("{0} {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $m) }

# Desktop / phone notification (only if you turned one on in the setup wizard). The text is short and
# generic: it never contains idea text. A notification problem can never fail a run.
function Send-Notice($Event, $Message) {
  if ($env:LBA_NOTIFY -eq '0') { return }
  $np = Join-Path $Here 'notify.py'
  if (-not (Test-Path -LiteralPath $np)) { return }
  $py = Get-Command python, python3, py -ErrorAction SilentlyContinue | Select-Object -First 1
  if (-not $py) { return }
  try { & $py.Source $np --workspace (Get-Location).Path --event $Event --message $Message *>> $Log } catch { }
}

if (-not $Slot) { $Slot = (Get-Date).DayOfWeek.ToString() }
$Slot = $Slot.Trim().Substring(0, [Math]::Min(3, $Slot.Trim().Length))
$Slot = (Get-Culture).TextInfo.ToTitleCase($Slot.ToLower())
$Date = Get-Date -Format 'yyyy-MM-dd'
$Out  = Join-Path 'runs' "$Date-$Slot.md"

if ((Test-Path -LiteralPath $Out) -and -not $Force) {
  Write-Log "skip $Slot ${Date}: already prepared ($Out)"; Write-Host "Already prepared: $Out (use -Force to redo)"; exit 0
}

$Role = '(blank)'; $Time = '(blank)'; $Found = $false
try {
  $cfg = Get-Content -Raw -LiteralPath 'docs\schedule.json' | ConvertFrom-Json
  foreach ($s in @($cfg.slots)) {
    if ($s.day -and ([string]$s.day).Substring(0, [Math]::Min(3, ([string]$s.day).Length)).ToLower() -eq $Slot.ToLower()) {
      $Found = $true
      if ($s.role) { $Role = [string]$s.role }
      if ($s.time) { $Time = [string]$s.time; if ($cfg.publish_utc_offset) { $Time = "$Time (UTC$($cfg.publish_utc_offset))" } }
      break
    }
  }
} catch { }
if (-not $Found) { Write-Log "no slot named $Slot in docs\schedule.json; running with blank role" }

if ($Tool -eq 'claude') {
  $Pointer = "Delegate each step to the matching Claude Code subagent (governance, brand-intelligence, content-intelligence, anti-repetition, idea-generation). The full orchestrator rules are in .claude/commands/scheduled.md if you need them."
  $Bin = if ($env:CLAUDE_BIN) { $env:CLAUDE_BIN } else { 'claude' }
} else {
  $Pointer = 'Use the Codex skills ($governance, $brand-intelligence, $content-intelligence, $anti-repetition, $idea-generation). The orchestrator rules are in AGENTS.md and $orchestrator.'
  $Bin = if ($env:CODEX_BIN) { $env:CODEX_BIN } else { 'codex' }
}

$Prompt = Get-Content -Raw -LiteralPath (Join-Path 'scripts' 'scheduled-prompt.md')
$Prompt = $Prompt.Replace('{{SLOT}}', $Slot).Replace('{{DATE}}', $Date).Replace('{{TIME}}', $Time).Replace('{{DAY_ROLE}}', $Role).Replace('{{POINTER}}', $Pointer)

if (-not (Get-Command $Bin -ErrorAction SilentlyContinue)) {
  $msg = "The '$Bin' command was not found on PATH for this scheduled run."
  Set-Content -LiteralPath (Join-Path 'runs' "$Date-$Slot.FAILED.md") -Value "# Scheduled preparation FAILED: $Slot $Date`n`n$msg"
  Write-Log "FAILED $Slot ${Date}: $msg"; Send-Notice 'failed' "Preparation for $Slot did not run: the $Bin command was not found."; Write-Error $msg; exit 1
}

Write-Log "start $Slot $Date via $Tool"
$extra = @()
if ($Tool -eq 'claude' -and $env:CLAUDE_EXTRA_ARGS) { $extra = $env:CLAUDE_EXTRA_ARGS -split '\s+' }
$ErrorActionPreference = 'Continue'
if ($Tool -eq 'claude') { $result = & $Bin -p $Prompt @extra 2>> $Log } else { $result = & $Bin exec $Prompt 2>> $Log }
$rc = $LASTEXITCODE
$ErrorActionPreference = 'Stop'
$text = ($result | Out-String).Trim()

if ($rc -ne 0 -or -not $text) {
  Set-Content -LiteralPath (Join-Path 'runs' "$Date-$Slot.FAILED.md") -Value "# Scheduled preparation FAILED: $Slot $Date`n`nThe tool exited with code $rc or returned no output. See runs\scheduler.log."
  Write-Log "FAILED $Slot $Date rc=$rc"; Send-Notice 'failed' "Preparation for $Slot failed. Open the runs folder to see why."; exit 1
}

$header = "# Scheduled preparation: $Slot $Date`n`nStatus: PREPARED. Waiting for you to select 1 idea. Nothing has been drafted, approved, or published.`n`n---`n`n"
Set-Content -LiteralPath $Out -Value ($header + $text) -Encoding UTF8
Write-Log "done $Slot $Date -> $Out"
Send-Notice 'prepared' "Your 3 post ideas for $Slot are ready. Open your workspace and pick one."
Write-Host "Prepared: $Out"
