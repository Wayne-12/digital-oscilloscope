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
$report=Join-Path $root "reports/capture/$id"
$build=Join-Path ([IO.Path]::GetTempPath()) "capture_$id"
New-Item -ItemType Directory -Path $report,$build | Out-Null
$relative=@('rtl/common/scope_pkg.sv','rtl/trigger/trigger_edge.sv','rtl/trigger/trigger_core.sv','rtl/capture/capture_bram.sv',
 'rtl/capture/bram_capture.sv','sim/models/ideal_clock.sv','sim/tb/trigger_scenario.sv','sim/tb/capture_scenario.sv','sim/tb/tb_capture.sv')
$sources=@($relative|ForEach-Object{Join-Path $root $_})
$hashInputs=@($sources)+@('run_capture_tb.ps1','generate_capture_vectors.py','audit_capture_traces.py','check_capture_project.tcl',
 'check_capture_synthesis.tcl','create_smoke_project.tcl','ensure_scope_clock_ip.tcl','vivado_toolchain.ps1','vivado_toolchain.json'|ForEach-Object{Join-Path $PSScriptRoot $_})
$hashes=@($hashInputs|Get-FileHash -Algorithm SHA256|Select-Object Path,Hash)
foreach($s in $sources){Copy-Item -LiteralPath $s -Destination $build}
$results=[Collections.Generic.List[object]]::new();$commands=[Collections.Generic.List[object]]::new()
$stages=@{};$verdict='FAIL';$failure=$null;$replay=$null;$native=$null;$synthesis=$null;$version=$null
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
 $args=@('capture_tb','--runall','--onfinish','quit','--onerror','quit','--sv_seed',"$Seed",
 '--testplusarg',('"VECTOR_DIR={0}"' -f $s.vectors.Replace('\','/')),
 '--testplusarg',('"EXPECTED_DIR={0}"' -f $s.expected.Replace('\','/')),
 '--testplusarg',('"TRACE_DIR={0}"' -f $s.traces.Replace('\','/')),'--log',"$Label.log")
 $log=Tool xsim $args $Label
 if($log -notmatch '(?m)^TEST_PASS tb_capture scenarios=5 errors=0'){throw 'Missing terminal capture PASS'}
 $matches=@([regex]::Matches($log,'(?m)^CAPTURE_SCENARIO_PASS sid=(\d+) adc=(\d+) sys=(\d+) cases=(\d+) frames=(\d+) points=(\d+) rereads=(\d+) aux_points=(\d+) seed=(\d+) errors=0'))
 if($matches.Count -ne 5 -or (@($matches|ForEach-Object{$_.Groups[1].Value}|Sort-Object)-join ',') -ne '0,1,2,3,4'){throw 'Missing capture clock scenarios'}
 $oracle=Get-Content -LiteralPath (Join-Path $s.expected 'oracle_manifest.json') -Raw|ConvertFrom-Json
 foreach($match in $matches){
  $sidValue=[int]$match.Groups[1].Value;$ref=$oracle.scenarios[$sidValue]
  if([int]$match.Groups[2].Value -ne $ref.adc_rate_hz -or [int]$match.Groups[3].Value -ne $ref.sys_rate_hz -or
   [int]$match.Groups[4].Value -ne $ref.cases -or [int]$match.Groups[5].Value -ne @($ref.frames).Count -or
   [int]$match.Groups[9].Value -ne $Seed){throw 'Capture scenario count/seed mismatch'}
 }
 if(@([regex]::Matches($log,'(?m)^CAPTURE_FRAME_PASS ')).Count -ne 71 -or
    @([regex]::Matches($log,'(?m)^CAPTURE_AUX_PASS ')).Count -ne 5 -or
    $log -notmatch '(?m)^TRIGGER_UNIT_PASS checks=28672 hits=\d+ errors=0'){throw 'Missing frame/aux/hysteresis tests'}
 $dest=Join-Path $report $Label;New-Item -ItemType Directory -Path $dest|Out-Null
 Copy-Item -LiteralPath $s.traces -Destination (Join-Path $dest 'traces') -Recurse
 $traces=@(Get-ChildItem -LiteralPath (Join-Path $dest 'traces') -Filter '*.csv' -File)
 if($traces.Count -ne 11){throw 'Missing capture traces'}
 $traceHashes=@($traces|Get-FileHash -Algorithm SHA256|ForEach-Object{[pscustomobject]@{file=Split-Path -Leaf $_.Path;hash=$_.Hash}}|Sort-Object file)
 $audit=@(& $PythonExe (Join-Path $PSScriptRoot 'audit_capture_traces.py') --traces (Join-Path $dest 'traces') --oracle-dir $s.expected --vector-dir $s.vectors --output (Join-Path $dest 'trace_audit.json') 2>&1)
 $audit|Set-Content -LiteralPath (Join-Path $dest 'audit.console.log') -Encoding utf8
 if($LASTEXITCODE -ne 0 -or ($audit -join ' ') -notmatch 'TRACE_AUDIT_PASS'){throw "CAPTURE trace audit failed: $audit"}
 $result=[pscustomobject]@{seed=$Seed;verdict='PASS';scenarios=5;frames=71;distinct_frame_points=1163264;trace_sha256=$traceHashes}
 $result|ConvertTo-Json -Depth 6|Set-Content -LiteralPath (Join-Path $dest 'manifest.json') -Encoding utf8
 Write-Host "CAPTURE_SEED_PASS seed=$Seed scenarios=5 frames=71"
 return $result
}
Push-Location -LiteralPath $build
try{
 $version=Tool xsim @('--version') version
 foreach($seed in $Seeds){
  $v=Join-Path $root "sim/vectors/capture/$id/seed_$seed";$e=Join-Path $root "sim/expected/capture/$id/seed_$seed"
  $gen=@(& $PythonExe (Join-Path $PSScriptRoot 'generate_capture_vectors.py') --output $v --expected-output $e --seed $seed 2>&1)
  $gen|Set-Content -LiteralPath (Join-Path $report "seed_$seed.oracle.log") -Encoding utf8
  if($LASTEXITCODE -ne 0 -or ($gen-join ' ') -notmatch 'ORACLE_PASS'){throw 'Oracle generation failed'}
  $stage=Join-Path $build "seed_$seed";New-Item -ItemType Directory -Path $stage|Out-Null
  Copy-Item -LiteralPath $v -Destination (Join-Path $stage 'vectors') -Recurse
  Copy-Item -LiteralPath $e -Destination (Join-Path $stage 'expected') -Recurse
  $t=Join-Path $stage 'traces';New-Item -ItemType Directory -Path $t|Out-Null
  $stages[$seed]=[pscustomobject]@{vectors=Join-Path $stage 'vectors';expected=Join-Path $stage 'expected';traces=$t;original_vectors=$v;original_expected=$e}
 }
 $null=Tool xvlog (@('--sv')+@($sources|ForEach-Object{Split-Path -Leaf $_})) compile
 $null=Tool xelab @('work.tb_capture','--snapshot','capture_tb','--timescale','1ns/1ps') elaborate
 foreach($seed in $Seeds){$results.Add((SeedRun $seed "seed_$seed"))}
 if(!$SkipReplay){
  $again=SeedRun $Seeds[0] "seed_$($Seeds[0])_replay"
  if(($again.trace_sha256|ConvertTo-Json -Compress) -cne ($results[0].trace_sha256|ConvertTo-Json -Compress)){throw 'Seed replay changed trace'}
  $replay=[pscustomobject]@{seed=$Seeds[0];verdict='PASS';identical_traces=11}
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
  $args=@('-mode','batch','-notrace','-source',(Join-Path $PSScriptRoot 'check_capture_project.tcl'),'-log',(Join-Path $nd 'vivado.log'),'-journal',(Join-Path $nd 'vivado.jou'),'-tclargs',$nd,$s.vectors,$s.expected,$nt,"$($Seeds[0])")
  $commands.Add([pscustomobject]@{tool=Join-Path $VivadoBin 'vivado.bat';arguments=$args})
  $lines=@(& (Join-Path $VivadoBin 'vivado.bat') @args 2>&1);$exit=$LASTEXITCODE;$log=$lines -join [Environment]::NewLine
  $log|Set-Content -LiteralPath (Join-Path $nd 'console.log') -Encoding utf8
  if($exit -ne 0 -or $log -notmatch 'CAPTURE_PROJECT_PASS' -or $log -match '(?im)^\s*(ERROR:|CRITICAL WARNING:|Fatal:|TEST_FAIL|CAPTURE_PROJECT_FAIL)'){throw "Native CAPTURE simulation failed: $nd"}
  foreach($name in @('xvlog.log','elaborate.log','simulate.log')){if((Get-Content -LiteralPath (Join-Path $nd $name) -Raw) -match '(?im)^\s*(WARNING:|ERROR:|Fatal:|TEST_FAIL)'){throw "Native HDL diagnostic: $name"}}
  $nativeCompile=Get-Content -LiteralPath (Join-Path $nd 'xvlog.log') -Raw
  foreach($moduleName in @('scope_pkg.sv','trigger_edge.sv','capture_bram.sv','bram_capture.sv','tb_capture.sv')){if($nativeCompile -notmatch [regex]::Escape($moduleName)){throw "Missing fresh native compilation: $moduleName"}}
  Copy-Item -LiteralPath $nt -Destination (Join-Path $nd 'traces') -Recurse
  $files=@(Get-ChildItem -LiteralPath $nt -File -Filter '*.csv');if($files.Count -ne 11){throw 'Missing native traces'}
  foreach($f in $files){$ref=Join-Path $report "seed_$($Seeds[0])/traces/$($f.Name)";if((Get-FileHash -LiteralPath $f.FullName).Hash -ne (Get-FileHash -LiteralPath $ref).Hash){throw 'Native traces differ'}}
  $native=[pscustomobject]@{verdict='PASS';report=$nd;identical_traces=11;top='tb_capture';clean_rebuild=$true}
  $synthDir=Join-Path $report 'synthesis';New-Item -ItemType Directory -Path $synthDir|Out-Null
  $synthSources=Join-Path $build 'synthesis_sources';$synthOut=Join-Path $build 'synthesis_reports'
  New-Item -ItemType Directory -Path $synthSources,$synthOut|Out-Null
  foreach($rel in @('rtl/common/scope_pkg.sv','rtl/trigger/trigger_edge.sv','rtl/trigger/trigger_core.sv','rtl/capture/capture_bram.sv','rtl/capture/bram_capture.sv')){
   $original=Join-Path $root $rel;$copy=Join-Path $synthSources $rel
   New-Item -ItemType Directory -Path (Split-Path -Parent $copy) -Force|Out-Null
   Copy-Item -LiteralPath $original -Destination $copy
   if((Get-FileHash -LiteralPath $original).Hash -ne (Get-FileHash -LiteralPath $copy).Hash){throw 'Synthesis source staging changed bytes'}
  }
  $synthScript=Join-Path $synthSources 'check_capture_synthesis.tcl';Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'check_capture_synthesis.tcl') -Destination $synthScript
  $synthArgs=@('-mode','batch','-notrace','-source',$synthScript,'-log',(Join-Path $synthOut 'vivado.log'),'-journal',(Join-Path $synthOut 'vivado.jou'),'-tclargs',$synthOut,$synthSources)
  $commands.Add([pscustomobject]@{tool=Join-Path $VivadoBin 'vivado.bat';arguments=$synthArgs})
  $synthLines=@(& (Join-Path $VivadoBin 'vivado.bat') @synthArgs 2>&1);$synthExit=$LASTEXITCODE;$synthText=$synthLines -join [Environment]::NewLine
  Copy-Item -LiteralPath $synthOut -Destination (Join-Path $synthDir 'artifacts') -Recurse
  $synthText|Set-Content -LiteralPath (Join-Path $synthDir 'console.log') -Encoding utf8
  if($synthExit -ne 0 -or $synthText -notmatch 'CAPTURE_BRAM_SYNTH_PASS' -or $synthText -match '(?im)^\s*(WARNING:|ERROR:|CRITICAL WARNING:|CAPTURE_BRAM_SYNTH_FAIL)'){throw "BRAM inference check failed: $synthDir"}
  $resources=Get-Content -LiteralPath (Join-Path $synthOut 'resources.json') -Raw|ConvertFrom-Json
  $synthesis=[pscustomobject]@{verdict='PASS';report=$synthDir;resources=$resources}

 }
 foreach($h in $hashes){if((Get-FileHash -LiteralPath $h.Path).Hash -ne $h.Hash){throw 'Sources changed during regression'}}
 $verdict='PASS'
}catch{$failure=$_.Exception.Message;throw}
finally{
 Pop-Location
 $commands|ConvertTo-Json -Depth 6|Set-Content -LiteralPath (Join-Path $report 'commands.json') -Encoding utf8
 [pscustomobject]@{verdict=$verdict;backend=$version;seeds=$Seeds;results=@($results.ToArray());replay=$replay;project=$native;synthesis=$synthesis;source_sha256=$hashes;temporary_build=$build;failure=$failure;data_paths=@(foreach($k in $stages.Keys){[pscustomobject]@{seed=$k;paths=$stages[$k]}})}|ConvertTo-Json -Depth 10|Set-Content -LiteralPath (Join-Path $report 'manifest.json') -Encoding utf8
 Write-Output "CAPTURE_REGRESSION_$verdict reports=$report"
}


