import os
import site
import sys
from pathlib import Path

if sys.platform == "win32":
    # os.add_dll_directory returns a handle — must be kept alive or Windows
    # removes the directory from the DLL search path when it's garbage collected.
    _dll_handles = []
    for _sp in site.getsitepackages():
        _nvidia = Path(_sp) / "nvidia"
        if _nvidia.exists():
            for _bin in _nvidia.glob("*/bin"):
                _dll_handles.append(os.add_dll_directory(str(_bin)))
