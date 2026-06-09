import json
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from django.db import transaction

from .models import Currency, Program, ProgramFee, University


class ProgramJsonParseError(ValueError):
    pass


@dataclass
class ProgramImportError:
    row_number: int | None
    message: str


@dataclass
class ProgramImportResult:
    total_rows: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[ProgramImportError] = field(default_factory=list)
    dry_run: bool = True

    @property
    def has_errors(self):
        return bool(self.errors)


DEGREE_ALIASES = {
    'bachelor': 'bachelor',
    'бакалавр': 'bachelor',
    'бакалавриат': 'bachelor',
    'master': 'master',
    'магистр': 'master',
    'магистратура': 'master',
    'specialist': 'specialist',
    'специалист': 'specialist',
    'специалитет': 'specialist',
    'language': 'language',
    'языковые курсы': 'language',
    'языковой курс': 'language',
    'foundation': 'foundation',
    'подкурс': 'foundation',
    'подготовительный курс': 'foundation',
    'подготовка': 'foundation',
    'school': 'school',
    'школа': 'school',
    'phd': 'phd',
    'аспирантура': 'phd',
    'докторантура': 'phd',
    'other': 'other',
    'другое': 'other',
}

TRUE_VALUES = {'true', '1', 'yes', 'y', 'on', 'да', 'д', 'истина'}
FALSE_VALUES = {'false', '0', 'no', 'n', 'off', 'нет', 'н', 'ложь'}


def normalize_spaces(value):
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def decode_json_content(content):
    if isinstance(content, str):
        return content.lstrip('\ufeff')
    try:
        return content.decode('utf-8-sig')
    except UnicodeDecodeError:
        return content.decode('utf-8-sig', errors='replace')


def loads_program_records(content):
    text = decode_json_content(content).strip()
    if not text:
        raise ProgramJsonParseError('Файл пустой.')

    candidates = [text]
    if not text.startswith('['):
        wrapped_text = text.rstrip(", \n\r\t")
        candidates.append(f'[{wrapped_text}]')

    last_error = None
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
            break
        except json.JSONDecodeError as exc:
            last_error = exc
    else:
        raise ProgramJsonParseError(
            f'Ошибка JSON: {last_error.msg}. Строка {last_error.lineno}, колонка {last_error.colno}.'
        )

    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        raise ProgramJsonParseError('JSON должен быть массивом объектов или одним объектом программы.')
    return payload


def decimal_or_zero(value):
    if value in (None, ''):
        return Decimal('0.00')
    try:
        return Decimal(str(value).replace(',', '.')).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError):
        raise ValueError(f'Некорректная стоимость: {value}')


def parse_bool(value):
    if isinstance(value, bool):
        return value
    if value in (None, ''):
        return True
    normalized = normalize_spaces(value).lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    raise ValueError(f'Некорректное значение is_active: {value}')


def normalize_degree(value):
    raw = normalize_spaces(value).lower()
    degree = DEGREE_ALIASES.get(raw, raw)
    allowed = {choice[0] for choice in Program.DEGREE_CHOICES}
    if degree not in allowed:
        allowed_display = ', '.join(sorted(allowed))
        raise ValueError(f'Неподдерживаемая степень: {value}. Допустимые значения: {allowed_display}')
    return degree


def get_usd_currency():
    currency, _ = Currency.objects.get_or_create(
        code='USD',
        defaults={'name': 'US Dollar', 'symbol': '$', 'rate_to_usd': Decimal('1.000000')},
    )
    return currency


def find_university(name):
    raw_name = normalize_spaces(name)
    if not raw_name:
        return None

    exact = University.objects.filter(name=raw_name).first()
    if exact:
        return exact

    raw_key = raw_name.casefold()
    for university in University.objects.only('id', 'name'):
        if normalize_spaces(university.name).casefold() == raw_key:
            return university
    return None


def validate_record(record, row_number):
    if not isinstance(record, dict):
        raise ValueError('Строка должна быть JSON-объектом.')

    university_name = normalize_spaces(record.get('university'))
    program_name = normalize_spaces(record.get('name'))
    degree_value = record.get('degree')

    missing = []
    if not university_name:
        missing.append('university')
    if not program_name:
        missing.append('name')
    if degree_value in (None, ''):
        missing.append('degree')
    if missing:
        raise ValueError(f'Не заполнены обязательные поля: {", ".join(missing)}')

    university = find_university(university_name)
    if not university:
        raise ValueError(f'Университет не найден: {university_name}')

    return {
        'row_number': row_number,
        'university': university,
        'university_name': university_name,
        'name': program_name,
        'degree': normalize_degree(degree_value),
        'duration': normalize_spaces(record.get('duration')),
        'tuition_fee': decimal_or_zero(record.get('tuition_fee')),
        'service_fee': decimal_or_zero(record.get('service_fee')),
        'is_active': parse_bool(record.get('is_active', True)),
    }


def update_program_fee(program, university, tuition_fee, service_fee):
    currency = university.local_currency or get_usd_currency()
    fee = program.fees.filter(currency=currency).order_by('-created_at', '-id').first()
    if not fee:
        fee = ProgramFee(program=program, currency=currency)
    fee.tuition_fee = tuition_fee
    fee.service_fee_usd = service_fee
    fee.save()
    return fee


def import_programs_from_json(content, *, dry_run=True, update_existing=True):
    result = ProgramImportResult(dry_run=dry_run)
    try:
        records = loads_program_records(content)
    except ProgramJsonParseError as exc:
        result.errors.append(ProgramImportError(row_number=None, message=str(exc)))
        return result

    result.total_rows = len(records)

    for index, record in enumerate(records, start=1):
        try:
            data = validate_record(record, index)
        except ValueError as exc:
            result.errors.append(ProgramImportError(row_number=index, message=str(exc)))
            result.skipped += 1
            continue

        existing = Program.objects.filter(
            university=data['university'],
            name=data['name'],
            degree=data['degree'],
            duration=data['duration'],
        ).first()

        if existing:
            if not update_existing:
                result.skipped += 1
                continue
            result.updated += 1
            if not dry_run:
                with transaction.atomic():
                    existing.is_active = data['is_active']
                    if data['is_active']:
                        existing.is_archived = False
                    existing.save(update_fields=['is_active', 'is_archived', 'updated_at'])
                    update_program_fee(existing, data['university'], data['tuition_fee'], data['service_fee'])
            continue

        result.created += 1
        if not dry_run:
            with transaction.atomic():
                program = Program.objects.create(
                    university=data['university'],
                    name=data['name'],
                    degree=data['degree'],
                    duration=data['duration'],
                    is_active=data['is_active'],
                    is_archived=False,
                )
                update_program_fee(program, data['university'], data['tuition_fee'], data['service_fee'])

    return result
