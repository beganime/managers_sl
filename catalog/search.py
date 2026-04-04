import re
import unicodedata
from difflib import SequenceMatcher


WORD_RE = re.compile(r'[\w\d]+', flags=re.UNICODE)


def normalize_text(value):
    value = (value or '').strip().lower()
    value = unicodedata.normalize('NFKD', value)
    value = ''.join(ch for ch in value if not unicodedata.combining(ch))
    value = value.replace('ё', 'е')
    value = re.sub(r'\s+', ' ', value)
    return value


def tokenize(value):
    return WORD_RE.findall(normalize_text(value))


def score_similarity(query, text):
    query = normalize_text(query)
    text = normalize_text(text)
    if not query or not text:
        return 0.0

    if query in text:
        return 1.0

    query_tokens = tokenize(query)
    text_tokens = tokenize(text)
    token_scores = []

    for q in query_tokens:
        best = 0.0
        for t in text_tokens:
            ratio = SequenceMatcher(None, q, t).ratio()
            if q and t and (q.startswith(t[:1]) or t.startswith(q[:1])):
                ratio += 0.05
            best = max(best, ratio)
        token_scores.append(best)

    if not token_scores:
        return SequenceMatcher(None, query, text).ratio()

    whole_ratio = SequenceMatcher(None, query, text).ratio()
    avg_token = sum(token_scores) / len(token_scores)
    return max(avg_token, whole_ratio * 0.85)


def rank_queryset_by_search(queryset, search, value_getter, min_score=0.45):
    ranked = []
    for obj in queryset:
        haystack = value_getter(obj)
        score = score_similarity(search, haystack)
        if score >= min_score:
            ranked.append((score, obj.id))

    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [obj_id for _, obj_id in ranked]