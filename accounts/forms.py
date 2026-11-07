from django import forms
from django.contrib.auth import password_validation
from .models import User


def validate_private_contact(value):
    import re
    if "@" in value:
        forms.EmailField().clean(value)
    elif not re.fullmatch(r"\+?[0-9 ()-]{7,30}", value) or len(re.sub(r"\D", "", value)) < 7:
        raise forms.ValidationError("Enter a valid contact email or phone number.")



class RegistrationForm(forms.Form):
    email = forms.EmailField(max_length=254, widget=forms.EmailInput(attrs={"autocomplete": "email"}))
    full_name = forms.CharField(max_length=150, required=False, widget=forms.TextInput(attrs={"autocomplete": "name"}))
    location = forms.CharField(max_length=150, required=False)
    password = forms.CharField(widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}), help_text="At least 12 characters; avoid common passwords and personal details.")
    password_confirm = forms.CharField(widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))

    def __init__(self, *args, seller=False, **kwargs):
        super().__init__(*args, **kwargs)
        if seller:
            profile = SellerOnboardingForm()
            self.fields.update(profile.fields)
        else:
            self.fields.pop("location")
            self.fields.pop("full_name")

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
    email = forms.EmailField(widget=forms.EmailInput(attrs={"autocomplete": "username"}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}))


class SellerOnboardingForm(forms.Form):
    full_name = forms.CharField(max_length=150, label="Seller name", help_text="The name buyers see on your listings.")
    location = forms.CharField(max_length=150, help_text="City or service area for arranging delivery; no street address needed.")
    private_contact = forms.CharField(max_length=100, validators=[validate_private_contact], help_text="A private email or phone for account support. Not displayed on public listings.")


class ProfileForm(forms.Form):
    full_name = forms.CharField(max_length=150, label="Display name")
    location = forms.CharField(max_length=150, required=False, help_text="City or area only; avoid your street address.")
    private_contact = forms.CharField(max_length=100, required=False, validators=[validate_private_contact],
                                     help_text="Private support email or phone; never shown on public listings.")

    def __init__(self, *args, seller=False, **kwargs):
        super().__init__(*args, **kwargs)
        if seller:
            self.fields["location"].required = True
            self.fields["private_contact"].required = True
