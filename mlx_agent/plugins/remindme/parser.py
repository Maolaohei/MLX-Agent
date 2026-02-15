"""
自然语言时间解析模块

支持中文和英文时间描述
"""

import re
import calendar
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any
from loguru import logger


class TimeParser:
    """自然语言时间解析器"""
    
    # 数字映射
    CN_NUMBERS = {
        '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
        '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
        '两': 2, '几': 3, '半': 0.5
    }
    
    # 时间单位
    TIME_UNITS = {
        # 秒
        '秒': 'seconds', '秒钟': 'seconds', 's': 'seconds', 'sec': 'seconds',
        # 分钟
        '分': 'minutes', '分钟': 'minutes', 'min': 'minutes', 'm': 'minutes',
        # 小时
        '小时': 'hours', '时': 'hours', 'h': 'hours', 'hr': 'hours',
        # 天
        '天': 'days', '日': 'days', 'd': 'days', 'day': 'days',
        # 周
        '周': 'weeks', '星期': 'weeks', '礼拜': 'weeks', 'w': 'weeks', 'week': 'weeks',
        # 月
        '月': 'months', '个月': 'months',
        # 年
        '年': 'years', 'y': 'years', 'year': 'years'
    }
    
    # 星期映射
    WEEKDAYS = {
        '周一': 0, '周一': 0, '星期1': 0, 'mon': 0, 'monday': 0,
        '周二': 1, '周二': 1, '星期2': 1, 'tue': 1, 'tuesday': 1,
        '周三': 2, '周三': 2, '星期3': 2, 'wed': 2, 'wednesday': 2,
        '周四': 3, '周四': 3, '星期4': 3, 'thu': 3, 'thursday': 3,
        '周五': 4, '周五': 4, '星期5': 4, 'fri': 4, 'friday': 4,
        '周六': 5, '周六': 5, '星期6': 5, 'sat': 5, 'saturday': 5,
        '周日': 6, '周日': 6, '周天': 6, '星期7': 6, '周日': 6,
        'sun': 6, 'sunday': 6,
        '今天': -1, '明天': -2, '后天': -3, '昨天': -4
    }
    
    # 时间关键词
    TIME_KEYWORDS = {
        '早上': '08:00', '早晨': '08:00', '上午': '09:00', '中午': '12:00',
        '下午': '14:00', '傍晚': '18:00', '晚上': '20:00', '夜里': '22:00',
        '午夜': '00:00', '凌晨': '05:00',
        'morning': '08:00', 'afternoon': '14:00', 'evening': '18:00',
        'night': '20:00', 'midnight': '00:00', 'noon': '12:00'
    }
    
    def __init__(self, base_time: datetime = None):
        """
        Args:
            base_time: 基准时间 (默认当前时间)
        """
        self.base_time = base_time or datetime.now()
    
    def parse(self, text: str) -> Optional[datetime]:
        """解析自然语言时间描述
        
        Args:
            text: 时间描述字符串
            
        Returns:
            解析后的 datetime，解析失败返回 None
        """
        text = text.strip().lower()
        
        # 尝试各种解析方式
        result = (
            self._parse_relative(text) or
            self._parse_absolute(text) or
            self._parse_weekday(text) or
            self._parse_specific(text)
        )
        
        return result
    
    def _parse_relative(self, text: str) -> Optional[datetime]:
        """解析相对时间 (如 "10分钟后", "2小时后")"""
        # 匹配 "X单位后" 或 "after X units"
        patterns = [
            # 中文: 10分钟后, 2小时后, 3天后
            r'(\d+|半|一|二|三|四|五|六|七|八|九|十|两|几)\s*(秒|分钟|分|小时|时|天|日|周|星期|礼拜|月|年)(钟|后|之后|以后)?',
            # 英文: 10 min, 2 hours
            r'(\d+(?:\.\d+)?)\s*(s|sec|min|m|h|hr|d|day|w|week|month|year)(?:s?)\s*(later|after)?'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                num_str, unit = match.group(1), match.group(2)
                
                # 转换中文数字
                if num_str in self.CN_NUMBERS:
                    num = self.CN_NUMBERS[num_str]
                else:
                    try:
                        num = float(num_str)
                    except ValueError:
                        continue
                
                # 标准化单位
                unit = self.TIME_UNITS.get(unit, 'minutes')
                
                return self._add_time(self.base_time, num, unit)
        
        return None
    
    def _parse_absolute(self, text: str) -> Optional[datetime]:
        """解析绝对时间 (如 "明天下午3点", "2024-01-01")"""
        result = self.base_time.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # 检查日期部分
        date_matched = False
        
        # 明天/后天/昨天
        if '明天' in text or 'tomorrow' in text:
            result += timedelta(days=1)
            date_matched = True
        elif '后天' in text:
            result += timedelta(days=2)
            date_matched = True
        elif '昨天' in text or 'yesterday' in text:
            result -= timedelta(days=1)
            date_matched = True
        
        # 时间关键词
        for keyword, time_str in self.TIME_KEYWORDS.items():
            if keyword in text:
                hour, minute = map(int, time_str.split(':'))
                result = result.replace(hour=hour, minute=minute)
                date_matched = True
                break
        
        # 匹配具体时间 (如 3点, 3:30, 15:00)
        time_patterns = [
            r'(\d{1,2})[:点:](\d{1,2})?\s*分?',
            r'(\d{1,2}):(\d{2})',
        ]
        
        for pattern in time_patterns:
            match = re.search(pattern, text)
            if match:
                hour = int(match.group(1))
                minute = int(match.group(2)) if match.group(2) else 0
                
                # 智能判断上午/下午
                if hour <= 12 and ('下午' in text or '晚上' in text or 'evening' in text or 'afternoon' in text):
                    hour += 12
                elif hour == 12 and ('上午' in text or '早上' in text or 'morning' in text):
                    hour = 0
                
                result = result.replace(hour=hour, minute=minute)
                date_matched = True
                break
        
        return result if date_matched else None
    
    def _parse_weekday(self, text: str) -> Optional[datetime]:
        """解析星期时间 (如 "下周一")"""
        for weekday_str, weekday_num in self.WEEKDAYS.items():
            if weekday_str in text:
                if weekday_num == -1:  # 今天
                    return self.base_time
                elif weekday_num == -2:  # 明天
                    return self.base_time + timedelta(days=1)
                elif weekday_num == -3:  # 后天
                    return self.base_time + timedelta(days=2)
                elif weekday_num == -4:  # 昨天
                    return self.base_time - timedelta(days=1)
                
                # 计算目标日期
                today_weekday = self.base_time.weekday()
                days_ahead = weekday_num - today_weekday
                
                if days_ahead <= 0:  # 如果已过，取下周
                    days_ahead += 7
                
                # 检查是否有 "下" 表示下周
                if '下' in text:
                    days_ahead += 7
                
                result = self.base_time + timedelta(days=days_ahead)
                
                # 尝试解析具体时间
                time_result = self._parse_absolute(text)
                if time_result:
                    result = result.replace(hour=time_result.hour, minute=time_result.minute)
                else:
                    # 默认早上9点
                    result = result.replace(hour=9, minute=0)
                
                return result
        
        return None
    
    def _parse_specific(self, text: str) -> Optional[datetime]:
        """解析特定格式 (ISO日期等)"""
        # ISO 格式
        iso_patterns = [
            r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})',  # 2024-01-01 或 2024/01/01
            r'(\d{1,2})[-/](\d{1,2})[-/](\d{4})',  # 01-01-2024
        ]
        
        for pattern in iso_patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    groups = match.groups()
                    if len(groups[0]) == 4:  # YYYY-MM-DD
                        year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
                    else:  # MM-DD-YYYY
                        month, day, year = int(groups[0]), int(groups[1]), int(groups[2])
                    
                    result = datetime(year, month, day)
                    
                    # 尝试解析时间
                    time_result = self._parse_absolute(text)
                    if time_result:
                        result = result.replace(hour=time_result.hour, minute=time_result.minute)
                    
                    return result
                except ValueError:
                    continue
        
        return None
    
    def _add_time(self, dt: datetime, num: float, unit: str) -> datetime:
        """添加时间"""
        if unit == 'seconds':
            return dt + timedelta(seconds=num)
        elif unit == 'minutes':
            return dt + timedelta(minutes=num)
        elif unit == 'hours':
            return dt + timedelta(hours=num)
        elif unit == 'days':
            return dt + timedelta(days=num)
        elif unit == 'weeks':
            return dt + timedelta(weeks=num)
        elif unit == 'months':
            # 简单处理：按30天计算
            return dt + timedelta(days=int(num * 30))
        elif unit == 'years':
            # 简单处理：按365天计算
            return dt + timedelta(days=int(num * 365))
        return dt
    
    def parse_repeat(self, text: str) -> Optional[Dict[str, Any]]:
        """解析重复模式
        
        Args:
            text: 描述字符串
            
        Returns:
            {'type': 'daily'|'weekly'|'monthly', 'interval': int}
        """
        text = text.lower()
        
        # 每天/每日/daily
        if re.search(r'每天|每日|every\s*day|daily', text):
            return {'type': 'daily', 'interval': 1}
        
        # 每周/weekly
        if re.search(r'每周|每星期|every\s*week|weekly', text):
            return {'type': 'weekly', 'interval': 1}
        
        # 每月/monthly
        if re.search(r'每月|每个月|every\s*month|monthly', text):
            return {'type': 'monthly', 'interval': 1}
        
        # 每X天
        match = re.search(r'每\s*(\d+)\s*(天|日)', text)
        if match:
            return {'type': 'daily', 'interval': int(match.group(1))}
        
        return None


def parse_time(text: str, base_time: datetime = None) -> Tuple[Optional[datetime], Optional[str]]:
    """便捷函数：解析时间描述
    
    Args:
        text: 时间描述
        base_time: 基准时间
        
    Returns:
        (datetime, error_message)
    """
    parser = TimeParser(base_time)
    result = parser.parse(text)
    
    if result is None:
        return None, f"无法解析时间描述: {text}"
    
    return result, None


def format_relative_time(dt: datetime, base_time: datetime = None) -> str:
    """格式化相对时间描述
    
    Args:
        dt: 目标时间
        base_time: 基准时间
        
    Returns:
        中文相对时间描述
    """
    base_time = base_time or datetime.now()
    diff = dt - base_time
    
    if diff.total_seconds() < 0:
        return "已过期"
    
    total_seconds = diff.total_seconds()
    
    if total_seconds < 60:
        return "即将到期"
    elif total_seconds < 3600:
        minutes = int(total_seconds / 60)
        return f"{minutes}分钟后"
    elif total_seconds < 86400:
        hours = int(total_seconds / 3600)
        minutes = int((total_seconds % 3600) / 60)
        if minutes > 0:
            return f"{hours}小时{minutes}分钟后"
        return f"{hours}小时后"
    elif total_seconds < 604800:  # 7天
        days = diff.days
        if days == 1:
            return f"明天 {dt.strftime('%H:%M')}"
        elif days == 2:
            return f"后天 {dt.strftime('%H:%M')}"
        return f"{days}天后"
    else:
        return dt.strftime('%Y-%m-%d %H:%M')
