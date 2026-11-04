param([string]$Script='scripts/create_cpu_ip.tcl')
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$binary='D:\AMD\Xilinx\vivado_2025.2\2025.2\Vivado\bin'
if ($env:SCOPE_VIVADO_BIN) { $binary=$env:SCOPE_VIVADO_BIN }
# A temporary drive alias avoids Vivado's non-ASCII path limitations.
# Files still reside under the requested folder; no files are moved.
$drive=@('R:','S:','T:','U:','V:') | Where-Object { -not (Test-Path "$_\") } | Select-Object -First 1
if (-not $drive) { throw 'No free drive alias available' }
subst $drive $root
if ($LASTEXITCODE -ne 0) { throw 'Drive alias failed' }
$oldLocation=Get-Location
try {
 Set-Location "$drive\"
 New-Item -ItemType Directory -Force -Path build/tool_tmp,build/tool_appdata | Out-Null
 $env:TEMP="$drive\build\tool_tmp"; $env:TMP=$env:TEMP
 $env:APPDATA="$drive\build\tool_appdata"
 $env:XILINX_TCLAPP_REPO=Join-Path (Split-Path $binary -Parent) 'data\XilinxTclStore'
 $env:XILINX_LOCAL_USER_DATA='NO'
 $tag=[System.IO.Path]::GetFileNameWithoutExtension($Script)
 & "$binary\vivado.bat" -mode batch -source $Script -log "reports/$tag.log" -journal "reports/$tag.jou"
 if ($LASTEXITCODE -ne 0) { throw "Offline stage failed; see reports/$tag.log" }
 $blockers=Select-String -LiteralPath "reports/$tag.log" -Pattern '^(ERROR:|CRITICAL WARNING:)'
 if ($blockers) { throw "Offline stage has error/critical messages; see reports/$tag.log" }
} finally {
 Set-Location $oldLocation
 subst $drive /d
}
