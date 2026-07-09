from django.test import TestCase
from rest_framework.test import APIClient


class AuthFlowTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_register_login_me(self):
        r = self.client.post(
            "/api/auth/register/",
            {"username": "aisha", "email": "aisha@x.com", "password": "flat12345"},
            format="json",
        )
        self.assertEqual(r.status_code, 201)

        r = self.client.post(
            "/api/auth/login/",
            {"username": "aisha", "password": "flat12345"},
            format="json",
        )
        self.assertEqual(r.status_code, 200)
        access = r.json()["access"]
        self.assertIn("refresh", r.json())

        r = self.client.get(
            "/api/auth/me/", HTTP_AUTHORIZATION=f"Bearer {access}"
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["username"], "aisha")

    def test_me_requires_auth(self):
        r = self.client.get("/api/auth/me/")
        self.assertEqual(r.status_code, 401)

    def test_login_rejects_wrong_password(self):
        self.client.post(
            "/api/auth/register/",
            {"username": "rohan", "email": "rohan@x.com", "password": "flat12345"},
            format="json",
        )
        r = self.client.post(
            "/api/auth/login/",
            {"username": "rohan", "password": "wrong-password"},
            format="json",
        )
        self.assertEqual(r.status_code, 401)

    def test_duplicate_username_rejected(self):
        payload = {"username": "priya", "email": "priya@x.com", "password": "flat12345"}
        r1 = self.client.post("/api/auth/register/", payload, format="json")
        self.assertEqual(r1.status_code, 201)
        r2 = self.client.post(
            "/api/auth/register/",
            {**payload, "email": "priya2@x.com"},
            format="json",
        )
        self.assertEqual(r2.status_code, 400)

    def test_duplicate_email_rejected(self):
        # email is unique=True on the custom User model.
        self.client.post(
            "/api/auth/register/",
            {"username": "meera", "email": "dup@x.com", "password": "flat12345"},
            format="json",
        )
        r = self.client.post(
            "/api/auth/register/",
            {"username": "meera2", "email": "dup@x.com", "password": "flat12345"},
            format="json",
        )
        self.assertEqual(r.status_code, 400)
