#requires -Version 7.0
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
$report=Join-Path $root "reports/measure/$id"
$build=Join-Path ([IO.Path]::GetTempPath()) "measure_$id"
New-Item -ItemType Directory -Path $report,$build | Out-Null
$relative=@('rtl/common/scope_pkg.sv','rtl/trigger/trigger_edge.sv','rtl/trigger/trigger_core.sv',
 'rtl/capture/capture_bram.sv','rtl/capture/bram_capture.sv','rtl/measure/measure_udiv.sv',
 'rtl/measure/measurement_core.sv','sim/tb/measure_capture_scenario.sv','sim/tb/tb_measure.sv','sim/tb/tb_trigger.sv','sim/tb/tb_measure_capture.sv')
$sources=@($relative|ForEach-Object{Join-Path $root $_})
$hashInputs=@($sources)+@('run_measure_tb.ps1','generate_measure_vectors.py','audit_measure_traces.py','check_measure_project.tcl',
 'create_smoke_project.tcl','ensure_scope_clock_ip.tcl','vivado_toolchain.ps1','vivado_toolchain.json'|ForEach-Object{Join-Path $PSScriptRoot $_})
$hashes=@($hashInputs|Get-FileHash -Algorithm SHA256|Select-Object Path,Hash)
foreach($s in $sources){Copy-Item -LiteralPath $s -Destination $build}
$results=[Collections.Generic.List[object]]::new();$commands=[Collections.Generic.List[object]]::new()
$stages=@{};$verdict='FAIL';$failure=$null;$replay=$null;$native=$null;$version=$null
function Tool([string]$Name,[string[]]$ToolArgs,[string]$Label){
 $path=Join-Path $VivadoBin "$Name.bat"
 $commands.Add([pscustomobject]@{tool=$path;arguments=$ToolArgs})
 $lines=@(& $path @ToolArgs 2>&1);$exit=$LASTEXITCODE;$log=$lines -join [Environment]::NewLine
 $log|Set-Content -LiteralPath (Join-Path $report "$Label.console.log") -Encoding utf8
 if($exit -ne 0 -or $log -match '(?im)^\s*(WARNING:|CRITICAL WARNING:|ERROR:|Fatal:|TEST_FAIL|FATAL_ERROR:)'){throw "$Label failed: $report/$Label.console.log"}
 return $log
}
function SeedRun([int]$Seed,[string]$Label,[switch]$All){
 $s=$stages[$Seed]
 $selected=@(1,2,3,4,5,6,7)
 foreach($feature in $selected){
  $top=if($feature -le 4){'tb_trigger'}else{'tb_measure'}
  $snapshot=if($feature -le 4){'trigger_tb'}else{'measure_tb'}
  $args=@($snapshot,'--runall','--onfinish','quit','--onerror','quit','--sv_seed',"$Seed",
   '--testplusarg',('"SEED={0}"' -f $Seed),'--testplusarg',('"STAGE={0}"' -f $feature),
   '--testplusarg',('"VECTOR_DIR={0}"' -f $s.vectors.Replace('\','/')),
   '--testplusarg',('"EXPECTED_DIR={0}"' -f $s.expected.Replace('\','/')),
   '--testplusarg',('"TRACE_DIR={0}"' -f $s.traces.Replace('\','/')),'--log',"$Label.stage$feature.log")
  $log=Tool xsim $args "$Label.stage$feature"
  if($log -notmatch "(?m)^TEST_PASS $top stage=$feature seed=$Seed checks=\d+ errors=0"){throw 'Missing terminal measurement PASS'}
  if($feature -eq 0){if(@([regex]::Matches($log,'(?m)^FEATURE_PASS ')).Count -ne 7){throw 'Missing feature results'}}
  elseif($log -notmatch "(?m)^FEATURE_PASS stage=$feature "){throw 'Missing independent feature PASS'}
  if($feature -eq 7 -and ($log -notmatch '(?m)^MEASURE_PROTOCOL_PASS invalid_configs=3 reset_aborts=13 errors=0' -or
    @([regex]::Matches($log,'(?m)^MEASURE_RESET_PASS ')).Count -ne 13)){throw 'Missing measurement protocol tests'}

 }
 $integration=Tool xsim @('measure_capture_tb','--runall','--onfinish','quit','--onerror','quit','--sv_seed',"$Seed",
   '--testplusarg',('"SEED={0}"' -f $Seed),'--testplusarg',('"VECTOR_DIR={0}"' -f $s.vectors.Replace('\','/')),
   '--testplusarg',('"EXPECTED_DIR={0}"' -f $s.expected.Replace('\','/')),
   '--testplusarg',('"TRACE_DIR={0}"' -f $s.traces.Replace('\','/'))) "$Label.capture"
 if($integration -notmatch '(?m)^TEST_PASS tb_measure_capture errors=0' -or
   @([regex]::Matches($integration,'(?m)^MEASURE_CAPTURE_PASS ')).Count -ne 9 -or
   $integration -notmatch '(?m)^MEASURE_CAPTURE_CONFIG_PASS invalid_arms=4 errors=0'){throw 'Missing independent capture/measurement integration'}
 $dest=Join-Path $report $Label;New-Item -ItemType Directory -Path $dest|Out-Null
 Copy-Item -LiteralPath $s.traces -Destination (Join-Path $dest 'traces') -Recurse
 $traces=@(Get-ChildItem -LiteralPath (Join-Path $dest 'traces') -Filter '*.csv' -File)
 if($traces.Count -ne 9){throw 'Missing measurement traces'}
 $traceHashes=@($traces|Get-FileHash -Algorithm SHA256|ForEach-Object{[pscustomobject]@{file=Split-Path -Leaf $_.Path;hash=$_.Hash}}|Sort-Object file)
 $audit=@(& $PythonExe (Join-Path $PSScriptRoot 'audit_measure_traces.py') --traces (Join-Path $dest 'traces') --expected $s.expected --vectors $s.vectors --output (Join-Path $dest 'trace_audit.json') 2>&1)
 $audit|Set-Content -LiteralPath (Join-Path $dest 'audit.console.log') -Encoding utf8
 if($LASTEXITCODE -ne 0 -or ($audit -join ' ') -notmatch 'TRACE_AUDIT_PASS'){throw "Measurement trace audit failed: $audit"}
 $audited=Get-Content -LiteralPath (Join-Path $dest 'trace_audit.json') -Raw|ConvertFrom-Json
 $result=[pscustomobject]@{seed=$Seed;verdict='PASS';features=7;trigger_cases=$audited.trigger_cases;
  measurement_cases=$audited.measurement_cases;integration_frames=$audited.integration_frames;
  trigger_samples=$audited.trigger_samples;integration_points=$audited.integration_points;trace_sha256=$traceHashes}
 Write-Host "MEASURE_SEED_PASS seed=$Seed features=7 frames=9"
 return $result
}
Push-Location -LiteralPath $build
try{
 $version=Tool xsim @('--version') version
 foreach($seed in $Seeds){
  $v=Join-Path $root "sim/vectors/measure/$id/seed_$seed";$e=Join-Path $root "sim/expected/measure/$id/seed_$seed"
  $gen=@(& $PythonExe (Join-Path $PSScriptRoot 'generate_measure_vectors.py') --output $v --expected-output $e --seed $seed 2>&1)
  $gen|Set-Content -LiteralPath (Join-Path $report "seed_$seed.oracle.log") -Encoding utf8
  if($LASTEXITCODE -ne 0 -or ($gen-join ' ') -notmatch 'ORACLE_PASS'){throw 'Oracle generation failed'}
  $stage=Join-Path $build "seed_$seed";New-Item -ItemType Directory -Path $stage|Out-Null
  Copy-Item -LiteralPath $v -Destination (Join-Path $stage 'vectors') -Recurse
  Copy-Item -LiteralPath $e -Destination (Join-Path $stage 'expected') -Recurse
  $t=Join-Path $stage 'traces';New-Item -ItemType Directory -Path $t|Out-Null
  $stages[$seed]=[pscustomobject]@{vectors=Join-Path $stage 'vectors';expected=Join-Path $stage 'expected';traces=$t;original_vectors=$v;original_expected=$e}
 }
 $null=Tool xvlog (@('--sv')+@($sources|ForEach-Object{Split-Path -Leaf $_})) compile
 $null=Tool xelab @('work.tb_measure','--snapshot','measure_tb','--timescale','1ns/1ps') elaborate
 $null=Tool xelab @('work.tb_trigger','--snapshot','trigger_tb','--timescale','1ns/1ps') elaborate_trigger
 $null=Tool xelab @('work.tb_measure_capture','--snapshot','measure_capture_tb','--timescale','1ns/1ps') elaborate_capture
 foreach($seed in $Seeds){$results.Add((SeedRun $seed "seed_$seed"))}
 if(!$SkipReplay){
  $again=SeedRun $Seeds[0] "seed_$($Seeds[0])_replay" -All
  if(($again.trace_sha256|ConvertTo-Json -Compress) -cne ($results[0].trace_sha256|ConvertTo-Json -Compress)){throw 'Seed replay changed trace'}
  $replay=[pscustomobject]@{seed=$Seeds[0];verdict='PASS';identical_traces=9}
 }
 if($Project){
  $nd=Join-Path $report 'project';$nt=Join-Path $build 'native_traces';New-Item -ItemType Directory -Path $nd,$nt|Out-Null
  # Rebuild native simulation from zero; package-dependent SDB files can
  # otherwise survive a previous top which did not use the ADC modules.
  $projectDir=Resolve-ScopeProjectDir -FpgaRoot $root
  $simulationDir=Join-Path $projectDir 'scope_smoke.sim'
  if(Test-Path -LiteralPath $simulationDir){
   $resolvedProject=(Resolve-Path -LiteralPath $projectDir).ProviderPath
   $resolvedSimulation=(Resolve-Path -LiteralPath $simulationDir).ProviderPath
   $expectedSimulation=Join-Path $resolvedProject 'scope_smoke.sim'
   if(!$resolvedSimulation.Equals($expectedSimulation,[StringComparison]::OrdinalIgnoreCase) -or
      !$resolvedSimulation.StartsWith($resolvedProject+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)){throw "Unsafe simulation cleanup target: $resolvedSimulation"}
   $simulationItem=Get-Item -LiteralPath $resolvedSimulation -Force
   $reparsePoints=@(Get-ChildItem -LiteralPath $resolvedSimulation -Recurse -Force|Where-Object{$_.Attributes -band [IO.FileAttributes]::ReparsePoint})
   if(($simulationItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -or $reparsePoints.Count -ne 0){throw 'Refusing simulation cleanup containing reparse points'}
   Remove-Item -LiteralPath $resolvedSimulation -Recurse -Force
   if(Test-Path -LiteralPath $resolvedSimulation){throw 'Simulation cleanup incomplete'}
  }
  "Clean native behavioral rebuild; generated target=$simulationDir"|Set-Content -LiteralPath (Join-Path $nd 'clean_rebuild.txt') -Encoding utf8
  $s=$stages[$Seeds[0]]
  $args=@('-mode','batch','-notrace','-source',(Join-Path $PSScriptRoot 'check_measure_project.tcl'),'-log',(Join-Path $nd 'vivado.log'),'-journal',(Join-Path $nd 'vivado.jou'),'-tclargs',$nd,$s.vectors,$s.expected,$nt,"$($Seeds[0])")
  $commands.Add([pscustomobject]@{tool=Join-Path $VivadoBin 'vivado.bat';arguments=$args})
  $lines=@(& (Join-Path $VivadoBin 'vivado.bat') @args 2>&1);$exit=$LASTEXITCODE;$log=$lines -join [Environment]::NewLine
  $log|Set-Content -LiteralPath (Join-Path $nd 'console.log') -Encoding utf8
  if($exit -ne 0 -or $log -notmatch 'MEASURE_PROJECT_PASS' -or $log -match '(?im)^\s*(ERROR:|CRITICAL WARNING:|Fatal:|TEST_FAIL|MEASURE_PROJECT_FAIL)'){throw "Native MEASURE simulation failed: $nd"}
  foreach($name in @('xvlog.log','elaborate.log','simulate.log')){if((Get-Content -LiteralPath (Join-Path $nd $name) -Raw) -match '(?im)^\s*(WARNING:|ERROR:|Fatal:|TEST_FAIL)'){throw "Native HDL diagnostic: $name"}}
  $nativeCompile=Get-Content -LiteralPath (Join-Path $nd 'xvlog.log') -Raw
  foreach($moduleName in @('scope_pkg.sv','trigger_core.sv','measurement_core.sv','bram_capture.sv','tb_measure.sv')){if($nativeCompile -notmatch [regex]::Escape($moduleName)){throw "Missing fresh native compilation: $moduleName"}}
  Copy-Item -LiteralPath $nt -Destination (Join-Path $nd 'traces') -Recurse
  $files=@(Get-ChildItem -LiteralPath $nt -File -Filter '*.csv');if($files.Count -ne 9){throw 'Missing native traces'}
  foreach($f in $files){$ref=Join-Path $report "seed_$($Seeds[0])/traces/$($f.Name)";if((Get-FileHash -LiteralPath $f.FullName).Hash -ne (Get-FileHash -LiteralPath $ref).Hash){throw 'Native traces differ'}}
  $native=[pscustomobject]@{verdict='PASS';report=$nd;identical_traces=9;top='tb_measure';clean_rebuild=$true}
 }
 foreach($h in $hashes){if((Get-FileHash -LiteralPath $h.Path).Hash -ne $h.Hash){throw 'Sources changed during regression'}}
 $verdict='PASS'
}catch{$failure=$_.Exception.Message;throw}
finally{
 Pop-Location
 $commands|ConvertTo-Json -Depth 6|Set-Content -LiteralPath (Join-Path $report 'commands.json') -Encoding utf8
 [pscustomobject]@{verdict=$verdict;backend=$version;seeds=$Seeds;results=@($results.ToArray());replay=$replay;project=$native;source_sha256=$hashes;temporary_build=$build;failure=$failure;data_paths=@(foreach($k in $stages.Keys){[pscustomobject]@{seed=$k;paths=$stages[$k]}})}|ConvertTo-Json -Depth 10|Set-Content -LiteralPath (Join-Path $report 'manifest.json') -Encoding utf8
 Write-Output "MEASURE_REGRESSION_$verdict reports=$report"
}


