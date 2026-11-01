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
$report=Join-Path $root "reports/loopback/$id"
$build=Join-Path ([IO.Path]::GetTempPath()) "loopback_$id"
New-Item -ItemType Directory -Path $report,$build | Out-Null
$relative=@('rtl/common/scope_pkg.sv','rtl/dac_dds/dds_sine_lut.sv','rtl/dac_dds/dds_core.sv',
 'rtl/adc_if/adc_capture.sv','sim/models/ideal_clock.sv','sim/models/ad9767_model.sv','sim/models/ad9226_model.sv',
 'sim/models/loopback_channel_model.sv','sim/models/sample_record_readout_model.sv','sim/tb/loopback_scenario.sv','sim/tb/tb_loopback.sv')
$sources=@($relative|ForEach-Object{Join-Path $root $_})
$hashInputs=@($sources)+@('run_loopback_tb.ps1','generate_loopback_vectors.py','audit_loopback_traces.py','check_loopback_project.tcl',
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
 $args=@('loopback_tb','--runall','--onfinish','quit','--onerror','quit','--sv_seed',"$Seed",
 '--testplusarg',('"VECTOR_DIR={0}"' -f $s.vectors.Replace('\','/')),
 '--testplusarg',('"EXPECTED_DIR={0}"' -f $s.expected.Replace('\','/')),
 '--testplusarg',('"TRACE_DIR={0}"' -f $s.traces.Replace('\','/')),'--log',"$Label.log")
 $log=Tool xsim $args $Label
 if($log -notmatch '(?m)^TEST_PASS tb_loopback profiles=13 delay_endpoints=2 errors=0'){throw 'Missing terminal loopback PASS'}
 $matches=@([regex]::Matches($log,'(?m)^LOOP_CASE_PASS key=(\S+) profile=(\d+) tco_ps=(\d+) cases=(\d+) cycles=(\d+) captured=(\d+) reported=(\d+) seed=(\d+) errors=0'))
 if($matches.Count -ne 26 -or @($matches|ForEach-Object{$_.Groups[1].Value}|Select-Object -Unique).Count -ne 26){throw 'Incomplete loopback profile/delay coverage'}
 if(@([regex]::Matches($log,'(?m)^LOOP_TEST_PASS ')).Count -ne 366){throw 'Missing loopback subtests'}
 foreach($match in $matches){
  $pidValue=[int]$match.Groups[2].Value;$delayValue=[int]$match.Groups[3].Value
  $expectedCycles=if($pidValue -eq 0){140960}else{40704};$expectedCases=if($pidValue -eq 0){15}else{14}
  if($match.Groups[1].Value -ne ('loop_p{0}_d{1}' -f $pidValue,$delayValue) -or $pidValue -lt 0 -or $pidValue -gt 12 -or $delayValue -notin @(3500,7000) -or
    [int]$match.Groups[4].Value -ne $expectedCases -or [int]$match.Groups[5].Value -ne $expectedCycles -or
    [int]$match.Groups[6].Value -ne ($expectedCycles-8*$expectedCases) -or $match.Groups[6].Value -ne $match.Groups[7].Value -or [int]$match.Groups[8].Value -ne $Seed){throw 'Loopback case count/seed mismatch'}
 }
 $dest=Join-Path $report $Label;New-Item -ItemType Directory -Path $dest|Out-Null
 Copy-Item -LiteralPath $s.traces -Destination (Join-Path $dest 'traces') -Recurse
 $traces=@(Get-ChildItem -LiteralPath (Join-Path $dest 'traces') -Filter '*.csv' -File)
 if($traces.Count -ne 52){throw 'Missing loopback traces'}
 $traceHashes=@($traces|Get-FileHash -Algorithm SHA256|ForEach-Object{[pscustomobject]@{file=Split-Path -Leaf $_.Path;hash=$_.Hash}}|Sort-Object file)
 $audit=@(& $PythonExe (Join-Path $PSScriptRoot 'audit_loopback_traces.py') --traces (Join-Path $dest 'traces') --oracle (Join-Path $s.expected 'oracle_manifest.json') --output (Join-Path $dest 'trace_audit.json') 2>&1)
 $audit|Set-Content -LiteralPath (Join-Path $dest 'audit.console.log') -Encoding utf8
 if($LASTEXITCODE -ne 0 -or ($audit -join ' ') -notmatch 'TRACE_AUDIT_PASS'){throw "LOOPBACK trace audit failed: $audit"}
 $result=[pscustomobject]@{seed=$Seed;verdict='PASS';profiles=13;delay_endpoints=2;cycles=1258816;trace_sha256=$traceHashes}
 $result|ConvertTo-Json -Depth 6|Set-Content -LiteralPath (Join-Path $dest 'manifest.json') -Encoding utf8
 Write-Host "LOOPBACK_SEED_PASS seed=$Seed profiles=13 delay_endpoints=2"
 return $result
}
Push-Location -LiteralPath $build
try{
 $version=Tool xsim @('--version') version
 foreach($seed in $Seeds){
  $v=Join-Path $root "sim/vectors/loopback/$id/seed_$seed";$e=Join-Path $root "sim/expected/loopback/$id/seed_$seed"
  $gen=@(& $PythonExe (Join-Path $PSScriptRoot 'generate_loopback_vectors.py') --output $v --expected-output $e --seed $seed 2>&1)
  $gen|Set-Content -LiteralPath (Join-Path $report "seed_$seed.oracle.log") -Encoding utf8
  if($LASTEXITCODE -ne 0 -or ($gen-join ' ') -notmatch 'ORACLE_PASS'){throw 'Oracle generation failed'}
  $stage=Join-Path $build "seed_$seed";New-Item -ItemType Directory -Path $stage|Out-Null
  Copy-Item -LiteralPath $v -Destination (Join-Path $stage 'vectors') -Recurse
  Copy-Item -LiteralPath $e -Destination (Join-Path $stage 'expected') -Recurse
  $t=Join-Path $stage 'traces';New-Item -ItemType Directory -Path $t|Out-Null
  $stages[$seed]=[pscustomobject]@{vectors=Join-Path $stage 'vectors';expected=Join-Path $stage 'expected';traces=$t;original_vectors=$v;original_expected=$e}
 }
 $null=Tool xvlog (@('--sv')+@($sources|ForEach-Object{Split-Path -Leaf $_})) compile
 $null=Tool xelab @('work.tb_loopback','--snapshot','loopback_tb','--timescale','1ns/1ps') elaborate
 foreach($seed in $Seeds){$results.Add((SeedRun $seed "seed_$seed"))}
 if(!$SkipReplay){
  $again=SeedRun $Seeds[0] "seed_$($Seeds[0])_replay"
  if(($again.trace_sha256|ConvertTo-Json -Compress) -cne ($results[0].trace_sha256|ConvertTo-Json -Compress)){throw 'Seed replay changed trace'}
  $replay=[pscustomobject]@{seed=$Seeds[0];verdict='PASS';identical_traces=52}
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
  $args=@('-mode','batch','-notrace','-source',(Join-Path $PSScriptRoot 'check_loopback_project.tcl'),'-log',(Join-Path $nd 'vivado.log'),'-journal',(Join-Path $nd 'vivado.jou'),'-tclargs',$nd,$s.vectors,$s.expected,$nt,"$($Seeds[0])")
  $commands.Add([pscustomobject]@{tool=Join-Path $VivadoBin 'vivado.bat';arguments=$args})
  $lines=@(& (Join-Path $VivadoBin 'vivado.bat') @args 2>&1);$exit=$LASTEXITCODE;$log=$lines -join [Environment]::NewLine
  $log|Set-Content -LiteralPath (Join-Path $nd 'console.log') -Encoding utf8
  if($exit -ne 0 -or $log -notmatch 'LOOPBACK_PROJECT_PASS' -or $log -match '(?im)^\s*(ERROR:|CRITICAL WARNING:|Fatal:|TEST_FAIL|LOOPBACK_PROJECT_FAIL)'){throw "Native LOOPBACK simulation failed: $nd"}
  foreach($name in @('xvlog.log','elaborate.log','simulate.log')){if((Get-Content -LiteralPath (Join-Path $nd $name) -Raw) -match '(?im)^\s*(WARNING:|ERROR:|Fatal:|TEST_FAIL)'){throw "Native HDL diagnostic: $name"}}
  $nativeCompile=Get-Content -LiteralPath (Join-Path $nd 'xvlog.log') -Raw
  foreach($moduleName in @('scope_pkg.sv','ad9226_model.sv','adc_capture.sv','loopback_channel_model.sv','tb_loopback.sv')){if($nativeCompile -notmatch [regex]::Escape($moduleName)){throw "Missing fresh native compilation: $moduleName"}}
  Copy-Item -LiteralPath $nt -Destination (Join-Path $nd 'traces') -Recurse
  $files=@(Get-ChildItem -LiteralPath $nt -File -Filter '*.csv');if($files.Count -ne 52){throw 'Missing native traces'}
  foreach($f in $files){$ref=Join-Path $report "seed_$($Seeds[0])/traces/$($f.Name)";if((Get-FileHash -LiteralPath $f.FullName).Hash -ne (Get-FileHash -LiteralPath $ref).Hash){throw 'Native traces differ'}}
  $native=[pscustomobject]@{verdict='PASS';report=$nd;identical_traces=52;top='tb_loopback';clean_rebuild=$true}
 }
 foreach($h in $hashes){if((Get-FileHash -LiteralPath $h.Path).Hash -ne $h.Hash){throw 'Sources changed during regression'}}
 $verdict='PASS'
}catch{$failure=$_.Exception.Message;throw}
finally{
 Pop-Location
 $commands|ConvertTo-Json -Depth 6|Set-Content -LiteralPath (Join-Path $report 'commands.json') -Encoding utf8
 [pscustomobject]@{verdict=$verdict;backend=$version;seeds=$Seeds;results=@($results.ToArray());replay=$replay;project=$native;source_sha256=$hashes;temporary_build=$build;failure=$failure;data_paths=@(foreach($k in $stages.Keys){[pscustomobject]@{seed=$k;paths=$stages[$k]}})}|ConvertTo-Json -Depth 10|Set-Content -LiteralPath (Join-Path $report 'manifest.json') -Encoding utf8
 Write-Output "LOOPBACK_REGRESSION_$verdict reports=$report"
}

