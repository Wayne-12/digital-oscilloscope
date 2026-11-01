param([ValidateSet('Verify','Hardware','Test','Build')][string]$Action='Verify')
$ErrorActionPreference='Stop'
$cpu=Split-Path $PSScriptRoot -Parent
$project=Split-Path $cpu -Parent
$panel=Join-Path $project 'VGA显示部分/板端独立版'
$python=Join-Path $project '.venv-ui/Scripts/python.exe'
function Check-Exit {if($LASTEXITCODE -ne 0){throw 'Current release check failed'}}
switch($Action){
 'Verify' {
  & $python (Join-Path $PSScriptRoot 'audit_current_version.py');Check-Exit
  & $python (Join-Path $panel 'verify_release.py');Check-Exit
 }
 'Hardware' {& $python (Join-Path $PSScriptRoot 'check_current_hardware.py');Check-Exit}
 'Test' {
  & (Join-Path $PSScriptRoot 'test_host.ps1')
  & (Join-Path $panel 'test_c.ps1')
  & $python -m unittest discover -s (Join-Path $project 'PC/tests');Check-Exit
 }
 'Build' {
  & (Join-Path $panel 'test_c.ps1')
  & (Join-Path $panel 'build_firmware.ps1')
  & $python (Join-Path $panel 'verify_release.py') snapshot;Check-Exit
  & (Join-Path $panel 'run.ps1') -Action simulate
  & (Join-Path $panel 'run.ps1') -Action build
  & $python (Join-Path $panel 'verify_release.py');Check-Exit
 }
}
# This entry never downloads the FPGA image or writes configuration Flash.
