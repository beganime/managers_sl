from django import forms


class PortalClientQuestionnaireForm(forms.Form):
    full_name = forms.CharField(label='ФИО', max_length=255)
    phone = forms.CharField(label='Телефон', max_length=80)
    email = forms.EmailField(label='Email', required=False)
    birth_date = forms.DateField(label='Дата рождения', required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    citizenship = forms.CharField(label='Гражданство', required=False, initial='Туркменистан')
    gender = forms.ChoiceField(label='Пол', required=False, choices=(('', '—'), ('male', 'Мужской'), ('female', 'Женский')))
    marital_status = forms.ChoiceField(label='Семейное положение', required=False, choices=(('', '—'), ('single', 'Не женат / не замужем'), ('married', 'Женат / замужем')))
    residence_region = forms.ChoiceField(label='Область', required=False, choices=(('', '—'), ('Лебап', 'Лебап'), ('Мары', 'Мары'), ('Ахал', 'Ахал'), ('Дашогуз', 'Дашогуз'), ('Балкан', 'Балкан'), ('Ашхабад', 'Ашхабад')))
    residence_city = forms.CharField(label='Город проживания', required=False)
    passport_number = forms.CharField(label='Номер загранпаспорта', required=False)
    passport_issued_by = forms.CharField(label='Кем выдан', required=False)
    passport_issue_date = forms.DateField(label='Дата выдачи', required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    passport_expiry_date = forms.DateField(label='Срок действия', required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    passport_pending = forms.BooleanField(label='Загранпаспорт отсутствует или оформляется', required=False)
    parent_name = forms.CharField(label='ФИО родителя', required=False)
    parent_relation = forms.CharField(label='Кем является', required=False)
    parent_phone = forms.CharField(label='Телефон родителя', required=False)
    school_name = forms.CharField(label='Школа / учебное заведение', required=False)
    school_country = forms.CharField(label='Страна обучения', required=False, initial='Туркменистан')
    graduation_year = forms.IntegerField(label='Год окончания', required=False, min_value=1980, max_value=2100)
    desired_country = forms.CharField(label='Желаемая страна', required=False)
    desired_city = forms.CharField(label='Желаемый город', required=False)
    desired_program = forms.CharField(label='Вузы и программы', required=False, widget=forms.Textarea(attrs={'rows': 4}))
    comments = forms.CharField(label='Комментарий', required=False, widget=forms.Textarea(attrs={'rows': 4}))

    def __init__(self, *args, questionnaire=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.questionnaire = questionnaire
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'input')
        if questionnaire and not self.is_bound:
            data = questionnaire.data or {}
            for name in self.fields:
                if name in data:
                    self.initial[name] = data[name]
            for name in ('full_name', 'phone', 'email', 'citizenship', 'desired_country', 'desired_city', 'desired_program'):
                value = getattr(questionnaire, name, None)
                if value:
                    self.initial[name] = value

