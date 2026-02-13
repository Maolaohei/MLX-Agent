import asyncio
import sys
import os
from pathlib import Path

# 添加项目根目录到 path
sys.path.insert(0, str(Path.cwd()))

from loguru import logger
from mlx_agent.config import Config
from mlx_agent.memory import MemorySystem

async def main():
    # 强制添加 index1 路径
    venv_bin = Path("/root/.openclaw/workspace/MLX-Agent/.venv/bin")
    if str(venv_bin) not in os.environ["PATH"]:
        os.environ["PATH"] = str(venv_bin) + os.pathsep + os.environ["PATH"]
        
    logger.info(f"PATH: {os.environ['PATH']}")
    logger.info("开始记忆系统诊断...")
    
    # 1. 加载配置
    config = Config.load()
    logger.info(f"配置加载完成: {config.memory.path}")
    
    # 2. 初始化记忆系统
    memory = MemorySystem(config.memory)
    try:
        await memory.initialize()
        logger.info("MemorySystem 初始化成功")
    except Exception as e:
        logger.error(f"MemorySystem 初始化失败: {e}")
        return

    # 3. 测试写入
    test_content = "测试记忆：用户喜欢草莓味甜甜圈"
    logger.info(f"尝试写入: {test_content}")
    try:
        doc_id = await memory.add(test_content, {"source": "test_script"})
        logger.info(f"写入成功，ID: {doc_id}")
    except Exception as e:
        logger.error(f"写入失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return

    # 4. 测试搜索
    query = "甜甜圈"
    logger.info(f"尝试搜索: {query}")
    try:
        results = await memory.search(query)
        logger.info(f"搜索结果数: {len(results)}")
        for r in results:
            logger.info(f" - {r.get('content')} (Score: {r.get('score')})")
    except Exception as e:
        logger.error(f"搜索失败: {e}")
        import traceback
        logger.error(traceback.format_exc())

    await memory.close()

if __name__ == "__main__":
    asyncio.run(main())
