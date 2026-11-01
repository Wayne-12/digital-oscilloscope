[CmdletBinding()]
param(
    [string]$VivadoBin,
    [ValidateRange(0, 2147483647)][int]$Seed = 20261020,
    [ValidateRange(0, 4096)][int]$RandomCycles = 128
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'vivado_toolchain.ps1')
$VivadoBin = Resolve-ScopeVivadoBin -RequestedBin $VivadoBin
$vivadoExe = Join-Path $VivadoBin 'vivado.bat'
if (-not (Test-Path -LiteralPath $vivadoExe)) { throw "Missing $vivadoExe" }
$fpgaRoot = Split-Path -Parent $PSScriptRoot
$projectDir = Resolve-ScopeProjectDir -FpgaRoot $fpgaRoot
$simulationDir = Join-Path $projectDir 'scope_smoke.sim'
$runId = (Get-Date -Format 'yyyyMMdd_HHmmss') + '_' + [guid]::NewGuid().ToString('N').Substring(0, 8)
$reportDir = Join-Path $fpgaRoot "reports/smoke/$runId"
New-Item -ItemType Directory -Path $reportDir | Out-Null
$results = [System.Collections.Generic.List[object]]::new()
$sourceHashes = @(Get-ChildItem -LiteralPath (Join-Path $fpgaRoot 'rtl'), (Join-Path $fpgaRoot 'sim') -File -Recurse |
    Where-Object { $_.Extension -in @('.sv', '.v') } |
    Get-FileHash -Algorithm SHA256 | Select-Object Path, Hash)
$verdict = 'FAIL'
$failure = $null

function Invoke-SmokePass {
    param([string]$Label)
    $stageDir = Join-Path $reportDir $Label
    New-Item -ItemType Directory -Path $stageDir | Out-Null
    $toolArgs = @('-mode', 'batch', '-notrace', '-source', (Join-Path $PSScriptRoot 'run_smoke.tcl'),
        '-log', (Join-Path $stageDir 'vivado.log'), '-journal', (Join-Path $stageDir 'vivado.jou'),
        '-tclargs', $stageDir, "$Seed", "$RandomCycles")
    $toolArgs | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $stageDir 'arguments.json') -Encoding utf8
    Push-Location -LiteralPath $stageDir
    try {
        $outputLines = @(& $vivadoExe @toolArgs 2>&1)
        $toolExitCode = $LASTEXITCODE
    } finally { Pop-Location }
    $consoleText = $outputLines -join [Environment]::NewLine
    $consoleText | Set-Content -LiteralPath (Join-Path $stageDir 'console.log') -Encoding utf8
    if ($toolExitCode -ne 0 -or $consoleText -match '(?im)^\s*(ERROR:|Fatal:|STEP1_FAIL|TEST_FAIL)') {
        throw "$Label failed (exit $toolExitCode); see $stageDir/console.log"
    }
    foreach ($logName in @('xvlog.log', 'elaborate.log', 'simulate.log', 'project_audit.txt')) {
        if (-not (Test-Path -LiteralPath (Join-Path $stageDir $logName))) {
            throw "Missing fresh artifact $Label/$logName"
        }
    }
    foreach ($logName in @('xvlog.log', 'elaborate.log', 'simulate.log')) {
        $logText = Get-Content -LiteralPath (Join-Path $stageDir $logName) -Raw
        if ($logText -match '(?im)^\s*(WARNING:|ERROR:|Fatal:|TEST_FAIL)') {
            throw "Unexpected warning/error in $Label/$logName"
        }
    }
    $transcript = Get-Content -LiteralPath (Join-Path $stageDir 'simulate.log') -Raw
    $pass = [regex]::Match($transcript, '(?m)^TEST_PASS tb_smoke [^\r\n]+')
    if (-not $pass.Success -or $pass.Value -notmatch "seed=$Seed\b") {
        throw "$Label missing terminal PASS or selected seed"
    }
    $compileLog = Get-Content -LiteralPath (Join-Path $stageDir 'xvlog.log') -Raw
    if ($Label -eq 'clean_rebuild' -and
        ($compileLog -notmatch 'Analyzing SystemVerilog file' -or $compileLog -notmatch 'tb_smoke')) {
        throw "$Label did not show fresh source compilation"
    }
    $result = [pscustomobject]@{ stage = $Label; verdict = 'PASS'; terminal = $pass.Value; reports = $stageDir }
    $results.Add($result)
    Write-Output "$Label PASS: $($pass.Value)"
}

try {
    Invoke-SmokePass -Label 'initial'
    # Delete only Vivado's known generated .sim directory after the tool exits.
    # Resolve and validate every deletion target; never delete project/sources.
    $resolvedProject = (Resolve-Path -LiteralPath $projectDir).ProviderPath
    $resolvedSimulation = (Resolve-Path -LiteralPath $simulationDir).ProviderPath
    $expectedSimulation = Join-Path $resolvedProject 'scope_smoke.sim'
    if (-not $resolvedSimulation.Equals($expectedSimulation, [StringComparison]::OrdinalIgnoreCase) -or
        -not $resolvedSimulation.StartsWith($resolvedProject + [IO.Path]::DirectorySeparatorChar,
                                           [StringComparison]::OrdinalIgnoreCase)) {
        throw "Unsafe simulation cleanup target: $resolvedSimulation"
    }
    $simulationItem = Get-Item -LiteralPath $resolvedSimulation -Force
    $reparsePoints = @(Get-ChildItem -LiteralPath $resolvedSimulation -Recurse -Force |
        Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint })
    if (($simulationItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -or $reparsePoints.Count -ne 0) {
        throw 'Refusing recursive cleanup of a simulation directory containing reparse points.'
    }
    Remove-Item -LiteralPath $resolvedSimulation -Recurse -Force
    if (Test-Path -LiteralPath $resolvedSimulation) { throw 'Simulation directory was not removed.' }
    "Deleted generated simulation directory: $resolvedSimulation" |
        Set-Content -LiteralPath (Join-Path $reportDir 'clean_rebuild.txt') -Encoding utf8
    Invoke-SmokePass -Label 'clean_rebuild'
    if ($results[0].terminal -ne $results[1].terminal) {
        throw 'Fixed-seed results differ after clean rebuild.'
    }
    foreach ($sourceRecord in $sourceHashes) {
        if ((Get-FileHash -LiteralPath $sourceRecord.Path -Algorithm SHA256).Hash -ne $sourceRecord.Hash) {
            throw "Source changed during smoke regression: $($sourceRecord.Path)"
        }
    }
    $verdict = 'PASS'
} catch {
    $failure = $_.Exception.Message
    throw
} finally {
    [pscustomobject]@{
        verdict = $verdict; part = 'xc7a35tcsg324-1'; part_is_temporary = $true
        board_preset = $null; constraints = @(); simulator = 'XSim'; simulation_top = 'tb_smoke'
        design_top = 'smoke_counter'; seed = $Seed; random_cycles = $RandomCycles
        source_sha256 = $sourceHashes; results = @($results.ToArray())
        simulation_directory = $simulationDir; failure = $failure
    } | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $reportDir 'manifest.json') -Encoding utf8
    Write-Output "SMOKE_REGRESSION_$verdict reports=$reportDir"
}
