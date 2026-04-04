import json
import os
from decimal import Decimal

import requests
from django.conf import settings
from django.db.models import Sum

from analytics.finance_models import summarize_office_finances
from analytics.models import Payment
from .models import DailyReport


def _safe_decimal(value):
    return Decimal(str(value or 0)).quantize(Decimal('0.01'))


def build_summary_payload(date_from=None, date_to=None, office_id=None):
    reports_qs = DailyReport.objects.select_related('employee', 'employee__office').all()
    payments_qs = Payment.objects.select_related('manager', 'manager__office').all()

    if date_from:
        reports_qs = reports_qs.filter(date__gte=date_from)
        payments_qs = payments_qs.filter(payment_date__gte=date_from)
    if date_to:
        reports_qs = reports_qs.filter(date__lte=date_to)
        payments_qs = payments_qs.filter(payment_date__lte=date_to)
    if office_id:
        reports_qs = reports_qs.filter(employee__office_id=office_id)
        payments_qs = payments_qs.filter(manager__office_id=office_id)

    reports = []
    offices = {}
    for report in reports_qs.order_by('-date', 'employee__first_name'):
        reports.append(
            {
                'date': str(report.date),
                'employee': f'{report.employee.first_name} {report.employee.last_name}'.strip() or report.employee.email,
                'office': getattr(getattr(report.employee, 'office', None), 'city', None),
                'content': report.content,
                'leads_processed': report.leads_processed,
                'deals_closed': report.deals_closed,
                'income': str(report.income),
                'expense': str(report.expense),
                'net_result': str(report.net_result),
            }
        )

        office = getattr(report.employee, 'office', None)
        if office and office.id not in offices:
            offices[office.id] = office

    payments_total = _safe_decimal(payments_qs.aggregate(total=Sum('amount_usd'))['total'])

    office_summaries = []
    for office in offices.values():
        fin = summarize_office_finances(office, date_from=date_from, date_to=date_to)
        office_summaries.append(
            {
                'office_id': office.id,
                'office_name': office.city,
                'monthly_revenue': str(_safe_decimal(getattr(office, 'monthly_revenue', 0))),
                'cashflow_income_usd': str(fin['income_usd']),
                'cashflow_expense_usd': str(fin['expense_usd']),
                'cashflow_net_usd': str(fin['net_usd']),
            }
        )

    return {
        'period': {'date_from': str(date_from) if date_from else None, 'date_to': str(date_to) if date_to else None},
        'payments_total_usd': str(payments_total),
        'office_summaries': office_summaries,
        'reports': reports,
    }


def _build_prompt(payload):
    return f"""
Ты — аналитик управленческой отчётности.
На основе переданных данных подготовь единый итоговый отчёт на русском языке.

Нужна структура:
1. Общая картина
2. Что хорошо
3. Что плохо / риски
4. Офисы и менеджеры, кто тянет план, кто отстаёт
5. Доходы / расходы / вывод по марже
6. Конкретные рекомендации админу на ближайшие 3-7 дней

Данные JSON:
{json.dumps(payload, ensure_ascii=False)}
""".strip()


def call_openai(prompt):
    api_key = getattr(settings, 'OPENAI_API_KEY', '') or os.getenv('OPENAI_API_KEY', '')
    model = getattr(settings, 'OPENAI_MODEL', 'gpt-4o-mini') or os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
    if not api_key:
        return None

    response = requests.post(
        'https://api.openai.com/v1/chat/completions',
        headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
        json={
            'model': model,
            'messages': [
                {'role': 'system', 'content': 'Ты делаешь управленческие итоговые отчёты.'},
                {'role': 'user', 'content': prompt},
            ],
            'temperature': 0.3,
        },
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    return data['choices'][0]['message']['content'].strip()


def call_gemini(prompt):
    api_key = getattr(settings, 'GEMINI_API_KEY', '') or os.getenv('GEMINI_API_KEY', '')
    model = getattr(settings, 'GEMINI_MODEL', 'gemini-1.5-flash') or os.getenv('GEMINI_MODEL', 'gemini-1.5-flash')
    if not api_key:
        return None

    response = requests.post(
        f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}',
        headers={'Content-Type': 'application/json'},
        json={
            'contents': [
                {
                    'parts': [{'text': prompt}],
                }
            ]
        },
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    return data['candidates'][0]['content']['parts'][0]['text'].strip()


def build_admin_ai_summary(date_from=None, date_to=None, office_id=None):
    payload = build_summary_payload(date_from=date_from, date_to=date_to, office_id=office_id)
    prompt = _build_prompt(payload)
    provider = (getattr(settings, 'AI_PROVIDER', '') or os.getenv('AI_PROVIDER', '') or 'openai').lower()

    summary_text = None
    error_message = None

    try:
        if provider == 'gemini':
            summary_text = call_gemini(prompt)
        else:
            summary_text = call_openai(prompt)
    except Exception as exc:
        error_message = str(exc)

    if not summary_text:
        # fallback, если AI не настроен
        summary_text = (
            'AI-резюме не было сгенерировано автоматически. '
            'Проверьте ключи API и настройки AI_PROVIDER. '
            f'Всего платежей (USD): {payload["payments_total_usd"]}. '
            f'Количество отчётов: {len(payload["reports"])}. '
            f'Количество офисов в отчёте: {len(payload["office_summaries"])}.'
        )

    return {
        'provider': provider,
        'summary': summary_text,
        'error': error_message,
        'payload': payload,
    }