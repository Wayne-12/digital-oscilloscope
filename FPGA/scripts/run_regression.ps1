[CmdletBinding()]
param(
    [int[]]$Seeds = @(20261020,42),
    [switch]$SystemOnly,
    [switch]$UnitsOnly,
    [string[]]$Tests = @(),
    [string]$PythonExe
)
$ErrorActionPreference='Stop'
$workspaceRoot=Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if(!$PythonExe){$PythonExe=Join-Path $workspaceRoot '.venv-ui/Scripts/python.exe'}
if(!(Test-Path -LiteralPath $PythonExe -PathType Leaf)){throw "Missing project Python: $PythonExe"}
if($SystemOnly -and $UnitsOnly){throw 'Select only one layer restriction.'}
if($Tests.Count -and !$UnitsOnly){throw '-Tests requires -UnitsOnly.'}
$names=@('SCOPE_SIM_ROOT','SCOPE_SIM_PROJECT_ROOT','SCOPE_NATIVE_PROJECT_DIR','TEMP','TMP','APPDATA')
$previous=@{};foreach($name in $names){$previous[$name]=[Environment]::GetEnvironmentVariable($name,'Process')}
$createdDrive=$null
try {
    $existing=@(& subst)
    $selectedDrive=$null
    foreach($line in $existing){
        if($line -match '^([A-Z]):\\: => (.+)$' -and
           [IO.Path]::GetFullPath($Matches[2]).TrimEnd('\') -eq [IO.Path]::GetFullPath($workspaceRoot).TrimEnd('\')){
            $selectedDrive=$Matches[1]+':'
            break
        }
    }
    if(!$selectedDrive){
        foreach($letter in 'Z','Y','X','W','V','U','T'){
            $candidate=$letter+':'
            if(Get-PSDrive -Name $letter -ErrorAction SilentlyContinue){continue}
            if(Test-Path -LiteralPath ($candidate+'/')){continue}
            & subst $candidate $workspaceRoot
            if($LASTEXITCODE -eq 0 -and (Test-Path -LiteralPath ($candidate+'/'))){
                $selectedDrive=$candidate;$createdDrive=$candidate;break
            }
        }
    }
    if(!$selectedDrive){throw 'Could not create an ASCII workspace alias; inspect subst permissions and available drive letters.'}
    $env:SCOPE_SIM_PROJECT_ROOT=$selectedDrive+'/'
    $env:SCOPE_SIM_ROOT=$selectedDrive+'/tmp/fpga_ascii'
    $env:SCOPE_NATIVE_PROJECT_DIR=$env:SCOPE_SIM_ROOT+'/native_'+$PID+'_'+[guid]::NewGuid().ToString('N').Substring(0,8)+'/scope_smoke'
    $env:TEMP=$env:SCOPE_SIM_ROOT+'/compiler_tmp';$env:TMP=$env:TEMP
    $env:APPDATA=$env:SCOPE_SIM_ROOT+'/tool_appdata'
    New-Item -ItemType Directory -Force -Path $env:TEMP,$env:APPDATA | Out-Null
    $runner=if($UnitsOnly){'run_unit_regression.py'}else{'run_system_regression.py'}
    $arguments=@((Join-Path $PSScriptRoot $runner),'--seeds')+@($Seeds|ForEach-Object{[string]$_})
    if($SystemOnly){$arguments+='--system-only'}
    if($Tests.Count){$arguments+=@('--tests')+$Tests}
    & $PythonExe @arguments
    $runExit=$LASTEXITCODE
} finally {
    foreach($name in $names){[Environment]::SetEnvironmentVariable($name,$previous[$name],'Process')}
    if($createdDrive){& subst $createdDrive /D}
}
exit $runExit
