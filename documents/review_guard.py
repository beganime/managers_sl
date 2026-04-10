from functools import lru_cache

from django.core.exceptions import ObjectDoesNotExist
from django.db import connection
from django.db.utils import OperationalError, ProgrammingError

DOCUMENT_REVIEW_TABLE = "documents_documentreview"


@lru_cache(maxsize=1)
def has_document_review_table() -> bool:
    try:
        with connection.cursor() as cursor:
            tables = connection.introspection.table_names(cursor)
        return DOCUMENT_REVIEW_TABLE in tables
    except (ProgrammingError, OperationalError):
        return False


def clear_document_review_table_cache() -> None:
    has_document_review_table.cache_clear()


def safe_get_document_review(document):
    if not has_document_review_table():
        return None

    try:
        return document.review
    except ObjectDoesNotExist:
        return None
    except (ProgrammingError, OperationalError):
        return None