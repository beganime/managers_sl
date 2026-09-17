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

    def messages(self, sl_id):
        return self._request(
            'GET', f'internal/sl/support-chats/{sl_id}/messages/', params={'actor': 'manager'}
        )

    def send_message(self, sl_id, *, text='', upload=None, manager_name=''):
        files = None
        if upload:
            files = {
                'file': (
                    upload.name,
                    upload.file,
                    getattr(upload, 'content_type', None) or 'application/octet-stream',
                )
            }
        return self._request(
            'POST',
            f'internal/sl/support-chats/{sl_id}/messages/',
            data={'actor': 'manager', 'text': text, 'manager_name': manager_name},
            files=files,
        )

    def mark_read(self, sl_id):
        return self._request(
            'POST', f'internal/sl/support-chats/{sl_id}/read/', data={'actor': 'manager'}
        )
