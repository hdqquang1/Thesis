# Building Open3D 0.19 with CUDA + PyTorch ops on Windows

Upstream Open3D does **not** build/test the PyTorch (`open3d.ml.torch`) ops on
Windows — its CI only builds ML ops on Linux. This documents the blockers hit
building them on Windows anyway, and the fixes that made it work.

## Environment

- Windows 11, Visual Studio 2022 (MSVC 14.38), CUDA 12.6 (nvcc 12.6.85)
- conda env `pc`: Python 3.12, PyTorch **2.12.0+cu126**
- GPU arch sm_89 (compute_89)
- Open3D source on `N:\`, out-of-source build dir on `C:\o3d_build`

## Working configuration

Build with the **Ninja** generator from an **x64 Native Tools Command Prompt for
VS 2022** (so `cl.exe` is on PATH), with the conda env active:

```bat
cmake -G Ninja -DCMAKE_BUILD_TYPE=Release ^
  -DBUILD_CUDA_MODULE=ON -DBUILD_PYTORCH_OPS=ON ^
  -DBUNDLE_OPEN3D_ML=ON -DOPEN3D_ML_ROOT=N:/Thesis/Open3D-ML ^
  -DBUILD_WEBRTC=OFF -DSTATIC_WINDOWS_RUNTIME=OFF ^
  -DBUILD_EXAMPLES=OFF -DBUILD_UNIT_TESTS=OFF -DBUILD_BENCHMARKS=OFF ^
  N:/Thesis/Open3D
ninja -j 2 install-pip-package
```

Prerequisites installed into the env: `pip install ninja`,
`conda install -c conda-forge glslang`, and **CMake 3.29** (CMake 4.x mangled the
`OPEN3D_ML_ROOT` URL). Verified working: `o3d.__DEVICE_API__ == "cuda"`,
`o3d._build_config["BUILD_PYTORCH_OPS"] == true`, `import open3d.ml.torch.ops`.

## Blockers and fixes

### 0. Generator: use Ninja, not MSBuild
The default Visual Studio/MSBuild generator failed on the torch ops with
`MSB3721 / nvcc fatal: A single input file is required for a non-link phase`,
because the `CUDA <ver>.targets` MSBuild rules mangle the nvcc command line.
Ninja invokes `nvcc`/`cl` directly and avoids that layer. (PyTorch's own build
system uses Ninja on Windows for the same reason.)

### 1. CMake 4.x mangled the Open3D-ML git URL
`-DOPEN3D_ML_ROOT=https://github.com/...` was passed to git as `https:/...`
(one slash collapsed) → clone failed and fell back to SSH. **Fix:** install
CMake 3.29 (`conda install -c conda-forge cmake=3.29`) and clone Open3D-ML
locally, pointing `OPEN3D_ML_ROOT` at the local path.

### 2. Missing `glslangValidator`
The GUI shader step needs it; the Native Tools prompt's trimmed PATH didn't have
it. **Fix:** `conda install -c conda-forge glslang`.

### 3. WebRTC prebuilt lib missing under Ninja
`ninja: 'webrtc.lib' ... missing and no known rule to make it`. WebRTC is the
browser-streaming visualizer, not the native GUI. **Fix:** `-DBUILD_WEBRTC=OFF`.

### 4. `nvcc fatal: A single input file is required` — bare `/utf-8`
`cpp/open3d/ml/pytorch/CMakeLists.txt` passed `/utf-8` to the target unwrapped;
nvcc reads a bare `/utf-8` as a second input file. **Fix (source):** wrap it
per-language — `/utf-8` for CXX, `-Xcompiler=/utf-8` for CUDA.

### 5. `_wassert` redeclaration cannot add dllexport/dllimport
PyTorch's `Macros.h` (in a Release/NDEBUG build) declares `_wassert` with
`C10_IMPORT` (`__declspec(dllimport)`), conflicting with CUDA's
`crt/common_functions.h` declaration. **Fix (torch header patch):** in
`torch/include/torch/headeronly/macros/Macros.h`, skip `C10_IMPORT` for the
`_wassert` decl when `__CUDACC__` is defined. *(Lives in the installed torch
package — reapply if torch is reinstalled/upgraded.)*

### 6. PyTorch's bundled fmt v12 doesn't compile under nvcc on Windows
Open3D pins its own fmt to 9.1.0 on MSVC for this reason, but torch bundles
fmt v12 (`torch/include/fmt`) which leaks into nvcc device compiles via
`-isystem torch/include` and fails (`/utf-8` unicode `static_assert`, plus
`char out of range` / `constexpr` device diagnostics). **Fix (source):** on the
`open3d_torch_ops` target, `-DFMT_UNICODE=0` and nvcc `--diag-suppress=27,128,2417`.

### 7. CUDA `cusparse.h` deprecated types → C4996
torch pulls in `cusparse.h`; its legacy types are `[[deprecated]]`, and `/WX`
promotes the C4996 to errors. **Fix (source):** `-DDISABLE_CUSPARSE_DEPRECATED`
on the target (CUDA macro that strips the deprecation attributes).

### 8. torch header warnings (C4251/C4275) promoted by `/WX`
`open3d_show_and_abort_on_warning()` forces `/WX` + nvcc `--Werror all-warnings`;
torch headers can't satisfy that (dll-interface warnings), and nvcc reorders
`/WX` after any `/WX-` we append, so it can't be overridden per-file.
**Fix (source):** don't call `open3d_show_and_abort_on_warning(open3d_torch_ops)`
for this third-party-binding target.

### 9. `compiler is out of heap space` (C1060)
The heaviest torch-template TUs exhaust RAM when several `cl` run in parallel.
**Fix:** lower build parallelism (`ninja -j 2`, or `-j 1`); optionally raise the
Windows pagefile.

### 10. `C2872: 'std': ambiguous symbol` in `compiled_autograd.h`
torch headers need MSVC conformance mode (`/permissive-`) for correct `::std`
lookup. `Caffe2Targets.cmake` sets `/permissive-` for `COMPILE_LANGUAGE:CXX`
only, so nvcc's host pass for `.cu` files lacked it. **Fix (source):** add
`$<$<COMPILE_LANGUAGE:CUDA>:-Xcompiler=/permissive->` on the target.

### 11. `LNK2038: RuntimeLibrary MT_StaticRelease vs MD_DynamicRelease`
Open3D defaults to the static CRT (`/MT`) on Windows, but PyTorch (and the
bundled BoringSSL as built here) use the dynamic CRT (`/MD`). A torch extension
must use `/MD`. **Fix:** `-DSTATIC_WINDOWS_RUNTIME=OFF` (rebuild so all bundled
deps also compile `/MD`).

## Source changes (in this repo)

All in `cpp/open3d/ml/pytorch/CMakeLists.txt`, inside the `if (MSVC)` block and at
the target setup:

- `/utf-8` wrapped per-language (CXX direct, CUDA via `-Xcompiler`).
- `target_compile_definitions(... FMT_UNICODE=0 DISABLE_CUSPARSE_DEPRECATED)`.
- nvcc `--diag-suppress=27,128,2417` for CUDA.
- `-Xcompiler=/permissive-` for CUDA.
- Removed the `open3d_show_and_abort_on_warning(open3d_torch_ops)` call.

Out-of-repo (env) changes: the `_wassert` patch in the installed torch
`Macros.h`; CMake 3.29, ninja, and glslang installed into the `pc` env.

## Notes

- Items 4 and 6–10 are genuine upstream gaps for Windows torch ops; 4 (the
  `/utf-8` wrap) and 10 (`/permissive-` for CUDA) are clean, PR-worthy fixes.
- `BUNDLE_OPEN3D_ML=ON` also needs pure-Python deps for the high-level models:
  `pip install tensorboard pandas scikit-learn tqdm addict pyyaml`. The compiled
  ops (`open3d.ml.torch.ops`) work without them.
