#!/usr/bin/env python3
"""
与重启后的 MLX-Agent 对话测试
"""

import asyncio
import os
os.chdir('/root/.openclaw/workspace/MLX-Agent')

from dotenv import load_dotenv
load_dotenv('/root/.openclaw/workspace/MLX-Agent/.env')

from rich.console import Console
from rich.panel import Panel
from rich import box

console = Console()

async def chat_test():
    console.print(Panel.fit(
        "🚀 与重启后的 MLX-Agent 对话测试\n"
        "测试她是否知道自己的技能",
        border_style="green"
    ))
    
    from mlx_agent import MLXAgent
    
    # 初始化 Agent
    console.print("\n[dim]初始化 Agent...[/dim]")
    agent = MLXAgent('config/config.yaml')
    
    # 初始化所有组件（模拟完整启动）
    console.print("[dim]初始化组件...[/dim]")
    await agent._init_api_manager()
    await agent._init_identity()
    await agent._init_compressor()
    await agent._init_memory()
    await agent._init_consolidator()
    await agent._init_skills()
    await agent._init_plugins()
    await agent._init_llm()
    
    console.print("[green]✅ Agent 准备就绪！[/green]\n")
    
    # 测试对话
    test_messages = [
        "你好，请介绍一下你自己",
        "你能做什么？",
        "帮我查一下天气",
        "提醒我10分钟后喝水",
    ]
    
    for msg in test_messages:
        console.print(Panel(
            f"[bold cyan]👤 用户:[/bold cyan] {msg}",
            box=box.ROUNDED,
            border_style="cyan"
        ))
        
        try:
            # 获取系统提示（调试用）
            base_prompt = "你是 MLX-Agent，一个强大的 AI 助手。"
            caps = agent._get_plugin_capabilities_text()
            if caps:
                base_prompt += f"\n\n【你的技能】\n{caps}"
            
            # 调用对话
            response = await agent.handle_message("test", "user123", msg)
            
            console.print(Panel(
                f"[bold green]🤖 Agent:[/bold green] {response[:500]}{'...' if len(response) > 500 else ''}",
                box=box.ROUNDED,
                border_style="green"
            ))
            console.print()
            
        except Exception as e:
            console.print(Panel(
                f"[bold red]❌ 错误:[/bold red] {e}",
                box=box.ROUNDED,
                border_style="red"
            ))
    
    # 显示系统提示中的技能部分
    console.print("\n" + "="*60)
    console.print("[bold]系统提示中的技能说明（调试用）:[/bold]")
    console.print("="*60)
    if caps:
        console.print(caps)
    console.print("="*60)

if __name__ == "__main__":
    asyncio.run(chat_test())
