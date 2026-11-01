[CmdletBinding()]
param([string]$VivadoBin, [switch]$RegenerateClockIp)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'vivado_toolchain.ps1')
$VivadoBin = Resolve-ScopeVivadoBin -RequestedBin $VivadoBin
$fpgaRoot = Split-Path -Parent $PSScriptRoot
$runId = (Get-Date -Format 'yyyyMMdd_HHmmss') + '_' + [guid]::NewGuid().ToString('N').Substring(0,8)
$reportDir = Join-Path $fpgaRoot "reports/safe_project/$runId"
New-Item -ItemType Directory -Path $reportDir | Out-Null
$verdict = 'FAIL'
$failure = $null
$sourceHashes = @()
$pulseChecks = $null
Push-Location -LiteralPath $reportDir
try {
    $clockIpSource = Join-Path $fpgaRoot 'ip/scope_clk_wiz/scope_clk_wiz.v'
    if ($RegenerateClockIp -or -not (Test-Path -LiteralPath $clockIpSource)) {
        $ipBuildDir = Join-Path ([IO.Path]::GetTempPath()) "scope_clock_ip_$runId"
        New-Item -ItemType Directory -Path $ipBuildDir | Out-Null
        # Stage the existing customization too, so upgrade_ip preserves its settings.
        $existingIp = Join-Path $fpgaRoot 'ip/scope_clk_wiz'
        if (Test-Path -LiteralPath (Join-Path $existingIp 'scope_clk_wiz.xci')) {
            New-Item -ItemType Directory -Path (Join-Path $ipBuildDir 'ip') | Out-Null
            Copy-Item -LiteralPath $existingIp -Destination (Join-Path $ipBuildDir 'ip') -Recurse
        }
        $generationArgs = @('-mode','batch','-notrace','-source',(Join-Path $PSScriptRoot 'generate_scope_clock_ip.tcl'),
            '-log',(Join-Path $ipBuildDir 'vivado.log'),'-journal',(Join-Path $ipBuildDir 'vivado.jou'),
            '-tclargs',$ipBuildDir)
        Push-Location -LiteralPath $ipBuildDir
        try {
            $generationLines = @(& (Join-Path $VivadoBin 'vivado.bat') @generationArgs 2>&1)
            $generationExitCode = $LASTEXITCODE
        } finally { Pop-Location }
        $generationText = $generationLines -join [Environment]::NewLine
        $generationText | Set-Content -LiteralPath (Join-Path $reportDir 'clock_ip_generation.console.log') -Encoding utf8
        Copy-Item -LiteralPath (Join-Path $ipBuildDir 'vivado.log') -Destination (Join-Path $reportDir 'clock_ip_generation.vivado.log')
        if ($generationExitCode -ne 0 -or $generationText -notmatch 'CLOCK_IP_GENERATION_PASS' -or
            $generationText -match '(?im)^\s*(ERROR:|CRITICAL WARNING:|CLOCK_IP_GENERATION_FAIL)') {
            throw 'Clocking Wizard generation failed; see clock_ip_generation.console.log'
        }
        foreach ($status in @('ip_status_before_upgrade.txt','ip_status_after_upgrade.txt')) {
            Copy-Item -LiteralPath (Join-Path $ipBuildDir "ip/$status") -Destination $reportDir
        }
        $upgradeLog = Join-Path $ipBuildDir 'ip_upgrade.log'
        if (Test-Path -LiteralPath $upgradeLog) { Copy-Item -LiteralPath $upgradeLog -Destination $reportDir }
        Copy-Item -LiteralPath (Join-Path $ipBuildDir 'ip/scope_clk_wiz') -Destination (Join-Path $fpgaRoot 'ip') -Recurse -Force
        "ASCII staging: $ipBuildDir; products copied to FPGA/ip/scope_clk_wiz" |
            Set-Content -LiteralPath (Join-Path $reportDir 'clock_ip_staging.txt') -Encoding utf8
    }
    $sourceFiles = @(Get-ChildItem -LiteralPath (Join-Path $fpgaRoot 'rtl'),(Join-Path $fpgaRoot 'sim') -Recurse -File |
        Where-Object { $_.Extension -in @('.sv','.v') } | Select-Object -ExpandProperty FullName)
    $sourceFiles += @((Join-Path $fpgaRoot 'ip/scope_clk_wiz/scope_clk_wiz.v'),
                      (Join-Path $fpgaRoot 'ip/scope_clk_wiz/scope_clk_wiz_clk_wiz.v'))
    $sourceHashes = @($sourceFiles | Get-FileHash -Algorithm SHA256 | Select-Object Path,Hash)
    $arguments = @('-mode','batch','-notrace','-source',(Join-Path $PSScriptRoot 'check_safe_project.tcl'),
        '-log',(Join-Path $reportDir 'vivado.log'),'-journal',(Join-Path $reportDir 'vivado.jou'),
        '-tclargs',$reportDir)
    $lines = @(& (Join-Path $VivadoBin 'vivado.bat') @arguments 2>&1)
    $exitCode = $LASTEXITCODE
    $transcript = $lines -join [Environment]::NewLine
    $transcript | Set-Content -LiteralPath (Join-Path $reportDir 'console.log') -Encoding utf8
    if ($exitCode -ne 0 -or $transcript -match '(?im)^\s*(ERROR:|CRITICAL WARNING:|Fatal:|SAFE_PROJECT_FAIL|TEST_FAIL)') {
        throw "Project check failed (exit $exitCode); see $reportDir/console.log"
    }
    if ($transcript -notmatch 'SAFE_PROJECT_PASS' -or $transcript -notmatch 'WRAPPER_SIM_PASS') {
        throw 'Missing project/wrapper terminal PASS'
    }
    foreach ($testStage in @('core','wrapper')) {
        foreach ($logName in @('xvlog.log','elaborate.log','simulate.log')) {
            $text = Get-Content -LiteralPath (Join-Path $reportDir "$testStage/$logName") -Raw
            if ($text -match '(?im)^\s*(WARNING:|ERROR:|Fatal:|TEST_FAIL)') { throw "HDL diagnostic in $testStage/$logName" }
        }
    }
    $coreText = Get-Content -LiteralPath (Join-Path $reportDir 'core/simulate.log') -Raw
    if ([regex]::Matches($coreText,'(?m)^SCENARIO_COVERAGE rate=\d+ transitions=18/18 faults=20/20 cancels=5/5 restarts=5/5 reenable=4/4 boundaries=4/4 pulses=5/5').Count -ne 4) {
        throw 'Project-mode core regression did not complete the directed coverage matrix.'
    }
    $wrapperText = Get-Content -LiteralPath (Join-Path $reportDir 'wrapper/simulate.log') -Raw
    $pulseMatch = [regex]::Match($wrapperText,'(?m)^CLOCK_PULSE_PASS rate=25000000 half_period_ns=20 checks=(\d+)')
    if (-not $pulseMatch.Success) { throw 'Missing real ODDR pulse-width checks.' }
    $pulseChecks = [int]$pulseMatch.Groups[1].Value
    foreach ($record in $sourceHashes) {
        if ((Get-FileHash -LiteralPath $record.Path -Algorithm SHA256).Hash -ne $record.Hash) {
            throw "Source changed during project regression: $($record.Path)"
        }
    }
    $verdict = 'PASS'
} catch { $failure=$_.Exception.Message; throw }
finally {
    Pop-Location
    [pscustomobject]@{ verdict=$verdict; part='xc7a35tcsg324-1'; part_is_temporary=$true
        top='scope_hw_top'; simulation_top='tb_safe'; hardware_clock_hz=25000000
        failure=$failure; vivado_bin=$VivadoBin; source_sha256=$sourceHashes; pulse_width_checks=$pulseChecks
    } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $reportDir 'manifest.json') -Encoding utf8
    Write-Output "SAFE_PROJECT_$verdict reports=$reportDir"
}
