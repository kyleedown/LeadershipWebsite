from django.contrib.auth.models import User
from django.db import models


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    notify_on_article_publish = models.BooleanField(default=False)
    notify_on_quiz_publish = models.BooleanField(default=False)

    def __str__(self):
        return f"Profile for {self.user.username}"
