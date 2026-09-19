from django.http import JsonResponse
from django.shortcuts import render
from django.urls import NoReverseMatch, reverse
from django.utils.http import url_has_allowed_host_and_scheme


ERROR_COPY = {
    400: {
        'eyebrow': 'Некорректный запрос',
        'title': 'Не удалось обработать данные',
        'description': 'Проверьте заполненные поля, обновите страницу и повторите действие.',
        'icon': 'file-warning',
    },
    403: {
        'eyebrow': 'Доступ ограничен',
        'title': 'Этот раздел доступен только администратору',
        'description': 'Ваша учётная запись не имеет прав для этого действия. Вернитесь назад или войдите под учётной записью администратора.',
        'icon': 'shield-alert',
    },
    404: {
        'eyebrow': 'Страница не найдена',
        'title': 'Такого адреса больше нет',
        'description': 'Возможно, ссылка устарела или страница была перемещена. Вернитесь назад либо откройте дашборд.',
        'icon': 'map-pinned',
    },
    500: {
        'eyebrow': 'Временная ошибка',
        'title': 'Сервис не смог завершить действие',
        'description': 'Данные не потеряны. Подождите немного и повторите попытку. Если ошибка повторится, сообщите администратору время и название страницы.',
        'icon': 'server-crash',
    },
}


def _safe_reverse(name, fallback):
    try:
        return reverse(name)
    except NoReverseMatch:
        return fallback


def _is_api_request(request):
    accept = str(request.headers.get('Accept') or '').lower()
    return request.path.startswith('/api/') or 'application/json' in accept


def _back_url(request, fallback):
    referer = str(request.META.get('HTTP_REFERER') or '')
    if referer and url_has_allowed_host_and_scheme(
        referer,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return referer
    return fallback


def error_response(request, status, exception=None):
    copy = ERROR_COPY[status]
    if _is_api_request(request):
        detail = copy['title']
        if status == 403 and exception and str(exception):
            detail = str(exception)
        return JsonResponse({'detail': detail, 'status': status}, status=status)

    user = getattr(request, 'user', None)
    is_authenticated = bool(user and user.is_authenticated)
    dashboard_url = _safe_reverse('portal:dashboard', '/portal/')
    login_url = _safe_reverse('portal:login', '/portal/login/')
    logout_url = _safe_reverse('portal:logout', login_url)
    detail = ''
    if status == 403 and exception and str(exception):
        detail = str(exception)

    context = {
        **copy,
        'status_code': status,
        'detail': detail,
        'back_url': _back_url(request, dashboard_url if is_authenticated else login_url),
        'primary_url': logout_url if status == 403 and is_authenticated else (dashboard_url if is_authenticated else login_url),
        'primary_label': 'Войти как администратор' if status == 403 else ('Открыть дашборд' if is_authenticated else 'Войти в систему'),
    }
    return render(request, 'errors/error.html', context=context, status=status)


def bad_request(request, exception=None):
    return error_response(request, 400, exception)


def permission_denied(request, exception=None):
    return error_response(request, 403, exception)


def page_not_found(request, exception=None):
    return error_response(request, 404, exception)


def server_error(request):
    return error_response(request, 500)
