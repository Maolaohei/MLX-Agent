# MLX-Agent 项目归档说明

## 📅 归档日期
2026-02-16

## 🏷️ 版本状态
- **版本**: v0.4.0
- **状态**: Production Ready → **Archived**
- **GitHub**: https://github.com/Maolaohei/MLX-Agent

## ✅ 归档前完成的工作

### 功能迁移
- [x] bilibili-downloader → BilibiliPlugin (5 tools)
- [x] pixiv-skill → PixivPlugin (5 tools)
- [x] anilist → AniListPlugin (6 tools)
- [x] pdf → PDFPlugin (6 tools)
- [x] excel → ExcelPlugin (6 tools)

### 最终统计
- 总插件数: 13个
- 总工具数: ~48个
- 代码行数: < 10,000行 (核心)

### 推送记录
```
commit 21b8b0e
feat: archive version - migrate 5 OpenClaw skills to plugins
```

## 📦 核心成果

### 插件系统架构
MLX-Agent 的插件系统实现了：
- 热插拔插件加载
- OpenAI Function Calling 兼容
- 自动依赖安装
- 配置驱动启用/禁用

### 记忆系统设计
- Markdown-first 存储
- 三层分级 (P0/P1/P2)
- SHA-256 去重
- ChromaDB 向量索引

## 🔄 重启方法

如需重新启用：

```bash
# 克隆仓库
git clone https://github.com/Maolaohei/MLX-Agent.git
cd MLX-Agent

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入配置

# 启动服务
python -m mlx_agent start
# 或
systemctl start mlx-agent
```

## 📝 设计遗产

详见: `memory/mlx-memory-design.md`

主要理念：
1. Markdown-first, Git-friendly 记忆系统
2. 双轨 Skill 架构（原生 + 兼容层）
3. 三层记忆分级 (Hot/Warm/Cold)
4. 异步高性能架构

## 🙏 致谢

感谢在开发过程中提供的支持和测试。

---

*项目已归档，但代码永存。*
*"简而不凡，快而稳定" —— MLX-Agent 设计理念*

**Archived by**: 忍野忍 (Shinobu Oshino) 🦇🍩
