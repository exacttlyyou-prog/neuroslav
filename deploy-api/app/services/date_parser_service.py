"""
Сервис для парсинга дат и времени.
Поддерживает различные форматы, включая относительные даты.
"""
from typing import Optional
from datetime import datetime, timedelta
from loguru import logger
import re


class DateParserService:
    """Сервис для парсинга дат и времени."""
    
    def __init__(self):
        pass
    
    def parse_datetime(self, date_string: str) -> Optional[datetime]:
        """
        Парсит строку с датой/временем и возвращает datetime объект.
        Поддерживает различные форматы, включая относительные даты.
        
        Args:
            date_string: строка с датой/временем
            
        Returns:
            datetime объект или None если не удалось распарсить
        """
        if not date_string or date_string.lower().strip() in ["не указано", "none", ""]:
            return None
            
        date_string = date_string.lower().strip()
        now = datetime.now()
        
        # Заменяем русские названия дней недели
        day_translations = {
            "понедельник": "monday",
            "вторник": "tuesday", 
            "среда": "wednesday",
            "четверг": "thursday",
            "пятница": "friday",
            "суббота": "saturday",
            "воскресенье": "sunday"
        }
        
        for ru_day, en_day in day_translations.items():
            date_string = date_string.replace(ru_day, en_day)
        
        # Обрабатываем относительные даты
        
        # 1. Завтра, послезавтра
        if "завтра" in date_string:
            return now + timedelta(days=1)
        elif "послезавтра" in date_string:
            return now + timedelta(days=2)
        elif "вчера" in date_string:
            return now - timedelta(days=1)
        
        # 2. Следующая неделя (по умолчанию понедельник)
        if "следующая неделя" in date_string or "next week" in date_string:
            days_ahead = 7 - now.weekday()  # До следующего понедельника
            if days_ahead <= 0:  # Если сегодня понедельник
                days_ahead += 7
            return now + timedelta(days=days_ahead)
        
        # 3. На следующей неделе + день недели
        next_week_pattern = r"на следующей неделе (\w+)|next week (\w+)|следующий (\w+)|next (\w+)"
        match = re.search(next_week_pattern, date_string)
        if match:
            day_name = None
            for group in match.groups():
                if group:
                    day_name = group.lower()
                    break
            
            if day_name:
                weekday_map = {
                    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
                    "friday": 4, "saturday": 5, "sunday": 6
                }
                
                if day_name in weekday_map:
                    target_weekday = weekday_map[day_name]
                    days_ahead = (7 - now.weekday() + target_weekday) % 7
                    if days_ahead == 0:  # Если это сегодня, берем следующую неделю
                        days_ahead = 7
                    return now + timedelta(days=days_ahead)
        
        # 4. На этой неделе + день недели
        this_week_pattern = r"на этой неделе (\w+)|this week (\w+)|эт(?:у|от) (\w+)|this (\w+)"
        match = re.search(this_week_pattern, date_string)
        if match:
            day_name = None
            for group in match.groups():
                if group:
                    day_name = group.lower()
                    break
            
            if day_name:
                weekday_map = {
                    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
                    "friday": 4, "saturday": 5, "sunday": 6
                }
                
                if day_name in weekday_map:
                    target_weekday = weekday_map[day_name]
                    days_ahead = (target_weekday - now.weekday()) % 7
                    if days_ahead == 0 and now.weekday() == target_weekday:
                        # Если это сегодня и тот же день недели, оставляем сегодня
                        return now
                    return now + timedelta(days=days_ahead)
        
        # 5. Через X дней/часов/минут
        through_pattern = r"через (\d+)\s*(минут|час|день|дня|дней|часов|часа)"
        match = re.search(through_pattern, date_string)
        if match:
            num = int(match.group(1))
            unit = match.group(2)
            
            if "минут" in unit:
                return now + timedelta(minutes=num)
            elif "час" in unit:
                return now + timedelta(hours=num)
            elif "день" in unit or "дня" in unit or "дней" in unit:
                return now + timedelta(days=num)
        
        # 6. В течение X дней
        within_pattern = r"в течение (\d+)\s*(день|дня|дней)"
        match = re.search(within_pattern, date_string)
        if match:
            num = int(match.group(1))
            return now + timedelta(days=num)
        
        # 7. Через X недель
        weeks_pattern = r"через (\d+)\s*(недел[ьи]|week)"
        match = re.search(weeks_pattern, date_string)
        if match:
            num = int(match.group(1))
            return now + timedelta(weeks=num)
        
        # 8. Пробуем стандартный dateutil парсер
        try:
            from dateutil import parser as dateutil_parser
            return dateutil_parser.parse(date_string)
        except Exception:
            pass
        
        # 9. Пробуем dateparser для более сложных случаев
        try:
            import dateparser
            result = dateparser.parse(
                date_string,
                settings={
                    'PREFER_DATES_FROM': 'future',
                    'RELATIVE_BASE': now,
                    'RETURN_AS_TIMEZONE_AWARE': False
                }
            )
            if result:
                return result
        except Exception as e:
            logger.debug(f"dateparser не смог распарсить '{date_string}': {e}")
        
        # 10. Если ничего не помогло, возвращаем None
        logger.warning(f"Не удалось распарсить дату: '{date_string}'")
        return None
    
    def parse_deadline(self, text: str, default_hours: int = 24) -> Optional[datetime]:
        """
        Парсит дедлайн из текста. Если не указан, возвращает дату через default_hours часов.
        
        Args:
            text: текст для анализа
            default_hours: часы по умолчанию, если дедлайн не найден
            
        Returns:
            datetime объект дедлайна
        """
        # Ищем упоминания времени в тексте
        time_patterns = [
            r"до (\d{1,2}:\d{2})",
            r"к (\d{1,2} \w+)",
            r"дедлайн (\w+ \w+|\d{1,2}.\d{1,2})",
            r"срок (.*?)(?:\.|$)",
            r"нужно до (.*?)(?:\.|$)",
        ]
        
        for pattern in time_patterns:
            match = re.search(pattern, text.lower())
            if match:
                time_str = match.group(1).strip()
                parsed_time = self.parse_datetime(time_str)
                if parsed_time:
                    return parsed_time
        
        # Если не нашли конкретное время, возвращаем default
        return datetime.now() + timedelta(hours=default_hours)


# Глобальный экземпляр сервиса
_date_parser = None


def get_date_parser_service() -> DateParserService:
    """Возвращает глобальный экземпляр DateParserService."""
    global _date_parser
    if _date_parser is None:
        _date_parser = DateParserService()
    return _date_parser