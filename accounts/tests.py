from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse

from .forms import ProfileForm, RegistrationForm
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


class ProfileFormTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user("testuser", "test@example.com", "Testpass123!")

    def _valid_data(self):
        return {
            "username": "testuser",
            "email": "test@example.com",
            "current_password": "Testpass123!",
        }

    def test_valid_form_is_valid(self):
        form = ProfileForm(data=self._valid_data(), instance=self.user, user=self.user)
        self.assertTrue(form.is_valid(), form.errors)

    def test_wrong_password_makes_form_invalid(self):
        data = self._valid_data()
        data["current_password"] = "wrongpassword"
        form = ProfileForm(data=data, instance=self.user, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn("current_password", form.errors)

    def test_invalid_email_rejected(self):
        data = self._valid_data()
        data["email"] = "not-an-email"
        form = ProfileForm(data=data, instance=self.user, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_blank_username_rejected(self):
        data = self._valid_data()
        data["username"] = ""
        form = ProfileForm(data=data, instance=self.user, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn("username", form.errors)


class ProfileViewTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user("testuser", "test@example.com", "Testpass123!")

    def test_get_requires_login(self):
        response = self.client.get(reverse("profile"))
        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('profile')}",
            fetch_redirect_response=False,
        )

    def test_get_returns_200_when_logged_in(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("profile"))
        self.assertEqual(response.status_code, 200)

    def test_get_uses_correct_template(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("profile"))
        self.assertTemplateUsed(response, "registration/profile.html")

    def test_get_form_prefilled_with_user_data(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("profile"))
        form = response.context["form"]
        self.assertEqual(form["username"].value(), "testuser")
        self.assertEqual(form["email"].value(), "test@example.com")

    def test_valid_post_updates_username(self):
        self.client.force_login(self.user)
        self.client.post(reverse("profile"), {
            "username": "newusername",
            "email": "test@example.com",
            "current_password": "Testpass123!",
        })
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "newusername")

    def test_valid_post_updates_email(self):
        self.client.force_login(self.user)
        self.client.post(reverse("profile"), {
            "username": "testuser",
            "email": "new@example.com",
            "current_password": "Testpass123!",
        })
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "new@example.com")

    def test_valid_post_redirects_to_profile(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("profile"), {
            "username": "testuser",
            "email": "test@example.com",
            "current_password": "Testpass123!",
        })
        self.assertRedirects(response, reverse("profile"))

    def test_valid_post_adds_success_message(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("profile"), {
            "username": "testuser",
            "email": "test@example.com",
            "current_password": "Testpass123!",
        })
        msgs = list(get_messages(response.wsgi_request))
        self.assertEqual(len(msgs), 1)
        self.assertIn("updated", str(msgs[0]))

    def test_wrong_password_rerenders_form(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("profile"), {
            "username": "testuser",
            "email": "test@example.com",
            "current_password": "wrongpassword",
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn("current_password", response.context["form"].errors)

    def test_wrong_password_does_not_update_user(self):
        self.client.force_login(self.user)
        self.client.post(reverse("profile"), {
            "username": "newusername",
            "email": "test@example.com",
            "current_password": "wrongpassword",
        })
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "testuser")

    def test_duplicate_username_is_rejected(self):
        User.objects.create_user("takenuser", "taken@example.com", "Testpass123!")
        self.client.force_login(self.user)
        response = self.client.post(reverse("profile"), {
            "username": "takenuser",
            "email": "test@example.com",
            "current_password": "Testpass123!",
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn("username", response.context["form"].errors)
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "testuser")


class PasswordChangeViewTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user("testuser", "test@example.com", "Testpass123!")

    def test_get_requires_login(self):
        response = self.client.get(reverse("password_change"))
        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('password_change')}",
            fetch_redirect_response=False,
        )

    def test_get_returns_200_when_logged_in(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("password_change"))
        self.assertEqual(response.status_code, 200)

    def test_get_uses_correct_template(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("password_change"))
        self.assertTemplateUsed(response, "registration/password_change_form.html")

    def test_valid_post_changes_password(self):
        self.client.force_login(self.user)
        self.client.post(reverse("password_change"), {
            "old_password": "Testpass123!",
            "new_password1": "Newpass456!",
            "new_password2": "Newpass456!",
        })
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Newpass456!"))

    def test_valid_post_redirects_to_done(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("password_change"), {
            "old_password": "Testpass123!",
            "new_password1": "Newpass456!",
            "new_password2": "Newpass456!",
        })
        self.assertRedirects(response, reverse("password_change_done"))

    def test_done_page_returns_200(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("password_change_done"))
        self.assertEqual(response.status_code, 200)

    def test_done_page_uses_correct_template(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("password_change_done"))
        self.assertTemplateUsed(response, "registration/password_change_done.html")


class NavbarTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user("testuser", "test@example.com", "Testpass123!")

    def test_navbar_username_is_link_when_authenticated(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("profile"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'href="{reverse("profile")}"')
        self.assertContains(response, self.user.username)

    def test_navbar_shows_login_link_when_anonymous(self):
        response = self.client.get(reverse("login"))
        self.assertNotContains(response, f'href="{reverse("profile")}"')
        self.assertNotContains(response, "testuser")
        self.assertContains(response, f'href="{reverse("login")}"')
