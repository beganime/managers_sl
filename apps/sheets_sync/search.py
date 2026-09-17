from django.conf import settings

from .client import GoogleSheetsGateway
from .models import SheetSearchSource


def configured_search_sources():
    sources = list(SheetSearchSource.objects.filter(is_active=True).values('title', 'spreadsheet_id'))
    primary_id = str(settings.GOOGLE_SHEETS_SPREADSHEET_ID or '').strip()
    if primary_id and all(source['spreadsheet_id'] != primary_id for source in sources):
        sources.insert(0, {'title': 'Основной учёт', 'spreadsheet_id': primary_id})
    return sources


def search_google_sheets(term, *, result_limit=100):
    needle = str(term or '').strip().casefold()
    if len(needle) < 2:
        return [], []
    results = []
    errors = []
    for source in configured_search_sources():
        try:
            gateway = GoogleSheetsGateway(spreadsheet_id=source['spreadsheet_id'])
            for sheet_name in sorted(gateway.sheet_titles()):
                for row_number, values in gateway.read_rows(sheet_name):
                    searchable = ' '.join(str(value or '') for value in values.values()).casefold()
                    if needle not in searchable:
                        continue
                    visible = [
                        {'label': key, 'value': value}
                        for key, value in values.items()
                        if str(value or '').strip() and key != 'Внутренний ID'
                    ]
                    results.append({
                        'source': source['title'],
                        'spreadsheet_id': source['spreadsheet_id'],
                        'sheet': sheet_name,
                        'row': row_number,
                        'values': visible,
                    })
                    if len(results) >= result_limit:
                        return results, errors
        except Exception as exc:
            errors.append(f"{source['title']}: {str(exc)[:180]}")
    return results, errors
