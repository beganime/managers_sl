# documents/ai_search.py
import json
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple

from django.conf import settings
from documents.models import InfoSnippet, KnowledgeSection

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "yandexgpt-5.1/latest"

MAX_SNIPPETS_FOR_AI = 12
MAX_SNIPPETS_FOR_OVERVIEW = 25
MAX_CONTEXT_CHARS_PER_SNIPPET = 1800
MIN_RELEVANCE_SCORE = 2.0


BASE_ASSISTANT_INTRO = (
    "Здравствуйте, я ИИ ассистент компании Students Life, чем могу помочь?"
)


CATEGORY_LABELS = {
    "script": "Скрипты продаж",
    "faq": "Ответы на частые вопросы",
    "requisites": "Реквизиты и счета",
    "links": "Полезные ссылки",
}


BASIC_INTENTS = {
    "hello": {
        "answer": BASE_ASSISTANT_INTRO,
        "phrases": [
            "привет", "здравствуйте", "здравствуй", "добрый день", "доброе утро",
            "добрый вечер", "салам", "hello", "hi", "hey", "првет", "привт",
            "здраствуйте", "здраствуй", "дарова",
        ],
    },
    "identity": {
        "answer": BASE_ASSISTANT_INTRO,
        "phrases": [
            "кто ты", "как тебя зовут", "ты кто", "что ты такое", "как звать",
            "тебя как зовут", "кто ты такой", "кто ты такая", "как тибя зовут",
            "как тбя зовут", "как тябя зовут", "кто ти", "как тебя звать",
            "who are you", "what is your name",
        ],
    },
    "thanks": {
        "answer": (
            "Пожалуйста. Если нужно, я могу помочь найти информацию в базе знаний "
            "Students Life: по вузам, скриптам продаж, документам, оплатам, визам, "
            "заявкам и внутренним инструкциям."
        ),
        "phrases": [
            "спасибо", "благодарю", "рахмет", "thanks", "thank you", "спс",
            "спосибо", "пасиба",
        ],
    },
    "bye": {
        "answer": "Хорошо, обращайтесь. Я всегда могу помочь с поиском по базе знаний Students Life.",
        "phrases": [
            "пока", "до свидания", "увидимся", "bye", "goodbye", "все спасибо",
            "всё спасибо",
        ],
    },
    "help": {
        "answer": (
            "Я могу помочь с поиском по базе знаний Students Life.\n\n"
            "**Что можно спросить:**\n"
            "- информацию про вузы, страны, поступление;\n"
            "- скрипты продаж и ответы клиентам;\n"
            "- документы, визы, оплаты, реквизиты;\n"
            "- внутренние инструкции и частые вопросы.\n\n"
            "Например: «найди скрипт для клиента, который сомневается», "
            "«что есть по вузам Китая», «какие документы нужны для поступления»."
        ),
        "phrases": [
            "что ты умеешь", "помощь", "help", "как пользоваться", "что спросить",
            "что можешь", "помоги", "инструкция",
        ],
    },
}


BROWSE_TOPICS = {
    "universities": {
        "label": "вузы / университеты / поступление",
        "aliases": [
            "вуз", "вузы", "университет", "университеты", "институт", "академия",
            "поступление", "учеба", "обучение", "страны", "китай", "россия",
            "турция", "малайзия", "кипр", "казахстан", "узбекистан", "беларусь",
            "корея", "европа", "бакалавриат", "магистратура", "foundation",
            "подкурс", "подготовительный курс",
        ],
    },
    "sales_scripts": {
        "label": "скрипты продаж",
        "aliases": [
            "скрипт", "скрипты", "скрипты продаж", "продажи", "возражения",
            "как ответить клиенту", "что сказать клиенту", "звонок", "переписка",
            "диалог", "лид", "клиент сомневается", "дожим", "продать",
        ],
    },
    "documents": {
        "label": "документы",
        "aliases": [
            "документ", "документы", "паспорт", "аттестат", "диплом",
            "перевод", "нотариус", "справка", "фото", "анкета", "заявление",
            "доверенность", "сертификат", "легализация", "апостиль",
        ],
    },
    "visa": {
        "label": "визы / приглашения",
        "aliases": [
            "виза", "визу", "приглашение", "посольство", "консульство",
            "миграция", "регистрация", "въезд", "выезд", "visa",
        ],
    },
    "payments": {
        "label": "оплаты / реквизиты / финансы",
        "aliases": [
            "оплата", "оплаты", "деньги", "счет", "счёт", "реквизиты",
            "касса", "чек", "долг", "рассрочка", "скидка", "платеж",
            "платёж", "доход", "расход",
        ],
    },
    "links": {
        "label": "полезные ссылки",
        "aliases": [
            "ссылка", "ссылки", "сайт", "официальный сайт", "линк", "url",
            "где посмотреть", "откуда взять",
        ],
    },
}


SYNONYMS = {
    "вуз": ["университет", "институт", "академия", "поступление", "обучение"],
    "вузы": ["университеты", "институты", "академии", "поступление", "обучение"],
    "универ": ["университет", "вуз"],
    "подкурс": ["подготовительный курс", "foundation", "языковой курс"],
    "кб": ["база знаний", "knowledge base"],
    "скрипт": ["скрипты продаж", "продажи", "возражения", "клиент"],
    "продажа": ["скрипт", "клиент", "лид", "возражения"],
    "док": ["документ", "документы"],
    "доки": ["документы", "паспорт", "аттестат", "диплом"],
    "оплата": ["платеж", "платёж", "деньги", "касса", "чек"],
    "счет": ["счёт", "реквизиты", "оплата"],
    "счёт": ["счет", "реквизиты", "оплата"],
    "виза": ["приглашение", "посольство", "консульство"],
    "клиент": ["лид", "заявка", "студент", "абитуриент"],
    "заявка": ["лид", "клиент", "абитуриент"],
}


STOP_WORDS = {
    "что", "как", "где", "кто", "когда", "почему", "зачем", "мне", "нам",
    "тебя", "тебе", "меня", "надо", "нужно", "можно", "есть", "это",
    "про", "по", "для", "или", "если", "то", "же", "ли", "из", "на",
    "в", "во", "с", "со", "а", "и", "да", "нет", "найди", "найти",
    "покажи", "скажи", "напиши", "объясни", "информация", "инфу",
}


def _build_yandex_openai_payload(
    system_prompt: str,
    user_prompt: str,
    folder_id: str,
    model_type: str,
):
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
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.15,
        "max_tokens": 2500,
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
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": auth_header,
            "x-folder-id": folder_id,
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


def _normalize_text(value: str) -> str:
    text = str(value or "").lower().replace("ё", "е")
    text = text.replace("students life", "studentslife")
    text = re.sub(r"[^a-zа-я0-9\s\-_/+]", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _tokens(value: str) -> List[str]:
    normalized = _normalize_text(value)
    result = []
    for token in re.findall(r"[a-zа-я0-9]+", normalized, flags=re.IGNORECASE):
        if len(token) <= 2:
            continue
        if token in STOP_WORDS:
            continue
        result.append(token)
    return result


def _similarity(a: str, b: str) -> float:
    a = _normalize_text(a)
    b = _normalize_text(b)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _token_fuzzy_match(token: str, words: List[str], threshold: float = 0.82) -> bool:
    if not token or len(token) <= 3:
        return False

    for word in words:
        if len(word) <= 3:
            continue
        if token in word or word in token:
            return True
        if SequenceMatcher(None, token, word).ratio() >= threshold:
            return True

    return False


def _expand_query_tokens(query: str) -> List[str]:
    base_tokens = _tokens(query)
    expanded = list(base_tokens)

    for token in base_tokens:
        for key, values in SYNONYMS.items():
            if token == key or _similarity(token, key) >= 0.84:
                expanded.extend(_tokens(" ".join(values)))

    seen = set()
    clean = []
    for item in expanded:
        if item not in seen:
            clean.append(item)
            seen.add(item)

    return clean


def _matches_phrase_or_fuzzy(query: str, phrases: List[str], threshold: float = 0.76) -> bool:
    normalized_query = _normalize_text(query)

    if not normalized_query:
        return False

    for phrase in phrases:
        normalized_phrase = _normalize_text(phrase)

        if normalized_phrase and normalized_phrase in normalized_query:
            return True

        if _similarity(normalized_query, normalized_phrase) >= threshold:
            return True

    query_tokens = _tokens(normalized_query)
    phrase_tokens = []
    for phrase in phrases:
        phrase_tokens.extend(_tokens(phrase))

    if not query_tokens or not phrase_tokens:
        return False

    matched = 0
    for token in query_tokens:
        if _token_fuzzy_match(token, phrase_tokens, threshold=0.78):
            matched += 1

    return matched >= max(1, min(2, len(query_tokens)))


def _detect_basic_intent(query: str) -> Optional[str]:
    normalized = _normalize_text(query)
    if not normalized:
        return None

    for intent, config in BASIC_INTENTS.items():
        if _matches_phrase_or_fuzzy(normalized, config["phrases"]):
            return intent

    return None


def _get_section_path(section) -> str:
    if not section:
        return "Без раздела"

    try:
        return section.full_path or section.title or "Без раздела"
    except Exception:
        return getattr(section, "title", None) or "Без раздела"


def _get_category_label(category: str) -> str:
    return CATEGORY_LABELS.get(category, category or "Без категории")


def _truncate(value: str, limit: int = 500) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


def _internet_search_links(query: str) -> str:
    encoded = urllib.parse.quote_plus(str(query or "").strip())
    if not encoded:
        encoded = urllib.parse.quote_plus("Students Life информация")

    return (
        "**Можно проверить в интернете:**\n"
        f"- Яндекс: https://yandex.ru/search/?text={encoded}\n"
        f"- Google: https://www.google.com/search?q={encoded}\n\n"
        "Важно: я могу подсказать направление поиска, но точный корпоративный ответ лучше добавлять в базу знаний, "
        "чтобы сотрудники потом находили его внутри приложения."
    )


def _load_knowledge():
    snippets = list(
        InfoSnippet.objects.select_related("section").all().order_by(
            "section__order", "category", "order", "title"
        )
    )
    sections = list(
        KnowledgeSection.objects.filter(is_active=True).select_related("parent").order_by(
            "parent__id", "order", "title"
        )
    )
    return snippets, sections


def _score_snippet(query: str, snippet, query_tokens: List[str]) -> float:
    title = getattr(snippet, "title", "") or ""
    content = getattr(snippet, "content", "") or ""
    category = getattr(snippet, "category", "") or ""
    section = getattr(snippet, "section", None)
    section_path = _get_section_path(section)

    title_norm = _normalize_text(title)
    content_norm = _normalize_text(content)
    section_norm = _normalize_text(section_path)
    category_norm = _normalize_text(_get_category_label(category))

    title_words = _tokens(title_norm)
    content_words = _tokens(content_norm[:5000])
    section_words = _tokens(section_norm)
    category_words = _tokens(category_norm)

    score = 0.0
    normalized_query = _normalize_text(query)

    if normalized_query and normalized_query in title_norm:
        score += 20
    if normalized_query and normalized_query in section_norm:
        score += 16
    if normalized_query and normalized_query in content_norm:
        score += 10

    for token in query_tokens:
        if token in title_norm:
            score += 7
        if token in section_norm:
            score += 6
        if token in category_norm:
            score += 5
        if token in content_norm:
            score += 2

        if _token_fuzzy_match(token, title_words, threshold=0.80):
            score += 4
        if _token_fuzzy_match(token, section_words, threshold=0.80):
            score += 4
        if _token_fuzzy_match(token, category_words, threshold=0.80):
            score += 3
        if _token_fuzzy_match(token, content_words[:350], threshold=0.84):
            score += 1

    for topic in BROWSE_TOPICS.values():
        if _matches_phrase_or_fuzzy(query, topic["aliases"], threshold=0.78):
            topic_tokens = _tokens(" ".join(topic["aliases"]))
            haystack = f"{title_norm} {section_norm} {category_norm}"
            if any(token in haystack for token in topic_tokens):
                score += 5

    return score


def _rank_snippets(query: str, snippets: List) -> List[Tuple[float, object]]:
    query_tokens = _expand_query_tokens(query)

    ranked = []
    for snippet in snippets:
        score = _score_snippet(query, snippet, query_tokens)
        ranked.append((score, snippet))

    ranked.sort(
        key=lambda item: (
            item[0],
            getattr(item[1], "updated_at", None) is not None,
            getattr(item[1], "id", 0) or 0,
        ),
        reverse=True,
    )
    return ranked


def _detect_browse_topic(query: str) -> Optional[Dict[str, object]]:
    for key, topic in BROWSE_TOPICS.items():
        if _matches_phrase_or_fuzzy(query, topic["aliases"], threshold=0.75):
            return {
                "key": key,
                "label": topic["label"],
                "aliases": topic["aliases"],
            }
    return None


def _is_broad_browse_query(query: str) -> bool:
    normalized = _normalize_text(query)

    broad_markers = [
        "что есть", "какая информация", "какие материалы", "покажи папку",
        "покажи раздел", "найди папку", "найди информацию", "информация про",
        "что у нас есть", "что есть по", "есть ли информация", "дай список",
        "покажи все", "покажи всё", "вся информация", "всю информацию",
    ]

    if any(marker in normalized for marker in broad_markers):
        return True

    words = _tokens(query)
    if len(words) <= 3 and _detect_browse_topic(query):
        return True

    return False


def _find_matching_sections(query: str, sections: List) -> List:
    query_tokens = _expand_query_tokens(query)
    ranked = []

    for section in sections:
        path = _get_section_path(section)
        title = getattr(section, "title", "") or ""
        haystack = f"{title} {path}"
        hay_tokens = _tokens(haystack)

        score = 0.0
        normalized_query = _normalize_text(query)
        normalized_haystack = _normalize_text(haystack)

        if normalized_query and normalized_query in normalized_haystack:
            score += 15

        for token in query_tokens:
            if token in normalized_haystack:
                score += 4
            if _token_fuzzy_match(token, hay_tokens, threshold=0.80):
                score += 2

        if score > 0:
            ranked.append((score, section))

    ranked.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in ranked[:10]]


def _render_folder_overview(query: str, ranked: List[Tuple[float, object]], sections: List) -> str:
    topic = _detect_browse_topic(query)
    topic_label = topic["label"] if topic else "запрошенной теме"

    useful_ranked = [(score, snippet) for score, snippet in ranked if score >= MIN_RELEVANCE_SCORE]
    useful_snippets = [snippet for _, snippet in useful_ranked[:MAX_SNIPPETS_FOR_OVERVIEW]]
    matching_sections = _find_matching_sections(query, sections)

    if not useful_snippets and not matching_sections:
        return (
            f"Я понял, что вы ищете информацию по теме **«{topic_label}»**, "
            "но в текущей базе знаний я не нашёл подходящих материалов.\n\n"
            "Что можно сделать:\n"
            "1. Попробуйте спросить другими словами.\n"
            "2. Проверьте, добавлена ли эта информация в базу знаний.\n"
            "3. Если информация нужна срочно, можно проверить в интернете.\n\n"
            f"{_internet_search_links(query)}"
        )

    grouped: Dict[str, List[object]] = {}
    for snippet in useful_snippets:
        section_path = _get_section_path(getattr(snippet, "section", None))
        grouped.setdefault(section_path, []).append(snippet)

    lines = []
    lines.append(f"Я нашёл информацию по теме **«{topic_label}»** в базе знаний Students Life.")
    lines.append("")

    if matching_sections:
        lines.append("**Подходящие разделы / папки:**")
        for section in matching_sections[:8]:
            lines.append(f"- { _get_section_path(section) }")
        lines.append("")

    if grouped:
        lines.append("**Найденные материалы:**")
        for section_path, items in grouped.items():
            lines.append(f"\n📁 **{section_path}**")
            for snippet in items[:8]:
                category_label = _get_category_label(getattr(snippet, "category", ""))
                title = getattr(snippet, "title", "Без названия")
                content = _truncate(getattr(snippet, "content", ""), 220)
                lines.append(f"- **{title}** · {category_label}")
                if content:
                    lines.append(f"  {content}")

    lines.append("")
    lines.append(
        "Что конкретнее вам нужно: условия поступления, документы, цены, скрипт ответа клиенту, "
        "виза, оплата или конкретный университет/страна?"
    )

    return "\n".join(lines)


def _build_context_text(top_ranked: List[Tuple[float, object]]) -> str:
    context_parts = []

    for index, (score, snippet) in enumerate(top_ranked, start=1):
        section_path = _get_section_path(getattr(snippet, "section", None))
        category_label = _get_category_label(getattr(snippet, "category", ""))
        title = getattr(snippet, "title", "Без названия")
        content = _truncate(
            getattr(snippet, "content", "") or "",
            MAX_CONTEXT_CHARS_PER_SNIPPET,
        )

        context_parts.append(
            f"--- Документ {index} ---\n"
            f"Релевантность: {round(score, 2)}\n"
            f"Раздел/папка: {section_path}\n"
            f"Категория: {category_label}\n"
            f"Название: {title}\n"
            f"Текст: {content}"
        )

    return "\n\n".join(context_parts)


def _build_sources_list(top_ranked: List[Tuple[float, object]]) -> str:
    sources = []
    seen = set()

    for _, snippet in top_ranked:
        title = getattr(snippet, "title", "Без названия")
        section_path = _get_section_path(getattr(snippet, "section", None))
        key = f"{section_path}::{title}"

        if key in seen:
            continue

        sources.append(f"- {section_path} → {title}")
        seen.add(key)

    if not sources:
        return "- Источники не найдены"

    return "\n".join(sources)


def _fallback_local_answer(query: str, top_ranked: List[Tuple[float, object]]) -> str:
    if not top_ranked:
        return (
            "К сожалению, в текущей базе знаний нет точного ответа на этот вопрос.\n\n"
            "Я могу подсказать направление поиска:\n\n"
            f"{_internet_search_links(query)}"
        )

    lines = []
    lines.append("Я нашёл похожую информацию в базе знаний Students Life.")
    lines.append("")
    lines.append("**Краткий ответ по найденным материалам:**")

    for index, (_, snippet) in enumerate(top_ranked[:5], start=1):
        title = getattr(snippet, "title", "Без названия")
        content = _truncate(getattr(snippet, "content", ""), 500)
        section_path = _get_section_path(getattr(snippet, "section", None))
        category_label = _get_category_label(getattr(snippet, "category", ""))

        lines.append("")
        lines.append(f"{index}. **{title}**")
        lines.append(f"   Раздел: {section_path}")
        lines.append(f"   Категория: {category_label}")
        if content:
            lines.append(f"   {content}")

    lines.append("")
    lines.append("**Источники:**")
    lines.append(_build_sources_list(top_ranked[:5]))
    lines.append("")
    lines.append(
        "Если нужно, уточните вопрос: страна, вуз, клиентская ситуация, документы, оплата или скрипт продаж."
    )

    return "\n".join(lines)


def _build_system_prompt() -> str:
    return (
        "Ты — корпоративный ИИ ассистент компании Students Life.\n"
        "Ты помогаешь сотрудникам искать информацию в базе знаний компании.\n\n"
        "Главные правила:\n"
        "1. Отвечай дружелюбно, но делово.\n"
        "2. Основной источник ответа — только документы из блока базы знаний.\n"
        "3. Не выдумывай факты, цены, правила вузов, визовые условия и сроки.\n"
        "4. Если точного ответа нет, так и скажи: «В базе знаний нет точного ответа».\n"
        "5. Если вопрос широкий, перечисли найденные разделы и спроси, что уточнить.\n"
        "6. Если пользователь спрашивает про интернет, объясни, что лучше проверить актуальность по официальным источникам.\n"
        "7. В конце обязательно укажи источники из базы знаний.\n"
        "8. Пиши на русском, если пользователь не просит другой язык.\n"
        "9. Не называй себя Yandex GPT, ChatGPT или внешней моделью. Ты — ИИ ассистент Students Life.\n"
        "10. Если в вопросе есть ошибки или опечатки, попытайся понять смысл по контексту.\n"
    )


def _build_user_prompt(query: str, context_text: str, sources_text: str) -> str:
    return (
        f"Вопрос пользователя:\n{query}\n\n"
        f"НАЙДЕННЫЕ ДОКУМЕНТЫ В БАЗЕ ЗНАНИЙ:\n{context_text}\n\n"
        f"СПИСОК ИСТОЧНИКОВ:\n{sources_text}\n\n"
        "Сформируй ответ:\n"
        "- сначала короткий понятный ответ;\n"
        "- затем детали из базы знаний;\n"
        "- затем, если нужно, уточняющий вопрос;\n"
        "- в конце блок **Источники:**."
    )


def _render_no_relevant_answer(query: str, snippets_count: int) -> str:
    return (
        "Я понял ваш вопрос, но в базе знаний Students Life не нашёл достаточно точной информации.\n\n"
        f"В базе сейчас есть материалов: {snippets_count}.\n\n"
        "Что можно сделать:\n"
        "1. Уточните запрос: страна, вуз, документ, оплата, виза, скрипт продаж или клиентская ситуация.\n"
        "2. Попробуйте написать другими словами.\n"
        "3. Если вопрос срочный и информации нет в базе, проверьте актуальность в интернете.\n\n"
        f"{_internet_search_links(query)}"
    )


def search_knowledge_base(query: str):
    """
    Главная функция для endpoint /ask_ai/.
    Возвращает строку, потому что documents/views.py ожидает {'answer': answer}.
    """
    query = str(query or "").strip()

    if not query:
        return "Введите ваш вопрос. Например: «что есть по вузам Китая?» или «найди скрипт продаж»."

    basic_intent = _detect_basic_intent(query)
    if basic_intent:
        return BASIC_INTENTS[basic_intent]["answer"]

    try:
        snippets, sections = _load_knowledge()
    except Exception as exc:
        logger.exception("AI Search failed to load knowledge base")
        return (
            "Не удалось загрузить базу знаний с сервера.\n\n"
            "Возможные причины:\n"
            "1. Таблица базы знаний ещё не создана миграциями.\n"
            "2. Есть ошибка подключения к базе данных.\n"
            "3. Сервер временно не может прочитать документы.\n\n"
            f"Техническая ошибка: {exc}"
        )

    if not snippets:
        return (
            "База знаний пока пуста. Добавьте материалы через админ-панель: "
            "разделы, скрипты продаж, FAQ, документы, ссылки и инструкции."
        )

    ranked = _rank_snippets(query, snippets)
    relevant_ranked = [
        item for item in ranked
        if item[0] >= MIN_RELEVANCE_SCORE
    ]

    if _is_broad_browse_query(query):
        return _render_folder_overview(query, ranked, sections)

    if not relevant_ranked:
        return _render_no_relevant_answer(query, snippets_count=len(snippets))

    top_ranked = relevant_ranked[:MAX_SNIPPETS_FOR_AI]
    context_text = _build_context_text(top_ranked)
    sources_text = _build_sources_list(top_ranked)

    system_prompt = _build_system_prompt()
    user_prompt = _build_user_prompt(query, context_text, sources_text)

    answer, err = _call_yandex(system_prompt, user_prompt)

    if answer:
        return answer

    logger.warning("Yandex AI Search unavailable, using local fallback. Error: %s", err)

    fallback = _fallback_local_answer(query, top_ranked[:6])

    if err:
        fallback += (
            "\n\n"
            "**Примечание для администратора:** внешний AI сейчас недоступен, "
            "поэтому показан локальный ответ по найденным материалам.\n"
            f"Ошибка AI: {err}"
        )

    return fallback