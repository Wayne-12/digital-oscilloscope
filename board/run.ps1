param([ValidateSet('program','prepare_flash','program_flash','verify_flash_boot')][string]$Action='verify_flash_boot')
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
& python "$root/sim/verify_submission.py"
if($LASTEXITCODE -ne 0){throw 'Submission integrity failed'}
& python "$root/build/stage_workspace.py"
if($LASTEXITCODE -ne 0){throw 'Workspace staging failed'}
& "$root/build/work/display/run.ps1" -Action $Action
if($LASTEXITCODE -ne 0){throw 'Board action failed'}
