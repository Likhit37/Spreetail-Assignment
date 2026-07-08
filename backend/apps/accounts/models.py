from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Custom user so we can extend auth later without a painful migration.

    A User is a login account. It is distinct from a Member (a person who
    appears in a group's expenses) — the same human may exist as a Member
    long before they ever hold a login. See apps.expenses.models.Member.
    """

    email = models.EmailField(unique=True)

    def __str__(self) -> str:
        return self.username
