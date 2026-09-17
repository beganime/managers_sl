from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.organizations.models import Company

from .models import ActivityLog, Application, ApplicationStageHistory, Client
from .workflow import WorkflowTransitionError, record_application_created, transition_application


class AdmissionWorkflowTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Workflow test')
        self.manager = get_user_model().objects.create_user(
            email='workflow-manager@example.invalid', password='test-only-password', is_staff=True,
        )
        self.student = Client.objects.create(
            company=self.company, manager=self.manager, full_name='Workflow Student', phone='', sl_id='SL-001',
        )
        self.application = Application.objects.create(
            client=self.student, company=self.company, manager=self.manager,
            university_name='TEST', program_name='Program',
        )

    def test_created_event_is_idempotent(self):
        event_id = uuid4()
        first, changed = record_application_created(self.application, actor=self.manager, event_id=event_id)
        second, repeated = record_application_created(self.application, actor=self.manager, event_id=event_id)
        self.assertTrue(changed)
        self.assertFalse(repeated)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(ApplicationStageHistory.objects.count(), 1)
        self.assertEqual(ActivityLog.objects.count(), 1)

    def test_forward_transition_records_old_and_new_stage_once(self):
        event_id = uuid4()
        application, history, changed = transition_application(
            self.application, Application.STAGE_APPLICATION_PREPARATION,
            actor=self.manager, event_id=event_id,
        )
        self.assertTrue(changed)
        self.assertEqual(application.current_stage, Application.STAGE_APPLICATION_PREPARATION)
        self.assertEqual(history.old_stage, Application.STAGE_DOCUMENT_COLLECTION)
        self.assertEqual(history.new_stage, Application.STAGE_APPLICATION_PREPARATION)
        repeated_application, repeated_history, repeated = transition_application(
            self.application, Application.STAGE_APPLICATION_PREPARATION,
            actor=self.manager, event_id=event_id,
        )
        self.assertFalse(repeated)
        self.assertEqual(repeated_application.pk, application.pk)
        self.assertEqual(repeated_history.pk, history.pk)

    def test_backward_transition_is_rejected(self):
        transition_application(self.application, Application.STAGE_APPLICATION_SUBMITTED, actor=self.manager)
        with self.assertRaises(WorkflowTransitionError):
            transition_application(self.application, Application.STAGE_DOCUMENTS_READY, actor=self.manager)

    def test_pause_requires_comment_and_can_resume(self):
        with self.assertRaises(WorkflowTransitionError):
            transition_application(self.application, Application.STAGE_ON_HOLD, actor=self.manager)
        transition_application(
            self.application, Application.STAGE_ON_HOLD, actor=self.manager, comment='Ждём решение семьи.',
        )
        application, _history, changed = transition_application(
            self.application, Application.STAGE_APPLICATION_PREPARATION,
            actor=self.manager, comment='Клиент продолжает поступление.',
        )
        self.assertTrue(changed)
        self.assertEqual(application.current_stage, Application.STAGE_APPLICATION_PREPARATION)

    def test_audit_rows_cannot_be_changed_or_deleted_through_model(self):
        history, _changed = record_application_created(self.application, actor=self.manager)
        history.comment = 'rewrite'
        with self.assertRaises(DjangoValidationError):
            history.save()
        with self.assertRaises(DjangoValidationError):
            history.delete()
        activity = ActivityLog.objects.get()
        activity.action = 'REWRITE'
        with self.assertRaises(DjangoValidationError):
            activity.save()
        with self.assertRaises(DjangoValidationError):
            activity.delete()

    def test_transition_api_uses_scoped_application(self):
        api = APIClient()
        api.force_authenticate(self.manager)
        response = api.post(
            reverse('crm-application-transition', args=[self.application.pk]),
            {'stage': Application.STAGE_DOCUMENTS_READY, 'event_id': str(uuid4())},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['changed'])
        self.assertEqual(response.data['application']['current_stage'], Application.STAGE_DOCUMENTS_READY)
