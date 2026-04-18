# documents/ai_search.py
import json
import logging
import os
import urllib.error
import urllib.request
import re

from django.conf import settings
from documents.models import InfoSnippet

logger = logging.getLogger(__name__)

# Используем основную модель Яндекса
DEFAULT_MODEL = "yandexgpt-5.1/latest"


def _build_yandex_openai_payload(system_prompt: str, user_prompt: str, folder_id: str, model_type: str):
    if model_type.startswith("gpt://"):
        model_uri = model_type
    elif "/" in model_type:
        model_uri = f"gpt://{folder_id}/{model_type}"
    else:
        model_uri = f"gpt://{folder_id}/{model_type}/latest"

    return {
        "model": model_uri,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.1,  # Низкая температура, чтобы ИИ не фантазировал, а отвечал строго по тексту
        "max_tokens": 2000
    }


def _call_yandex(system_prompt: str, user_prompt: str):
    api_key = os.getenv("YANDEX_API_KEY", "") or getattr(settings, "YANDEX_API_KEY", "")
    folder_id = os.getenv("YANDEX_FOLDER_ID", "") or getattr(settings, "YANDEX_FOLDER_ID", "")
    model_type = os.getenv("YANDEX_MODEL", "") or getattr(settings, "YANDEX_MODEL", DEFAULT_MODEL)

    if not api_key or not folder_id:
        return None, "YANDEX_API_KEY или YANDEX_FOLDER_ID не заданы в .env"

    url = "https://ai.api.cloud.yandex.net/v1/chat/completions"
    payload = _build_yandex_openai_payload(system_prompt, user_prompt, folder_id, model_type)

    if api_key.startswith("t1.") or api_key.startswith("t2."):
        auth_header = f"Bearer {api_key}"
    else:
        auth_header = f"Api-Key {api_key}"

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": auth_header,
            "x-folder-id": folder_id
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            choices = data.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "").strip(), None
            return None, "Пустой ответ от Yandex GPT"
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        logger.exception("Yandex HTTPError in AI Search")
        return None, f"Ошибка API: {exc.code} - {body}"
    except Exception as exc:
        logger.exception("Yandex Unknown Error in AI Search")
        return None, str(exc)


def search_knowledge_base(query: str):
    # Бьем запрос на ключевые слова
    words = [w.lower() for w in re.findall(r'\w+', query) if len(w) > 2]
    
    # Берем все документы базы знаний
    snippets = InfoSnippet.objects.select_related('section').all()

    if not snippets.exists():
        return "База знаний пока пуста. Добавьте документы через админ-панель."

    # Простой алгоритм релевантности (считаем совпадения слов)
    ranked = []
    for snip in snippets:
        score = 0
        text = f"{snip.title} {snip.content}".lower()
        for w in words:
            if w in text:
                score += 1
        ranked.append((score, snip))

    # Сортируем и берем Топ-15 самых подходящих документов (чтобы не перегрузить ИИ)
    ranked.sort(key=lambda x: x[0], reverse=True)
    top_snippets = [r[1] for r in ranked[:15]]

    # Формируем контекст для нейросети
    context_text = "\n\n".join([
        f"--- Документ ---\nНазвание: {s.title}\nТекст: {s.content}"
        for s in top_snippets
    ])

    system_prompt = (
        "Ты — умный корпоративный ИИ-помощник компании Students Life.\n"
        "Твоя задача — отвечать на вопросы сотрудников СТРОГО на основе предоставленных Документов из Базы Знаний.\n\n"
        "ПРАВИЛА:\n"
        "1. Отвечай ТОЛЬКО опираясь на текст из блока 'НАЙДЕННЫЕ ДОКУМЕНТЫ В БАЗЕ ЗНАНИЙ'.\n"
        "2. Если в документах нет ответа на вопрос, ответь: «К сожалению, в текущей базе знаний нет ответа на этот вопрос.» Не придумывай информацию от себя!\n"
        "3. В конце своего ответа ОБЯЗАТЕЛЬНО укажи источники, которые ты использовал, в формате: \n\n**Источники:**\n- Название документа 1\n- Название документа 2\n"
        "4. Оформляй ответ красиво, используй Markdown (жирный текст, списки)."
    )

    user_prompt = f"Вопрос пользователя: {query}\n\nНАЙДЕННЫЕ ДОКУМЕНТЫ В БАЗЕ ЗНАНИЙ:\n{context_text}"

    answer, err = _call_yandex(system_prompt, user_prompt)
    if err:
        return f"**Ошибка при обращении к ИИ:**\n{err}"

    return answer