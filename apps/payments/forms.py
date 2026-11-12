from django import forms

from .models import Payment


class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ('client', 'amount', 'photo', 'note')
        widgets = {
            'client': forms.Select(attrs={'class': 'input', 'data-client-select': '1'}),
            'amount': forms.NumberInput(attrs={'class': 'input', 'min': '0', 'step': '0.01', 'placeholder': 'Сумма оплаты'}),
            'photo': forms.FileInput(attrs={'class': 'input', 'accept': 'image/*'}),
            'note': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Комментарий (необязательно)'}),
        }

    def clean_photo(self):
        photo = self.cleaned_data.get('photo')
        if photo and photo.size > 15 * 1024 * 1024:
            raise forms.ValidationError('Фото больше 15 МБ. Сожмите изображение.')
        return photo
