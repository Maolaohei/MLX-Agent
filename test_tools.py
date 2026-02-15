#!/usr/bin/env python3
"""
测试 MLX-Agent 的工具调用功能
直接使用 _slow_handle_message，绕过 chat_manager
"""

import asyncio
import os
os.chdir('/root/.openclaw/workspace/MLX-Agent')

from dotenv import load_dotenv
load_dotenv('/root/.openclaw/workspace/MLX-Agent/.env')

print("=" * 60)
print("🧪 测试 MLX-Agent 工具调用")
print("=" * 60)

from mlx_agent import MLXAgent

async def test():
    agent = MLXAgent('config/config.yaml')
    
    # 初始化组件
    print("\n🔄 初始化组件...")
    await agent._init_api_manager()
    await agent._init_identity()
    await agent._init_compressor()
    await agent._init_memory()
    await agent._init_consolidator()
    await agent._init_skills()
    await agent._init_plugins()
    await agent._init_llm()
    print("✅ 组件初始化完成")
    
    # 显示系统提示中的技能说明
    print("\n" + "=" * 60)
    print("📋 系统提示中的技能说明:")
    print("=" * 60)
    caps = agent._get_plugin_capabilities_text()
    print(caps)
    print("=" * 60)
    
    # 测试直接调用 _slow_handle_message
    print("\n📝 测试对话（直接使用 _slow_handle_message）:")
    print("-" * 60)
    
    test_messages = [
        "你能做什么？",
        "帮我生成今日晨报",
        "成都天气怎么样？",
        "提醒我10分钟后喝水",
    ]
    
    for msg in test_messages:
        print(f"\n👤 用户: {msg}")
        print("🤖 Agent 思考中...")
        
        try:
            # 直接调用 _slow_handle_message
            response = await agent._slow_handle_message(
                text=msg,
                context={"platform": "test", "user_id": "user123"},
                history=[]
            )
            
            print(f"🤖 Agent: {response[:300]}{'...' if len(response) > 300 else ''}")
            
        except Exception as e:
            print(f"❌ 错误: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("✅ 测试完成")
    print("=" * 60)

asyncio.run(test())
