from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from accounts.models import Role

User = get_user_model()

DEFAULT_USERS = [
    ('salesman', 'salesman123', Role.SALESMAN, 'Field Salesman A'),
    ('admin', 'admin123', Role.ADMIN, 'Factory Admin User'),
    ('production', 'production123', Role.PRODUCTION, 'Production Floor Supervisor'),
    ('accountant', 'accountant123', Role.ACCOUNTANT, 'Auditor & Accountant User'),
    ('owner', 'owner123', Role.OWNER, 'Business Owner User'),
]


class Command(BaseCommand):
    help = 'Seeds initial test users for each business role'

    def handle(self, *args, **options):
        for username, password, role, full_name in DEFAULT_USERS:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={'role': role, 'first_name': full_name}
            )
            user.role = role
            user.set_password(password)
            user.save()
            action = 'Created' if created else 'Updated'
            self.stdout.write(self.style.SUCCESS(f"{action} user '{username}' with role '{role}'"))
