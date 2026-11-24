#!/usr/bin/env bash
# Build dist/OpenCardShop-<version>-Setup.exe on Linux: a per-user Windows installer
# with its own Python, Tcl/Tk and Pillow, so nothing else needs installing on Windows.
#
# Needs: makensis (sudo apt install nsis), curl, python3 with pip (sudo apt install python3-pip),
# python3.12 for byte-compiling, and network access to conda.anaconda.org and pypi.org.
# Python and Tcl/Tk come from conda-forge (win-64), Pillow from its official Windows wheel.
# No CardShop Plus content is packaged.
set -euo pipefail
src="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
version="$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' "$src/opencardshop/__init__.py")"
out="${1:-$src/dist}"
cache="${OPENCARDSHOP_BUILD_CACHE:-$HOME/.cache/opencardshop-build}"
python_spec="${PYTHON_SPEC:-python=3.12}"
pillow_spec="${PILLOW_SPEC:-pillow>=11}"
micromamba_url="${MICROMAMBA_URL:-https://conda.anaconda.org/conda-forge/linux-64/micromamba-2.10.0-0.tar.bz2}"
compile_python="${COMPILE_PYTHON:-python3.12}"

mkdir -p "$cache" "$out"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
stage="$work/stage"
runtime="$stage/runtime"

# 1. Python + Tcl/Tk for Windows from conda-forge.
if [ ! -x "$cache/micromamba/bin/micromamba" ]; then
    mkdir -p "$cache/micromamba"
    curl -fsSL "$micromamba_url" | tar -xj -C "$cache/micromamba" bin/micromamba
fi
export MAMBA_ROOT_PREFIX="$cache/mamba-root"
"$cache/micromamba/bin/micromamba" create -y -q --platform win-64 -p "$work/env" -c conda-forge --override-channels "$python_spec" tk

# 2. Copy the unmodified package files. micromamba rewrites the build prefix inside some
#    files as text, which corrupts binaries such as _tkinter.pyd when run on Linux.
python3 - "$work/env" "$MAMBA_ROOT_PREFIX/pkgs" "$runtime" <<'EOF'
import json, shutil, sys
from pathlib import Path
env, pkgs, runtime = map(Path, sys.argv[1:])
cache = {p.name: p for p in pkgs.rglob("*") if p.is_dir() and (p / "info" / "index.json").is_file()}
for meta in (env / "conda-meta").glob("*.json"):
    record = json.loads(meta.read_text())
    if record.get("noarch") in ("python", {"type": "python"}):
        continue  # pip, setuptools, wheel: not needed by the application
    package = cache[meta.stem]
    licences = package / "info" / "licenses"
    if licences.is_dir():  # keep each bundled component's licence text
        shutil.copytree(licences, runtime / "licenses" / record["name"], dirs_exist_ok=True)
    for entry in record.get("paths_data", {}).get("paths", []):
        source = package / entry["_path"]
        if source.is_file():
            target = runtime / entry["_path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
EOF

# 3. Lay it out like a python.org installation: extension DLLs beside the .pyd files and
#    Tcl/Tk scripts in runtime\tcl, where _tkinter looks without any environment variables.
for dll in tcl86t.dll tk86t.dll zlib1.dll ffi-8.dll libexpat.dll liblzma.dll libbz2.dll \
           libssl-3-x64.dll libcrypto-3-x64.dll sqlite3.dll; do
    mv "$runtime/Library/bin/$dll" "$runtime/DLLs/"
done
mkdir -p "$runtime/tcl"
for folder in tcl8.6 tk8.6 tcl8; do mv "$runtime/Library/lib/$folder" "$runtime/tcl/"; done
rm -rf "$runtime/tcl/tk8.6/demos" "$runtime/Library" "$runtime/Scripts" "$runtime/Tools" "$runtime/include" \
       "$runtime/libs" "$runtime/share" "$runtime/etc" "$runtime/conda-meta"
rm -rf "$runtime"/Lib/{test,idlelib,ensurepip,lib2to3,turtledemo,venv,pydoc_data} "$runtime"/Lib/site-packages/*
rm -f "$runtime"/*.pdb "$runtime"/DLLs/_test*.pyd "$runtime"/DLLs/xxlimited*.pyd "$runtime"/DLLs/_ctypes_test.pyd
find "$runtime" -name '__pycache__' -prune -exec rm -rf {} +
find "$runtime" -name 'tests' -path '*/Lib/*' -prune -exec rm -rf {} +

# 4. Pillow's official Windows wheel (its libraries are built in).
python3 -m pip download -q --only-binary=:all: --platform win_amd64 --implementation cp \
    --python-version "$(sed -n 's/^python=\([0-9.]*\).*/\1/p' <<<"$python_spec")" "$pillow_spec" -d "$cache/wheels"
wheel="$(ls -t "$cache"/wheels/pillow-*-win_amd64.whl | head -1)"
python3 -m zipfile -e "$wheel" "$runtime/Lib/site-packages/"
"$compile_python" -m compileall -q -j0 --invalidation-mode unchecked-hash "$runtime/Lib" >/dev/null

# 5. The application, the open starter pack and the icon.
mkdir -p "$stage/app/assets"
cp "$src/main.py" "$stage/app/"
cp -r "$src/opencardshop" "$stage/app/"
cp -r "$src/assets/fallback_fonts" "$src/assets/starter" "$src/assets/icons" "$stage/app/assets/"
cp "$src/README.md" "$src/NOTICE.md" "$src/LICENSE" "$stage/app/"
find "$stage/app" -name '__pycache__' -prune -exec rm -rf {} +
cp "$src/assets/icons/opencardshop.ico" "$stage/"
sed 's/$/\r/' "$src/LICENSE" > "$stage/LICENSE.txt"
printf '@echo off\r\nrem Command-line export, for example: opencardshop-cli card.occard --export card.pdf --paper A4\r\n"%%~dp0runtime\\python.exe" -E -s "%%~dp0app\\main.py" %%*\r\n' > "$stage/opencardshop-cli.cmd"

# 6. Check that every DLL and extension module can find its dependencies.
python3 - "$runtime" <<'EOF'
import sys
from pathlib import Path
try:
    import pefile
except ImportError:
    print("pefile not installed; skipping the DLL dependency check"); raise SystemExit
runtime = Path(sys.argv[1])
system = {"kernel32.dll", "user32.dll", "gdi32.dll", "advapi32.dll", "shell32.dll", "ole32.dll", "oleaut32.dll",
          "comdlg32.dll", "comctl32.dll", "imm32.dll", "ws2_32.dll", "netapi32.dll", "userenv.dll", "version.dll",
          "shlwapi.dll", "bcrypt.dll", "crypt32.dll", "rpcrt4.dll", "winmm.dll", "iphlpapi.dll", "secur32.dll",
          "msvcrt.dll", "ntdll.dll", "psapi.dll", "dbghelp.dll", "msimg32.dll", "uxtheme.dll", "dwmapi.dll",
          "cabinet.dll", "msi.dll", "wtsapi32.dll", "mpr.dll", "winspool.drv", "propsys.dll",
          "d3d11.dll", "d3dcompiler_47.dll", "dxgi.dll"}
missing = []
for module in list(runtime.glob("*.dll")) + list(runtime.glob("*.exe")) + list(runtime.rglob("*.pyd")) + list((runtime / "DLLs").glob("*.dll")):
    pe = pefile.PE(str(module), fast_load=True)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]])
    if any("import table" in warning.lower() for warning in pe.get_warnings()):
        missing.append((module.name, "damaged import table"))
    for entry in getattr(pe, "DIRECTORY_ENTRY_IMPORT", []):
        name = entry.dll.decode().lower()
        if name.startswith(("api-ms-", "ext-ms-")) or name in system:
            continue
        if not ((runtime / name).exists() or (runtime / "DLLs" / name).exists() or (module.parent / name).exists()
                or any(p.name.lower() == name for p in [*runtime.iterdir(), *(runtime / "DLLs").iterdir(), *module.parent.iterdir()])):
            missing.append((module.relative_to(runtime).as_posix(), name))
if missing:
    raise SystemExit(f"Unresolved Windows DLL dependencies: {missing}")
print("DLL dependency check passed")
EOF

# 7. Installer.
size_kb="$(du -sk "$stage" | cut -f1)"
makensis -V2 -DVERSION="$version" -DSTAGE="$stage" -DSIZE_KB="$size_kb" \
    -DOUTFILE="$out/OpenCardShop-$version-Setup.exe" "$src/packaging/windows/opencardshop.nsi"
echo "Built $out/OpenCardShop-$version-Setup.exe"
