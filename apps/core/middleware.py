from django.core.cache import cache
from django.contrib.auth import get_user_model
from django.utils import timezone


class EmployeeActivityMiddleware:
    """Record meaningful authenticated web activity without writing on every request."""

    EXCLUDED_PREFIXES = ('/static/', '/media/', '/health/', '/favicon')
    CACHE_SECONDS = 60

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        user = getattr(request, 'user', None)
        if (
            user
            and user.is_authenticated
            and request.path.startswith(('/portal/', '/admin/'))
            and not request.path.startswith(self.EXCLUDED_PREFIXES)
        ):
            cache_key = f'employee-activity:{user.pk}'
            if cache.add(cache_key, '1', timeout=self.CACHE_SECONDS):
                # ``request.user`` is normally a SimpleLazyObject.  ``type(user)``
                # is therefore not the custom User model and causes a 500 after a
                # successful login.  Use the configured model explicitly.
                get_user_model().objects.filter(pk=user.pk).update(last_activity=timezone.now())
        return response
