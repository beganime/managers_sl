import re

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class SheetsSyncError(RuntimeError):
    pass


class HeaderMismatchError(SheetsSyncError):
    pass


def column_letter(index):
    result = ''
    value = index + 1
    while value:
        value, remainder = divmod(value - 1, 26)
        result = chr(65 + remainder) + result
    return result


def quote_sheet(title):
    return "'" + str(title).replace("'", "''") + "'"


class GoogleSheetsGateway:
    def __init__(self, spreadsheet_id=None, credentials_file=None):
        self.spreadsheet_id = spreadsheet_id or settings.GOOGLE_SHEETS_SPREADSHEET_ID
        self.credentials_file = credentials_file or settings.GOOGLE_SHEETS_CREDENTIALS_FILE
        if not self.spreadsheet_id:
            raise ImproperlyConfigured('GOOGLE_SHEETS_SPREADSHEET_ID не задан.')
        if not self.credentials_file:
            raise ImproperlyConfigured('GOOGLE_SHEETS_CREDENTIALS_FILE не задан.')
        self._service = None

    @property
    def service(self):
        if self._service is None:
            try:
                from google.oauth2 import service_account
                from googleapiclient.discovery import build
            except ImportError as exc:
                raise ImproperlyConfigured(
                    'Установите google-api-python-client и google-auth.'
                ) from exc

            credentials = service_account.Credentials.from_service_account_file(
                self.credentials_file,
                scopes=['https://www.googleapis.com/auth/spreadsheets'],
            )
            self._service = build('sheets', 'v4', credentials=credentials, cache_discovery=False)
        return self._service

    def metadata(self):
        return self.service.spreadsheets().get(
            spreadsheetId=self.spreadsheet_id,
            includeGridData=False,
        ).execute()

    def health_check(self):
        metadata = self.metadata()
        return {
            'spreadsheet_id': metadata.get('spreadsheetId'),
            'title': metadata.get('properties', {}).get('title', ''),
            'sheets': [item['properties']['title'] for item in metadata.get('sheets', [])],
        }

    def sheet_titles(self):
        return set(self.health_check()['sheets'])

    def sheet_id(self, sheet_name):
        for item in self.metadata().get('sheets', []):
            properties = item.get('properties', {})
            if properties.get('title') == sheet_name:
                return properties.get('sheetId')
        raise SheetsSyncError(f'Лист {sheet_name} не найден.')

    def headers(self, sheet_name):
        result = self.service.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id,
            range=f'{quote_sheet(sheet_name)}!1:1',
        ).execute()
        values = result.get('values', [])
        headers = values[0] if values else []
        duplicates = {header for header in headers if header and headers.count(header) > 1}
        if duplicates:
            raise HeaderMismatchError(
                f'В листе {sheet_name} повторяются заголовки: {", ".join(sorted(duplicates))}'
            )
        return headers

    def ensure_sheet(self, sheet_name, headers):
        if sheet_name not in self.sheet_titles():
            response = self.service.spreadsheets().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={'requests': [{'addSheet': {'properties': {'title': sheet_name}}}]},
            ).execute()
            sheet_id = response['replies'][0]['addSheet']['properties']['sheetId']
            self.service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=f'{quote_sheet(sheet_name)}!A1',
                valueInputOption='RAW',
                body={'values': [list(headers)]},
            ).execute()
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={'requests': [
                    {
                        'updateSheetProperties': {
                            'properties': {'sheetId': sheet_id, 'gridProperties': {'frozenRowCount': 1}},
                            'fields': 'gridProperties.frozenRowCount',
                        }
                    },
                    {
                        'repeatCell': {
                            'range': {'sheetId': sheet_id, 'startRowIndex': 0, 'endRowIndex': 1, 'startColumnIndex': 0, 'endColumnIndex': len(headers)},
                            'cell': {'userEnteredFormat': {
                                'backgroundColor': {'red': 1, 'green': 1, 'blue': 1},
                                'textFormat': {'foregroundColor': {'red': 0, 'green': 0, 'blue': 0}, 'bold': True},
                                'horizontalAlignment': 'CENTER',
                                'wrapStrategy': 'WRAP',
                            }},
                            'fields': 'userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,wrapStrategy)',
                        }
                    },
                ]},
            ).execute()
        existing = self.headers(sheet_name)
        missing = [header for header in headers if header not in existing]
        if missing:
            start_column = column_letter(len(existing))
            self.service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=f'{quote_sheet(sheet_name)}!{start_column}1',
                valueInputOption='RAW',
                body={'values': [missing]},
            ).execute()
            sheet_id = self.sheet_id(sheet_name)
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={'requests': [{
                    'repeatCell': {
                        'range': {
                            'sheetId': sheet_id,
                            'startRowIndex': 0,
                            'endRowIndex': 1,
                            'startColumnIndex': len(existing),
                            'endColumnIndex': len(existing) + len(missing),
                        },
                        'cell': {'userEnteredFormat': {
                            'backgroundColor': {'red': 1, 'green': 1, 'blue': 1},
                            'textFormat': {
                                'foregroundColor': {'red': 0, 'green': 0, 'blue': 0},
                                'bold': True,
                            },
                            'horizontalAlignment': 'CENTER',
                            'wrapStrategy': 'WRAP',
                        }},
                        'fields': 'userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,wrapStrategy)',
                    }
                }]},
            ).execute()

    def replace_reference_column(self, sheet_name, column, header, values):
        existing_headers = self.headers(sheet_name)
        column_index = ord(column.upper()) - 65
        if column_index >= len(existing_headers) or existing_headers[column_index] != header:
            raise HeaderMismatchError(
                f'Ожидался заголовок {header} в {sheet_name}!{column}1.'
            )
        quoted = quote_sheet(sheet_name)
        self.service.spreadsheets().values().clear(
            spreadsheetId=self.spreadsheet_id,
            range=f'{quoted}!{column}2:{column}1000',
            body={},
        ).execute()
        rows = [[str(value)] for value in values if str(value).strip()]
        if rows:
            self.service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=f'{quoted}!{column}2',
                valueInputOption='RAW',
                body={'values': rows},
            ).execute()
        return len(rows)

    def set_dropdown_validation(self, sheet_name, header, values, start_row=2, end_row=2000):
        headers = self.headers(sheet_name)
        if header not in headers:
            raise HeaderMismatchError(f'В листе {sheet_name} нет столбца {header}.')
        column_index = headers.index(header)
        self.service.spreadsheets().batchUpdate(
            spreadsheetId=self.spreadsheet_id,
            body={
                'requests': [{
                    'setDataValidation': {
                        'range': {
                            'sheetId': self.sheet_id(sheet_name),
                            'startRowIndex': max(int(start_row) - 1, 1),
                            'endRowIndex': max(int(end_row), int(start_row)),
                            'startColumnIndex': column_index,
                            'endColumnIndex': column_index + 1,
                        },
                        'rule': {
                            'condition': {
                                'type': 'ONE_OF_LIST',
                                'values': [
                                    {'userEnteredValue': str(value)}
                                    for value in values
                                ],
                            },
                            'strict': True,
                            'showCustomUi': True,
                            'inputMessage': 'Выберите статус обработки анкеты.',
                        },
                    }
                }],
            },
        ).execute()

    def find_row(self, sheet_name, identity_header, identity_value):
        headers = self.headers(sheet_name)
        if identity_header not in headers:
            raise HeaderMismatchError(
                f'В листе {sheet_name} нет ключевого столбца {identity_header}.'
            )
        column = column_letter(headers.index(identity_header))
        result = self.service.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id,
            range=f'{quote_sheet(sheet_name)}!{column}2:{column}',
        ).execute()
        matches = []
        for offset, row in enumerate(result.get('values', []), start=2):
            if row and str(row[0]).strip() == str(identity_value).strip():
                matches.append(offset)
        if len(matches) > 1:
            raise SheetsSyncError(
                f'В листе {sheet_name} найдено несколько строк для {identity_value}.'
            )
        return matches[0] if matches else None

    def read_rows(self, sheet_name, start_row=2):
        """Read a sheet once and return rows mapped by their header names."""
        headers = self.headers(sheet_name)
        if not headers:
            return []
        result = self.service.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id,
            range=(
                f'{quote_sheet(sheet_name)}!A{start_row}:'
                f'{column_letter(len(headers) - 1)}'
            ),
        ).execute()
        rows = []
        for row_number, source_values in enumerate(
            result.get('values', []),
            start=start_row,
        ):
            padded = list(source_values) + [''] * (len(headers) - len(source_values))
            rows.append({
                'row_number': row_number,
                'values': dict(zip(headers, padded[:len(headers)])),
            })
        return rows

    def upsert_row(
        self,
        sheet_name,
        identity_header,
        identity_value,
        values,
        create_only_values=None,
    ):
        create_only_values = create_only_values or {}
        headers = self.headers(sheet_name)
        unknown = [
            header
            for header in (*values, *create_only_values)
            if header not in headers
        ]
        if unknown:
            raise HeaderMismatchError(
                f'В листе {sheet_name} отсутствуют столбцы: {", ".join(unknown)}'
            )
        row_number = self.find_row(sheet_name, identity_header, identity_value)
        if row_number is None:
            row = [''] * len(headers)
            for header, value in {**create_only_values, **values}.items():
                row[headers.index(header)] = value
            response = self.service.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range=f'{quote_sheet(sheet_name)}!A:{column_letter(len(headers) - 1)}',
                valueInputOption='USER_ENTERED',
                insertDataOption='INSERT_ROWS',
                body={'values': [row]},
            ).execute()
            updated_range = response.get('updates', {}).get('updatedRange', '')
            match = re.search(r'![A-Z]+(\d+):', updated_range)
            if not match:
                raise SheetsSyncError(f'Google Sheets не вернул номер добавленной строки: {updated_range}')
            return int(match.group(1)), True

        updates = []
        for header, value in values.items():
            column = column_letter(headers.index(header))
            updates.append({
                'range': f'{quote_sheet(sheet_name)}!{column}{row_number}',
                'values': [[value]],
            })
        if updates:
            self.service.spreadsheets().values().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={'valueInputOption': 'USER_ENTERED', 'data': updates},
            ).execute()
        return row_number, False
