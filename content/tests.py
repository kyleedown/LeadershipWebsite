import logging
from unittest.mock import MagicMock

from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserProfile
from .models import Article
from .observers import (
    ArticleObserver,
    ArticlePublisher,
    EmailNotificationObserver,
    LoggingObserver,
    PublicationCounterObserver,
    article_publisher,
)


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


# =============================================================================
# Observer Pattern Tests
# =============================================================================

class ArticlePublisherTest(TestCase):
    """
    Unit tests for ArticlePublisher (the Subject in the Observer pattern).

    These tests verify subscribe/unsubscribe/notify behaviour in isolation,
    with no Django DB or signal involvement.
    """

    def setUp(self):
        self.publisher = ArticlePublisher()
        self.mock_article = MagicMock()
        self.mock_article.title = "Test Article"
        self.mock_article.slug = "test-article"

    def test_subscribe_registers_observer(self):
        """An observer added via subscribe() should receive notifications."""
        observer = MagicMock(spec=ArticleObserver)
        self.publisher.subscribe(observer)
        self.publisher.notify(self.mock_article)
        observer.on_article_published.assert_called_once_with(self.mock_article)

    def test_unsubscribe_removes_observer(self):
        """An observer removed via unsubscribe() should no longer receive notifications."""
        observer = MagicMock(spec=ArticleObserver)
        self.publisher.subscribe(observer)
        self.publisher.unsubscribe(observer)
        self.publisher.notify(self.mock_article)
        observer.on_article_published.assert_not_called()

    def test_duplicate_subscribe_is_ignored(self):
        """Subscribing the same observer twice should not cause double notifications."""
        observer = MagicMock(spec=ArticleObserver)
        self.publisher.subscribe(observer)
        self.publisher.subscribe(observer)
        self.publisher.notify(self.mock_article)
        observer.on_article_published.assert_called_once_with(self.mock_article)

    def test_notify_calls_all_observers(self):
        """All registered observers should be notified on a single notify() call."""
        obs1 = MagicMock(spec=ArticleObserver)
        obs2 = MagicMock(spec=ArticleObserver)
        self.publisher.subscribe(obs1)
        self.publisher.subscribe(obs2)
        self.publisher.notify(self.mock_article)
        obs1.on_article_published.assert_called_once_with(self.mock_article)
        obs2.on_article_published.assert_called_once_with(self.mock_article)

    def test_notify_with_no_observers_does_not_raise(self):
        """notify() on a publisher with no subscribers should complete silently."""
        try:
            self.publisher.notify(self.mock_article)
        except Exception as exc:
            self.fail(f"notify() raised an unexpected exception: {exc}")

    def test_observer_count_reflects_subscriptions(self):
        """observer_count should accurately reflect the number of subscribed observers."""
        self.assertEqual(self.publisher.observer_count, 0)
        obs = MagicMock(spec=ArticleObserver)
        self.publisher.subscribe(obs)
        self.assertEqual(self.publisher.observer_count, 1)
        self.publisher.unsubscribe(obs)
        self.assertEqual(self.publisher.observer_count, 0)


class PublicationCounterObserverTest(TestCase):
    """Unit tests for PublicationCounterObserver."""

    def test_counter_starts_at_zero(self):
        """A freshly created counter should report zero publications."""
        counter = PublicationCounterObserver()
        self.assertEqual(counter.count, 0)

    def test_counter_increments_on_each_notification(self):
        """Counter should increment once per on_article_published() call."""
        counter = PublicationCounterObserver()
        mock_article = MagicMock()
        counter.on_article_published(mock_article)
        self.assertEqual(counter.count, 1)
        counter.on_article_published(mock_article)
        self.assertEqual(counter.count, 2)


class LoggingObserverTest(TestCase):
    """Unit tests for LoggingObserver."""

    def test_logging_observer_emits_log_message(self):
        """LoggingObserver should emit an INFO log when an article is published."""
        observer = LoggingObserver()
        mock_article = MagicMock()
        mock_article.title = "My Article"
        mock_article.slug = "my-article"
        mock_article.published_date = timezone.now()

        with self.assertLogs("content.observers", level="INFO") as log_context:
            observer.on_article_published(mock_article)

        self.assertTrue(
            any("My Article" in line for line in log_context.output),
            "Expected article title to appear in the log output.",
        )


class ArticlePublishSignalTest(TestCase):
    """
    Integration tests verifying the Observer pattern is correctly wired
    to Django's save signals via ContentConfig.ready().

    Each test uses its own PublicationCounterObserver subscribed to the
    global article_publisher so we can count exactly how many times
    notify() fires.
    """

    def setUp(self):
        self.counter = PublicationCounterObserver()
        article_publisher.subscribe(self.counter)

    def tearDown(self):
        article_publisher.unsubscribe(self.counter)

    def test_publishing_a_new_article_notifies_observers(self):
        """Creating a new article with is_published=True should notify observers once."""
        Article.objects.create(
            title="Brand New Published",
            body="Body.",
            slug="brand-new-published",
            is_published=True,
        )
        self.assertEqual(self.counter.count, 1)

    def test_creating_draft_does_not_notify_observers(self):
        """Creating an article with is_published=False should not notify observers."""
        Article.objects.create(
            title="Still a Draft",
            body="Body.",
            slug="still-a-draft",
            is_published=False,
        )
        self.assertEqual(self.counter.count, 0)

    def test_transitioning_draft_to_published_notifies_observers(self):
        """Flipping is_published from False to True should notify observers exactly once."""
        article = Article.objects.create(
            title="Becoming Published",
            body="Body.",
            slug="becoming-published",
            is_published=False,
        )
        self.assertEqual(self.counter.count, 0)

        article.is_published = True
        article.save()
        self.assertEqual(self.counter.count, 1)

    def test_re_saving_published_article_does_not_re_notify(self):
        """Saving an already-published article again should NOT fire another notification."""
        article = Article.objects.create(
            title="Already Published",
            body="Body.",
            slug="already-published",
            is_published=True,
        )
        self.assertEqual(self.counter.count, 1)

        # Edit title but keep it published — no second notification expected
        article.title = "Already Published (Edited)"
        article.save()
        self.assertEqual(self.counter.count, 1)

    def test_multiple_articles_each_trigger_one_notification(self):
        """Each distinct article publish should produce exactly one notification."""
        for i in range(3):
            Article.objects.create(
                title=f"Article {i}",
                body="Body.",
                slug=f"article-{i}",
                is_published=True,
            )
        self.assertEqual(self.counter.count, 3)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class EmailNotificationObserverTests(TestCase):

    def setUp(self):
        self.publisher = ArticlePublisher()
        self.observer = EmailNotificationObserver()
        self.publisher.subscribe(self.observer)

    def _make_article(self, slug="test-article"):
        return Article.objects.create(
            title="Test Article",
            slug=slug,
            body="Body text.",
            is_published=False,
        )

    def test_sends_email_to_opted_in_user(self):
        user = User.objects.create_user("notified", "notified@example.com", "pass")
        UserProfile.objects.create(user=user, notify_on_article_publish=True)
        self.publisher.notify(self._make_article())
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("notified@example.com", mail.outbox[0].to)

    def test_does_not_send_to_opted_out_user(self):
        user = User.objects.create_user("quiet", "quiet@example.com", "pass")
        UserProfile.objects.create(user=user, notify_on_article_publish=False)
        self.publisher.notify(self._make_article())
        self.assertEqual(len(mail.outbox), 0)

    def test_does_not_send_to_user_without_profile(self):
        User.objects.create_user("noprofile", "noprofile@example.com", "pass")
        self.publisher.notify(self._make_article())
        self.assertEqual(len(mail.outbox), 0)

    def test_sends_to_all_opted_in_users_in_one_email(self):
        for i in range(3):
            u = User.objects.create_user(f"user{i}", f"user{i}@example.com", "pass")
            UserProfile.objects.create(user=u, notify_on_article_publish=True)
        self.publisher.notify(self._make_article())
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(len(mail.outbox[0].to), 3)

    def test_email_subject_contains_article_title(self):
        user = User.objects.create_user("notified", "notified@example.com", "pass")
        UserProfile.objects.create(user=user, notify_on_article_publish=True)
        article = self._make_article()
        self.publisher.notify(article)
        self.assertIn(article.title, mail.outbox[0].subject)

    def test_sends_no_email_when_no_opted_in_users(self):
        self.publisher.notify(self._make_article())
        self.assertEqual(len(mail.outbox), 0)

    def test_send_mail_failure_does_not_propagate(self):
        from unittest.mock import patch
        user = User.objects.create_user("notified", "notified@example.com", "pass")
        UserProfile.objects.create(user=user, notify_on_article_publish=True)
        with patch("django.core.mail.send_mail", side_effect=Exception("SMTP error")):
            try:
                self.publisher.notify(self._make_article())
            except Exception as exc:
                self.fail(f"on_article_published raised an unexpected exception: {exc}")
