import io

from django.core.files.base import ContentFile
from django.test import SimpleTestCase

from .models import extract_docx_lines


class DocumentEncodingSmokeTests(SimpleTestCase):
    def test_docx_text_extraction_preserves_cyrillic_and_turkmen_text(self):
        try:
            from docx import Document as DocxDocument
        except Exception as exc:
            self.skipTest(f'python-docx is unavailable in this environment: {exc}')

        text = 'Здравствуйте, Сабира, Aşgabat, Türkmen, Университет'
        try:
            document = DocxDocument()
            document.add_paragraph(text)
            buffer = io.BytesIO()
            document.save(buffer)
        except Exception as exc:
            self.skipTest(f'DOCX smoke generation is unavailable in this environment: {exc}')

        file_obj = ContentFile(buffer.getvalue(), name='encoding-smoke.docx')
        extracted = '\n'.join(extract_docx_lines(file_obj))

        self.assertIn('Здравствуйте', extracted)
        self.assertIn('Aşgabat', extracted)
        self.assertIn('Türkmen', extracted)
        self.assertIn('Университет', extracted)
        self.assertNotIn('????', extracted)
