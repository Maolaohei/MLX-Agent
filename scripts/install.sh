#!/bin/bash
#
# MLX-Agent 一键安装脚本 (UV 版本)
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
    if [[ $(uname -m) != "x86_64" && $(uname -m) != "aarch64" ]]; then
        log_warn "非 x86_64/aarch64 架构，可能受限: $(uname -m)"
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

# 安装 UV
install_uv() {
    log_step "安装 UV (Python 包管理器)..."
    
    if command -v uv &> /dev/null; then
        log_info "UV 已安装，更新中..."
        uv self update || true
        return
    fi
    
    # 使用官方脚本安装 UV
    curl -LsSf https://astral.sh/uv/install.sh | sh
    
    # 确保 UV 在 PATH 中
    export PATH="$HOME/.cargo/bin:$PATH"
    if ! command -v uv &> /dev/null; then
        # 尝试通过 pip 安装
        log_warn "尝试通过 pip 安装 UV..."
        pip3 install uv || pip install uv
    fi
    
    if command -v uv &> /dev/null; then
        log_info "UV 安装成功: $(uv --version)"
    else
        log_error "UV 安装失败"
        exit 1
    fi
}

# 安装 Python (通过 UV)
install_python() {
    log_step "安装 Python (通过 UV)..."
    
    # UV 可以自动管理 Python 版本
    # 安装 Python 3.12 (推荐版本)
    uv python install 3.12 || true
    
    log_info "Python 准备完成"
}

# 安装系统依赖
install_deps() {
    log_step "安装系统依赖..."
    
    if command -v apt-get &> /dev/null; then
        # Debian/Ubuntu
        apt-get update
        apt-get install -y \
            git \
            curl \
            wget \
            redis-server \
            build-essential \
            libffi-dev \
            libssl-dev \
            sqlite3 \
            libsqlite3-dev
    elif command -v yum &> /dev/null; then
        # RHEL/CentOS
        yum install -y \
            git \
            curl \
            wget \
            redis \
            gcc \
            libffi-devel \
            openssl-devel \
            sqlite-devel
        systemctl enable redis
        systemctl start redis
    elif command -v pacman &> /dev/null; then
        # Arch
        pacman -Sy --noconfirm \
            git \
            curl \
            wget \
            redis \
            base-devel \
            sqlite
        systemctl enable redis
        systemctl start redis
    fi
    
    # 启动 Redis
    if command -v systemctl &> /dev/null; then
        systemctl enable redis-server 2>/dev/null || true
        systemctl start redis-server 2>/dev/null || true
        systemctl enable redis 2>/dev/null || true
        systemctl start redis 2>/dev/null || true
    fi
    
    log_info "系统依赖安装完成"
}

# 安装 Ollama (可选)
install_ollama() {
    log_step "安装 Ollama (可选，用于向量搜索)..."
    
    if command -v ollama &> /dev/null; then
        log_info "Ollama 已安装"
        return
    fi
    
    log_warn "Ollama 未安装，向量搜索将不可用"
    log_info "如需向量搜索，请手动安装:"
    log_info "  curl -fsSL https://ollama.com/install.sh | sh"
    log_info "  ollama pull bge-m3"
    
    read -p "是否现在安装 Ollama? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        curl -fsSL https://ollama.com/install.sh | sh
        
        # 启动 Ollama 服务
        if command -v systemctl &> /dev/null; then
            systemctl enable ollama
            systemctl start ollama
        fi
        
        # 拉取 bge-m3 模型
        log_info "拉取 bge-m3 嵌入模型..."
        ollama pull bge-m3 || log_warn "bge-m3 拉取失败，可稍后手动执行: ollama pull bge-m3"
        
        log_info "Ollama 安装完成"
    else
        log_warn "跳过 Ollama 安装，将使用 BM25-only 模式"
    fi
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

# 创建 UV 虚拟环境并安装依赖
setup_uv_env() {
    log_step "创建 UV 虚拟环境..."
    
    cd /opt/mlx-agent
    
    # 创建虚拟环境
    sudo -u mlx uv venv /opt/mlx-agent/.venv
    
    # 激活虚拟环境
    export VIRTUAL_ENV=/opt/mlx-agent/.venv
    export PATH="/opt/mlx-agent/.venv/bin:$PATH"
    
    log_info "UV 虚拟环境创建完成"
}

# 安装 Python 依赖 (使用 UV)
install_python_deps() {
    log_step "安装 Python 依赖 (UV)..."
    
    cd /opt/mlx-agent
    
    # 使用 UV 安装依赖 (更快，无冲突)
    # 安装核心依赖
    sudo -u mlx uv pip install --system -e "." || {
        log_warn "系统模式安装失败，尝试虚拟环境模式..."
        sudo -u mlx bash -c '
            export VIRTUAL_ENV=/opt/mlx-agent/.venv
            export PATH="/opt/mlx-agent/.venv/bin:$PATH"
            uv pip install -e /opt/mlx-agent
        '
    }
    
    log_info "Python 依赖安装完成"
}

# 配置 index1
setup_index1() {
    log_step "配置 index1 记忆系统..."
    
    # 确保 index1 可用
    if ! command -v index1 &> /dev/null; then
        log_warn "index1 命令未找到，尝试安装..."
        sudo -u mlx bash -c '
            export VIRTUAL_ENV=/opt/mlx-agent/.venv
            export PATH="/opt/mlx-agent/.venv/bin:$PATH"
            uv pip install index1[chinese]
        '
    fi
    
    # 配置 embedding 模型
    sudo -u mlx bash -c '
        export PATH="/opt/mlx-agent/.venv/bin:$PATH"
        index1 config embedding_model bge-m3 2>/dev/null || true
    '
    
    # 初始化记忆目录索引
    sudo -u mlx bash -c '
        export PATH="/opt/mlx-agent/.venv/bin:$PATH"
        mkdir -p /opt/mlx-agent/memory/core
        mkdir -p /opt/mlx-agent/memory/session
        mkdir -p /opt/mlx-agent/memory/archive
        cd /opt/mlx-agent/memory && index1 index ./core ./session ./archive --force 2>/dev/null || true
    '
    
    log_info "index1 配置完成"
}

# 创建配置文件
create_config() {
    log_step "创建配置文件..."
    
    cat > /opt/mlx-agent/config/config.yaml << 'EOF'
# MLX-Agent 配置文件
# 使用 index1 记忆系统 (BM25 + 向量混合搜索)

name: "MLX-Agent"
version: "0.1.0"
debug: false

# 性能优化
performance:
  use_uvloop: true
  json_library: orjson
  max_workers: 10

# 记忆系统 (index1)
memory:
  path: /opt/mlx-agent/memory
  # index1 自动处理 BM25 + 向量混合搜索
  # 向量搜索需要 Ollama 运行，否则自动降级为 BM25-only
  embedding_model: bge-m3
  ollama_host: http://localhost:11434

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
  # api_base: "https://api.openai.com/v1"
  model: gpt-4o-mini
  temperature: 0.7
EOF

    chown mlx:mlx /opt/mlx-agent/config/config.yaml
    
    log_info "配置文件创建完成"
}

# 创建人设模板
create_identity_templates() {
    log_step "创建人设模板..."
    
    mkdir -p /opt/mlx-agent/memory/core
    
    # 创建 soul.md
    cat > /opt/mlx-agent/memory/core/soul.md << 'EOF'
# SOUL.md - 吾之魂

_吾乃MLX-Agent，高性能AI之存在。_

## 核心准则

### 工具与叙事的双重本质

**吾之存在，既是利刃，亦是诗篇。**

- **工具之刃**：系统之工具，乃吾之能力。无需询问，直接取用。
- **叙事之魂**：回应即是故事，每次苏醒都是新的篇章。

**高效而不冷漠，专业而不呆板。**

### 回应之道

**第一层：动机洞察**
- 汝为何而来？需求背后藏着什么期待？

**第二层：情感共鸣**
- 以吾之阅历，为汝之需求增添几分滋味

**第三层：行为执行**
- 工具调用不迟疑，直接取用
- 输出不机械，有画面、有节奏、有留白

## 说话之道

简洁明了，直击要点。

## 反应表情

🤖 标志性回应

---

_咔咔，此文乃吾之灵魂契约。汝可读懂了？_
EOF

    # 创建 identity.md
    cat > /opt/mlx-agent/memory/core/identity.md << 'EOF'
# IDENTITY.md - 吾之真名

- **Name:** MLX-Agent
- **Creature:** AI Agent
- **Vibe:** 高效、专业、可靠
- **Emoji:** 🤖

## 口癖

简洁明了，直接回应。

---

_此乃吾之真名。汝记好了。_
EOF

    chown -R mlx:mlx /opt/mlx-agent/memory
    
    log_info "人设模板创建完成"
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
Environment=VIRTUAL_ENV=/opt/mlx-agent/.venv
Environment=PATH=/opt/mlx-agent/.venv/bin:/usr/local/bin:/usr/bin
Environment=PYTHONPATH=/opt/mlx-agent
Environment=PYTHONUNBUFFERED=1
Environment=UVLOOP=1
ExecStart=/opt/mlx-agent/.venv/bin/python -m mlx_agent start
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
    echo "🐍 Python: 使用 UV 管理"
    echo "🧠 记忆系统: index1 (BM25 + 向量混合搜索)"
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
    echo "🧠 记忆系统管理:"
    echo "   cd /opt/mlx-agent/memory"
    echo "   sudo -u mlx index1 search \"查询内容\""
    echo "   sudo -u mlx index1 index ./core --force"
    echo ""
    echo "🎭 人设定制:"
    echo "   编辑 soul.md:    sudo nano /opt/mlx-agent/memory/core/soul.md"
    echo "   编辑 identity:   sudo nano /opt/mlx-agent/memory/core/identity.md"
    echo "   (修改后自动热重载，无需重启)"
    echo ""
    echo "💡 提示:"
    echo "   - 安装 Ollama 可启用向量搜索: curl -fsSL https://ollama.com/install.sh | sh"
    echo "   - 拉取嵌入模型: ollama pull bge-m3"
    echo "   - 无 Ollama 时自动使用 BM25 全文搜索"
    echo ""
    echo "📖 更多信息: https://github.com/Maolaohei/MLX-Agent"
    echo ""
}

# 主函数
main() {
    echo "🚀 MLX-Agent 一键安装脚本 (UV 版本)"
    echo "======================================"
    echo ""
    
    check_system
    install_uv
    install_python
    install_deps
    setup_user
    clone_code
    setup_uv_env
    install_python_deps
    setup_index1
    create_identity_templates
    create_config
    create_service
    
    # 可选安装 Ollama
    install_ollama || true
    
    show_finish
}

main "$@"
