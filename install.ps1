# ==============================================================================
# youtubu Windows 一键部署脚本 (PowerShell)
# 支持一行命令运行: 
#   irm https://raw.githubusercontent.com/furina707/youtubu/main/install.ps1 | iex
# ==============================================================================

# 设置控制台输出编码为 UTF-8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

function Write-Info($msg) {
    Write-Host "[INFO] $msg" -ForegroundColor Cyan
}

function Write-Success($msg) {
    Write-Host "[SUCCESS] $msg" -ForegroundColor Green
}

function Write-Warn($msg) {
    Write-Host "[WARN] $msg" -ForegroundColor Yellow
}

function Write-Err($msg) {
    Write-Host "[ERROR] $msg" -ForegroundColor Red
    exit 1
}

Write-Host "=======================================================" -ForegroundColor Blue
Write-Host "        youtubu Windows 一键自动部署与安装向导        " -ForegroundColor Blue
Write-Host "  YouTube/抖音 视频下载 · 本地语音识别 · 双语字幕翻译  " -ForegroundColor Blue
Write-Host "=======================================================" -ForegroundColor Blue
Write-Host ""

# 1. 检查 Python
Write-Info "正在检测 Python 环境..."
$pythonCmd = $null
if (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonCmd = "python"
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $pythonCmd = "py"
}

if (-not $pythonCmd) {
    Write-Warn "未检测到 Python！正在尝试通过 winget 自动安装 Python 3.11..."
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install -e --id Python.Python.3.11 --accept-package-agreements --accept-source-agreements
        Write-Info "安装完成，请重新打开 PowerShell 并再次运行本命令。"
        exit 0
    } else {
        Write-Err "未找到 Python 且未检测到 winget，请先前往 https://www.python.org/downloads/ 安装 Python (勾选 Add Python to PATH)。"
    }
}

$pyVer = & $pythonCmd --version 2>&1
Write-Info "当前 Python: $pyVer"

# 2. 检查 Git
Write-Info "正在检测 Git..."
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Warn "未检测到 Git，尝试使用 winget 安装 Git..."
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install -e --id Git.Git --accept-package-agreements --accept-source-agreements
        Write-Info "Git 安装成功，请重新运行脚本。"
        exit 0
    } else {
        Write-Err "请先安装 Git: https://git-scm.com/download/win"
    }
}

# 3. 确定安装目录与克隆/更新代码
$installDir = if ($env:YOUTUBU_DIR) { $env:YOUTUBU_DIR } else { "$HOME\youtubu" }

# 如果当前已经在项目目录中，则使用当前目录
if (Test-Path ".\src\pipeline.py") {
    $installDir = (Get-Location).Path
    Write-Info "检测到当前目录即为 youtubu 仓库: $installDir"
} elseif (Test-Path "$installDir\.git") {
    Write-Info "目标目录已存在仓库: $installDir，正在拉取最新更新..."
    Set-Location $installDir
    git pull origin main
} else {
    Write-Info "正在克隆代码仓库到: $installDir ..."
    git clone "https://github.com/furina707/youtubu.git" $installDir
    Set-Location $installDir
}

# 4. 创建与激活虚拟环境
$venvDir = "$installDir\venv"
if (-not (Test-Path $venvDir)) {
    Write-Info "正在创建 Python 虚拟环境 (venv)..."
    & $pythonCmd -m venv $venvDir
} else {
    Write-Info "检测到已有虚拟环境，跳过创建。"
}

$venvPython = "$venvDir\Scripts\python.exe"
$venvPip = "$venvDir\Scripts\pip.exe"

if (-not (Test-Path $venvPython)) {
    Write-Err "虚拟环境 Python 未找到，请检查环境配置。"
}

# 5. 网络镜像检测与优化 (国内加速)
Write-Info "正在升级 pip..."
& $venvPython -m pip install --upgrade pip -q

$isCN = $false
try {
    $testBaidu = Test-Connection -ComputerName "www.baidu.com" -Count 1 -Quiet
    $testGoogle = Test-Connection -ComputerName "www.google.com" -Count 1 -Quiet
    if ($testBaidu -and -not $testGoogle) {
        $isCN = $true
    }
} catch {
    # 保持默认
}

if ($isCN) {
    Write-Info "检测到中国大陆网络环境，配置清华大学 PyPI 镜像源..."
    & $venvPip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
    $env:HF_ENDPOINT = "https://hf-mirror.com"
}

# 6. 检测 NVIDIA GPU (CUDA)
Write-Info "正在检测显卡与 CUDA 环境..."
$hasCUDA = $false
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
    try {
        $gpuOut = nvidia-smi 2>&1
        if ($LASTEXITCODE -eq 0) {
            $hasCUDA = $true
            Write-Info "检测到 NVIDIA GPU，正在配置 CUDA 12.1 硬件加速版本 PyTorch..."
            & $venvPip install torch --index-url https://download.pytorch.org/whl/cu121
        }
    } catch {
        # 降级 CPU
    }
}

if (-not $hasCUDA) {
    Write-Info "未检测到独立 GPU，将使用 CPU 计算推理模式。"
}

# 7. 安装核心依赖
Write-Info "正在安装项目所需核心依赖 (requirements.txt)..."
& $venvPip install -r "$installDir\requirements.txt"

# 8. 生成快捷启动批处理文件
# 8.1 start_tui.bat (终端交互模式)
$tuiBat = @"
@echo off
chcp 65001 >nul
title youtubu - 终端交互面板
cd /d "%~dp0"
if exist "%~dp0venv\Scripts\activate.bat" call "%~dp0venv\Scripts\activate.bat"
if not defined HF_ENDPOINT set HF_ENDPOINT=https://hf-mirror.com
python tui.py
pause
"@
[System.IO.File]::WriteAllText("$installDir\start_tui.bat", $tuiBat, [System.Text.Encoding]::UTF8)

# 8.2 start_gui.bat (桌面图形模式)
$guiBat = @"
@echo off
chcp 65001 >nul
title youtubu - 桌面主程序
cd /d "%~dp0"
if exist "%~dp0venv\Scripts\activate.bat" call "%~dp0venv\Scripts\activate.bat"
if not defined HF_ENDPOINT set HF_ENDPOINT=https://hf-mirror.com
python -m src.main
pause
"@
[System.IO.File]::WriteAllText("$installDir\start_gui.bat", $guiBat, [System.Text.Encoding]::UTF8)

# 8.3 run.bat (CLI 命令行快捷运行)
$runBat = @"
@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist "%~dp0venv\Scripts\activate.bat" call "%~dp0venv\Scripts\activate.bat"
if not defined HF_ENDPOINT set HF_ENDPOINT=https://hf-mirror.com
if "%~1"=="" (
    python tui.py
) else (
    python -m src.main %*
)
"@
[System.IO.File]::WriteAllText("$installDir\run.bat", $runBat, [System.Text.Encoding]::UTF8)

Write-Host ""
Write-Success "======================================================="
Write-Success "             🎉 Windows 部署安装完成！                  "
Write-Success "======================================================="
Write-Host ""
Write-Host "项目安装目录: $installDir" -ForegroundColor Cyan
Write-Host ""
Write-Host "【快速启动方式】" -ForegroundColor Yellow
Write-Host "1. 双击运行 TUI 终端模式:"
Write-Host "   $installDir\start_tui.bat" -ForegroundColor Cyan
Write-Host ""
Write-Host "2. 双击运行 GUI 桌面图形模式:"
Write-Host "   $installDir\start_gui.bat" -ForegroundColor Cyan
Write-Host ""
Write-Host "3. PowerShell / CMD 命令行直接调用:"
Write-Host "   cd $installDir; .\run.bat `"https://www.youtube.com/watch?v=xxxx`" --src en --tgt zh" -ForegroundColor Cyan
Write-Host ""
