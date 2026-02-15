#!/usr/bin/env python3
"""
MLX-Agent Phase 2 功能演示 - 简化版
"""

import os
import sys

os.chdir('/root/.openclaw/workspace/MLX-Agent')
sys.path.insert(0, '/root/.openclaw/workspace/MLX-Agent')

from dotenv import load_dotenv
load_dotenv('/root/.openclaw/workspace/MLX-Agent/.env')

print("=" * 60)
print("🚀 MLX-Agent Phase 2 功能演示")
print("=" * 60)

# 1. 基础导入测试
print("\n✅ 1. 基础导入测试")
from mlx_agent import MLXAgent
from mlx_agent.config import Config
from mlx_agent.plugins import PluginManager, Plugin
from mlx_agent.plugins.backup import BackupPlugin
from mlx_agent.plugins.api_manager import APIManagerPlugin
from mlx_agent.plugins.briefing import BriefingPlugin
from mlx_agent.plugins.remindme import RemindmePlugin
print("   所有模块导入成功!")

# 2. 配置系统
print("\n✅ 2. 配置系统")
config = Config.load('config/config.yaml')
print(f"   配置版本: {config.version}")
print(f"   Agent名称: {config.name}")
print(f"   性能优化: uvloop={config.performance.use_uvloop}")

# 3. Agent 初始化
print("\n✅ 3. Agent 初始化")
agent = MLXAgent('config/config.yaml')
print(f"   Agent 实例创建成功")
print(f"   配置版本: {agent.config.version}")

# 4. 插件系统 (Phase 2 核心)
print("\n✅ 4. 插件系统 (Phase 2 核心)")
pm = PluginManager()

# 注册所有插件
backup = BackupPlugin()
api_mgr = APIManagerPlugin()
briefing = BriefingPlugin()
remindme = RemindmePlugin()

pm.register(backup)
pm.register(api_mgr)
pm.register(briefing)
pm.register(remindme)

plugins = pm.list_plugins()
print(f"   已注册插件: {len(plugins)} 个")
for p in plugins:
    plugin = pm.get(p)
    tools = plugin.get_tools()
    print(f"      • {p}: {len(tools)} 个工具")

# 5. 插件工具展示
print("\n✅ 5. 插件工具展示")
all_tools = pm.get_all_tools()
print(f"   总工具数: {len(all_tools)}")
for tool in all_tools:
    name = tool.get('function', {}).get('name', 'unknown')
    desc = tool.get('function', {}).get('description', '')[:40]
    print(f"      • {name}: {desc}...")

# 6. 条件性思考模式 (Phase 2)
print("\n✅ 6. 条件性思考模式 (Phase 2)")
print("   功能: auto_reasoning 参数已集成到 LLM 客户端")
print("   行为: 有工具调用时自动启用思考模式")
print("   代码: llm.chat(..., auto_reasoning=True)")

# 7. 三层记忆架构 (Phase 2)
print("\n✅ 7. 三层记忆架构 (Phase 2)")
print("   热层 (Hot): ChromaDB - 活跃记忆")
print("   温层 (Warm): SQLite - 中期归档")
print("   冷层 (Cold): ChromaDB - 长期存档")
print("   文件: mlx_agent/memory/tiered.py")

# 8. API 管理器状态
print("\n✅ 8. API 管理器")
print(f"   API 配置路径: config/apis.yaml")
print(f"   可用 API: Tavily, Browser.cash, SauceNAO")

# 9. 安装脚本
print("\n✅ 9. 安装脚本 (Phase 2 更新)")
print("   文件: scripts/install.sh")
print("   特性:")
print("      • 插件系统配置")
print("      • 三层记忆架构支持")
print("      • 条件性思考模式")
print("      • 环境变量模板 (.env.example)")

# 10. 快速开始文档
print("\n✅ 10. 文档")
print("   README.md - 项目说明")
print("   QUICKSTART.md - 快速开始指南")
print("   .env.example - 环境变量模板")

# 总结
print("\n" + "=" * 60)
print("✨ MLX-Agent Phase 2 演示完成!")
print("=" * 60)
print("\n核心特性:")
print("   🔌 插件系统 - 4个核心插件已就绪")
print("   🧠 三层记忆架构 - 热/温/冷分层存储")
print("   🤔 条件性思考 - 智能推理模式")
print("   💾 自动备份恢复 - WebDAV支持")
print("   ⏰ 智能提醒系统 - 自然语言解析")
print("   📰 每日晨报 - 定时简报生成")
print("\n下一步:")
print("   1. 编辑 .env 填入 API Key")
print("   2. 运行: python -m mlx_agent start")
print("   3. 或使用: ./scripts/install.sh 安装")
print("\nGitHub: https://github.com/Maolaohei/MLX-Agent")
print("=" * 60)
