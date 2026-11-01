$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$tool = 'D:\AMD\Xilinx\vivado_2025.2\2025.2\gnu\microblaze\nt\bin'
if ($env:SCOPE_MB_BIN) { $tool = $env:SCOPE_MB_BIN }
$out = Join-Path $root 'build'
New-Item -ItemType Directory -Force -Path $out | Out-Null
$sources = @('start.S','main.c','scope_cpu.c','memory.c') | ForEach-Object { Join-Path $root "firmware\$_" }
& "$tool\mb-gcc.exe" -Os -Wall -Wextra -Werror -ffreestanding -fno-builtin -G0 -mlittle-endian -mxl-soft-mul -mxl-soft-div -nostdlib "-Wl,-T,$root\firmware\link.ld" "-Wl,-Map,$out\scope_cpu.map" @sources -o "$out\scope_cpu.elf"
if ($LASTEXITCODE -ne 0) { throw 'MicroBlaze firmware build failed' }
& "$tool\mb-size.exe" "$out\scope_cpu.elf"
if ($LASTEXITCODE -ne 0) { throw 'ELF size check failed' }
& "$tool\mb-objdump.exe" -d "$out\scope_cpu.elf" | Set-Content -LiteralPath "$out\scope_cpu.disasm"
Write-Output "OFFLINE_ELF_READY $out\scope_cpu.elf"
