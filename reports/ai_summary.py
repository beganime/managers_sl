import logging
import random
import re
from decimal import Decimal

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
MAX_REPORT_CONTENT_CHARS = 1200
MAX_TRIGGER_EXAMPLES = 7
MAX_EMPLOYEE_ROWS = 8


TRIGGER_GROUPS = {
    "client_negative": {
        "title": "Клиентский негатив / риск отказа",
        "severity": 5,
        "keywords": [
            "отказ", "отказался", "жалоба", "претензия", "недоволен", "недовольна",
            "конфликт", "скандал", "ругался", "негатив", "возврат", "refund", "cancel",
            "не отвечает", "игнор", "пропал", "не выходит на связь", "передумал",
            "не хочет", "сомневается", "плохой отзыв", "обман", "обманули",
        ],
        "recommendation": "Связаться с клиентом, понять причину негатива, закрепить ответственного и следующий шаг.",
    },
    "document_problem": {
        "title": "Проблемы с документами",
        "severity": 4,
        "keywords": [
            "документ", "документы", "паспорт", "перевод", "нотариус", "апостиль",
            "легализация", "не хватает", "не загрузил", "не загрузила", "ошибка в документе",
            "неверно", "неправильно", "опечатка", "фото не подходит", "просрочен",
            "просроченный", "отклонили", "отклонено", "не приняли", "справка",
        ],
        "recommendation": "Проверить чек-лист документов и поставить дедлайн на исправление.",
    },
    "payment_risk": {
        "title": "Финансовый риск / оплата",
        "severity": 5,
        "keywords": [
            "не оплатил", "не оплатила", "оплата задерживается", "долг", "задолженность",
            "просрочка", "не сходится", "касса", "чек", "без чека", "скидка", "рассрочка",
            "возврат денег", "вернуть деньги", "минус", "расход", "переплата", "недоплата",
        ],
        "recommendation": "Сверить оплату с кассой/платежами и зафиксировать финансовый статус клиента.",
    },
    "deadline_delay": {
        "title": "Задержки / дедлайны",
        "severity": 4,
        "keywords": [
            "задержка", "задерживается", "долго", "ждём", "ждем", "перенос", "перенесли",
            "не успели", "не успел", "дедлайн", "срочно", "горит", "завис", "зависла",
            "очередь", "опоздал", "опоздала", "просрочили", "завтра крайний",
        ],
        "recommendation": "Назначить конкретный дедлайн, ответственного и контрольный звонок.",
    },
    "admission_risk": {
        "title": "Поступление / вуз / виза",
        "severity": 4,
        "keywords": [
            "вуз не ответил", "университет не ответил", "инвойс", "offer", "оффер",
            "приглашение", "экзамен", "собеседование", "не прошел", "не прошла",
            "провалил", "провалила", "виза", "отказ визы", "посольство", "консульство",
            "дедлайн подачи", "не приняли заявку", "application rejected",
        ],
        "recommendation": "Проверить статус заявки у вуза/посольства и заранее подготовить запасной сценарий.",
    },
    "staff_discipline": {
        "title": "Дисциплина сотрудника / процесс",
        "severity": 3,
        "keywords": [
            "забыл", "забыла", "не закрыл день", "не закрыла день", "не внес", "не внесла",
            "не сделал", "не сделала", "нет отчёта", "нет отчета", "без отчета",
            "не дозвонился", "не дозвонилась", "не записал", "не записала",
        ],
        "recommendation": "Проверить соблюдение регламента: отчет, CRM, звонки, следующий шаг по клиенту.",
    },
    "technical_problem": {
        "title": "Техническая ошибка",
        "severity": 3,
        "keywords": [
            "сбой", "не работает", "ошибка 500", "ошибка 400", "500", "400", "баг",
            "сервер", "приложение", "зависает", "виснет", "не открывается",
            "не сохраняется", "не грузится", "api", "ошибка api",
        ],
        "recommendation": "Передать разработчику пример ошибки, дату, сотрудника и действие, где ошибка появилась.",
    },
}

POSITIVE_KEYWORDS = [
    "оплатил", "оплатила", "закрыл", "закрыла", "закрыта сделка", "подписал", "подписала",
    "договор", "поступил", "поступила", "одобрено", "одобрили", "получили приглашение",
    "приглашение готово", "виза готова", "успешно", "прошел экзамен", "прошла экзамен",
    "клиент доволен", "рекомендовал", "рекомендовала", "новый клиент", "повторный клиент",
]

NEXT_STEP_KEYWORDS = [
    "завтра", "сегодня", "до ", "дедлайн", "следующий шаг", "план", "нужно", "сделать",
    "позвонить", "написать", "отправить", "проверить", "подготовить", "встретиться",
]

CLIENT_KEYWORDS = [
    "клиент", "студент", "абитуриент", "родитель", "мама", "отец", "заявка", "лид",
]

MONEY_KEYWORDS = [
    "оплата", "оплатил", "оплатила", "деньги", "касса", "чек", "долг", "расход",
    "доход", "usd", "руб", "манат", "перевод", "карта",
]

STYLE_PROFILES = [
    {
        "name": "Деловой директорский стиль",
        "opening": "Коротко по управленческой картине: смотрю на цифры, риски и то, что нужно поправить в работе команды.",
        "good_word": "сильные стороны",
        "risk_word": "зоны контроля",
        "advice_word": "управленческие действия",
    },
    {
        "name": "Жёсткий аудит без воды",
        "opening": "Разбор прямой: где есть результат — фиксируем, где есть провал — закрываем без затягивания.",
        "good_word": "что сработало",
        "risk_word": "критичные места",
        "advice_word": "что сделать срочно",
    },
    {
        "name": "Спокойный аналитический стиль",
        "opening": "Картина периода собрана по отчетам, финансам и текстовым сигналам сотрудников.",
        "good_word": "позитивные признаки",
        "risk_word": "наблюдаемые риски",
        "advice_word": "рекомендации на улучшение",
    },
    {
        "name": "Стиль наставника команды",
        "opening": "Смотрю на отчет как на инструмент роста: что команда делает правильно и где можно усилиться.",
        "good_word": "что стоит сохранить",
        "risk_word": "что мешает росту",
        "advice_word": "следующие шаги",
    },
    {
        "name": "Продажный фокус",
        "opening": "Главный фокус — лиды, сделки, деньги и скорость движения клиента по воронке.",
        "good_word": "точки продаж",
        "risk_word": "потери в воронке",
        "advice_word": "как поднять конверсию",
    },
    {
        "name": "Риск-контроль",
        "opening": "Приоритет разбора — не пропустить деньги, дедлайны, негатив клиентов и зависшие заявки.",
        "good_word": "стабильные участки",
        "risk_word": "сигналы риска",
        "advice_word": "контрольные меры",
    },
]


def _num(value):
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


def _safe_int(value, default=0):
    try:
        return int(value or default)
    except Exception:
        return default


def _date_str(value):
    return str(value) if value else None


def _truncate_text(value, limit=MAX_REPORT_CONTENT_CHARS):
    text = (value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


def _normalize_text(value):
    return re.sub(r"\s+", " ", str(value or "").lower()).strip()


def _format_money(value, currency="руб."):
    amount = _num(value)
    if amount == amount.to_integral():
        return f"{amount.quantize(Decimal('1'))} {currency}"
    return f"{amount.quantize(Decimal('0.01'))} {currency}"


def _percent(part, total):
    part = _num(part)
    total = _num(total)
    if total <= 0:
        return Decimal("0")
    return ((part / total) * Decimal("100")).quantize(Decimal("0.1"))


def _contains_any(text, keywords):
    normalized = _normalize_text(text)
    return any(keyword.lower() in normalized for keyword in keywords)


def _is_income_entry(entry_type: str) -> bool:
    normalized = str(entry_type or "").strip().lower()
    return normalized in {"income", "in", "plus", "credit", "deposit", "приход", "доход"}


def _score_report_quality(report_item):
    """
    Оценка качества заполнения отчёта.
    Это не KPI сотрудника, а подсказка администратору: насколько текст отчёта полезен для анализа.
    """
    content = report_item.get("content", "") or ""
    normalized = _normalize_text(content)
    flags = []
    score = 100

    if len(normalized) < 60:
        score -= 30
        flags.append("слишком короткий текст")
    elif len(normalized) < 140:
        score -= 12
        flags.append("мало деталей")

    if not _contains_any(normalized, CLIENT_KEYWORDS):
        score -= 12
        flags.append("не указано, с каким клиентом/заявкой работали")

    if not _contains_any(normalized, NEXT_STEP_KEYWORDS):
        score -= 18
        flags.append("нет следующего шага или дедлайна")

    if report_item.get("leads_processed", 0) == 0 and report_item.get("deals_closed", 0) == 0:
        score -= 10
        flags.append("нет движения по лидам/сделкам")

    if _num(report_item.get("income", 0)) == 0 and _num(report_item.get("expense", 0)) == 0 and not _contains_any(normalized, MONEY_KEYWORDS):
        score -= 8
        flags.append("нет финансового статуса")

    score = max(0, min(100, score))
    if not flags:
        flags.append("отчёт заполнен достаточно информативно")

    return score, flags


def _build_reports_payload(reports_qs):
    reports_payload = []
    office_stats = {}
    total_income = Decimal("0")
    total_expense = Decimal("0")
    total_leads = 0
    total_deals = 0
    total_quality = 0

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

        leads_processed = _safe_int(getattr(report, "leads_processed", 0))
        deals_closed = _safe_int(getattr(report, "deals_closed", 0))

        total_income += income_value
        total_expense += expense_value
        total_leads += leads_processed
        total_deals += deals_closed

        report_item = {
            "date": _date_str(getattr(report, "date", None)),
            "employee": employee_name,
            "office": office_name,
            "leads_processed": leads_processed,
            "deals_closed": deals_closed,
            "income": str(income_value),
            "expense": str(expense_value),
            "content": _truncate_text(getattr(report, "content", "") or ""),
        }
        quality_score, quality_flags = _score_report_quality(report_item)
        report_item["quality_score"] = quality_score
        report_item["quality_flags"] = quality_flags
        total_quality += quality_score

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
                "quality_total": 0,
            },
        )

        office_stats[office_key]["employees"].add(employee_name)
        office_stats[office_key]["reports_count"] += 1
        office_stats[office_key]["income"] += income_value
        office_stats[office_key]["expense"] += expense_value
        office_stats[office_key]["leads_processed"] += leads_processed
        office_stats[office_key]["deals_closed"] += deals_closed
        office_stats[office_key]["quality_total"] += quality_score

        reports_payload.append(report_item)

    office_summaries = []
    for _, stat in sorted(office_stats.items(), key=lambda item: item[1]["office_name"]):
        reports_count = stat["reports_count"] or 1
        conversion = _percent(stat["deals_closed"], stat["leads_processed"])
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
                "conversion_percent": str(conversion),
                "avg_report_quality": int(round(stat["quality_total"] / reports_count)),
            }
        )

    avg_quality = int(round(total_quality / len(reports_payload))) if reports_payload else 0

    summary_totals = {
        "reports_count": len(reports_payload),
        "reports_income_total": str(total_income),
        "reports_expense_total": str(total_expense),
        "reports_balance_total": str(total_income - total_expense),
        "leads_processed_total": total_leads,
        "deals_closed_total": total_deals,
        "conversion_percent": str(_percent(total_deals, total_leads)),
        "avg_report_quality": avg_quality,
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


def _pick_style_profile():
    """
    Специально выбираем стиль через SystemRandom, чтобы при новой генерации
    интонация отчёта могла отличаться даже при одинаковых фильтрах.
    """
    return random.SystemRandom().choice(STYLE_PROFILES)


def _scan_report_triggers(reports):
    trigger_counts = {
        key: {
            "title": config["title"],
            "count": 0,
            "severity": config["severity"],
            "recommendation": config["recommendation"],
            "examples": [],
        }
        for key, config in TRIGGER_GROUPS.items()
    }
    positive_examples = []

    for report in reports:
        content = report.get("content", "") or ""
        normalized = _normalize_text(content)
        employee = report.get("employee") or "Неизвестный сотрудник"
        office = report.get("office") or "Без офиса"
        preview = _truncate_text(content.replace("\n", " "), 120)

        for key, config in TRIGGER_GROUPS.items():
            matched = [kw for kw in config["keywords"] if kw.lower() in normalized]
            if matched:
                trigger_counts[key]["count"] += 1
                if len(trigger_counts[key]["examples"]) < MAX_TRIGGER_EXAMPLES:
                    trigger_counts[key]["examples"].append(
                        {
                            "employee": employee,
                            "office": office,
                            "preview": preview,
                            "matched": matched[:3],
                        }
                    )

        if _contains_any(normalized, POSITIVE_KEYWORDS) and len(positive_examples) < 5:
            positive_examples.append(
                {
                    "employee": employee,
                    "office": office,
                    "preview": preview,
                }
            )

    active_triggers = [
        item for item in trigger_counts.values()
        if item["count"] > 0
    ]
    active_triggers.sort(key=lambda item: (item["severity"], item["count"]), reverse=True)

    return active_triggers, positive_examples


def _collect_employee_stats(reports):
    stats = {}

    for report in reports:
        employee = report.get("employee") or "Неизвестный сотрудник"
        office = report.get("office") or "Без офиса"

        stats.setdefault(
            employee,
            {
                "employee": employee,
                "office": office,
                "reports_count": 0,
                "leads_processed": 0,
                "deals_closed": 0,
                "income": Decimal("0"),
                "expense": Decimal("0"),
                "quality_total": 0,
                "risk_reports": 0,
            },
        )

        stats[employee]["reports_count"] += 1
        stats[employee]["leads_processed"] += _safe_int(report.get("leads_processed", 0))
        stats[employee]["deals_closed"] += _safe_int(report.get("deals_closed", 0))
        stats[employee]["income"] += _num(report.get("income", 0))
        stats[employee]["expense"] += _num(report.get("expense", 0))
        stats[employee]["quality_total"] += _safe_int(report.get("quality_score", 0))

        content = _normalize_text(report.get("content", ""))
        if any(any(keyword.lower() in content for keyword in group["keywords"]) for group in TRIGGER_GROUPS.values()):
            stats[employee]["risk_reports"] += 1

    result = []
    for item in stats.values():
        reports_count = item["reports_count"] or 1
        item["balance"] = item["income"] - item["expense"]
        item["conversion_percent"] = str(_percent(item["deals_closed"], item["leads_processed"]))
        item["avg_quality"] = int(round(item["quality_total"] / reports_count))
        result.append(item)

    result.sort(
        key=lambda item: (
            item["deals_closed"],
            item["leads_processed"],
            item["balance"],
            item["avg_quality"],
        ),
        reverse=True,
    )
    return result


def _build_health_status(balance, finance_balance, conversion, avg_quality, active_triggers):
    critical_triggers = [t for t in active_triggers if t["severity"] >= 5]
    if balance < 0 or finance_balance < 0:
        return "🔴 Требует внимания: есть отрицательный баланс, нужен финансовый контроль."
    if critical_triggers:
        return "🟠 Есть риски: в отчётах найдены критичные триггеры по клиентам или оплатам."
    if _num(conversion) < 10 and _num(conversion) > 0:
        return "🟡 Средняя картина: сделки есть, но конверсию нужно усиливать."
    if avg_quality < 55:
        return "🟡 Данные слабые: отчёты заполнены неполно, анализ может быть неточным."
    return "🟢 Картина стабильная: критичных отклонений по выбранному периоду не видно."


def _make_period_label(payload):
    period = payload.get("period", {})
    date_from = period.get("date_from")
    date_to = period.get("date_to")
    office_id = period.get("office_id")

    if date_from and date_to:
        label = f"Период: {date_from} — {date_to}"
    elif date_from:
        label = f"Период: с {date_from}"
    elif date_to:
        label = f"Период: до {date_to}"
    else:
        label = "Период: все доступные данные"

    if office_id:
        label += f" | офис ID: {office_id}"

    return label


def _line_or_default(items, default):
    return items if items else [default]


def _generate_sl_ai_summary(payload: dict) -> str:
    """
    Внутренний движок SL_AI для генерации управленческого резюме.
    Это локальная имитация AI-аналитика: математика + триггеры + разные стили подачи.
    """
    totals = payload.get("summary_totals", {})
    offices = payload.get("office_summaries", [])
    reports = payload.get("recent_reports", [])
    finance_entries = payload.get("recent_finance_entries", [])

    income = _num(totals.get("reports_income_total", "0"))
    expense = _num(totals.get("reports_expense_total", "0"))
    balance = _num(totals.get("reports_balance_total", "0"))
    deals = _safe_int(totals.get("deals_closed_total", 0))
    leads = _safe_int(totals.get("leads_processed_total", 0))
    reports_count = _safe_int(totals.get("reports_count", 0))
    conversion = _num(totals.get("conversion_percent", "0"))
    avg_quality = _safe_int(totals.get("avg_report_quality", 0))

    payments_total = _num(payload.get("payments_total", "0"))
    expenses_total = _num(payload.get("expenses_total", "0"))
    finance_balance = _num(payload.get("office_finance_balance", "0"))

    style = _pick_style_profile()
    active_triggers, positive_examples = _scan_report_triggers(reports)
    employee_stats = _collect_employee_stats(reports)
    health_status = _build_health_status(balance, finance_balance, conversion, avg_quality, active_triggers)

    top_office = None
    if offices:
        top_office = sorted(
            offices,
            key=lambda item: (
                _safe_int(item.get("deals_closed", 0)),
                _safe_int(item.get("leads_processed", 0)),
                _num(item.get("balance", 0)),
            ),
            reverse=True,
        )[0]

    weakest_office = None
    if offices:
        weakest_office = sorted(
            offices,
            key=lambda item: (
                _num(item.get("balance", 0)),
                _safe_int(item.get("deals_closed", 0)),
                _safe_int(item.get("avg_report_quality", 0)),
            ),
        )[0]

    good_points = []
    if balance > 0:
        good_points.append(f"- По отчётам сохраняется положительный баланс: {_format_money(balance)}.")
    if deals > 0:
        good_points.append(f"- Закрыто сделок: {deals}. Это главный показатель результата за период.")
    if leads > 0:
        good_points.append(f"- В работу взято/обработано лидов: {leads}, конверсия в сделки — {conversion}%.")
    if finance_balance > 0:
        good_points.append(f"- По офисным финансовым записям сальдо положительное: {_format_money(finance_balance)}.")
    if avg_quality >= 75:
        good_points.append(f"- Среднее качество отчётов хорошее: {avg_quality}/100, данные пригодны для анализа.")
    for item in positive_examples[:3]:
        good_points.append(f"- Позитивный сигнал: {item['office']} / {item['employee']} — {item['preview']}")

    risk_points = []
    if balance < 0:
        risk_points.append(f"- Расходы по отчётам выше доходов: баланс {_format_money(balance)}.")
    if finance_balance < 0:
        risk_points.append(f"- Финансовые записи офисов дают отрицательное сальдо: {_format_money(finance_balance)}.")
    if leads > 0 and deals == 0:
        risk_points.append("- Лиды есть, но сделок нет: нужно проверить качество обработки заявок и дожим.")
    if avg_quality < 55:
        risk_points.append(f"- Среднее качество отчётов низкое: {avg_quality}/100. Часть данных может быть неполной.")
    if not reports:
        risk_points.append("- Отчётов за выбранный период нет, поэтому управленческий анализ ограничен.")

    lines = []

    lines.append(f"🧠 SL AI — {style['name']}")
    lines.append(style["opening"])
    lines.append(_make_period_label(payload))
    lines.append("")
    lines.append("📌 1. Главный вывод")
    lines.append(health_status)
    lines.append(
        f"Обработано отчётов: {reports_count}. Лидов: {leads}. Сделок: {deals}. "
        f"Конверсия: {conversion}%. Качество отчётов: {avg_quality}/100."
    )
    lines.append("")

    lines.append("📊 2. Цифры периода")
    lines.append(f"- Доход по отчётам: {_format_money(income)}")
    lines.append(f"- Расход по отчётам: {_format_money(expense)}")
    lines.append(f"- Баланс по отчётам: {_format_money(balance)}")
    lines.append(f"- Внешние платежи / Payments: {_format_money(payments_total)}")
    lines.append(f"- Внешние расходы / Expenses: {_format_money(expenses_total)}")
    lines.append(f"- Чистый баланс офисных фин. записей: {_format_money(finance_balance)}")
    lines.append("")

    lines.append(f"✅ 3. {style['good_word'].capitalize()}")
    lines.extend(_line_or_default(good_points, "- Сильные стороны не выделены: нужно больше данных по сделкам, оплатам и действиям сотрудников."))
    lines.append("")

    lines.append(f"⚠️ 4. {style['risk_word'].capitalize()}")
    lines.extend(_line_or_default(risk_points, "- Критичных финансовых или операционных отклонений по базовым показателям не видно."))

    if active_triggers:
        lines.append("- Найдены текстовые триггеры в отчётах:")
        for trigger in active_triggers[:5]:
            lines.append(f"  • {trigger['title']}: {trigger['count']} упомин.")
            for example in trigger["examples"][:2]:
                matched = ", ".join(example["matched"])
                lines.append(
                    f"    - {example['office']} / {example['employee']}: {example['preview']} "
                    f"(триггеры: {matched})"
                )
    else:
        lines.append("- По расширенному списку триггеров тревожных формулировок не найдено.")
    lines.append("")

    lines.append("🏢 5. Разбор по офисам")
    if offices:
        for office in offices:
            office_balance = _num(office.get("balance", "0"))
            icon = "🟢" if office_balance >= 0 else "🔴"
            lines.append(
                f"{icon} {office.get('office_name', 'Без офиса')}: "
                f"отчётов {office.get('reports_count', 0)}, "
                f"лидов {office.get('leads_processed', 0)}, "
                f"сделок {office.get('deals_closed', 0)}, "
                f"конверсия {office.get('conversion_percent', '0')}%, "
                f"баланс {_format_money(office_balance)}, "
                f"качество отчётов {office.get('avg_report_quality', 0)}/100."
            )
    else:
        lines.append("- Данные по офисам отсутствуют.")
    lines.append("")

    lines.append("👥 6. Сотрудники и качество отчётов")
    if employee_stats:
        for item in employee_stats[:MAX_EMPLOYEE_ROWS]:
            quality_icon = "🟢" if item["avg_quality"] >= 75 else "🟡" if item["avg_quality"] >= 50 else "🔴"
            lines.append(
                f"{quality_icon} {item['employee']} ({item['office']}): "
                f"отчётов {item['reports_count']}, лидов {item['leads_processed']}, "
                f"сделок {item['deals_closed']}, конверсия {item['conversion_percent']}%, "
                f"баланс {_format_money(item['balance'])}, "
                f"качество {item['avg_quality']}/100, риск-отчётов {item['risk_reports']}."
            )
    else:
        lines.append("- Нет данных по сотрудникам для сравнения.")
    lines.append("")

    lines.append("💰 7. Финансовые записи офисов")
    if finance_entries:
        for entry in finance_entries[:8]:
            entry_type = str(entry.get("entry_type") or "-")
            lines.append(
                f"- {entry.get('entry_date') or 'без даты'} | {entry.get('office')}: "
                f"{entry_type} — {_format_money(entry.get('amount', 0))}. "
                f"{entry.get('title') or ''}"
            )
    else:
        lines.append("- Отдельных финансовых записей офисов за период не найдено.")
    lines.append("")

    lines.append(f"🎯 8. {style['advice_word'].capitalize()}")
    recommendations = []

    if leads > 0 and deals == 0:
        recommendations.append("1. Проверить все активные лиды: у каждого должен быть статус, следующий шаг и дата следующего контакта.")
    else:
        recommendations.append("1. Разобрать лиды без сделки и понять, где именно теряется клиент: цена, документы, вуз, виза или слабый дожим.")

    if active_triggers:
        top_trigger = active_triggers[0]
        recommendations.append(f"2. Главный риск периода — «{top_trigger['title']}». {top_trigger['recommendation']}")
    else:
        recommendations.append("2. Сохранять контрольные звонки по клиентам, даже если явных проблем в отчётах нет.")

    if balance < 0 or finance_balance < 0:
        recommendations.append("3. Срочно сверить доходы, расходы, чеки и офисные записи. Отрицательный баланс нельзя оставлять без объяснения.")
    else:
        recommendations.append("3. Сверить данные отчётов с фактическими оплатами, чтобы исключить расхождение между CRM и кассой.")

    if avg_quality < 70:
        recommendations.append("4. Провести короткий инструктаж по отчётам: сотрудники должны писать факт, цифру, проблему, следующий шаг и дедлайн.")
    else:
        recommendations.append("4. Закрепить текущий формат отчётов и просить сотрудников добавлять больше конкретики по клиентам.")

    if top_office and _safe_int(top_office.get("deals_closed", 0)) > 0:
        recommendations.append(
            f"5. Забрать лучшие практики у офиса «{top_office.get('office_name')}» "
            f"и передать их офисам с более слабой конверсией."
        )
    elif weakest_office:
        recommendations.append(
            f"5. Отдельно проверить офис «{weakest_office.get('office_name')}»: "
            f"там слабее показатели по балансу/сделкам/качеству отчётов."
        )
    else:
        recommendations.append("5. Назначить ответственного за контроль ежедневного закрытия рабочего дня.")

    lines.extend(recommendations)
    lines.append("")

    lines.append("🚀 9. Дальнейшие рекомендации к улучшению")
    lines.append("- На сегодня: проверить все отчёты с триггерами, дозвониться до проблемных клиентов, закрыть финансовые расхождения.")
    lines.append("- На неделю: сравнить конверсию офисов, найти слабые этапы воронки, провести мини-разбор с менеджерами.")
    lines.append("- На систему: ввести правило — каждый отчёт должен содержать клиента/заявку, действие, результат, деньги, проблему и следующий шаг.")
    lines.append("")

    lines.append("🧾 10. Подсказка по качеству отчётов")
    if avg_quality >= 75:
        lines.append("- Отчёты в целом информативные. Для ещё лучшего анализа добавляйте больше конкретики по причинам отказов и оплатам.")
    elif avg_quality >= 50:
        lines.append("- Отчёты средние. Не хватает стабильной структуры: факт → цифра → проблема → следующий шаг.")
    else:
        lines.append("- Отчёты слабые. AI-анализ будет полезнее, если менеджеры начнут писать конкретные действия, суммы, дедлайны и статусы клиентов.")

    return "\n".join(lines)


def _empty_summary(payload):
    return {
        "provider": "SL_AI",
        "model": "rule-based-engine-v2-tone-triggers",
        "ai_used": False,
        "summary": (
            "Недостаточно данных для анализа: за выбранный период нет отчётов и нет финансовых записей.\n\n"
            "Что сделать:\n"
            "1. Проверьте фильтр даты и офиса.\n"
            "2. Убедитесь, что сотрудники закрывали рабочий день.\n"
            "3. Проверьте, что доходы/расходы внесены в систему.\n"
            "4. После появления данных запустите генерацию снова."
        ),
        "error": "Нет данных для анализа",
        "meta": {
            "period": payload.get("period", {}),
            "reports_count": 0,
            "offices_count": 0,
        },
    }


def _safe_error_summary(error_text, payload=None):
    payload = payload or {}
    return (
        "SL AI не смог полностью собрать автоматический анализ, но система не оставила администратора без подсказки.\n\n"
        "Возможные причины:\n"
        "1. В базе есть некорректная сумма, дата или пустое поле.\n"
        "2. Один из связанных модулей финансов/расходов временно недоступен.\n"
        "3. В отчёте есть данные неожиданного формата.\n\n"
        "Что сделать администратору:\n"
        "1. Проверить последние отчёты сотрудников за выбранный период.\n"
        "2. Проверить последние доходы/расходы и суммы.\n"
        "3. Если ошибка повторяется — отправить разработчику текст ошибки ниже.\n\n"
        f"Техническая ошибка: {error_text}"
    )


def build_admin_ai_summary(date_from=None, date_to=None, office_id=None):
    payload = {
        "period": {
            "date_from": _date_str(date_from),
            "date_to": _date_str(date_to),
            "office_id": office_id,
        },
        "summary_totals": {
            "reports_count": 0,
            "reports_income_total": "0",
            "reports_expense_total": "0",
            "reports_balance_total": "0",
            "leads_processed_total": 0,
            "deals_closed_total": 0,
            "conversion_percent": "0",
            "avg_report_quality": 0,
        },
        "payments_total": "0",
        "expenses_total": "0",
        "office_finance_balance": "0",
        "office_summaries": [],
        "recent_finance_entries": [],
        "recent_reports": [],
    }

    try:
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

        payload.update(
            {
                "summary_totals": summary_totals,
                "payments_total": str(payments_total),
                "expenses_total": str(expenses_total),
                "office_finance_balance": str(finance_balance),
                "office_summaries": office_summaries,
                "recent_finance_entries": finance_entries,
                "recent_reports": reports_payload,
            }
        )

        if not reports_payload and not finance_entries:
            return _empty_summary(payload)

        summary_text = _generate_sl_ai_summary(payload)
        error = None

    except Exception as e:
        logger.exception("SL_AI Engine Error")
        summary_text = _safe_error_summary(str(e), payload)
        error = str(e)

    return {
        "provider": "SL_AI",
        "model": "rule-based-engine-v2-tone-triggers",
        "ai_used": error is None,
        "summary": summary_text,
        "error": error,
        "meta": {
            "period": payload["period"],
            "reports_count": payload["summary_totals"].get("reports_count", 0),
            "offices_count": len(payload.get("office_summaries", [])),
            "payments_total": payload.get("payments_total", "0"),
            "expenses_total": payload.get("expenses_total", "0"),
            "office_finance_balance": payload.get("office_finance_balance", "0"),
            "avg_report_quality": payload["summary_totals"].get("avg_report_quality", 0),
            "conversion_percent": payload["summary_totals"].get("conversion_percent", "0"),
        },
    }