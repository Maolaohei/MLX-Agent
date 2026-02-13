# MLX-Agent

[![Status](https://img.shields.io/badge/status-archived-lightgrey)](https://github.com/Maolaohei/MLX-Agent/blob/main/ARCHIVE.md)
[![Version](https://img.shields.io/badge/version-0.2.0-blue)](https://github.com/Maolaohei/MLX-Agent/releases)
[![Python](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

> 高性能、轻量级、多平台 AI Agent 系统
> 
> **⚠️ 项目状态：已归档 / 开发暂停**
> 
> 当前版本 v0.2.0 已完成核心架构，服务已停止。可随时唤醒继续开发。

---

## 📦 归档说明

本项目已暂停开发并归档。如需查看详细开发记录，请参阅 [ARCHIVE.md](ARCHIVE.md)。

### 已完成的核心功能 ✅

- **多轮对话历史** - 20轮上下文记忆
- **混合检索系统** - SQLite + BM25 + 向量语义
- **LLM 故障转移** - kimi-k2.5 / gemini-3-pro 双模型
- **条件性思考模式** - 有工具时自动开启 reasoning
- **动态技能系统** - 热加载插件（无限武库）
- **自愈型工具执行器** - 熔断器 + 重试 + 优雅降级
- **API 统一管理** - 集中式密钥管理
- **持续 Typing 状态** - 处理期间保持输入指示

### 唤醒方式 🚀

```bash
# 克隆仓库
git clone https://github.com/Maolaohei/MLX-Agent.git
cd MLX-Agent

# 启动服务
systemctl enable mlx-agent
systemctl start mlx-agent
```

---

## 🎯 项目定位（历史）

**MLX-Agent** 是一个面向中文用户的高性能 AI Agent 系统，采用 **"核心自研 + 兼容复用"** 的双轨架构：

- **核心功能**（Python 3.13+）：记忆系统、多平台适配、任务调度
- **兼容生态**（OpenClaw 技能）：通过兼容层复用现有技能

## 🚀 核心特性

| 特性 | 说明 | 状态 |
|------|------|------|
| 🧠 智能记忆 | 基于 **index1** 的 BM25 + 向量混合搜索 | ✅ 已完成 |
| 🔌 双轨 Skill | 原生 Python + OpenClaw 兼容层 | ✅ 已完成 |
| ⚡ 高性能 | Python 3.13 + uvloop + orjson | ✅ 已完成 |
| 💬 多平台 | Telegram 适配器 | ✅ 已完成 |
| 🐧 平台支持 | Linux x86_64 | ✅ 已完成 |
| 📦 便捷部署 | 裸机 + systemd，一键安装 | ✅ 已完成 |

## 📊 性能指标

```
启动时间: < 2 秒
内存占用: < 256 MB
并发用户: > 50
代码行数: < 10,000 行（核心）
```

## 🛠️ 技术栈

| 组件 | 技术选择 |
|------|----------|
| 语言 | Python 3.13+ |
| 异步 | uvloop + asyncio |
| JSON | orjson |
| 记忆系统 | index1 (BM25 + bge-m3 混合搜索) |
| 部署 | 裸机 + systemd |
| 配置 | Pydantic + YAML |

## 📁 项目结构

```
mlx-agent/
├── mlx_agent/              # 核心包
│   ├── agent.py           # 主 Agent 类
│   ├── api_manager.py     # API 密钥管理
│   ├── chat.py            # 对话系统（多轮历史）
│   ├── llm.py             # LLM 客户端（故障转移）
│   ├── memory/            # 记忆系统（混合检索）
│   ├── skills/            # Skill 系统
│   │   ├── manager.py     # 插件管理器（热加载）
│   │   ├── plugin.py      # 插件基类
│   │   ├── compat/        # OpenClaw 兼容层
│   │   └── native/        # 原生 Python 技能
│   ├── platforms/         # 平台适配器
│   │   └── telegram.py    # Telegram 适配
│   └── tasks/             # 任务队列系统
├── plugins/               # 动态插件目录
├── config/                # 配置文件
├── scripts/               # 工具脚本
├── ARCHIVE.md             # 📋 开发档案
└── pyproject.toml         # 项目配置
```

## 📝 开发计划

### Phase 1: 核心框架 ✅ 已完成
- [x] 项目脚手架
- [x] 记忆系统实现 (index1 + BM25/向量混合)
- [x] Skill 系统（含兼容层）
- [x] Telegram 适配器
- [x] 一键安装脚本

### Phase 2: 增强功能 ⏸️ 待开发
- [ ] 流式输出 (Streaming SSE/WebSocket)
- [ ] 高级调度器 (APScheduler Cron)
- [ ] Stateful Shell (持久化终端)
- [ ] QQ Bot / Discord 适配器

### Phase 3: 生态完善 ⏸️ 待开发
- [ ] Web 管理界面
- [ ] 性能监控
- [ ] 官方 Skills 扩展

## 📄 文档

- [ARCHIVE.md](ARCHIVE.md) - 详细开发档案
- [SKILL.md](skills/api-manager/SKILL.md) - API 管理器文档

## 🤝 贡献

欢迎贡献代码、提交 Issue 或建议！

## 📄 许可

MIT License

---

*Designed by 忍野忍 (Shinobu Oshino)* 🍩🦇
