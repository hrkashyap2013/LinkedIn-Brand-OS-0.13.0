<#
.SYNOPSIS
  Register (or remove) the scheduled preparation runs in Windows Task Scheduler.
.DESCRIPTION
  Reads docs\schedule.json. Each slot's preparation starts LeadHours before its publish time.
  The lead time is never guessed: pass -LeadHours or set "prep_lead_hours" in the file.
  It also registers the reminder check (at sign-in and every 30 minutes), so a results-check reminder that came
  due while your computer was off still reaches you once it is back on.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\register-schedule.ps1 -LeadHours 12
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\register-schedule.ps1 -RemindersOnly
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\register-schedule.ps1 -Remove
#>
[CmdletBinding()]
param(
  [ValidateSet('claude','codex')][string]$Tool = 'claude',
  [double]$LeadHours = [double]::NaN,
  [string]$Workspace = "",
  [switch]$DryRun,
  [switch]$Remove,
  [switch]$RemindersOnly,
  [switch]$NoReminders
)
$ErrorActionPreference = 'Stop'
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Workspace) { $Workspace = Split-Path -Parent $Here }
$Prefix = 'LinkedInBrand-'

if ($Remove) {
  if ($DryRun) { Write-Host "(dry run) would remove scheduled tasks named $Prefix*"; exit 0 }
  Get-ScheduledTask -TaskName "$Prefix*" -ErrorAction SilentlyContinue | Unregister-ScheduledTask -Confirm:$false
  Write-Host "Removed scheduled runs."; exit 0
}

function Register-Reminders([switch]$DryRunOnly) {
  if ($DryRunOnly) { Write-Host "Reminder check: at sign-in and every 30 minutes (task ${Prefix}Reminders)"; return }
  Write-Host "Reminder check: at sign-in and every 30 minutes (task ${Prefix}Reminders)"
  if ($DryRun) { return }
  $py = Get-Command python, python3, py -ErrorAction SilentlyContinue | Select-Object -First 1
  if (-not $py) { Write-Error 'Python 3 was not found on PATH, so the reminder check could not be registered.'; exit 1 }
  $rscript = Join-Path $Workspace 'scripts\reminders.py'
  $action = New-ScheduledTaskAction -Execute $py.Source -Argument "`"$rscript`" tick" -WorkingDirectory $Workspace
  $t1 = New-ScheduledTaskTrigger -AtLogOn
  $t2 = New-ScheduledTaskTrigger -Once -At ([datetime]::Today) -RepetitionInterval (New-TimeSpan -Minutes 30) -RepetitionDuration (New-TimeSpan -Days 3650)
  $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries
  Register-ScheduledTask -TaskName "${Prefix}Reminders" -Action $action -Trigger @($t1, $t2) -Settings $settings `
    -Description 'LinkedIn brand agents: fires results-check reminders that are due. Never publishes.' -Force | Out-Null
  Write-Host "Registered task ${Prefix}Reminders"
}

if ($RemindersOnly) {
  Register-Reminders
  if ($DryRun) { Write-Host "(dry run - Task Scheduler not changed)" } else { Write-Host "Done." }
  exit 0
}

$cfg = Get-Content -Raw -LiteralPath (Join-Path $Workspace 'docs\schedule.json') | ConvertFrom-Json
$slots = @($cfg.slots)
if ($slots.Count -eq 0) { Write-Error "docs\schedule.json has no slots. Add your publishing days first."; exit 1 }
if (-not $cfg.publish_utc_offset) { Write-Error 'Set "publish_utc_offset" (for example "+05:30") in docs\schedule.json.'; exit 1 }
$lead = $LeadHours
if ([double]::IsNaN($lead) -and $null -ne $cfg.prep_lead_hours -and "$($cfg.prep_lead_hours)" -ne '') { $lead = [double]$cfg.prep_lead_hours }
if ([double]::IsNaN($lead)) { Write-Error 'The preparation lead time is not set. Pass -LeadHours N or set "prep_lead_hours" in docs\schedule.json. It is not guessed.'; exit 1 }

$offText = [string]$cfg.publish_utc_offset
$sign = if ($offText.StartsWith('-')) { -1 } else { 1 }
$parts = $offText.TrimStart('+', '-').Split(':')
$offset = [TimeSpan]::new($sign * [int]$parts[0], $sign * [int]$parts[1], 0)
$days = @('Mon','Tue','Wed','Thu','Fri','Sat','Sun')
$nowAt = [DateTimeOffset]::UtcNow.ToOffset($offset)

$plan = @()
foreach ($s in $slots) {
  $d = ([string]$s.day).Substring(0, 3)
  $d = $d.Substring(0, 1).ToUpper() + $d.Substring(1).ToLower()
  if ($days -notcontains $d) { Write-Error "Unknown day in slot: $($s.day)"; exit 1 }
  $t = ([string]$s.time).Split(':')
  $nowIdx = (([int]$nowAt.DayOfWeek) + 6) % 7
  $delta = ($days.IndexOf($d) - $nowIdx + 7) % 7
  $date = $nowAt.Date.AddDays($delta)
  $publish = [DateTimeOffset]::new($date.Year, $date.Month, $date.Day, [int]$t[0], [int]$t[1], 0, $offset)
  $local = $publish.AddHours(-$lead).ToLocalTime()
  $plan += [pscustomobject]@{ Slot = $d; Day = $local.DayOfWeek; At = $local.TimeOfDay }
}

Write-Host "Scheduled preparation entries (computed in this machine's local time):"
$plan | ForEach-Object { Write-Host ("  {0}: starts {1} {2:hh\:mm}" -f $_.Slot, $_.Day, $_.At) }
if (-not $NoReminders) { Register-Reminders -DryRunOnly }
if ($DryRun) { Write-Host "(dry run - Task Scheduler not changed)"; exit 0 }

$script = Join-Path $Workspace 'scripts\run-scheduled.ps1'
foreach ($p in $plan) {
  $argText = "-NoProfile -ExecutionPolicy Bypass -File `"$script`" -Slot $($p.Slot) -Tool $Tool"
  $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $argText -WorkingDirectory $Workspace
  $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $p.Day -At ([datetime]::Today.Add($p.At))
  $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries
  Register-ScheduledTask -TaskName "$Prefix$($p.Slot)" -Action $action -Trigger $trigger -Settings $settings `
    -Description 'LinkedIn brand agents: scheduled preparation (3 ideas). Never publishes.' -Force | Out-Null
  Write-Host "Registered task $Prefix$($p.Slot)"
}
if (-not $NoReminders) { Register-Reminders }
Write-Host "Done. If your clock changes for daylight saving, run this again."
