param([ValidateSet('ui','verify','test')][string]$Action='ui',[Parameter(ValueFromRemainingArguments=$true)][string[]]$ScopeArgs)
$ErrorActionPreference='Stop'
$scopePython='python'
foreach($candidate in @((Join-Path $PSScriptRoot '.venv/Scripts/python.exe'),(Join-Path $PSScriptRoot '../../.venv-ui/Scripts/python.exe'))){
 if(Test-Path -LiteralPath $candidate){$scopePython=(Resolve-Path -LiteralPath $candidate).Path;break}
}
switch($Action){
 'ui' { & $scopePython "$PSScriptRoot/src/pc/ui/launch_scope.py" @ScopeArgs }
 'verify' { & $scopePython "$PSScriptRoot/sim/verify_submission.py" }
 'test' { & $scopePython "$PSScriptRoot/sim/run_tests.py" }
}
exit $LASTEXITCODE
