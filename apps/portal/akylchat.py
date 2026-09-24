import time

import requests

from django.conf import settings


class AkylChatError(RuntimeError):
    pass


class AkylChatClient:
    def __init__(self):
        self.base_url = str(getattr(settings, 'AKYLCHAT_API_BASE_URL', '') or '').rstrip('/')
        self.token = str(getattr(settings, 'AKYLCHAT_SERVICE_TOKEN', '') or '')
        self.timeout = int(getattr(settings, 'SERVICE_REQUEST_TIMEOUT', 20))

    @property
    def configured(self):
        return bool(self.base_url and self.token)

    def _request(self, method, path, *, params=None, data=None, files=None):
        if not self.configured:
            raise AkylChatError('Связь с Akylchat ещё не настроена.')
        try:
            response = requests.request(
                method,
                f'{self.base_url}/{path.lstrip("/")}',
                headers={'Authorization': f'Bearer {self.token}', 'Accept': 'application/json'},
                params=params,
                data=data,
                files=files,
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            detail = ''
            if getattr(exc, 'response', None) is not None:
                try:
                    detail = str(exc.response.json().get('detail') or '')
                except (TypeError, ValueError, AttributeError):
                    detail = exc.response.text[:300]
            raise AkylChatError(detail or 'Akylchat временно недоступен.') from exc
        return response.json() if response.content else {}

    def rooms(self):
        return self._request('GET', 'internal/sl/support-chats/', params={'actor': 'manager'})

    def room(self, sl_id):
        normalized_sl_id = str(sl_id or '').strip().upper()
        payload = self._request(
            'GET',
            'internal/sl/support-chats/',
            params={'actor': 'manager', 'sl_id': normalized_sl_id},
        )
        matches = [
            item for item in payload.get('results', [])
            if str(item.get('sl_id') or '').strip().upper() == normalized_sl_id
        ]
        if len(matches) != 1 or not matches[0].get('id'):
            raise AkylChatError('Не удалось однозначно определить чат этого клиента.')
        return matches[0]

    def messages(self, sl_id):
        room = self.room(sl_id)
        payload = self._request(
            'GET',
            f'internal/sl/support-chats/{sl_id}/messages/',
            params={'actor': 'manager', '_': int(time.time() * 1000)},
        )
        room_id = str(room['id'])
        results = payload.get('results', [])
        if any(str(item.get('room') or '') != room_id for item in results):
            raise AkylChatError('Сервис вернул сообщения другого клиента.')
        return {**payload, 'results': results, 'sl_id': room.get('sl_id'), 'room_id': room_id}

    def send_message(self, sl_id, *, text='', upload=None, manager_name=''):
        room = self.room(sl_id)
        files = None
        if upload:
            files = {
                'file': (
                    upload.name,
                    upload.file,
                    getattr(upload, 'content_type', None) or 'application/octet-stream',
                )
            }
        payload = self._request(
            'POST',
            f'internal/sl/support-chats/{sl_id}/messages/',
            data={'actor': 'manager', 'text': text, 'manager_name': manager_name},
            files=files,
        )
        if payload.get('room') and str(payload['room']) != str(room['id']):
            raise AkylChatError('Сервис подтвердил отправку в другой чат.')
        return payload

    def mark_read(self, sl_id):
        return self._request(
            'POST', f'internal/sl/support-chats/{sl_id}/read/', data={'actor': 'manager'}
        )
