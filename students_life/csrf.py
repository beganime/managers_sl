from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme


def _append_query_param(url, key, value):
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query[key] = value
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def csrf_failure(request, reason=''):
    """Keep portal users out of the plain Django 403 page when a form token expires."""
    is_portal_request = request.path.startswith('/portal/') or request.path == '/'
    if not is_portal_request:
        return HttpResponseForbidden('CSRF verification failed.')

    if request.path.startswith('/portal/login/'):
        return redirect(_append_query_param(reverse('portal:login'), 'csrf_error', '1'))

    referer = request.META.get('HTTP_REFERER') or ''
    if referer and url_has_allowed_host_and_scheme(
        referer,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(_append_query_param(referer, 'csrf_error', '1'))

    user = getattr(request, 'user', None)
    if user is not None and user.is_authenticated:
        return redirect(_append_query_param(reverse('portal:dashboard'), 'csrf_error', '1'))
    return redirect(_append_query_param(reverse('portal:login'), 'csrf_error', '1'))
