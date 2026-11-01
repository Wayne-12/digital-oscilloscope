#requires -Version 7.0
[CmdletBinding()]
param([string]$VivadoBin,[string]$PythonExe,[int[]]$Seeds=@(20261020,42),[switch]$SkipReplay,[switch]$Project)
$ErrorActionPreference='Stop';Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'vivado_toolchain.ps1')
$VivadoBin=Resolve-ScopeVivadoBin -RequestedBin $VivadoBin
if(!$PythonExe){$PythonExe=(Get-Command python.exe -ErrorAction Stop).Source}
if($Seeds.Count -eq 0 -or @($Seeds|Select-Object -Unique).Count -ne $Seeds.Count){throw 'Seeds must be nonempty and unique'}
$root=Split-Path -Parent $PSScriptRoot
$id=(Get-Date -Format 'yyyyMMdd_HHmmss')+'_'+[guid]::NewGuid().ToString('N').Substring(0,8)
$report=Join-Path $root "reports/spectrum/$id";$build=Join-Path ([IO.Path]::GetTempPath()) "spectrum_$id"
New-Item -ItemType Directory -Path $report,$build|Out-Null
$relative=@('rtl/common/scope_pkg.sv','rtl/common/multires_pkg.sv','rtl/common/fft_window_pkg.sv','rtl/common/spectrum_pkg.sv',
 'rtl/measure/measure_udiv.sv','rtl/measure/measurement_core.sv','rtl/trigger/trigger_edge.sv','rtl/trigger/trigger_core.sv',
 'rtl/capture/capture_bram.sv','rtl/capture/bram_capture.sv','rtl/dac_dds/dds_sine_lut.sv','rtl/dac_dds/dds_core.sv','rtl/multires/multires_envelope.sv',
 'rtl/measure/fft_hann_lut.sv','rtl/measure/fft_ip_wrapper.sv','rtl/measure/spectrum_isqrt.sv','rtl/measure/spectrum_analyzer.sv',
 'sim/tb/uart_capture_backend.sv','sim/tb/tb_fft_wrapper.sv','sim/tb/tb_spectrum.sv','sim/tb/tb_spectrum_capture.sv','sim/tb/tb_spectrum_control.sv','sim/tb/tb_spectrum_isqrt.sv')
$sources=@($relative|ForEach-Object{Join-Path $root $_})
$inputs=$sources+@('run_spectrum_tb.ps1','generate_spectrum_vectors.py','generate_fft_tables.py','audit_spectrum_traces.py','ensure_scope_fft_ip.tcl','prepare_fft_development.tcl','check_spectrum_project.tcl','create_smoke_project.tcl','ensure_scope_clock_ip.tcl','vivado_toolchain.ps1','vivado_toolchain.json'|ForEach-Object{Join-Path $PSScriptRoot $_})+@((Join-Path $root '../PC/protocol/spectrum_reference.py'),(Join-Path $root '../PC/tests/test_spectrum_reference.py'))
$hashes=@($inputs|Get-FileHash -Algorithm SHA256|Select-Object Path,Hash)
foreach($s in $sources){Copy-Item -LiteralPath $s -Destination $build}
$commands=[Collections.Generic.List[object]]::new();$results=[Collections.Generic.List[object]]::new();$negatives=[Collections.Generic.List[object]]::new();$stages=@{}
$verdict='FAIL';$failure=$null;$native=$null;$replay=$null
$traceNames=@('fft_raw.csv','spectrum_bins.csv','spectrum_results.csv','spectrum_capture_bins.csv','spectrum_capture_results.csv','spectrum_capture_roi.csv')
$tops=@('tb_fft_wrapper','tb_spectrum','tb_spectrum_capture','tb_spectrum_control','tb_spectrum_isqrt')
function CheckLog([string]$Log,[switch]$NativeLog){
 foreach($line in ($Log -split "`r?`n")){
  if($line -match '^\s*(ERROR:|CRITICAL WARNING:|Fatal:|TEST_FAIL|FATAL_ERROR:)'){throw "Tool diagnostic: $line"}
  if($line -match '^\s*WARNING:'){
   if($line -match '^\s*WARNING: \[VRFC 10-9145\].*xfft_v9_1_15.*scope_fft_1024.vhd:201') {continue}
   if($NativeLog -and $line -match '^\s*WARNING: \[(Board 49-26|Project 1-5713|Vivado 12-13650|Wavedata 42-489|Simtcl 6-168|Add_Wave-1)\]'){continue}
   throw "Unclassified warning: $line"
  }
 }
}
function Tool([string]$Name,[string[]]$ToolArgs,[string]$Label,[switch]$NativeLog){
 $p=Join-Path $VivadoBin "$Name.bat";$commands.Add([pscustomobject]@{tool=$p;arguments=$ToolArgs})
 $lines=@(& $p @ToolArgs 2>&1);$exit=$LASTEXITCODE;$log=$lines -join [Environment]::NewLine
 $log|Set-Content -LiteralPath (Join-Path $report "$Label.console.log") -Encoding utf8
 if($exit -ne 0){throw "$Label exit=$exit"};CheckLog $log -NativeLog:$NativeLog;return $log
}
function Audit([string]$Expected,[string]$Trace,[string]$Output){
 $lines=@(& $PythonExe (Join-Path $PSScriptRoot 'audit_spectrum_traces.py') --expected $Expected --traces $Trace --output $Output 2>&1)
 $lines|Set-Content -LiteralPath "$Output.log" -Encoding utf8
 if($LASTEXITCODE -ne 0 -or ($lines -join ' ') -notmatch 'SPECTRUM_TRACE_AUDIT_PASS'){throw "Trace audit failed: $lines"}
 return Get-Content -LiteralPath $Output -Raw|ConvertFrom-Json
}
function TraceHashes([string]$Directory){return @($traceNames|ForEach-Object{[pscustomobject]@{file=$_;sha256=(Get-FileHash -LiteralPath (Join-Path $Directory $_)).Hash}}|Sort-Object file)}
function SeedRun([int]$Seed,[string]$Label){
 $s=$stages[$Seed];$dest=Join-Path $report $Label;$td=Join-Path $dest 'traces';New-Item -ItemType Directory -Path $td|Out-Null
 foreach($top in $tops){
  $log=Tool xsim @($top,'--runall','--onfinish','quit','--onerror','quit','--sv_seed',"$Seed",'--testplusarg',('"SEED={0}"' -f $Seed),
   '--testplusarg',('"VECTOR_DIR={0}"' -f $s.vectors.Replace('\','/')),'--testplusarg',('"EXPECTED_DIR={0}"' -f $s.expected.Replace('\','/')),'--log',"$Label.$top.log") "$Label.$top"
  $pattern=switch($top){
   tb_fft_wrapper {"^TEST_PASS tb_fft_wrapper seed=$Seed cases=5 bins=5120 errors=0"}
   tb_spectrum {"^TEST_PASS tb_spectrum seed=$Seed cases=42 bins=43008 errors=0"}
   tb_spectrum_capture {"^TEST_PASS tb_spectrum_capture seed=$Seed jobs=2 errors=0"}
   tb_spectrum_control {'^TEST_PASS tb_spectrum_control controls=14 recoveries=14 invalid=2 errors=0'}
   tb_spectrum_isqrt {'^TEST_PASS tb_spectrum_isqrt cases=291 errors=0'}
  }
  if($log -notmatch "(?m)$pattern"){throw "Incomplete PASS $top"}
  Write-Host "SPECTRUM_TOP_PASS seed=$Seed top=$top"
 }
 foreach($n in $traceNames){Copy-Item -LiteralPath (Join-Path $build $n) -Destination $td}
 $au=Audit $s.expected $td (Join-Path $dest 'audit.json')
 return [pscustomobject]@{seed=$Seed;verdict='PASS';audit=$au;traces=(TraceHashes $td)}
}
Push-Location -LiteralPath $build
try{
 $null=Tool xsim @('--version') version
 $unit=@(& $PythonExe -m unittest discover -s (Join-Path $root '../PC/tests') -p test_spectrum_reference.py -v 2>&1)
 $unit|Set-Content -LiteralPath (Join-Path $report 'pc_tests.log') -Encoding utf8;if($LASTEXITCODE -ne 0){throw 'Python oracle tests failed'}
 foreach($seed in $Seeds){
  $v=Join-Path $root "sim/vectors/spectrum/$id/seed_$seed";$e=Join-Path $root "sim/expected/spectrum/$id/seed_$seed"
  $gen=@(& $PythonExe (Join-Path $PSScriptRoot 'generate_spectrum_vectors.py') --output $v --expected-output $e --seed $seed 2>&1)
  $gen|Set-Content -LiteralPath (Join-Path $report "seed_$seed.oracle.log") -Encoding utf8
  if($LASTEXITCODE -ne 0 -or ($gen -join ' ') -notmatch 'DFT_ORACLE_PASS'){throw 'DFT generation failed'}
  $sd=Join-Path $build "seed_$seed";New-Item -ItemType Directory -Path $sd|Out-Null
  Copy-Item -LiteralPath $v -Destination (Join-Path $sd vectors) -Recurse;Copy-Item -LiteralPath $e -Destination (Join-Path $sd expected) -Recurse
  $stages[$seed]=[pscustomobject]@{vectors=Join-Path $sd vectors;expected=Join-Path $sd expected;original_vectors=$v;original_expected=$e}
 }
 $prep=Tool vivado @('-mode','batch','-notrace','-source',(Join-Path $PSScriptRoot 'prepare_fft_development.tcl'),'-log','prepare.log','-journal','prepare.jou','-tclargs',$build,$root) prepare -NativeLog
 if($prep -notmatch 'FFT_PREPARE_PASS'){throw 'FFT generation incomplete'}
 # Preserve the actual IP products/configuration; only XCI is registered in the project.
 $ipDir=Join-Path $root 'ip/scope_fft_1024';New-Item -ItemType Directory -Path $ipDir -Force|Out-Null
 Copy-Item -Path (Join-Path $build 'ip/scope_fft_1024/*') -Destination $ipDir -Recurse -Force
 Copy-Item -LiteralPath (Join-Path $build 'ip/fft_contract_readback.txt') -Destination (Join-Path $root 'ip/fft_contract_readback.txt')
 Copy-Item -LiteralPath (Join-Path $VivadoBin '../data/xsim/xsim.ini') -Destination $build
 $null=Tool xvhdl @('--relax','ip/scope_fft_1024/sim/scope_fft_1024.vhd') compile_vendor
 $null=Tool xvlog (@('--sv')+@($sources|ForEach-Object{Split-Path -Leaf $_})) compile
 # Read the exact dependency list exported by this installed Vivado release.
 $exported=Get-Content -LiteralPath (Join-Path $build 'export/scope_fft_1024/xsim/scope_fft_1024.sh') -Raw
 $elab=@($exported -split "`n"|Where-Object{$_ -match '^  xelab '})[0]
 $libs=@([regex]::Matches($elab,'-L ([A-Za-z0-9_]+)')|ForEach-Object{$_.Groups[1].Value}|Where-Object{$_ -ne 'xil_defaultlib'})
 if($libs -notcontains 'xfft_v9_1_15'){throw 'Unexpected FFT dependency revision'}
 $libArgs=@();foreach($l in $libs){$libArgs+=@('-L',$l)}
 foreach($top in $tops){$null=Tool xelab (@("work.$top",'--snapshot',$top,'--timescale','1ns/1ps')+$libArgs) "elaborate.$top"}
 foreach($seed in $Seeds){$results.Add((SeedRun $seed "seed_$seed"))}
 if(!$SkipReplay){
  $again=SeedRun $Seeds[0] "seed_$($Seeds[0])_replay"
  if(($again.traces|ConvertTo-Json -Compress) -cne ($results[0].traces|ConvertTo-Json -Compress)){throw 'Replay changed FFT traces'}
  $replay=[pscustomobject]@{verdict='PASS';seed=$Seeds[0];identical_traces=6}
 }
 foreach($bad in 1..2){
  $null=Tool xelab (@('work.tb_spectrum_control','--snapshot',"fft_fault_$bad",'--generic_top',('"BAD={0}"' -f $bad),'--timescale','1ns/1ps')+$libArgs) "fault_$bad.elaborate"
  $sig=if($bad -eq 1){'FFT_INPUT_TLAST'}else{'SPECTRUM_TIMESTAMP'}
  $lines=@(& (Join-Path $VivadoBin 'xsim.bat') "fft_fault_$bad" --runall --onfinish quit --onerror quit --log "fault_$bad.log" 2>&1);$log=$lines -join [Environment]::NewLine
  $log|Set-Content -LiteralPath (Join-Path $report "fault_$bad.console.log") -Encoding utf8
  if($log -notmatch "Fatal: $sig" -or $log -match 'NEGATIVE_TEST_DID_NOT_FIRE|TEST_PASS'){throw 'Expected protocol assertion did not fire'}
  $negatives.Add([pscustomobject]@{case=$bad;verdict='PASS';expected_fatal=$sig})
 }
 if($Project){
  $nd=Join-Path $report project;$nt=Join-Path $nd traces;New-Item -ItemType Directory -Path $nt|Out-Null
  $pd=Resolve-ScopeProjectDir -FpgaRoot $root;$sim=Join-Path $pd scope_smoke.sim
  if(Test-Path -LiteralPath $sim){
   $resolved=(Resolve-Path -LiteralPath $sim).ProviderPath
   if(!$resolved.Equals($sim,[StringComparison]::OrdinalIgnoreCase) -or !$resolved.StartsWith($pd+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)){throw 'Unsafe simulation cleanup'}
   if(@(Get-Item -LiteralPath $sim -Force;Get-ChildItem -LiteralPath $sim -Recurse -Force)|Where-Object{$_.Attributes -band [IO.FileAttributes]::ReparsePoint}){throw 'Refusing reparse point cleanup'}
   Remove-Item -LiteralPath $resolved -Recurse -Force
  }
  "Deleted exact generated directory $sim"|Set-Content -LiteralPath (Join-Path $nd clean_rebuild.txt)
  $s=$stages[$Seeds[0]]
  $log=Tool vivado @('-mode','batch','-notrace','-source',(Join-Path $PSScriptRoot check_spectrum_project.tcl),'-log',(Join-Path $nd vivado.log),'-journal',(Join-Path $nd vivado.jou),'-tclargs',$nd,$s.vectors,$s.expected,$nt,"$($Seeds[0])") project -NativeLog
  if($log -notmatch 'SPECTRUM_PROJECT_PASS'){throw 'Native clean rebuild incomplete'}
  foreach($top in $tops){foreach($l in @('xvlog','elaborate','simulate')){CheckLog (Get-Content -LiteralPath (Join-Path $nd "$top.$l.log") -Raw) -NativeLog}}
  $au=Audit $s.expected $nt (Join-Path $nd audit.json);$nh=TraceHashes $nt
  if(($nh|ConvertTo-Json -Compress) -cne ($results[0].traces|ConvertTo-Json -Compress)){throw 'Native and standalone FFT traces differ'}
  $native=[pscustomobject]@{verdict='PASS';tops=5;identical_traces=6;audit=$au}
 }
 foreach($h in $hashes){if((Get-FileHash -LiteralPath $h.Path).Hash -ne $h.Hash){throw 'Sources changed during regression'}}
 $verdict='PASS'
}catch{$failure=$_.Exception.Message;throw}
finally{
 Pop-Location
 [pscustomobject]@{verdict=$verdict;seeds=$Seeds;results=$results;replay=$replay;native=$native;negative_assertions=$negatives;source_sha256=$hashes;commands=$commands;stages=@(foreach($seed in $Seeds){[pscustomobject]@{seed=$seed;paths=$stages[$seed]}});temporary_build=$build;failure=$failure}|ConvertTo-Json -Depth 12|Set-Content -LiteralPath (Join-Path $report manifest.json) -Encoding utf8
 Write-Host "SPECTRUM_REGRESSION_$verdict reports=$report"
}
