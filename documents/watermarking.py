import os
import shutil
from pathlib import Path

from django.conf import settings
from django.core.files import File
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
    return getattr(settings, 'DOCUMENT_WATERMARK_IMAGE', '') or os.getenv('DOCUMENT_WATERMARK_IMAGE', '')


def build_approved_document(generated_document):
    source_field = getattr(generated_document, 'generated_file', None)
    if not source_field:
        return None

    source_path = Path(source_field.path)
    if not source_path.exists():
        return None

    watermark_path = _get_watermark_path()
    target_name = f'approved_{source_path.name}'
    target_rel = f'generated_documents/approved/{target_name}'
    target_abs = source_path.parent / target_name

    # Если watermark не настроен или это не docx — просто копируем файл
    if not watermark_path or not str(source_path).lower().endswith('.docx') or Document is None:
        shutil.copyfile(source_path, target_abs)
        with open(target_abs, 'rb') as f:
            return File(f, name=target_rel)

    doc = Document(str(source_path))

    section = doc.sections[-1]
    footer = section.footer
    paragraph = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run = paragraph.add_run()
    try:
        run.add_picture(watermark_path, width=Mm(35))
    except Exception:
        # fallback: если картинка не открылась, просто копируем исходник
        shutil.copyfile(source_path, target_abs)
        with open(target_abs, 'rb') as f:
            return File(f, name=target_rel)

    doc.save(str(target_abs))
    with open(target_abs, 'rb') as f:
        return File(f, name=target_rel)