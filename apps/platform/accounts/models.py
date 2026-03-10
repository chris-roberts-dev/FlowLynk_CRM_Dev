"""
apps.platform.accounts.models — Global User and tenant-scoped Membership.

User is the global identity (email-based login).
Membership binds a User to an Organization with status tracking.
"""

from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.db import models

from apps.common.models.base import TimestampedModel


# ──────────────────────────────────────────────
# User manager
# ──────────────────────────────────────────────
class UserManager(BaseUserManager):
    """Custom manager for email-based User model."""

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required.")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self.create_user(email, password, **extra_fields)


# ──────────────────────────────────────────────
# User (global — not tenant-scoped)
# ──────────────────────────────────────────────
class UserStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    LOCKED = "LOCKED", "Locked"
    INVITED = "INVITED", "Invited"


class User(AbstractBaseUser, PermissionsMixin, TimestampedModel):
    """
    Global user identity. Email is the unique identifier.

    NOT tenant-scoped — a single User may have Memberships in multiple
    Organizations.
    """

    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    status = models.CharField(
        max_length=20,
        choices=UserStatus.choices,
        default=UserStatus.ACTIVE,
    )
    is_staff = models.BooleanField(
        default=False,
        help_text="Designates whether the user can access the admin site.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Designates whether this user account is active.",
    )

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []  # email is already required by USERNAME_FIELD

    class Meta:
        ordering = ["email"]

    def __str__(self):
        return self.email

    def get_full_name(self):
        full = f"{self.first_name} {self.last_name}".strip()
        return full or self.email

    def get_short_name(self):
        return self.first_name or self.email.split("@")[0]


# ──────────────────────────────────────────────
# Membership (tenant-scoped join between User ↔ Organization)
# ──────────────────────────────────────────────
class MembershipStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    INACTIVE = "INACTIVE", "Inactive"


class Membership(TimestampedModel):
    """
    Binds a User to an Organization.

    Multi-membership is supported: one User may belong to multiple Orgs.
    Each Membership carries its own status and is the anchor for
    RBAC grants (MembershipRole) and audit trails.
    """

    user = models.ForeignKey(
        "platform_accounts.User",
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    organization = models.ForeignKey(
        "platform_organizations.Organization",
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    status = models.CharField(
        max_length=20,
        choices=MembershipStatus.choices,
        default=MembershipStatus.ACTIVE,
        db_index=True,
    )
    last_login_at = models.DateTimeField(null=True, blank=True)
    default_location = models.ForeignKey(
        "crm_locations.Location",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Optional default location context for this member.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "organization"],
                name="uq_membership_user_org",
            ),
        ]
        indexes = [
            models.Index(
                fields=["organization", "status"],
                name="idx_membership_org_status",
            ),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.email} @ {self.organization.slug} ({self.status})"

    @property
    def is_active(self):
        return self.status == MembershipStatus.ACTIVE


class TenantMember(Membership):
    """
    Proxy model for tenant-facing member management.

    This gives tenant admins their own "Members" entry in the admin
    (under CRM) separate from the platform-level Membership admin.
    No new database table is created.
    """

    class Meta:
        proxy = True
        verbose_name = "Member"
        verbose_name_plural = "Members"
