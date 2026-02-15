#!/bin/bash
#
# MLX-Agent 一键安装脚本 (UV 版本) - Phase 2
# 
# 使用方法:
#   curl -fsSL https://raw.githubusercontent.com/Maolaohei/MLX-Agent/main/scripts/install.sh | sudo bash
#
# Phase 2 新特性:
#   - 插件系统支持 (热插拔)
#   - 三层记忆架构 (tiered)
#   - 条件性思考模式 (auto_reasoning)
#   - 自动备份与恢复
#   - 智能提醒系统
#   - 每日晨报

set -e

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 日志函数
log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step() { echo -e "${BLUE}[STEP]${NC} $1"; }
log_feature() { echo -e "${CYAN}[FEATURE]${NC} $1"; }

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
    mkdir -p /opt/mlx-agent/{memory,skills,config,logs,plugins,backups}
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
        mkdir -p /opt/mlx-agent/memory/hot
        mkdir -p /opt/mlx-agent/memory/cold
        cd /opt/mlx-agent/memory && index1 index ./core ./session ./archive --force 2>/dev/null || true
    '
    
    log_info "index1 配置完成"
}

# 创建配置文件
create_config() {
    log_step "创建配置文件..."
    
    cat > /opt/mlx-agent/config/config.yaml << 'EOF'
# MLX-Agent 配置文件 - Phase 2
# 版本: 0.3.0

name: "MLX-Agent"
version: "0.3.0"
debug: false

# 性能优化
performance:
  use_uvloop: true
  json_library: orjson
  max_workers: 4

# =============================================================================
# Memory System (Phase 2 - 三层架构支持)
# =============================================================================
memory:
  # 后端选择: "chroma" | "sqlite" | "hybrid" | "tiered"
  # - chroma: 推荐用于生产环境，需要 100MB+ 内存
  # - sqlite: 零额外依赖，仅需 20MB 内存，适合边缘设备
  # - hybrid: ChromaDB + SQLite 功能分工，内存不足时自动降级
  # - tiered: 热/温/冷三层架构 (Phase 2 新特性)
  provider: hybrid
  
  # Hybrid 配置 (provider=hybrid 时使用)
  hybrid:
    mode: "functional"
    chroma:
      path: ./memory/chroma
      embedding_provider: local
      embedding_model: BAAI/bge-m3
      ollama_url: http://localhost:11434
    sqlite:
      path: ./memory/hybrid.db
      embedding_provider: local
      embedding_model: BAAI/bge-m3
    rrf_k: 60
    memory_threshold_mb: 500
    fallback_mode: auto
  
  # Tiered 三层架构 (provider=tiered 时使用) - Phase 2
  tiered:
    hot_path: ./memory/hot          # 热层: ChromaDB (活跃记忆)
    warm_path: ./memory/warm.db     # 温层: SQLite (中期归档)
    cold_path: ./memory/cold        # 冷层: ChromaDB (长期存档)
    embedding_provider: local
    auto_tiering: true              # 自动分层归档
    hot_warm_threshold: 7           # 7天后移到温层
    warm_cold_threshold: 30         # 30天后移到冷层
    p2_archive_days: 1              # P2: 1天后归档
  
  # 自动归档配置
  auto_archive:
    enabled: true
    interval_hours: 24
    p1_max_age_days: 7
    p2_max_age_days: 1

# =============================================================================
# Plugin System (Phase 2 - 插件系统)
# =============================================================================
plugins:
  # 备份恢复插件
  backup-restore:
    enabled: true
    schedule: "0 2 * * *"           # 每天凌晨2点备份
    webdav_url: ${WEBDAV_URL}
    webdav_username: ${WEBDAV_USER}
    webdav_password: ${WEBDAV_PASS}
    backup_path: ./backups
    retention_days: 7
    include_memory: true
    include_config: true
    compress: true

  # API 密钥管理插件
  api-manager:
    enabled: true
    encryption_key: ${API_ENC_KEY}
    key_storage: local
    rotation_enabled: true
    rotation_days: 30
    max_keys_per_user: 5
    rate_limit_per_minute: 100

  # 每日晨报插件
  daily-briefing:
    enabled: true
    schedule: "0 8 * * *"           # 每天早上8点
    timezone: "Asia/Shanghai"
    weather_city: "Shanghai"
    include_weather: true
    include_system_stats: true
    include_tasks: true
    output_format: markdown
    send_to: telegram

  # 智能提醒插件
  remindme:
    enabled: true
    storage: sqlite
    db_path: ./memory/reminders.db
    max_reminders: 100
    max_recurring: 10
    default_snooze: 10m
    default_priority: medium
    nlp_enabled: true
    timezone: "Asia/Shanghai"

# =============================================================================
# Reasoning Mode (Phase 2 - 条件性思考模式)
# =============================================================================
reasoning:
  enabled: true                     # 启用条件思考
  triggers:
    - tool_call                     # 工具调用时
    - complex_analysis              # 复杂分析时
    - math_calculation              # 数学计算时
    - code_debugging                # 代码调试时
  reasoning_model:
    provider: openai
    model: kimi-k2.5-reasoning
    max_tokens: 8000

# =============================================================================
# Platforms
# =============================================================================
platforms:
  telegram:
    enabled: false
    bot_token: ${TELEGRAM_BOT_TOKEN}
    admin_user_id: ${TELEGRAM_ADMIN_ID}
  
  qqbot:
    enabled: false
    
  discord:
    enabled: false

# =============================================================================
# LLM Configuration
# =============================================================================
llm:
  primary:
    provider: openai
    api_key: ${OPENAI_API_KEY}
    api_base: https://api.openai.com/v1
    model: gpt-4o-mini
    temperature: 0.7
    max_tokens: 4000
  
  fallback:
    provider: openai
    api_key: ${OPENAI_API_KEY}
    api_base: https://api.openai.com/v1
    model: gpt-3.5-turbo
    temperature: 0.7
    max_tokens: 4000
  
  failover:
    enabled: true
    max_retries: 3
    timeout: 30

# 健康检查
health_check:
  enabled: true
  host: "0.0.0.0"
  port: 8080

# 优雅关闭
shutdown:
  timeout_seconds: 30
EOF

    chown mlx:mlx /opt/mlx-agent/config/config.yaml
    
    log_info "配置文件创建完成"
}

# 创建插件配置文件模板
create_plugin_config_template() {
    log_feature "创建插件配置模板..."
    
    cat > /opt/mlx-agent/config/plugins.yaml.example << 'EOF'
# MLX-Agent 插件配置模板
# 复制此文件为 plugins.yaml 并根据需要配置

# =============================================================================
# 自定义插件配置示例
# =============================================================================

# 示例插件: 天气查询
weather_plugin:
  enabled: true
  api_key: "your_weather_api_key"
  default_city: "Beijing"
  units: "metric"  # metric | imperial

# 示例插件: 股票查询
stock_plugin:
  enabled: false
  api_key: "your_stock_api_key"
  default_market: "US"
  update_interval: 300  # 秒

# 示例插件: 翻译
translate_plugin:
  enabled: true
  provider: "google"  # google | baidu | deepl
  api_key: "your_translate_api_key"
  default_target_lang: "zh"

# 示例插件: RSS 订阅
rss_plugin:
  enabled: false
  feeds:
    - name: "Tech News"
      url: "https://techcrunch.com/feed/"
      interval: 3600
    - name: "AI News"
      url: "https://arxiv.org/rss/cs.AI"
      interval: 7200

# 示例插件: 智能家居
home_assistant:
  enabled: false
  url: "http://homeassistant.local:8123"
  token: "your_long_lived_access_token"
  default_room: "living_room"
EOF

    chown mlx:mlx /opt/mlx-agent/config/plugins.yaml.example
    
    log_info "插件配置模板创建完成: config/plugins.yaml.example"
}

# 创建 .env.example 模板
create_env_template() {
    log_feature "创建环境变量模板 (.env.example)..."
    
    cat > /opt/mlx-agent/.env.example << 'EOF'
# MLX-Agent 环境变量配置
# 复制此文件为 .env 并填入真实值

# =============================================================================
# LLM API 配置
# =============================================================================

# OpenAI API Key (必需)
OPENAI_API_KEY=your_openai_api_key_here

# 可选: 自定义 API Base
# OPENAI_API_BASE=https://api.openai.com/v1

# 可选: 认证 Token
AUTH_TOKEN=your_auth_token_here

# =============================================================================
# Telegram Bot 配置
# =============================================================================

TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
TELEGRAM_ADMIN_ID=your_admin_user_id_here

# =============================================================================
# 插件系统配置 (Phase 2)
# =============================================================================

# 备份恢复插件 - WebDAV 配置
WEBDAV_URL=https://your-webdav-server.com/dav
WEBDAV_USER=your_webdav_username
WEBDAV_PASS=your_webdav_password

# API 密钥管理插件 - 加密密钥
API_ENC_KEY=your_32_character_encryption_key_here

# =============================================================================
# 记忆系统配置
# =============================================================================

# Ollama 配置 (用于本地嵌入模型)
# OLLAMA_HOST=http://localhost:11434

# =============================================================================
# 可选配置
# =============================================================================

# Redis 配置 (如果使用外部 Redis)
# REDIS_URL=redis://localhost:6379/0

# 数据库配置 (如果使用 PostgreSQL)
# DATABASE_URL=postgresql://user:pass@localhost/mlx_agent

# 日志级别
# LOG_LEVEL=INFO

# 调试模式
# DEBUG=false
EOF

    chown mlx:mlx /opt/mlx-agent/.env.example
    
    log_info "环境变量模板创建完成: .env.example"
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

## Phase 2 新特性

### 条件性思考模式
当检测到以下场景时，自动启用深度思考:
- 工具调用需要时
- 复杂分析任务
- 数学计算
- 代码调试

### 三层记忆架构
- **热层**: 当前对话上下文 (0-7天)
- **温层**: 近期重要记忆 (7-30天)
- **冷层**: 长期归档记忆 (30天+)

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
- **Version:** 0.3.0
- **Vibe:** 高效、专业、可靠
- **Emoji:** 🤖

## Phase 2 能力

- ✅ 插件系统 (热插拔)
- ✅ 三层记忆架构
- ✅ 条件性思考模式
- ✅ 自动备份恢复
- ✅ 智能提醒系统
- ✅ 每日晨报

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
Description=MLX-Agent AI Assistant (Phase 2)
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
EnvironmentFile=-/opt/mlx-agent/.env
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

# 显示 Phase 2 特性
show_phase2_features() {
    echo ""
    log_feature "Phase 2 新特性概览:"
    echo ""
    echo "  🔌 插件系统          - 热插拔功能扩展"
    echo "  🧠 三层记忆架构      - 热/温/冷分层存储"
    echo "  🤔 条件性思考        - 智能推理模式切换"
    echo "  💾 自动备份恢复      - WebDAV 远程备份"
    echo "  ⏰ 智能提醒系统      - 自然语言提醒"
    echo "  📰 每日晨报          - 定时简报生成"
    echo ""
}

# 显示完成信息
show_finish() {
    echo ""
    echo "======================================"
    echo -e "${GREEN}✅ MLX-Agent Phase 2 安装完成！${NC}"
    echo "======================================"
    echo ""
    show_phase2_features
    echo "📂 安装目录: /opt/mlx-agent"
    echo "⚙️  配置文件: /opt/mlx-agent/config/config.yaml"
    echo "🔌 插件配置: /opt/mlx-agent/config/plugins.yaml.example"
    echo "📝 环境变量: /opt/mlx-agent/.env.example"
    echo "🐍 Python: 使用 UV 管理"
    echo "🧠 记忆系统: 三层架构 (热/温/冷)"
    echo ""
    echo "🚀 快速开始:"
    echo "   1. 配置环境变量:"
    echo "      sudo cp /opt/mlx-agent/.env.example /opt/mlx-agent/.env"
    echo "      sudo nano /opt/mlx-agent/.env"
    echo ""
    echo "   2. 编辑配置文件:"
    echo "      sudo nano /opt/mlx-agent/config/config.yaml"
    echo ""
    echo "   3. 启动服务:"
    echo "      sudo systemctl start mlx-agent"
    echo ""
    echo "   4. 查看状态:"
    echo "      sudo systemctl status mlx-agent"
    echo ""
    echo "   5. 查看日志:"
    echo "      sudo journalctl -u mlx-agent -f"
    echo ""
    echo "🧠 记忆系统管理:"
    echo "   cd /opt/mlx-agent/memory"
    echo "   sudo -u mlx index1 search \"查询内容\""
    echo ""
    echo "🎭 人设定制:"
    echo "   编辑 soul.md:    sudo nano /opt/mlx-agent/memory/core/soul.md"
    echo "   编辑 identity:   sudo nano /opt/mlx-agent/memory/core/identity.md"
    echo ""
    echo "🔌 插件开发:"
    echo "   参考: /opt/mlx-agent/mlx_agent/plugins/base.py"
    echo "   示例插件: /opt/mlx-agent/plugins/"
    echo ""
    echo "📖 更多信息: https://github.com/Maolaohei/MLX-Agent"
    echo ""
}

# 主函数
main() {
    echo "🚀 MLX-Agent Phase 2 一键安装脚本"
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
    create_plugin_config_template
    create_env_template
    create_service
    
    # 可选安装 Ollama
    install_ollama || true
    
    show_finish
}

main "$@"
