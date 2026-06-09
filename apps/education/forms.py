from django import forms


class ProgramJsonImportForm(forms.Form):
    json_file = forms.FileField(
        label='JSON-файл с программами',
        help_text='Загрузите файл .json до 10 MB. Поддерживается JSON-массив или несколько объектов через запятую без внешних квадратных скобок.',
    )
    dry_run = forms.BooleanField(
        label='Тестовый импорт / dry-run',
        required=False,
        initial=True,
        help_text='Если включено, система только проверит файл и покажет отчёт, но ничего не создаст и не обновит.',
    )
    update_existing = forms.BooleanField(
        label='Обновлять существующие программы',
        required=False,
        initial=True,
        help_text='Если программа уже найдена по ВУЗу, названию, степени и длительности, обновить статус и стоимость.',
    )

    def clean_json_file(self):
        uploaded_file = self.cleaned_data['json_file']
        max_size = 10 * 1024 * 1024
        if uploaded_file.size > max_size:
            raise forms.ValidationError('Файл слишком большой. Максимальный размер: 10 MB.')
        if not uploaded_file.name.lower().endswith('.json'):
            raise forms.ValidationError('Загрузите файл с расширением .json.')
        return uploaded_file
