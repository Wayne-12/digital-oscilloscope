#requires -Version 7.0
[CmdletBinding()]
param([string]$VivadoBin,[string]$PythonExe,
 [ValidateRange(0,2147483647)][int[]]$Seeds=@(20261020,42),
 [ValidateRange(1048576,1048576)][int]$BulkBytes=1048576,[switch]$SkipReplay,[switch]$Project)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'vivado_toolchain.ps1')
$VivadoBin=Resolve-ScopeVivadoBin -RequestedBin $VivadoBin
if(!$PythonExe){$PythonExe=(Get-Command python.exe -ErrorAction Stop).Source}
if($Seeds.Count -eq 0 -or @($Seeds|Select-Object -Unique).Count -ne $Seeds.Count){throw 'Seeds must be nonempty and unique'}
$root=Split-Path -Parent $PSScriptRoot
$id=(Get-Date -Format 'yyyyMMdd_HHmmss')+'_'+[guid]::NewGuid().ToString('N').Substring(0,8)
$report=Join-Path $root "reports/uart/$id";$build=Join-Path ([IO.Path]::GetTempPath()) "uart_$id"
New-Item -ItemType Directory -Path $report,$build|Out-Null
$relative=@('rtl/common/scope_pkg.sv','rtl/common/multires_pkg.sv','rtl/common/protocol_pkg.sv',
 'rtl/multires/multires_envelope.sv','rtl/measure/measure_udiv.sv','rtl/measure/measurement_core.sv',
 'rtl/trigger/trigger_edge.sv','rtl/trigger/trigger_core.sv','rtl/capture/capture_bram.sv','rtl/capture/bram_capture.sv',
 'rtl/dac_dds/dds_sine_lut.sv','rtl/dac_dds/dds_core.sv')+
 @(Get-ChildItem (Join-Path $root 'rtl/uart_proto') -Filter '*.sv' -File|ForEach-Object{$_.FullName.Substring($root.Length+1)})+
 @('sim/tb/uart_capture_backend.sv','sim/tb/tb_uart_bytes.sv','sim/tb/tb_uart_bits.sv')
$sources=@($relative|ForEach-Object{Join-Path $root $_})
$inputs=$sources+@('run_uart_tb.ps1','generate_uart_vectors.py','audit_uart_traces.py','check_uart_project.tcl','create_smoke_project.tcl','ensure_scope_clock_ip.tcl','vivado_toolchain.ps1','vivado_toolchain.json'|ForEach-Object{Join-Path $PSScriptRoot $_})+
 @((Join-Path $root '../PC/protocol/scope_protocol.py'),(Join-Path $root '../PC/tests/test_scope_protocol.py'))
$hashes=@($inputs|Get-FileHash -Algorithm SHA256|Select-Object Path,Hash)
foreach($s in $sources){Copy-Item -LiteralPath $s -Destination $build}
$results=[Collections.Generic.List[object]]::new();$commands=[Collections.Generic.List[object]]::new();$stages=@{}
$verdict='FAIL';$failure=$null;$native=$null;$replay=$null;$version=$null
function Tool([string]$Name,[string[]]$ToolArgs,[string]$Label){
 $p=Join-Path $VivadoBin "$Name.bat";$commands.Add([pscustomobject]@{tool=$p;arguments=$ToolArgs})
 $lines=@(& $p @ToolArgs 2>&1);$exit=$LASTEXITCODE;$log=$lines -join [Environment]::NewLine
 $log|Set-Content -LiteralPath (Join-Path $report "$Label.console.log") -Encoding utf8
 if($exit -ne 0 -or $log -match '(?im)^\s*(WARNING:|CRITICAL WARNING:|ERROR:|Fatal:|TEST_FAIL|FATAL_ERROR:)'){throw "$Label failed: $report/$Label.console.log"}
 return $log
}
function SeedRun([int]$Seed,[string]$Label){
 $s=$stages[$Seed];$dest=Join-Path $report $Label;New-Item -ItemType Directory -Path $dest|Out-Null
 foreach($kind in @('bits','bytes')){
  $args=@("uart_$kind",'--runall','--onfinish','quit','--onerror','quit','--sv_seed',"$Seed",'--testplusarg',('"SEED={0}"' -f $Seed),
   '--testplusarg',('"VECTOR_DIR={0}"' -f $s.vectors.Replace('\','/')),'--testplusarg','"TRACE_DIR=."','--log',"$Label.$kind.log")
  $log=Tool xsim $args "$Label.$kind"
  if($log -notmatch "(?m)^TEST_PASS tb_uart_$kind .*errors=0"){throw "Missing UART $kind PASS"}
  if($kind -eq 'bytes' -and $log -notmatch "bulk=$BulkBytes "){throw 'Missing 1 MiB payload proof'}
 }
 $td=Join-Path $dest 'traces';New-Item -ItemType Directory -Path $td|Out-Null
 foreach($n in @('uart_bits.hex','uart_bytes.hex')){Copy-Item -LiteralPath (Join-Path $build $n) -Destination $td}
 $audit=@(& $PythonExe (Join-Path $PSScriptRoot 'audit_uart_traces.py') --vectors $s.vectors --traces $td --output (Join-Path $dest 'audit.json') 2>&1)
 $audit|Set-Content -LiteralPath (Join-Path $dest 'audit.console.log') -Encoding utf8
 if($LASTEXITCODE -ne 0 -or ($audit -join ' ') -notmatch 'TRACE_AUDIT_PASS'){throw "UART audit failed $audit"}
 return [pscustomobject]@{seed=$Seed;verdict='PASS';audit=(Get-Content (Join-Path $dest 'audit.json') -Raw|ConvertFrom-Json);traces=@(Get-ChildItem -LiteralPath $td -File|Get-FileHash|ForEach-Object{[pscustomobject]@{file=Split-Path -Leaf $_.Path;sha256=$_.Hash}}|Sort-Object file)}
}
Push-Location -LiteralPath $build
try{
 $version=Tool xsim @('--version') version
 $unit=@(& $PythonExe -m unittest discover -s (Join-Path $root '../PC/tests') -p 'test_scope_protocol.py' -v 2>&1)
 $unit|Set-Content -LiteralPath (Join-Path $report 'pc_tests.log') -Encoding utf8
 if($LASTEXITCODE -ne 0){throw 'PC codec unit tests failed'}
 foreach($seed in $Seeds){
  $v=Join-Path $root "sim/vectors/uart/$id/seed_$seed";$e=Join-Path $root "sim/expected/uart/$id/seed_$seed"
  $gen=@(& $PythonExe (Join-Path $PSScriptRoot 'generate_uart_vectors.py') --output $v --expected-output $e --seed $seed --bulk-bytes $BulkBytes 2>&1)
  $gen|Set-Content -LiteralPath (Join-Path $report "seed_$seed.oracle.log") -Encoding utf8
  if($LASTEXITCODE -ne 0 -or ($gen -join ' ') -notmatch 'ORACLE_PASS'){throw 'UART oracle failed'}
  $stage=Join-Path $build "seed_$seed";New-Item -ItemType Directory -Path $stage|Out-Null
  Copy-Item -LiteralPath $v -Destination (Join-Path $stage 'vectors') -Recurse
  # Stage one read-only runtime directory in ASCII TEMP; retain stimulus and
  # independent golden files separately in the user's documented project tree.
  Get-ChildItem -LiteralPath $e -File|Copy-Item -Destination (Join-Path $stage 'vectors')
  $stages[$seed]=[pscustomobject]@{vectors=Join-Path $stage 'vectors';original_vectors=$v;original_expected=$e}
 }
 $null=Tool xvlog (@('--sv')+@($sources|ForEach-Object{Split-Path -Leaf $_})) compile
 foreach($kind in @('bits','bytes')){$null=Tool xelab @("work.tb_uart_$kind",'--snapshot',"uart_$kind",'--timescale','1ns/1ps') "elaborate.$kind"}
 foreach($seed in $Seeds){$results.Add((SeedRun $seed "seed_$seed"));Write-Host "UART_SEED_PASS seed=$seed bulk=$BulkBytes"}
 if(!$SkipReplay){
  $again=SeedRun $Seeds[0] "seed_$($Seeds[0])_replay"
  if(($again.traces|ConvertTo-Json -Compress) -cne ($results[0].traces|ConvertTo-Json -Compress)){throw 'UART replay trace changed'}
  $replay=[pscustomobject]@{verdict='PASS';seed=$Seeds[0];identical_traces=2}
 }
 if($Project){
  $nd=Join-Path $report 'project';$nt=Join-Path $nd 'traces';New-Item -ItemType Directory -Path $nd,$nt|Out-Null
  $projectDir=Resolve-ScopeProjectDir -FpgaRoot $root;$simulationDir=Join-Path $projectDir 'scope_smoke.sim'
  if(Test-Path -LiteralPath $simulationDir){
   $resolved=(Resolve-Path -LiteralPath $simulationDir).ProviderPath
   if(!$resolved.Equals($simulationDir,[StringComparison]::OrdinalIgnoreCase) -or !$resolved.StartsWith($projectDir+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)){throw 'Unsafe simulation cleanup target'}
   $item=Get-Item -LiteralPath $resolved -Force
   if(($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or @(Get-ChildItem -LiteralPath $resolved -Recurse -Force|Where-Object{$_.Attributes -band [IO.FileAttributes]::ReparsePoint}).Count){throw 'Refusing reparse point cleanup'}
   Remove-Item -LiteralPath $resolved -Recurse -Force
  }
  "Deleted exact generated directory $simulationDir"|Set-Content -LiteralPath (Join-Path $nd 'clean_rebuild.txt') -Encoding utf8
  $args=@('-mode','batch','-notrace','-source',(Join-Path $PSScriptRoot 'check_uart_project.tcl'),'-log',(Join-Path $nd 'vivado.log'),'-journal',(Join-Path $nd 'vivado.jou'),'-tclargs',$nd,$stages[$Seeds[0]].vectors,$nt,"$($Seeds[0])")
  $commands.Add([pscustomobject]@{tool=Join-Path $VivadoBin 'vivado.bat';arguments=$args})
  $lines=@(& (Join-Path $VivadoBin 'vivado.bat') @args 2>&1);$exit=$LASTEXITCODE;$log=$lines -join [Environment]::NewLine
  $log|Set-Content -LiteralPath (Join-Path $nd 'console.log') -Encoding utf8
  if($exit -ne 0 -or $log -notmatch 'UART_PROJECT_PASS' -or $log -match '(?im)^\s*(ERROR:|CRITICAL WARNING:|Fatal:|UART_PROJECT_FAIL)'){throw 'Native UART simulation failed'}
  foreach($n in @('bits','bytes')){foreach($l in @('xvlog','elaborate','simulate')){
   if((Get-Content -LiteralPath (Join-Path $nd "tb_uart_$n.$l.log") -Raw) -match '(?im)^\s*(WARNING:|ERROR:|Fatal:|TEST_FAIL)'){throw 'Native UART HDL diagnostic'}
  }}
  foreach($f in Get-ChildItem -LiteralPath $nt -File){if((Get-FileHash -LiteralPath $f.FullName).Hash -ne (Get-FileHash -LiteralPath (Join-Path $report "seed_$($Seeds[0])/traces/$($f.Name)")).Hash){throw 'Native UART trace differs'}}
  $native=[pscustomobject]@{verdict='PASS';identical_traces=2;clean_rebuild=$true;report=$nd}
 }
 foreach($h in $hashes){if((Get-FileHash -LiteralPath $h.Path).Hash -ne $h.Hash){throw 'Sources changed during UART regression'}}
 $verdict='PASS'
}catch{$failure=$_.Exception.Message;throw}
finally{
 Pop-Location
 $commands|ConvertTo-Json -Depth 6|Set-Content -LiteralPath (Join-Path $report 'commands.json') -Encoding utf8
 [pscustomobject]@{verdict=$verdict;backend=$version;seeds=$Seeds;bulk_bytes_per_seed=$BulkBytes;results=@($results.ToArray());replay=$replay;project=$native;source_sha256=$hashes;temporary_build=$build;failure=$failure}|ConvertTo-Json -Depth 12|Set-Content -LiteralPath (Join-Path $report 'manifest.json') -Encoding utf8
 Write-Output "UART_REGRESSION_$verdict reports=$report"
}
