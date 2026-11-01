#requires -Version 7.0
[CmdletBinding()]
param([string]$VivadoBin)
$ErrorActionPreference='Stop';Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot vivado_toolchain.ps1);$VivadoBin=Resolve-ScopeVivadoBin -RequestedBin $VivadoBin
$root=Split-Path -Parent $PSScriptRoot;$id=(Get-Date -Format yyyyMMdd_HHmmss)+'_'+[guid]::NewGuid().ToString('N').Substring(0,8)
$report=Join-Path $root "reports/innovation_synthesis/$id";$build=Join-Path ([IO.Path]::GetTempPath()) "innovation_synth_$id";$out=Join-Path $build artifacts
New-Item -ItemType Directory -Path $report,$out|Out-Null
$relative=@('rtl/common/scope_pkg.sv','rtl/common/multires_pkg.sv','rtl/common/protocol_pkg.sv','rtl/common/innovation_pkg.sv','rtl/measure/measure_udiv.sv','rtl/uart_proto/frame_tx.sv','rtl/innovation/relative_calibrator.sv','rtl/innovation/calibration_apply.sv','rtl/innovation/health_compare.sv','rtl/innovation/capture_moments.sv','rtl/innovation/capture_result_stream.sv','rtl/innovation/capture_result_uart.sv','scripts/check_innovation_synthesis.tcl')
$hashes=@(foreach($rel in $relative){$source=Join-Path $root $rel;$copy=Join-Path $build $rel;New-Item -ItemType Directory -Path (Split-Path -Parent $copy) -Force|Out-Null;Copy-Item -LiteralPath $source -Destination $copy;$h=(Get-FileHash -LiteralPath $source).Hash;if((Get-FileHash -LiteralPath $copy).Hash -ne $h){throw 'Staging changed bytes'};[pscustomobject]@{file=$rel;sha256=$h}})
$args=@('-mode','batch','-notrace','-source',(Join-Path $build scripts/check_innovation_synthesis.tcl),'-log',(Join-Path $out vivado.log),'-journal',(Join-Path $out vivado.jou),'-tclargs',$out,$build)
$verdict='FAIL';$failure=$null;$resources=$null
Push-Location -LiteralPath $build
try{
 $lines=@(& (Join-Path $VivadoBin vivado.bat) @args 2>&1);$exit=$LASTEXITCODE;$log=$lines -join [Environment]::NewLine;$log|Set-Content -LiteralPath (Join-Path $report console.log) -Encoding utf8
 if($exit -or $log -notmatch 'INNOVATION_OOC_SYNTH_PASS tops=6 latches=0 blackboxes=0' -or $log -match '(?im)^\s*(CRITICAL WARNING:|ERROR:|INNOVATION_OOC_SYNTH_FAIL)'){throw 'Incomplete synthesis or diagnostic'}
 $resources=@(Get-Content -LiteralPath (Join-Path $out resources.json) -Raw|ConvertFrom-Json)
 if($resources.Count -ne 6){throw 'Missing netlists'}
 foreach($h in $hashes){if((Get-FileHash -LiteralPath (Join-Path $root $h.file)).Hash -ne $h.sha256){throw 'Source changed during synthesis'}};$verdict='PASS'
}catch{$failure=$_.Exception.Message;throw}
finally{Pop-Location;Copy-Item -LiteralPath $out -Destination (Join-Path $report artifacts) -Recurse;[pscustomobject]@{verdict=$verdict;part='xc7a35tcsg324-1';resources=$resources;source_sha256=$hashes;temporary_build=$build;tool=Join-Path $VivadoBin vivado.bat;arguments=$args;failure=$failure}|ConvertTo-Json -Depth 8|Set-Content -LiteralPath (Join-Path $report manifest.json) -Encoding utf8;Write-Host "INNOVATION_SYNTHESIS_$verdict reports=$report"}
