from django.contrib import admin
from .models import Article
from django_summernote.admin import SummernoteModelAdmin 

admin.site.register(Article)

class ArticleAdmin(SummernoteModelAdmin):
    summernote_fields = ('body',)

admin.site.register(Article, ArticleAdmin)