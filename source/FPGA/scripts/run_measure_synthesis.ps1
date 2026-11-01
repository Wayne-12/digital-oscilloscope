#requires -Version 7.0
[CmdletBinding()]
param([string]$VivadoBin)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'vivado_toolchain.ps1')
$VivadoBin=Resolve-ScopeVivadoBin -RequestedBin $VivadoBin
$root=Split-Path -Parent $PSScriptRoot
$id=(Get-Date -Format 'yyyyMMdd_HHmmss')+'_'+[guid]::NewGuid().ToString('N').Substring(0,8)
$report=Join-Path $root "reports/measure_synthesis/$id"
$build=Join-Path ([IO.Path]::GetTempPath()) "measure_synth_$id"
$out=Join-Path $build 'artifacts'
New-Item -ItemType Directory -Path $report,$out|Out-Null
$relative=@('rtl/common/scope_pkg.sv','rtl/trigger/trigger_edge.sv','rtl/trigger/trigger_core.sv',
 'rtl/capture/capture_bram.sv','rtl/capture/bram_capture.sv','rtl/measure/measure_udiv.sv','rtl/measure/measurement_core.sv')
$hashes=@(foreach($rel in $relative){
 $source=Join-Path $root $rel;$copy=Join-Path $build $rel
 New-Item -ItemType Directory -Path (Split-Path -Parent $copy) -Force|Out-Null
 Copy-Item -LiteralPath $source -Destination $copy
 $hash=(Get-FileHash -LiteralPath $source).Hash
 if((Get-FileHash -LiteralPath $copy).Hash -ne $hash){throw 'Source staging changed bytes'}
 [pscustomobject]@{file=$rel;sha256=$hash}
})
$script=Join-Path $build 'check_measure_synthesis.tcl'
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'check_measure_synthesis.tcl') -Destination $script
$args=@('-mode','batch','-notrace','-source',$script,'-log',(Join-Path $out 'vivado.log'),
 '-journal',(Join-Path $out 'vivado.jou'),'-tclargs',$out,$build)
$verdict='FAIL';$failure=$null;$resources=$null;$advisories=@()
Push-Location -LiteralPath $build
try{
 $lines=@(& (Join-Path $VivadoBin 'vivado.bat') @args 2>&1);$exit=$LASTEXITCODE;$log=$lines -join [Environment]::NewLine
 $log|Set-Content -LiteralPath (Join-Path $report 'console.log') -Encoding utf8
 # Retain this exact floorplanning advisory in the manifest and original log.
 # This run proves synthesis/resource mapping; floorplanning is not performed.
 # No message severity is changed, and every other warning still fails.
 $warnings=@([regex]::Matches($log,'(?im)^\s*WARNING:[^\r\n]*')|ForEach-Object{$_.Value.Trim()})
 $advisories=@($warnings|Where-Object{$_ -cmatch "^WARNING: \[Netlist 29-101\] Netlist 'trigger_core' is not ideal for floorplanning, since the cellview 'trigger_core' contains a large number of primitives\.  Please consider enabling hierarchy in synthesis if you want to do floorplanning\.$"})
 if($exit -ne 0 -or $log -notmatch 'MEASURE_OOC_SYNTH_PASS tops=3 latches=0' -or
   $log -match '(?im)^\s*(CRITICAL WARNING:|ERROR:|MEASURE_OOC_SYNTH_FAIL)' -or
   $warnings.Count -ne $advisories.Count -or $advisories.Count -gt 1){throw 'OOC synthesis diagnostic or incomplete PASS'}
 $resources=Get-Content -LiteralPath (Join-Path $out 'resources.json') -Raw|ConvertFrom-Json
 if(@($resources).Count -ne 3){throw 'Missing OOC resource records'}
 foreach($h in $hashes){if((Get-FileHash -LiteralPath (Join-Path $root $h.file)).Hash -ne $h.sha256){throw 'Sources changed during synthesis'}}
 $verdict='PASS'
}catch{$failure=$_.Exception.Message;throw}
finally{
 Pop-Location
 Copy-Item -LiteralPath $out -Destination (Join-Path $report 'artifacts') -Recurse
 [pscustomobject]@{verdict=$verdict;part='xc7a35tcsg324-1';stage='out_of_context_synthesis';resources=$resources;
  source_sha256=$hashes;retained_floorplanning_advisories=$advisories;temporary_build=$build;tool=Join-Path $VivadoBin 'vivado.bat';arguments=$args;failure=$failure}|
  ConvertTo-Json -Depth 7|Set-Content -LiteralPath (Join-Path $report 'manifest.json') -Encoding utf8
 Write-Output "MEASURE_SYNTHESIS_$verdict reports=$report"
}
