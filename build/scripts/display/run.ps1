param([ValidateSet('simulate','build','program','prepare_flash','program_flash','verify_flash_boot')][string]$Action='simulate')
$ErrorActionPreference='Stop'
$panelFolder=$PSScriptRoot
$cpuFolder=Join-Path (Split-Path $panelFolder -Parent) 'cpu'
$binary='D:/AMD/Xilinx/vivado_2025.2/2025.2/Vivado/bin'
if($env:SCOPE_VIVADO_BIN){$binary=$env:SCOPE_VIVADO_BIN}
if($Action -in @('program','prepare_flash','program_flash','verify_flash_boot')){
 & python "$panelFolder/verify_release.py"
 if($LASTEXITCODE -ne 0){throw 'Release verification failed'}
 if($Action -eq 'program_flash'){
  & python "$panelFolder/verify_flash_image.py"
  if($LASTEXITCODE -ne 0){throw 'Flash image verification failed'}
 }
 if($Action -ne 'prepare_flash' -and -not (Get-Process hw_server -ErrorAction SilentlyContinue)){
  Start-Process -FilePath "$binary/hw_server.bat" -WindowStyle Hidden
 }
}
$aliases=@('L:','M:','N:','O:','Q:') | Where-Object {-not (Test-Path "$_\")} | Select-Object -First 2
if($aliases.Count -ne 2){throw 'Two free drive aliases required'}
$previousLocation=Get-Location
$mounted=@()
$environmentNames=@('SCOPE_CPU_ROOT','TEMP','TMP','APPDATA','XILINX_TCLAPP_REPO','XILINX_LOCAL_USER_DATA')
$previousEnvironment=@{}
foreach($name in $environmentNames){$previousEnvironment[$name]=[Environment]::GetEnvironmentVariable($name)}
try {
 foreach($pair in @(@($aliases[0],$panelFolder),@($aliases[1],$cpuFolder))){
  subst $pair[0] $pair[1]
  if($LASTEXITCODE -ne 0){throw 'Drive alias creation failed'}
  $mounted+=$pair[0]
 }
 Set-Location "$($aliases[0])/"
 New-Item -ItemType Directory -Force output/tool_tmp,output/tool_appdata | Out-Null
 $env:SCOPE_CPU_ROOT="$($aliases[1])/"
 $env:TEMP="$($aliases[0])/output/tool_tmp";$env:TMP=$env:TEMP
 $env:APPDATA="$($aliases[0])/output/tool_appdata"
 $env:XILINX_TCLAPP_REPO=Join-Path (Split-Path $binary -Parent) 'data/XilinxTclStore'
 $env:XILINX_LOCAL_USER_DATA='NO'
 foreach($required in @('font.mem','small_font.mem','knob_ticks.mem','panel_small_font.svh','panel_font.h','panel_knob.h','output/panel.elf')){
  if(-not (Test-Path -LiteralPath $required)){throw "Missing $required; generate fonts and compile firmware first"}
 }
 if(-not (Test-Path output/page_0.mem)){throw 'Run test_c.ps1 to generate the test page first'}
 if($Action -eq 'build'){
  & python "$panelFolder/verify_release.py" snapshot
  if($LASTEXITCODE -ne 0){throw 'Source snapshot failed'}
 }
 & "$binary/vivado.bat" -mode batch -notrace -source "$Action.tcl" -log "output/$Action.log" -journal "output/$Action.jou"
 if($LASTEXITCODE -ne 0){throw "$Action failed; see output/$Action.log"}
 $marker=@{simulate='PANEL_SIMULATION_PASS';build='PANEL_BUILD_PASS';program='BOARD_PROGRAM_PASS';prepare_flash='PANEL_FLASH_PREPARE_PASS';program_flash='PANEL_FLASH_PROGRAM_PASS';verify_flash_boot='PANEL_FLASH_BOOT_PASS'}[$Action]
 if(-not (Select-String -LiteralPath "output/$Action.log" -Pattern "^$marker`$" -Quiet)){throw "$Action did not reach PASS"}
 if($Action -eq 'prepare_flash'){
  & python "$panelFolder/verify_flash_image.py" snapshot
  if($LASTEXITCODE -ne 0){throw 'Flash image binding failed'}
 }
 if($Action -eq 'build'){
  & python "$panelFolder/verify_release.py"
  if($LASTEXITCODE -ne 0){throw 'Completed build did not match its source snapshot'}
 }
} finally {
 Set-Location $previousLocation
 foreach($alias in $mounted){subst $alias /d}
 foreach($name in $environmentNames){[Environment]::SetEnvironmentVariable($name,$previousEnvironment[$name])}
}
