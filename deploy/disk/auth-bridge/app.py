import hashlib
import hmac
import json
import os
import re
import sqlite3
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import PurePosixPath

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


MANAGER_AUTH_URL = os.environ['MANAGER_AUTH_URL']
MANAGER_AUTH_TOKEN = os.environ['MANAGER_AUTH_TOKEN']
S3_ENDPOINT = os.environ['S3_ENDPOINT'].rstrip('/')
S3_REGION = os.environ['S3_REGION']
S3_BUCKET = os.environ['S3_BUCKET']
S3_ACCESS_KEY = os.environ['S3_ACCESS_KEY']
S3_SECRET_KEY = os.environ['S3_SECRET_KEY']
S3_KEY_PREFIX = os.environ.get('S3_KEY_PREFIX', 'disk/').strip('/') + '/'
DISK_PROVISION_TOKEN = os.environ['DISK_PROVISION_TOKEN']
DISK_ACTIVITY_HOOK_TOKEN = os.environ['DISK_ACTIVITY_HOOK_TOKEN']
ACTIVITY_DB_PATH = os.environ.get('ACTIVITY_DB_PATH', '/data/activity.sqlite3')
MAX_BODY_SIZE = 64 * 1024
MAX_UPLOAD_SIZE = 50 * 1024 * 1024
UPLOAD_EXTENSIONS = {'.pdf', '.docx', '.jpg', '.jpeg', '.png'}
ACTIVITY_ACTIONS = {'upload', 'download', 'delete', 'rename', 'mkdir', 'rmdir', 'copy'}
ACTIVITY_LOCK = threading.Lock()
SL_ID_RE = re.compile(r'^SL-[A-Z0-9-]{1,28}$', re.IGNORECASE)
ROOT_CATEGORIES = ('Бюджет', 'Контракт', 'Гослиния', 'Магистры')
CLIENT_FOLDERS = ('оригиналы', 'переводы', 'договоры', 'университеты', 'приглашения')

S3_CLIENT = boto3.client(
    's3',
    endpoint_url=S3_ENDPOINT,
    region_name=S3_REGION,
    aws_access_key_id=S3_ACCESS_KEY,
    aws_secret_access_key=S3_SECRET_KEY,
    config=Config(
        connect_timeout=5,
        read_timeout=10,
        retries={'max_attempts': 3, 'mode': 'standard'},
        s3={'addressing_style': 'path'},
    ),
)


def activity_connection():
    connection = sqlite3.connect(ACTIVITY_DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


def init_activity_db():
    os.makedirs(os.path.dirname(ACTIVITY_DB_PATH) or '.', exist_ok=True)
    with activity_connection() as connection:
        connection.executescript('''
            CREATE TABLE IF NOT EXISTS activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                action TEXT NOT NULL,
                virtual_path TEXT NOT NULL DEFAULT '',
                virtual_target_path TEXT NOT NULL DEFAULT '',
                file_size INTEGER NOT NULL DEFAULT 0,
                protocol TEXT NOT NULL DEFAULT '',
                ip TEXT NOT NULL DEFAULT '',
                event_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS activity_event_at_idx
                ON activity(event_at DESC);
        ''')


def event_time(value) -> str:
    try:
        timestamp = int(value)
        # SFTPGo sends nanoseconds since epoch.
        if timestamp > 10_000_000_000:
            timestamp /= 1_000_000_000
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError, OverflowError):
        return datetime.now(tz=timezone.utc).isoformat()


def record_activity(payload: dict):
    action = str(payload.get('action') or '').strip().lower()
    username = str(payload.get('username') or '').strip().lower()
    if action not in ACTIVITY_ACTIONS or not username:
        raise ValueError('Invalid activity')

    with ACTIVITY_LOCK, activity_connection() as connection:
        connection.execute(
            '''
            INSERT INTO activity (
                username, action, virtual_path, virtual_target_path,
                file_size, protocol, ip, event_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                username[:254],
                action,
                str(payload.get('virtual_path') or payload.get('path') or '')[:2048],
                str(payload.get('virtual_target_path') or payload.get('target_path') or '')[:2048],
                max(0, int(payload.get('file_size') or 0)),
                str(payload.get('protocol') or '')[:32],
                str(payload.get('ip') or '')[:64],
                event_time(payload.get('timestamp')),
            ),
        )


def recent_activity(limit: int = 40) -> list[dict]:
    safe_limit = min(max(limit, 1), 100)
    with activity_connection() as connection:
        rows = connection.execute(
            '''
            SELECT id, username, action, virtual_path, virtual_target_path,
                   file_size, event_at
            FROM activity
            ORDER BY id DESC
            LIMIT ?
            ''',
            (safe_limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def manager_authenticate(username: str, password: str) -> dict | None:
    body = json.dumps({'username': username, 'password': password}).encode()
    request = urllib.request.Request(
        MANAGER_AUTH_URL,
        data=body,
        method='POST',
        headers={
            'Authorization': f'Bearer {MANAGER_AUTH_TOKEN}',
            'Content-Type': 'application/json',
            'User-Agent': 'sl-disk-auth-bridge/1.0',
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            result = json.load(response)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError):
        return None
    return result if result.get('authenticated') else None


def sftpgo_user(auth_result: dict) -> dict:
    username = auth_result['username']
    local_id = hashlib.sha256(username.encode()).hexdigest()[:24]
    return {
        'status': 1,
        'username': username,
        'home_dir': f'/srv/sftpgo/data/{local_id}',
        'permissions': {'/': ['*']},
        'max_sessions': 5,
        'filesystem': {
            'provider': 1,
            's3config': {
                'bucket': S3_BUCKET,
                'region': S3_REGION,
                'access_key': S3_ACCESS_KEY,
                'access_secret': {'status': 'Plain', 'payload': S3_SECRET_KEY},
                'endpoint': S3_ENDPOINT,
                'key_prefix': S3_KEY_PREFIX,
                'force_path_style': True,
            },
        },
        'description': auth_result.get('display_name', ''),
    }


def safe_student_name(full_name: str, sl_id: str) -> str:
    cleaned = re.sub(r'[\\/\x00-\x1f\x7f]+', ' ', full_name)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip(' .')
    if not cleaned:
        raise ValueError('Invalid full_name')
    return f'{cleaned[:180]} ({sl_id})'


def safe_upload_name(filename: str) -> str:
    cleaned = re.sub(r'[\\/\x00-\x1f\x7f]+', '_', filename).strip(' .')
    if not cleaned or cleaned in {'.', '..'}:
        raise ValueError('Invalid file name')
    cleaned = cleaned[:220]
    if PurePosixPath(cleaned).suffix.lower() not in UPLOAD_EXTENSIONS:
        raise ValueError('Unsupported file format')
    return cleaned


def unique_upload_key(relative_folder: str, filename: str) -> str:
    path = PurePosixPath(filename)
    for number in range(1, 1000):
        candidate_name = filename if number == 1 else f'{path.stem} ({number}){path.suffix}'
        key = f'{S3_KEY_PREFIX}{relative_folder.strip("/")}/{candidate_name}'
        try:
            S3_CLIENT.head_object(Bucket=S3_BUCKET, Key=key)
        except ClientError as exc:
            code = str(exc.response.get('Error', {}).get('Code', ''))
            if code in {'404', 'NoSuchKey', 'NotFound'}:
                return key
            raise
    raise ValueError('Too many files with the same name')


def upload_client_file(relative_folder: str, filename: str, content, content_type: str) -> str:
    key = unique_upload_key(relative_folder, filename)
    S3_CLIENT.upload_fileobj(
        content,
        S3_BUCKET,
        key,
        ExtraArgs={'ContentType': content_type or 'application/octet-stream'},
    )
    return key


def provision_client_folders(academic_year: int, category: str, student_name: str) -> list[str]:
    for root_category in ROOT_CATEGORIES:
        S3_CLIENT.put_object(
            Bucket=S3_BUCKET,
            Key=f'{S3_KEY_PREFIX}{academic_year}/{root_category}/',
            Body=b'',
            ContentType='application/x-directory',
        )

    root = f'{academic_year}/{category}/{student_name}'
    paths = []
    for folder in CLIENT_FOLDERS:
        relative_path = f'{root}/{folder}/'
        S3_CLIENT.put_object(
            Bucket=S3_BUCKET,
            Key=f'{S3_KEY_PREFIX}{relative_path}',
            Body=b'',
            ContentType='application/x-directory',
        )
        paths.append(relative_path)
    return paths


class Handler(BaseHTTPRequestHandler):
    server_version = 'SLDiskAuth/1.0'

    def do_GET(self):
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path == '/healthz':
            return self.respond(200, {'status': 'ok'})
        if parsed.path == '/activity/recent':
            return self.respond(200, {'events': recent_activity()})
        return self.respond(404, {'detail': 'Not found'})

    def do_POST(self):
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path not in {'/auth/sftpgo', '/internal/folders', '/internal/files', '/events/sftpgo'}:
            return self.respond(404, {'detail': 'Not found'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            return self.respond(400, {'detail': 'Invalid request'})
        if parsed.path == '/internal/files':
            return self.handle_file_upload(length)
        if length <= 0 or length > MAX_BODY_SIZE:
            return self.respond(400, {'detail': 'Invalid request'})
        try:
            payload = json.loads(self.rfile.read(length))
        except (ValueError, UnicodeDecodeError):
            return self.respond(400, {'detail': 'Invalid JSON'})

        if parsed.path == '/events/sftpgo':
            supplied_token = urllib.parse.parse_qs(parsed.query).get('token', [''])[0]
            if not supplied_token or not hmac.compare_digest(
                supplied_token,
                DISK_ACTIVITY_HOOK_TOKEN,
            ):
                return self.respond(401, {'detail': 'Authentication failed'})
            try:
                record_activity(payload)
            except (TypeError, ValueError):
                return self.respond(400, {'detail': 'Invalid activity'})
            return self.respond(200, {'status': 'recorded'})

        if parsed.path == '/internal/folders':
            return self.handle_folder_provisioning(payload)

        username = str(payload.get('username') or '').strip()
        password = str(payload.get('password') or '')
        if not username or not password:
            return self.respond(401, {'detail': 'Authentication failed'})

        auth_result = manager_authenticate(username, password)
        if not auth_result:
            return self.respond(401, {'detail': 'Authentication failed'})
        return self.respond(200, sftpgo_user(auth_result))

    def valid_provision_token(self) -> bool:
        supplied_token = self.headers.get('Authorization', '').removeprefix('Bearer ').strip()
        return bool(
            supplied_token
            and hmac.compare_digest(supplied_token, DISK_PROVISION_TOKEN)
        )

    def handle_file_upload(self, length: int):
        if not self.valid_provision_token():
            return self.respond(401, {'detail': 'Authentication failed'})
        if length <= 0 or length > MAX_UPLOAD_SIZE:
            return self.respond(413, {'detail': 'File must be between 1 byte and 50 MB'})

        try:
            academic_year = int(self.headers.get('X-Academic-Year', ''))
        except ValueError:
            return self.respond(400, {'detail': 'Invalid academic year'})
        sl_id = urllib.parse.unquote(self.headers.get('X-SL-ID', '')).strip().upper()
        full_name = urllib.parse.unquote(self.headers.get('X-Client-Name', '')).strip()
        category = urllib.parse.unquote(self.headers.get('X-Disk-Category', '')).strip()
        folder = urllib.parse.unquote(self.headers.get('X-Disk-Folder', '')).strip()
        actor = urllib.parse.unquote(self.headers.get('X-Actor', '')).strip().lower()
        try:
            filename = safe_upload_name(urllib.parse.unquote(self.headers.get('X-File-Name', '')))
            student_name = safe_student_name(full_name, sl_id)
        except ValueError as exc:
            return self.respond(400, {'detail': str(exc)})
        if not 2020 <= academic_year <= 2100:
            return self.respond(400, {'detail': 'Invalid academic year'})
        if not SL_ID_RE.fullmatch(sl_id):
            return self.respond(400, {'detail': 'Invalid SL-ID'})
        if category not in ROOT_CATEGORIES or folder not in CLIENT_FOLDERS:
            return self.respond(400, {'detail': 'Invalid disk folder'})
        if not actor or len(actor) > 254:
            return self.respond(400, {'detail': 'Invalid actor'})

        relative_folder = f'{academic_year}/{category}/{student_name}/{folder}'
        try:
            with tempfile.SpooledTemporaryFile(max_size=4 * 1024 * 1024) as temporary:
                remaining = length
                while remaining:
                    chunk = self.rfile.read(min(1024 * 1024, remaining))
                    if not chunk:
                        return self.respond(400, {'detail': 'Incomplete upload'})
                    temporary.write(chunk)
                    remaining -= len(chunk)
                temporary.seek(0)
                key = upload_client_file(
                    relative_folder,
                    filename,
                    temporary,
                    self.headers.get('Content-Type', ''),
                )
        except Exception as exc:
            print(f'file upload failed for {academic_year}/{sl_id}: {exc}', flush=True)
            return self.respond(502, {'detail': 'Storage is temporarily unavailable'})

        virtual_path = '/' + key.removeprefix(S3_KEY_PREFIX)
        record_activity({
            'username': actor,
            'action': 'upload',
            'virtual_path': virtual_path,
            'file_size': length,
            'protocol': 'ManagerSL',
            'ip': self.headers.get('X-Forwarded-For', '').split(',')[0].strip(),
        })
        return self.respond(201, {
            'status': 'uploaded',
            'path': virtual_path,
            'size': length,
        })

    def handle_folder_provisioning(self, payload: dict):
        if not self.valid_provision_token():
            return self.respond(401, {'detail': 'Authentication failed'})

        try:
            academic_year = int(payload.get('academic_year'))
        except (TypeError, ValueError):
            return self.respond(400, {'detail': 'Invalid academic_year'})
        sl_id = str(payload.get('sl_id') or '').strip().upper()
        full_name = str(payload.get('full_name') or '').strip()
        category = str(payload.get('category') or '').strip()
        if not 2020 <= academic_year <= 2100:
            return self.respond(400, {'detail': 'Invalid academic_year'})
        if not SL_ID_RE.fullmatch(sl_id):
            return self.respond(400, {'detail': 'Invalid sl_id'})
        if category not in ROOT_CATEGORIES:
            return self.respond(400, {'detail': 'Invalid category'})
        try:
            student_name = safe_student_name(full_name, sl_id)
        except ValueError:
            return self.respond(400, {'detail': 'Invalid full_name'})

        try:
            paths = provision_client_folders(academic_year, category, student_name)
        except Exception as exc:
            print(f'folder provisioning failed for {academic_year}/{sl_id}: {exc}', flush=True)
            return self.respond(502, {'detail': 'Storage is temporarily unavailable'})
        return self.respond(200, {
            'status': 'ready',
            'root': f'{academic_year}/{category}/{student_name}/',
            'paths': paths,
        })

    def respond(self, status: int, payload: dict):
        encoded = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, fmt, *args):
        print(f'{self.address_string()} - {fmt % args}', flush=True)


if __name__ == '__main__':
    init_activity_db()
    ThreadingHTTPServer(('0.0.0.0', 9000), Handler).serve_forever()
