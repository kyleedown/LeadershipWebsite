from django.db import models
from django.urls import reverse
from django.utils import timezone


class Article(models.Model):
    title = models.CharField(max_length=200)
    body = models.TextField()
    slug = models.SlugField(unique=True)
    published_date = models.DateTimeField(default=timezone.now)
    is_published = models.BooleanField(default=False)

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("article_detail", kwargs={"slug": self.slug})
