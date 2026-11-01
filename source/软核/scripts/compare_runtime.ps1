$ErrorActionPreference='Stop'
$cpu=Split-Path $PSScriptRoot -Parent
$project=Split-Path $cpu -Parent
$panel=Join-Path $project 'VGA显示部分/板端独立版'
$base=Join-Path $cpu 'reports/version_sync_20261030/baseline'
New-Item -ItemType Directory -Path $base -Force | Out-Null
$header=Get-Content -LiteralPath (Join-Path $cpu 'firmware/scope_cpu.h') -Raw
$header=$header -replace '(?s)/\* Current integrated panel MMIO extension.*?PANEL_FRAME=44, PANEL_VPP=48, PANEL_HZ=52 };',''
Set-Content -LiteralPath (Join-Path $base 'scope_cpu.h') -Value $header -Encoding utf8
$source=Get-Content -LiteralPath (Join-Path $panel 'panel_main.c') -Raw
$source=$source.Replace('#include "scope_cpu.h"',"#include `"scope_cpu.h`"`nenum { PANEL_INPUT=28, PANEL_STATUS=32, PANEL_CONTROL=36, PANEL_MS=40,`n PANEL_FRAME=44, PANEL_VPP=48, PANEL_HZ=52 };")
Set-Content -LiteralPath (Join-Path $base 'panel_main.c') -Value $source -Encoding utf8
$tool='D:/AMD/Xilinx/vivado_2025.2/2025.2/gnu/microblaze/nt/bin'
subst L: $panel;subst M: $cpu;subst N: $base
try {
 Set-Location L:/
 & "$tool/mb-gcc.exe" -Os -Wall -Wextra -Werror -ffreestanding -fno-builtin -G0 -mlittle-endian -mxl-soft-mul -mxl-soft-div -nostdlib '-Wl,-T,M:/firmware/link.ld' '-IN:/' '-IM:/firmware' M:/firmware/start.S N:/panel_main.c M:/firmware/scope_cpu.c M:/firmware/memory.c -o N:/previous_layout.elf
 if($LASTEXITCODE -ne 0){throw 'Baseline compile failed'}
 & "$tool/mb-objcopy.exe" -O binary N:/previous_layout.elf N:/before.bin
 if($LASTEXITCODE -ne 0){throw 'Baseline binary export failed'}
 & "$tool/mb-objcopy.exe" -O binary L:/output/panel.elf N:/after.bin
 if($LASTEXITCODE -ne 0){throw 'Current binary export failed'}
 $before=(Get-FileHash N:/before.bin).Hash;$after=(Get-FileHash N:/after.bin).Hash
 if($before -ne $after){throw 'Runtime load image changed'}
 @{result='PASS';load_image_sha256=$after;runtime_bytes_unchanged=$true} | ConvertTo-Json | Set-Content N:/comparison.json -Encoding utf8
 Write-Output "RUNTIME_LOAD_IMAGE_UNCHANGED $after"
} finally {Set-Location $project;subst L: /d;subst M: /d;subst N: /d}
