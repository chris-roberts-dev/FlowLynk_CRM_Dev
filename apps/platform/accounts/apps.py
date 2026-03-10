from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.platform.accounts"
    label = "platform_accounts"
    verbose_name = "Accounts"
