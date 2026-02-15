#!/usr/bin/env python3
"""
记忆系统迁移脚本

将 v0.2.0 的 index1 格式记忆迁移到 v0.3.0 的 ChromaDB 格式
"""

import os
import sys
import json
import asyncio
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

from loguru import logger


async def migrate_memory(old_path: str = "./memory", new_path: str = "./memory"):
    """迁移记忆数据
    
    Args:
        old_path: 旧记忆目录路径
        new_path: 新记忆目录路径
    """
    old_path = Path(old_path)
    new_path = Path(new_path)
    
    if not old_path.exists():
        logger.warning(f"Old memory path does not exist: {old_path}")
        return
    
    logger.info(f"Starting memory migration from {old_path} to {new_path}")
    
    # 统计
    migrated_count = 0
    skipped_count = 0
    error_count = 0
    
    # 遍历所有 Markdown 文件
    for subdir in ["core", "session", "archive"]:
        dir_path = old_path / subdir
        if not dir_path.exists():
            continue
        
        level = "P0" if subdir == "core" else "P1" if subdir == "session" else "P2"
        
        for md_file in dir_path.glob("*.md"):
            try:
                content = md_file.read_text(encoding="utf-8")
                
                # 解析 Markdown 内容
                # 格式: ## [id] timestamp\ncontent\n<!-- metadata: {...} -->
                lines = content.split('\n')
                current_entry = None
                
                for line in lines:
                    line = line.strip()
                    
                    if line.startswith('## ['):
                        # 保存之前的条目
                        if current_entry:
                            await _save_to_chroma(current_entry, level, new_path)
                            migrated_count += 1
                        
                        # 解析新条目
                        # 格式: ## [id] HH:MM
                        entry_id = line[4:line.find(']')]
                        current_entry = {
                            'id': entry_id,
                            'content': '',
                            'metadata': {},
                            'timestamp': line.split()[-1] if len(line.split()) > 1 else '00:00'
                        }
                    
                    elif line.startswith('<!-- metadata:'):
                        # 解析元数据
                        if current_entry:
                            try:
                                meta_str = line[15:-4].strip()  # 移除 <!-- metadata: 和 -->
                                current_entry['metadata'] = json.loads(meta_str)
                            except json.JSONDecodeError:
                                pass
                    
                    elif line and current_entry:
                        # 累加内容
                        if current_entry['content']:
                            current_entry['content'] += '\n'
                        current_entry['content'] += line
                
                # 保存最后一个条目
                if current_entry and current_entry['content']:
                    await _save_to_chroma(current_entry, level, new_path)
                    migrated_count += 1
                    
            except Exception as e:
                logger.error(f"Failed to migrate {md_file}: {e}")
                error_count += 1
    
    logger.info(f"Migration complete:")
    logger.info(f"  Migrated: {migrated_count}")
    logger.info(f"  Skipped: {skipped_count}")
    logger.info(f"  Errors: {error_count}")


async def _save_to_chroma(entry: Dict, level: str, base_path: Path):
    """保存条目到 ChromaDB"""
    # 这里我们只需要将数据写入 JSON 文件
    # ChromaDB 会在初始化时自动索引
    
    chroma_dir = base_path / "chroma_import"
    chroma_dir.mkdir(parents=True, exist_ok=True)
    
    # 生成 ChromaDB 兼容的 ID
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    memory_id = f"{level}_{timestamp}_{entry['id']}"
    
    # 准备文档
    document = {
        "id": memory_id,
        "content": entry['content'],
        "metadata": {
            "level": level,
            **entry.get('metadata', {}),
            "migrated_from": "index1",
            "migrated_at": datetime.now().isoformat()
        }
    }
    
    # 写入 JSONL 文件
    import_file = chroma_dir / f"{level}_migrated.jsonl"
    with open(import_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(document, ensure_ascii=False) + "\n")


async def import_to_chroma(memory_path: str = "./memory"):
    """将迁移的数据导入 ChromaDB"""
    try:
        import chromadb
        from chromadb.config import Settings
    except ImportError:
        logger.error("chromadb not installed. Run: pip install chromadb")
        return
    
    memory_path = Path(memory_path)
    chroma_dir = memory_path / "chroma_import"
    
    if not chroma_dir.exists():
        logger.info("No migration data found to import")
        return
    
    # 初始化 ChromaDB
    client = chromadb.PersistentClient(
        path=str(memory_path / "chroma"),
        settings=Settings(anonymized_telemetry=False)
    )
    
    collection = client.get_or_create_collection(name="memories")
    
    imported_count = 0
    
    # 导入所有 JSONL 文件
    for jsonl_file in chroma_dir.glob("*.jsonl"):
        try:
            with open(jsonl_file, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    
                    doc = json.loads(line)
                    collection.add(
                        ids=[doc["id"]],
                        documents=[doc["content"]],
                        metadatas=[doc["metadata"]]
                    )
                    imported_count += 1
                    
        except Exception as e:
            logger.error(f"Failed to import {jsonl_file}: {e}")
    
    logger.info(f"Imported {imported_count} memories to ChromaDB")
    
    # 清理导入文件
    import shutil
    shutil.rmtree(chroma_dir)
    logger.info("Cleaned up migration files")


async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Migrate MLX-Agent memory system")
    parser.add_argument("--old-path", default="./memory", help="Old memory path")
    parser.add_argument("--new-path", default="./memory", help="New memory path")
    parser.add_argument("--import-only", action="store_true", help="Only import to ChromaDB")
    
    args = parser.parse_args()
    
    if args.import_only:
        await import_to_chroma(args.new_path)
    else:
        await migrate_memory(args.old_path, args.new_path)
        await import_to_chroma(args.new_path)
    
    logger.info("Migration complete!")


if __name__ == "__main__":
    asyncio.run(main())
