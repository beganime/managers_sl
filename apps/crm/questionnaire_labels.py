QUESTIONNAIRE_VALUE_LABELS = {
    'male': 'Мужской',
    'female': 'Женский',
    'school_student': 'Школьник / предварительная заявка',
    'applicant': 'Абитуриент / полная анкета',
    'express': 'Экспресс-заявка',
    'full': 'Полная анкета',
    'government': 'Гослиния',
    'budget': 'Бюджет',
    'contract': 'Контракт',
    'medical': 'Медик',
    'single': 'Не состоит в браке',
    'married': 'Состоит в браке',
    'divorced': 'Разведён(а)',
    'widowed': 'Вдовец / вдова',
    'phone': 'Телефон',
    'telegram': 'Telegram',
    'imo': 'Imo',
    'email': 'Email',
    True: 'Да',
    False: 'Нет',
}


QUESTIONNAIRE_DOCUMENT_LABELS = {
    'form_type': 'Тип заявки', 'application_type': 'Тип заявки',
    'stage': 'Этап заполнения', 'academic_year': 'Год поступления',
    'full_name': 'ФИО', 'birth_date': 'Дата рождения',
    'date_of_birth': 'Дата рождения', 'gender': 'Пол',
    'is_conscript': 'Призывник', 'citizenship': 'Гражданство',
    'marital_status': 'Семейное положение',
    'face_photo_url': 'Фотография абитуриента',
    'residence_country': 'Страна проживания',
    'residence_region': 'Область / регион',
    'residence_city': 'Город / населённый пункт',
    'residence_street': 'Улица', 'residence_house': 'Дом / квартира',
    'residence_postal_code': 'Почтовый индекс',
    'current_residence': 'Где проживает сейчас',
    'current_location': 'Где находится сейчас',
    'passport_number': 'Загранпаспорт: серия и номер',
    'passport_issued_by': 'Где оформлен паспорт',
    'passport_issue_date': 'Дата начала действия паспорта',
    'passport_expiry_date': 'Дата окончания действия паспорта',
    'has_international_passport': 'Действующий загранпаспорт',
    'passport_pending': 'Паспорт оформляется',
    'phone': 'Основной номер телефона', 'email': 'Email',
    'extra_phone': 'Дополнительный номер телефона', 'imo': 'Imo',
    'telegram': 'Telegram', 'messenger': 'Мессенджер',
    'preferred_contact_method': 'Предпочтительный способ связи',
    'parent_full_name': 'ФИО родителя / представителя',
    'parent_name': 'ФИО родителя / представителя',
    'parent_relation': 'Кем является родитель / представитель',
    'parent_contacts': 'Контакты родителя / представителя',
    'parent_phone': 'Телефон родителя / представителя',
    'parent_messenger': 'Мессенджер родителя / представителя',
    'parent_workplace': 'Место работы родителя / представителя',
    'family_members': 'Состав семьи',
    'education_level': 'Уровень образования', 'school_class': 'Класс',
    'school_name': 'Учебное заведение',
    'school_country': 'Страна учебного заведения',
    'school_city': 'Город учебного заведения',
    'graduation_year': 'Год окончания',
    'education_status': 'Текущий статус образования',
    'achievements': 'Достижения', 'languages': 'Языки',
    'language': 'Язык', 'level': 'Уровень владения',
    'desired_universities': 'Желаемые вузы',
    'university_choices': 'Выбранные вузы и программы',
    'university_name': 'Вуз', 'programs': 'Программы', 'name': 'Название',
    'desired_program': 'Желаемые направления',
    'admission_goal': 'Цель поступления',
    'desired_city': 'Желаемый город поступления',
    'desired_country': 'Желаемая страна поступления',
    'desired_language': 'Желаемый язык обучения',
    'desired_education_level': 'Желаемый уровень обучения',
    'admission_urgency': 'Срочность поступления',
    'funding_type': 'Форма поступления',
    'requested_services': 'Нужные услуги', 'help_needed': 'Нужна помощь с',
    'request_text': 'Что хочет клиент',
    'has_visa': 'Есть действующая виза',
    'visa_country': 'Страна оформления визы',
    'visa_city': 'Город оформления визы',
    'visa_valid_until': 'Срок действия визы',
    'hobbies': 'Хобби', 'applicant_comment': 'Комментарий абитуриента',
    'comment': 'Комментарий', 'note': 'Замечание',
    'referral_source': 'Откуда узнали о Student’s Life',
    'data_processing_consent': 'Согласие на обработку персональных данных',
    'documents_uploaded': 'Документы загружены',
    'status': 'Статус анкеты', 'submitted_at': 'Дата отправки анкеты',
    'generated_document_url': 'Документ анкеты',
    'generated_document_at': 'Дата формирования документа',
}


QUESTIONNAIRE_INTERNAL_FIELDS = {
    'id', 'public_id', 'client_id', 'user_id', 'source', 'fcm_token',
    'document_file', 'generated_document', 'generated_document_url',
    'generated_document_at', 'missing_required_fields',
    'missing_required_field_labels', 'reviewed_at', 'reviewed_by',
    'reviewed_by_display', 'reviewed_by_name', 'reviewed_by_email',
    'review_comment', 'updated_at', 'created_at', 'attachments',
}


def questionnaire_field_label(field):
    """Return a Russian UI label without exposing an API variable name."""
    return QUESTIONNAIRE_DOCUMENT_LABELS.get(str(field), 'Дополнительное поле')


def questionnaire_value_label(value):
    try:
        return QUESTIONNAIRE_VALUE_LABELS.get(value, value)
    except TypeError:
        return value
