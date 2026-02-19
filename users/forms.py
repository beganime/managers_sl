from django import forms
from django.contrib.auth.forms import UserCreationForm as BaseUserCreationForm, UserChangeForm as BaseUserChangeForm
from .models import User

class UserCreationForm(BaseUserCreationForm):
    # Явно указываем виджеты для обоих полей, чтобы они были скрыты точками
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
        fields = ('email', 'first_name', 'last_name', 'office') 

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")
        if password and confirm_password and password != confirm_password:
            raise forms.ValidationError("Пароли не совпадают")
        return cleaned_data
    
    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
        if commit:
            user.save()
        return user

class UserChangeForm(BaseUserChangeForm):
    class Meta:
        model = User
        fields = '__all__'