[CmdletBinding()]
param(
    [string]$VivadoBin,
    [string]$PythonExe,
    [ValidateRange(0,2147483647)][int[]]$Seeds = @(20261020,42),
    [ValidateRange(10000,100000)][int]$RandomSamples = 12000,
    [switch]$SkipReplay,
    [switch]$Project
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'vivado_toolchain.ps1')
$VivadoBin=Resolve-ScopeVivadoBin -RequestedBin $VivadoBin
if ([string]::IsNullOrWhiteSpace($PythonExe)) {
    $pythonCommand=Get-Command python.exe -ErrorAction Stop
    $PythonExe=$pythonCommand.Source
}
if ($Seeds.Count -eq 0 -or @($Seeds | Select-Object -Unique).Count -ne $Seeds.Count) {
    throw 'Supply at least one seed without duplicates.'
}
$fpgaRoot=Split-Path -Parent $PSScriptRoot
$runId=(Get-Date -Format 'yyyyMMdd_HHmmss')+'_'+[guid]::NewGuid().ToString('N').Substring(0,8)
$reportDir=Join-Path $fpgaRoot "reports/ad9226/$runId"
$buildDir=Join-Path ([IO.Path]::GetTempPath()) "ad9226_$runId"
New-Item -ItemType Directory -Path $reportDir,$buildDir | Out-Null
$relativeSources=@('rtl/common/scope_pkg.sv','rtl/adc_if/adc_capture.sv',
    'sim/models/ideal_clock.sv','sim/models/ad9226_model.sv','sim/tb/ad9226_scenario.sv','sim/tb/tb_ad9226.sv')
$sourceFiles=@($relativeSources | ForEach-Object {Join-Path $fpgaRoot $_})
$sourceHashes=@($sourceFiles | Get-FileHash -Algorithm SHA256 | Select-Object Path,Hash)
foreach($source in $sourceFiles){Copy-Item -LiteralPath $source -Destination $buildDir}
$results=[Collections.Generic.List[object]]::new()
$commands=[Collections.Generic.List[object]]::new()
$staging=@{}
$verdict='FAIL'
$failure=$null
$version=$null
$replay=$null
$projectResult=$null

function Invoke-AdcTool {
    param([string]$Tool,[string[]]$ToolArgs,[string]$Label)
    $path=Join-Path $VivadoBin "$Tool.bat"
    $commands.Add([pscustomobject]@{tool=$path;arguments=$ToolArgs})
    $lines=@(& $path @ToolArgs 2>&1)
    $code=$LASTEXITCODE
    $log=$lines -join [Environment]::NewLine
    $log | Set-Content -LiteralPath (Join-Path $reportDir "$Label.console.log") -Encoding utf8
    if($code -ne 0 -or $log -match '(?im)^\s*(WARNING:|ERROR:|Fatal:|TEST_FAIL|FATAL_ERROR:|application-specific initialization failed:)') {
        throw "$Label failed (exit $code); see $reportDir/$Label.console.log"
    }
    return $log
}

function Invoke-AdcSeed {
    param([int]$Seed,[string]$Label)
    $paths=$staging[$Seed]
    $runArgs=@('ad9226_tb','--runall','--onfinish','quit','--onerror','quit','--sv_seed',"$Seed",
        '--testplusarg',('"SEED={0}"' -f $Seed),
        '--testplusarg',('"VECTOR_DIR={0}"' -f $paths.vectors.Replace('\','/')),
        '--testplusarg',('"EXPECTED_DIR={0}"' -f $paths.expected.Replace('\','/')),
        '--testplusarg',('"TRACE_DIR={0}"' -f $paths.traces.Replace('\','/')),'--log',"$Label.log")
    $log=Invoke-AdcTool -Tool xsim -ToolArgs $runArgs -Label $Label
    if($log -notmatch '(?m)^TEST_PASS tb_ad9226 cases=18 latency=7\+1 random_per_case_at_least=10000 errors=0') {
        throw 'Missing ADC terminal PASS.'
    }
    $caseMatches=@([regex]::Matches($log,
        '(?m)^ADC_CASE_PASS case=(\S+) compared=(\d+) random=(\d+) continuous=(\d+) model_latency=7 capture_extra=1 total_latency=8 ramp=4096 zero=256 forced_high=(\d+) forced_low=(\d+) missing=(\d+) seed=(\d+)'))
    if($caseMatches.Count -ne 18 -or @($caseMatches | ForEach-Object {$_.Groups[1].Value} | Select-Object -Unique).Count -ne 18) {
        throw 'Missing or duplicate ADC case coverage.'
    }
    $oracle=Get-Content -LiteralPath (Join-Path $paths.expected 'oracle_manifest.json') -Raw | ConvertFrom-Json
    $cases=@(foreach($match in $caseMatches) {
        if([int]$match.Groups[2].Value -ne $oracle.total_samples -or
           [int]$match.Groups[3].Value -ne $RandomSamples -or [int]$match.Groups[4].Value -ne $RandomSamples -or
           [int]$match.Groups[5].Value -lt 1 -or [int]$match.Groups[6].Value -lt 1 -or
           [int]$match.Groups[8].Value -ne $Seed) {throw 'Incomplete ADC comparison, continuity, or OTR fault coverage.'}
        [pscustomobject]@{case=$match.Groups[1].Value;compared=[int]$match.Groups[2].Value
            random=[int]$match.Groups[3].Value;continuous=[int]$match.Groups[4].Value
            forced_high=[int]$match.Groups[5].Value;forced_low=[int]$match.Groups[6].Value
            missing=[int]$match.Groups[7].Value;seed=$Seed;verdict='PASS'}
    })
    $expectedNames=@(
        foreach($rate in @(10000000,25000000,50000000,65000000)) {
            foreach($delay in @(3500,7000)) {'r{0}_d{1}_p0_f0' -f $rate,$delay}
        }
        foreach($profile in 1..4) {foreach($delay in @(3500,7000)) {'r25000000_d{0}_p{1}_f0' -f $delay,$profile}}
        foreach($delay in @(3500,7000)) {'r25000000_d{0}_p0_f100' -f $delay}
    )
    if((@($cases.case | Sort-Object) -join ',') -ne (@($expectedNames | Sort-Object) -join ',')) {
        throw 'ADC clock/delay/profile matrix mismatch.'
    }
    $stage=Join-Path $reportDir $Label
    New-Item -ItemType Directory -Path $stage | Out-Null
    Copy-Item -LiteralPath $paths.traces -Destination (Join-Path $stage 'traces') -Recurse
    $traceFiles=@(Get-ChildItem -LiteralPath (Join-Path $stage 'traces') -Filter '*.csv' -File)
    if($traceFiles.Count -ne 18) {throw 'Missing ADC sample traces.'}
    $traceHashes=@($traceFiles | Get-FileHash -Algorithm SHA256 | ForEach-Object {
        [pscustomobject]@{file=(Split-Path -Leaf $_.Path);hash=$_.Hash}
    } | Sort-Object file)
    $result=[pscustomobject]@{seed=$Seed;verdict='PASS';cases=$cases;trace_sha256=$traceHashes}
    [pscustomobject]@{backend=$version.Trim();source_sha256=$sourceHashes;watchdog='20ms';result=$result
        oracle=(Join-Path $paths.expected 'oracle_manifest.json');plusargs=$runArgs
    } | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $stage 'manifest.json') -Encoding utf8
    Write-Host "ADC_SEED_PASS seed=$Seed cases=18 random_per_case=$RandomSamples"
    return $result
}

Push-Location -LiteralPath $buildDir
try {
    $pythonVersion=@(& $PythonExe --version 2>&1) -join ' '
    if($LASTEXITCODE -ne 0) {throw 'Cannot run Python oracle generator.'}
    $version=Invoke-AdcTool -Tool xsim -ToolArgs @('--version') -Label version
    foreach($seed in $Seeds) {
        $vectorOriginal=Join-Path $fpgaRoot "sim/vectors/ad9226/$runId/seed_$seed"
        $expectedOriginal=Join-Path $fpgaRoot "sim/expected/ad9226/$runId/seed_$seed"
        $oracleArgs=@((Join-Path $PSScriptRoot 'generate_ad9226_vectors.py'),
            '--output',$vectorOriginal,'--expected-output',$expectedOriginal,'--seed',"$seed",'--random-samples',"$RandomSamples")
        $generation=@(& $PythonExe @oracleArgs 2>&1)
        $generationCode=$LASTEXITCODE
        $generationText=$generation -join [Environment]::NewLine
        $generationText | Set-Content -LiteralPath (Join-Path $reportDir "seed_$seed.oracle.log") -Encoding utf8
        if($generationCode -ne 0 -or $generationText -notmatch 'ORACLE_PASS') {throw 'Independent ADC oracle generation failed.'}
        $dataDir=Join-Path $buildDir "data_seed_$seed"
        New-Item -ItemType Directory -Path $dataDir | Out-Null
        $v=Join-Path $dataDir 'vectors';$e=Join-Path $dataDir 'expected';$t=Join-Path $dataDir 'traces'
        Copy-Item -LiteralPath $vectorOriginal -Destination $v -Recurse
        Copy-Item -LiteralPath $expectedOriginal -Destination $e -Recurse
        New-Item -ItemType Directory -Path $t | Out-Null
        $staging[$seed]=[pscustomobject]@{vectors=$v;expected=$e;traces=$t
            original_vectors=$vectorOriginal;original_expected=$expectedOriginal}
    }
    $compileArgs=@('--sv')+@($sourceFiles | ForEach-Object {Split-Path -Leaf $_})
    $null=Invoke-AdcTool -Tool xvlog -ToolArgs $compileArgs -Label compile
    $null=Invoke-AdcTool -Tool xelab -ToolArgs @('work.tb_ad9226','--snapshot','ad9226_tb','--timescale','1ns/1ps') -Label elaborate
    foreach($seed in $Seeds) {$results.Add((Invoke-AdcSeed -Seed $seed -Label "seed_$seed"))}
    if(-not $SkipReplay) {
        $again=Invoke-AdcSeed -Seed $Seeds[0] -Label "seed_$($Seeds[0])_replay"
        if(($again.trace_sha256 | ConvertTo-Json -Depth 4 -Compress) -cne
           ($results[0].trace_sha256 | ConvertTo-Json -Depth 4 -Compress)) {throw 'ADC replay sample traces changed.'}
        $replay=[pscustomobject]@{seed=$Seeds[0];verdict='PASS';trace_files_identical=18}
        Write-Host "ADC_REPLAY_PASS seed=$($Seeds[0]) trace_files_identical=18"
    }
    if($Project) {
        $nativeDir=Join-Path $reportDir 'project'
        $nativeTraceDir=Join-Path $buildDir 'project_traces'
        New-Item -ItemType Directory -Path $nativeDir,$nativeTraceDir | Out-Null
        $paths=$staging[$Seeds[0]]
        $argsNative=@('-mode','batch','-notrace','-source',(Join-Path $PSScriptRoot 'check_ad9226_project.tcl'),
            '-log',(Join-Path $nativeDir 'vivado.log'),'-journal',(Join-Path $nativeDir 'vivado.jou'),
            '-tclargs',$nativeDir,$paths.vectors,$paths.expected,$nativeTraceDir,"$($Seeds[0])")
        $commands.Add([pscustomobject]@{tool=(Join-Path $VivadoBin 'vivado.bat');arguments=$argsNative})
        $nativeLines=@(& (Join-Path $VivadoBin 'vivado.bat') @argsNative 2>&1)
        $nativeExit=$LASTEXITCODE
        $nativeText=$nativeLines -join [Environment]::NewLine
        $nativeText | Set-Content -LiteralPath (Join-Path $nativeDir 'console.log') -Encoding utf8
        if($nativeExit -ne 0 -or $nativeText -notmatch 'ADC_PROJECT_PASS' -or
            $nativeText -match '(?im)^\s*(ERROR:|CRITICAL WARNING:|Fatal:|TEST_FAIL|ADC_PROJECT_FAIL)') {
            throw "ADC native project simulation failed; see $nativeDir/console.log"
        }
        foreach($name in @('xvlog.log','elaborate.log','simulate.log')) {
            if((Get-Content -LiteralPath (Join-Path $nativeDir $name) -Raw) -match '(?im)^\s*(WARNING:|ERROR:|Fatal:|TEST_FAIL)') {
                throw "HDL diagnostic in native $name"
            }
        }
        Copy-Item -LiteralPath $nativeTraceDir -Destination (Join-Path $nativeDir 'traces') -Recurse
        $nativeTraces=@(Get-ChildItem -LiteralPath $nativeTraceDir -Filter '*.csv' -File)
        if($nativeTraces.Count -ne 18) {throw 'Missing native ADC sample traces.'}
        foreach($trace in $nativeTraces) {
            $reference=Join-Path $reportDir "seed_$($Seeds[0])/traces/$($trace.Name)"
            if((Get-FileHash -LiteralPath $trace.FullName -Algorithm SHA256).Hash -ne
               (Get-FileHash -LiteralPath $reference -Algorithm SHA256).Hash) {throw 'Native/standalone ADC sample trace mismatch.'}
        }
        $projectResult=[pscustomobject]@{verdict='PASS';report=$nativeDir;simulation_top='tb_ad9226';trace_files_identical=18}
    }
    foreach($record in $sourceHashes){if((Get-FileHash -LiteralPath $record.Path -Algorithm SHA256).Hash -ne $record.Hash){throw 'ADC source changed during regression.'}}
    $verdict='PASS'
} catch {$failure=$_.Exception.Message;throw}
finally {
    Pop-Location
    $commands | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $reportDir 'commands.json') -Encoding utf8
    [pscustomobject]@{verdict=$verdict;backend=$version;python=$PythonExe;seeds=$Seeds;random_samples=$RandomSamples
        results=@($results.ToArray());replay=$replay;project=$projectResult;source_sha256=$sourceHashes
        temporary_build=$buildDir;data_paths=@(foreach($seedKey in $staging.Keys){
            [pscustomobject]@{seed=$seedKey;paths=$staging[$seedKey]}
        });failure=$failure
    } | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $reportDir 'manifest.json') -Encoding utf8
    Write-Output "AD9226_REGRESSION_$verdict reports=$reportDir"
}
