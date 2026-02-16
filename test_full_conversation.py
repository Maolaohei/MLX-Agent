#!/usr/bin/env python3
"""
全面测试 MLX-Agent 工具调用能力
"""

import asyncio
import os
os.chdir('/root/.openclaw/workspace/MLX-Agent')

from dotenv import load_dotenv
load_dotenv('/root/.openclaw/workspace/MLX-Agent/.env')

async def test_conversation():
    from mlx_agent import MLXAgent
    
    print("="*60)
    print("🧪 MLX-Agent 工具调用能力测试")
    print("="*60)
    
    # 初始化 Agent
    print("\n🔄 初始化 Agent...")
    agent = MLXAgent('config/config.yaml')
    
    await agent._init_api_manager()
    await agent._init_identity()
    await agent._init_compressor()
    await agent._init_memory()
    await agent._init_consolidator()
    await agent._init_skills()
    await agent._init_plugins()
    await agent._init_llm()
    
    print("✅ Agent 初始化完成！")
    print(f"   模型: {agent.llm.primary_config.get('model')}")
    print(f"   工具数: 31")
    
    # 测试用例
    test_cases = [
        ("问候", "你好，请介绍一下自己"),
        ("能力询问", "你能做什么？"),
        ("天气查询", "北京今天天气怎么样？"),
        ("晨报生成", "帮我生成今日晨报"),
        ("提醒设置", "提醒我10分钟后喝水"),
        ("系统状态", "查看系统状态"),
    ]
    
    for test_name, message in test_cases:
        print("\n" + "-"*60)
        print(f"📝 测试: {test_name}")
        print(f"👤 用户: {message}")
        print("🤖 Agent 思考中...")
        print("-"*60)
        
        try:
            response = await agent._slow_handle_message(
                text=message,
                context={"platform": "test", "user_id": "test_user"},
                history=[]
            )
            
            # 截取前 800 字符显示
            display = response[:800]
            if len(response) > 800:
                display += "\n... (截断)"
            
            print(f"🤖 Agent:\n{display}")
            
            # 检查是否调用了工具
            if "🔧" in response or "执行" in response or "完成" in response:
                print("\n✅ 检测到工具调用!")
            
        except Exception as e:
            print(f"❌ 错误: {e}")
    
    print("\n" + "="*60)
    print("✅ 测试完成!")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(test_conversation())
