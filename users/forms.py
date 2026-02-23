# users/forms.py
from django import forms
from django.contrib.auth.forms import UserChangeForm as BaseUserChangeForm
from .models import User

class UserCreationForm(forms.ModelForm):
    password = forms.CharField(
        label="Пароль", 
        widget=forms.PasswordInput(attrs={'class': 'border p-2 w-full rounded'})
    )
    confirm_password = forms.CharField(
        label="Повторите пароль", 
        widget=forms.PasswordInput(attrs={'class': 'border p-2 w-full rounded'})
    )

    class Meta:
        model = User
        # Добавили поля групп и прав доступа в форму создания
        fields = ('email', 'first_name', 'last_name', 'office', 'is_staff', 'is_superuser', 'groups') 

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")
        if password and confirm_password and password != confirm_password:
            self.add_error('confirm_password', "Пароли не совпадают")
        return cleaned_data
    
    def save(self, commit=True):
        user = super().save(commit=False)
        # Хэшируем пароль перед сохранением
        user.set_password(self.cleaned_data["password"])
        if commit:
            user.save()
            # Обязательно для сохранения групп (ManyToMany полей) при создании
            self.save_m2m() 
        return user

class UserChangeForm(BaseUserChangeForm):
    class Meta:
        model = User
        fields = '__all__'