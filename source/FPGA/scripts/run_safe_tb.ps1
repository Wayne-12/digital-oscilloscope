[CmdletBinding()]
param(
    [string]$VivadoBin,
    [ValidateRange(0, 2147483647)][int[]]$Seeds = @(20261020, 42),
    [switch]$SkipReplay
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'vivado_toolchain.ps1')
$VivadoBin = Resolve-ScopeVivadoBin -RequestedBin $VivadoBin
foreach ($tool in @('xvlog', 'xelab', 'xsim')) {
    if (-not (Test-Path -LiteralPath (Join-Path $VivadoBin "$tool.bat"))) { throw "Missing $tool.bat" }
}
if ($Seeds.Count -eq 0 -or @($Seeds | Select-Object -Unique).Count -ne $Seeds.Count) {
    throw 'Supply at least one seed, with no duplicates.'
}
$fpgaRoot = Split-Path -Parent $PSScriptRoot
$runId = (Get-Date -Format 'yyyyMMdd_HHmmss') + '_' + [guid]::NewGuid().ToString('N').Substring(0, 8)
$reportDir = Join-Path $fpgaRoot "reports/safe/$runId"
$buildDir = Join-Path ([IO.Path]::GetTempPath()) "scope_safe_$runId"
New-Item -ItemType Directory -Path $reportDir, $buildDir | Out-Null
$relativeSources = @(
    'rtl/common/scope_pkg.sv',
    'rtl/clock_reset/scope_reset_sync.sv',
    'rtl/clock_reset/scope_enable_sync.sv',
    'rtl/clock_reset/scope_safe_ctrl.sv',
    'rtl/top/scope_core.sv',
    'sim/models/ideal_clock.sv',
    'sim/models/scope_pin_model.sv',
    'sim/tb/safe_scenario.sv',
    'sim/tb/tb_safe.sv'
)
$sourceFiles = @($relativeSources | ForEach-Object { Join-Path $fpgaRoot $_ })
$sourceHashes = @($sourceFiles | Get-FileHash -Algorithm SHA256 | Select-Object Path,Hash)
foreach ($sourceFile in $sourceFiles) { Copy-Item -LiteralPath $sourceFile -Destination $buildDir }
$commands = [System.Collections.Generic.List[object]]::new()
$results = [System.Collections.Generic.List[object]]::new()
$verdict = 'FAIL'
$failure = $null
$version = $null
$firstEvidence = $null
$replayResult = $null

function Get-SafeEvidence {
    param([string]$Transcript)
    return (([regex]::Matches($Transcript,
        '(?m)^(AGENT_PASS|SCENARIO_COVERAGE|STATE_COVERAGE|TRANSITION_COVERAGE|TEST_CASE_PASS|TEST_PASS) [^\r\n]+') |
        ForEach-Object Value | Sort-Object) -join "`n")
}

function Invoke-SafeStage {
    param([string]$Tool, [string[]]$ToolArgs, [string]$Label)
    $toolPath = Join-Path $VivadoBin "$Tool.bat"
    $commands.Add([pscustomobject]@{ tool=$toolPath; arguments=$ToolArgs })
    $lines = @(& $toolPath @ToolArgs 2>&1)
    $code = $LASTEXITCODE
    $transcript = $lines -join [Environment]::NewLine
    $transcript | Set-Content -LiteralPath (Join-Path $reportDir "$Label.console.log") -Encoding utf8
    if ($code -ne 0 -or $transcript -match '(?im)^\s*(ERROR:|WARNING:|Fatal:|TEST_FAIL|FATAL_ERROR:|application-specific initialization failed:)') {
        throw "$Label failed (exit $code); see $reportDir/$Label.console.log"
    }
    return $transcript
}

Push-Location -LiteralPath $buildDir
try {
    $version = Invoke-SafeStage -Tool xsim -ToolArgs @('--version') -Label version
    $compileArgs = @('--sv') + @($sourceFiles | ForEach-Object { Split-Path -Leaf $_ })
    $null = Invoke-SafeStage -Tool xvlog -ToolArgs $compileArgs -Label compile
    $null = Invoke-SafeStage -Tool xelab -ToolArgs @('work.tb_safe','--snapshot','safe_tb','--timescale','1ns/1ps') -Label elaborate
    foreach ($seed in $Seeds) {
        $label = "seed_$seed"
        $runArgs = @('safe_tb','--runall','--onfinish','quit','--onerror','quit',
            '--sv_seed',"$seed",'--testplusarg',('"SEED={0}"' -f $seed),'--log',"$label.log")
        $transcript = Invoke-SafeStage -Tool xsim -ToolArgs $runArgs -Label $label
        $terminal = [regex]::Match($transcript,'(?m)^TEST_PASS tb_safe [^\r\n]+')
        $agents = @([regex]::Matches($transcript,'(?m)^AGENT_PASS rate=(\d+) states=10/10 startups=(\d+) checks=(\d+) seed=(\d+)'))
        if (-not $terminal.Success -or $agents.Count -ne 4) { throw 'Incomplete terminal PASS/agent coverage.' }
        $agentResults = @($agents | ForEach-Object { [pscustomobject]@{
            rate_hz=[int]$_.Groups[1].Value; states_visited=10; startups=[int]$_.Groups[2].Value
            checks=[int]$_.Groups[3].Value; effective_seed=[int]$_.Groups[4].Value
        } })
        if (@($agentResults.rate_hz | Sort-Object) -join ',' -ne '10000000,25000000,50000000,65000000') {
            throw 'Missing clock-rate coverage.'
        }
        $coverage = @([regex]::Matches($transcript,
            '(?m)^SCENARIO_COVERAGE rate=(\d+) transitions=18/18 faults=20/20 cancels=5/5 restarts=5/5 reenable=4/4 boundaries=4/4 pulses=5/5 signature=([0-9a-fA-F]{8})'))
        if ($coverage.Count -ne 4) { throw 'Incomplete scenario/transition coverage.' }
        foreach ($agent in $agentResults) {
            if ($agent.effective_seed -ne ($seed -bxor $agent.rate_hz)) {
                throw "Selected seed did not reach the $($agent.rate_hz) Hz agent."
            }
            $rateCoverage = @($coverage | Where-Object { [int]$_.Groups[1].Value -eq $agent.rate_hz })
            if ($rateCoverage.Count -ne 1) { throw 'Duplicate or missing coverage rate.' }
            $agent | Add-Member -NotePropertyName coverage -NotePropertyValue ([pscustomobject]@{
                transitions=18; faults=20; cancellations=5; restarts=5; shutdown_reenables=4
                boundary_aborts=4; short_low_pulses=5; random_signature=$rateCoverage[0].Groups[2].Value
            })
        }
        if ($seed -eq $Seeds[0]) { $firstEvidence = Get-SafeEvidence -Transcript $transcript }
        $result = [pscustomobject]@{ seed=$seed; verdict='PASS'; agents=$agentResults; terminal=$terminal.Value }
        $results.Add($result)
        [pscustomobject]@{ top='tb_safe'; backend=$version.Trim(); source_sha256=$sourceHashes
            seed=$seed; plusargs=@("SEED=$seed"); watchdog='5ms'; result=$result
        } | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath (Join-Path $reportDir "$label.manifest.json") -Encoding utf8
        Write-Output "$($terminal.Value) seed=$seed"
    }
    if (-not $SkipReplay) {
        $replaySeed = $Seeds[0]
        $replayLabel = "seed_${replaySeed}_replay"
        $replayArgs = @('safe_tb','--runall','--onfinish','quit','--onerror','quit',
            '--sv_seed',"$replaySeed",'--testplusarg',('"SEED={0}"' -f $replaySeed),'--log',"$replayLabel.log")
        $replayTranscript = Invoke-SafeStage -Tool xsim -ToolArgs $replayArgs -Label $replayLabel
        if ((Get-SafeEvidence -Transcript $replayTranscript) -cne $firstEvidence) {
            throw 'Fixed-seed replay changed the random choices, coverage, checks, or terminal result.'
        }
        $firstEvidence | Set-Content -LiteralPath (Join-Path $reportDir 'replayed_evidence.txt') -Encoding utf8
        $replayResult = [pscustomobject]@{seed=$replaySeed;verdict='PASS';evidence='replayed_evidence.txt'}
        $replayResult | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $reportDir "$replayLabel.manifest.json") -Encoding utf8
        Write-Output "SEED_REPLAY_PASS seed=$replaySeed signatures_and_coverage=identical"
    }
    $verdict = 'PASS'
} catch { $failure=$_.Exception.Message; throw }
finally {
    Pop-Location
    Get-ChildItem -LiteralPath $buildDir -File | Where-Object { $_.Extension -in @('.log','.jou','.pb') } |
        Copy-Item -Destination $reportDir
    $commands | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $reportDir 'commands.json') -Encoding utf8
    [pscustomobject]@{ verdict=$verdict; backend=$version; top='tb_safe'; results=@($results.ToArray())
        source_sha256=$sourceHashes; temporary_build=$buildDir; failure=$failure; replay=$replayResult
    } | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $reportDir 'manifest.json') -Encoding utf8
    Write-Output "SAFE_REGRESSION_$verdict reports=$reportDir"
}
