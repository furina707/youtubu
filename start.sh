#!/usr/bin/env bash
# ==============================================================================
# youtubu Linux / macOS 一键自动部署与启动入口
# ==============================================================================

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}========================================================${NC}"
echo -e "${BLUE}          youtubu 跨平台自动检测与启动中心            ${NC}"
echo -e "${BLUE}========================================================${NC}"
echo ""

# 1. 自动检测环境是否已部署
if [ ! -f "$SCRIPT_DIR/venv/bin/python" ]; then
    echo -e "${YELLOW}[检测] 未检测到虚拟环境，正在自动执行一键安装部署...${NC}"
    echo ""
    bash "$SCRIPT_DIR/install.sh"
    exit 0
fi

# 2. 如果已安装，提供启动模式选择
echo -e "${GREEN}[检测] 系统环境已就绪！${NC}"
echo ""
echo -e "请选择运行模式 (5秒无操作将默认启动 [1] Web 模式):"
echo -e "--------------------------------------------------------"
echo -e " [1] 启动 Web 浏览器服务 (局域网/公网可访问: 8000 端口)"
echo -e " [2] 启动 Web 服务 + Cloudflare 公网穿透 (生成外网访问链接)"
echo -e " [3] 启动 TUI 终端交互控制台"
echo -e " [4] 重新执行一键安装部署"
echo -e "--------------------------------------------------------"
echo ""

read -t 5 -p "请输入选项 [1-4] (默认 1): " choice || choice="1"
choice=${choice:-1}

case "$choice" in
    1)
        echo -e "${CYAN}正在启动 Web 浏览器服务...${NC}"
        ./run.sh --web
        ;;
    2)
        echo -e "${CYAN}正在启动 Web 服务与 Cloudflare 隧道...${NC}"
        if ! command -v cloudflared &>/dev/null; then
            echo -e "${YELLOW}未检测到 cloudflared 命令，请先安装：${NC}"
            echo -e "curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb && sudo dpkg -i cloudflared.deb"
            exit 1
        fi
        ./run.sh --web &
        sleep 3
        cloudflared tunnel --url http://localhost:8000
        ;;
    3)
        ./run.sh
        ;;
    4)
        bash "$SCRIPT_DIR/install.sh"
        ;;
    *)
        ./run.sh --web
        ;;
esac
