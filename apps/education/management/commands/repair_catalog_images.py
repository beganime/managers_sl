import io
import json
import re
import time
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.education.models import City, Country, University


WIKIPEDIA_API = 'https://ru.wikipedia.org/w/api.php'
FLAG_URL = 'https://flagcdn.com/w640/{code}.png'
USER_AGENT = 'SL-System-Catalog/1.0 (admin@manager-sl.ru)'
REQUEST_TIMEOUT = (5, 25)
MAX_DOWNLOAD_BYTES = 12 * 1024 * 1024


def normalized_words(value):
    return set(re.findall(r'[\w]+', str(value or '').lower(), flags=re.UNICODE))


def page_score(query, title):
    query_words = normalized_words(query)
    title_words = normalized_words(title)
    if not query_words or not title_words:
        return 0
    return len(query_words & title_words) / len(title_words)


def wikipedia_image(session, query):
    response = session.get(
        WIKIPEDIA_API,
        params={
            'action': 'query',
            'generator': 'search',
            'gsrsearch': query,
            'gsrlimit': 5,
            'prop': 'pageimages|info',
            'piprop': 'thumbnail|name',
            'pithumbsize': 1280,
            'inprop': 'url',
            'format': 'json',
        },
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    pages = response.json().get('query', {}).get('pages', {}).values()
    candidates = [page for page in pages if page.get('thumbnail', {}).get('source')]
    if not candidates:
        return None
    page = max(candidates, key=lambda item: page_score(query, item.get('title')))
    return {
        'url': page['thumbnail']['source'],
        'source': page.get('fullurl', ''),
        'title': page.get('title', ''),
    }


def download_image(session, url):
    response = session.get(url, timeout=REQUEST_TIMEOUT, stream=True)
    response.raise_for_status()
    content_length = int(response.headers.get('Content-Length') or 0)
    if content_length > MAX_DOWNLOAD_BYTES:
        raise ValueError('Remote image is too large')
    chunks = []
    size = 0
    for chunk in response.iter_content(64 * 1024):
        size += len(chunk)
        if size > MAX_DOWNLOAD_BYTES:
            raise ValueError('Remote image is too large')
        chunks.append(chunk)
    return b''.join(chunks)


def load_font(size, bold=False):
    candidates = [
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf' if bold else '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf' if bold else '/usr/share/fonts/dejavu/DejaVuSans.ttf',
    ]
    for filename in candidates:
        if Path(filename).exists():
            return ImageFont.truetype(filename, size=size)
    return ImageFont.load_default()


def wrap_text(draw, text, font, max_width):
    words = str(text or '').split()
    lines = []
    current = ''
    for word in words:
        candidate = f'{current} {word}'.strip()
        if current and draw.textbbox((0, 0), candidate, font=font)[2] > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines[:3]


def placeholder_image(title, subtitle='', size=(1280, 720)):
    image = Image.new('RGB', size, '#F7F7F7')
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 28, size[1]), fill='#B40000')
    draw.rectangle((28, 0, 44, size[1]), fill='#07497F')
    title_font = load_font(56, bold=True)
    subtitle_font = load_font(30)
    y = 210
    for line in wrap_text(draw, title, title_font, size[0] - 170):
        draw.text((100, y), line, font=title_font, fill='#111111')
        y += 72
    if subtitle:
        draw.text((102, min(y + 18, size[1] - 90)), subtitle, font=subtitle_font, fill='#555555')
    return image


def prepared_jpeg(raw, title, subtitle='', size=(1280, 720)):
    try:
        image = Image.open(io.BytesIO(raw))
        image = ImageOps.exif_transpose(image).convert('RGB')
        image = ImageOps.fit(image, size, method=Image.Resampling.LANCZOS)
    except Exception:
        image = placeholder_image(title, subtitle, size)
    output = io.BytesIO()
    image.save(output, format='JPEG', quality=86, optimize=True, progressive=True)
    return output.getvalue()


class Command(BaseCommand):
    help = 'Restore missing catalog media from Wikipedia/FlagCDN with a local branded fallback.'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true', help='Replace files that already exist in storage.')
        parser.add_argument('--delay', type=float, default=0.08, help='Pause between public API requests.')

    def handle(self, *args, **options):
        force = options['force']
        delay = max(options['delay'], 0)
        session = requests.Session()
        session.headers['User-Agent'] = USER_AGENT
        manifest = []
        counters = {'downloaded': 0, 'fallback': 0, 'reused': 0, 'failed': 0}

        def exists(field):
            return bool(field and field.name and default_storage.exists(field.name))

        def save_image(obj, field_name, title, query, subtitle='', direct_url='', allow_remote=True, size=(1280, 720)):
            field = getattr(obj, field_name)
            if exists(field) and not force:
                counters['reused'] += 1
                manifest.append({
                    'model': obj.__class__.__name__,
                    'id': obj.pk,
                    'name': title,
                    'field': field_name,
                    'path': field.name,
                    'source': 'existing_media',
                    'source_title': '',
                    'fallback': False,
                })
                return field.name

            source = {'url': direct_url, 'source': direct_url, 'title': title} if direct_url else None
            try:
                if not source and allow_remote and query:
                    source = wikipedia_image(session, query)
                if source:
                    raw = download_image(session, source['url'])
                    counters['downloaded'] += 1
                else:
                    raw = b''
                    counters['fallback'] += 1
            except (requests.RequestException, ValueError) as exc:
                self.stderr.write(f'{obj.__class__.__name__} {obj.pk}: {exc}')
                raw = b''
                source = None
                counters['fallback'] += 1

            payload = prepared_jpeg(raw, title, subtitle, size=size)
            filename = f'{obj.__class__.__name__.lower()}-{obj.pk}-{field_name}.jpg'
            if field and field.name and default_storage.exists(field.name):
                default_storage.delete(field.name)
            field.save(filename, ContentFile(payload), save=False)
            obj.save(update_fields=[field_name, 'updated_at'])
            manifest.append({
                'model': obj.__class__.__name__,
                'id': obj.pk,
                'name': title,
                'field': field_name,
                'path': field.name,
                'source': source.get('source', '') if source else '',
                'source_title': source.get('title', '') if source else '',
                'fallback': not bool(source),
            })
            if delay:
                time.sleep(delay)
            return field.name

        with transaction.atomic():
            for country in Country.objects.order_by('pk'):
                code = country.code.strip().lower()
                flag_url = FLAG_URL.format(code=code) if re.fullmatch(r'[a-z]{2}', code) else ''
                save_image(country, 'flag', country.name, f'Флаг {country.name}', 'Флаг страны', flag_url)
                image_name = save_image(country, 'image', country.name, f'intitle:"{country.name}" страна', 'Страна обучения')
                if not exists(country.cover_image) or force:
                    country.cover_image = image_name
                    country.save(update_fields=['cover_image', 'updated_at'])

            for city in City.objects.select_related('country').order_by('pk'):
                image_name = save_image(
                    city,
                    'image',
                    city.name,
                    f'intitle:"{city.name}" {city.country.name} город',
                    city.country.name,
                )
                if not exists(city.cover_image) or force:
                    city.cover_image = image_name
                    city.save(update_fields=['cover_image', 'updated_at'])

            for university in University.objects.select_related('country', 'city').order_by('pk'):
                city_name = university.city.name if university.city else university.country.name
                source_image = None
                if university.city and exists(university.city.image):
                    source_image = university.city.image
                elif exists(university.country.image):
                    source_image = university.country.image

                if source_image:
                    old_name = university.cover_image.name if university.cover_image else ''
                    if old_name.startswith('erp/education/university_covers/university-') and default_storage.exists(old_name):
                        default_storage.delete(old_name)
                    university.cover_image = source_image.name
                    university.save(update_fields=['cover_image', 'updated_at'])
                    manifest.append({
                        'model': 'University',
                        'id': university.pk,
                        'name': university.name,
                        'field': 'cover_image',
                        'path': university.cover_image.name,
                        'source': 'city_catalog_image',
                        'source_title': city_name,
                        'fallback': False,
                    })
                else:
                    save_image(
                        university,
                        'cover_image',
                        university.name,
                        '',
                        f'{city_name}, {university.country.name}',
                        allow_remote=False,
                    )

                save_image(
                    university,
                    'logo',
                    university.name,
                    '',
                    f'{city_name}, {university.country.name}',
                    allow_remote=False,
                    size=(640, 640),
                )

        manifest_path = 'erp/education/catalog_image_sources.json'
        if default_storage.exists(manifest_path):
            default_storage.delete(manifest_path)
        default_storage.save(
            manifest_path,
            ContentFile(json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf-8')),
        )
        self.stdout.write(self.style.SUCCESS(json.dumps(counters, ensure_ascii=False)))
