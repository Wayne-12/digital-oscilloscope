[CmdletBinding()]
param(
    [string]$VivadoBin,
    [uint32[]]$Seeds = @(20261020),
    [ValidateRange(0, 10000)][int]$RandomCases = 1000
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

. (Join-Path $PSScriptRoot 'vivado_toolchain.ps1')
$VivadoBin = Resolve-ScopeVivadoBin -RequestedBin $VivadoBin
foreach ($toolName in @('xvlog', 'xelab', 'xsim')) {
    if (-not (Test-Path -LiteralPath (Join-Path $VivadoBin "$toolName.bat"))) {
        throw "Missing $toolName.bat in $VivadoBin"
    }
}
if ($Seeds.Count -eq 0 -or @($Seeds | Select-Object -Unique).Count -ne $Seeds.Count) {
    throw 'Supply at least one seed, with no duplicates.'
}

$fpgaRoot = Split-Path -Parent $PSScriptRoot
$runId = (Get-Date -Format 'yyyyMMdd_HHmmss') + '_' + [guid]::NewGuid().ToString('N').Substring(0, 8)
$reportDir = Join-Path $fpgaRoot "reports/scope_pkg/$runId"
# Stage compiler inputs in a unique TEMP directory; keep authored files in FPGA/.
$buildDir = Join-Path ([IO.Path]::GetTempPath()) "scope_pkg_$runId"
New-Item -ItemType Directory -Path $reportDir, $buildDir | Out-Null
$sourceFiles = @(
    (Join-Path $fpgaRoot 'rtl/common/scope_pkg.sv'),
    (Join-Path $fpgaRoot 'rtl/common/sample_stream_if.sv'),
    (Join-Path $fpgaRoot 'sim/models/scope_pkg_import_probe.sv'),
    (Join-Path $fpgaRoot 'sim/tb/tb_scope_pkg.sv')
)
$sourceHashes = @($sourceFiles | Get-FileHash -Algorithm SHA256 | Select-Object Path, Hash)
foreach ($sourceFile in $sourceFiles) {
    Copy-Item -LiteralPath $sourceFile -Destination $buildDir
}
$results = [System.Collections.Generic.List[object]]::new()
$commandLog = [System.Collections.Generic.List[object]]::new()
$verdict = 'FAIL'
$failureText = $null
$version = $null

function Invoke-XSimStage {
    param([string]$Tool, [string[]]$ToolArgs, [string]$Label)
    $exePath = Join-Path $VivadoBin "$Tool.bat"
    $commandLog.Add([pscustomobject]@{ tool = $exePath; arguments = $ToolArgs })
    $outputLines = @(& $exePath @ToolArgs 2>&1)
    $toolExitCode = $LASTEXITCODE
    $outputText = $outputLines -join [Environment]::NewLine
    $outputText | Set-Content -LiteralPath (Join-Path $reportDir "$Label.console.log") -Encoding utf8
    if ($toolExitCode -ne 0 -or $outputText -match '(?im)^\s*(ERROR:|WARNING:|FATAL_ERROR:|Fatal:|TEST_FAIL\b|application-specific initialization failed:)') {
        throw "$Label failed (exit $toolExitCode). See $reportDir/$Label.console.log"
    }
    return $outputText
}

Push-Location -LiteralPath $buildDir
try {
    $version = Invoke-XSimStage -Tool 'xsim' -ToolArgs @('--version') -Label 'version'
    $null = Invoke-XSimStage -Tool 'xvlog' -ToolArgs @('--sv', 'scope_pkg.sv', 'sample_stream_if.sv', 'scope_pkg_import_probe.sv', 'tb_scope_pkg.sv') -Label 'compile'
    $null = Invoke-XSimStage -Tool 'xelab' -ToolArgs @('work.tb_scope_pkg', '--snapshot', 'scope_pkg_tb', '--timescale', '1ns/1ps') -Label 'elaborate'
    foreach ($seed in $Seeds) {
        $label = "seed_$seed"
        # Preserve quotes through the vendor's Windows .bat argument forwarding.
        $testArgs = @('scope_pkg_tb', '--runall', '--onerror', 'quit', '--onfinish', 'quit',
                      '--sv_seed', "$seed", '--testplusarg', ('"SEED={0}"' -f $seed),
                      '--testplusarg', ('"RANDOM_CASES={0}"' -f $RandomCases), '--log', "$label.log")
        $transcript = Invoke-XSimStage -Tool 'xsim' -ToolArgs $testArgs -Label $label
        $passMatch = [regex]::Match($transcript,
            "(?m)^TEST_PASS tb_scope_pkg seed=$seed transactions=(\d+) checks=(\d+)\s*$")
        if (-not $passMatch.Success -or
            [int]$passMatch.Groups[1].Value -ne (8192 + $RandomCases)) {
            throw "Missing or incomplete terminal PASS for seed $seed."
        }
        $result = [pscustomobject]@{
            seed = $seed; random_cases = $RandomCases; verdict = 'PASS'
            transactions = [int]$passMatch.Groups[1].Value
            immediate_assertions = [int]$passMatch.Groups[2].Value
        }
        $results.Add($result)
        [pscustomobject]@{
            top = 'tb_scope_pkg'; backend = 'XSim'; simulator_version = $version.Trim()
            mode = 'behavioral'; source_sha256 = $sourceHashes
            seed = $seed; plusargs = @("SEED=$seed", "RANDOM_CASES=$RandomCases")
            watchdog = '100us'; result = $result
            transcript = "$label.console.log"
        } | ConvertTo-Json -Depth 6 |
            Set-Content -LiteralPath (Join-Path $reportDir "$label.manifest.json") -Encoding utf8
        Write-Output $passMatch.Value.Trim()
    }
    $verdict = 'PASS'
} catch {
    $failureText = $_.Exception.Message
    throw
} finally {
    Pop-Location
    Get-ChildItem -LiteralPath $buildDir -File |
        Where-Object { $_.Extension -in @('.log', '.jou', '.pb') } |
        Copy-Item -Destination $reportDir
    $commandLog | ConvertTo-Json -Depth 5 |
        Set-Content -LiteralPath (Join-Path $reportDir 'commands.json') -Encoding utf8
    [pscustomobject]@{
        top = 'tb_scope_pkg'; backend = 'XSim'; mode = 'behavioral'; verdict = $verdict
        simulator_version = $version
        timeunit = '1ns'; timeprecision = '1ps'; watchdog = '100us'
        source_sha256 = $sourceHashes; seeds = $Seeds; random_cases = $RandomCases
        results = @($results.ToArray()); failure = $failureText; temporary_build = $buildDir
    } | ConvertTo-Json -Depth 6 |
        Set-Content -LiteralPath (Join-Path $reportDir 'manifest.json') -Encoding utf8
    Write-Output "REGRESSION_$verdict reports=$reportDir"
}
