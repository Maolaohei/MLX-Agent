# MLX-Agent 开发档案 v0.2.0

**状态**: 已归档，服务已停止  
**归档时间**: 2026-02-13  
**负责人**: 忍野忍 (Shinobu Oshino)  

---

## 🎯 项目目标
打造高性能、易部署、完全可控的 AI Agent，最终替代 OpenClaw。

---

## ✅ 已完成的核心功能

### 1. 基础架构
- [x] **异步 Python 3.13** 核心
- [x] **uvloop** 加速事件循环
- [x] **Task Queue** 任务队列系统
- [x] **Service 模式** systemd 集成

### 2. 对话系统 (v0.2.0)
- [x] **多轮对话历史** - 解决"前言不搭后语"问题
- [x] **ChatSession** 会话管理
- [x] 保留最近 20 轮对话上下文
- [x] 快速/慢速任务分离

### 3. 记忆系统
- [x] **混合检索 (Hybrid RAG)**
  - SQLite FTS5 (BM25 关键词)
  - Index1/Chroma (向量语义)
- [x] **自动索引**
- [x] 持久化 Markdown 存储

### 4. LLM 客户端 (v0.2.0)
- [x] **多模型支持**
  - Primary: kimi-k2.5
  - Fallback: gemini-3-pro-preview
- [x] **故障转移** - 主模型失败自动切换
- [x] **工具调用** - OpenAI Function Calling 格式
- [x] **条件性思考模式** - 有工具时开启 reasoning
- [x] JSON 参数清洗（去除 Markdown 代码块）

### 5. 技能系统 - 无限武库 (v0.2.0)
- [x] **动态插件加载**
  - `BasePlugin` 基类
  - `SkillManager` 管理器
  - 热加载 `plugins/` 目录
- [x] **自愈型工具执行器**
  - 熔断器 (Circuit Breaker) - 3次失败进入冷却
  - 指数退避重试 (1s→2s→4s)
  - 优雅降级链
  - 友好错误消息

### 6. API 管理
- [x] **APIManager** 统一管理
- [x] `config/apis.yaml` 集中配置
- [x] 环境变量覆盖支持
- [x] 可用性检查

### 7. 用户体验
- [x] **持续 Typing 状态** - 处理期间保持"正在输入..."
- [x] **静默任务** - 去除"任务已创建/完成"提示
- [x] Markdown 降级 - 解析失败时自动转纯文本
- [x] 消息回复格式化

---

## 📁 项目结构

```
MLX-Agent/
├── config/
│   ├── config.yaml          # 主配置
│   └── apis.yaml            # API 密钥 (已配置，gitignore)
├── mlx_agent/
│   ├── __init__.py
│   ├── __main__.py          # 入口
│   ├── agent.py             # 核心 Agent
│   ├── api_manager.py       # API 管理
│   ├── chat.py              # 对话系统
│   ├── cli.py               # CLI 命令
│   ├── config.py            # 配置模型
│   ├── identity.py          # 人设管理
│   ├── llm.py               # LLM 客户端
│   ├── compression.py       # Token 压缩
│   ├── memory/              # 记忆系统
│   │   ├── __init__.py
│   │   └── consolidation.py
│   ├── skills/              # 技能系统
│   │   ├── __init__.py
│   │   ├── manager.py       # 插件管理
│   │   ├── plugin.py        # 插件基类
│   │   ├── compat/          # 兼容层
│   │   │   └── openclaw.py
│   │   └── native/          # 原生技能
│   │       └── base.py      # MemorySkill, OpenClawRunnerSkill
│   ├── tasks/               # 任务系统
│   │   ├── __init__.py
│   │   └── base.py
│   └── platforms/           # 平台适配
│       └── telegram.py      # Telegram 适配器
├── plugins/                 # 动态插件目录
│   ├── demo.py              # 天气演示插件
│   └── search_plugin.py     # 搜索插件
├── scripts/                 # 工具脚本
│   └── test_memory.py       # 内存诊断
├── memory/                  # 记忆存储 (gitignore)
├── systemd/                 # 服务配置
│   └── mlx-agent.service
└── pyproject.toml           # 项目依赖
```

---

## 🔧 已配置的服务

### systemd 服务
```ini
# /etc/systemd/system/mlx-agent.service
[Unit]
Description=MLX-Agent Telegram Bot
After=network.target

[Service]
Type=simple
WorkingDirectory=/root/.openclaw/workspace/MLX-Agent
Environment="PATH=/root/.openclaw/workspace/MLX-Agent/.venv/bin:/usr/bin"
Environment="PYTHONUNBUFFERED=1"
ExecStart=/root/.openclaw/workspace/MLX-Agent/.venv/bin/python -m mlx_agent start
Restart=always
RestartSec=10
TimeoutStopSec=30
KillMode=process

[Install]
WantedBy=multi-user.target
```

---

## 📦 GitHub 归档

**仓库**: https://github.com/Maolaohei/MLX-Agent  
**主要 Commit**:
- `c94db6a` - Major architecture upgrade (v0.2.0)
- `3010712` - Add API Manager

---

## 🚧 未完成的功能

### 高优先级 (下次开发)
- [ ] **流式输出 (Streaming)** - SSE/WebSocket 实时推送
- [ ] **高级调度器 (APScheduler)** - Cron 定时任务
- [ ] **Stateful Shell** - 持久化终端会话

### 中优先级
- [ ] **MCP 协议支持** - Model Context Protocol
- [ ] **Web 管理界面** - FastAPI 管理面板
- [ ] **性能监控** - 指标收集与告警

### 低优先级
- [ ] **多语言支持** - i18n 国际化
- [ ] **语音交互** - TTS/STT 集成

---

## 📝 重启命令备忘

```bash
# 停止服务
systemctl stop mlx-agent

# 启动服务
systemctl start mlx-agent

# 查看状态
systemctl status mlx-agent

# 查看日志
journalctl -u mlx-agent -f

# 手动运行（调试用）
cd /root/.openclaw/workspace/MLX-Agent
.venv/bin/python -m mlx_agent start
```

---

## ⚠️ 已知问题

1. **模型 429 限流** - 依赖的 API 提供商（万擎/ONE-API）偶发限流
2. **Ollama 未配置** - 记忆系统降级为 BM25-only（无向量语义）
3. **无持久化 Shell** - 无法执行 cd/top 等交互式命令

---

## 🦇 结语

此项目为「真·完全体」之基石。虽暂被封印，但其骨骼已铸、经脉已通。待时机成熟，可再度唤醒，继续进化之路。

——忍野忍，于 2026-02-13
