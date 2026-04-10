from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Article


class ArticleModelTest(TestCase):

    def test_str_representation(self):
        """Article __str__ should return its title."""
        article = Article(title="My First Article", slug="my-first-article")
        self.assertEqual(str(article), "My First Article")

    def test_is_published_defaults_to_false(self):
        """Newly created articles should not be published by default."""
        article = Article.objects.create(
            title="Draft Article",
            body="Some body text.",
            slug="draft-article",
        )
        self.assertFalse(article.is_published)

    def test_published_date_defaults_to_now(self):
        """published_date should be set automatically close to the current time."""
        before = timezone.now()
        article = Article.objects.create(
            title="Timed Article",
            body="Body content.",
            slug="timed-article",
        )
        after = timezone.now()
        self.assertGreaterEqual(article.published_date, before)
        self.assertLessEqual(article.published_date, after)


class ArticleModelUrlTest(TestCase):

    def test_get_absolute_url(self):
        """get_absolute_url should return the correct detail URL for an article."""
        article = Article.objects.create(
            title="URL Test Article",
            body="Body text.",
            slug="url-test-article",
            is_published=True,
        )
        self.assertEqual(article.get_absolute_url(), "/articles/url-test-article/")


class ArticleListViewTest(TestCase):

    def test_article_list_returns_200(self):
        """GET /articles/ should return a 200 OK response."""
        response = self.client.get(reverse("article_list"))
        self.assertEqual(response.status_code, 200)

    def test_article_list_shows_published_articles(self):
        """Published articles should appear in the article list."""
        Article.objects.create(
            title="Published Article",
            body="Body text.",
            slug="published-article",
            is_published=True,
        )
        response = self.client.get(reverse("article_list"))
        self.assertContains(response, "Published Article")

    def test_article_list_hides_unpublished_articles(self):
        """Unpublished articles should NOT appear in the article list."""
        Article.objects.create(
            title="Draft Article",
            body="Body text.",
            slug="draft-article",
            is_published=False,
        )
        response = self.client.get(reverse("article_list"))
        self.assertNotContains(response, "Draft Article")

    def test_article_list_links_to_detail_page(self):
        """Each article in the list should link to its detail page."""
        Article.objects.create(
            title="Linked Article",
            body="Body text.",
            slug="linked-article",
            is_published=True,
        )
        response = self.client.get(reverse("article_list"))
        self.assertContains(response, 'href="/articles/linked-article/"')


class ArticleDetailViewTest(TestCase):

    def setUp(self):
        self.published = Article.objects.create(
            title="A Published Article",
            body="This is the article body.",
            slug="a-published-article",
            is_published=True,
        )
        self.draft = Article.objects.create(
            title="A Draft Article",
            body="This is a draft.",
            slug="a-draft-article",
            is_published=False,
        )

    def test_detail_returns_200_for_published_article(self):
        """GET /articles/<slug>/ should return 200 for a published article."""
        response = self.client.get(reverse("article_detail", kwargs={"slug": self.published.slug}))
        self.assertEqual(response.status_code, 200)

    def test_detail_displays_article_title(self):
        """The article title should appear on the detail page."""
        response = self.client.get(reverse("article_detail", kwargs={"slug": self.published.slug}))
        self.assertContains(response, "A Published Article")

    def test_detail_displays_article_body(self):
        """The article body should appear on the detail page."""
        response = self.client.get(reverse("article_detail", kwargs={"slug": self.published.slug}))
        self.assertContains(response, "This is the article body.")

    def test_detail_returns_404_for_unpublished_article(self):
        """GET /articles/<slug>/ should return 404 for a draft (unpublished) article."""
        response = self.client.get(reverse("article_detail", kwargs={"slug": self.draft.slug}))
        self.assertEqual(response.status_code, 404)

    def test_detail_returns_404_for_nonexistent_slug(self):
        """GET /articles/<slug>/ should return 404 if the slug doesn't exist."""
        response = self.client.get(reverse("article_detail", kwargs={"slug": "does-not-exist"}))
        self.assertEqual(response.status_code, 404)

    def test_detail_uses_correct_template(self):
        """The detail view should render the article_detail.html template."""
        response = self.client.get(reverse("article_detail", kwargs={"slug": self.published.slug}))
        self.assertTemplateUsed(response, "content/article_detail.html")

    def test_detail_passes_article_to_template(self):
        """The detail view should pass the correct article object to the template."""
        response = self.client.get(reverse("article_detail", kwargs={"slug": self.published.slug}))
        self.assertEqual(response.context["article"], self.published)
