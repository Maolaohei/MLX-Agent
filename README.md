# MLX-Agent（施工中，不可用）

> 高性能、轻量级、多平台 AI Agent 系统
> 
> 核心理念：简而不凡，快而稳定

## 🎯 项目定位

**MLX-Agent** 是一个面向中文用户的高性能 AI Agent 系统，采用 **"核心自研 + 兼容复用"** 的双轨架构：

- **核心功能**（Python 3.13+）：记忆系统、多平台适配、任务调度
- **兼容生态**（OpenClaw 技能）：通过兼容层复用 6000+ 现有技能

## 🚀 核心特性

| 特性 | 说明 | 状态 |
|------|------|------|
| 🧠 智能记忆 | 基于 **index1** 的 BM25 + 向量混合搜索 | ✅ Phase 1 |
| 🔌 双轨 Skill | 原生 Python + OpenClaw 兼容层 | ✅ Phase 1 |
| ⚡ 高性能 | Python 3.13 + uvloop + orjson | ✅ Phase 1 |
| 💬 多平台 | Telegram、QQBot、Discord | 🚧 Phase 2 |
| 🐧 平台支持 | Linux x86_64 | ✅ |
| 📦 便捷部署 | 裸机 + systemd，一键安装 | ✅ Phase 1 |

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
| 缓存 | Redis |
| 部署 | 裸机 + systemd |

## 📁 项目结构

```
mlx-agent/
├── mlx_agent/              # 核心包
│   ├── __init__.py
│   ├── agent.py           # 主 Agent 类
│   ├── gateway.py         # 网关服务
│   ├── memory/            # 记忆系统
│   ├── skills/            # Skill 系统
│   │   ├── native/        # 原生 Python 技能
│   │   └── compat/        # OpenClaw 兼容层
│   ├── llm/               # LLM 路由
│   ├── platforms/         # 平台适配器
│   └── utils/             # 工具函数
├── skills/                 # 默认 Skills
├── config/                 # 配置
├── scripts/                # 脚本
│   └── install.sh         # 一键安装
├── docs/                   # 文档
├── tests/                  # 测试
└── pyproject.toml         # 项目配置
```

## 🚀 快速开始

### 一键安装

```bash
curl -fsSL https://raw.githubusercontent.com/Maolaohei/MLX-Agent/main/scripts/install.sh | sudo bash
```

### 手动安装 (UV 推荐)

```bash
# 1. 克隆仓库
git clone https://github.com/Maolaohei/MLX-Agent.git
cd MLX-Agent

# 2. 安装 UV (如果尚未安装)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 3. 创建虚拟环境并安装依赖
uv venv
uv pip install -e ".[all]"

# 4. 配置 index1 记忆系统
uv run index1 config embedding_model bge-m3

# 5. 配置
mkdir -p config
cp config/config.example.yaml config/config.yaml
# 编辑 config/config.yaml

# 6. 启动
uv run python -m mlx_agent
```

### 使用传统 pip

```bash
pip install -e ".[all]"
python -m mlx_agent
```

## 📝 开发计划

### Phase 1: 核心框架 (当前)
- [x] 项目脚手架
- [x] 记忆系统实现 (index1 + BM25/向量混合)
- [ ] Skill 系统（含兼容层）
- [ ] Telegram 适配器
- [x] 一键安装脚本 (UV 版本)

### Phase 2: 多平台支持
- [ ] QQ Bot 适配器
- [ ] Discord 适配器
- [ ] 多线程优化

### Phase 3: 生态完善
- [ ] 文档完善
- [ ] 官方 Skills
- [ ] 社区建设

## 🤝 贡献

欢迎贡献代码、提交 Issue 或建议！

## 📄 许可

MIT License

---

*Designed by 忍野忍 (Shinobu Oshino)* 🍩
