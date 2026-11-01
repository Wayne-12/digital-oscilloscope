#requires -Version 7.0
[CmdletBinding()]
param([string]$VivadoBin)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'vivado_toolchain.ps1')
$VivadoBin=Resolve-ScopeVivadoBin -RequestedBin $VivadoBin
$root=Split-Path -Parent $PSScriptRoot
$id=(Get-Date -Format 'yyyyMMdd_HHmmss')+'_'+[guid]::NewGuid().ToString('N').Substring(0,8)
$report=Join-Path $root "reports/multires_synthesis/$id"
$build=Join-Path ([IO.Path]::GetTempPath()) "multires_synth_$id"
$out=Join-Path $build 'artifacts'
New-Item -ItemType Directory -Path $report,$out|Out-Null
$relative=@('rtl/common/scope_pkg.sv','rtl/common/multires_pkg.sv','rtl/measure/measure_udiv.sv','rtl/multires/multires_envelope.sv')
$hashes=@(foreach($rel in $relative){
 $source=Join-Path $root $rel;$copy=Join-Path $build $rel
 New-Item -ItemType Directory -Path (Split-Path -Parent $copy) -Force|Out-Null
 Copy-Item -LiteralPath $source -Destination $copy
 $hash=(Get-FileHash -LiteralPath $source).Hash
 if((Get-FileHash -LiteralPath $copy).Hash -ne $hash){throw 'Source staging changed bytes'}
 [pscustomobject]@{file=$rel;sha256=$hash}
})
$script=Join-Path $build 'check_multires_synthesis.tcl'
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'check_multires_synthesis.tcl') -Destination $script
$args=@('-mode','batch','-notrace','-source',$script,'-log',(Join-Path $out 'vivado.log'),
 '-journal',(Join-Path $out 'vivado.jou'),'-tclargs',$out,$build)
$verdict='FAIL';$failure=$null;$resources=$null
Push-Location -LiteralPath $build
try{
 $lines=@(& (Join-Path $VivadoBin 'vivado.bat') @args 2>&1);$exit=$LASTEXITCODE;$log=$lines -join [Environment]::NewLine
 $log|Set-Content -LiteralPath (Join-Path $report 'console.log') -Encoding utf8
 if($exit -ne 0 -or $log -notmatch 'MULTIRES_OOC_SYNTH_PASS tops=1 latches=0' -or
   $log -match '(?im)^\s*(WARNING:|CRITICAL WARNING:|ERROR:|MULTIRES_OOC_SYNTH_FAIL)'){throw 'OOC synthesis diagnostic or incomplete PASS'}
 $resources=Get-Content -LiteralPath (Join-Path $out 'resources.json') -Raw|ConvertFrom-Json
 if(@($resources).Count -ne 1){throw 'Missing OOC resource records'}
 foreach($h in $hashes){if((Get-FileHash -LiteralPath (Join-Path $root $h.file)).Hash -ne $h.sha256){throw 'Sources changed during synthesis'}}
 $verdict='PASS'
}catch{$failure=$_.Exception.Message;throw}
finally{
 Pop-Location
 Copy-Item -LiteralPath $out -Destination (Join-Path $report 'artifacts') -Recurse
 [pscustomobject]@{verdict=$verdict;part='xc7a35tcsg324-1';stage='out_of_context_synthesis';resources=$resources;
  source_sha256=$hashes;temporary_build=$build;tool=Join-Path $VivadoBin 'vivado.bat';arguments=$args;failure=$failure}|
  ConvertTo-Json -Depth 7|Set-Content -LiteralPath (Join-Path $report 'manifest.json') -Encoding utf8
 Write-Output "MULTIRES_SYNTHESIS_$verdict reports=$report"
}


