"""
Tests for login / logout functionality.

These tests use Django's built-in auth views (django.contrib.auth.urls),
which are mounted at /accounts/ in urls.py. No custom view code is needed —
these tests verify that the wiring, templates, and redirects all behave correctly.
"""

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


class LoginPageTest(TestCase):

    def test_login_page_returns_200(self):
        """GET /accounts/login/ should return a 200 OK response."""
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)

    def test_login_page_uses_correct_template(self):
        """The login view should render registration/login.html."""
        response = self.client.get(reverse("login"))
        self.assertTemplateUsed(response, "registration/login.html")

    def test_login_page_contains_form(self):
        """The login page should contain a <form> element."""
        response = self.client.get(reverse("login"))
        self.assertContains(response, "<form")

    def test_login_page_shows_log_in_heading(self):
        """The login page should display a 'Log In' heading."""
        response = self.client.get(reverse("login"))
        self.assertContains(response, "Log In")


class LoginFlowTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser",
            password="securepass123",
        )

    def test_valid_credentials_redirects_to_home(self):
        """Posting valid credentials should redirect to LOGIN_REDIRECT_URL (/)."""
        response = self.client.post(
            reverse("login"),
            {"username": "testuser", "password": "securepass123"},
        )
        self.assertRedirects(response, "/")

    def test_valid_login_authenticates_user(self):
        """After a successful login the session should contain the user's id."""
        self.client.post(
            reverse("login"),
            {"username": "testuser", "password": "securepass123"},
        )
        # Django stores the user id in the session under _auth_user_id
        self.assertIn("_auth_user_id", self.client.session)

    def test_invalid_password_returns_200_with_error(self):
        """Posting a wrong password should re-render the login page (not redirect)."""
        response = self.client.post(
            reverse("login"),
            {"username": "testuser", "password": "wrongpassword"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "registration/login.html")

    def test_invalid_password_shows_error_message(self):
        """Failed login should display an error message to the user."""
        response = self.client.post(
            reverse("login"),
            {"username": "testuser", "password": "wrongpassword"},
        )
        self.assertContains(response, "didn't match")

    def test_invalid_password_does_not_authenticate(self):
        """A failed login attempt should not create an authenticated session."""
        self.client.post(
            reverse("login"),
            {"username": "testuser", "password": "wrongpassword"},
        )
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_nonexistent_user_returns_error(self):
        """Posting credentials for a user that doesn't exist should re-render login."""
        response = self.client.post(
            reverse("login"),
            {"username": "nobody", "password": "anything"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "registration/login.html")


class LogoutFlowTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser",
            password="securepass123",
        )
        self.client.login(username="testuser", password="securepass123")

    def test_logout_redirects_to_home(self):
        """POST /accounts/logout/ should redirect to LOGOUT_REDIRECT_URL (/)."""
        response = self.client.post(reverse("logout"))
        self.assertRedirects(response, "/")

    def test_logout_clears_session(self):
        """After logout the session should no longer contain the user id."""
        self.assertIn("_auth_user_id", self.client.session)
        self.client.post(reverse("logout"))
        self.assertNotIn("_auth_user_id", self.client.session)


class NavbarAuthLinksTest(TestCase):
    """
    Verify that the base template shows the right nav links depending on
    whether a user is logged in or not.  We use the home page (/) since it
    extends base.html.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="navuser",
            password="securepass123",
        )

    def test_anonymous_user_sees_log_in_link(self):
        """An unauthenticated visitor should see a 'Log In' link in the navbar."""
        response = self.client.get("/")
        self.assertContains(response, "Log In")
        self.assertNotContains(response, "Log Out")

    def test_authenticated_user_sees_log_out_button(self):
        """A logged-in user should see their username and a 'Log Out' button."""
        self.client.login(username="navuser", password="securepass123")
        response = self.client.get("/")
        self.assertContains(response, "Log Out")
        self.assertContains(response, "navuser")
        self.assertNotContains(response, "Log In")
