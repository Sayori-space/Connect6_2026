# Connect6 (六子棋)

PyQt5 六子棋客户端，支持人机对弈、AI-vs-AI、棋谱保存。

## 环境要求

| 组件 | 说明 |
|------|------|
| Python | 3.12（3.11 也可，Windows 推荐 `py -3`） |
| PyQt5 | `pip install PyQt5>=5.15.0` |
| GPU + OpenCL | 可选，运行 KataGo 引擎时需要（NVIDIA/AMD/Intel 均可） |
| C++ 编译工具链 | 可选，仅需重新编译 kata.exe 时使用 |

```bash
pip install -r requirements.txt
```

## 快速运行

```bash
# Windows
py -3 main.py

# macOS / Linux
python3 main.py
```

PyOpenGL 为可选依赖——未安装时自动降级为静态星空背景。

## AI 引擎

游戏提供五种 AI，启动后在 AI 配置页选择：

| 引擎 | 速度 | 棋力 | 依赖 |
|------|------|------|------|
| **AlphaBetaAI** | 极快 | 入门 | 无 |
| **AlphaBeltaPlusAI** | 快 | 中级 | 无 |
| **AlphaBeltaMaxAI** | 中 | 高级 | 无（推荐，零依赖最强） |
| **AB-Kata** | 中 | 很强 | kata.exe + 模型 |
| **KataGomo** | 慢 | 最强 | kata.exe + 模型 |

**AlphaBeltaMaxAI** 是纯 Python + Cython 加速的传统剪枝引擎（迭代加深、置换表、威胁静态搜索、PVS 零窗口、开局库），无需任何外部依赖。

---

## KataGo 引擎部署（Windows）

以下两种 AI 需要 KataGo 引擎：
- **KataGomo** — 引擎 MCTS 直出，不需要自己的搜索
- **AB-Kata** — Alpha-Beta 搜索 + NN 评估混合

### 1. 前置：GPU 与 OpenCL

本机使用 **NVIDIA RTX 4050 + OpenCL** 后端。需安装：

- **NVIDIA 显卡驱动**（自带 OpenCL.dll，无需额外操作）  
- 如需重新编译 kata.exe，需额外安装：
  - [CUDA Toolkit 11.8](https://developer.nvidia.com/cuda-11-8-0-download-archive)（提供 `OpenCL.lib` 链接库）
  - Visual Studio 2022（提供 MSVC 编译器 + NMake）
  - [CMake](https://cmake.org/download/) 3.20+

验证 OpenCL 可用：

```powershell
# 检查 OpenCL.dll 是否存在
Test-Path "C:\Windows\System32\OpenCL.dll"
```

### 2. 模型文件部署

模型文件约 **93 MB**，需要团队成员自行下载放置：

```
ai/models/kata/
└── connectsix19x_b18trans.bin.gz   # ← 下载这个文件放到这里
```

下载后将文件放到 `ai/models/kata/` 目录下即可。引擎启动时程序会自动检测——没放着时 AB-Kata 和 KataGomo 会降级为 AlphaBeltaMaxAI。

### 3. C++ 编译 kata.exe

二进制文件 `ai/kata_src/cpp/katago.exe` 已经编译好并在仓库中。**仅在需要重新编译或换机器时**才需要以下步骤。

#### 目录结构

```
ai/kata_src/cpp/
├── build.bat            ← 编译脚本
├── CMakeLists.txt       ← CMake 配置（KataGo 官方，已修改 Connect6 规则）
├── eigen/               ← Eigen 头文件（已解压在仓库中）
├── opencl_headers/      ← OpenCL 头文件
├── katago.exe           ← 编译产物（已在仓库中）
└── ...
```

#### 编译步骤

1. 安装 Visual Studio 2022（确保安装"使用 C++ 的桌面开发"工作负载）
2. 安装 CUDA Toolkit 11.8（编译时需要 `OpenCL.lib`）
3. 安装 CMake 3.20+
4. 修改 `build.bat` 中的路径：
   - `D:\apps\vs_studio_\VC\Auxiliary\Build\vcvars64.bat` → 你本机的 VS 安装目录
   - `D:\apps\cmake\...\cmake.exe` → 你本机的 CMake 路径
   - 项目根目录路径 → 你本机的仓库路径
5. 在 **Developer Command Prompt for VS** 中执行（或直接双击 `build.bat`）：

```batch
cd ai\kata_src\cpp
build.bat
```

编译参数说明：

```
-G "NMake Makefiles"          # 使用 NMake 生成器
-DUSE_BACKEND=OPENCL          # OpenCL 后端（兼容性最好）
-DNO_GIT_REVISION=1           # 跳过 git 版本检查
-DEIGEN3_INCLUDE_DIRS=eigen   # Eigen 头文件路径
-DOpenCL_INCLUDE_DIR=...      # OpenCL 头文件
-DOpenCL_LIBRARY=...          # OpenCL.lib（CUDA Toolkit 提供）
-DCMAKE_BUILD_TYPE=Release
```

编译完成后产物为 `katago.exe`（约 2.4 MB），放置在 `ai/kata_src/cpp/` 目录下。

#### 非 NVIDIA GPU 用户

如果使用 AMD 或 Intel GPU，需要修改：
- 安装对应的 OpenCL SDK（AMD ROCm / Intel oneAPI）
- 修改 `OpenCL_LIBRARY` 和 `OpenCL_INCLUDE_DIR` 指向对应 SDK
- 或在 CMake 中改用 CPU 后端：`-DUSE_BACKEND=EIGEN`

### 4. 验证 KataGo 引擎

```bash
py -3 -c "from ai.kata_gomo_ai import KataGomoAI; ai = KataGomoAI(); print(ai.name)"
```

输出 `KataGomo` 表示引擎就绪；输出 `KataGomo(降级)` 表示未找到引擎或模型。

---

## Cython 扩展

`ai/_cython_core.pyx` 加速了 AlphaBeltaMaxAI 的核心热循环（候选格估值、局面更新、邻近奖励），提供约 **2-3x** 的搜索速度提升。

已编译的 `.pyd` 文件（Python 3.12 / Windows x64）已在仓库中。如果在其他平台或 Python 版本运行，需重新编译：

```bash
pip install cython
cd ai
cythonize -i _cython_core.pyx
```

未加载 Cython 时自动回退到纯 Python 实现，不影响功能。

---

## 测试

```bash
# 运行全部测试
py -3 -m unittest discover tests -v

# 仅运行核心 AI 测试
py -3 -m unittest tests.test_alpha_belta_max_ai tests.test_alpha_belta_plus_ai tests.test_ai_position_suite

# 性能基准
py -3 scripts/benchmark_ai.py tests/fixtures/ai_positions --engine alpha_belta_max --format json
```

---

## 棋谱记录

对局结束后自动保存到 `chess_manual/` 目录，文件名格式为 `YYYY-MM-DDTHH-MM-SS.txt`（JSON）。

```json
{"1": [{"B": "(9, 9)"}, {"W": "(8, 8)"}, ...], "2": [...], ...}
```

每局记录包含：黑/白引擎名称、获胜方、完整着法序列。

---

## 目录结构

```
c6/
├── main.py                  # 入口
├── utils/constants.py       # 常量（EMPTY/BLACK/WHITE）
├── models/                  # 数据模型（Move, Player, GameConfig）
├── game/                    # 游戏逻辑（Board, 规则, GameManager）
├── ai/                      # AI 引擎
│   ├── base_ai.py           #   抽象基类
│   ├── alpha_beta_ai.py     #   Alpha-Beta 基线
│   ├── alpha_belta_plus_ai.py  # 战术保护增强版
│   ├── alpha_belta_max_ai.py   # 最大优化版（Cython 加速）
│   ├── kata_gomo_ai.py      #   KataGo MCTS 直出
│   ├── ab_kata_ai.py        #   Alpha-Beta + NN 混合
│   ├── _cython_core.pyx     #   Cython 热路径
│   ├── _cython_core.*.pyd   #   已编译扩展
│   ├── models/kata/         #   NN 模型文件（需自行下载）
│   └── kata_src/cpp/        #   KataGo C++ 源码 + katago.exe
├── ui/                      # PyQt5 界面
├── tests/                   # 单元测试 + fixtures
├── scripts/                 # 工具脚本（benchmark, 自对弈, 分析）
└── chess_manual/            # 对局记录（自动保存）
```
