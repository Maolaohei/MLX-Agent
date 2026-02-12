#!/usr/bin/env python3
"""
MLX-Agent CLI

命令行工具
"""

import asyncio
import sys
from pathlib import Path

import click
from loguru import logger
from rich.console import Console
from rich.panel import Panel

from mlx_agent import MLXAgent, __version__

console = Console()


@click.group()
@click.version_option(version=__version__, prog_name="mlx-agent")
@click.option("--config", "-c", help="配置文件路径")
@click.option("--verbose", "-v", is_flag=True, help="详细输出")
@click.pass_context
def cli(ctx, config, verbose):
    """MLX-Agent - 高性能 AI Agent 系统"""
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config
    
    # 配置日志
    if verbose:
        logger.remove()
        logger.add(sys.stderr, level="DEBUG")
    else:
        logger.remove()
        logger.add(sys.stderr, level="INFO")


@cli.command()
@click.pass_context
def start(ctx):
    """启动 MLX-Agent"""
    config_path = ctx.obj.get("config_path")
    
    console.print(Panel.fit(
        f"🚀 MLX-Agent v{__version__}\n"
        f"高性能、轻量级、多平台 AI Agent",
        title="启动",
        border_style="green"
    ))
    
    try:
        agent = MLXAgent(config_path)
        asyncio.run(agent.start())
    except KeyboardInterrupt:
        console.print("\n[yellow]已停止[/yellow]")
    except Exception as e:
        console.print(f"[red]错误: {e}[/red]")
        raise click.Abort()


@cli.command()
def init():
    """初始化配置"""
    config_path = Path("config/config.yaml")
    
    if config_path.exists():
        console.print(f"[yellow]配置文件已存在: {config_path}[/yellow]")
        if not click.confirm("是否覆盖?"):
            return
    
    # 创建默认配置
    from mlx_agent.config import Config
    config = Config()
    config.save(str(config_path))
    
    console.print(f"[green]✓ 配置文件已创建: {config_path}[/green]")
    console.print("[dim]请编辑配置文件后运行: mlx-agent start[/dim]")


@cli.command()
def status():
    """查看状态"""
    # TODO: 实现状态检查
    console.print("[dim]状态检查功能开发中...[/dim]")


def main():
    """主入口"""
    cli()


if __name__ == "__main__":
    main()
