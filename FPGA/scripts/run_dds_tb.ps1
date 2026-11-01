[CmdletBinding()]
param([string]$VivadoBin,[string]$PythonExe,
 [ValidateRange(0,2147483647)][int[]]$Seeds=@(20261020,42),[switch]$SkipReplay,[switch]$Project)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'vivado_toolchain.ps1')
$VivadoBin=Resolve-ScopeVivadoBin -RequestedBin $VivadoBin
if(!$PythonExe){$PythonExe=(Get-Command python.exe -ErrorAction Stop).Source}
if($Seeds.Count -eq 0 -or @($Seeds|Select-Object -Unique).Count -ne $Seeds.Count){throw 'Seeds must be nonempty and unique.'}
$root=Split-Path -Parent $PSScriptRoot
$id=(Get-Date -Format 'yyyyMMdd_HHmmss')+'_'+[guid]::NewGuid().ToString('N').Substring(0,8)
$report=Join-Path $root "reports/dds/$id"
$build=Join-Path ([IO.Path]::GetTempPath()) "dds_$id"
New-Item -ItemType Directory -Path $report,$build | Out-Null
$relative=@('rtl/common/scope_pkg.sv','rtl/dac_dds/dds_sine_lut.sv','rtl/dac_dds/dds_core.sv',
 'sim/models/ideal_clock.sv','sim/models/ad9767_model.sv','sim/tb/dds_scenario.sv','sim/tb/tb_dds.sv','sim/tb/tb_ad9767_fault.sv',
 'rtl/clock_reset/scope_reset_sync.sv','rtl/clock_reset/scope_enable_sync.sv',
 'rtl/clock_reset/scope_safe_ctrl.sv','rtl/top/scope_core.sv','sim/models/scope_pin_model.sv','sim/tb/dds_safe_scenario.sv')
$sources=@($relative|ForEach-Object{Join-Path $root $_})
$hashInputs=@($sources)+@('run_dds_tb.ps1','generate_dds_vectors.py','audit_dds_traces.py','check_dds_project.tcl',
 'create_smoke_project.tcl','ensure_scope_clock_ip.tcl','vivado_toolchain.ps1','vivado_toolchain.json'|ForEach-Object{Join-Path $PSScriptRoot $_})
$hashes=@($hashInputs|Get-FileHash -Algorithm SHA256|Select-Object Path,Hash)
foreach($s in $sources){Copy-Item -LiteralPath $s -Destination $build}
$results=[Collections.Generic.List[object]]::new();$commands=[Collections.Generic.List[object]]::new()
$stages=@{};$verdict='FAIL';$failure=$null;$replay=$null;$native=$null;$faults=@();$version=$null
function Tool([string]$Name,[string[]]$ToolArgs,[string]$Label,[switch]$ExpectFailure){
 $path=Join-Path $VivadoBin "$Name.bat"
 $commands.Add([pscustomobject]@{tool=$path;arguments=$ToolArgs})
 $lines=@(& $path @ToolArgs 2>&1);$exit=$LASTEXITCODE;$log=$lines -join [Environment]::NewLine
 $log|Set-Content -LiteralPath (Join-Path $report "$Label.console.log") -Encoding utf8
 if(!$ExpectFailure -and ($exit -ne 0 -or $log -match '(?im)^\s*(WARNING:|ERROR:|Fatal:|TEST_FAIL|FATAL_ERROR:)')){throw "$Label failed: $report/$Label.console.log"}
 return $log
}
function SeedRun([int]$Seed,[string]$Label){
 $s=$stages[$Seed]
 $args=@('dds_tb','--runall','--onfinish','quit','--onerror','quit','--sv_seed',"$Seed",
 '--testplusarg',('"VECTOR_DIR={0}"' -f $s.vectors.Replace('\','/')),
 '--testplusarg',('"EXPECTED_DIR={0}"' -f $s.expected.Replace('\','/')),
 '--testplusarg',('"TRACE_DIR={0}"' -f $s.traces.Replace('\','/')),'--log',"$Label.log")
 $log=Tool xsim $args $Label
 if($log -notmatch '(?m)^TEST_PASS tb_dds rates=4 cases_per_rate=18 safety=1 errors=0'){throw 'Missing terminal DDS PASS'}
 if(@([regex]::Matches($log,'(?m)^DAC_TIMING_PASS .*errors=0')).Count -ne 4 -or $log -notmatch '(?m)^DDS_SAFETY_PASS startups=24 aborts=17 reset_faults=6 lock_faults=6 .*errors=0'){throw 'Missing DAC timing or safety coverage'}
 $m=@([regex]::Matches($log,'(?m)^DDS_CASE_PASS rate=(\d+) cases=18 cycles=(\d+) active=(\d+) safe=(\d+) first_mid=(\d+) seed=(\d+) errors=0'))
 if($m.Count -ne 4 -or (@($m|ForEach-Object{$_.Groups[1].Value}|Sort-Object)-join ',') -ne '10000000,25000000,50000000,65000000'){throw 'Incomplete DDS rate coverage'}
 foreach($x in $m){if([int]$x.Groups[2].Value -ne 151932 -or [int]$x.Groups[3].Value -le 100000 -or [int]$x.Groups[6].Value -ne $Seed){throw 'DDS count/seed mismatch'}}
 $dest=Join-Path $report $Label;New-Item -ItemType Directory -Path $dest|Out-Null
 Copy-Item -LiteralPath $s.traces -Destination (Join-Path $dest 'traces') -Recurse
 $traces=@(Get-ChildItem -LiteralPath (Join-Path $dest 'traces') -Filter '*.csv' -File)
 if($traces.Count -ne 4){throw 'Missing DDS traces'}
 $traceHashes=@($traces|Get-FileHash -Algorithm SHA256|ForEach-Object{[pscustomobject]@{file=Split-Path -Leaf $_.Path;hash=$_.Hash}}|Sort-Object file)
 $audit=@(& $PythonExe (Join-Path $PSScriptRoot 'audit_dds_traces.py') --traces (Join-Path $dest 'traces') --oracle (Join-Path $s.expected 'oracle_manifest.json') --output (Join-Path $dest 'trace_audit.json') 2>&1)
 if($LASTEXITCODE -ne 0 -or ($audit -join ' ') -notmatch 'TRACE_AUDIT_PASS'){throw "DDS trace audit failed: $audit"}
 $result=[pscustomobject]@{seed=$Seed;verdict='PASS';rates=4;cases_per_rate=18;cycles_per_rate=151932;trace_sha256=$traceHashes}
 $result|ConvertTo-Json -Depth 6|Set-Content -LiteralPath (Join-Path $dest 'manifest.json') -Encoding utf8
 Write-Host "DDS_SEED_PASS seed=$Seed rates=4 cases_per_rate=18"
 return $result
}
Push-Location -LiteralPath $build
try{
 $version=Tool xsim @('--version') version
 foreach($seed in $Seeds){
  $v=Join-Path $root "sim/vectors/dds/$id/seed_$seed";$e=Join-Path $root "sim/expected/dds/$id/seed_$seed"
  $gen=@(& $PythonExe (Join-Path $PSScriptRoot 'generate_dds_vectors.py') --output $v --expected-output $e --seed $seed 2>&1)
  $gen|Set-Content -LiteralPath (Join-Path $report "seed_$seed.oracle.log") -Encoding utf8
  if($LASTEXITCODE -ne 0 -or ($gen-join ' ') -notmatch 'ORACLE_PASS'){throw 'Oracle generation failed'}
  $stage=Join-Path $build "seed_$seed";New-Item -ItemType Directory -Path $stage|Out-Null
  Copy-Item -LiteralPath $v -Destination (Join-Path $stage 'vectors') -Recurse
  Copy-Item -LiteralPath $e -Destination (Join-Path $stage 'expected') -Recurse
  $t=Join-Path $stage 'traces';New-Item -ItemType Directory -Path $t|Out-Null
  $stages[$seed]=[pscustomobject]@{vectors=Join-Path $stage 'vectors';expected=Join-Path $stage 'expected';traces=$t;original_vectors=$v;original_expected=$e}
 }
 $null=Tool xvlog (@('--sv')+@($sources|ForEach-Object{Split-Path -Leaf $_})) compile
 $null=Tool xelab @('work.tb_dds','--snapshot','dds_tb','--timescale','1ns/1ps') elaborate
 foreach($seed in $Seeds){$results.Add((SeedRun $seed "seed_$seed"))}
 if(!$SkipReplay){
  $again=SeedRun $Seeds[0] "seed_$($Seeds[0])_replay"
  if(($again.trace_sha256|ConvertTo-Json -Compress) -cne ($results[0].trace_sha256|ConvertTo-Json -Compress)){throw 'Seed replay changed trace'}
  $replay=[pscustomobject]@{seed=$Seeds[0];verdict='PASS';identical_traces=4}
 }
 $null=Tool xelab @('work.tb_ad9767_fault','--snapshot','dac_fault_tb','--timescale','1ns/1ps') fault_elaborate
 $faultPatterns=@{setup='setup time';hold='hold time';skew='ACLK WR1 phase mismatch';b_unknown='B clocks';first_mid='first input not midpoint'}
 $faults=@(foreach($fault in @('setup','hold','skew','b_unknown','first_mid')){
  $log=Tool xsim @('dac_fault_tb','--runall','--onfinish','quit','--onerror','quit','--testplusarg',('"FAULT={0}"' -f $fault),'--log',"fault_$fault.log") "fault_$fault" -ExpectFailure
  if($log -notmatch ('TEST_FAIL AD9767 '+$faultPatterns[$fault]) -or $log -match 'FAULT_NOT_DETECTED'){throw "Fault not detected correctly: $fault"}
  [pscustomobject]@{fault=$fault;verdict='EXPECTED_FAILURE_DETECTED';diagnostic=$faultPatterns[$fault]}
 })
 if($Project){
  $nd=Join-Path $report 'project';$nt=Join-Path $build 'native_traces';New-Item -ItemType Directory -Path $nd,$nt|Out-Null
  $s=$stages[$Seeds[0]]
  $args=@('-mode','batch','-notrace','-source',(Join-Path $PSScriptRoot 'check_dds_project.tcl'),'-log',(Join-Path $nd 'vivado.log'),'-journal',(Join-Path $nd 'vivado.jou'),'-tclargs',$nd,$s.vectors,$s.expected,$nt,"$($Seeds[0])")
  $commands.Add([pscustomobject]@{tool=Join-Path $VivadoBin 'vivado.bat';arguments=$args})
  $lines=@(& (Join-Path $VivadoBin 'vivado.bat') @args 2>&1);$exit=$LASTEXITCODE;$log=$lines -join [Environment]::NewLine
  $log|Set-Content -LiteralPath (Join-Path $nd 'console.log') -Encoding utf8
  if($exit -ne 0 -or $log -notmatch 'DDS_PROJECT_PASS' -or $log -match '(?im)^\s*(ERROR:|CRITICAL WARNING:|Fatal:|TEST_FAIL|DDS_PROJECT_FAIL)'){throw "Native DDS simulation failed: $nd"}
  foreach($name in @('xvlog.log','elaborate.log','simulate.log')){if((Get-Content -LiteralPath (Join-Path $nd $name) -Raw) -match '(?im)^\s*(WARNING:|ERROR:|Fatal:|TEST_FAIL)'){throw "Native HDL diagnostic: $name"}}
  Copy-Item -LiteralPath $nt -Destination (Join-Path $nd 'traces') -Recurse
  $files=@(Get-ChildItem -LiteralPath $nt -File -Filter '*.csv');if($files.Count -ne 4){throw 'Missing native traces'}
  foreach($f in $files){$ref=Join-Path $report "seed_$($Seeds[0])/traces/$($f.Name)";if((Get-FileHash -LiteralPath $f.FullName).Hash -ne (Get-FileHash -LiteralPath $ref).Hash){throw 'Native traces differ'}}
  $native=[pscustomobject]@{verdict='PASS';report=$nd;identical_traces=4;top='tb_dds'}
 }
 foreach($h in $hashes){if((Get-FileHash -LiteralPath $h.Path).Hash -ne $h.Hash){throw 'Sources changed during regression'}}
 $verdict='PASS'
}catch{$failure=$_.Exception.Message;throw}
finally{
 Pop-Location
 $commands|ConvertTo-Json -Depth 6|Set-Content -LiteralPath (Join-Path $report 'commands.json') -Encoding utf8
 [pscustomobject]@{verdict=$verdict;backend=$version;seeds=$Seeds;results=@($results.ToArray());replay=$replay;fault_detection=$faults;project=$native;source_sha256=$hashes;temporary_build=$build;failure=$failure;data_paths=@(foreach($k in $stages.Keys){[pscustomobject]@{seed=$k;paths=$stages[$k]}})}|ConvertTo-Json -Depth 10|Set-Content -LiteralPath (Join-Path $report 'manifest.json') -Encoding utf8
 Write-Output "DDS_REGRESSION_$verdict reports=$report"
}
