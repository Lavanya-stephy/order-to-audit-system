from django.contrib.auth.models import AbstractUser
from django.db import models


class Role(models.TextChoices):
    SALESMAN = 'salesman', 'Salesman'
    ADMIN = 'admin', 'Factory Admin'
    PRODUCTION = 'production', 'Production Supervisor'
    ACCOUNTANT = 'accountant', 'Accountant / Auditor (Read-Only)'
    OWNER = 'owner', 'Owner'


class User(AbstractUser):
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.SALESMAN,
        help_text='Operational business role defining access permissions.',
    )
    phone_number = models.CharField(max_length=20, blank=True, default='')

    @property
    def is_salesman(self):
        return self.role == Role.SALESMAN

    @property
    def is_factory_admin(self):
        return self.role == Role.ADMIN or self.is_superuser

    @property
    def is_production(self):
        return self.role == Role.PRODUCTION

    @property
    def is_accountant(self):
        return self.role == Role.ACCOUNTANT

    @property
    def is_owner(self):
        return self.role == Role.OWNER

    def __str__(self):
        return f"{self.username} [{self.get_role_display()}]"
