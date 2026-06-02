"""Build Cython extensions.  Run:  py -3 setup_cython.py build_ext --inplace"""
import os
import sys
from setuptools import setup, Extension
from Cython.Build import cythonize

# Locate MSVC compiler
VS_BASE = r"D:\apps\vs_studio_"
vcvars = os.path.join(VS_BASE, "VC", "Auxiliary", "Build", "vcvars64.bat")
if not os.path.exists(vcvars):
    # Try auto-detect
    import subprocess
    try:
        result = subprocess.run(
            ['cmd', '/c', 'where', 'cl.exe'],
            capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stdout.strip():
            vcvars = None  # cl.exe already in PATH
        else:
            print("ERROR: Cannot find MSVC compiler.")
            print("Run this script from a 'x64 Native Tools Command Prompt' or")
            print(f"check that {VS_BASE} exists.")
            sys.exit(1)
    except Exception:
        pass

# Set up MSVC environment if needed
if vcvars and os.path.exists(vcvars):
    import subprocess
    result = subprocess.run(
        f'cmd /c ""{vcvars}" >nul 2>&1 && set"',
        capture_output=True, text=True, shell=True)
    for line in result.stdout.splitlines():
        if '=' in line:
            key, _, value = line.partition('=')
            if key.upper() in ('PATH', 'LIB', 'INCLUDE', 'LIBPATH'):
                os.environ[key] = value

ext = Extension(
    "ai._cython_core",
    sources=[r"ai\_cython_core.pyx"],
)

setup(
    name="_cython_core",
    ext_modules=cythonize(
        [ext],
        compiler_directives={
            "language_level": "3",
            "boundscheck": False,
            "wraparound": False,
        },
    ),
)
