# MLX-Agent

[![Status](https://img.shields.io/badge/status-production-green)](https://github.com/Maolaohei/MLX-Agent)
[![Version](https://img.shields.io/badge/version-0.3.0-blue)](https://github.com/Maolaohei/MLX-Agent/releases)
[![Python](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

> 高性能、轻量级、多平台 AI Agent 系统
> 
> **✅ 项目状态：生产就绪 / v0.3.0**

---

## 🚀 核心特性

| 特性 | 说明 | 状态 |
|------|------|------|
| 🧠 智能记忆 | 基于 **ChromaDB** 的向量存储 + 分级记忆 (P0/P1/P2) | ✅ 生产就绪 |
| 🌊 流式输出 | SSE 流式响应，实时显示 AI 思考过程 | ✅ 生产就绪 |
| 💓 健康检查 | HTTP 端点监控，支持 Kubernetes Probes | ✅ 生产就绪 |
| ⚡ 优雅关闭 | SIGTERM 信号处理，有序释放资源 | ✅ 生产就绪 |
| 🔌 双轨 Skill | 原生 Python + OpenClaw 兼容层 | ✅ 生产就绪 |
| 🔄 故障转移 | 主备模型自动切换 (kimi-k2.5 / gemini-3-pro) | ✅ 生产就绪 |
| 💬 多平台 | Telegram 适配器（QQ/Discord 预留） | ✅ 生产就绪 |

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

# 安装依赖
pip install -e ".[telegram,openai]"
```

### 2. 配置环境变量

```bash
export TELEGRAM_BOT_TOKEN="your_bot_token"
export TELEGRAM_ADMIN_ID="your_admin_id"
export OPENAI_API_KEY="your_api_key"
export AUTH_TOKEN="your_auth_token"
```

### 3. 启动服务

```bash
# 开发模式
mlx-agent start

# 或使用 Python 模块
python -m mlx_agent start

# 生产模式（systemd）
systemctl enable mlx-agent
systemctl start mlx-agent
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

## 🛠️ 架构升级 (v0.2.0 → v0.3.0)

### 稳定性改进
- ✅ 优雅关闭：SIGTERM 处理，30秒超时
- ✅ 健康检查：4个 HTTP 端点
- ✅ 错误处理：全局异常捕获，友好错误消息
- ✅ 资源管理：有序关闭，防止内存泄漏

### 功能增强
- ✅ ChromaDB：替换 index1，支持向量搜索
- ✅ 流式输出：SSE 实时响应
- ✅ 分级记忆：P0/P1/P2 自动归档
- ✅ 重试机制：指数退避，最多3次重试

### 配置变更

```yaml
# 新增配置
memory:
  embedding_provider: local  # local/openai/ollama
  chroma_path: ./memory/chroma
  auto_archive:
    enabled: true
    p1_max_age_days: 7
    p2_max_age_days: 1

health_check:
  enabled: true
  port: 8080

shutdown:
  timeout_seconds: 30
```

---

## 📊 性能指标

```
启动时间:      < 2 秒
内存占用:      < 300 MB
优雅关闭:      < 10 秒
流式首字符:    < 100ms
健康检查:      < 10ms
并发用户:      > 50
```

---

## 📁 项目结构

```
mlx-agent/
├── mlx_agent/              # 核心包
│   ├── agent.py           # 主 Agent 类（优雅关闭）
│   ├── health.py          # 健康检查服务器
│   ├── llm.py             # LLM 客户端（流式支持）
│   ├── memory/            # 记忆系统（ChromaDB）
│   ├── platforms/         # 平台适配器
│   │   └── telegram.py    # Telegram（流式输出）
│   ├── skills/            # Skill 系统
│   └── tasks/             # 任务队列系统
├── config/                # 配置文件
│   └── config.yaml
├── systemd/               # 服务配置
│   └── mlx-agent.service
├── memory/                # 记忆存储（gitignore）
└── pyproject.toml         # 项目配置
```

---

## 📝 更新日志

详见 [CHANGELOG.md](CHANGELOG.md)

### v0.3.0 (2026-02-15)
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
