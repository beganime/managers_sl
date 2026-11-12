import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings

from apps.organizations.models import Company

from .lead_bridge import claim_lead, process_lead, send_weekly_lead_report
from .models import Lead


@override_settings(ELITE_TASK_SERVICE_TOKEN='service-secret')
class LeadBridgeActionTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Students Life')
        self.manager = get_user_model().objects.create_user(
            email='manager@example.com', password='secret123'
        )
        self.other = get_user_model().objects.create_user(
            email='other@example.com', password='secret123'
        )
        self.lead = Lead.objects.create(
            company=self.company,
            full_name='Клиент',
            phone='+99360000000',
            api_source='website',
        )
        self.headers = {'HTTP_AUTHORIZATION': 'Bearer service-secret'}
        self.factory = RequestFactory()

    def payload(self, email, role='manager'):
        return json.dumps({'email': email, 'full_name': email, 'role': role})

    def test_first_manager_claims_and_repeat_is_idempotent(self):
        def request(email):
            return self.factory.post(
                '/', data=self.payload(email), content_type='application/json', **self.headers
            )

        first = claim_lead(request(self.manager.email), self.lead.pk)
        repeat = claim_lead(request(self.manager.email), self.lead.pk)
        conflict = claim_lead(request(self.other.email), self.lead.pk)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(repeat.status_code, 200)
        self.assertEqual(conflict.status_code, 409)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.manager, self.manager)
        self.assertEqual(self.lead.status, 'new')

    def test_assignee_can_mark_processed(self):
        self.lead.manager = self.manager
        self.lead.save(update_fields=['manager'])
        request = self.factory.post(
            '/',
            data=self.payload(self.manager.email),
            content_type='application/json',
            **self.headers,
        )
        response = process_lead(request, self.lead.pk)
        self.assertEqual(response.status_code, 200)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.status, 'contacted')
        self.assertEqual(self.lead.processed_by, self.manager)
        self.assertIsNotNone(self.lead.processed_at)


@override_settings(
    ELITE_TASK_API_URL='https://task.manager-sl.ru',
    ELITE_TASK_INTEGRATION_KEY='integration-key',
)
class LeadWeeklyReportTests(TestCase):
    @patch('apps.crm.lead_bridge._elite_task_post')
    def test_weekly_report_is_sent(self, post):
        post.return_value = {'sent': True}
        send_weekly_lead_report()
        path, payload = post.call_args.args
        self.assertEqual(path, '/integrations/v1/crm/reports')
        self.assertEqual(payload['total'], 0)
        self.assertEqual(payload['processed'], 0)
