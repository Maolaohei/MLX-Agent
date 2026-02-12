"""
记忆整合系统

每日自动整理记忆：
- 合并相似记忆
- 识别过时信息
- 生成摘要
"""

import hashlib
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Set
from collections import defaultdict

from loguru import logger


class MemoryConsolidator:
    """记忆整合器
    
    定期整理碎片化记忆，保持记忆库整洁
    """
    
    def __init__(self, memory_path: Path, similarity_threshold: float = 0.7):
        """初始化整合器
        
        Args:
            memory_path: 记忆目录路径
            similarity_threshold: 相似度阈值，超过则合并
        """
        self.memory_path = Path(memory_path)
        self.similarity_threshold = similarity_threshold
        self.consolidation_log: List[Dict] = []
    
    async def consolidate(
        self,
        days_back: int = 7,
        dry_run: bool = False
    ) -> Dict:
        """执行记忆整合
        
        Args:
            days_back: 处理最近几天的记忆
            dry_run: 试运行模式（不实际修改文件）
            
        Returns:
            整合报告
        """
        logger.info(f"Starting memory consolidation (days_back={days_back}, dry_run={dry_run})")
        
        report = {
            'started_at': datetime.now().isoformat(),
            'dry_run': dry_run,
            'processed_files': 0,
            'memories_found': 0,
            'duplicates_removed': 0,
            'consolidated_groups': 0,
            'archived_memories': 0,
            'errors': []
        }
        
        try:
            # 1. 扫描所有记忆文件
            all_memories = self._scan_memories(days_back)
            report['memories_found'] = len(all_memories)
            
            # 2. 查找并合并相似记忆
            groups = self._find_similar_groups(all_memories)
            report['consolidated_groups'] = len(groups)
            
            # 3. 识别过时记忆
            outdated = self._find_outdated_memories(all_memories, days_threshold=30)
            report['archived_memories'] = len(outdated)
            
            # 4. 执行整合
            if not dry_run:
                # 合并相似记忆
                for group in groups:
                    await self._merge_group(group)
                
                # 归档过时记忆
                for memory in outdated:
                    await self._archive_memory(memory)
                
                # 清理空文件
                self._cleanup_empty_files()
            
            report['completed_at'] = datetime.now().isoformat()
            
            logger.info(f"Consolidation completed: {report}")
            return report
            
        except Exception as e:
            logger.error(f"Consolidation failed: {e}")
            report['errors'].append(str(e))
            return report
    
    def _scan_memories(self, days_back: int) -> List[Dict]:
        """扫描记忆文件
        
        Args:
            days_back: 扫描最近几天的文件
            
        Returns:
            记忆条目列表
        """
        memories = []
        cutoff_date = datetime.now() - timedelta(days=days_back)
        
        for subdir in ['core', 'session', 'archive']:
            dir_path = self.memory_path / subdir
            if not dir_path.exists():
                continue
            
            for md_file in dir_path.glob('*.md'):
                try:
                    # 解析文件名日期
                    file_date = datetime.strptime(md_file.stem, '%Y-%m-%d')
                    if file_date < cutoff_date:
                        continue
                    
                    # 解析文件内容
                    file_memories = self._parse_memory_file(md_file, subdir)
                    memories.extend(file_memories)
                    
                except ValueError:
                    # 文件名不符合日期格式
                    continue
        
        return memories
    
    def _parse_memory_file(self, file_path: Path, level: str) -> List[Dict]:
        """解析记忆文件
        
        Args:
            file_path: Markdown 文件路径
            level: 记忆级别 (core/session/archive)
            
        Returns:
            记忆条目列表
        """
        memories = []
        content = file_path.read_text(encoding='utf-8')
        
        # 匹配记忆条目：## [ID] HH:MM
        pattern = r'##\s*\[([^\]]+)\]\s*(\d{2}:\d{2})\s*\n([^#]+?)(?=\n##\s*\[|$)'
        matches = re.findall(pattern, content, re.DOTALL)
        
        for memory_id, time_str, body in matches:
            # 解析元数据 <!-- metadata: {...} -->
            metadata_match = re.search(r'<!--\s*metadata:\s*(.+?)\s*-->', body)
            metadata = {}
            if metadata_match:
                try:
                    metadata = json.loads(metadata_match.group(1))
                except json.JSONDecodeError:
                    pass
            
            # 清理正文
            clean_body = re.sub(r'<!--\s*metadata:.+?-->', '', body).strip()
            
            memories.append({
                'id': memory_id.strip(),
                'time': time_str,
                'date': file_path.stem,
                'content': clean_body,
                'level': level,
                'metadata': metadata,
                'source_file': str(file_path),
                'full_text': body
            })
        
        return memories
    
    def _find_similar_groups(self, memories: List[Dict]) -> List[List[Dict]]:
        """查找相似记忆组
        
        使用简单的文本相似度算法
        
        Args:
            memories: 记忆列表
            
        Returns:
            相似记忆组列表
        """
        groups = []
        used = set()
        
        for i, mem1 in enumerate(memories):
            if i in used:
                continue
            
            group = [mem1]
            used.add(i)
            
            for j, mem2 in enumerate(memories[i+1:], start=i+1):
                if j in used:
                    continue
                
                similarity = self._calculate_similarity(
                    mem1['content'],
                    mem2['content']
                )
                
                if similarity >= self.similarity_threshold:
                    group.append(mem2)
                    used.add(j)
            
            if len(group) > 1:
                groups.append(group)
        
        return groups
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """计算两段文本的相似度
        
        使用 Jaccard 相似度（基于词集）
        
        Args:
            text1: 文本1
            text2: 文本2
            
        Returns:
            相似度 (0-1)
        """
        if not text1 or not text2:
            return 0.0
        
        # 分词（简单按空格和标点分割）
        def tokenize(text: str) -> Set[str]:
            # 转小写，替换标点为空格
            text = re.sub(r'[^\w\s]', ' ', text.lower())
            # 分词并过滤短词
            words = {w for w in text.split() if len(w) > 2}
            return words
        
        words1 = tokenize(text1)
        words2 = tokenize(text2)
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1 & words2
        union = words1 | words2
        
        return len(intersection) / len(union) if union else 0.0
    
    def _find_outdated_memories(
        self,
        memories: List[Dict],
        days_threshold: int = 30
    ) -> List[Dict]:
        """查找过时的记忆
        
        规则：
        - P2 级别超过 30 天
        - 标记为 temporary 的记忆
        
        Args:
            memories: 记忆列表
            days_threshold: 天数阈值
            
        Returns:
            过时记忆列表
        """
        cutoff = datetime.now() - timedelta(days=days_threshold)
        outdated = []
        
        for memory in memories:
            # P0 级别永不过时
            if memory.get('level') == 'core' or memory.get('metadata', {}).get('level') == 'P0':
                continue
            
            # 检查是否为临时记忆
            if memory.get('metadata', {}).get('temporary'):
                outdated.append(memory)
                continue
            
            # 检查日期
            try:
                mem_date = datetime.strptime(memory.get('date', ''), '%Y-%m-%d')
                if mem_date < cutoff and memory.get('level') == 'archive':
                    outdated.append(memory)
            except ValueError:
                pass
        
        return outdated
    
    async def _merge_group(self, group: List[Dict]):
        """合并相似记忆组
        
        Args:
            group: 相似记忆组
        """
        if len(group) < 2:
            return
        
        # 保留最早的作为主要记忆
        main_memory = min(group, key=lambda m: f"{m.get('date', '')} {m.get('time', '')}")
        
        # 提取其他记忆的差异信息
        variations = []
        for mem in group:
            if mem['id'] != main_memory['id']:
                variations.append({
                    'date': mem.get('date'),
                    'content': mem.get('content', '')[:200]
                })
        
        # 生成合并后的内容
        merged_content = main_memory['content']
        if variations:
            merged_content += f"\n\n[Related memories from {len(variations)} occasions]"
        
        # 更新主记忆
        main_file = Path(main_memory['source_file'])
        if main_file.exists():
            content = main_file.read_text(encoding='utf-8')
            
            # 更新内容
            old_entry = f"## [{main_memory['id']}] {main_memory['time']}\n{main_memory['full_text']}"
            new_entry = f"## [{main_memory['id']}] {main_memory['time']}\n{merged_content}\n<!-- metadata: {{\"consolidated\": true, \"variations\": {len(variations)}}} -->"
            
            content = content.replace(old_entry, new_entry)
            main_file.write_text(content, encoding='utf-8')
        
        # 删除其他记忆
        for mem in group:
            if mem['id'] != main_memory['id']:
                await self._remove_memory_entry(mem)
        
        logger.info(f"Merged {len(group)} similar memories into {main_memory['id']}")
    
    async def _remove_memory_entry(self, memory: Dict):
        """从文件中移除记忆条目
        
        Args:
            memory: 要移除的记忆
        """
        file_path = Path(memory['source_file'])
        if not file_path.exists():
            return
        
        content = file_path.read_text(encoding='utf-8')
        
        # 构造要移除的条目模式
        pattern = rf"##\s*\[{re.escape(memory['id'])}\]\s*{re.escape(memory['time'])}\s*\n[^#]*?(?=\n##\s*\[|$)"
        
        # 移除条目
        new_content = re.sub(pattern, '', content, flags=re.DOTALL)
        
        if new_content != content:
            file_path.write_text(new_content, encoding='utf-8')
            logger.debug(f"Removed memory entry: {memory['id']}")
    
    async def _archive_memory(self, memory: Dict):
        """归档记忆
        
        Args:
            memory: 要归档的记忆
        """
        # 移动到 archive 目录
        archive_dir = self.memory_path / 'archive'
        archive_dir.mkdir(parents=True, exist_ok=True)
        
        # 从原文件移除
        await self._remove_memory_entry(memory)
        
        # 添加到归档文件
        today = datetime.now().strftime('%Y-%m-%d')
        archive_file = archive_dir / f'{today}_consolidated.md'
        
        archive_entry = f"\n## [{memory['id']}] {memory.get('date')} {memory.get('time')} (ARCHIVED)\n"
        archive_entry += f"{memory['content']}\n"
        archive_entry += f"<!-- metadata: {json.dumps(memory.get('metadata', {}), ensure_ascii=False)} -->\n"
        
        with open(archive_file, 'a', encoding='utf-8') as f:
            f.write(archive_entry)
        
        logger.debug(f"Archived memory: {memory['id']}")
    
    def _cleanup_empty_files(self):
        """清理空文件"""
        for subdir in ['core', 'session', 'archive']:
            dir_path = self.memory_path / subdir
            if not dir_path.exists():
                continue
            
            for md_file in dir_path.glob('*.md'):
                content = md_file.read_text(encoding='utf-8').strip()
                # 如果文件内容为空或只有空白
                if not content or not re.search(r'##\s*\[', content):
                    md_file.unlink()
                    logger.info(f"Removed empty file: {md_file}")
    
    def get_consolidation_history(self) -> List[Dict]:
        """获取整合历史"""
        return self.consolidation_log
