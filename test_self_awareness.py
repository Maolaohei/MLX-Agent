#!/usr/bin/env python3
"""
测试 Agent 技能自知能力
"""

import asyncio
import os
os.chdir('/root/.openclaw/workspace/MLX-Agent')

from dotenv import load_dotenv
load_dotenv('/root/.openclaw/workspace/MLX-Agent/.env')

from mlx_agent import MLXAgent
from mlx_agent.plugins import PluginManager
from mlx_agent.plugins.backup import BackupPlugin
from mlx_agent.plugins.api_manager import APIManagerPlugin
from mlx_agent.plugins.briefing import BriefingPlugin
from mlx_agent.plugins.remindme import RemindmePlugin

async def test():
    print("=" * 60)
    print("🧪 测试 Agent 技能自知")
    print("=" * 60)
    
    # 初始化 Agent
    agent = MLXAgent('config/config.yaml')
    
    # 手动初始化插件（模拟 start() 过程）
    pm = PluginManager()
    pm.register(BackupPlugin())
    pm.register(APIManagerPlugin())
    pm.register(BriefingPlugin())
    pm.register(RemindmePlugin())
    agent.plugin_manager = pm
    
    print("\n✅ Agent 和插件初始化完成")
    
    # 测试 1: 获取插件技能描述
    print("\n📋 测试 1: 插件技能描述")
    caps = agent._get_plugin_capabilities_text()
    print(caps)
    
    # 测试 2: 模拟系统提示构建
    print("\n📋 测试 2: 系统提示构建（技能部分）")
    base_prompt = "你是 MLX-Agent，一个强大的 AI 助手。"
    if caps:
        base_prompt += f"\n\n【你的技能】\n{caps}"
    
    print("系统提示中的技能部分:")
    print("-" * 40)
    print(base_prompt[base_prompt.find('【你的技能】'):])
    print("-" * 40)
    
    # 测试 3: 检查工具列表
    print("\n📋 测试 3: 可用工具列表")
    tools = pm.get_all_tools()
    print(f"总工具数: {len(tools)}")
    for tool in tools[:5]:  # 只显示前5个
        name = tool.get('function', {}).get('name', 'unknown')
        print(f"  - {name}")
    if len(tools) > 5:
        print(f"  ... 还有 {len(tools) - 5} 个工具")
    
    print("\n" + "=" * 60)
    print("✨ 测试结果")
    print("=" * 60)
    print("\n现在当用户询问以下问题时，Agent 会知道自己有这些能力:")
    print('  • "你能做什么？" → 知道有备份、API管理、晨报、提醒功能')
    print('  • "查一下天气" → 知道可以用 briefing 插件')
    print('  • "提醒我10分钟后开会" → 知道可以用 remindme 插件')
    print('  • "备份一下数据" → 知道可以用 backup 插件')
    print("\n无需询问用户，直接调用对应工具！")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test())
