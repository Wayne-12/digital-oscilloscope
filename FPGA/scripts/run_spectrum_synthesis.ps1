#requires -Version 7.0
[CmdletBinding()]
param([string]$VivadoBin)
$ErrorActionPreference='Stop';Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'vivado_toolchain.ps1')
$VivadoBin=Resolve-ScopeVivadoBin -RequestedBin $VivadoBin
$root=Split-Path -Parent $PSScriptRoot
$id=(Get-Date -Format 'yyyyMMdd_HHmmss')+'_'+[guid]::NewGuid().ToString('N').Substring(0,8)
$report=Join-Path $root "reports/spectrum_synthesis/$id";$build=Join-Path ([IO.Path]::GetTempPath()) "spectrum_synth_$id";$out=Join-Path $build artifacts
New-Item -ItemType Directory -Path $report,$out|Out-Null
$relative=@('rtl/common/fft_window_pkg.sv','rtl/common/spectrum_pkg.sv','rtl/measure/fft_hann_lut.sv','rtl/measure/fft_ip_wrapper.sv','rtl/measure/spectrum_isqrt.sv','rtl/measure/spectrum_analyzer.sv','ip/scope_fft_1024/scope_fft_1024.xci','scripts/ensure_scope_fft_ip.tcl','scripts/check_spectrum_synthesis.tcl')
$hashes=@(foreach($rel in $relative){
 $source=Join-Path $root $rel;$copy=Join-Path $build $rel;New-Item -ItemType Directory -Path (Split-Path -Parent $copy) -Force|Out-Null;Copy-Item -LiteralPath $source -Destination $copy
 $hash=(Get-FileHash -LiteralPath $source).Hash;if((Get-FileHash -LiteralPath $copy).Hash -ne $hash){throw 'Source staging changed bytes'}
 [pscustomobject]@{file=$rel;sha256=$hash}
})
$args=@('-mode','batch','-notrace','-source',(Join-Path $build scripts/check_spectrum_synthesis.tcl),'-log',(Join-Path $out vivado.log),'-journal',(Join-Path $out vivado.jou),'-tclargs',$out,$build)
$verdict='FAIL';$failure=$null;$resources=$null
Push-Location -LiteralPath $build
try{
 $lines=@(& (Join-Path $VivadoBin vivado.bat) @args 2>&1);$exit=$LASTEXITCODE;$log=$lines -join [Environment]::NewLine
 $log|Set-Content -LiteralPath (Join-Path $report console.log) -Encoding utf8
 if($exit -ne 0 -or $log -notmatch 'SPECTRUM_OOC_SYNTH_PASS .*latches=0 blackboxes=0' -or $log -match '(?im)^\s*(CRITICAL WARNING:|ERROR:|SPECTRUM_OOC_SYNTH_FAIL)'){throw 'Synthesis incomplete or diagnostic'}
 $resources=Get-Content -LiteralPath (Join-Path $out resources.json) -Raw|ConvertFrom-Json
 foreach($h in $hashes){if((Get-FileHash -LiteralPath (Join-Path $root $h.file)).Hash -ne $h.sha256){throw 'Source changed during synthesis'}}
 $verdict='PASS'
}catch{$failure=$_.Exception.Message;throw}
finally{
 Pop-Location;Copy-Item -LiteralPath $out -Destination (Join-Path $report artifacts) -Recurse
 # Retain the IP synthesis logs as well as the top synthesis report.
 Get-ChildItem -LiteralPath $build -Recurse -File -Filter '*.log'|ForEach-Object{
  $rel=[IO.Path]::GetRelativePath($build,$_.FullName);$dest=Join-Path $report "logs/$rel";New-Item -ItemType Directory -Path (Split-Path -Parent $dest) -Force|Out-Null;Copy-Item -LiteralPath $_.FullName -Destination $dest
 }
 [pscustomobject]@{verdict=$verdict;part='xc7a35tcsg324-1';stage='out_of_context_synthesis';resources=$resources;source_sha256=$hashes;temporary_build=$build;tool=Join-Path $VivadoBin vivado.bat;arguments=$args;failure=$failure}|ConvertTo-Json -Depth 7|Set-Content -LiteralPath (Join-Path $report manifest.json) -Encoding utf8
 Write-Host "SPECTRUM_SYNTHESIS_$verdict reports=$report"
}
