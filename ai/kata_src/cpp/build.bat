@echo off
call "D:\apps\vs_studio_\VC\Auxiliary\Build\vcvars64.bat"
if %ERRORLEVEL% neq 0 exit /b %ERRORLEVEL%

set ROOT=D:\workplace\python_project\c6\ai\kata_src\cpp
set CMAKE=D:\apps\cmake\cmake-4.3.3-windows-x86_64\cmake-4.3.3-windows-x86_64\bin\cmake.exe
cd /d "%ROOT%"

rmdir /s /q CMakeFiles 2>nul
del CMakeCache.txt 2>nul

%CMAKE% . -G "NMake Makefiles" ^
    -DUSE_BACKEND=OPENCL ^
    -DNO_GIT_REVISION=1 ^
    -DEIGEN3_INCLUDE_DIRS=eigen ^
    -DOpenCL_INCLUDE_DIR="%ROOT%/opencl_headers" ^
    -DOpenCL_LIBRARY="C:/Program Files/NVIDIA GPU Computing Toolkit/CUDA/v11.8/lib/x64/OpenCL.lib" ^
    -DCMAKE_BUILD_TYPE=Release
if %ERRORLEVEL% neq 0 exit /b %ERRORLEVEL%
nmake
