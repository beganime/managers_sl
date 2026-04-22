# documents/ai_search.py
import logging
import re
import time
import urllib.parse
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple

from documents.models import InfoSnippet, KnowledgeSection

logger = logging.getLogger(__name__)

# Локальный AI-поиск Students Life.
# Внешний ИИ полностью отключён: никаких Yandex GPT / OpenAI / Gemini API.
# Ответы строятся только локально: приветствия, команды, fuzzy-поиск, база знаний.

THINKING_DELAY_SECONDS = 2

MAX_SNIPPETS_FOR_OVERVIEW = 25
MAX_SNIPPETS_FOR_ANSWER = 8
MAX_CONTENT_PREVIEW_CHARS = 700
MAX_COPY_CONTENT_CHARS = 3000
MIN_RELEVANCE_SCORE = 2.0

COPY_FENCE = "`" * 3

ASSISTANT_NAME = "ИИ ассистент компании Students Life"
AUTHOR_NAME = "Ягмуров Бегенч"
DEVELOPER_NAME = "Ягмуров Бегенч"
DEVELOPER_CONTACTS = "begenchyagmurow2008@gmail.com / @beganime (телеграм)"

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
            "здраствуйте", "здраствуй", "дарова", "салам алейкум",
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
    "author": {
        "answer": (
            f"Автор ИИ этого проекта — **{AUTHOR_NAME}**.\n\n"
            f"Разработчик программы — **{DEVELOPER_NAME}**.\n\n"
            f"Контакты разработчика: **{DEVELOPER_CONTACTS}**."
        ),
        "phrases": [
            "автор ии", "кто автор ии", "автор этого ии", "кто сделал ии",
            "кто создал ии", "кто автор", "создатель ии", "разработчик ии",
            "кто разработал ии", "автор ассистента", "кто создал ассистента",
        ],
    },
    "developer": {
        "answer": (
            f"Разработчик программы — **{DEVELOPER_NAME}**.\n\n"
            f"Контакты разработчика: **{DEVELOPER_CONTACTS}**."
        ),
        "phrases": [
            "разработчик программы", "кто разработчик программы", "кто разработал программу",
            "разработчик приложения", "кто разработчик", "кто сделал программу",
            "кто сделал приложение", "кто создатель программы", "кто написал программу",
            "программист", "разраб", "developer",
        ],
    },
    "contacts": {
        "answer": (
            f"Контакты разработчика:\n\n"
            f"- Email: **begenchyagmurow2008@gmail.com**\n"
            f"- Telegram: **@beganime**"
        ),
        "phrases": [
            "контакты разработчика", "контакт разработчика", "как связаться с разработчиком",
            "телеграм разработчика", "telegram разработчика", "email разработчика",
            "почта разработчика", "контакты автора", "контакты программиста",
            "связь с разработчиком",
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
            "спосибо", "пасиба", "благодарю вас",
        ],
    },
    "bye": {
        "answer": "Хорошо, обращайтесь. Я всегда могу помочь с поиском по базе знаний Students Life.",
        "phrases": [
            "пока", "до свидания", "увидимся", "bye", "goodbye", "все спасибо",
            "всё спасибо", "до встречи",
        ],
    },
    "help": {
        "answer": (
            "Я могу помочь с поиском по базе знаний Students Life.\n\n"
            "**Что можно спросить:**\n"
            "- информацию про вузы, страны, поступление;\n"
            "- скрипты продаж и ответы клиентам;\n"
            "- документы, визы, оплаты, реквизиты;\n"
            "- внутренние инструкции и частые вопросы;\n"
            "- контакты разработчика или автора ИИ.\n\n"
            "**Примеры запросов:**\n"
            "- «Что есть по вузам Китая?»\n"
            "- «Найди скрипт для клиента, который сомневается»\n"
            "- «Какие документы нужны для поступления?»\n"
            "- «Кто разработчик программы?»"
        ),
        "phrases": [
            "что ты умеешь", "помощь", "help", "как пользоваться", "что спросить",
            "что можешь", "помоги", "инструкция", "как с тобой работать",
        ],
    },
}


BROWSE_TOPICS = {
    "universities": {
        "label": "вузы / университеты / поступление",
        "aliases": [
            "вуз", "вузы", "вузи", "университет", "университеты", "универ",
            "институт", "академия", "поступление", "паступление", "учеба",
            "учёба", "обучение", "страны", "китай", "россия", "турция",
            "малайзия", "кипр", "казахстан", "узбекистан", "беларусь",
            "корея", "европа", "бакалавриат", "магистратура", "foundation",
            "подкурс", "подготовительный курс", "языковой курс",
        ],
    },
    "sales_scripts": {
        "label": "скрипты продаж",
        "aliases": [
            "скрипт", "скрипты", "скрпит", "скрпиты", "скрипты продаж",
            "продажи", "продажа", "возражения", "как ответить клиенту",
            "что сказать клиенту", "звонок", "переписка", "диалог", "лид",
            "клиент сомневается", "дожим", "продать", "продавать",
        ],
    },
    "documents": {
        "label": "документы",
        "aliases": [
            "документ", "документы", "доки", "док", "паспорт", "аттестат",
            "диплом", "перевод", "нотариус", "справка", "фото", "анкета",
            "заявление", "доверенность", "сертификат", "легализация", "апостиль",
        ],
    },
    "visa": {
        "label": "визы / приглашения",
        "aliases": [
            "виза", "визу", "визы", "приглашение", "приглошение", "посольство",
            "консульство", "миграция", "регистрация", "въезд", "выезд", "visa",
        ],
    },
    "payments": {
        "label": "оплаты / реквизиты / финансы",
        "aliases": [
            "оплата", "оплаты", "аплата", "деньги", "счет", "счёт", "реквизиты",
            "касса", "чек", "долг", "рассрочка", "скидка", "платеж", "платёж",
            "доход", "расход", "финансы",
        ],
    },
    "links": {
        "label": "полезные ссылки",
        "aliases": [
            "ссылка", "ссылки", "сайт", "официальный сайт", "линк", "url",
            "где посмотреть", "откуда взять", "полезные ссылки",
        ],
    },
}


SYNONYMS = {
    "вуз": ["университет", "институт", "академия", "поступление", "обучение"],
    "вузы": ["университеты", "институты", "академии", "поступление", "обучение"],
    "вузи": ["вузы", "университеты", "поступление"],
    "универ": ["университет", "вуз"],
    "университет": ["вуз", "поступление", "обучение"],
    "подкурс": ["подготовительный курс", "foundation", "языковой курс"],
    "кб": ["база знаний", "knowledge base"],
    "скрипт": ["скрипты продаж", "продажи", "возражения", "клиент"],
    "скрпит": ["скрипт", "скрипты продаж"],
    "скрпиты": ["скрипты", "скрипты продаж"],
    "продажа": ["скрипт", "клиент", "лид", "возражения"],
    "продажи": ["скрипт", "клиент", "лид", "возражения"],
    "док": ["документ", "документы"],
    "доки": ["документы", "паспорт", "аттестат", "диплом"],
    "документ": ["документы", "паспорт", "аттестат", "диплом"],
    "оплата": ["платеж", "платёж", "деньги", "касса", "чек"],
    "аплата": ["оплата", "платеж", "деньги"],
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
    "дай", "нужна", "нужен", "хочу", "можешь", "пожалуйста",
}


def _apply_thinking_delay():
    if THINKING_DELAY_SECONDS and THINKING_DELAY_SECONDS > 0:
        time.sleep(THINKING_DELAY_SECONDS)


def _normalize_text(value: str) -> str:
    text = str(value or "").lower().replace("ё", "е")
    text = text.replace("students life", "studentslife")
    text = text.replace("student's life", "studentslife")
    text = text.replace("students-life", "studentslife")
    text = re.sub(r"[^a-zа-я0-9\s\-_/+@.]", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _tokens(value: str) -> List[str]:
    normalized = _normalize_text(value)
    result = []

    for token in re.findall(r"[a-zа-я0-9@.]+", normalized, flags=re.IGNORECASE):
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

    # Сначала проверяем служебные команды, чтобы запросы типа
    # «кто автор ИИ» не перехватывались обычным «кто ты».
    priority_order = [
        "author",
        "developer",
        "contacts",
        "identity",
        "hello",
        "help",
        "thanks",
        "bye",
    ]

    for intent in priority_order:
        config = BASIC_INTENTS.get(intent)
        if not config:
            continue

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


def _truncate(value: str, limit: int = MAX_CONTENT_PREVIEW_CHARS) -> str:
    text = str(value or "").strip()

    if len(text) <= limit:
        return text

    return text[:limit].rstrip() + "…"


def _copy_block(text: str, limit: int = MAX_COPY_CONTENT_CHARS) -> str:
    clean_text = str(text or "").strip()

    if not clean_text:
        return ""

    clean_text = _truncate(clean_text, limit)

    return (
        f"{COPY_FENCE}\n"
        f"{clean_text}\n"
        f"{COPY_FENCE}"
    )


def _internet_search_links(query: str) -> str:
    encoded = urllib.parse.quote_plus(str(query or "").strip())

    if not encoded:
        encoded = urllib.parse.quote_plus("Students Life информация")

    return (
        "**Можно проверить в интернете:**\n"
        f"- Яндекс: https://yandex.ru/search/?text={encoded}\n"
        f"- Google: https://www.google.com/search?q={encoded}\n\n"
        "Важно: точный корпоративный ответ лучше добавить в базу знаний, "
        "чтобы сотрудники потом находили его внутри приложения."
    )


def _load_knowledge():
    snippets = list(
        InfoSnippet.objects.select_related("section").all().order_by(
            "section__order",
            "category",
            "order",
            "title",
        )
    )

    sections = list(
        KnowledgeSection.objects.filter(is_active=True).select_related("parent").order_by(
            "parent__id",
            "order",
            "title",
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
    content_words = _tokens(content_norm[:6000])
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

        if _token_fuzzy_match(token, content_words[:400], threshold=0.84):
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
        "что есть про", "найди всё", "найди все",
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


def _render_folder_overview(query: str, ranked: List[Tuple[float, object]], sections: List) -> str:
    topic = _detect_browse_topic(query)
    topic_label = topic["label"] if topic else "запрошенной теме"

    useful_ranked = [
        (score, snippet)
        for score, snippet in ranked
        if score >= MIN_RELEVANCE_SCORE
    ]

    useful_snippets = [
        snippet
        for _, snippet in useful_ranked[:MAX_SNIPPETS_FOR_OVERVIEW]
    ]

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
            lines.append(f"- {_get_section_path(section)}")
        lines.append("")

    if grouped:
        lines.append("**Найденные материалы:**")

        for section_path, items in grouped.items():
            lines.append("")
            lines.append(f"📁 **{section_path}**")

            for snippet in items[:8]:
                category_label = _get_category_label(getattr(snippet, "category", ""))
                title = getattr(snippet, "title", "Без названия")
                content = _truncate(getattr(snippet, "content", ""), 280)

                lines.append(f"- **{title}** · {category_label}")

                if content:
                    lines.append(f"  {content}")

    lines.append("")
    lines.append(
        "Что конкретнее вам нужно: условия поступления, документы, цены, скрипт ответа клиенту, "
        "виза, оплата или конкретный университет/страна?"
    )

    return "\n".join(lines)


def _render_precise_local_answer(query: str, top_ranked: List[Tuple[float, object]]) -> str:
    if not top_ranked:
        return _render_no_relevant_answer(query, snippets_count=0)

    lines = []
    lines.append("Я нашёл подходящую информацию в базе знаний Students Life.")
    lines.append("")
    lines.append("**Краткий ответ:**")

    best_score, best_snippet = top_ranked[0]
    best_title = getattr(best_snippet, "title", "Без названия")
    best_content = getattr(best_snippet, "content", "") or ""
    best_section = _get_section_path(getattr(best_snippet, "section", None))
    best_category = _get_category_label(getattr(best_snippet, "category", ""))

    lines.append(f"Больше всего подходит материал **«{best_title}»**.")
    lines.append(f"Раздел: **{best_section}**.")
    lines.append(f"Категория: **{best_category}**.")
    lines.append("")

    if best_content:
        lines.append("**Основная информация:**")
        lines.append(_truncate(best_content, MAX_CONTENT_PREVIEW_CHARS))
        lines.append("")
        lines.append("**Текст для копирования:**")
        lines.append(_copy_block(best_content))
        lines.append("")

    if len(top_ranked) > 1:
        lines.append("**Дополнительно найдено:**")

        for index, (_, snippet) in enumerate(top_ranked[1:MAX_SNIPPETS_FOR_ANSWER], start=2):
            title = getattr(snippet, "title", "Без названия")
            section_path = _get_section_path(getattr(snippet, "section", None))
            category_label = _get_category_label(getattr(snippet, "category", ""))
            content = _truncate(getattr(snippet, "content", ""), 350)

            lines.append("")
            lines.append(f"{index}. **{title}**")
            lines.append(f"   Раздел: {section_path}")
            lines.append(f"   Категория: {category_label}")

            if content:
                lines.append(f"   {content}")
                lines.append("   **Текст для копирования:**")
                lines.append(_copy_block(getattr(snippet, "content", ""), limit=1400))

    lines.append("")
    lines.append("**Источники:**")
    lines.append(_build_sources_list(top_ranked[:MAX_SNIPPETS_FOR_ANSWER]))
    lines.append("")
    lines.append(
        "Если нужно, уточните вопрос: страна, вуз, клиентская ситуация, документы, оплата, "
        "виза или скрипт продаж."
    )

    return "\n".join(lines)


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
    documents/views.py ожидает строку и возвращает её как {'answer': answer}.

    Важно:
    - внешний ИИ отключён;
    - ответ формируется локально;
    - поиск работает по InfoSnippet и KnowledgeSection;
    - добавлена имитация думания 2 секунды.
    """
    query = str(query or "").strip()

    if not query:
        return "Введите ваш вопрос. Например: «что есть по вузам Китая?» или «найди скрипт продаж»."

    _apply_thinking_delay()

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

    top_ranked = relevant_ranked[:MAX_SNIPPETS_FOR_ANSWER]

    return _render_precise_local_answer(query, top_ranked)