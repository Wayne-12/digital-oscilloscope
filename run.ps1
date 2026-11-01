param([ValidateSet('verify','ui','firmware','simulate','build')][string]$Action='verify')
$ErrorActionPreference='Stop'
$sourceRoot=Join-Path $PSScriptRoot 'source'
switch($Action) {
 'verify' { & python (Join-Path $sourceRoot 'VGA显示部分/verify_package.py'); if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}; & python (Join-Path $PSScriptRoot 'serve/verify_upload.py') }
 'ui' { & python (Join-Path $sourceRoot 'PC/ui/launch_scope.py') }
 'firmware' { & (Join-Path $sourceRoot 'VGA显示部分/build_firmware.ps1') }
 'simulate' { & (Join-Path $sourceRoot 'VGA显示部分/run.ps1') -Action simulate }
 'build' { & (Join-Path $sourceRoot 'VGA显示部分/run.ps1') -Action build }
}
if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
