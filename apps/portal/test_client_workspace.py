import io
import base64
from unittest.mock import patch
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import Http404
from django.core.exceptions import PermissionDenied
from django.test import override_settings
from .test_client_insights import ClientInsightsTests
from .client_workspace import ClientWorkspaceView, ClientAvatarView
from .models import ClientWorkspaceProfile


@override_settings(EXTERNAL_ACCOUNT_ENCRYPTION_KEY=base64.urlsafe_b64encode(b'x' * 32).decode())
class ClientWorkspaceTests(ClientInsightsTests):
    def test_avatar_upload_and_scope(self):
        stream = io.BytesIO()
        Image.new('RGB', (400, 300), 'red').save(stream, 'PNG')
        req = self.request({'action': 'avatar', 'avatar': SimpleUploadedFile('photo.png', stream.getvalue(), 'image/png')})
        self.assertEqual(ClientWorkspaceView.as_view()(req, pk=self.student.pk).status_code, 302)
        response = ClientAvatarView.as_view()(self.request(), pk=self.student.pk)
        self.assertEqual(response['Content-Type'], 'image/jpeg')
        self.assertEqual(Image.open(io.BytesIO(response.content)).size, (256, 256))
        with self.assertRaises(Http404):
            ClientAvatarView.as_view()(self.request(user=self.other), pk=self.student.pk)

    def test_reject_fake_photo(self):
        req = self.request({'action': 'avatar', 'avatar': SimpleUploadedFile('fake.png', b'<script/>', 'image/png')})
        ClientWorkspaceView.as_view()(req, pk=self.student.pk)
        self.assertFalse(ClientWorkspaceProfile.objects.get(client=self.student).avatar)

    @patch('apps.portal.client_workspace.post_service')
    def test_create_stores_encrypted_password_and_prevents_double_send(self, remote):
        self.student.sl_id = 'SL-TEST-001'
        self.student.save()
        remote.return_value = {'status': 'created', 'sl_id': self.student.sl_id, 'user_id': 123}
        for _ in range(2):
            ClientWorkspaceView.as_view()(self.request({'action': 'account'}), pk=self.student.pk)
        self.assertEqual(remote.call_count, 1)
        self.assertTrue(remote.call_args.args[2]['create_only'])
        self.assertEqual(remote.call_args.args[2]['password'], 'Synthetic_0710')
        record = ClientWorkspaceProfile.objects.get(client=self.student)
        self.assertTrue(record.password_encrypted.startswith('aesgcm:v1:'))
        self.student.refresh_from_db()
        self.assertNotIn('mobile_password', self.student.custom_data)

    def test_no_credentials_for_nonowner(self):
        with patch('apps.portal.views.client_queryset', return_value=type(self.student).objects.all()):
            with self.assertRaises(PermissionDenied):
                ClientWorkspaceView.as_view()(self.request({'action': 'reveal'}, self.other), pk=self.student.pk)

    def test_workspace_renders_empty(self):
        response = ClientWorkspaceView.as_view()(self.request(), pk=self.student.pk)
        self.assertEqual(response.status_code, 200)
