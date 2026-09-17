from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.organizations.models import Company

from .document_versions import DocumentVersionError, record_document_review, record_document_version
from .models import ActivityLog, Application, Client, ClientFile, ClientFileReviewEvent, ClientFileVersion


class ClientDocumentVersionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email='document-manager@example.com', password='test-password',
        )
        self.company = Company.objects.create(name='Students Life')
        self.student = Client.objects.create(
            company=self.company, manager=self.user, full_name='Иван Иванов', phone='+000000001',
        )
        self.application = Application.objects.create(
            client=self.student, company=self.company, manager=self.user,
            university_name='КФУ', program_name='Лечебное дело',
        )
        self.document = ClientFile.objects.create(
            client=self.student, application=self.application, uploaded_by=self.user,
            title='Паспорт', file='', source='students_life_mobile_app',
            external_mobile_document_id=71,
        )

    def upload(self, number, *, event_id=None):
        return record_document_version(
            self.document,
            original_name='passport.pdf',
            storage_path=f'2027/SL-001/originals/passport__v{number}.pdf',
            folder_url='https://disk.test/folder',
            mime_type='application/pdf',
            size_bytes=120 + number,
            sha256=str(number) * 64,
            uploaded_by=self.user,
            source_service='test',
            event_id=event_id,
        )

    def test_reupload_keeps_versions_and_each_review(self):
        version_one, created = self.upload(1)
        self.assertTrue(created)
        review, created = record_document_review(
            self.document,
            status=ClientFile.STATUS_REJECTED,
            comment='Нужен полный разворот.',
            reviewer=self.user,
            source_service='test',
        )
        self.assertTrue(created)
        self.assertEqual(review.version, version_one)

        version_two, _ = self.upload(2)
        self.document.refresh_from_db()
        self.assertEqual(version_two.version_number, 2)
        self.assertEqual(self.document.current_version_number, 2)
        self.assertEqual(self.document.status, ClientFile.STATUS_PENDING)
        self.assertEqual(list(
            self.document.versions.order_by('version_number').values_list('storage_path', flat=True)
        ), [
            '2027/SL-001/originals/passport__v1.pdf',
            '2027/SL-001/originals/passport__v2.pdf',
        ])
        self.assertEqual(version_one.review_events.get().comment, 'Нужен полный разворот.')
        self.assertEqual(ActivityLog.objects.filter(action='DOCUMENT_VERSION_UPLOADED').count(), 2)
        self.assertEqual(ActivityLog.objects.filter(action='DOCUMENT_VERSION_REVIEWED').count(), 1)

    def test_upload_and_review_event_ids_are_idempotent(self):
        upload_id = uuid4()
        version, created = self.upload(1, event_id=upload_id)
        repeated, created_again = self.upload(1, event_id=upload_id)
        self.assertFalse(created_again)
        self.assertEqual(repeated, version)
        self.assertEqual(ClientFileVersion.objects.count(), 1)

        review_id = uuid4()
        first, created = record_document_review(
            self.document, status=ClientFile.STATUS_APPROVED,
            reviewer=self.user, source_service='test', event_id=review_id,
        )
        repeated, created_again = record_document_review(
            self.document, status=ClientFile.STATUS_APPROVED,
            reviewer=self.user, source_service='test', event_id=review_id,
        )
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(repeated, first)
        self.assertEqual(ClientFileReviewEvent.objects.count(), 1)

    def test_application_from_another_student_is_rejected(self):
        other = Client.objects.create(
            company=self.company, manager=self.user, full_name='Другой', phone='+000000002',
        )
        other_application = Application.objects.create(
            client=other, company=self.company, manager=self.user,
            university_name='РУДН', program_name='Стоматология',
        )
        with self.assertRaises(DocumentVersionError):
            record_document_version(
                self.document,
                application=other_application,
                original_name='passport.pdf',
                storage_path='test/passport.pdf',
            )

    def test_versions_and_reviews_are_immutable(self):
        version, _ = self.upload(1)
        review, _ = record_document_review(
            self.document, status=ClientFile.STATUS_APPROVED, reviewer=self.user,
        )
        version.original_name = 'changed.pdf'
        with self.assertRaises(Exception):
            version.save()
        review.comment = 'changed'
        with self.assertRaises(Exception):
            review.save()
