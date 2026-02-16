# MLX-Agent 停止维护

[![Status](https://img.shields.io/badge/status-production-green)](https://github.com/Maolaohei/MLX-Agent)
[![Version](https://img.shields.io/badge/version-0.4.0-blue)](https://github.com/Maolaohei/MLX-Agent/releases)
[![Python](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

> 高性能、轻量级、多平台 AI Agent 系统
> 
> **✅ 项目状态：生产就绪 / v0.4.0**

---

## 🚀 核心特性

| 特性 | 说明 | 状态 |
|------|------|------|
| 🧠 智能记忆 | 基于 **ChromaDB** 的向量存储 + 分级记忆 (P0/P1/P2) + 自动归档 | ✅ 生产就绪 |
| 🔍 多源搜索 | **Tavily** / **Brave** / DuckDuckGo 搜索 provider | ✅ 生产就绪 |
| 📁 大文件传输 | 分片上传/下载，支持断点续传 | ✅ 生产就绪 |
| 🌐 反爬浏览器 | Playwright + Stealth 配置，绕过反爬检测 | ✅ 生产就绪 |
| ✅ 配置验证 | Pydantic 配置验证 + 自动修复 | ✅ 生产就绪 |
| 🌊 流式输出 | SSE 流式响应，实时显示 AI 思考过程 | ✅ 生产就绪 |
| 💓 健康检查 | HTTP 端点监控，支持 Kubernetes Probes | ✅ 生产就绪 |
| ⚡ 优雅关闭 | SIGTERM 信号处理，有序释放资源 | ✅ 生产就绪 |
| 🔌 双轨 Skill | 原生 Python + OpenClaw 兼容层 | ✅ 生产就绪 |
| 🔄 故障转移 | 主备模型自动切换 (kimi-k2.5 / gemini-3-pro) | ✅ 生产就绪 |
| 💬 多平台 | Telegram 适配器（QQ/Discord 预留） | ✅ 生产就绪 |
| 🔧 **插件系统** | **Phase 2: 热插拔插件 + 4 个核心插件** | 🎉 **新增** |
| 🧊 **三层记忆** | **Hot/Warm/Cold 分层存储架构** | 🎉 **新增** |
| 🧩 **条件思考** | **auto_reasoning 智能切换推理模式** | 🎉 **新增** |

---

## 🆕 Phase 2 新特性

### 🧩 插件系统 (Plugin System)

MLX-Agent v0.4.0 引入热插拔插件架构，支持动态加载、配置驱动的功能扩展。

#### 核心插件列表

| 插件名 | 功能 | 状态 |
|--------|------|------|
| **backup-restore** | 自动备份、WebDAV 同步、定时任务调度 | ✅ 已集成 |
| **api-manager** | API 密钥加密存储、自动轮换、权限管理 | ✅ 已集成 |
| **daily-briefing** | 每日晨报生成、天气查询、系统状态报告 | ✅ 已集成 |
| **remindme** | 自然语言提醒解析、定时调度、循环提醒 | ✅ 已集成 |

#### 插件特性

```yaml
# 插件配置示例
plugins:
  backup-restore:
    enabled: true
    schedule: "0 2 * * *"      # 每天凌晨2点备份
    webdav_url: ${WEBDAV_URL}
    retention_days: 7
  
  api-manager:
    enabled: true
    encryption_key: ${API_ENC_KEY}
    rotation_days: 30
  
  daily-briefing:
    enabled: true
    schedule: "0 8 * * *"      # 每天早上8点
    weather_city: "Shanghai"
    include_system_stats: true
  
  remindme:
    enabled: true
    max_reminders: 100
    default_snooze: 10m
```

#### 快速使用插件

```bash
# 查看所有插件
/plugins list

# 启用/禁用插件
/plugin enable backup-restore
/plugin disable remindme

# 触发每日晨报
/dailybriefing

# 设置提醒
/remindme "明天下午3点开会"
/remindme "每周末备份数据"
```

📚 **插件开发指南**: [docs/PLUGIN_GUIDE.md](docs/PLUGIN_GUIDE.md)

---

### 🧊 三层记忆架构 (Tiered Memory)

Phase 2 引入 Hot/Warm/Cold 三层存储架构，优化存储效率和检索性能。

```
┌─────────────────────────────────────────────────────────────────┐
│                         三层记忆架构                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  🔥 Hot Layer (热层)                                            │
│  ├── 存储: ChromaDB (内存优化)                                   │
│  ├── 内容: P0 + 7天内P1 + 1天内P2                               │
│  └── 特性: 毫秒级检索，活跃数据常驻                               │
│                              ↓                                  │
│  🌡️ Warm Layer (温层)                                           │
│  ├── 存储: SQLite (轻量索引)                                     │
│  ├── 内容: 7-30天的P1记忆                                       │
│  └── 特性: 关键词搜索，中期归档                                   │
│                              ↓                                  │
│  🧊 Cold Layer (冷层)                                           │
│  ├── 存储: ChromaDB (压缩存储)                                   │
│  ├── 内容: 30天+ P1/P2 长期存档                                 │
│  └── 特性: 深度语义检索，低频访问                                 │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

#### 配置方法

```yaml
memory:
  provider: tiered  # 启用三层架构
  
  tiered:
    hot_path: ./memory/hot
    warm_path: ./memory/warm.db
    cold_path: ./memory/cold
    embedding_provider: local
    auto_tiering: true          # 自动分层归档
    hot_warm_threshold: 7       # 7天后移到温层
    warm_cold_threshold: 30     # 30天后移到冷层
    p2_archive_days: 1          # P2 1天后归档
```

---

### 🧩 条件性思考模式 (Conditional Reasoning)

`auto_reasoning` 参数启用后，系统会根据上下文自动决定是否使用推理模式。

```yaml
llm:
  auto_reasoning: true  # 启用条件思考
```

#### 自动触发推理的场景

| 场景 | 示例 | 模式 |
|------|------|------|
| 工具调用 | "搜索最新新闻" | 🧠 推理模式 |
| 复杂分析 | "为什么代码这么慢？" | 🧠 推理模式 |
| 数学计算 | "计算 1234 * 5678" | 🧠 推理模式 |
| 日常对话 | "你好" | ⚡ 标准模式 |
| 简单确认 | "好的" | ⚡ 标准模式 |

---

## 📦 快速开始

### 1. 安装依赖

```bash
# 克隆仓库
git clone https://github.com/Maolaohei/MLX-Agent.git
cd MLX-Agent

# 创建虚拟环境
python3.13 -m venv .venv
source .venv/bin/activate

# 安装依赖 (含插件支持)
pip install -e ".[telegram,openai,plugins]"
```

### 2. 配置环境变量

```bash
# 必需配置
export TELEGRAM_BOT_TOKEN="your_bot_token"
export TELEGRAM_ADMIN_ID="your_admin_id"
export OPENAI_API_KEY="your_api_key"
export AUTH_TOKEN="your_auth_token"

# 插件配置 (可选)
export WEBDAV_URL="https://your-webdav-server"
export API_ENC_KEY="your-encryption-key"
```

### 3. 配置插件 (可选)

编辑 `config/config.yaml`，启用需要的插件：

```yaml
plugins:
  backup-restore:
    enabled: true
    schedule: "0 2 * * *"
  daily-briefing:
    enabled: true
    schedule: "0 8 * * *"
  remindme:
    enabled: true
```

### 4. 启动服务

```bash
# 开发模式
mlx-agent start

# 或使用 Python 模块
python -m mlx_agent start

# 生产模式（systemd）
systemctl enable mlx-agent
systemctl start mlx-agent
```

### 5. 快速测试

```bash
# 基础健康检查
curl http://localhost:8080/health

# Telegram 交互
/plugins list              # 查看插件
/dailybriefing             # 生成晨报
/remindme "10分钟后喝水"    # 设置提醒
```

---

## 🏥 健康检查

服务启动后，健康检查端点可用：

```bash
# 基础健康状态
curl http://localhost:8080/health

# 就绪检查（Kubernetes readinessProbe）
curl http://localhost:8080/health/ready

# 存活检查（Kubernetes livenessProbe）
curl http://localhost:8080/health/live

# 详细指标
curl http://localhost:8080/health/metrics

# 插件状态
curl http://localhost:8080/health/plugins
```

### Kubernetes 配置示例

```yaml
livenessProbe:
  httpGet:
    path: /health/live
    port: 8080
  initialDelaySeconds: 30
  periodSeconds: 10

readinessProbe:
  httpGet:
    path: /health/ready
    port: 8080
  initialDelaySeconds: 5
  periodSeconds: 5
```

---

## 🧠 记忆系统

### 分级记忆架构

```
P0 (核心记忆)    - 永不删除，手动管理
  └── 用户偏好、重要人物信息

P1 (会话记忆)    - 7天自动归档
  └── 对话上下文、学习到的信息

P2 (临时记忆)    - 24小时自动清理
  └── 工具执行结果、临时数据
```

### 三层存储架构 (Phase 2)

| 层级 | 存储 | 内容 | 保留时间 |
|------|------|------|----------|
| 🔥 Hot | ChromaDB | 活跃记忆 | P0 + 7天P1 + 1天P2 |
| 🌡️ Warm | SQLite | 中期归档 | 7-30天P1 |
| 🧊 Cold | ChromaDB | 长期存档 | 30天+ P1/P2 |

### 配置嵌入模型

```yaml
memory:
  embedding_provider: local  # local, openai, ollama
  embedding_model: BAAI/bge-m3
```

---

## 🌊 流式输出

长消息（>100字符）会自动使用流式输出：

1. 先显示 "⏳ 正在思考..."
2. AI 内容实时显示
3. 支持打字状态同步

### 手动启用流式

```python
async for chunk in agent.handle_message_stream(
    platform="telegram",
    user_id="123456",
    text="很长的查询内容..."
):
    print(chunk, end="")
```

---

## 🛠️ 架构升级

### v0.3.0 → v0.4.0 (Phase 2)

#### 新增功能
- ✅ **插件系统**: 热插拔架构，4个核心插件
- ✅ **三层记忆**: Hot/Warm/Cold 分层存储
- ✅ **条件思考**: auto_reasoning 智能模式切换

#### 插件配置

```yaml
plugins:
  backup-restore:
    enabled: true
    schedule: "0 2 * * *"
    webdav_url: ${WEBDAV_URL}
  api-manager:
    enabled: true
    rotation_days: 30
  daily-briefing:
    enabled: true
    schedule: "0 8 * * *"
  remindme:
    enabled: true
    max_reminders: 100
```

### v0.2.0 → v0.3.0 (Phase 1)

#### 稳定性改进
- ✅ 优雅关闭：SIGTERM 处理，30秒超时
- ✅ 健康检查：4个 HTTP 端点
- ✅ 错误处理：全局异常捕获，友好错误消息
- ✅ 资源管理：有序关闭，防止内存泄漏

#### 功能增强
- ✅ ChromaDB：替换 index1，支持向量搜索
- ✅ 流式输出：SSE 实时响应
- ✅ 分级记忆：P0/P1/P2 自动归档
- ✅ 重试机制：指数退避，最多3次重试

---

## 📊 性能指标

```
启动时间:      < 2 秒
内存占用:      < 300 MB
优雅关闭:      < 10 秒
流式首字符:    < 100ms
健康检查:      < 10ms
并发用户:      > 50
插件加载:      < 500ms
```

---

## 📁 项目结构

```
mlx-agent/
├── mlx_agent/              # 核心包
│   ├── agent.py           # 主 Agent 类
│   ├── health.py          # 健康检查服务器
│   ├── llm.py             # LLM 客户端
│   ├── memory/            # 记忆系统 (三层架构)
│   ├── platforms/         # 平台适配器
│   ├── skills/            # Skill 系统
│   ├── tasks/             # 任务队列
│   └── plugins/           # 插件系统 (Phase 2)
│       ├── backup_restore.py
│       ├── api_manager.py
│       ├── daily_briefing.py
│       └── remindme.py
├── config/                # 配置文件
│   └── config.yaml
├── docs/                  # 文档
│   └── PLUGIN_GUIDE.md    # 插件开发指南
├── systemd/               # 服务配置
│   └── mlx-agent.service
├── memory/                # 记忆存储（gitignore）
└── pyproject.toml         # 项目配置
```

---

## 📝 更新日志

详见 [CHANGELOG.md](CHANGELOG.md)

### v0.4.0 (2026-02-15) - Phase 2
- 🎉 **插件系统**: 热插拔插件架构
- 🔧 **4个核心插件**: backup-restore, api-manager, daily-briefing, remindme
- 🧊 **三层记忆**: Hot/Warm/Cold 分层存储
- 🧩 **条件思考**: auto_reasoning 智能模式切换

### v0.3.0 (2026-02-15) - Phase 1
- 🎉 生产就绪版本
- 🌊 流式输出支持
- 🧠 ChromaDB 记忆系统
- 💓 健康检查端点
- ⚡ 优雅关闭机制

### v0.2.0 (2026-02-13)
- 核心架构完成
- 多轮对话历史
- 混合检索系统
- 故障转移支持

---

## 🤝 贡献

欢迎贡献代码、提交 Issue 或建议！

## 📄 许可

MIT License

---

*Designed by 忍野忍 (Shinobu Oshino)* 🍩🦇
