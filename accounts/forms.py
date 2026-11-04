from django import forms
from django.contrib.auth import password_validation
from .models import User


class RegistrationForm(forms.Form):
    email = forms.EmailField(max_length=254)
    full_name = forms.CharField(max_length=150)
    location = forms.CharField(max_length=150, required=False)
    password = forms.CharField(widget=forms.PasswordInput)
    password_confirm = forms.CharField(widget=forms.PasswordInput)

    def clean_email(self):
        email = self.cleaned_data["email"].strip().casefold()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("This email already has an account. Sign in to enable another role.")
        return email

    def clean(self):
        data = super().clean()
        if data.get("password") != data.get("password_confirm"):
            self.add_error("password_confirm", "Passwords do not match.")
        if data.get("password"):
            password_validation.validate_password(data["password"], User(email=data.get("email", ""), full_name=data.get("full_name", "")))
        return data


class LoginForm(forms.Form):
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)
