import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from PIL import Image

try:
    import pymupdf
except Exception:  # pragma: no cover
    pymupdf = None


logger = logging.getLogger(__name__)

EXECUTOR_WORD = "исполнитель"

CONSENT_TEMPLATE_PREFIX = "согласие"
DEFAULT_WATERMARK_WIDTH_MM = 40


def _mm_to_pt(value_mm: float) -> float:
    return float(value_mm) * 72.0 / 25.4


def _normalize_title(value: str) -> str:
    """
    Нормализуем название шаблона/документа, чтобы проверка работала стабильно:
    - убираем лишние пробелы;
    - приводим к нижнему регистру;
    - заменяем ё на е;
    - убираем кавычки и невидимые символы в начале.
    """
    text = str(value or "")
    text = text.replace("\ufeff", "")
    text = text.replace("ё", "е").replace("Ё", "Е")
    text = text.strip()

    text = re.sub(r"^[\s\"'«»“”„.,:;()\[\]{}\-–—_]+", "", text)
    text = re.sub(r"\s+", " ", text)

    return text.casefold()


def _document_title_candidates(generated_document, source_docx_path: Path | None = None) -> list[str]:
    candidates: list[str] = []

    template = getattr(generated_document, "template", None)
    template_title = getattr(template, "title", "") if template else ""
    document_title = getattr(generated_document, "title", "") or ""

    if template_title:
        candidates.append(str(template_title))

    if document_title:
        candidates.append(str(document_title))

    if source_docx_path is not None:
        candidates.append(source_docx_path.stem)

    return candidates


def _is_consent_document(generated_document, source_docx_path: Path | None = None) -> bool:
    """
    Если шаблон/документ начинается со слова 'СОГЛАСИЕ',
    approved PDF делаем без watermark.
    """
    for title in _document_title_candidates(generated_document, source_docx_path):
        normalized = _normalize_title(title)

        if normalized.startswith(CONSENT_TEMPLATE_PREFIX):
            logger.info(
                "Document %s matched consent template rule. Title=%r. Watermark will be skipped.",
                getattr(generated_document, "id", None),
                title,
            )
            return True

    return False


def _candidate_watermark_paths(raw: str) -> list[Path]:
    if not raw:
        return []

    base_dir = Path(getattr(settings, "BASE_DIR", Path.cwd()))
    raw_path = Path(raw)

    candidates = [
        raw_path,
        base_dir / raw,
        base_dir / "branding" / raw,
        base_dir / "media" / raw,
    ]

    unique: list[Path] = []
    seen = set()

    for item in candidates:
        key = str(item)

        if key in seen:
            continue

        seen.add(key)
        unique.append(item)

    return unique


def _get_watermark_path():
    raw = getattr(settings, "DOCUMENT_WATERMARK_IMAGE", "") or os.getenv("DOCUMENT_WATERMARK_IMAGE", "")

    if not raw:
        logger.error("DOCUMENT_WATERMARK_IMAGE is empty")
        return None

    candidates = _candidate_watermark_paths(raw)

    for candidate in candidates:
        try:
            if candidate.exists() and candidate.is_file():
                logger.info("Watermark resolved to: %s", candidate)
                return candidate
        except Exception:
            logger.exception("Failed while checking watermark path candidate: %s", candidate)

    logger.error(
        "Watermark file not found. Raw value: %r. Checked: %s",
        raw,
        [str(p) for p in candidates],
    )
    return None


def _get_soffice_binary() -> str | None:
    env_value = os.getenv("LIBREOFFICE_BIN", "").strip()

    if env_value:
        return env_value

    for name in ("soffice", "libreoffice"):
        path = shutil.which(name)

        if path:
            return path

    logger.error("LibreOffice binary not found. Checked: soffice, libreoffice")
    return None


def _resolve_source_docx_path(generated_document) -> Path | None:
    source_field = getattr(generated_document, "generated_file", None)

    if not source_field:
        logger.error("Generated document %s has no generated_file", getattr(generated_document, "id", None))
        return None

    source_name = getattr(source_field, "name", "") or ""
    source_path_raw = getattr(source_field, "path", "") or ""
    source_path = Path(source_path_raw) if source_path_raw else None

    if not source_name.lower().endswith(".docx"):
        logger.error(
            "Generated document %s is not a .docx file: %s",
            getattr(generated_document, "id", None),
            source_name,
        )
        return None

    if not source_path or not source_path.exists():
        logger.error(
            "Generated document file path does not exist for document %s: %s",
            getattr(generated_document, "id", None),
            source_path_raw,
        )
        return None

    return source_path


def _convert_docx_to_pdf(source_docx_path: Path, workdir: Path) -> Path | None:
    soffice_bin = _get_soffice_binary()

    if not soffice_bin:
        return None

    input_docx_path = workdir / source_docx_path.name
    shutil.copy2(source_docx_path, input_docx_path)

    profile_dir = workdir / "lo-profile"
    profile_dir.mkdir(parents=True, exist_ok=True)

    command = [
        soffice_bin,
        "--headless",
        f"-env:UserInstallation={profile_dir.resolve().as_uri()}",
        "--convert-to",
        "pdf:writer_pdf_Export",
        "--outdir",
        str(workdir),
        str(input_docx_path),
    ]

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except Exception:
        logger.exception("LibreOffice conversion crashed for %s", source_docx_path)
        return None

    if completed.stdout:
        logger.info("LibreOffice stdout: %s", completed.stdout.strip())

    if completed.returncode != 0:
        logger.error(
            "LibreOffice failed for %s. Return code=%s stderr=%s",
            source_docx_path,
            completed.returncode,
            (completed.stderr or "").strip(),
        )
        return None

    output_pdf_path = workdir / f"{input_docx_path.stem}.pdf"

    if not output_pdf_path.exists():
        logger.error(
            "LibreOffice did not create PDF for %s. Expected path: %s",
            source_docx_path,
            output_pdf_path,
        )
        return None

    return output_pdf_path


def _get_image_ratio(watermark_path: Path) -> float:
    with Image.open(watermark_path) as image:
        img_w, img_h = image.size

    if not img_w or not img_h:
        raise ValueError("Invalid watermark image size")

    return img_h / img_w


def _get_default_width_pt() -> float:
    """
    Размер watermark по умолчанию — 40 мм, то есть примерно 4.0 см.

    Если на сервере задан DOCUMENT_WATERMARK_WIDTH_MM в .env/settings.py,
    он будет иметь приоритет. Поэтому если там стоит 31, нужно заменить на 40.
    """
    width_mm = float(
        getattr(
            settings,
            "DOCUMENT_WATERMARK_WIDTH_MM",
            os.getenv("DOCUMENT_WATERMARK_WIDTH_MM", DEFAULT_WATERMARK_WIDTH_MM),
        )
        or DEFAULT_WATERMARK_WIDTH_MM
    )
    return _mm_to_pt(width_mm)


def _find_executor_rect_on_last_page(page):
    """
    Ищем слово 'Исполнитель' именно на последней странице.
    Берём последнее найденное совпадение.
    """
    search_variants = [
        "Исполнитель",
        "исполнитель",
        "ИСПОЛНИТЕЛЬ",
    ]

    rects = []

    for variant in search_variants:
        try:
            rects.extend(page.search_for(variant))
        except Exception:
            logger.exception("search_for failed for variant %s", variant)

    if rects:
        rects = sorted(rects, key=lambda r: (round(r.y0, 2), round(r.x0, 2)))
        return rects[-1]

    try:
        words = page.get_text("words") or []
    except Exception:
        logger.exception("Failed to extract words from page")
        words = []

    matched_word_rects = []

    for item in words:
        if len(item) < 5:
            continue

        x0, y0, x1, y1, word = item[:5]
        normalized = str(word or "").strip(" \t\r\n:;,.()[]{}\"'").casefold()

        if normalized == EXECUTOR_WORD:
            matched_word_rects.append(pymupdf.Rect(x0, y0, x1, y1))

    if matched_word_rects:
        matched_word_rects = sorted(
            matched_word_rects,
            key=lambda r: (round(r.y0, 2), round(r.x0, 2)),
        )
        return matched_word_rects[-1]

    return None


def _build_rect_centered_on_word(page, word_rect, watermark_path: Path):
    """
    Ставим watermark точно поверх слова.
    Центр watermark = центр слова "Исполнитель".
    """
    image_ratio = _get_image_ratio(watermark_path)

    cover_scale = float(
        getattr(
            settings,
            "DOCUMENT_WATERMARK_EXECUTOR_SCALE",
            os.getenv("DOCUMENT_WATERMARK_EXECUTOR_SCALE", 1.8),
        )
        or 1.8
    )

    default_width_pt = _get_default_width_pt()
    target_width_pt = max(default_width_pt, word_rect.width * cover_scale)
    target_height_pt = target_width_pt * image_ratio

    center_x = (word_rect.x0 + word_rect.x1) / 2
    center_y = (word_rect.y0 + word_rect.y1) / 2

    x0 = center_x - (target_width_pt / 2)
    x1 = center_x + (target_width_pt / 2)
    y0 = center_y - (target_height_pt / 2)
    y1 = center_y + (target_height_pt / 2)

    page_rect = page.rect

    if x0 < 0:
        shift = -x0
        x0 += shift
        x1 += shift

    if x1 > page_rect.width:
        shift = x1 - page_rect.width
        x0 -= shift
        x1 -= shift

    if y0 < 0:
        shift = -y0
        y0 += shift
        y1 += shift

    if y1 > page_rect.height:
        shift = y1 - page_rect.height
        y0 -= shift
        y1 -= shift

    return pymupdf.Rect(x0, y0, x1, y1)


def _build_bottom_left_rect(page, watermark_path: Path):
    width_pt = _get_default_width_pt()
    image_ratio = _get_image_ratio(watermark_path)
    height_pt = width_pt * image_ratio

    bottom_mm = float(
        getattr(settings, "DOCUMENT_WATERMARK_BOTTOM_MM", os.getenv("DOCUMENT_WATERMARK_BOTTOM_MM", 8)) or 8
    )
    left_mm = float(
        getattr(settings, "DOCUMENT_WATERMARK_LEFT_MM", os.getenv("DOCUMENT_WATERMARK_LEFT_MM", 15)) or 15
    )

    bottom_pt = _mm_to_pt(bottom_mm)
    left_pt = _mm_to_pt(left_mm)

    page_rect = page.rect

    x0 = min(left_pt, max(0, page_rect.width - width_pt - _mm_to_pt(5)))
    x1 = x0 + width_pt
    y1 = page_rect.height - bottom_pt
    y0 = y1 - height_pt

    if y0 < 0:
        y0 = _mm_to_pt(5)
        y1 = y0 + height_pt

    return pymupdf.Rect(x0, y0, x1, y1)


def _apply_watermark_to_last_pdf_page(source_pdf_path: Path, watermark_path: Path, output_pdf_path: Path) -> bool:
    if pymupdf is None:
        logger.error("PyMuPDF is not installed")
        return False

    try:
        pdf = pymupdf.open(str(source_pdf_path))
    except Exception:
        logger.exception("Failed to open PDF for watermarking: %s", source_pdf_path)
        return False

    try:
        if len(pdf) == 0:
            logger.error("PDF has no pages: %s", source_pdf_path)
            return False

        last_page = pdf[-1]
        executor_rect = _find_executor_rect_on_last_page(last_page)

        if executor_rect is not None:
            rect = _build_rect_centered_on_word(last_page, executor_rect, watermark_path)
            logger.info(
                "Executor word found on last page in PDF %s. Watermark placed directly over the word.",
                source_pdf_path,
            )
        else:
            rect = _build_bottom_left_rect(last_page, watermark_path)
            logger.info(
                "Executor word NOT found on last page in PDF %s. Watermark placed bottom-left.",
                source_pdf_path,
            )

        last_page.insert_image(
            rect,
            filename=str(watermark_path),
            overlay=True,
            keep_proportion=True,
        )

        pdf.save(str(output_pdf_path), deflate=True, garbage=3)
        logger.info("Watermark applied to last PDF page: %s", output_pdf_path)
        return True

    except Exception:
        logger.exception(
            "Failed while applying watermark to the last page of PDF %s using %s",
            source_pdf_path,
            watermark_path,
        )
        return False
    finally:
        pdf.close()


def _build_approved_name(source_docx_path: Path, without_watermark: bool = False) -> str:
    prefix = "approved_no_watermark" if without_watermark else "approved"
    safe_stem = source_docx_path.stem or "document"
    return f"generated_documents/approved/{prefix}_{safe_stem}.pdf"


def build_approved_document(generated_document):
    source_docx_path = _resolve_source_docx_path(generated_document)

    if source_docx_path is None:
        return None

    with tempfile.TemporaryDirectory(prefix="approved_pdf_") as tmp_dir_raw:
        tmp_dir = Path(tmp_dir_raw)

        source_pdf_path = _convert_docx_to_pdf(source_docx_path, tmp_dir)

        if source_pdf_path is None:
            logger.error(
                "Failed to convert DOCX to PDF for document %s",
                getattr(generated_document, "id", None),
            )
            return None

        if _is_consent_document(generated_document, source_docx_path):
            approved_name = _build_approved_name(source_docx_path, without_watermark=True)
            logger.info(
                "Approved PDF for document %s created without watermark because template starts with СОГЛАСИЕ.",
                getattr(generated_document, "id", None),
            )
            return ContentFile(source_pdf_path.read_bytes(), name=approved_name)

        watermark_path = _get_watermark_path()

        if watermark_path is None:
            logger.error("Watermark path could not be resolved")
            return None

        approved_pdf_path = tmp_dir / f"approved_{source_docx_path.stem}.pdf"

        success = _apply_watermark_to_last_pdf_page(
            source_pdf_path=source_pdf_path,
            watermark_path=watermark_path,
            output_pdf_path=approved_pdf_path,
        )

        if not success or not approved_pdf_path.exists():
            logger.error(
                "Failed to build approved PDF with watermark for document %s",
                getattr(generated_document, "id", None),
            )
            return None

        approved_name = _build_approved_name(source_docx_path, without_watermark=False)
        return ContentFile(approved_pdf_path.read_bytes(), name=approved_name)