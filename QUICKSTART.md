# MLX-Agent 快速开始指南

欢迎使用 MLX-Agent! 本指南将帮助你在几分钟内启动并运行。

## 📋 目录

- [系统要求](#系统要求)
- [安装](#安装)
- [配置](#配置)
- [启动](#启动)
- [基本使用](#基本使用)
- [常见问题](#常见问题)

---

## 🖥️ 系统要求

- **操作系统**: Linux (Ubuntu 20.04+, Debian 11+, CentOS 8+)
- **架构**: x86_64 或 aarch64
- **内存**: 最小 512MB，推荐 2GB+
- **Python**: 3.10 或更高版本 (脚本会自动安装)
- **Redis**: 用于缓存和消息队列

---

## 🚀 安装

### 方式一: 一键安装脚本 (推荐)

```bash
# 使用 curl 下载并运行安装脚本
curl -fsSL https://raw.githubusercontent.com/Maolaohei/MLX-Agent/main/scripts/install.sh | sudo bash
```

安装脚本会自动完成:
- 安装 UV (Python 包管理器)
- 安装 Python 3.12
- 安装系统依赖 (Redis 等)
- 创建 mlx 用户
- 下载 MLX-Agent 代码
- 创建虚拟环境并安装依赖
- 创建配置文件和人设模板
- 创建系统服务

### 方式二: 手动安装

```bash
# 1. 克隆仓库
git clone https://github.com/Maolaohei/MLX-Agent.git
cd MLX-Agent

# 2. 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 3. 安装依赖
pip install -e "."

# 4. 复制配置模板
cp config/config.yaml.example config/config.yaml
cp .env.example .env
```

---

## ⚙️ 配置

### 1. 配置环境变量

```bash
# 复制环境变量模板
sudo cp /opt/mlx-agent/.env.example /opt/mlx-agent/.env

# 编辑环境变量
sudo nano /opt/mlx-agent/.env
```

**必需配置:**

```env
# OpenAI API Key (必需)
OPENAI_API_KEY=sk-your-api-key-here

# Telegram Bot (可选，如使用 Telegram)
TELEGRAM_BOT_TOKEN=your-bot-token
TELEGRAM_ADMIN_ID=your-user-id
```

### 2. 编辑主配置文件

```bash
sudo nano /opt/mlx-agent/config/config.yaml
```

**关键配置项:**

```yaml
# 记忆系统后端选择
memory:
  provider: hybrid  # 可选: chroma | sqlite | hybrid | tiered

# Telegram 平台
platforms:
  telegram:
    enabled: true
    bot_token: ${TELEGRAM_BOT_TOKEN}
    admin_user_id: ${TELEGRAM_ADMIN_ID}

# LLM 配置
llm:
  primary:
    provider: openai
    api_key: ${OPENAI_API_KEY}
    model: gpt-4o-mini
```

### 3. 配置人设 (可选)

编辑人设文件来自定义 Agent 的性格:

```bash
# 编辑灵魂文件
sudo nano /opt/mlx-agent/memory/core/soul.md

# 编辑身份信息
sudo nano /opt/mlx-agent/memory/core/identity.md
```

---

## 🏃 启动

### 使用系统服务 (推荐)

```bash
# 启动服务
sudo systemctl start mlx-agent

# 查看状态
sudo systemctl status mlx-agent

# 查看日志
sudo journalctl -u mlx-agent -f

# 设置开机自启
sudo systemctl enable mlx-agent

# 停止服务
sudo systemctl stop mlx-agent

# 重启服务
sudo systemctl restart mlx-agent
```

### 手动运行

```bash
cd /opt/mlx-agent
source .venv/bin/activate
python -m mlx_agent start
```

---

## 💬 基本使用

### Telegram 机器人

1. 在 Telegram 中搜索你的 Bot
2. 发送 `/start` 开始对话
3. 直接发送消息即可与 Agent 聊天

### 可用命令

- `/start` - 开始对话
- `/help` - 显示帮助
- `/status` - 查看系统状态
- `/memory` - 记忆管理

### 插件使用示例

#### 智能提醒
```
提醒我明天下午3点开会
提醒我每周五晚上健身
```

#### 每日晨报
```
# 自动每天早上8点发送晨报
# 包含天气、系统状态、今日任务
```

---

## 🔌 Phase 2 新特性

### 插件系统

MLX-Agent 支持热插拔插件:

```bash
# 查看可用插件
ls /opt/mlx-agent/mlx_agent/plugins/

# 启用插件
# 编辑 config/config.yaml，设置 plugins.plugin_name.enabled: true
```

### 三层记忆架构

自动分层存储记忆:
- **热层 (0-7天)**: 活跃记忆，快速访问
- **温层 (7-30天)**: 中期归档，关键词搜索
- **冷层 (30天+)**: 长期存档，深度检索

配置方式:
```yaml
memory:
  provider: tiered
  tiered:
    hot_path: ./memory/hot
    warm_path: ./memory/warm.db
    cold_path: ./memory/cold
    auto_tiering: true
```

### 条件性思考模式

自动在以下场景启用深度推理:
- 工具调用
- 复杂分析
- 数学计算
- 代码调试

---

## 🛠️ 故障排除

### 服务无法启动

```bash
# 检查日志
sudo journalctl -u mlx-agent -n 50

# 检查配置文件语法
python3 -c "import yaml; yaml.safe_load(open('/opt/mlx-agent/config/config.yaml'))"

# 检查环境变量
cat /opt/mlx-agent/.env
```

### 记忆系统问题

```bash
# 重新初始化记忆系统
cd /opt/mlx-agent/memory
sudo -u mlx index1 index ./core ./session --force

# 检查记忆统计
sudo -u mlx python -c "from mlx_agent.memory import create_memory_backend; ..."
```

### API 连接问题

```bash
# 测试 API 连接
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

---

## 📚 更多信息

- [完整文档](https://github.com/Maolaohei/MLX-Agent/tree/main/docs)
- [API 参考](https://github.com/Maolaohei/MLX-Agent/blob/main/docs/api.md)
- [插件开发指南](https://github.com/Maolaohei/MLX-Agent/blob/main/docs/plugin-development.md)
- [更新日志](https://github.com/Maolaohei/MLX-Agent/blob/main/CHANGELOG.md)

---

## 🤝 获取帮助

- **GitHub Issues**: https://github.com/Maolaohei/MLX-Agent/issues
- **Discussions**: https://github.com/Maolaohei/MLX-Agent/discussions

---

**祝你使用愉快!** 🤖
