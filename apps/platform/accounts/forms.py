"""
apps.platform.accounts.forms — Authentication and member management forms.

LoginForm: email + password authentication on the base domain.
TenantMemberAddForm: add a new member to the current org (creates User if needed).
TenantMemberChangeForm: edit an existing member's status.
"""

from django import forms
from django.contrib.auth import authenticate

from apps.platform.accounts.models import MembershipStatus, User


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


# ──────────────────────────────────────────────
# Tenant member management forms
# ──────────────────────────────────────────────
class TenantMemberAddForm(forms.ModelForm):
    """
    ModelForm for tenant admins to add a member to their organization.

    If a User with the given email already exists, they are linked
    to the org via a new Membership. If not, a new User is created
    with the provided name and password.

    Extra fields (email, first_name, last_name, password) handle user
    creation; the model field (status) comes from TenantMember.
    """

    email = forms.EmailField(
        help_text="If this email already has a FlowLynk account, they'll be added to your organization.",
    )
    first_name = forms.CharField(
        max_length=150,
        required=False,
        help_text="Only used when creating a new user account.",
    )
    last_name = forms.CharField(
        max_length=150,
        required=False,
        help_text="Only used when creating a new user account.",
    )
    password = forms.CharField(
        widget=forms.PasswordInput,
        required=False,
        help_text="Set a password for new accounts. Leave blank if the user already exists.",
    )

    class Meta:
        from apps.platform.accounts.models import TenantMember

        model = TenantMember
        fields = ["status"]

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get("email")

        if email:
            existing_user = User.objects.filter(email__iexact=email).first()
            if existing_user is None:
                if not cleaned_data.get("password"):
                    self.add_error(
                        "password",
                        "Password is required when creating a new user account.",
                    )
            self._existing_user = existing_user
        else:
            self._existing_user = None
        return cleaned_data

    def get_or_create_user(self):
        """Return the User (existing or newly created)."""
        email = self.cleaned_data["email"]

        if self._existing_user is not None:
            return self._existing_user

        return User.objects.create_user(
            email=email,
            password=self.cleaned_data["password"],
            first_name=self.cleaned_data.get("first_name", ""),
            last_name=self.cleaned_data.get("last_name", ""),
        )


class TenantMemberChangeForm(forms.ModelForm):
    """
    Form for editing an existing member in the tenant context.

    Shows user info as read-only and allows editing membership status.
    """

    # Read-only display fields pulled from the related User
    email = forms.EmailField(disabled=True, required=False)
    first_name = forms.CharField(disabled=True, required=False)
    last_name = forms.CharField(disabled=True, required=False)

    class Meta:
        from apps.platform.accounts.models import TenantMember

        model = TenantMember
        fields = ["status"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["email"].initial = self.instance.user.email
            self.fields["first_name"].initial = self.instance.user.first_name
            self.fields["last_name"].initial = self.instance.user.last_name
