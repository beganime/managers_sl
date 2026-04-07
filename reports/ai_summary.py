import json
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


def _num(value):
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


def _date_str(value):
    return str(value) if value else None


def _call_gemini(prompt: str):
    api_key = getattr(settings, "GEMINI_API_KEY", "") or os.getenv("GEMINI_API_KEY", "")
    model = getattr(settings, "GEMINI_MODEL", "") or os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

    if not api_key:
        return None, "GEMINI_API_KEY не задан"

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                ]
            }
        ]
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            raw = resp.read().decode("utf-8")
            data = json.loads(raw)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        return None, f"Gemini HTTPError: {exc.code} {body}"
    except Exception as exc:
        return None, str(exc)

    candidates = data.get("candidates") or []
    if not candidates:
        return None, f"Пустой ответ Gemini: {json.dumps(data, ensure_ascii=False)}"

    parts = candidates[0].get("content", {}).get("parts", [])
    text = "\n".join(part.get("text", "") for part in parts if part.get("text"))
    return text.strip() or None, None


def build_admin_ai_summary(date_from=None, date_to=None, office_id=None):
    reports_qs = DailyReport.objects.select_related("employee", "employee__office").all()

    if date_from:
        reports_qs = reports_qs.filter(date__gte=date_from)
    if date_to:
        reports_qs = reports_qs.filter(date__lte=date_to)
    if office_id:
        reports_qs = reports_qs.filter(employee__office_id=office_id)

    reports_payload = []
    office_stats = {}

    for report in reports_qs.order_by("-date", "employee_id"):
        office = getattr(report.employee, "office", None)
        office_key = getattr(office, "id", None) or 0
        office_name = getattr(office, "city", None) or "Без офиса"
        employee_name = f"{report.employee.first_name} {report.employee.last_name}".strip() or report.employee.email

        office_stats.setdefault(
            office_key,
            {
                "office_name": office_name,
                "employees": set(),
                "reports_count": 0,
                "income": Decimal("0"),
                "expense": Decimal("0"),
            },
        )

        office_stats[office_key]["employees"].add(employee_name)
        office_stats[office_key]["reports_count"] += 1
        office_stats[office_key]["income"] += _num(
            getattr(report, "income", None)
            or getattr(report, "income_usd", None)
            or getattr(report, "total_income", None)
        )
        office_stats[office_key]["expense"] += _num(
            getattr(report, "expense", None)
            or getattr(report, "expense_usd", None)
            or getattr(report, "total_expense", None)
        )

        reports_payload.append(
            {
                "date": _date_str(getattr(report, "date", None)),
                "employee": employee_name,
                "office": office_name,
                "leads_processed": getattr(report, "leads_processed", 0),
                "deals_closed": getattr(report, "deals_closed", 0),
                "income": str(
                    _num(
                        getattr(report, "income", None)
                        or getattr(report, "income_usd", None)
                        or getattr(report, "total_income", None)
                    )
                ),
                "expense": str(
                    _num(
                        getattr(report, "expense", None)
                        or getattr(report, "expense_usd", None)
                        or getattr(report, "total_expense", None)
                    )
                ),
                "content": getattr(report, "content", "") or "",
            }
        )

    payments_total = Decimal("0")
    if Payment is not None:
        payments_qs = Payment.objects.select_related("manager", "manager__office").all()
        if date_from:
            payments_qs = payments_qs.filter(payment_date__gte=date_from)
        if date_to:
            payments_qs = payments_qs.filter(payment_date__lte=date_to)
        if office_id:
            payments_qs = payments_qs.filter(manager__office_id=office_id)

        for item in payments_qs:
            payments_total += _num(getattr(item, "amount_usd", None) or getattr(item, "amount", None))

    expenses_total = Decimal("0")
    if Expense is not None:
        expenses_qs = Expense.objects.select_related("manager", "manager__office").all()
        if date_from:
            expenses_qs = expenses_qs.filter(date__gte=date_from)
        if date_to:
            expenses_qs = expenses_qs.filter(date__lte=date_to)
        if office_id:
            expenses_qs = expenses_qs.filter(manager__office_id=office_id)

        for item in expenses_qs:
            expenses_total += _num(getattr(item, "amount_usd", None) or getattr(item, "amount", None))

    finance_entries = []
    finance_balance = Decimal("0")
    if OfficeFinanceEntry is not None:
        finance_qs = OfficeFinanceEntry.objects.select_related("office", "created_by").all()
        if date_from:
            finance_qs = finance_qs.filter(entry_date__gte=date_from)
        if date_to:
            finance_qs = finance_qs.filter(entry_date__lte=date_to)
        if office_id:
            finance_qs = finance_qs.filter(office_id=office_id)

        for item in finance_qs.order_by("-entry_date", "-id"):
            amount = _num(getattr(item, "amount_usd", None) or getattr(item, "amount", None))
            entry_type = getattr(item, "entry_type", "") or ""
            finance_balance += amount if entry_type == "income" else -amount
            finance_entries.append(
                {
                    "office": getattr(getattr(item, "office", None), "city", None) or "Без офиса",
                    "entry_type": entry_type,
                    "title": getattr(item, "title", "") or "",
                    "amount": str(amount),
                    "entry_date": _date_str(getattr(item, "entry_date", None)),
                }
            )

    office_summaries = []
    for stat in office_stats.values():
        office_summaries.append(
            {
                "office_name": stat["office_name"],
                "reports_count": stat["reports_count"],
                "employees": sorted(list(stat["employees"])),
                "income": str(stat["income"]),
                "expense": str(stat["expense"]),
                "balance": str(stat["income"] - stat["expense"]),
            }
        )

    payload = {
        "period": {
            "date_from": _date_str(date_from),
            "date_to": _date_str(date_to),
            "office_id": office_id,
        },
        "reports_count": len(reports_payload),
        "payments_total": str(payments_total),
        "expenses_total": str(expenses_total),
        "office_finance_balance": str(finance_balance),
        "office_summaries": office_summaries,
        "finance_entries": finance_entries[:60],
        "reports": reports_payload[:120],
    }

    prompt = f"""
Ты — сильный операционный аналитик.
Подготовь для администратора единый итоговый отчёт на русском языке.

Структура:
1. Общая картина
2. Что хорошо
3. Какие проблемы и риски
4. Что видно по офисам
5. Что видно по доходам и расходам
6. Какие сотрудники/офисы выделяются
7. 5 конкретных рекомендаций админу

Данные:
{json.dumps(payload, ensure_ascii=False)}
""".strip()

    summary_text, error = _call_gemini(prompt)

    if not summary_text:
      summary_text = (
          "AI-резюме пока не сгенерировано. "
          f"Отчётов: {len(reports_payload)}. "
          f"Платежей: {payments_total}. "
          f"Расходов: {expenses_total}. "
          f"Баланс office finance: {finance_balance}."
      )

    return {
        "provider": "gemini",
        "summary": summary_text,
        "error": error,
        "payload": payload,
    }