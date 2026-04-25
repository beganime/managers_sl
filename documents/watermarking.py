import logging
import os
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


EXECUTOR_TRIGGER_WORD = "исполнитель"


def _mm_to_pt(value_mm: float) -> float:
    return float(value_mm) * 72.0 / 25.4


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
        logger.error(
            "Generated document %s has no generated_file",
            getattr(generated_document, "id", None),
        )
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


def _get_watermark_image_size(watermark_path: Path) -> tuple[int, int]:
    with Image.open(watermark_path) as image:
        img_w, img_h = image.size

    if not img_w or not img_h:
        raise ValueError("Invalid watermark image size")

    return img_w, img_h


def _get_watermark_width_pt() -> float:
    width_mm = float(
        getattr(
            settings,
            "DOCUMENT_WATERMARK_WIDTH_MM",
            os.getenv("DOCUMENT_WATERMARK_WIDTH_MM", 35),
        )
        or 35
    )
    return _mm_to_pt(width_mm)


def _get_watermark_rect_center(page, watermark_path: Path):
    width_pt = _get_watermark_width_pt()
    img_w, img_h = _get_watermark_image_size(watermark_path)
    height_pt = width_pt * (img_h / img_w)

    page_rect = page.rect

    x0 = (page_rect.width - width_pt) / 2
    y0 = (page_rect.height - height_pt) / 2
    x1 = x0 + width_pt
    y1 = y0 + height_pt

    return pymupdf.Rect(x0, y0, x1, y1)


def _get_watermark_rect_bottom_left(page, watermark_path: Path):
    width_pt = _get_watermark_width_pt()

    bottom_mm = float(
        getattr(
            settings,
            "DOCUMENT_WATERMARK_BOTTOM_MM",
            os.getenv("DOCUMENT_WATERMARK_BOTTOM_MM", 8),
        )
        or 8
    )
    left_mm = float(
        getattr(
            settings,
            "DOCUMENT_WATERMARK_LEFT_MM",
            os.getenv("DOCUMENT_WATERMARK_LEFT_MM", 15),
        )
        or 15
    )

    bottom_pt = _mm_to_pt(bottom_mm)
    left_pt = _mm_to_pt(left_mm)

    img_w, img_h = _get_watermark_image_size(watermark_path)
    height_pt = width_pt * (img_h / img_w)

    page_rect = page.rect

    x0 = min(left_pt, max(0, page_rect.width - width_pt - _mm_to_pt(5)))
    x1 = x0 + width_pt

    y1 = page_rect.height - bottom_pt
    y0 = y1 - height_pt

    if y0 < 0:
        y0 = _mm_to_pt(5)
        y1 = y0 + height_pt

    return pymupdf.Rect(x0, y0, x1, y1)


def _page_has_executor_word(page) -> bool:
    try:
        text = page.get_text("text") or ""
    except Exception:
        logger.exception("Failed to extract text from PDF page")
        return False

    normalized = " ".join(text.split()).casefold()
    return EXECUTOR_TRIGGER_WORD in normalized


def _find_executor_page_index(pdf) -> int | None:
    for index in range(len(pdf)):
        page = pdf[index]

        if _page_has_executor_word(page):
            return index

    return None


def _apply_watermark_to_pdf(source_pdf_path: Path, watermark_path: Path, output_pdf_path: Path) -> bool:
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

        executor_page_index = _find_executor_page_index(pdf)

        if executor_page_index is not None:
            target_page = pdf[executor_page_index]
            rect = _get_watermark_rect_center(target_page, watermark_path)
            logger.info(
                "Executor word found in PDF %s on page %s. Watermark will be placed in center.",
                source_pdf_path,
                executor_page_index + 1,
            )
        else:
            target_page = pdf[-1]
            rect = _get_watermark_rect_bottom_left(target_page, watermark_path)
            logger.info(
                "Executor word not found in PDF %s. Watermark will be placed bottom-left on last page.",
                source_pdf_path,
            )

        target_page.insert_image(
            rect,
            filename=str(watermark_path),
            overlay=True,
            keep_proportion=True,
        )

        pdf.save(str(output_pdf_path), deflate=True, garbage=3)
        logger.info("Watermark applied to PDF: %s", output_pdf_path)
        return True

    except Exception:
        logger.exception(
            "Failed while applying watermark to PDF %s using %s",
            source_pdf_path,
            watermark_path,
        )
        return False
    finally:
        pdf.close()


def build_approved_document(generated_document):
    source_docx_path = _resolve_source_docx_path(generated_document)

    if source_docx_path is None:
        return None

    watermark_path = _get_watermark_path()

    if watermark_path is None:
        logger.error("Watermark path could not be resolved")
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

        approved_pdf_path = tmp_dir / f"approved_{source_docx_path.stem}.pdf"

        success = _apply_watermark_to_pdf(
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

        approved_name = f"generated_documents/approved/approved_{source_docx_path.stem}.pdf"
        return ContentFile(approved_pdf_path.read_bytes(), name=approved_name)