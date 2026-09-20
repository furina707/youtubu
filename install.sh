#!/usr/bin/env bash
# ==============================================================================
# youtubu 一键部署脚本 (Linux / macOS)
# 支持 Ubuntu, Debian, CentOS, RHEL, Fedora, Arch Linux 等
# ==============================================================================

set -e

# 颜色输出定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

info() {
    echo -e "${CYAN}[INFO]${NC} $1"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

# 打印横幅
echo -e "${BLUE}"
echo "======================================================="
echo "        youtubu 一键自动部署与安装向导              "
echo "  YouTube/抖音 视频下载 · 本地语音识别 · 双语字幕翻译  "
echo "======================================================="
echo -e "${NC}"

# 1. 检查权限
SUDO=""
if [ "$(id -u)" -ne 0 ]; then
    if command -v sudo &>/dev/null; then
        SUDO="sudo"
        info "已启用 sudo 权限执行系统软件包安装。"
    else
        warn "未检测到 root 或 sudo 权限，系统级依赖（ffmpeg, python3）可能需要手动安装。"
    fi
fi

# 2. 检测系统包管理器并安装基础依赖
install_system_deps() {
    info "正在检查并安装系统依赖 (git, python3, ffmpeg, pip)..."

    if command -v apt-get &>/dev/null; then
        $SUDO apt-get update -y
        $SUDO apt-get install -y git python3 python3-pip python3-venv ffmpeg curl
    elif command -v dnf &>/dev/null; then
        $SUDO dnf install -y epel-release || true
        $SUDO dnf install -y git python3 python3-pip ffmpeg curl
    elif command -v yum &>/dev/null; then
        $SUDO yum install -y epel-release || true
        $SUDO yum install -y git python3 python3-pip ffmpeg curl
    elif command -v pacman &>/dev/null; then
        $SUDO pacman -Sy --noconfirm git python python-pip ffmpeg curl
    elif command -v brew &>/dev/null; then
        brew install git python ffmpeg
    else
        warn "未能识别的包管理器，请确保已安装 git, python3, ffmpeg。"
    fi
}

install_system_deps

# 验证 Python 版本
if ! command -v python3 &>/dev/null; then
    error "Python3 未安装，请先安装 Python 3.9+ 后重试。"
fi

PYTHON_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
info "当前 Python 版本: $PYTHON_VER"

# 3. 确定安装目录与克隆仓库
REPO_URL="https://github.com/furina707/youtubu.git"
INSTALL_DIR="${YOUTUBU_DIR:-$HOME/youtubu}"

if [ -d "$INSTALL_DIR/.git" ]; then
    info "检测到已存在仓库目录: $INSTALL_DIR，正在拉取最新代码..."
    cd "$INSTALL_DIR"
    git pull origin main
else
    info "正在克隆代码仓库到: $INSTALL_DIR ..."
    git clone "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# 4. 创建虚拟环境
VENV_DIR="$INSTALL_DIR/venv"
if [ ! -d "$VENV_DIR" ]; then
    info "正在创建 Python 虚拟环境 (venv)..."
    python3 -m venv "$VENV_DIR"
else
    info "检测到已有虚拟环境，跳过创建。"
fi

# 激活虚拟环境
source "$VENV_DIR/bin/activate"

# 5. 网络区域检测与镜像配置 (针对国内服务器优化)
info "正在优化 pip 安装源..."
pip install --upgrade pip

# 检测国内网络并设置 HF / pip 镜像
IS_CN=false
if curl -s --connect-timeout 2 https://www.baidu.com &>/dev/null; then
    if ! curl -s --connect-timeout 3 https://www.google.com &>/dev/null; then
        IS_CN=true
    fi
fi

if [ "$IS_CN" = true ]; then
    info "检测到当前服务器位于中国大陆网络，配置镜像加速..."
    pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
    export HF_ENDPOINT="https://hf-mirror.com"
fi

# 6. 检测 GPU / CUDA 并安装 PyTorch
info "正在检测 GPU 硬件环境..."
HAS_CUDA=false
if command -v nvidia-smi &>/dev/null; then
    if nvidia-smi &>/dev/null; then
        HAS_CUDA=true
        info "检测到 NVIDIA 独立显卡与驱动支持！将安装 CUDA 12 加速版本 PyTorch..."
    fi
fi

if [ "$HAS_CUDA" = true ]; then
    pip install torch --index-url https://download.pytorch.org/whl/cu121
else
    info "未检测到可用 GPU，将采用 CPU 模式运行。"
fi

# 7. 安装项目依赖
info "正在安装项目核心依赖 (requirements.txt)..."
pip install -r requirements.txt

# 8. 生成便捷启动脚本 run.sh
cat << 'EOF' > "$INSTALL_DIR/run.sh"
#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -f "$SCRIPT_DIR/venv/bin/activate" ]; then
    source "$SCRIPT_DIR/venv/bin/activate"
fi

# 如果是国内服务器则自动设置 HF 镜像
if [ -z "$HF_ENDPOINT" ]; then
    export HF_ENDPOINT="https://hf-mirror.com"
fi

if [ "$1" = "--web" ]; then
    shift
    PORT="${1:-8000}"
    python3 web.py --host 0.0.0.0 --port "$PORT"
elif [ $# -eq 0 ]; then
    # 无参数默认启动 TUI 交互界面
    python3 tui.py
else
    # 带参数以 CLI 命令行运行
    python3 -m src.main "$@"
fi
EOF

chmod +x "$INSTALL_DIR/run.sh"

# 尝试创建全局软链接到 /usr/local/bin/youtubu (若有权限)
if [ -w "/usr/local/bin" ] || [ -n "$SUDO" ]; then
    $SUDO ln -sf "$INSTALL_DIR/run.sh" /usr/local/bin/youtubu 2>/dev/null || true
fi

echo ""
echo -e "${GREEN}======================================================="
echo "             🎉 youtubu 部署完成！                     "
echo "=======================================================${NC}"
echo ""
echo -e "安装路径: ${CYAN}$INSTALL_DIR${NC}"
echo ""
echo -e "${YELLOW}【启动方式】${NC}"
echo -e "1. 启动 Web 浏览器服务 (公网/局域网访问):"
echo -e "   ${CYAN}cd $INSTALL_DIR && ./run.sh --web${NC}"
echo -e "   随后在浏览器访问: ${GREEN}http://<服务器IP>:8000${NC}"
echo ""
echo -e "2. 快速启动 TUI 终端交互面板:"
echo -e "   ${CYAN}cd $INSTALL_DIR && ./run.sh${NC}"
if command -v youtubu &>/dev/null; then
    echo -e "   或者直接在任何地方输入: ${CYAN}youtubu${NC}"
fi
echo ""
echo -e "3. CLI 命令行直接处理视频:"
echo -e "   ${CYAN}./run.sh \"<视频链接>\" --src en --tgt zh${NC}"
echo ""

# 自动启动
echo -e "${YELLOW}-------------------------------------------------------${NC}"
echo -e "部署完毕！将在 5 秒后自动启动 Web 服务（按 Ctrl+C 可取消）..."
sleep 5
info "正在启动 Web 浏览器控制台..."
cd "$INSTALL_DIR"
./run.sh --web


