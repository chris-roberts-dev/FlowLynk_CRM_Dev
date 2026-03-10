"""
apps.platform.accounts.forms — Authentication forms.

LoginForm: email + password authentication on the base domain.
"""
from django import forms
from django.contrib.auth import authenticate


class LoginForm(forms.Form):
    """
    Email/password login form served on the base domain.

    After successful authentication, the view resolves the user's
    active memberships and either redirects to the single org or
    presents an org picker.
    """

    email = forms.EmailField(
        widget=forms.EmailInput(
            attrs={
                "class": "form-control form-control-lg",
                "placeholder": "you@company.com",
                "autofocus": True,
            }
        ),
    )
    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control form-control-lg",
                "placeholder": "Password",
            }
        ),
    )

    def __init__(self, *args, request=None, **kwargs):
        self.request = request
        self.user_cache = None
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get("email")
        password = cleaned_data.get("password")

        if email and password:
            self.user_cache = authenticate(
                self.request,
                username=email,  # USERNAME_FIELD is email
                password=password,
            )
            if self.user_cache is None:
                raise forms.ValidationError(
                    "Invalid email or password. Please try again."
                )
            if not self.user_cache.is_active:
                raise forms.ValidationError(
                    "This account has been deactivated. Please contact your administrator."
                )

        return cleaned_data

    def get_user(self):
        return self.user_cache
