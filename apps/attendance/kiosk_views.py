"""Публичные страницы киоска-планшета: PWA-сканер, манифест, service worker.

Страница /kiosk/ не требует входа пользователя: планшет аутентифицируется
токеном устройства, который хранится только на планшете и отправляется
заголовком X-Kiosk-Token на API киоска.
"""

import json

from django.http import HttpResponse, JsonResponse
from django.views import View
from django.views.generic import TemplateView


class KioskScannerView(TemplateView):
    template_name = 'kiosk/scanner.html'


class KioskManifestView(View):
    def get(self, request):
        payload = {
            'name': 'SL Киоск',
            'short_name': 'Киоск',
            'description': 'Планшет-сканер для отметки рабочего дня',
            'start_url': '/kiosk/',
            'scope': '/kiosk/',
            'display': 'fullscreen',
            'orientation': 'portrait',
            'background_color': '#0f172a',
            'theme_color': '#0f172a',
            'icons': [],
        }
        return JsonResponse(payload, content_type='application/manifest+json')


class KioskServiceWorkerView(View):
    def get(self, request):
        script = """
const CACHE = 'sl-kiosk-v1';
const APP_SHELL = ['/kiosk/', '/static/kiosk/jsQR.js'];
self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(APP_SHELL)));
  self.skipWaiting();
});
self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  if (url.pathname.startsWith('/api/')) return; // API — только сеть
  event.respondWith(
    fetch(event.request).then((response) => {
      const copy = response.clone();
      caches.open(CACHE).then((cache) => cache.put(event.request, copy));
      return response;
    }).catch(() => caches.match(event.request).then((cached) => cached || caches.match('/kiosk/')))
  );
});
""".strip()
        return HttpResponse(script, content_type='application/javascript')
