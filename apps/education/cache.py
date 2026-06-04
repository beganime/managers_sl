from urllib.parse import urlencode

from django.core.cache import cache


EDUCATION_CACHE_TTL = 60 * 10
EDUCATION_CACHE_REGISTRY_KEY = 'education_catalog_cache_keys'


def normalize_query_params(params):
    pairs = []
    for key in sorted(params.keys()):
        values = params.getlist(key) if hasattr(params, 'getlist') else [params[key]]
        for value in sorted(str(item) for item in values):
            pairs.append((key, value))
    return urlencode(pairs)


def make_education_cache_key(namespace, request=None, *, scope='public', extra=''):
    query = normalize_query_params(request.GET) if request is not None else ''
    return f'education:{namespace}:{scope}:{query}:{extra}'


def remember_education_cache_key(key):
    keys = set(cache.get(EDUCATION_CACHE_REGISTRY_KEY, []))
    keys.add(key)
    cache.set(EDUCATION_CACHE_REGISTRY_KEY, sorted(keys), None)


def education_cache_get(key):
    return cache.get(key)


def education_cache_set(key, value, timeout=EDUCATION_CACHE_TTL):
    cache.set(key, value, timeout)
    remember_education_cache_key(key)


def clear_education_cache():
    keys = cache.get(EDUCATION_CACHE_REGISTRY_KEY, [])
    for key in keys:
        cache.delete(key)
    cache.delete(EDUCATION_CACHE_REGISTRY_KEY)
