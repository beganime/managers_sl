from django.test import TestCase

from apps.employees.models import EmployeeAccess, EmployeeProfile, EmployeeRole
from apps.organizations.models import Company, Office
from users.models import User

from .services import get_admin_users


class AdminRecipientTests(TestCase):
    def test_document_managers_and_staff_can_be_combined_without_query_error(self):
        company = Company.objects.create(name='Students Life')
        office = Office.objects.create(company=company, name='Main', city='Ashgabat')
        role = EmployeeRole.objects.create(
            code='document-manager',
            name='Document manager',
            role_type='manager',
        )
        staff = User.objects.create_user(
            email='staff-notifications@example.com',
            password='test-password',
            is_staff=True,
        )
        manager = User.objects.create_user(
            email='document-manager@example.com',
            password='test-password',
        )
        profile = EmployeeProfile.objects.create(
            user=manager,
            company=company,
            office=office,
            role=role,
        )
        EmployeeAccess.objects.create(
            employee=profile,
            can_manage_documents=True,
        )

        recipients = list(get_admin_users(company=company, office=office))

        self.assertCountEqual(recipients, [staff, manager])
