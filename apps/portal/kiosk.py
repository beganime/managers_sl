"""Страница печати QR-бейджей киоска (только для attendance-администратора)."""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.shortcuts import redirect
from django.views.generic import TemplateView

from apps.attendance.kiosk import build_badge_code, badge_qr_svg, issue_badge, regenerate_badge
from apps.attendance.services import attendance_profile_q
from apps.employees.models import EmployeeProfile

from .engagement import AdminOnlyMixin


class KioskBadgesView(AdminOnlyMixin, TemplateView):
    template_name = 'portal/kiosk_badges.html'
    page_title = 'Бейджи киоска'
    active_page = 'kiosk_badges'

    def get_tracked_people(self):
        return (
            EmployeeProfile.objects
            .filter(attendance_profile_q())
            .select_related('user', 'office')
            .order_by('user__last_name', 'user__first_name', 'user__email')
        )

    def post(self, request, *args, **kwargs):
        try:
            user_id = int(request.POST.get('user_id') or 0)
        except ValueError:
            user_id = 0
        user = get_user_model().objects.filter(pk=user_id).first()
        tracked_ids = {person.user_id for person in self.get_tracked_people()}
        if user is None or user.pk not in tracked_ids:
            messages.error(request, 'Сотрудник не найден или не входит в учёт посещаемости.')
        else:
            regenerate_badge(user)
            messages.success(request, f'Бейдж для {user.get_full_name() or user.email} перевыпущен. Старый код больше не действует — перепечатайте бейдж.')
        return redirect('portal:kiosk_badges')

    def get_context_data(self, **kwargs):
        cards = []
        for person in self.get_tracked_people():
            badge = issue_badge(person.user)
            code = build_badge_code(badge)
            cards.append({
                'person': person,
                'code': code,
                'qr_svg': badge_qr_svg(code),
                'issued_at': badge.issued_at,
            })
        return super().get_context_data(cards=cards, **kwargs)


class KioskQrGeneratorView(AdminOnlyMixin, TemplateView):
    """Одиночная генерация QR-бейджа: выбор сотрудника → крупный код для печати."""

    template_name = 'portal/kiosk_qr.html'
    page_title = 'Генератор QR'
    active_page = 'kiosk_qr'

    def get_tracked_people(self):
        return (
            EmployeeProfile.objects
            .filter(attendance_profile_q())
            .select_related('user', 'office')
            .order_by('user__last_name', 'user__first_name', 'user__email')
        )

    def get_selected(self, people):
        raw = self.request.GET.get('user_id', '').strip()
        if not raw:
            return None
        try:
            user_id = int(raw)
        except ValueError:
            return None
        for person in people:
            if person.user_id == user_id:
                return person
        return None

    def get_context_data(self, **kwargs):
        people = self.get_tracked_people()
        selected = self.get_selected(people)
        result = None
        if selected is not None:
            badge = issue_badge(selected.user)
            code = build_badge_code(badge)
            result = {
                'person': selected,
                'code': code,
                'qr_svg': badge_qr_svg(code),
                'issued_at': badge.issued_at,
            }
        return super().get_context_data(people=people, result=result, **kwargs)
