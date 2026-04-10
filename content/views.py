from django.shortcuts import render, get_object_or_404

from .models import Article


def home(request):
    return render(request, "home.html")


def article_list(request):
    articles = Article.objects.filter(is_published=True).order_by("-published_date")
    return render(request, "content/article_list.html", {"articles": articles})


# def article(request):
#     return render(request, "content/article.html")

def article_detail(request, slug):
    article = get_object_or_404(Article, slug=slug, is_published=True)
    return render(request, "content/article_detail.html", {"article": article})