# Managers SL Mobile API Documentation

Документация для будущего React Native приложения по текущей ветке `rebuild-erp-core`.

Дата актуализации: 2026-05-22.

## 1. Базовая информация

Текущая архитектура API:

- Авторизация и часть системных endpoints пока находятся в старом пространстве `/api/...`.
- Новые ERP/CRM/HRM модули находятся в `/api/v1/...`.
- Отдельный wrapper `apps/mobile_api` ещё не создан. Когда начнётся отдельный этап мобильного приложения, можно будет добавить красивые mobile-specific endpoints, не ломая текущие API.

Примеры base URL:

```text
Local:      http://127.0.0.1:8000
Production: https://your-domain.com
```

Все защищённые запросы используют JWT:

```http
Authorization: Bearer <access_token>
Content-Type: application/json
Accept: application/json
```

Для загрузки файлов:

```http
Authorization: Bearer <access_token>
Content-Type: multipart/form-data
```

## 2. Формат ответов

DRF использует `LimitOffsetPagination`, размер страницы по умолчанию `50`.

Списки обычно приходят так:

```json
{
  "count": 125,
  "next": "https://api.example.com/api/v1/crm/leads/?limit=50&offset=50",
  "previous": null,
  "results": [
    {
      "id": 1,
      "created_at": "2026-05-22T10:00:00+05:00",
      "updated_at": "2026-05-22T10:15:00+05:00"
    }
  ]
}
```

Параметры пагинации:

```text
?limit=20&offset=0
```

Ошибки валидации:

```json
{
  "phone": ["This field is required."]
}
```

Ошибка доступа:

```json
{
  "detail": "Authentication credentials were not provided."
}
```

## 3. Авторизация

### POST `/api/auth/login/`

Вход по email и паролю. В проекте `email` является `USERNAME_FIELD`.

Request:

```json
{
  "email": "manager@example.com",
  "password": "password"
}
```

Response `200`:

```json
{
  "access": "jwt-access-token",
  "refresh": "jwt-refresh-token",
  "user": {
    "id": 12,
    "email": "manager@example.com",
    "first_name": "Ali",
    "last_name": "Manager",
    "full_name": "Ali Manager",
    "role": "manager",
    "is_superuser": false,
    "is_staff": false,
    "is_admin_role": false,
    "managersalary": null,
    "office": null
  }
}
```

Как использовать в приложении:

1. Сохранить `access` и `refresh` в secure storage.
2. В каждый API-запрос добавлять `Authorization: Bearer <access>`.
3. Если API вернул `401`, обновить access через refresh endpoint.

### POST `/api/auth/refresh/`

Request:

```json
{
  "refresh": "jwt-refresh-token"
}
```

Response `200`:

```json
{
  "access": "new-jwt-access-token"
}
```

### POST `/api/auth/logout/`

Request:

```json
{
  "refresh": "jwt-refresh-token"
}
```

Response `200`:

```json
{
  "detail": "Logout completed successfully"
}
```

На клиенте после logout нужно удалить оба токена.

## 4. Системные endpoints

### GET `/api/health/`

Публичная проверка сервера.

Response:

```json
{
  "status": "ok",
  "service": "managers-sl-backend",
  "time": "2026-05-22T15:00:00+05:00"
}
```

### GET `/api/app/config/`

Текущая конфигурация приложения для авторизованного пользователя.

Response:

```json
{
  "user": {
    "id": 12,
    "email": "manager@example.com",
    "role": "manager",
    "is_admin": false
  },
  "notifications": {
    "start_day": "08:00",
    "end_day": "17:50",
    "daily_report": "21:00"
  },
  "endpoints": {
    "login": "/api/auth/login/",
    "logout": "/api/auth/logout/",
    "refresh": "/api/auth/refresh/",
    "dashboard": "/api/app/dashboard/",
    "health": "/api/health/"
  }
}
```

### GET `/api/app/dashboard/`

Старый dashboard endpoint. Можно временно использовать для первого экрана, но позже лучше заменить на новый `/api/v1/dashboard/` в `apps/mobile_api`.

Response для менеджера:

```json
{
  "role": "manager",
  "today": "2026-05-22",
  "workday": {
    "has_active_shift": true,
    "has_report_today": false,
    "forgotten_shift_count": 0
  },
  "salary": {
    "fixed_salary_usd": 500.0,
    "bonus_balance_usd": 120.0,
    "month_revenue_usd": 3000.0,
    "month_plan_usd": 5000.0,
    "plan_progress_percent": 60,
    "motivation_target_usd": 6000.0,
    "motivation_reward_usd": 300.0
  },
  "counts": {
    "clients": 18,
    "deals": 7,
    "pending_payments": 2,
    "tasks": 5
  },
  "recent": {
    "clients": [],
    "deals": [],
    "tasks": [],
    "leads": []
  }
}
```

## 5. Общие CRUD правила

Большинство `/api/v1/...` endpoints сделаны через DRF `ModelViewSet`.

Стандартные методы:

```text
GET    /resource/        список
POST   /resource/        создать
GET    /resource/{id}/   получить одну запись
PATCH  /resource/{id}/   частично обновить
PUT    /resource/{id}/   полностью обновить
DELETE /resource/{id}/   удалить
```

Частые query параметры:

```text
?search=text
?company=1
?office=2
?status=new
?date_from=2026-05-01
?date_to=2026-05-31
?is_active=true
?limit=20&offset=0
```

Важно:

- Все `id`, `company`, `office`, `client`, `manager` и похожие поля в request body передаются как integer id.
- Денежные поля обычно приходят строками или decimal-числами. На мобильном клиенте лучше хранить их как string до форматирования.
- Поля вида `*_name`, `*_display`, `*_url`, `can_*`, `*_count` чаще всего read-only и нужны для UI.
- Для `PATCH` можно отправлять только изменённые поля.

## 6. CRM API

Base path: `/api/v1/crm/`

### Endpoints

| Endpoint | Назначение |
| --- | --- |
| `GET/POST /api/v1/crm/lead-sources/` | Источники лидов |
| `GET/POST /api/v1/crm/leads/` | Лиды |
| `POST /api/v1/crm/leads/{id}/convert/` | Конвертация лида в клиента |
| `GET/POST /api/v1/crm/clients/` | Клиенты |
| `GET /api/v1/crm/clients/{id}/timeline/` | Таймлайн клиента |
| `GET/POST /api/v1/crm/applications/` | Заявки клиента |
| `GET/POST /api/v1/crm/activities/` | Активности клиента |
| `GET/POST /api/v1/crm/notes/` | Заметки клиента |
| `GET/POST /api/v1/crm/files/` | Файлы клиента, multipart upload |

### Фильтры

```text
leads:        ?status=new&office=1&search=ali
clients:      ?status=consultation&office=1&search=ali
applications: ?status=submitted&client=10&search=medicine
activities:   ?client=10
notes:        ?client=10
files:        ?client=10&application=4
```

### Создать лид

Request:

```json
{
  "company": 1,
  "office": 1,
  "source": 2,
  "full_name": "Ali Veliyev",
  "phone": "+99361234567",
  "email": "ali@example.com",
  "country": "Turkmenistan",
  "city": "Ashgabat",
  "direction": "admission",
  "interested_country": "Turkey",
  "interested_program": "Business Administration",
  "status": "new",
  "comment": "Interested in bachelor programs"
}
```

Response `201`:

```json
{
  "id": 101,
  "source_name": "Instagram",
  "manager_name": "Ali Manager",
  "company_name": "Students Life",
  "office_name": "Ashgabat",
  "full_name": "Ali Veliyev",
  "phone": "+99361234567",
  "email": "ali@example.com",
  "direction": "admission",
  "status": "new",
  "converted_at": null,
  "company": 1,
  "office": 1,
  "source": 2,
  "manager": 12,
  "created_at": "2026-05-22T15:10:00+05:00",
  "updated_at": "2026-05-22T15:10:00+05:00"
}
```

### Конвертировать лид в клиента

Request:

```http
POST /api/v1/crm/leads/101/convert/
```

Response `200`:

```json
{
  "detail": "Lead converted to client.",
  "client": {
    "id": 55,
    "full_name": "Ali Veliyev",
    "phone": "+99361234567",
    "email": "ali@example.com",
    "status": "new",
    "status_display": "Новый",
    "source_lead": 101,
    "company": 1,
    "office": 1,
    "manager": 12
  }
}
```

### Получить таймлайн клиента

```http
GET /api/v1/crm/clients/55/timeline/
```

Response:

```json
{
  "client": {},
  "applications": [],
  "activities": [],
  "notes": [],
  "files": []
}
```

## 7. Education Catalog API

Base path: `/api/v1/education/`

### Endpoints

| Endpoint | Назначение |
| --- | --- |
| `/countries/` | Страны |
| `/cities/` | Города |
| `/currencies/` | Валюты и курс к USD |
| `/universities/` | Университеты |
| `/programs/` | Программы |
| `/program-fees/` | Стоимость программ |
| `/intakes/` | Наборы/intakes |
| `/required-documents/` | Необходимые документы |
| `/university-contacts/` | Контакты университетов |

Стандартные методы CRUD доступны, но для мобильного каталога чаще всего нужны `GET`.

### Фильтры

```text
countries:            ?is_active=true&search=turkey
cities:               ?country=1&is_active=true&search=istanbul
universities:         ?country=1&city=2&is_active=true&search=ankara
programs:             ?university=5&degree=bachelor&is_active=true&search=business
program-fees:         ?program=10&currency=1
intakes:              ?program=10&is_active=true
required-documents:   ?university=5&program=10
university-contacts:  ?university=5&is_active=true
```

### Пример списка университетов

```http
GET /api/v1/education/universities/?country=1&search=medical&limit=20
```

Response:

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 5,
      "country_name": "Turkey",
      "city_name": "Istanbul",
      "currency_code": "USD",
      "programs_count": 12,
      "name": "Istanbul Medical University",
      "website": "https://example.edu",
      "description": "Short description",
      "is_active": true,
      "country": 1,
      "city": 2,
      "local_currency": 1
    }
  ]
}
```

### Пример программы

```json
{
  "id": 10,
  "university_name": "Istanbul Medical University",
  "country_name": "Turkey",
  "degree": "bachelor",
  "degree_display": "Bachelor",
  "name": "Medicine",
  "faculty": "Medical Faculty",
  "language": "English",
  "duration": "6 years",
  "fees": [],
  "intakes": [],
  "required_documents": [],
  "university": 5
}
```

## 8. ERP Services API

Base path: `/api/v1/services/`

### Endpoints

| Endpoint | Назначение |
| --- | --- |
| `/categories/` | Категории услуг |
| `/services/` | Услуги |
| `/prices/` | История/варианты цен |

### Фильтры

```text
categories: ?company=1&is_active=true&search=visa
services:   ?company=1&category=2&is_active=true&is_public=true&search=translation
prices:     ?service=7&currency=1
```

Важно: поле `real_cost` скрывается сериализатором для обычных пользователей. Его могут видеть только админы/бухгалтерия по backend permissions.

### Пример услуги

```json
{
  "id": 7,
  "company_name": "Students Life",
  "category_name": "Visa",
  "currency_code": "USD",
  "currency_symbol": "$",
  "prices": [],
  "title": "Student visa support",
  "code": "student_visa_support",
  "description": "Full visa support package",
  "price_client": "300.00",
  "is_active": true,
  "is_public": true,
  "sort_order": 10,
  "custom_data": {},
  "company": 1,
  "category": 2,
  "currency": 1
}
```

## 9. Finance API

Base path: `/api/v1/finance/`

### Endpoints

| Endpoint | Назначение |
| --- | --- |
| `/cashboxes/` | Кассы |
| `/deals/` | Сделки |
| `/payments/` | Платежи |
| `/payments/{id}/confirm/` | Подтвердить платёж |
| `/expense-categories/` | Категории расходов |
| `/expenses/` | Расходы |
| `/expenses/{id}/confirm/` | Подтвердить расход |
| `/incomes/` | Доходы |
| `/transactions/` | Транзакции, read-only |
| `/commissions/` | Комиссии сотрудников |
| `/periods/` | Финансовые периоды |
| `/periods/{id}/calculate/` | Пересчитать период |
| `/periods/{id}/close/` | Закрыть период |

### Фильтры

```text
?company=1
?office=1
?manager=12
?client=55
?status=paid_partial
?is_confirmed=false
?date_from=2026-05-01
?date_to=2026-05-31
?search=ali
```

### Создать сделку

Request:

```json
{
  "company": 1,
  "office": 1,
  "client": 55,
  "application": 4,
  "manager": 12,
  "deal_type": "service",
  "service": 7,
  "title": "Student visa support for Ali",
  "currency": 1,
  "price_client": "300.00",
  "expected_revenue_usd": "300.00",
  "comment": "First payment expected this week",
  "custom_data": {}
}
```

Response:

```json
{
  "id": 30,
  "client_name": "Ali Veliyev",
  "manager_name": "Ali Manager",
  "service_title": "Student visa support",
  "currency_code": "USD",
  "deal_type": "service",
  "deal_type_display": "Service",
  "title": "Student visa support for Ali",
  "price_client": "300.00",
  "expected_revenue_usd": "300.00",
  "total_to_pay_usd": "300.00",
  "paid_amount_usd": "0.00",
  "payment_status": "new",
  "payment_status_display": "New",
  "client": 55,
  "application": 4,
  "manager": 12,
  "service": 7,
  "currency": 1
}
```

`total_to_pay_usd` считается backend через `currency.rate_to_usd`.

### Создать платёж

Request:

```json
{
  "company": 1,
  "office": 1,
  "deal": 30,
  "client": 55,
  "manager": 12,
  "cashbox": 3,
  "amount": "150.00",
  "currency": 1,
  "exchange_rate": "1.000000",
  "method": "cash",
  "payment_date": "2026-05-22",
  "comment": "First installment"
}
```

Response:

```json
{
  "id": 44,
  "deal_title": "Student visa support for Ali",
  "client_name": "Ali Veliyev",
  "manager_name": "Ali Manager",
  "cashbox_name": "Main cashbox",
  "currency_code": "USD",
  "amount": "150.00",
  "exchange_rate": "1.000000",
  "amount_usd": "150.00",
  "method": "cash",
  "method_display": "Cash",
  "payment_date": "2026-05-22",
  "is_confirmed": false,
  "confirmed_by": null,
  "confirmed_at": null,
  "deal": 30,
  "client": 55,
  "manager": 12,
  "cashbox": 3,
  "currency": 1
}
```

### Подтвердить платёж

```http
POST /api/v1/finance/payments/44/confirm/
```

Response:

```json
{
  "id": 44,
  "amount_usd": "150.00",
  "is_confirmed": true,
  "confirmed_by": 1,
  "confirmed_by_name": "Admin User",
  "confirmed_at": "2026-05-22T15:30:00+05:00"
}
```

После подтверждения backend:

- обновляет `deal.paid_amount_usd`;
- обновляет `deal.payment_status`;
- создаёт `Transaction` типа `payment`, если есть `cashbox`.

### Подтвердить расход

```http
POST /api/v1/finance/expenses/80/confirm/
```

После подтверждения backend создаёт `Transaction` типа `expense`, если есть `cashbox`.

## 10. ERP Documents API

Base path: `/api/v1/documents/`

### Endpoints

| Endpoint | Назначение |
| --- | --- |
| `/templates/` | DOCX шаблоны |
| `/templates/{id}/generate/` | Сгенерировать документ из шаблона |
| `/template-fields/` | Поля шаблонов |
| `/generated/` | Сгенерированные документы |
| `/generated/{id}/generate/` | Перегенерировать файл |
| `/generated/{id}/submit-for-approval/` | Отправить на проверку |
| `/generated/{id}/approve/` | Approve, только admin |
| `/generated/{id}/reject/` | Reject, только admin |
| `/generated/{id}/download-original/` | Скачать оригинал, если разрешено |
| `/generated/{id}/download-approved/` | Скачать approved файл |
| `/approvals/` | Очередь согласований |
| `/approvals/{id}/approve/` | Approve через approval object |
| `/approvals/{id}/reject/` | Reject через approval object |
| `/stamp-rules/` | Правила печати/штампа |
| `/download-logs/` | Логи скачиваний, read-only |

### Фильтры

```text
?company=1
?office=1
?status=pending_approval
?template=3
?client=55
?manager=12
?date_from=2026-05-01
?date_to=2026-05-31
?search=contract
```

### Сгенерировать документ из шаблона

Request:

```json
{
  "client": 55,
  "application": 4,
  "deal": 30,
  "title": "Contract for Ali Veliyev",
  "context_data": {
    "client_full_name": "Ali Veliyev",
    "passport_number": "A1234567",
    "university_name": "Istanbul Medical University"
  },
  "comment": "Please approve"
}
```

```http
POST /api/v1/documents/templates/3/generate/
```

Response `201`:

```json
{
  "id": 91,
  "template_name": "Student contract",
  "client_name": "Ali Veliyev",
  "deal_title": "Student visa support for Ali",
  "manager_name": "Ali Manager",
  "status": "pending_approval",
  "status_display": "Pending approval",
  "title": "Contract for Ali Veliyev",
  "context_data": {
    "client_full_name": "Ali Veliyev"
  },
  "generated_file_url": "https://api.example.com/media/erp/documents/generated/contract.docx",
  "approved_file_url": null,
  "can_download_original": false,
  "can_download_approved": false,
  "can_download": false
}
```

### Approve с печатью

```http
POST /api/v1/documents/generated/91/approve/
```

Request:

```json
{
  "approval_type": "approve_with_stamp",
  "with_stamp": true,
  "comment": "Approved with stamp"
}
```

### Reject

```http
POST /api/v1/documents/generated/91/reject/
```

Request:

```json
{
  "reason": "Passport number is missing"
}
```

### Скачать файл

```http
GET /api/v1/documents/generated/91/download-approved/
```

Response: бинарный файл `FileResponse`, не JSON. Клиент должен скачивать как файл.

## 11. Attendance API

Base path: `/api/v1/attendance/`

### Endpoints

| Endpoint | Назначение |
| --- | --- |
| `/workdays/` | Рабочие дни |
| `/workdays/today/` | Сегодняшний рабочий день |
| `/workdays/start/` | Начать рабочий день |
| `/workdays/report/` | Отправить daily report |
| `/workdays/close/` | Закрыть рабочий день |
| `/reports/` | Daily reports |
| `/reminders/` | Напоминания |
| `/auto-close-logs/` | Логи автозакрытия, read-only |

### Фильтры

```text
?company=1
?office=1
?employee=12
?manager=12
?status=started
?date_from=2026-05-01
?date_to=2026-05-31
?search=ali
```

### Рекомендуемый mobile flow рабочего дня

1. При открытии приложения вызвать `GET /api/v1/attendance/workdays/today/`.
2. Если статус `not_started`, показать кнопку "Start".
3. После начала дня вызвать `POST /api/v1/attendance/workdays/start/`.
4. В конце дня отправить отчёт через `POST /api/v1/attendance/workdays/report/`.
5. После отчёта закрыть день через `POST /api/v1/attendance/workdays/close/`.

### GET today

Response:

```json
{
  "id": 10,
  "company_name": "Students Life",
  "office_name": "Ashgabat",
  "employee_name": "Ali Manager",
  "status": "started",
  "status_display": "Started",
  "date": "2026-05-22",
  "started_at": "2026-05-22T09:00:00+05:00",
  "closed_at": null,
  "total_work_seconds": 0,
  "total_work_hours": 0.0,
  "report_required": true,
  "has_report": false,
  "sessions": [],
  "daily_report": null,
  "company": 1,
  "office": 1,
  "employee": 12
}
```

### POST start

Request:

```json
{
  "note": "Started from mobile app"
}
```

Response: `WorkDaySerializer`.

### POST report

Request:

```json
{
  "content": "Worked with leads and clients.",
  "results": "Converted 2 leads, prepared 1 application.",
  "plans": "Follow up with pending payments tomorrow.",
  "problems": "",
  "leads_processed": 12,
  "deals_closed": 1,
  "comment": "Submitted from mobile"
}
```

Response:

```json
{
  "workday": {},
  "report": {
    "id": 22,
    "content": "Worked with leads and clients.",
    "results": "Converted 2 leads, prepared 1 application.",
    "plans": "Follow up with pending payments tomorrow.",
    "problems": "",
    "leads_processed": 12,
    "deals_closed": 1,
    "submitted_at": "2026-05-22T18:00:00+05:00"
  }
}
```

### POST close

Request:

```json
{
  "comment": "Closed from mobile app"
}
```

Response: `WorkDaySerializer`.

## 12. Projects API

Base path: `/api/v1/projects/`

### Endpoints

| Endpoint | Назначение |
| --- | --- |
| `/` | Проекты |
| `/{id}/` | Детали проекта |
| `/sections/` | Секции проекта |
| `/tasks/` | Задачи |
| `/tasks/{id}/add_comment/` | Добавить комментарий |
| `/tasks/{id}/complete_task/` | Завершить задачу |
| `/tasks/{id}/reopen_task/` | Переоткрыть задачу |
| `/tasks/{id}/assign/` | Назначить пользователя |
| `/tasks/{id}/add_watcher/` | Добавить наблюдателя |
| `/comments/` | Комментарии задач |
| `/checklists/` | Чеклисты |
| `/checklist-items/` | Пункты чеклистов |
| `/attachments/` | Вложения задач, multipart upload |
| `/notes/` | Заметки проекта |
| `/watchers/` | Наблюдатели задач |

### Фильтры

```text
projects: ?company=1&office=1&status=active&owner=12&participant=12&search=erp
tasks:    ?project=3&section=5&status=todo&priority=high&assigned_to=12&search=contract
comments: ?task=9&search=text
files:    ?task=9&attachment_type=file
```

### Создать задачу

Request:

```json
{
  "project": 3,
  "section": 5,
  "title": "Prepare contract",
  "description": "Generate contract and submit for approval",
  "status": "todo",
  "priority": "high",
  "deadline": "2026-05-25T18:00:00+05:00",
  "assigned_to": 12,
  "custom_data": {}
}
```

Response:

```json
{
  "id": 9,
  "project_title": "ERP migration",
  "section_title": "Documents",
  "assigned_to_data": {
    "id": 12,
    "full_name": "Ali Manager",
    "email": "manager@example.com"
  },
  "status": "todo",
  "status_display": "To do",
  "priority": "high",
  "priority_display": "High",
  "title": "Prepare contract",
  "comments_count": 0,
  "attachments_count": 0,
  "watchers_count": 0,
  "project": 3,
  "section": 5,
  "assigned_to": 12
}
```

### Завершить задачу

```http
POST /api/v1/projects/tasks/9/complete_task/
```

Response: `ProjectTaskSerializer` со статусом `done`.

### Добавить комментарий

```http
POST /api/v1/projects/tasks/9/add_comment/
```

Request:

```json
{
  "text": "Contract generated and sent for approval."
}
```

Response: `TaskCommentSerializer`.

## 13. Knowledge API

Base path: `/api/v1/knowledge/`

### Endpoints

| Endpoint | Назначение |
| --- | --- |
| `/categories/` | Категории базы знаний |
| `/articles/` | Статьи |
| `/articles/{id}/mark-read/` | Отметить статью прочитанной |
| `/articles/{id}/publish/` | Опубликовать, только admin |
| `/articles/{id}/archive/` | Архивировать, только admin |
| `/attachments/` | Вложения статей |
| `/tests/` | Тесты |
| `/tests/{id}/start/` | Начать попытку |
| `/tests/{id}/submit/` | Отправить ответы |
| `/questions/` | Вопросы |
| `/attempts/` | Попытки |
| `/attempts/{id}/submit/` | Отправить ответы по попытке |
| `/read-logs/` | Логи чтения, read-only |

### Фильтры

```text
?company=1
?office=1
?category=2
?article=3
?test=4
?status=published
?is_active=true
?is_public=true
?is_featured=true
?is_required=true
?is_passed=false
?search=visa
```

### Отметить статью прочитанной

```http
POST /api/v1/knowledge/articles/15/mark-read/
```

Response:

```json
{
  "id": 33,
  "article_title": "How to prepare documents",
  "user_name": "Ali Manager",
  "read_count": 2,
  "last_read_at": "2026-05-22T15:40:00+05:00",
  "article": 15,
  "user": 12
}
```

### Начать тест

```http
POST /api/v1/knowledge/tests/4/start/
```

Response:

```json
{
  "id": 18,
  "test_title": "Visa process test",
  "status": "in_progress",
  "started_at": "2026-05-22T15:42:00+05:00",
  "answers": {},
  "score_points": 0,
  "max_points": 10,
  "score_percent": "0.00",
  "is_passed": false,
  "test": 4,
  "user": 12
}
```

### Отправить тест

```http
POST /api/v1/knowledge/tests/4/submit/
```

Request:

```json
{
  "attempt": 18,
  "answers": {
    "101": "a",
    "102": ["a", "c"],
    "103": "Free text answer"
  }
}
```

Response: `KnowledgeTestAttemptSerializer`.

## 14. Custom Fields API

Base path: `/api/v1/customfields/`

### Endpoints

| Endpoint | Назначение |
| --- | --- |
| `/fields/` | Описания кастомных полей |
| `/options/` | Опции select/multi-select |
| `/values/` | Значения кастомных полей для конкретных объектов |

### Фильтры

```text
fields:  ?company=1&office=1&entity_key=crm.client&field_type=select&is_active=true&is_public=true&search=passport
options: ?field=3&is_active=true
values:  ?company=1&office=1&field=3&content_type=crm.client&object_id=55&search=value
```

### Как использовать в мобильном приложении

1. Для формы клиента запросить поля:

```http
GET /api/v1/customfields/fields/?entity_key=crm.client&is_active=true&is_public=true
```

2. Если поле типа `select` или `multi_select`, взять его `options`.
3. При сохранении значения отправить:

```json
{
  "field": 3,
  "company": 1,
  "office": 1,
  "content_type": 42,
  "object_id": 55,
  "value": {
    "value": "yes"
  }
}
```

Важно: сейчас `content_type` это id Django ContentType. Для мобильного wrapper позже лучше сделать endpoint, который принимает `entity_key` строкой, чтобы не заставлять приложение знать ContentType id.

## 15. Notifications API

Base path: `/api/v1/notifications/`

### Endpoints

| Endpoint | Назначение |
| --- | --- |
| `/` | Уведомления текущего пользователя |
| `/{id}/mark-read/` | Отметить одно уведомление прочитанным |
| `/mark-all-read/` | Отметить все прочитанными |
| `/send-test/` | Создать тестовое уведомление |
| `/device-tokens/` | CRUD device tokens |
| `/device-tokens/register/` | Зарегистрировать push token |
| `/device-tokens/unregister/` | Отключить push token |
| `/templates/` | Шаблоны уведомлений |
| `/logs/` | Логи отправки, read-only |

### Фильтры

```text
notifications: ?unread=true&type=task&channel=in_app&status=sent&search=payment
device-tokens: ?platform=ios&is_active=true
logs:          ?notification=10&channel=push&status=failed
```

### Register device token

```http
POST /api/v1/notifications/device-tokens/register/
```

Request:

```json
{
  "token": "expo-or-firebase-device-token",
  "platform": "ios",
  "device_name": "iPhone 15",
  "app_version": "1.0.0",
  "locale": "ru",
  "timezone": "Asia/Ashgabat"
}
```

Response `201`:

```json
{
  "id": 6,
  "user_name": "Ali Manager",
  "token": "expo-or-firebase-device-token",
  "platform": "ios",
  "device_name": "iPhone 15",
  "app_version": "1.0.0",
  "locale": "ru",
  "timezone": "Asia/Ashgabat",
  "is_active": true,
  "last_seen_at": "2026-05-22T15:45:00+05:00",
  "user": 12,
  "company": 1,
  "office": 1
}
```

### Unregister device token

```http
POST /api/v1/notifications/device-tokens/unregister/
```

Request:

```json
{
  "token": "expo-or-firebase-device-token"
}
```

Response:

```json
{
  "detail": "Device token disabled."
}
```

### List notifications

```http
GET /api/v1/notifications/?unread=true&limit=20
```

Response:

```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 20,
      "title": "Payment confirmed",
      "body": "Payment #44 was confirmed.",
      "notification_type": "payment",
      "channel": "in_app",
      "priority": "normal",
      "status": "sent",
      "is_read": false,
      "data": {
        "payment_id": 44
      },
      "target_url": "/portal/finance/",
      "created_at": "2026-05-22T15:50:00+05:00"
    }
  ]
}
```

## 16. Mobile app recommended startup flow

### First launch

1. `GET /api/health/`
2. Show login screen.
3. `POST /api/auth/login/`
4. Save `access` and `refresh`.
5. `GET /api/app/config/`
6. Register push token:

```http
POST /api/v1/notifications/device-tokens/register/
```

### Every app open

1. Try `GET /api/app/config/`.
2. If `401`, call `/api/auth/refresh/`.
3. Load dashboard data:
   - temporary: `GET /api/app/dashboard/`;
   - later: `/api/v1/dashboard/` from `apps/mobile_api`.
4. Load workday:

```http
GET /api/v1/attendance/workdays/today/
```

5. Load unread notifications:

```http
GET /api/v1/notifications/?unread=true&limit=20
```

### CRM client flow

1. Create lead:

```http
POST /api/v1/crm/leads/
```

2. Convert lead:

```http
POST /api/v1/crm/leads/{lead_id}/convert/
```

3. Create application:

```http
POST /api/v1/crm/applications/
```

4. Create deal:

```http
POST /api/v1/finance/deals/
```

5. Add payment:

```http
POST /api/v1/finance/payments/
```

6. Admin confirms payment:

```http
POST /api/v1/finance/payments/{payment_id}/confirm/
```

### Document flow

1. Get templates:

```http
GET /api/v1/documents/templates/?is_active=true
```

2. Generate document:

```http
POST /api/v1/documents/templates/{template_id}/generate/
```

3. Submit/approve/reject depending on role:

```http
POST /api/v1/documents/generated/{document_id}/submit-for-approval/
POST /api/v1/documents/generated/{document_id}/approve/
POST /api/v1/documents/generated/{document_id}/reject/
```

4. Download when allowed:

```http
GET /api/v1/documents/generated/{document_id}/download-approved/
```

## 17. Field reference

Ниже перечислены основные поля сериализаторов. Поля `*_name`, `*_display`, `*_url`, counters и timestamps обычно read-only.

### CRM

```text
LeadSource:
id, created_at, updated_at, is_active, name, code, description

Lead:
id, source_name, manager_name, company_name, office_name, created_at, updated_at,
full_name, phone, email, country, city, direction, interested_country,
interested_program, status, comment, submitter_ip, submitter_user_agent,
submitter_referer, converted_at, company, office, source, manager

Client:
id, manager_name, company_name, office_name, status_display, created_at, updated_at,
full_name, phone, email, dob, citizenship, city, address, address_registration,
passport_local_num, passport_inter_num, passport_issued_by, passport_issued_date,
status, is_priority, is_partner_client, partner_name, comments, custom_data,
company, office, manager, source_lead, shared_with

Application:
id, client_name, manager_name, status_display, created_at, updated_at,
university_name, program_name, country, degree, language, intake, status,
submitted_at, decision_at, comment, custom_data, client, company, office, manager

ClientActivity:
id, client_name, manager_name, activity_type_display, created_at, updated_at,
activity_type, title, description, due_at, completed_at, client, manager

ClientNote:
id, client_name, author_name, created_at, updated_at, text, is_private, client, author

ClientFile:
id, client_name, uploaded_by_name, file_url, created_at, updated_at, title, file,
file_type, comment, client, application, uploaded_by
```

### Education

```text
Country:
id, created_at, updated_at, is_active, sort_order, name, code, flag, description

City:
id, country_name, created_at, updated_at, is_active, sort_order, name, description, country

Currency:
id, created_at, updated_at, code, name, symbol, rate_to_usd

University:
id, country_name, city_name, currency_code, programs_count, contacts,
required_documents, created_at, updated_at, is_active, name, legal_name, logo,
cover_image, website, email, phone, address, description, admission_requirements,
invitation_info, dormitory_info, expenses_info, age_limit, commission_info,
custom_data, company, country, city, local_currency, added_by

Program:
id, university_name, country_name, degree_display, fees, intakes,
required_documents, created_at, updated_at, is_active, name, degree, faculty,
language, duration, description, admission_requirements, is_archived,
custom_data, university
```

### Services

```text
ServiceCategory:
id, company_name, created_at, updated_at, is_active, sort_order, name, code,
description, company

Service:
id, company_name, category_name, currency_code, currency_symbol, prices,
created_at, updated_at, is_active, sort_order, title, code, description,
price_client, is_public, custom_data, company, category, currency

ServicePrice:
id, service_title, currency_code, currency_symbol, created_at, updated_at,
price_client, valid_from, valid_to, notes, service, currency
```

### Finance

```text
Cashbox:
id, company_name, office_name, currency_code, created_at, updated_at, is_active,
name, balance, company, office, currency

Deal:
id, company_name, office_name, client_name, manager_name, service_title,
currency_code, deal_type_display, payment_status_display, created_at, updated_at,
deal_type, university_name, program_name, title, price_client,
expected_revenue_usd, total_to_pay_usd, paid_amount_usd, payment_status,
comment, custom_data, company, office, client, application, manager, service,
currency

Payment:
id, company_name, office_name, deal_title, client_name, manager_name, cashbox_name,
currency_code, method_display, confirmed_by_name, created_at, updated_at, amount,
exchange_rate, amount_usd, method, payment_date, is_confirmed, confirmed_at,
comment, company, office, deal, client, manager, cashbox, currency, confirmed_by

Expense:
id, company_name, office_name, category_name, employee_name, cashbox_name,
currency_code, confirmed_by_name, created_at, updated_at, title, amount,
exchange_rate, amount_usd, date, is_confirmed, confirmed_at, comment, company,
office, category, employee, cashbox, currency, confirmed_by
```

### Documents

```text
DocumentTemplate:
id, company_name, created_by_name, fields_config, file_url, created_at,
updated_at, is_active, name, code, description, file, requires_approval,
company, created_by

GeneratedDocument:
id, company_name, office_name, template_name, client_name, application_title,
deal_title, manager_name, approved_by_name, status_display, approval,
generated_file_url, approved_file_url, can_download_original,
can_download_approved, can_download, created_at, updated_at, title,
context_data, status, generated_file, approved_file, generation_error,
submitted_at, generated_at, approved_at, company, office, template, client,
application, deal, manager, approved_by
```

### Attendance

```text
WorkDay:
id, company_name, office_name, employee_name, status_display, total_work_hours,
has_report, sessions, daily_report, created_at, updated_at, date, status,
started_at, closed_at, auto_closed_at, total_work_seconds, report_required,
comment, custom_data, company, office, employee

DailyReport:
id, company_name, office_name, employee_name, workday_status, created_at,
updated_at, date, content, results, plans, problems, leads_processed,
deals_closed, comment, submitted_at, workday, company, office, employee
```

### Projects

```text
Project:
id, company_name, office_name, created_by_data, owner_data, participants_data,
responsible_users_data, status_display, tasks_count, completed_tasks_count,
progress_percent, sections, notes, created_at, updated_at, is_active, title,
code, description, status, deadline, is_pinned, custom_data, company, office,
created_by, owner, participants, responsible_users

ProjectTask:
id, assigned_to_data, created_by_data, completed_by_data, project_title,
section_title, status_display, priority_display, comments_count,
attachments_count, watchers_count, checklists, watchers, created_at, updated_at,
sort_order, title, description, status, priority, deadline, completed_at,
custom_data, project, section, parent, assigned_to, created_by, completed_by
```

### Knowledge

```text
KnowledgeArticle:
id, company_name, office_name, category_name, author_name, status_display,
attachments_count, tests_count, attachments, tests, created_at, updated_at,
is_active, title, slug, summary, content, status, tags, is_featured, is_public,
published_at, views_count, custom_data, company, office, category, author,
updated_by

KnowledgeTest:
id, company_name, office_name, article_title, questions_count, max_points,
questions, created_at, updated_at, is_active, title, description, pass_percent,
max_attempts, time_limit_minutes, is_required, is_public, custom_data, company,
office, article, created_by

KnowledgeTestAttempt:
id, test_title, user_name, status_display, created_at, updated_at, status,
started_at, submitted_at, answers, score_points, max_points, score_percent,
is_passed, test, user
```

### Notifications

```text
DeviceToken:
id, user_name, company_name, office_name, created_at, updated_at, is_active,
token, platform, device_name, app_version, locale, timezone, last_seen_at,
company, office, user

Notification:
id, company_name, office_name, recipient_name, sender_name, template_name,
status_display, type_display, channel_display, priority_display, is_read, logs,
created_at, updated_at, notification_type, channel, priority, status, title,
body, data, target_url, object_id, queued_at, sent_at, read_at, failed_at,
error_message, company, office, recipient, sender, template, content_type
```

## 18. Status and choice values

### CRM

```text
Lead.status: new, contacted, qualified, converted, lost, spam
Lead.direction: admission, visa, translation, tickets, work_visa, other
Client.status: new, consultation, documents, application, invitation, visa,
arrived, success, rejected, archive
Application.status: draft, documents, submitted, in_review, accepted,
invitation, visa, enrolled, rejected, cancelled
ClientActivity.activity_type: call, message, meeting, note, status_change,
document, payment
```

### Finance

```text
Deal.deal_type: university, service, other
Deal.payment_status: new, paid_partial, paid_full, refunded, cancelled
Payment.method: cash, card, bank, transfer, online, other
Transaction.transaction_type: income, expense, payment, transfer_in,
transfer_out, correction
EmployeeCommission.status: pending, approved, paid, cancelled
FinancialPeriod.status filter: open, closed
```

### Attendance

```text
WorkDay.status: not_started, started, report_submitted, closed, auto_closed, missed
```

### Notifications

```text
DeviceToken.platform: ios, android, web, unknown
Notification.notification_type: attendance, task, document, payment, system, knowledge
Notification.channel: in_app, push, email
Notification.priority: low, normal, high, urgent
Notification.status: new, queued, sent, read, failed, cancelled
NotificationLog.status: pending, success, failed, skipped
```

## 19. Что лучше добавить в Sprint 11 `apps.mobile_api`

Для React Native будет удобнее сделать thin wrapper поверх текущих модулей:

```text
POST /api/v1/auth/login/
POST /api/v1/auth/refresh/
GET  /api/v1/me/
GET  /api/v1/dashboard/
GET  /api/v1/mobile/bootstrap/
GET  /api/v1/mobile/search/?q=ali
```

Рекомендуемый `GET /api/v1/mobile/bootstrap/`:

```json
{
  "user": {},
  "permissions": {},
  "company": {},
  "office": {},
  "workday": {},
  "unread_notifications_count": 3,
  "dictionaries": {
    "lead_statuses": [],
    "client_statuses": [],
    "payment_methods": []
  }
}
```

Так мобильное приложение сможет стартовать одним запросом, а текущие `/api/v1/...` endpoints останутся стабильной базой.
