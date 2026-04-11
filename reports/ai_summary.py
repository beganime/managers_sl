import json
import logging
import os
import urllib.error
import urllib.request
from decimal import Decimal

from django.conf import settings

from reports.models import DailyReport

try:
    from analytics.models import Payment, Expense
except Exception:  # pragma: no cover
    Payment = None
    Expense = None

try:
    from analytics.finance_models import OfficeFinanceEntry
except Exception:  # pragma: no cover
    try:
        from analytics.models import OfficeFinanceEntry  # type: ignore
    except Exception:
        OfficeFinanceEntry = None


logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-1.5-flash"
MAX_REPORTS_FOR_PROMPT = 60
MAX_FINANCE_ENTRIES_FOR_PROMPT = 40
MAX_REPORT_CONTENT_CHARS = 700


def _num(value):
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


def _date_str(value):
    return str(value) if value else None


def _truncate_text(value, limit=MAX_REPORT_CONTENT_CHARS):
    text = (value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


def _is_income_entry(entry_type: str) -> bool:
    normalized = str(entry_type or "").strip().lower()
    return normalized in {"income", "in", "plus", "credit", "deposit", "приход", "доход"}


def _build_gemini_payload(prompt: str):
    return {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.35,
            "topP": 0.9,
            "maxOutputTokens": 1800,
        },
    }


def _extract_gemini_text(data: dict):
    prompt_feedback = data.get("promptFeedback") or {}
    block_reason = prompt_feedback.get("blockReason")
    if block_reason:
        return None, f"Gemini заблокировал запрос: {block_reason}"

    candidates = data.get("candidates") or []
    if not candidates:
        return None, f"Gemini не вернул candidates: {json.dumps(data, ensure_ascii=False)}"

    candidate = candidates[0] or {}
    finish_reason = candidate.get("finishReason")
    content = candidate.get("content") or {}
    parts = content.get("parts") or []

    texts = []
    for part in parts:
        text = part.get("text")
        if text:
            texts.append(text)

    result_text = "\n".join(texts).strip()

    if result_text:
        return result_text, None

    if finish_reason:
        return None, f"Gemini не вернул текст. finishReason={finish_reason}"

    return None, f"Gemini не вернул текст: {json.dumps(data, ensure_ascii=False)}"


def _call_gemini(prompt: str):
    api_key = os.getenv("GEMINI_API_KEY", "") or getattr(settings, "GEMINI_API_KEY", "")
    model = os.getenv("GEMINI_MODEL", "") or getattr(settings, "GEMINI_MODEL", DEFAULT_MODEL)

    if not api_key:
        return None, "GEMINI_API_KEY не задан", model

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )

    payload = _build_gemini_payload(prompt)

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "ManagersSL/1.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            raw = resp.read().decode("utf-8")
            data = json.loads(raw)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        logger.exception("Gemini HTTPError")
        return None, f"Gemini HTTPError {exc.code}: {body}", model
    except urllib.error.URLError as exc:
        logger.exception("Gemini URLError")
        return None, f"Gemini URLError: {exc}", model
    except Exception as exc:
        logger.exception("Gemini unknown error")
        return None, str(exc), model

    text, error = _extract_gemini_text(data)
    if error:
        logger.warning("Gemini empty/bad response: %s", error)
        return None, error, model

    return text, None, model


def _build_reports_payload(reports_qs):
    reports_payload = []
    office_stats = {}
    total_income = Decimal("0")
    total_expense = Decimal("0")
    total_leads = 0
    total_deals = 0

    for report in reports_qs.order_by("-date", "employee_id")[:MAX_REPORTS_FOR_PROMPT]:
        office = getattr(report.employee, "office", None)
        office_key = getattr(office, "id", None) or 0
        office_name = getattr(office, "city", None) or "Без офиса"
        employee_name = (
            f"{getattr(report.employee, 'first_name', '')} {getattr(report.employee, 'last_name', '')}"
        ).strip() or getattr(report.employee, "email", "Без имени")

        income_value = _num(
            getattr(report, "income", None)
            or getattr(report, "income_usd", None)
            or getattr(report, "total_income", None)
        )
        expense_value = _num(
            getattr(report, "expense", None)
            or getattr(report, "expense_usd", None)
            or getattr(report, "total_expense", None)
        )

        leads_processed = int(getattr(report, "leads_processed", 0) or 0)
        deals_closed = int(getattr(report, "deals_closed", 0) or 0)

        total_income += income_value
        total_expense += expense_value
        total_leads += leads_processed
        total_deals += deals_closed

        office_stats.setdefault(
            office_key,
            {
                "office_name": office_name,
                "employees": set(),
                "reports_count": 0,
                "income": Decimal("0"),
                "expense": Decimal("0"),
                "leads_processed": 0,
                "deals_closed": 0,
            },
        )

        office_stats[office_key]["employees"].add(employee_name)
        office_stats[office_key]["reports_count"] += 1
        office_stats[office_key]["income"] += income_value
        office_stats[office_key]["expense"] += expense_value
        office_stats[office_key]["leads_processed"] += leads_processed
        office_stats[office_key]["deals_closed"] += deals_closed

        reports_payload.append(
            {
                "date": _date_str(getattr(report, "date", None)),
                "employee": employee_name,
                "office": office_name,
                "leads_processed": leads_processed,
                "deals_closed": deals_closed,
                "income": str(income_value),
                "expense": str(expense_value),
                "content": _truncate_text(getattr(report, "content", "") or ""),
            }
        )

    office_summaries = []
    for _, stat in sorted(office_stats.items(), key=lambda item: item[1]["office_name"]):
        office_summaries.append(
            {
                "office_name": stat["office_name"],
                "reports_count": stat["reports_count"],
                "employees": sorted(list(stat["employees"])),
                "income": str(stat["income"]),
                "expense": str(stat["expense"]),
                "balance": str(stat["income"] - stat["expense"]),
                "leads_processed": stat["leads_processed"],
                "deals_closed": stat["deals_closed"],
            }
        )

    summary_totals = {
        "reports_count": len(reports_payload),
        "reports_income_total": str(total_income),
        "reports_expense_total": str(total_expense),
        "reports_balance_total": str(total_income - total_expense),
        "leads_processed_total": total_leads,
        "deals_closed_total": total_deals,
    }

    return reports_payload, office_summaries, summary_totals


def _build_payments_total(date_from=None, date_to=None, office_id=None):
    payments_total = Decimal("0")

    if Payment is None:
        return payments_total

    payments_qs = Payment.objects.select_related("manager", "manager__office").all()

    if date_from:
        payments_qs = payments_qs.filter(payment_date__gte=date_from)
    if date_to:
        payments_qs = payments_qs.filter(payment_date__lte=date_to)
    if office_id:
        payments_qs = payments_qs.filter(manager__office_id=office_id)

    for item in payments_qs:
        payments_total += _num(getattr(item, "amount_usd", None) or getattr(item, "amount", None))

    return payments_total


def _build_expenses_total(date_from=None, date_to=None, office_id=None):
    expenses_total = Decimal("0")

    if Expense is None:
        return expenses_total

    expenses_qs = Expense.objects.select_related("manager", "manager__office").all()

    if date_from:
        expenses_qs = expenses_qs.filter(date__gte=date_from)
    if date_to:
        expenses_qs = expenses_qs.filter(date__lte=date_to)
    if office_id:
        expenses_qs = expenses_qs.filter(manager__office_id=office_id)

    for item in expenses_qs:
        expenses_total += _num(getattr(item, "amount_usd", None) or getattr(item, "amount", None))

    return expenses_total


def _build_finance_entries(date_from=None, date_to=None, office_id=None):
    finance_entries = []
    finance_balance = Decimal("0")

    if OfficeFinanceEntry is None:
        return finance_entries, finance_balance

    finance_qs = OfficeFinanceEntry.objects.select_related("office", "created_by").all()

    if date_from:
        finance_qs = finance_qs.filter(entry_date__gte=date_from)
    if date_to:
        finance_qs = finance_qs.filter(entry_date__lte=date_to)
    if office_id:
        finance_qs = finance_qs.filter(office_id=office_id)

    for item in finance_qs.order_by("-entry_date", "-id")[:MAX_FINANCE_ENTRIES_FOR_PROMPT]:
        amount = _num(getattr(item, "amount_usd", None) or getattr(item, "amount", None))
        entry_type = getattr(item, "entry_type", "") or ""

        if _is_income_entry(entry_type):
            finance_balance += amount
        else:
            finance_balance -= amount

        finance_entries.append(
            {
                "office": getattr(getattr(item, "office", None), "city", None) or "Без офиса",
                "entry_type": entry_type,
                "title": _truncate_text(getattr(item, "title", "") or "", 160),
                "amount": str(amount),
                "entry_date": _date_str(getattr(item, "entry_date", None)),
            }
        )

    return finance_entries, finance_balance


def _build_prompt(payload: dict):
    return f"""
Ты — сильный операционный аналитик и помощник администратора.

Сделай итоговый управленческий отчёт на русском языке.
Пиши конкретно, без воды, с опорой только на данные ниже.
Если данных мало или они неполные — прямо скажи об этом.
Не выдумывай факты.

Структура ответа:
1. Общая картина
2. Что хорошо
3. Проблемы и риски
4. Что видно по офисам
5. Доходы и расходы
6. Кто или какой офис выделяется
7. 5 конкретных рекомендаций администратору

Данные:
{json.dumps(payload, ensure_ascii=False)}
""".strip()


def build_admin_ai_summary(date_from=None, date_to=None, office_id=None):
    reports_qs = DailyReport.objects.select_related("employee", "employee__office").all()

    if date_from:
        reports_qs = reports_qs.filter(date__gte=date_from)
    if date_to:
        reports_qs = reports_qs.filter(date__lte=date_to)
    if office_id:
        reports_qs = reports_qs.filter(employee__office_id=office_id)

    reports_payload, office_summaries, summary_totals = _build_reports_payload(reports_qs)
    payments_total = _build_payments_total(date_from=date_from, date_to=date_to, office_id=office_id)
    expenses_total = _build_expenses_total(date_from=date_from, date_to=date_to, office_id=office_id)
    finance_entries, finance_balance = _build_finance_entries(
        date_from=date_from,
        date_to=date_to,
        office_id=office_id,
    )

    payload = {
        "period": {
            "date_from": _date_str(date_from),
            "date_to": _date_str(date_to),
            "office_id": office_id,
        },
        "summary_totals": summary_totals,
        "payments_total": str(payments_total),
        "expenses_total": str(expenses_total),
        "office_finance_balance": str(finance_balance),
        "office_summaries": office_summaries,
        "recent_finance_entries": finance_entries,
        "recent_reports": reports_payload,
    }

    if not reports_payload and not finance_entries:
        return {
            "provider": "gemini",
            "model": os.getenv("GEMINI_MODEL", "") or getattr(settings, "GEMINI_MODEL", DEFAULT_MODEL),
            "ai_used": False,
            "summary": "Недостаточно данных для AI-анализа: нет отчётов и нет финансовых записей за выбранный период.",
            "error": "Нет данных для анализа",
            "meta": {
                "period": payload["period"],
                "reports_count": 0,
                "offices_count": 0,
            },
        }

    prompt = _build_prompt(payload)
    summary_text, error, model = _call_gemini(prompt)

    if summary_text:
        return {
            "provider": "gemini",
            "model": model,
            "ai_used": True,
            "summary": summary_text,
            "error": None,
            "meta": {
                "period": payload["period"],
                "reports_count": summary_totals["reports_count"],
                "offices_count": len(office_summaries),
                "payments_total": str(payments_total),
                "expenses_total": str(expenses_total),
                "office_finance_balance": str(finance_balance),
            },
        }

    fallback_text = (
        "AI-резюме не удалось сгенерировать. "
        "Проверьте GEMINI_API_KEY, GEMINI_MODEL, доступ сервера к Google API "
        "и ограничения ключа. Подробность ошибки есть в поле error."
    )

    return {
        "provider": "gemini",
        "model": model,
        "ai_used": False,
        "summary": fallback_text,
        "error": error,
        "meta": {
            "period": payload["period"],
            "reports_count": summary_totals["reports_count"],
            "offices_count": len(office_summaries),
            "payments_total": str(payments_total),
            "expenses_total": str(expenses_total),
            "office_finance_balance": str(finance_balance),
        },
    }