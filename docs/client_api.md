# Client API ManagerSL

API для будущего клиентского приложения доступно по префиксу:

`https://manager-sl.ru/api/client/v1/`

Эти endpoints предназначены для студентов/клиентов и отдают только публичные данные. Внутренние заметки, commission_info, custom_data, себестоимость услуг, приватные служебные поля и управленческие данные не возвращаются.

## Endpoints

| Endpoint | Описание |
| --- | --- |
| `GET /api/client/v1/countries/` | Активные страны |
| `GET /api/client/v1/cities/` | Активные города |
| `GET /api/client/v1/universities/` | Активные ВУЗы с программами |
| `GET /api/client/v1/universities/{id}/` | Карточка ВУЗа |
| `GET /api/client/v1/programs/` | Активные программы |
| `GET /api/client/v1/programs/{id}/` | Карточка программы |
| `GET /api/client/v1/services/` | Публичные активные услуги |

## Фильтры

Общие:

- `search` или `q` — поиск по названию, стране, городу, описанию.
- `is_active=true` — публичный API всегда возвращает только активные записи.

ВУЗы:

- `country=ID` или `country=Россия`
- `city=ID` или `city=Москва`

Программы:

- `country=ID`
- `city=ID`
- `university=ID`
- `degree=bachelor|master|phd|foundation|language|other`
- `language=english`

Услуги:

- `category=ID` или `category=Визы`
- `search=...`

## Пример ответа ВУЗа

```json
{
  "id": 12,
  "name": "Example University",
  "legal_name": "Example University",
  "country": 1,
  "country_name": "Россия",
  "city": 5,
  "city_name": "Москва",
  "description": "Описание ВУЗа",
  "logo": "https://manager-sl.ru/media/erp/education/university_logos/logo.png",
  "cover": "https://manager-sl.ru/media/erp/education/university_covers/cover.jpg",
  "logo_url": "https://manager-sl.ru/media/erp/education/university_logos/logo.png",
  "cover_image_url": "https://manager-sl.ru/media/erp/education/university_covers/cover.jpg",
  "programs_count": 14,
  "website": "https://example.edu",
  "address": "Москва",
  "admission_requirements": "Условия поступления",
  "invitation_info": "Информация по приглашению",
  "dormitory_info": "Общежитие",
  "expenses_info": "Расходы и проживание",
  "age_limit": "18+",
  "public_contacts": {
    "website": "https://example.edu",
    "email": "info@example.edu",
    "phone": "+79990000000",
    "address": "Москва"
  },
  "programs": [],
  "required_documents": []
}
```

## Пример ответа программы

```json
{
  "id": 24,
  "university": 12,
  "university_name": "Example University",
  "university_logo": "https://manager-sl.ru/media/erp/education/university_logos/logo.png",
  "university_cover": "https://manager-sl.ru/media/erp/education/university_covers/cover.jpg",
  "country": "Россия",
  "city": "Москва",
  "name": "Computer Science",
  "degree": "bachelor",
  "degree_display": "Бакалавриат",
  "faculty": "IT",
  "language": "English",
  "duration": "4 года",
  "description": "Описание программы",
  "admission_requirements": "Требования",
  "fees": [
    {
      "currency": "USD",
      "tuition_fee": "3000.00",
      "service_fee_usd": "500.00"
    }
  ],
  "intakes": [],
  "required_documents": []
}
```

## Изображения стран и городов

`GET /api/client/v1/countries/` дополнительно возвращает:

- `image_url` — абсолютный URL изображения страны, сейчас совпадает с флагом, если флаг загружен;
- `cover_image_url` — абсолютный URL обложки страны, сейчас совпадает с флагом, если флаг загружен;
- `cities_count` — количество активных городов;
- `universities_count` — количество активных ВУЗов.

`GET /api/client/v1/cities/` дополнительно возвращает:

- `image_url`;
- `cover_image_url`;
- `universities_count`.

Если изображения нет, API возвращает `null`. Старые поля не удаляются.

## Что скрыто

API не возвращает:

- `commission_info`;
- внутренние заметки сотрудников;
- `custom_data`;
- `real_cost` и себестоимость услуг;
- автора записи и служебные поля добавления;
- приватные контакты сотрудников/партнёров, если они не вынесены в публичные поля ВУЗа.

## Изображения ВУЗов

Для обратной совместимости API сохраняет старые поля `logo` и `cover`. Новые клиентские приложения могут использовать более явные поля:

- `logo_url` — абсолютный URL логотипа ВУЗа;
- `cover_image_url` — абсолютный URL обложки ВУЗа;
- `programs_count` — количество активных программ ВУЗа;
- `university_logo` — логотип ВУЗа внутри ответа программы;
- `university_cover` — обложка ВУЗа внутри ответа программы.

Если изображение не загружено, поле возвращает `null`. В клиентском приложении в этом случае нужно показывать placeholder.
