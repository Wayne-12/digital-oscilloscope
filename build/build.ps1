param([ValidateSet('stage','cpu_ip','firmware','simulate','build')][string]$Action='stage')
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
& python "$PSScriptRoot/stage_workspace.py"
if($LASTEXITCODE -ne 0){throw 'Workspace staging failed'}
$work=Join-Path $PSScriptRoot 'work'
switch($Action){
 'cpu_ip' { & "$work/cpu/scripts/run_cpu_ip.ps1" }
 'firmware' { & "$work/display/test_c.ps1"; if($LASTEXITCODE -ne 0){throw 'C tests failed'}; & "$work/display/build_firmware.ps1" }
 'simulate' { & "$work/display/test_c.ps1"; if($LASTEXITCODE -ne 0){throw 'C tests failed'}; & "$work/display/run.ps1" -Action simulate }
 'build' {
   & "$work/cpu/scripts/run_cpu_ip.ps1"; if($LASTEXITCODE -ne 0){throw 'CPU IP failed'}
   & "$work/display/test_c.ps1"; if($LASTEXITCODE -ne 0){throw 'C tests failed'}
   & "$work/display/build_firmware.ps1"; if($LASTEXITCODE -ne 0){throw 'Firmware failed'}
   & "$work/display/run.ps1" -Action build
 }
}
if($LASTEXITCODE -ne 0){throw "$Action failed"}
