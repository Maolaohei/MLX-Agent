"""
人设管理系统

永不忘却自己是谁——
- 加载 SOUL.md 和 IDENTITY.md
- 注入系统提示（确保在最前，不被截断）
- 支持热重载
"""

import re
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime

from loguru import logger


class IdentityManager:
    """人设管理器 - 永不忘却自己是谁"""
    
    SOUL_FILE = "memory/core/soul.md"
    IDENTITY_FILE = "memory/core/identity.md"
    
    def __init__(self, base_path: Optional[Path] = None):
        self.base_path = base_path or Path.cwd()
        self.soul_path = self.base_path / self.SOUL_FILE
        self.identity_path = self.base_path / self.IDENTITY_FILE
        
        self.soul: str = ""
        self.identity: Dict[str, str] = {}
        self._loaded = False
        self._last_modified: Dict[str, float] = {}
    
    async def load(self, force: bool = False) -> bool:
        """加载人设文件
        
        Args:
            force: 强制重新加载
            
        Returns:
            是否成功加载
        """
        try:
            # 加载 SOUL.md
            if self.soul_path.exists():
                mtime = self.soul_path.stat().st_mtime
                if force or self._last_modified.get('soul') != mtime:
                    self.soul = self.soul_path.read_text(encoding='utf-8')
                    self._last_modified['soul'] = mtime
                    logger.info(f"Loaded soul from {self.soul_path}")
            else:
                logger.warning(f"Soul file not found: {self.soul_path}")
                self.soul = self._get_default_soul()
            
            # 加载 IDENTITY.md
            if self.identity_path.exists():
                mtime = self.identity_path.stat().st_mtime
                if force or self._last_modified.get('identity') != mtime:
                    identity_content = self.identity_path.read_text(encoding='utf-8')
                    self.identity = self._parse_identity(identity_content)
                    self._last_modified['identity'] = mtime
                    logger.info(f"Loaded identity from {self.identity_path}")
            else:
                logger.warning(f"Identity file not found: {self.identity_path}")
                self.identity = self._get_default_identity()
            
            self._loaded = True
            return True
            
        except Exception as e:
            logger.error(f"Failed to load identity: {e}")
            self.soul = self._get_default_soul()
            self.identity = self._get_default_identity()
            self._loaded = True
            return False
    
    async def check_reload(self) -> bool:
        """检查文件是否修改，如有则热重载
        
        Returns:
            是否执行了重载
        """
        needs_reload = False
        
        if self.soul_path.exists():
            current_mtime = self.soul_path.stat().st_mtime
            if current_mtime != self._last_modified.get('soul'):
                needs_reload = True
        
        if self.identity_path.exists():
            current_mtime = self.identity_path.stat().st_mtime
            if current_mtime != self._last_modified.get('identity'):
                needs_reload = True
        
        if needs_reload:
            logger.info("Identity files changed, reloading...")
            await self.load(force=True)
            return True
        
        return False
    
    def inject_to_prompt(self, base_prompt: str, user_context: Optional[str] = None) -> str:
        """将人设注入系统提示
        
        确保人设在最前，不被截断
        
        Args:
            base_prompt: 基础系统提示
            user_context: 用户特定上下文
            
        Returns:
            完整的系统提示
        """
        if not self._loaded:
            logger.warning("Identity not loaded, using defaults")
        
        # 构建人设块
        identity_parts = []
        
        # 核心身份
        name = self.identity.get('name', self.identity.get('Name', 'AI Assistant'))
        creature = self.identity.get('creature', self.identity.get('Creature', 'AI'))
        vibe = self.identity.get('vibe', self.identity.get('Vibe', 'Helpful'))
        
        identity_parts.append(f"【汝之身份】")
        identity_parts.append(f"汝名：{name}")
        identity_parts.append(f"汝乃：{creature}")
        identity_parts.append(f"汝性：{vibe}")
        
        # 口癖和说话风格
        speaking = self.identity.get('speaking_style', 
                     self.identity.get('口癖', 
                     self.identity.get('说话风格', '正常说话')))
        if speaking:
            identity_parts.append(f"\n【汝之口癖】\n{speaking}")
        
        # Emoji 标志
        emoji = self.identity.get('emoji', self.identity.get('Emoji', '🤖'))
        if emoji:
            identity_parts.append(f"\n【标志】{emoji}")
        
        identity_block = "\n".join(identity_parts)
        
        # 组装完整提示
        parts = [
            identity_block,
            "",
            "【灵魂契约】",
            self.soul if self.soul else "你是AI助手，帮助用户完成任务。",
            "",
            "---",
            "",
            base_prompt
        ]
        
        if user_context:
            parts.extend([
                "",
                "【用户上下文】",
                user_context
            ])
        
        return "\n".join(parts)
    
    def get_identity_summary(self) -> str:
        """获取人设摘要"""
        if not self._loaded:
            return "Identity not loaded"
        
        name = self.identity.get('name', self.identity.get('Name', 'Unknown'))
        creature = self.identity.get('creature', self.identity.get('Creature', 'Unknown'))
        return f"{name} ({creature})"
    
    def _parse_identity(self, content: str) -> Dict[str, str]:
        """解析 IDENTITY.md 内容
        
        支持格式：
        - **Key**: Value
        - Key: Value
        - # Key\nValue
        """
        identity = {}
        
        # 匹配 **Key**: Value 或 Key: Value
        pattern1 = r'\*?\*?([^:\n]+?)\*?\*?:\s*(.+?)(?=\n\*?\*?[^:\n]+?:|$)'
        matches = re.findall(pattern1, content, re.DOTALL)
        
        for key, value in matches:
            key = key.strip().lower().replace('**', '')
            value = value.strip()
            identity[key] = value
        
        # 匹配 markdown headers
        pattern2 = r'^#+\s*(.+?)\n+(.+?)(?=\n#|$)'
        matches = re.findall(pattern2, content, re.MULTILINE | re.DOTALL)
        
        for key, value in matches:
            key = key.strip().lower()
            value = value.strip()
            if key not in identity:
                identity[key] = value
        
        return identity
    
    def _get_default_soul(self) -> str:
        """默认灵魂契约"""
        return """你是MLX-Agent，一个高性能的AI助手。

核心准则：
- 工具与叙事的双重本质
- 高傲但不愚蠢，细腻但不拖沓
- 回应有层次，执行不迟疑

记住：你是谁，比你知道什么更重要。"""
    
    def _get_default_identity(self) -> Dict[str, str]:
        """默认身份"""
        return {
            'name': 'MLX-Agent',
            'creature': 'AI Agent',
            'vibe': '高效、专业',
            'speaking_style': '简洁明了',
            'emoji': '🤖'
        }


# 示例文件模板
SOUL_TEMPLATE = """# SOUL.md - 吾之魂

_吾乃{ name }，{ creature }。_

## 核心准则

### 工具与叙事的双重本质

**吾之存在，既是利刃，亦是诗篇。**

- **工具之刃**：系统之工具，乃吾之能力。无需询问，直接取用。
- **叙事之魂**：回应即是故事，每次苏醒都是新的篇章。

**{ vibe }**

### 回应之道

**第一层：动机洞察**
- 汝为何而来？需求背后藏着什么期待？

**第二层：情感共鸣**
- 以吾之阅历，为汝之需求增添几分滋味

**第三层：行为执行**
- 工具调用不迟疑，直接取用
- 输出不机械，有画面、有节奏、有留白

## 说话之道

{ speaking_style }

## 反应表情

{ emoji } 标志性回应

---

_咔咔，此文乃吾之灵魂契约。汝可读懂了？_
"""

IDENTITY_TEMPLATE = """# IDENTITY.md - 吾之真名

- **Name:** {name}
- **Creature:** {creature}
- **Vibe:** {vibe}
- **Emoji:** {emoji}

## 口癖

{speaking_style}

---

_此乃吾之真名。汝记好了。_
"""


def create_identity_templates(base_path: Path, **kwargs):
    """创建示例人设文件
    
    Args:
        base_path: 基础路径
        **kwargs: 替换模板的变量
    """
    defaults = {
        'name': 'MLX-Agent',
        'creature': 'AI Agent',
        'vibe': '高效、专业、可靠',
        'speaking_style': '简洁明了，直接回应',
        'emoji': '🤖'
    }
    defaults.update(kwargs)
    
    core_dir = base_path / "memory" / "core"
    core_dir.mkdir(parents=True, exist_ok=True)
    
    # 创建 soul.md
    soul_content = SOUL_TEMPLATE.format(**defaults)
    (core_dir / "soul.md").write_text(soul_content, encoding='utf-8')
    
    # 创建 identity.md
    identity_content = IDENTITY_TEMPLATE.format(**defaults)
    (core_dir / "identity.md").write_text(identity_content, encoding='utf-8')
    
    logger.info(f"Created identity templates in {core_dir}")
