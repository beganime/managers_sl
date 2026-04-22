import json
import logging
import os
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

# Константы для внутреннего анализа SL_AI
MAX_REPORTS_FOR_ANALYSIS = 100
MAX_FINANCE_ENTRIES_FOR_ANALYSIS = 50
MAX_REPORT_CONTENT_CHARS = 1000


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


def _build_reports_payload(reports_qs):
    reports_payload = []
    office_stats = {}
    total_income = Decimal("0")
    total_expense = Decimal("0")
    total_leads = 0
    total_deals = 0

    for report in reports_qs.order_by("-date", "employee_id")[:MAX_REPORTS_FOR_ANALYSIS]:
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

    for item in finance_qs.order_by("-entry_date", "-id")[:MAX_FINANCE_ENTRIES_FOR_ANALYSIS]:
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


def _generate_sl_ai_summary(payload: dict) -> str:
    """
    Внутренний движок SL_AI для генерации управленческого резюме
    на основе правил, эвристики и математики.
    """
    totals = payload.get("summary_totals", {})
    offices = payload.get("office_summaries", [])
    reports = payload.get("recent_reports", [])
    
    income = Decimal(totals.get("reports_income_total", "0"))
    expense = Decimal(totals.get("reports_expense_total", "0"))
    balance = Decimal(totals.get("reports_balance_total", "0"))
    deals = totals.get("deals_closed_total", 0)
    leads = totals.get("leads_processed_total", 0)
    reports_count = totals.get("reports_count", 0)
    
    finance_balance = Decimal(payload.get("office_finance_balance", "0"))

    # 3. Анализ текста отчетов на маркеры проблем
    risk_keywords = ["ошибка", "проблема", "жалоба", "отказ", "минус", "сложно", "сбой", "недоволен", "возврат"]
    risks_found = []
    
    for r in reports:
        content = r.get("content", "").lower()
        if any(kw in content for kw in risk_keywords):
            emp = r.get("employee", "Неизвестный")
            off = r.get("office", "Неизвестный офис")
            preview = r.get("content", "").replace("\n", " ")[:80]
            risks_found.append(f"⚠️ {off} ({emp}): {preview}...")
            if len(risks_found) >= 5:  # Берем топ-5 проблем, чтобы не перегружать отчет
                break

    # 4 и 6. Анализ по офисам и поиск лидера
    office_details = []
    top_office_name = None
    max_deals = -1
    
    for o in offices:
        name = o.get("office_name")
        o_bal = Decimal(o.get("balance", "0"))
        o_deals = o.get("deals_closed", 0)
        o_leads = o.get("leads_processed", 0)
        
        status_icon = "🟢" if o_bal >= 0 else "🔴"
        office_details.append(f"{status_icon} {name}: Сделок {o_deals} (Лидов: {o_leads}) | Баланс: {o_bal} руб.")
        
        if o_deals > max_deals:
            max_deals = o_deals
            top_office_name = name

    # Сборка итогового текста
    lines = []
    
    # 1. Общая картина
    lines.append("📊 1. Общая картина")
    lines.append(f"Обработано отчетов: {reports_count}. В работе {leads} лидов, из них успешно закрыто сделок: {deals}.")
    lines.append(f"Операционный баланс по отчетам: {balance} руб.")
    lines.append("")

    # 2. Что хорошо
    lines.append("✅ 2. Что хорошо")
    good_points = []
    if balance > 0:
        good_points.append("- Сохраняется положительный финансовый баланс по отчетам.")
    if deals > 0:
        good_points.append(f"- Успешно закрыты сделки: {deals} шт.")
    if finance_balance > 0:
        good_points.append("- Положительное сальдо по финансовым записям офисов.")
    if not good_points:
         good_points.append("- Сотрудники стабильно заполняют документацию.")
    lines.extend(good_points)
    lines.append("")

    # 3. Проблемы и риски
    lines.append("⚠️ 3. Проблемы и риски")
    if balance < 0:
        lines.append("- Внимание: Расходы по отчетам превышают доходы (отрицательный баланс).")
    if risks_found:
        lines.append("- В текстах отчетов зафиксированы следующие тревожные сигналы:")
        lines.extend(risks_found)
    else:
        lines.append("- Критических проблем в комментариях сотрудников не выявлено.")
    lines.append("")

    # 4. Что видно по офисам
    lines.append("🏢 4. Что видно по офисам")
    if office_details:
        lines.extend(office_details)
    else:
        lines.append("- Данные в разрезе офисов отсутствуют.")
    lines.append("")

    # 5. Доходы и расходы
    lines.append("💰 5. Доходы и расходы")
    lines.append(f"- Заявленный доход в отчетах: {income}")
    lines.append(f"- Заявленный расход в отчетах: {expense}")
    lines.append(f"- Внешние платежи (Payments): {payload.get('payments_total', '0')}")
    lines.append(f"- Внешние расходы (Expenses): {payload.get('expenses_total', '0')}")
    lines.append(f"- Чистый баланс по фин. записям: {finance_balance}")
    lines.append("")

    # 6. Кто выделяется
    lines.append("🏆 6. Кто выделяется")
    if top_office_name and max_deals > 0:
        lines.append(f"- Явный лидер периода — офис «{top_office_name}» (закрыто {max_deals} сделок).")
    else:
        lines.append("- В данном периоде ярко выраженных лидеров не зафиксировано.")
    lines.append("")

    # 7. Рекомендации
    lines.append("💡 7. Рекомендации администратору")
    lines.append("1. Проверить конверсию из лидов в сделки в отстающих филиалах.")
    if risks_found:
        lines.append("2. Связаться с сотрудниками для решения проблем, указанных в отчетах.")
    else:
        lines.append("2. Поддерживать текущий ритм работы с клиентами.")
    
    if balance < 0 or finance_balance < 0:
        lines.append("3. ОПЕРЕЙШН: Срочно провести аудит превышения расходов!")
    else:
        lines.append("3. Сверить заявленные в отчетах доходы с фактическими поступлениями в кассу.")
        
    lines.append("4. Проконтролировать своевременность внесения всех чеков и расходов в базу.")
    if top_office_name:
        lines.append(f"5. Собрать лучшие практики у офиса «{top_office_name}» и внедрить в другие филиалы.")
    else:
        lines.append("5. Мотивировать команду на ускорение закрытия зависших сделок.")

    return "\n".join(lines)


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
            "provider": "SL_AI",
            "model": "rule-based-engine-v1",
            "ai_used": False,
            "summary": "Недостаточно данных для анализа: нет отчётов и нет финансовых записей за выбранный период.",
            "error": "Нет данных для анализа",
            "meta": {
                "period": payload["period"],
                "reports_count": 0,
                "offices_count": 0,
            },
        }

    # Вызов локального алгоритма SL_AI вместо Yandex GPT
    try:
        summary_text = _generate_sl_ai_summary(payload)
        error = None
    except Exception as e:
        logger.exception("SL_AI Engine Error")
        summary_text = "Ошибка при генерации локального отчета SL_AI."
        error = str(e)

    return {
        "provider": "SL_AI",
        "model": "rule-based-engine-v1",
        "ai_used": True,  # Оставляем True для фронтенда, так как логика анализа выполнена
        "summary": summary_text,
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