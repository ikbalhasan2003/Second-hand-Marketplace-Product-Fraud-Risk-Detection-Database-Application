from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin, Group, Permission
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra):
        user = self.model(email=email.strip().casefold(), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra):
        raise ValueError("Use provision_admin; administrator membership is separately controlled.")


class User(AbstractBaseUser, PermissionsMixin):
    user_id = models.BigAutoField(primary_key=True)
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=150)
    location = models.CharField(max_length=150, null=True, blank=True)
    private_contact = models.CharField(max_length=100, null=True, blank=True)
    status = models.CharField(max_length=16, default="active")
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    deactivated_at = models.DateTimeField(null=True, blank=True)
    groups = models.ManyToManyField(Group, db_table="users_groups", blank=True, related_name="user_set", related_query_name="user")
    user_permissions = models.ManyToManyField(Permission, db_table="users_user_permissions", blank=True, related_name="user_set", related_query_name="user")
    objects = UserManager()
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        db_table = "users"
        constraints = [models.UniqueConstraint(Lower("email"), name="users_email_ci_uq")]

    def __str__(self):
        return self.full_name


class AdministratorTransition(models.Model):
    created_at = models.DateTimeField(default=timezone.now)
    target = models.ForeignKey(User, on_delete=models.PROTECT)
    previous_admin_ids = models.JSONField(default=list)
    reason = models.TextField()

    class Meta:
        db_table = "administrator_transitions"
