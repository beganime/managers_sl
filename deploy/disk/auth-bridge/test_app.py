import io
import os
import tempfile
import unittest
from unittest import mock

from botocore.exceptions import ClientError


os.environ.setdefault('MANAGER_AUTH_URL', 'https://manager.invalid/auth')
os.environ.setdefault('MANAGER_AUTH_TOKEN', 'test')
os.environ.setdefault('S3_ENDPOINT', 'https://s3.invalid')
os.environ.setdefault('S3_REGION', 'ru-1')
os.environ.setdefault('S3_BUCKET', 'test-bucket')
os.environ.setdefault('S3_ACCESS_KEY', 'test')
os.environ.setdefault('S3_SECRET_KEY', 'test')
os.environ.setdefault('DISK_PROVISION_TOKEN', 'test')
os.environ.setdefault('DISK_ACTIVITY_HOOK_TOKEN', 'test')
os.environ.setdefault('ACTIVITY_DB_PATH', os.path.join(tempfile.gettempdir(), 'disksl-test-activity.sqlite3'))

import app  # noqa: E402


class UploadHelpersTests(unittest.TestCase):
    @mock.patch.object(app, 'S3_CLIENT')
    def test_weekly_report_upload_uses_private_archive_prefix(self, storage):
        handler = object.__new__(app.Handler)
        handler.headers = {
            'X-File-Name': 'weekly-report.docx',
            'X-Employee-Name': 'Иван Иванов',
            'X-Report-Period': '2026-09-28_2026-10-03',
            'X-Report-ID': '42',
            'Content-Type': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        }
        handler.rfile = io.BytesIO(b'PK\x03\x04test')
        handler.valid_provision_token = lambda: True
        handler.respond = lambda status, payload: (status, payload)

        status, payload = handler.handle_staff_report_upload(8)

        self.assertEqual(status, 201)
        self.assertEqual(payload['path'], '/Служебные отчёты/2026/10/42 — Иван Иванов — 2026-09-28_2026-10-03.docx')
        self.assertEqual(storage.upload_fileobj.call_args.args[1], 'test-bucket')

    @mock.patch.object(app, 'S3_CLIENT')
    def test_storage_usage_paginates_and_calculates_free_space(self, storage):
        storage.list_objects_v2.side_effect = [
            {
                'Contents': [{'Size': 100}, {'Size': 250}],
                'IsTruncated': True,
                'NextContinuationToken': 'next',
            },
            {'Contents': [{'Size': 650}], 'IsTruncated': False},
        ]

        result = app.storage_usage()

        self.assertEqual(result['used_bytes'], 1000)
        self.assertEqual(result['free_bytes'], app.S3_QUOTA_BYTES - 1000)
        self.assertEqual(result['objects'], 3)
        self.assertEqual(storage.list_objects_v2.call_count, 2)

    def test_accepts_supported_file_name(self):
        self.assertEqual(app.safe_upload_name('passport.pdf'), 'passport.pdf')
        self.assertEqual(app.safe_upload_name('scan/photo.JPG'), 'scan_photo.JPG')

    def test_rejects_unsupported_file_name(self):
        with self.assertRaises(ValueError):
            app.safe_upload_name('payload.exe')

    @mock.patch.object(app, 'S3_CLIENT')
    def test_upload_uses_unique_key_and_content_type(self, storage):
        storage.head_object.side_effect = ClientError(
            {'Error': {'Code': '404', 'Message': 'Not found'}},
            'HeadObject',
        )
        content = io.BytesIO(b'%PDF-1.4')

        key = app.upload_client_file(
            '2027/Контракт/Иван Иванов (SL-2027-001)/оригиналы',
            'passport.pdf',
            content,
            'application/pdf',
        )

        self.assertTrue(key.endswith('/оригиналы/passport.pdf'))
        storage.upload_fileobj.assert_called_once_with(
            content,
            'test-bucket',
            key,
            ExtraArgs={'ContentType': 'application/pdf'},
        )


if __name__ == '__main__':
    unittest.main()
