"""Process-local, writable ASCII paths for the Windows Vivado toolchain."""
import atexit
import os
from pathlib import Path
import subprocess
import tempfile


def configure(binary):
    binary = Path(binary)
    if os.name != 'nt':
        return {}
    selected = os.environ.get('SCOPE_SIM_ROOT')
    if selected and Path(selected).is_dir():
        root = Path(selected)
    else:
        target = Path(__file__).resolve().parents[2]
        # Never replace or delete another task's drive mapping.
        diagnostics = []
        for letter in 'ZYXWVUT':
            drive = letter+':'
            if Path(drive+'/').exists():
                if os.path.samefile(drive+'/', target):
                    workspace = Path(drive+'/')
                    root = workspace/'tmp/fpga_ascii'
                    break
                continue
            result = subprocess.run(['subst', drive, str(target)], capture_output=True)
            diagnostics.append((drive, result.returncode, result.stdout.decode('utf-8','replace'), result.stderr.decode('utf-8','replace')))
            if result.returncode == 0 and Path(drive+'/').is_dir():
                workspace = Path(drive+'/')
                root = workspace/'tmp/fpga_ascii'
                atexit.register(subprocess.run, ['subst', drive, '/D'], capture_output=True)
                break
        else:
            raise OSError('Could not create an ASCII workspace alias. On restricted Windows hosts, launch FPGA/scripts/run_regression.ps1 so PowerShell prepares the alias before Python. Details: '+repr(diagnostics))
        os.environ['SCOPE_SIM_PROJECT_ROOT'] = workspace.as_posix()
    paths = {'TEMP':root/'compiler_tmp', 'TMP':root/'compiler_tmp',
             'APPDATA':root/'tool_appdata'}
    for name, path in paths.items():
        path.mkdir(parents=True, exist_ok=True)
        os.environ[name] = path.as_posix()
    os.environ.update(SCOPE_SIM_ROOT=root.as_posix(), XILINX_LOCAL_USER_DATA='NO',
                      XILINX_TCLAPP_REPO=(binary.parent/'data/XilinxTclStore').as_posix())
    if 'SCOPE_NATIVE_PROJECT_DIR' not in os.environ:
        os.environ['SCOPE_NATIVE_PROJECT_DIR']=(root/f'native_{os.getpid()}'/'scope_smoke').as_posix()
    tempfile.tempdir = (root/'compiler_tmp').as_posix()
    return {name:os.environ[name] for name in (*paths, 'SCOPE_SIM_ROOT',
                  'SCOPE_SIM_PROJECT_ROOT', 'SCOPE_NATIVE_PROJECT_DIR', 'XILINX_LOCAL_USER_DATA', 'XILINX_TCLAPP_REPO') if name in os.environ}
