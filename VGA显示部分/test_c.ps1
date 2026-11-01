$ErrorActionPreference='Stop'
$cpu=Join-Path (Split-Path $PSScriptRoot -Parent) '软核/firmware'
Push-Location $PSScriptRoot
try {
 New-Item -ItemType Directory -Force output | Out-Null
 $msvc='D:/Visual Studio/Visual Studio 2026/Community/VC/Tools/MSVC/14.51.36231'
 $sdk='D:/Windows Kits/10'
 $env:INCLUDE="$msvc/include;$sdk/Include/10.0.26100.0/ucrt;$sdk/Include/10.0.26100.0/shared;$sdk/Include/10.0.26100.0/um"
 $env:LIB="$msvc/lib/x64;$sdk/Lib/10.0.26100.0/ucrt/x64;$sdk/Lib/10.0.26100.0/um/x64"
 & "$msvc/bin/Hostx64/x64/cl.exe" /nologo /std:c11 /utf-8 /O2 /W3 /WX /MT "-I$cpu" test_panel.c panel_model.c "$cpu/scope_cpu.c" /Fooutput/ /Feoutput/test_panel.exe
 if($LASTEXITCODE -ne 0){throw 'C test compile failed'}
 & ./output/test_panel.exe | Tee-Object output/c_tests.log
 if($LASTEXITCODE -ne 0){throw 'C test failed'}
} finally {Pop-Location}
