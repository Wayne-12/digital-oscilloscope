[CmdletBinding()]
param([string]$VivadoBin)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'vivado_toolchain.ps1')
$VivadoBin = Resolve-ScopeVivadoBin -RequestedBin $VivadoBin
$project = Join-Path (Split-Path -Parent $PSScriptRoot) 'project/scope_smoke/scope_smoke.xpr'
if (-not (Test-Path -LiteralPath $project -PathType Leaf)) { throw "Missing project: $project" }
# Use this launcher when the Windows .xpr association still selects an older Vivado.
& (Join-Path $VivadoBin 'vivado.bat') -mode gui $project
if ($LASTEXITCODE -ne 0) { throw "Vivado exited with code $LASTEXITCODE" }
