"""
Token 压缩系统

智能管理上下文窗口：
- 使用 tiktoken 计算 token 数
- 超限记忆自动压缩/摘要
- 优先级：P0 > P1 > P2
"""

from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

from loguru import logger


@dataclass
class CompressedMemory:
    """压缩后的记忆"""
    content: str
    original_tokens: int
    compressed_tokens: int
    compression_ratio: float
    level: str
    

try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False
    logger.warning("tiktoken not installed, using approximate token count")


class TokenCompressor:
    """Token 压缩器
    
    管理记忆 token 预算，自动压缩低优先级记忆
    """
    
    def __init__(self, model: str = "gpt-4o", encoding_name: Optional[str] = None):
        """初始化压缩器
        
        Args:
            model: 模型名称，用于选择 tokenizer
            encoding_name: 指定 encoding，覆盖模型选择
        """
        self.model = model
        self.encoding_name = encoding_name
        self._encoding = None
        
        if TIKTOKEN_AVAILABLE:
            try:
                if encoding_name:
                    self._encoding = tiktoken.get_encoding(encoding_name)
                else:
                    # 尝试根据模型获取 encoding
                    if "gpt-4" in model or "gpt-3.5" in model:
                        self._encoding = tiktoken.encoding_for_model(model)
                    else:
                        # 默认使用 cl100k_base
                        self._encoding = tiktoken.get_encoding("cl100k_base")
                logger.info(f"TokenCompressor initialized with encoding: {self._encoding.name}")
            except Exception as e:
                logger.warning(f"Failed to load tiktoken encoding: {e}")
                self._encoding = None
    
    def count_tokens(self, text: str) -> int:
        """计算文本的 token 数
        
        Args:
            text: 输入文本
            
        Returns:
            token 数量
        """
        if not text:
            return 0
        
        if self._encoding:
            try:
                return len(self._encoding.encode(text))
            except Exception as e:
                logger.debug(f"tiktoken encoding failed: {e}")
        
        # 近似计算：中文 1.5 tokens/字，英文 0.25 tokens/char
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        other_chars = len(text) - chinese_chars
        return int(chinese_chars * 1.5 + other_chars * 0.25)
    
    def compress_for_context(
        self,
        memories: List[Dict],
        max_tokens: int,
        system_prompt: str = "",
        user_message: str = "",
        reserve_tokens: int = 500
    ) -> str:
        """压缩记忆以适应上下文窗口
        
        策略：
        1. 先计算系统提示和用户消息的 token
        2. 剩余预算分配给记忆
        3. 按优先级加载记忆 (P0 > P1 > P2)
        4. 超限部分进行压缩或丢弃
        
        Args:
            memories: 记忆列表，每项包含 content, level, metadata
            max_tokens: 总 token 上限
            system_prompt: 系统提示（不压缩）
            user_message: 用户消息（不压缩）
            reserve_tokens: 为输出预留的 token
            
        Returns:
            压缩后的记忆文本
        """
        # 计算固定开销
        system_tokens = self.count_tokens(system_prompt)
        user_tokens = self.count_tokens(user_message)
        
        # 可用预算
        available_tokens = max_tokens - system_tokens - user_tokens - reserve_tokens
        
        if available_tokens <= 0:
            logger.warning("No token budget left for memories")
            return ""
        
        logger.debug(f"Token budget: {available_tokens} (total: {max_tokens}, "
                    f"system: {system_tokens}, user: {user_tokens}, reserve: {reserve_tokens})")
        
        # 按优先级分组
        p0_memories = [m for m in memories if m.get('level') == 'P0' or m.get('metadata', {}).get('level') == 'P0']
        p1_memories = [m for m in memories if m.get('level') == 'P1' or m.get('metadata', {}).get('level') == 'P1']
        p2_memories = [m for m in memories if m.get('level') == 'P2' or m.get('metadata', {}).get('level') == 'P2']
        other_memories = [m for m in memories if m not in p0_memories + p1_memories + p2_memories]
        
        # 按优先级排序
        sorted_memories = p0_memories + p1_memories + p2_memories + other_memories
        
        # 逐步加载记忆，直到预算用尽
        selected_memories = []
        current_tokens = 0
        
        for memory in sorted_memories:
            content = memory.get('content', '')
            level = memory.get('level', memory.get('metadata', {}).get('level', 'P1'))
            
            tokens = self.count_tokens(content)
            
            # P0 级别：永远保留（即使超出预算也尽量保留）
            if level == 'P0':
                selected_memories.append(memory)
                current_tokens += tokens
                continue
            
            # 检查是否还有预算
            if current_tokens + tokens <= available_tokens:
                selected_memories.append(memory)
                current_tokens += tokens
            else:
                # 预算不足，尝试压缩
                remaining_budget = available_tokens - current_tokens
                if remaining_budget > 50:  # 至少保留 50 tokens
                    compressed = self._compress_memory(content, remaining_budget)
                    if compressed:
                        memory = memory.copy()
                        memory['content'] = compressed
                        memory['_compressed'] = True
                        selected_memories.append(memory)
                        current_tokens += self.count_tokens(compressed)
                
                # P1 级别：如果压缩后仍放不下，跳过
                # P2 级别：直接跳过
                if level == 'P2':
                    break
        
        # 格式化输出
        return self._format_memories(selected_memories)
    
    def compress_memories_batch(
        self,
        memories: List[Dict],
        max_tokens: int
    ) -> Tuple[List[CompressedMemory], int]:
        """批量压缩记忆
        
        Args:
            memories: 记忆列表
            max_tokens: 总 token 上限
            
        Returns:
            (压缩后的记忆列表, 总 token 数)
        """
        result = []
        total_tokens = 0
        
        for memory in memories:
            content = memory.get('content', '')
            original_tokens = self.count_tokens(content)
            
            # 如果单条就超限，需要压缩
            if original_tokens > max_tokens // len(memories):
                target_tokens = max_tokens // len(memories)
                compressed_content = self._compress_memory(content, target_tokens)
                compressed_tokens = self.count_tokens(compressed_content)
            else:
                compressed_content = content
                compressed_tokens = original_tokens
            
            cm = CompressedMemory(
                content=compressed_content,
                original_tokens=original_tokens,
                compressed_tokens=compressed_tokens,
                compression_ratio=compressed_tokens / original_tokens if original_tokens > 0 else 1.0,
                level=memory.get('level', memory.get('metadata', {}).get('level', 'P1'))
            )
            
            result.append(cm)
            total_tokens += compressed_tokens
            
            if total_tokens >= max_tokens:
                break
        
        return result, total_tokens
    
    def _compress_memory(self, content: str, max_tokens: int) -> str:
        """压缩单条记忆到指定 token 数
        
        策略：
        1. 保留前 30% 和后 20%
        2. 中间部分用 [...X chars omitted...] 替代
        
        Args:
            content: 原始内容
            max_tokens: 目标 token 数
            
        Returns:
            压缩后的内容
        """
        current_tokens = self.count_tokens(content)
        
        if current_tokens <= max_tokens:
            return content
        
        # 粗略估计字符数（保守估计）
        target_chars = int(max_tokens * 2.5)  # 假设平均 2.5 chars/token
        
        if len(content) <= target_chars:
            return content
        
        # 保留开头和结尾
        head_len = int(target_chars * 0.3)
        tail_len = int(target_chars * 0.2)
        
        head = content[:head_len]
        tail = content[-tail_len:] if tail_len > 0 else ""
        omitted = len(content) - head_len - tail_len
        
        return f"{head}\n\n[...{omitted} chars omitted...]\n\n{tail}"
    
    def _format_memories(self, memories: List[Dict]) -> str:
        """格式化记忆列表为文本"""
        if not memories:
            return ""
        
        parts = ["【相关记忆】"]
        
        for i, m in enumerate(memories, 1):
            content = m.get('content', '').strip()
            level = m.get('level', m.get('metadata', {}).get('level', 'P1'))
            compressed = m.get('_compressed', False)
            
            prefix = f"{i}. [{level}]"
            if compressed:
                prefix += " (compressed)"
            
            parts.append(f"{prefix} {content[:300]}{'...' if len(content) > 300 else ''}")
        
        return "\n".join(parts)
    
    def get_compression_stats(self, memories: List[Dict], max_tokens: int) -> Dict:
        """获取压缩统计信息
        
        Args:
            memories: 记忆列表
            max_tokens: 预算
            
        Returns:
            统计信息字典
        """
        total_original = sum(self.count_tokens(m.get('content', '')) for m in memories)
        
        compressed, total_compressed = self.compress_memories_batch(memories, max_tokens)
        
        return {
            'total_memories': len(memories),
            'original_tokens': total_original,
            'compressed_tokens': total_compressed,
            'compression_ratio': total_compressed / total_original if total_original > 0 else 1.0,
            'memories_kept': len(compressed),
            'memories_dropped': len(memories) - len(compressed),
            'within_budget': total_compressed <= max_tokens
        }
