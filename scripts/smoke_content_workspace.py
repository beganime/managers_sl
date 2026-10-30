"""Read-only production smoke: no accounts, content or notifications created."""
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory
from apps.portal.content_views import ClientContentView, ClientNewsView, news_request
from apps.portal.views import UniversityFormView, ProgramFormView

user = get_user_model().objects.filter(is_superuser=True, is_active=True).first()
assert user, 'No active administrator for read-only page rendering'
for view in (ClientContentView, ClientNewsView, UniversityFormView, ProgramFormView):
    request = RequestFactory().get('/portal/client-content/', HTTP_HOST='manager-sl.ru')
    request.user = user
    request.session = {}
    request._messages = FallbackStorage(request)
    response = view.as_view()(request)
    response.render()
    print(view.__name__, response.status_code)
payload = news_request()
print('News service GET:', 'OK' if isinstance(payload.get('results'), list) else 'INVALID')
import requests
for url, expected in (
    ('https://manager-sl.ru/client-app/api/v1/news/', 200),
    ('https://manager-sl.ru/client-app/api/v1/news/manage/', 403),
    ('https://manager-sl.ru/api/client/v1/universities/?limit=1', 200),
    ('https://manager-sl.ru/api/client/v1/programs/?limit=1', 200),
):
    response = requests.get(url, timeout=(10, 25))
    print(url, response.status_code)
    assert response.status_code == expected
