"""
Оркестрация «7 шагов»: явный pipeline (шаги 3–7), каждый шаг — вызов своего сервиса.
Шаги 1–2 (wake, приём/транскрипция) — вне pipeline (webhook, record_meeting).
"""
from typing import Dict, Any, List, Optional
from datetime import datetime
from loguru import logger
from pydantic import BaseModel, Field

from app.services.ollama_service import OllamaService
from app.services.context_loader import ContextLoader
from app.services.rag_service import RAGService
from app.models.schemas import AgentResponse


class PipelineInterpreted(BaseModel):
    """Шаг 3: интерпретация сырого ввода в смыслы."""
    intent: str = Field(description="Краткое намерение: вопрос, утверждение, запрос действия, и т.п.")
    entities: List[str] = Field(default_factory=list, description="Упомянутые сущности: люди, проекты, даты")
    key_points: List[str] = Field(default_factory=list, description="Ключевые смыслы/тезисы")
    suggested_recipients: List[str] = Field(default_factory=list, description="Кому может быть адресован вывод, если ясно из текста")


class SevenStepPipeline:
    """
    Pipeline шагов 3–7: интерпретация → обогащение из Notion/RAG → суммаризация → ToV → получатели.
    Каждый шаг вызывается отдельно, переиспользуются RAG, ContextLoader, Ollama.
    """
    
    def __init__(self):
        self.ollama = OllamaService()
        self.context_loader = ContextLoader()
        self.rag = RAGService()
    
    async def step_3_interpret(self, user_input: str) -> PipelineInterpreted:
        """Шаг 3: интерпретация в смыслы (intent, сущности, тезисы)."""
        try:
            prompt = f"""По тексту пользователя выдели намерение, упомянутые сущности и ключевые тезисы.
Текст: "{user_input}"

Верни JSON:
- intent: одно короткое предложение (намерение)
- entities: список упомянутых людей, проектов, дат (пустой массив, если нет)
- key_points: 1–3 ключевых смысла/тезиса
- suggested_recipients: если ясно «кому» пишут — имена/никнеймы, иначе []"""
            out = await self.ollama.generate_structured(
                prompt=prompt,
                response_schema=PipelineInterpreted,
                temperature=0.2
            )
            logger.info("pipeline step_3 interpret: intent=%s", getattr(out, "intent", ""))
            return out
        except Exception as e:
            logger.warning("pipeline step_3 interpret failed: %s", e)
            return PipelineInterpreted(
                intent="не удалось разобрать",
                entities=[],
                key_points=[],
                suggested_recipients=[]
            )
    
    async def step_4_enrich(self, user_input: str, interpreted: PipelineInterpreted) -> List[str]:
        """Шаг 4: сверка со знаниями — RAG (встречи, знания) + люди/проекты из контекста."""
        items: List[str] = []
        try:
            await self.context_loader.ensure_notion_sync()
        except Exception as e:
            logger.debug("pipeline step_4 ensure_notion_sync: %s", e)
        try:
            meetings = await self.rag.search_similar_meetings(user_input, limit=2)
            for m in meetings or []:
                c = m.get("content") or m.get("text")
                if c:
                    items.append(str(c)[:500])
        except Exception as e:
            logger.debug("pipeline step_4 RAG meetings: %s", e)
        try:
            knowledge = await self.rag.search_knowledge(user_input, limit=2)
            for k in knowledge or []:
                c = k.get("content")
                if c:
                    items.append(str(c)[:500])
        except Exception as e:
            logger.debug("pipeline step_4 RAG knowledge: %s", e)
        # Контекст людей/проектов по тексту (resolve_entity — люди и проекты из Notion/JSON)
        try:
            resolved = await self.context_loader.resolve_entity(user_input)
            for p in (resolved.get("people") or [])[:5]:
                desc = (p.get("name") or "") + " " + (p.get("role") or "") + " " + (p.get("context") or "")
                if desc.strip():
                    items.append(desc.strip()[:300])
            for pr in (resolved.get("projects") or [])[:3]:
                desc = (pr.get("name") or pr.get("key") or "") + " " + (pr.get("description") or "")
                if desc.strip():
                    items.append(desc.strip()[:300])
        except Exception as e:
            logger.debug("pipeline step_4 resolve_entity: %s", e)
        logger.info("pipeline step_4 enrich: %d фрагментов", len(items))
        return items
    
    async def step_5_summarize(self, user_input: str, context_items: List[str]) -> str:
        """Шаг 5: суммаризация — сжатие ввода + контекст в короткое саммари."""
        if not context_items:
            context_blob = ""
        else:
            context_blob = "Контекст из базы:\n" + "\n".join(context_items[:6])
        try:
            prompt = f"""Сообщение пользователя: "{user_input}"
{context_blob}

Дай краткое саммари (2–4 предложения): о чём речь, что важно."""
            response = await self.ollama.client.chat(
                model=self.ollama.model_name,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.3, "num_predict": 300}
            )
            text = ""
            if hasattr(response, "message") and hasattr(response.message, "content"):
                text = (response.message.content or "").strip()
            elif isinstance(response, dict):
                text = (response.get("message", {}).get("content") or response.get("response", "") or "").strip()
            if text:
                logger.info("pipeline step_5 summarize: %d символов", len(text))
                return text
        except Exception as e:
            logger.warning("pipeline step_5 summarize failed: %s", e)
        return user_input[:300]
    
    async def step_6_format_tov(self, summary: str, tov_style: str = "brief") -> str:
        """Шаг 6: короткий формат по ToV (tone of voice)."""
        tov_hint = {"brief": "коротко, по делу, 1–2 фразы", "friendly": "дружески, но коротко", "default": "нейтрально, 1–2 фразы"}.get(tov_style.lower(), "коротко, 1–2 фразы")
        try:
            prompt = f"""Саммари: {summary}
Перепиши в стиле ответа в чат: {tov_hint}. Без лишних вступлений."""
            response = await self.ollama.client.chat(
                model=self.ollama.model_name,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.3, "num_predict": 200}
            )
            text = ""
            if hasattr(response, "message") and hasattr(response.message, "content"):
                text = (response.message.content or "").strip()
            elif isinstance(response, dict):
                text = (response.get("message", {}).get("content") or response.get("response", "") or "").strip()
            if text:
                return text
        except Exception as e:
            logger.warning("pipeline step_6 tov failed: %s", e)
        return summary[:200]
    
    async def step_7_resolve_recipients(
        self,
        interpreted: PipelineInterpreted,
        sender_chat_id: Optional[str]
    ) -> List[str]:
        """Шаг 7: сверка с никами — кому отправить (chat_id). По умолчанию — отправитель."""
        if not sender_chat_id:
            return []
        recipients: List[str] = []
        suggested = interpreted.suggested_recipients or []
        if not suggested:
            return [str(sender_chat_id)]
        try:
            from app.services.agents.message_agent import MessageAgent
            msg_agent = MessageAgent()
            for r in suggested[:3]:
                cid = await msg_agent._resolve_recipient_to_chat_id(r, sender_chat_id)
                if cid and cid not in recipients:
                    recipients.append(str(cid))
        except Exception as e:
            logger.debug("pipeline step_7 resolve_recipients: %s", e)
        if not recipients:
            return [str(sender_chat_id)]
        return recipients
    
    async def run(
        self,
        user_input: str,
        sender_chat_id: Optional[str] = None,
        sender_username: Optional[str] = None
    ) -> AgentResponse:
        """
        Запуск pipeline шагов 3–7 подряд. Возвращает AgentResponse, совместимый с роутером.
        """
        start = datetime.now()
        steps: Dict[str, Any] = {}
        tov_style = "brief"
        try:
            interpreted = await self.step_3_interpret(user_input)
            steps["interpreted"] = {
                "intent": interpreted.intent,
                "entities": interpreted.entities,
                "key_points": interpreted.key_points,
            }
            context_items = await self.step_4_enrich(user_input, interpreted)
            steps["context_items_count"] = len(context_items)
            summary = await self.step_5_summarize(user_input, context_items)
            steps["summary_len"] = len(summary)
            formatted = await self.step_6_format_tov(summary, tov_style)
            steps["formatted_len"] = len(formatted)
            recipient_ids = await self.step_7_resolve_recipients(interpreted, sender_chat_id)
            steps["recipient_chat_ids"] = recipient_ids
        except Exception as e:
            logger.error("pipeline run failed: %s", e, exc_info=True)
            return AgentResponse(
                agent_type="pipeline",
                response="Не удалось пройти полный цикл. Ошибка: " + str(e)[:100],
                actions=[],
                metadata={"error": str(e), "steps": steps, "pipeline_failed": True}
            )
        elapsed_ms = int((datetime.now() - start).total_seconds() * 1000)
        return AgentResponse(
            agent_type="pipeline",
            response=formatted,
            actions=[{"type": "pipeline_completed", "steps": list(steps.keys())}],
            metadata={
                "decision_trace": {
                    "selected_agent": "pipeline",
                    "pipeline_steps": steps,
                    "processing_time_ms": elapsed_ms,
                    "start_time": start.isoformat(),
                },
                "recipient_chat_ids": steps.get("recipient_chat_ids", [sender_chat_id] if sender_chat_id else []),
            }
        )
