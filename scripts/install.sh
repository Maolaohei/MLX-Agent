#!/bin/bash
#
# MLX-Agent 一键安装脚本
# 
# 使用方法:
#   curl -fsSL https://raw.githubusercontent.com/Maolaohei/MLX-Agent/main/scripts/install.sh | sudo bash
#

set -e

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 日志函数
log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step() { echo -e "${BLUE}[STEP]${NC} $1"; }

# 检查系统
check_system() {
    log_step "检查系统环境..."
    
    # 检查架构
    if [[ $(uname -m) != "x86_64" ]]; then
        log_error "仅支持 x86_64 架构"
        exit 1
    fi
    
    # 检查 Linux
    if [[ ! -f /etc/os-release ]]; then
        log_error "无法识别操作系统"
        exit 1
    fi
    
    source /etc/os-release
    log_info "系统: $NAME $VERSION_ID"
    
    # 检查是否有 sudo
    if [[ $EUID -ne 0 ]]; then
        log_error "请使用 sudo 运行此脚本"
        exit 1
    fi
}

# 安装 Python 3.13
install_python() {
    log_step "安装 Python 3.13..."
    
    if command -v python3.13 &> /dev/null; then
        log_info "Python 3.13 已安装"
        return
    fi
    
    if [[ -f /etc/debian_version ]]; then
        # Debian/Ubuntu
        apt-get update
        apt-get install -y software-properties-common
        add-apt-repository -y ppa:deadsnakes/ppa
        apt-get update
        apt-get install -y python3.13 python3.13-venv python3.13-dev
    else
        log_error "不支持的操作系统，请手动安装 Python 3.13"
        exit 1
    fi
    
    log_info "Python 3.13 安装完成"
}

# 安装系统依赖
install_deps() {
    log_step "安装系统依赖..."
    
    apt-get install -y \
        git \
        curl \
        wget \
        redis-server \
        build-essential \
        libffi-dev \
        libssl-dev
    
    # 启动 Redis
    systemctl enable redis-server
    systemctl start redis-server
    
    log_info "系统依赖安装完成"
}

# 创建用户和目录
setup_user() {
    log_step "创建 mlx 用户..."
    
    if ! id -u mlx &>/dev/null; then
        useradd -r -s /bin/bash -m -d /opt/mlx-agent mlx
        log_info "创建用户 mlx"
    else
        log_info "用户 mlx 已存在"
    fi
    
    # 创建目录
    mkdir -p /opt/mlx-agent/{memory,skills,config,logs}
    chown -R mlx:mlx /opt/mlx-agent
}

# 克隆代码
clone_code() {
    log_step "下载 MLX-Agent..."
    
    if [[ -d /opt/mlx-agent/.git ]]; then
        log_info "代码已存在，更新中..."
        cd /opt/mlx-agent
        sudo -u mlx git pull
    else
        sudo -u mlx git clone https://github.com/Maolaohei/MLX-Agent.git /tmp/mlx-agent-tmp
        sudo -u mlx cp -r /tmp/mlx-agent-tmp/* /opt/mlx-agent/
        rm -rf /tmp/mlx-agent-tmp
    fi
    
    log_info "代码下载完成"
}

# 创建虚拟环境
setup_venv() {
    log_step "创建 Python 虚拟环境..."
    
    sudo -u mlx python3.13 -m venv /opt/mlx-agent/venv
    source /opt/mlx-agent/venv/bin/activate
    
    # 升级 pip
    pip install --upgrade pip wheel setuptools
    
    log_info "虚拟环境创建完成"
}

# 安装依赖
install_python_deps() {
    log_step "安装 Python 依赖..."
    
    source /opt/mlx-agent/venv/bin/activate
    
    # 安装核心依赖
    pip install \
        uvloop \
        orjson \
        aiohttp \
        aiofiles \
        pydantic \
        pydantic-settings \
        pyyaml \
        loguru \
        redis \
        asyncpg \
        pymilvus \
        httpx \
        click \
        rich \
        python-telegram-bot
    
    log_info "Python 依赖安装完成"
}

# 创建配置文件
create_config() {
    log_step "创建配置文件..."
    
    cat > /opt/mlx-agent/config/config.yaml << 'EOF'
# MLX-Agent 配置文件

name: "MLX-Agent"
version: "0.1.0"
debug: false

# 性能优化
performance:
  use_uvloop: true
  json_library: orjson
  max_workers: 10

# 记忆系统
memory:
  path: /opt/mlx-agent/memory
  vector_db: milvus  # 或 zilliz
  vector_db_host: localhost
  vector_db_port: 19530
  collection_name: mlx_memories

# 平台配置
platforms:
  telegram:
    enabled: false
    # bot_token: "YOUR_BOT_TOKEN_HERE"
    
  qqbot:
    enabled: false
    
  discord:
    enabled: false

# LLM 配置
llm:
  provider: openai
  # api_key: "YOUR_API_KEY_HERE"
  model: gpt-4o-mini
  temperature: 0.7
EOF

    chown mlx:mlx /opt/mlx-agent/config/config.yaml
    
    log_info "配置文件创建完成"
}

# 创建 systemd 服务
create_service() {
    log_step "创建系统服务..."
    
    cat > /etc/systemd/system/mlx-agent.service << 'EOF'
[Unit]
Description=MLX-Agent AI Assistant
After=network.target redis-server.service

[Service]
Type=simple
User=mlx
Group=mlx
WorkingDirectory=/opt/mlx-agent
Environment=PATH=/opt/mlx-agent/venv/bin:/usr/local/bin
Environment=PYTHONPATH=/opt/mlx-agent
Environment=PYTHONUNBUFFERED=1
Environment=UVLOOP=1
ExecStart=/opt/mlx-agent/venv/bin/python -m mlx_agent start
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=mlx-agent

# 性能优化
OOMScoreAdjust=-100
Nice=-5

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable mlx-agent
    
    log_info "系统服务创建完成"
}

# 显示完成信息
show_finish() {
    echo ""
    echo "======================================"
    echo -e "${GREEN}✅ MLX-Agent 安装完成！${NC}"
    echo "======================================"
    echo ""
    echo "📂 安装目录: /opt/mlx-agent"
    echo "⚙️  配置文件: /opt/mlx-agent/config/config.yaml"
    echo ""
    echo "🚀 使用方法:"
    echo "   1. 编辑配置文件:"
    echo "      sudo nano /opt/mlx-agent/config/config.yaml"
    echo ""
    echo "   2. 启动服务:"
    echo "      sudo systemctl start mlx-agent"
    echo ""
    echo "   3. 查看状态:"
    echo "      sudo systemctl status mlx-agent"
    echo ""
    echo "   4. 查看日志:"
    echo "      sudo journalctl -u mlx-agent -f"
    echo ""
    echo "📖 更多信息: https://github.com/Maolaohei/MLX-Agent"
    echo ""
}

# 主函数
main() {
    echo "🚀 MLX-Agent 一键安装脚本"
    echo "=========================="
    echo ""
    
    check_system
    install_python
    install_deps
    setup_user
    clone_code
    setup_venv
    install_python_deps
    create_config
    create_service
    
    show_finish
}

main "$@"
