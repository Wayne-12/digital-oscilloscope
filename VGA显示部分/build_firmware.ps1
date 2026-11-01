$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$cpu=Join-Path $root '软核'
$tool='D:/AMD/Xilinx/vivado_2025.2/2025.2/gnu/microblaze/nt/bin'
$aliases=@('L:','M:','N:','O:','Q:') | Where-Object {-not (Test-Path "$_\")} | Select-Object -First 2
if($aliases.Count -ne 2){throw 'Two free aliases required'}
$savedLocation=Get-Location
try {
 subst $aliases[0] $PSScriptRoot
 subst $aliases[1] $cpu
 Set-Location "$($aliases[0])/"
 $c="$($aliases[1])/firmware"
 & "$tool/mb-gcc.exe" -Oz -flto -Wall -Wextra -Werror -ffreestanding -fno-builtin -ffunction-sections -fdata-sections -G0 -mlittle-endian -mxl-soft-mul -mxl-soft-div -nostdlib '-Wl,--gc-sections' "-Wl,-T,$c/link.ld" "-Wl,-Map,output/panel.map" "-I$c" "$c/start.S" panel_main.c panel_model.c "$c/scope_cpu.c" "$c/memory.c" -lgcc -o output/panel.elf
 if($LASTEXITCODE -ne 0){throw 'Panel C firmware compile failed'}
 & "$tool/mb-size.exe" output/panel.elf
} finally {Set-Location $savedLocation;foreach($a in $aliases){subst $a /d}}
