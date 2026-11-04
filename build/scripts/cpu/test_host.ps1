$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
New-Item -ItemType Directory -Force -Path "$root\build" | Out-Null
$msvc='D:\Visual Studio\Visual Studio 2026\Community\VC\Tools\MSVC\14.51.36231'
$sdk='D:\Windows Kits\10'
$env:INCLUDE="$msvc\include;$sdk\Include\10.0.26100.0\ucrt;$sdk\Include\10.0.26100.0\shared;$sdk\Include\10.0.26100.0\um"
$env:LIB="$msvc\lib\x64;$sdk\Lib\10.0.26100.0\ucrt\x64;$sdk\Lib\10.0.26100.0\um\x64"
& "$msvc\bin\Hostx64\x64\cl.exe" /nologo /std:c11 /O2 /W4 /WX /MT "-I$root\firmware" "$root\firmware\scope_cpu.c" "$root\tests\test_scope_cpu.c" "/Fo$root\build\\" "/Fe$root\build\test_scope_cpu.exe"
if ($LASTEXITCODE -ne 0) { throw 'Host C compilation failed' }
& "$root\build\test_scope_cpu.exe" | Tee-Object -FilePath "$root\reports\host_test.txt"
if ($LASTEXITCODE -ne 0) { throw 'Host C tests failed' }
