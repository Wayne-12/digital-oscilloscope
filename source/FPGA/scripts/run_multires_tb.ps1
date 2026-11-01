#requires -Version 7.0
[CmdletBinding()]
param([string]$VivadoBin,[string]$PythonExe,
 [ValidateRange(0,2147483647)][int[]]$Seeds=@(20261020,42),[switch]$SkipReplay,[switch]$Project)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'vivado_toolchain.ps1')
$VivadoBin=Resolve-ScopeVivadoBin -RequestedBin $VivadoBin
if(!$PythonExe){$PythonExe=(Get-Command python.exe -ErrorAction Stop).Source}
if($Seeds.Count -eq 0 -or @($Seeds|Select-Object -Unique).Count -ne $Seeds.Count){throw 'Seeds must be nonempty and unique'}
$root=Split-Path -Parent $PSScriptRoot
$id=(Get-Date -Format 'yyyyMMdd_HHmmss')+'_'+[guid]::NewGuid().ToString('N').Substring(0,8)
$report=Join-Path $root "reports/multires/$id";$build=Join-Path ([IO.Path]::GetTempPath()) "multires_$id"
New-Item -ItemType Directory -Path $report,$build|Out-Null
$relative=@('rtl/common/scope_pkg.sv','rtl/common/multires_pkg.sv','rtl/common/scope_async_fifo.sv',
 'rtl/measure/measure_udiv.sv','rtl/measure/measurement_core.sv','rtl/trigger/trigger_edge.sv','rtl/trigger/trigger_core.sv',
 'rtl/capture/capture_bram.sv','rtl/capture/bram_capture.sv',
 'rtl/dac_dds/dds_sine_lut.sv','rtl/dac_dds/dds_core.sv','rtl/multires/multires_envelope.sv',
 'sim/tb/uart_capture_backend.sv','sim/tb/tb_multires.sv','sim/tb/tb_multires_capture.sv','sim/tb/tb_multires_fault.sv')
$sources=@($relative|ForEach-Object{Join-Path $root $_})
$inputs=$sources+@('run_multires_tb.ps1','generate_multires_vectors.py','audit_multires_traces.py','check_multires_project.tcl',
 'create_smoke_project.tcl','ensure_scope_clock_ip.tcl','vivado_toolchain.ps1','vivado_toolchain.json'|ForEach-Object{Join-Path $PSScriptRoot $_})+
 @((Join-Path $root '../PC/protocol/envelope_reference.py'),(Join-Path $root '../PC/tests/test_envelope_reference.py'))
$hashes=@($inputs|Get-FileHash -Algorithm SHA256|Select-Object Path,Hash)
foreach($s in $sources){Copy-Item -LiteralPath $s -Destination $build}
$results=[Collections.Generic.List[object]]::new();$commands=[Collections.Generic.List[object]]::new();$negatives=[Collections.Generic.List[object]]::new();$stages=@{}
$verdict='FAIL';$failure=$null;$native=$null;$replay=$null;$version=$null
$traceNames=@('multires_cases.csv','multires_buckets.csv','multires_roi.csv','multires_bram_cases.csv','multires_bram_buckets.csv','multires_bram_roi.csv')
function Tool([string]$Name,[string[]]$ToolArgs,[string]$Label){
 $p=Join-Path $VivadoBin "$Name.bat";$commands.Add([pscustomobject]@{tool=$p;arguments=$ToolArgs})
 $lines=@(& $p @ToolArgs 2>&1);$exit=$LASTEXITCODE;$log=$lines -join [Environment]::NewLine
 $log|Set-Content -LiteralPath (Join-Path $report "$Label.console.log") -Encoding utf8
 if($exit -ne 0 -or $log -match '(?im)^\s*(WARNING:|CRITICAL WARNING:|ERROR:|Fatal:|TEST_FAIL|FATAL_ERROR:)'){throw "$Label failed: $report/$Label.console.log"}
 return $log
}
function SeedRun([int]$Seed,[string]$Label){
 $s=$stages[$Seed];$oracle=Get-Content -LiteralPath (Join-Path $s.expected 'oracle.json') -Raw|ConvertFrom-Json;$dest=Join-Path $report $Label;New-Item -ItemType Directory -Path $dest|Out-Null
 foreach($kind in @('multires','multires_bram')){
  $args=@($kind,'--runall','--onfinish','quit','--onerror','quit','--sv_seed',"$Seed",'--testplusarg',('"SEED={0}"' -f $Seed),
   '--testplusarg',('"VECTOR_DIR={0}"' -f $s.vectors.Replace('\','/')),'--testplusarg',('"EXPECTED_DIR={0}"' -f $s.expected.Replace('\','/')),
   '--testplusarg','"TRACE_DIR=."','--log',"$Label.$kind.log")
  $log=Tool xsim $args "$Label.$kind"
  if($kind -eq 'multires'){
   if($log -notmatch "(?m)^TEST_PASS tb_multires seed=$Seed cases=$($oracle.case_count) samples=$($oracle.sample_comparisons) buckets=$($oracle.bucket_comparisons) roi=$($oracle.roi_comparisons) errors=0" -or
    @([regex]::Matches($log,'(?m)^MULTIRES_CASE_PASS ')).Count -ne 80 -or
    @([regex]::Matches($log,'(?m)^MULTIRES_CONTROL_POINT_PASS ')).Count -ne 14 -or
    $log -notmatch '(?m)^MULTIRES_CONTROL_PASS invalid=8 cancels=7 resets=7 recoveries=15 errors=0'){throw 'Incomplete core/control PASS'}
  }else{
   $backend=0;$jobs=3
   if($log -notmatch "(?m)^TEST_PASS tb_multires_capture backend=$backend seed=$Seed jobs=$jobs errors=0" -or
    @([regex]::Matches($log,'(?m)^MULTIRES_CAPTURE_JOB_PASS ')).Count -ne $jobs){throw 'Incomplete actual-memory integration PASS'}
  }
 }
 $td=Join-Path $dest 'traces';New-Item -ItemType Directory -Path $td|Out-Null
 foreach($n in $traceNames){Copy-Item -LiteralPath (Join-Path $build $n) -Destination $td}
 $audit=@(& $PythonExe (Join-Path $PSScriptRoot 'audit_multires_traces.py') --vectors $s.vectors --expected $s.expected --traces $td --output (Join-Path $dest 'audit.json') 2>&1)
 $audit|Set-Content -LiteralPath (Join-Path $dest 'audit.console.log') -Encoding utf8
 if($LASTEXITCODE -ne 0 -or ($audit -join ' ') -notmatch 'TRACE_AUDIT_PASS'){throw "Multires trace audit failed $audit"}
 $au=Get-Content -LiteralPath (Join-Path $dest 'audit.json') -Raw|ConvertFrom-Json
 return [pscustomobject]@{seed=$Seed;verdict='PASS';audit=$au;traces=@(Get-ChildItem -LiteralPath $td -File|Get-FileHash|ForEach-Object{[pscustomobject]@{file=Split-Path -Leaf $_.Path;sha256=$_.Hash}}|Sort-Object file)}
}
Push-Location -LiteralPath $build
try{
 $version=Tool xsim @('--version') version
 $unit=@(& $PythonExe -m unittest discover -s (Join-Path $root '../PC/tests') -p 'test_envelope_reference.py' -v 2>&1)
 $unit|Set-Content -LiteralPath (Join-Path $report 'pc_tests.log') -Encoding utf8
 if($LASTEXITCODE -ne 0){throw 'PC envelope oracle tests failed'}
 $preflight=Join-Path ([IO.Path]::GetTempPath()) 'scope_step10_preflight/preflight.log'
 if(Test-Path -LiteralPath $preflight){Copy-Item -LiteralPath $preflight -Destination (Join-Path $report 'initial_preflight.log')}
 foreach($seed in $Seeds){
  $v=Join-Path $root "sim/vectors/multires/$id/seed_$seed";$e=Join-Path $root "sim/expected/multires/$id/seed_$seed"
  $gen=@(& $PythonExe (Join-Path $PSScriptRoot 'generate_multires_vectors.py') --output $v --expected-output $e --seed $seed 2>&1)
  $gen|Set-Content -LiteralPath (Join-Path $report "seed_$seed.oracle.log") -Encoding utf8
  if($LASTEXITCODE -ne 0 -or ($gen -join ' ') -notmatch 'ORACLE_PASS'){throw 'Multires oracle failed'}
  $stage=Join-Path $build "seed_$seed";New-Item -ItemType Directory -Path $stage|Out-Null
  Copy-Item -LiteralPath $v -Destination (Join-Path $stage 'vectors') -Recurse;Copy-Item -LiteralPath $e -Destination (Join-Path $stage 'expected') -Recurse
  $stages[$seed]=[pscustomobject]@{vectors=Join-Path $stage 'vectors';expected=Join-Path $stage 'expected';original_vectors=$v;original_expected=$e}
 }
 $null=Tool xvlog (@('--sv')+@($sources|ForEach-Object{Split-Path -Leaf $_})) compile
 foreach($kind in @('multires','multires_bram')){$null=Tool xelab @("work.tb_$kind",'--snapshot',$kind,'--timescale','1ns/1ps') "elaborate.$kind"}
 foreach($seed in $Seeds){$results.Add((SeedRun $seed "seed_$seed"));Write-Host "MULTIRES_SEED_PASS seed=$seed cases=80 integration_jobs=3"}
 if(!$SkipReplay){
  $again=SeedRun $Seeds[0] "seed_$($Seeds[0])_replay"
  if(($again.traces|ConvertTo-Json -Compress) -cne ($results[0].traces|ConvertTo-Json -Compress)){throw 'Multires replay changed traces'}
  $replay=[pscustomobject]@{verdict='PASS';seed=$Seeds[0];identical_traces=6}
 }
 foreach($bad in 1..3){
  $null=Tool xelab @('work.tb_multires_fault','--snapshot',"multires_fault_$bad",'--generic_top',('"BAD={0}"' -f $bad),'--timescale','1ns/1ps') "fault_$bad.elaborate"
  $args=@("multires_fault_$bad",'--runall','--onfinish','quit','--onerror','quit','--log',"fault_$bad.log")
  $commands.Add([pscustomobject]@{tool=Join-Path $VivadoBin 'xsim.bat';arguments=$args})
  $lines=@(& (Join-Path $VivadoBin 'xsim.bat') @args 2>&1);$log=$lines -join [Environment]::NewLine
  $log|Set-Content -LiteralPath (Join-Path $report "fault_$bad.console.log") -Encoding utf8
  $signature=@('MULTIRES_READ_RANGE_ASSERT','MULTIRES_SAMPLE_FORMAT_ASSERT','MULTIRES_RESPONSE_PROTOCOL_ASSERT')[$bad-1]
  if($log -notmatch "Fatal: $signature" -or $log -match 'NEGATIVE_TEST_DID_NOT_FIRE|TEST_PASS'){throw "Missing expected negative assertion $bad"}
  $negatives.Add([pscustomobject]@{case=$bad;verdict='PASS';expected_fatal=$signature})
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
  $s=$stages[$Seeds[0]]
  $args=@('-mode','batch','-notrace','-source',(Join-Path $PSScriptRoot 'check_multires_project.tcl'),'-log',(Join-Path $nd 'vivado.log'),'-journal',(Join-Path $nd 'vivado.jou'),'-tclargs',$nd,$s.vectors,$s.expected,$nt,"$($Seeds[0])")
  $commands.Add([pscustomobject]@{tool=Join-Path $VivadoBin 'vivado.bat';arguments=$args})
  $lines=@(& (Join-Path $VivadoBin 'vivado.bat') @args 2>&1);$exit=$LASTEXITCODE;$log=$lines -join [Environment]::NewLine
  $log|Set-Content -LiteralPath (Join-Path $nd 'console.log') -Encoding utf8
  if($exit -ne 0 -or $log -notmatch 'MULTIRES_PROJECT_PASS' -or $log -match '(?im)^\s*(ERROR:|CRITICAL WARNING:|Fatal:|MULTIRES_PROJECT_FAIL)'){throw 'Native multires simulation failed'}
  foreach($top in @('tb_multires','tb_multires_bram')){foreach($l in @('xvlog','elaborate','simulate')){
   if((Get-Content -LiteralPath (Join-Path $nd "$top.$l.log") -Raw) -match '(?im)^\s*(WARNING:|ERROR:|Fatal:|TEST_FAIL)'){throw 'Native HDL diagnostic'}
  }}
  foreach($f in $traceNames){if((Get-FileHash -LiteralPath (Join-Path $nt $f)).Hash -ne (Get-FileHash -LiteralPath (Join-Path $report "seed_$($Seeds[0])/traces/$f")).Hash){throw 'Native multires trace differs'}}
  $native=[pscustomobject]@{verdict='PASS';identical_traces=6;clean_rebuild=$true;report=$nd;top='tb_multires'}
 }
 foreach($h in $hashes){if((Get-FileHash -LiteralPath $h.Path).Hash -ne $h.Hash){throw 'Sources changed during regression'}}
 $verdict='PASS'
}catch{$failure=$_.Exception.Message;throw}
finally{
 Pop-Location
 $commands|ConvertTo-Json -Depth 6|Set-Content -LiteralPath (Join-Path $report 'commands.json') -Encoding utf8
 [pscustomobject]@{verdict=$verdict;backend=$version;seeds=$Seeds;results=@($results.ToArray());negative_tests=@($negatives.ToArray());replay=$replay;project=$native;source_sha256=$hashes;temporary_build=$build;failure=$failure}|ConvertTo-Json -Depth 12|Set-Content -LiteralPath (Join-Path $report 'manifest.json') -Encoding utf8
 Write-Output "MULTIRES_REGRESSION_$verdict reports=$report"
}
