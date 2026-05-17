from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .forms import RegistrationForm
from .models import UserProfile


class UserProfileTests(TestCase):

    def test_profile_defaults_both_notify_fields_to_false(self):
        user = User.objects.create_user("testuser", "t@example.com", "Testpass123!")
        profile = UserProfile.objects.create(user=user)
        self.assertFalse(profile.notify_on_article_publish)
        self.assertFalse(profile.notify_on_quiz_publish)

    def test_profile_str_returns_username(self):
        user = User.objects.create_user("testuser", "t@example.com", "Testpass123!")
        profile = UserProfile.objects.create(user=user)
        self.assertEqual(str(profile), "Profile for testuser")

    def test_profile_links_to_user(self):
        user = User.objects.create_user("testuser", "t@example.com", "Testpass123!")
        profile = UserProfile.objects.create(user=user)
        self.assertEqual(profile.user, user)

    def test_deleting_user_cascades_to_profile(self):
        user = User.objects.create_user("testuser", "t@example.com", "Testpass123!")
        profile = UserProfile.objects.create(user=user)
        pk = profile.pk
        user.delete()
        self.assertFalse(UserProfile.objects.filter(pk=pk).exists())


class RegistrationFormTests(TestCase):

    def _valid_data(self):
        return {
            "username": "newuser",
            "email": "new@example.com",
            "password1": "Testpass123!",
            "password2": "Testpass123!",
        }

    def test_valid_form_is_valid(self):
        form = RegistrationForm(data=self._valid_data())
        self.assertTrue(form.is_valid(), form.errors)

    def test_email_is_required(self):
        data = self._valid_data()
        data["email"] = ""
        form = RegistrationForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_invalid_email_format_is_rejected(self):
        data = self._valid_data()
        data["email"] = "not-an-email"
        form = RegistrationForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_mismatched_passwords_are_rejected(self):
        data = self._valid_data()
        data["password2"] = "different"
        form = RegistrationForm(data=data)
        self.assertFalse(form.is_valid())

    def test_notify_checkboxes_default_false_when_omitted(self):
        form = RegistrationForm(data=self._valid_data())
        self.assertTrue(form.is_valid(), form.errors)
        self.assertFalse(form.cleaned_data["notify_on_article_publish"])
        self.assertFalse(form.cleaned_data["notify_on_quiz_publish"])

    def test_notify_article_can_be_opted_in(self):
        data = self._valid_data()
        data["notify_on_article_publish"] = True
        form = RegistrationForm(data=data)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(form.cleaned_data["notify_on_article_publish"])

    def test_notify_quiz_can_be_opted_in(self):
        data = self._valid_data()
        data["notify_on_quiz_publish"] = True
        form = RegistrationForm(data=data)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(form.cleaned_data["notify_on_quiz_publish"])


class RegisterViewTests(TestCase):

    def test_get_returns_200(self):
        response = self.client.get(reverse("register"))
        self.assertEqual(response.status_code, 200)

    def test_get_uses_correct_template(self):
        response = self.client.get(reverse("register"))
        self.assertTemplateUsed(response, "registration/register.html")

    def test_get_passes_registration_form_to_context(self):
        response = self.client.get(reverse("register"))
        self.assertIn("form", response.context)
        self.assertIsInstance(response.context["form"], RegistrationForm)

    def test_valid_post_creates_user(self):
        self.client.post(reverse("register"), {
            "username": "newuser",
            "email": "new@example.com",
            "password1": "Testpass123!",
            "password2": "Testpass123!",
        })
        self.assertTrue(User.objects.filter(username="newuser").exists())

    def test_valid_post_saves_email_on_user(self):
        self.client.post(reverse("register"), {
            "username": "newuser",
            "email": "new@example.com",
            "password1": "Testpass123!",
            "password2": "Testpass123!",
        })
        user = User.objects.get(username="newuser")
        self.assertEqual(user.email, "new@example.com")

    def test_valid_post_creates_user_profile_with_preferences(self):
        self.client.post(reverse("register"), {
            "username": "newuser",
            "email": "new@example.com",
            "password1": "Testpass123!",
            "password2": "Testpass123!",
            "notify_on_article_publish": True,
        })
        user = User.objects.get(username="newuser")
        profile = UserProfile.objects.get(user=user)
        self.assertTrue(profile.notify_on_article_publish)
        self.assertFalse(profile.notify_on_quiz_publish)

    def test_valid_post_logs_user_in(self):
        self.client.post(reverse("register"), {
            "username": "newuser",
            "email": "new@example.com",
            "password1": "Testpass123!",
            "password2": "Testpass123!",
        })
        response = self.client.get(reverse("home"))
        self.assertEqual(response.wsgi_request.user.username, "newuser")

    def test_valid_post_redirects_to_home(self):
        response = self.client.post(reverse("register"), {
            "username": "newuser",
            "email": "new@example.com",
            "password1": "Testpass123!",
            "password2": "Testpass123!",
        })
        self.assertRedirects(response, "/")

    def test_invalid_post_rerenders_form_with_errors(self):
        response = self.client.post(reverse("register"), {
            "username": "",
            "email": "not-valid",
            "password1": "abc",
            "password2": "xyz",
        })
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "registration/register.html")
        self.assertFalse(response.context["form"].is_valid())
