from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User


class RegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    notify_on_article_publish = forms.BooleanField(
        required=False,
        label="Notify me when a new article is published",
    )
    notify_on_quiz_publish = forms.BooleanField(
        required=False,
        label="Notify me when a new quiz is published",
    )

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")
