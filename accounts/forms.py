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


class ProfileForm(forms.ModelForm):
    current_password = forms.CharField(widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ("username", "email")

    def __init__(self, *args, **kwargs):
        if "user" not in kwargs:
            raise TypeError("ProfileForm requires a 'user' keyword argument.")
        self.user = kwargs.pop("user")
        super().__init__(*args, **kwargs)

    def clean_current_password(self):
        pw = self.cleaned_data["current_password"]
        if not self.user.check_password(pw):
            raise forms.ValidationError("Incorrect password.")
        return pw
