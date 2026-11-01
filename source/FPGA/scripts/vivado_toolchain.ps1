# Repository-local selection; no changes to the machine PATH or old installation.
function Resolve-ScopeProjectDir {
    param([string]$FpgaRoot)
    if ($env:SCOPE_NATIVE_PROJECT_DIR) {
        return [IO.Path]::GetFullPath($env:SCOPE_NATIVE_PROJECT_DIR)
    }
    return [IO.Path]::GetFullPath((Join-Path $FpgaRoot 'project/scope_smoke'))
}

function Resolve-ScopeVivadoBin {
    param([string]$RequestedBin)
    $selectedBin = $RequestedBin
    if ([string]::IsNullOrWhiteSpace($selectedBin)) {
        $configuration = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'vivado_toolchain.json') -Raw |
            ConvertFrom-Json
        $selectedBin = $configuration.bin
    }
    foreach ($name in @('vivado', 'xvlog', 'xelab', 'xsim')) {
        if (-not (Test-Path -LiteralPath (Join-Path $selectedBin "$name.bat") -PathType Leaf)) {
            throw "Missing $name.bat in $selectedBin; edit vivado_toolchain.json or supply -VivadoBin."
        }
    }
    return (Resolve-Path -LiteralPath $selectedBin).ProviderPath
}
