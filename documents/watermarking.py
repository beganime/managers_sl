import os
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile

try:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Mm
except Exception:  # pragma: no cover
    Document = None
    WD_ALIGN_PARAGRAPH = None
    Mm = None


def _get_watermark_path():
    raw = getattr(settings, 'DOCUMENT_WATERMARK_IMAGE', '') or os.getenv('DOCUMENT_WATERMARK_IMAGE', '')
    if not raw:
        return None

    watermark_path = Path(raw)
    if watermark_path.exists() and watermark_path.is_file():
        return watermark_path

    return None


def _iter_unique_footers(section):
    seen = set()

    for footer in (
        getattr(section, 'footer', None),
        getattr(section, 'first_page_footer', None),
        getattr(section, 'even_page_footer', None),
    ):
        if footer is None:
            continue
        footer_id = id(footer)
        if footer_id in seen:
            continue
        seen.add(footer_id)
        yield footer


def _append_watermark_to_footer(footer, watermark_path):
    if getattr(footer, 'is_linked_to_previous', False):
        footer.is_linked_to_previous = False

    paragraph = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run = paragraph.add_run()
    run.add_picture(str(watermark_path), width=Mm(35))


def build_approved_document(generated_document):
    source_field = getattr(generated_document, 'generated_file', None)
    if not source_field:
        return None

    source_name = getattr(source_field, 'name', '') or ''
    source_path = Path(getattr(source_field, 'path', ''))
    if not source_name.lower().endswith('.docx'):
        return None
    if not source_path.exists():
        return None
    if Document is None or WD_ALIGN_PARAGRAPH is None or Mm is None:
        return None

    watermark_path = _get_watermark_path()
    if watermark_path is None:
        return None

    try:
        doc = Document(str(source_path))

        added = 0
        for section in doc.sections:
            for footer in _iter_unique_footers(section):
                _append_watermark_to_footer(footer, watermark_path)
                added += 1

        if added == 0:
            return None

        buffer = BytesIO()
        doc.save(buffer)
        buffer.seek(0)

        approved_name = f'generated_documents/approved/approved_{Path(source_name).name}'
        return ContentFile(buffer.read(), name=approved_name)
    except Exception:
        return None