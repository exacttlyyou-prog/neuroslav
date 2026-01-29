"""
Простой text splitter без зависимостей от langchain.
"""
from typing import List


class RecursiveCharacterTextSplitter:
    """
    Простая реализация text splitter для разбиения текста на чанки.
    Аналог langchain_text_splitters.RecursiveCharacterTextSplitter.
    """
    
    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        length_function=None
    ):
        """
        Инициализация text splitter.
        
        Args:
            chunk_size: Максимальный размер чанка
            chunk_overlap: Размер перекрытия между чанками
            length_function: Функция для подсчета длины (по умолчанию len)
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.length_function = length_function or len
        
        # Разделители для разбиения текста (от более крупных к более мелким)
        self.separators = ["\n\n", "\n", ". ", " ", ""]
    
    def split_text(self, text: str) -> List[str]:
        """
        Разбивает текст на чанки.
        
        Args:
            text: Текст для разбиения
            
        Returns:
            Список чанков
        """
        if not text:
            return []
        
        # Начинаем с самого текста
        splits = [text]
        
        # Применяем разделители по порядку
        for separator in self.separators:
            if separator == "":
                # Последний разделитель - разбиваем посимвольно
                new_splits = []
                for split in splits:
                    new_splits.extend(self._split_by_size(split))
                splits = new_splits
            else:
                # Разбиваем по разделителю
                new_splits = []
                for split in splits:
                    if self.length_function(split) <= self.chunk_size:
                        new_splits.append(split)
                    else:
                        parts = split.split(separator)
                        current_chunk = ""
                        for part in parts:
                            part_with_sep = part if not current_chunk else separator + part
                            if self.length_function(current_chunk + part_with_sep) <= self.chunk_size:
                                current_chunk += part_with_sep
                            else:
                                if current_chunk:
                                    new_splits.append(current_chunk)
                                current_chunk = part
                        if current_chunk:
                            new_splits.append(current_chunk)
                splits = new_splits
        
        # Объединяем маленькие чанки
        final_chunks = []
        current_chunk = ""
        
        for split in splits:
            if self.length_function(current_chunk + split) <= self.chunk_size:
                current_chunk += split
            else:
                if current_chunk:
                    final_chunks.append(current_chunk.strip())
                current_chunk = split
        
        if current_chunk:
            final_chunks.append(current_chunk.strip())
        
        # Добавляем перекрытие между чанками
        if self.chunk_overlap > 0 and len(final_chunks) > 1:
            overlapped_chunks = [final_chunks[0]]
            for i in range(1, len(final_chunks)):
                prev_chunk = final_chunks[i - 1]
                current_chunk = final_chunks[i]
                
                # Берем последние chunk_overlap символов из предыдущего чанка
                overlap_text = prev_chunk[-self.chunk_overlap:] if len(prev_chunk) > self.chunk_overlap else prev_chunk
                overlapped_chunk = overlap_text + current_chunk
                
                # Если получилось слишком длинно, обрезаем
                if self.length_function(overlapped_chunk) > self.chunk_size:
                    overlapped_chunk = current_chunk
                
                overlapped_chunks.append(overlapped_chunk)
            
            return overlapped_chunks
        
        return [chunk for chunk in final_chunks if chunk.strip()]
    
    def _split_by_size(self, text: str) -> List[str]:
        """Разбивает текст по размеру чанка."""
        chunks = []
        for i in range(0, len(text), self.chunk_size):
            chunks.append(text[i:i + self.chunk_size])
        return chunks
