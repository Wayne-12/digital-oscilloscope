#requires -Version 7.0
[CmdletBinding()]
param([string]$VivadoBin,[string]$PythonExe,[ValidateRange(0,2147483647)][int[]]$Seeds=@(20261020,42),[switch]$Project,[switch]$SkipReplay)
$ErrorActionPreference='Stop';Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot vivado_toolchain.ps1);. (Join-Path $PSScriptRoot innovation_sources.ps1)
$VivadoBin=Resolve-ScopeVivadoBin -RequestedBin $VivadoBin;if(!$PythonExe){$PythonExe=(Get-Command python.exe).Source}
if(!$Seeds.Count -or @($Seeds|Select-Object -Unique).Count -ne $Seeds.Count){throw 'Use nonempty unique seeds'}
$root=Split-Path -Parent $PSScriptRoot;$id=(Get-Date -Format yyyyMMdd_HHmmss)+'_'+[guid]::NewGuid().ToString('N').Substring(0,8)
$report=Join-Path $root "reports/innovation/$id";$build=Join-Path ([IO.Path]::GetTempPath()) "innovation_$id"
New-Item -ItemType Directory -Path $report,$build|Out-Null
$sources=@($InnovationRelativeSources|ForEach-Object{Join-Path $root $_});foreach($p in $sources){Copy-Item -LiteralPath $p -Destination $build}
$extra=@('run_innovation_tb.ps1','innovation_sources.ps1','generate_innovation_vectors.py','audit_innovation_traces.py','innovation_channel_oracle.py','check_innovation_project.tcl','ensure_scope_fft_ip.tcl','prepare_fft_development.tcl','ensure_scope_clock_ip.tcl','create_smoke_project.tcl','vivado_toolchain.ps1','vivado_toolchain.json')
$inputs=$sources+@($extra|ForEach-Object{Join-Path $PSScriptRoot $_})+@((Join-Path $root '../PC/protocol/innovation_reference.py'),(Join-Path $root '../PC/protocol/spectrum_reference.py'),(Join-Path $root '../PC/protocol/scope_protocol.py'),(Join-Path $root '../PC/tests/test_innovation_reference.py'))
$hashes=@($inputs|Get-FileHash|Select-Object Path,Hash)
$tops=@('tb_innovation_units','tb_innovation_health','tb_innovation_bram','tb_innovation_control')
$traceNames=@('health_raw.csv','health_fits.csv','health_features.csv','health_fft.csv','health_display.csv','innovation_bram_jobs.csv')
foreach($backend in @('bram')){foreach($job in 0..2){foreach($kind in @('uart','container')){$traceNames+="innovation_${backend}_job${job}_${kind}.hex"}}}
foreach($backend in @('bram')){foreach($profile in 0..3){
 $tops+="tb_innovation_${backend}_channel${profile}"
 $traceNames+="innovation_${backend}_channel${profile}_source.csv","innovation_${backend}_channel${profile}_jobs.csv"
 foreach($job in 0..2){foreach($kind in @('uart','container')){$traceNames+="innovation_${backend}_channel${profile}_job${job}_${kind}.hex"}}
}}
$stages=@{};$results=[Collections.Generic.List[object]]::new();$commands=[Collections.Generic.List[object]]::new();$negatives=[Collections.Generic.List[object]]::new()
$verdict='FAIL';$failure=$null;$replay=$null;$native=$null
function CheckLog([string]$Log,[switch]$NativeLog){
 foreach($line in ($Log -split "`r?`n")){
  if($line -match '^\s*(ERROR:|CRITICAL WARNING:|Fatal:|TEST_FAIL|FATAL_ERROR:)'){throw "Diagnostic: $line"}
  if($line -match '^\s*WARNING:'){
   if($line -match '^\s*WARNING: \[VRFC 10-9145\].*xfft_v9_1_15.*scope_fft_1024.vhd:201'){continue}
   if($NativeLog -and $line -match '^\s*WARNING: \[(Board 49-26|Project 1-5713|Vivado 12-13650|Wavedata 42-489|Simtcl 6-168|Add_Wave-1)\]'){continue}
   throw "Unclassified warning: $line"
  }
 }
}
function Tool([string]$Name,[string[]]$ToolArgs,[string]$Label,[switch]$NativeLog){
 $p=Join-Path $VivadoBin "$Name.bat";$commands.Add([pscustomobject]@{tool=$p;arguments=$ToolArgs})
 $lines=@(& $p @ToolArgs 2>&1);$exit=$LASTEXITCODE;$log=$lines -join [Environment]::NewLine;$log|Set-Content -LiteralPath (Join-Path $report "$Label.console.log") -Encoding utf8
 if($exit){throw "$Label exit=$exit"};CheckLog $log -NativeLog:$NativeLog;return $log
}
function TraceHashes([string]$Directory){return @($traceNames|ForEach-Object{[pscustomobject]@{file=$_;sha256=(Get-FileHash -LiteralPath (Join-Path $Directory $_)).Hash}}|Sort-Object file)}
function Audit([string]$Vectors,[string]$Traces,[string]$Output){
 $log=@(& $PythonExe (Join-Path $PSScriptRoot audit_innovation_traces.py) --vectors $Vectors --traces $Traces --output $Output 2>&1)
 $log|Set-Content -LiteralPath "$Output.log" -Encoding utf8
 if($LASTEXITCODE -or ($log -join ' ') -notmatch 'INNOVATION_TRACE_AUDIT_PASS'){throw "Innovation audit: $log"}
 return Get-Content -LiteralPath $Output -Raw|ConvertFrom-Json
}
function PassCheck([string]$Log,[string]$Top,[int]$Seed){
 if($Top -match '^tb_innovation_(bram)_channel[0-3]$'){
  $backend=0
  if($Log -notmatch "(?m)^TEST_PASS tb_innovation_capture backend=$backend seed=$Seed jobs=3 errors=0"){throw "Incomplete connected channel PASS $Top"}
  return
 }
 $pattern=switch($Top){
  tb_innovation_units {'^TEST_PASS tb_innovation_units fit=38 apply=1024 health=16 aborts=2 errors=0'}
  tb_innovation_health {"^TEST_PASS tb_innovation_health seed=$Seed profiles=8 raw=354304 corrected=34816 fft_bins=8192 errors=0"}
  tb_innovation_bram {"^TEST_PASS tb_innovation_capture backend=0 seed=$Seed jobs=3 errors=0"}
  tb_innovation_control {'^TEST_PASS tb_innovation_control invalid=2 cancels=3 resets=3 recoveries=6 errors=0'}
 }
 if($Log -notmatch "(?m)$pattern"){throw "Incomplete terminal PASS $Top"}
}
function SeedRun([int]$Seed,[string]$Label){
 $s=$stages[$Seed];$td=Join-Path $report "$Label/traces";New-Item -ItemType Directory -Path $td|Out-Null
 foreach($top in $tops){
  $log=Tool xsim @($top,'--runall','--onfinish','quit','--onerror','quit','--sv_seed',"$Seed",'--testplusarg',('"SEED={0}"' -f $Seed),'--testplusarg',('"VECTOR_DIR={0}"' -f $s.vectors.Replace('\','/')),'--log',"$Label.$top.log") "$Label.$top"
  PassCheck $log $top $Seed;Write-Host "INNOVATION_TOP_PASS seed=$Seed top=$top"
 }
 foreach($n in $traceNames){Copy-Item -LiteralPath (Join-Path $build $n) -Destination $td}
 $au=Audit $s.vectors $td (Join-Path $report "$Label/audit.json")
 return [pscustomobject]@{seed=$Seed;verdict='PASS';audit=$au;traces=(TraceHashes $td)}
}
Push-Location -LiteralPath $build
try{
 $null=Tool xsim @('--version') version
 $unit=@(& $PythonExe -m unittest discover -s (Join-Path $root '../PC/tests') -p test_innovation_reference.py -v 2>&1)
 $unit|Set-Content -LiteralPath (Join-Path $report pc_tests.log) -Encoding utf8;if($LASTEXITCODE -or ($unit -join ' ') -notmatch 'Ran 6 tests'){throw 'PC tests incomplete'}
 foreach($seed in $Seeds){
  $v=Join-Path $root "sim/vectors/innovation/$id/seed_$seed";$gen=@(& $PythonExe (Join-Path $PSScriptRoot generate_innovation_vectors.py) --output $v --seed $seed 2>&1)
  $gen|Set-Content -LiteralPath (Join-Path $report "seed_$seed.oracle.log") -Encoding utf8;if($LASTEXITCODE -or ($gen -join ' ') -notmatch 'INNOVATION_ORACLE_PASS'){throw 'Oracle generation failed'}
  $sd=Join-Path $build "seed_$seed";New-Item -ItemType Directory -Path $sd|Out-Null;Copy-Item -LiteralPath $v -Destination (Join-Path $sd vectors) -Recurse
  $stages[$seed]=[pscustomobject]@{vectors=Join-Path $sd vectors;original_vectors=$v}
 }
 $log=Tool vivado @('-mode','batch','-notrace','-source',(Join-Path $PSScriptRoot prepare_fft_development.tcl),'-log','prepare.log','-journal','prepare.jou','-tclargs',$build,$root) prepare -NativeLog
 if($log -notmatch 'FFT_PREPARE_PASS'){throw 'FFT preparation incomplete'}
 Copy-Item -LiteralPath (Join-Path $VivadoBin '../data/xsim/xsim.ini') -Destination $build
 $null=Tool xvhdl @('--relax','ip/scope_fft_1024/sim/scope_fft_1024.vhd') compile_vendor
 $null=Tool xvlog (@('--sv')+@($sources|ForEach-Object{Split-Path -Leaf $_})) compile
 $exported=Get-Content -LiteralPath (Join-Path $build export/scope_fft_1024/xsim/scope_fft_1024.sh) -Raw;$line=@($exported -split "`n"|Where-Object{$_ -match '^  xelab '})[0]
 $libArgs=@();foreach($m in [regex]::Matches($line,'-L ([A-Za-z0-9_]+)')){if($m.Groups[1].Value -ne 'xil_defaultlib'){$libArgs+=@('-L',$m.Groups[1].Value)}}
 foreach($top in $tops){$null=Tool xelab (@("work.$top",'--snapshot',$top,'--timescale','1ns/1ps')+$libArgs) "elaborate.$top"}
 foreach($seed in $Seeds){$results.Add((SeedRun $seed "seed_$seed"))}
 if(!$SkipReplay){$again=SeedRun $Seeds[0] "seed_$($Seeds[0])_replay";if(($again.traces|ConvertTo-Json -Compress) -cne ($results[0].traces|ConvertTo-Json -Compress)){throw 'Replay changed innovation traces'};$replay=[pscustomobject]@{verdict='PASS';seed=$Seeds[0];identical_traces=$traceNames.Count}}
 foreach($bad in 1..2){
  $null=Tool xelab (@('work.tb_innovation_control','--snapshot',"innovation_fault_$bad",'--generic_top',('"BAD={0}"' -f $bad),'--timescale','1ns/1ps')+$libArgs) "fault_$bad.elaborate"
  $lines=@(& (Join-Path $VivadoBin xsim.bat) "innovation_fault_$bad" --runall --onfinish quit --onerror quit --log "fault_$bad.log" 2>&1);$log=$lines -join [Environment]::NewLine
  $log|Set-Content -LiteralPath (Join-Path $report "fault_$bad.console.log") -Encoding utf8;$sig=if($bad -eq 1){'INNOVATION_BUCKET_RECORD'}else{'INNOVATION_ROI_RECORD'}
  if($log -notmatch "Fatal: $sig" -or $log -match 'NEGATIVE_TEST_DID_NOT_FIRE|TEST_PASS'){throw 'Missing expected negative assertion'};$negatives.Add([pscustomobject]@{case=$bad;verdict='PASS';expected_fatal=$sig})
 }
 if($Project){
  $nd=Join-Path $report project;$nt=Join-Path $nd traces;New-Item -ItemType Directory -Path $nt|Out-Null
  $pd=Resolve-ScopeProjectDir -FpgaRoot $root;$sim=Join-Path $pd scope_smoke.sim
  if(Test-Path -LiteralPath $sim){
   $resolved=(Resolve-Path -LiteralPath $sim).ProviderPath
   if(!$resolved.Equals($sim,[StringComparison]::OrdinalIgnoreCase) -or !$resolved.StartsWith($pd+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)){throw 'Unsafe cleanup path'}
   if(@(Get-Item -LiteralPath $sim -Force;Get-ChildItem -LiteralPath $sim -Recurse -Force)|Where-Object{$_.Attributes -band [IO.FileAttributes]::ReparsePoint}){throw 'Refusing reparse point cleanup'}
   Remove-Item -LiteralPath $resolved -Recurse -Force
  }
  "Deleted exact generated directory $sim"|Set-Content -LiteralPath (Join-Path $nd clean_rebuild.txt)
  $s=$stages[$Seeds[0]];$log=Tool vivado @('-mode','batch','-notrace','-source',(Join-Path $PSScriptRoot check_innovation_project.tcl),'-log',(Join-Path $nd vivado.log),'-journal',(Join-Path $nd vivado.jou),'-tclargs',$nd,$s.vectors,$nt,"$($Seeds[0])") project -NativeLog
  if($log -notmatch 'INNOVATION_PROJECT_PASS'){throw 'Native project incomplete'}
  foreach($top in $tops){foreach($kind in @('xvlog','elaborate','simulate')){CheckLog (Get-Content -LiteralPath (Join-Path $nd "$top.$kind.log") -Raw) -NativeLog};PassCheck (Get-Content -LiteralPath (Join-Path $nd "$top.simulate.log") -Raw) $top $Seeds[0]}
  $au=Audit $s.vectors $nt (Join-Path $nd audit.json);$nh=TraceHashes $nt
  if(($nh|ConvertTo-Json -Compress) -cne ($results[0].traces|ConvertTo-Json -Compress)){throw 'Native traces differ'};$native=[pscustomobject]@{verdict='PASS';tops=$tops.Count;identical_traces=$traceNames.Count;audit=$au}
 }
 foreach($h in $hashes){if((Get-FileHash -LiteralPath $h.Path).Hash -ne $h.Hash){throw "Sources changed: $($h.Path)"}}
 $verdict='PASS'
}catch{$failure=$_.Exception.Message;throw}
finally{
 Pop-Location
 [pscustomobject]@{verdict=$verdict;seeds=$Seeds;results=$results;replay=$replay;native=$native;negative_assertions=$negatives;source_sha256=$hashes;commands=$commands;stages=@(foreach($seed in $Seeds){[pscustomobject]@{seed=$seed;paths=$stages[$seed]}});temporary_build=$build;failure=$failure}|ConvertTo-Json -Depth 14|Set-Content -LiteralPath (Join-Path $report manifest.json) -Encoding utf8
 Write-Host "INNOVATION_REGRESSION_$verdict reports=$report"
}
