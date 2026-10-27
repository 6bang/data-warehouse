import os

from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.warehouse.models import AccountProfile


class Command(BaseCommand):
    help = "Create an initial administrator using an explicit ADMIN_PASSWORD; never reset existing passwords"

    @transaction.atomic
    def handle(self, *args, **options):
        username = os.getenv("ADMIN_USERNAME", "admin").strip()
        if not username:
            raise CommandError("ADMIN_USERNAME cannot be empty.")
        user = User.objects.filter(username=username).first()
        if user:
            if not user.is_superuser:
                raise CommandError("ADMIN_USERNAME already belongs to a non-administrator; no changes made.")
            self.stdout.write("Administrator already exists; password and account unchanged.")
            return
        password = os.getenv("ADMIN_PASSWORD", "")
        if not password:
            self.stdout.write(self.style.WARNING("Skipped administrator creation: set ADMIN_PASSWORD or run createsuperuser."))
            return
        try:
            validate_password(password, User(username=username))
        except ValidationError as exc:
            raise CommandError("ADMIN_PASSWORD is not strong enough: " + " ".join(exc.messages)) from exc
        user = User.objects.create_superuser(username=username, password=password)
        AccountProfile.objects.update_or_create(
            user=user,
            defaults={
                "role": AccountProfile.Role.ADMIN,
                "approval_status": AccountProfile.ApprovalStatus.APPROVED,
            },
        )
        self.stdout.write(self.style.SUCCESS(f"Administrator {username} created"))
