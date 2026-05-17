"""
Observer Pattern — Article Publishing
======================================
Pattern: Observer (a.k.a. Publish-Subscribe)

Why this pattern?
    The Article model should not need to know *who* cares when it gets
    published — that would tightly couple unrelated concerns (logging,
    analytics, future email notifications, etc.) into the model itself.
    The Observer pattern solves this by defining a one-to-many dependency:
    the ArticlePublisher (Subject) maintains a list of ArticleObserver
    objects and automatically notifies them all whenever an article is
    published, without the Article model having any knowledge of them.

Structure:
    ArticleObserver  – abstract base class; concrete observers implement
                       on_article_published().
    ArticlePublisher – the Subject; owns subscribe/unsubscribe/notify.
    LoggingObserver  – concrete observer that logs a message.
    PublicationCounterObserver – concrete observer that tracks a count.

Wired up in:
    content/apps.py — Django post_save signal triggers notify() only when
    an article *transitions* from unpublished → published.
"""

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class ArticleObserver(ABC):
    """
    Abstract base for all article-event observers.

    Any class that wants to react to an article being published must
    subclass this and implement on_article_published().
    """

    @abstractmethod
    def on_article_published(self, article) -> None:
        """
        Called by ArticlePublisher when an article transitions to published.

        Args:
            article: The Article model instance that was just published.
        """


class ArticlePublisher:
    """
    The Subject in the Observer pattern.

    Maintains a registry of ArticleObserver instances and fans out
    notification to all of them when an article is published.
    """

    def __init__(self):
        self._observers: list[ArticleObserver] = []

    def subscribe(self, observer: ArticleObserver) -> None:
        """Register an observer. Duplicate registrations are silently ignored."""
        if observer not in self._observers:
            self._observers.append(observer)

    def unsubscribe(self, observer: ArticleObserver) -> None:
        """Remove an observer. Raises ValueError if observer is not registered."""
        self._observers.remove(observer)

    @property
    def observer_count(self) -> int:
        """Number of currently registered observers."""
        return len(self._observers)

    def notify(self, article) -> None:
        """
        Notify all registered observers that an article was published.

        Iterates over a snapshot of the observer list so that an observer
        can safely unsubscribe itself during notification.
        """
        for observer in list(self._observers):
            observer.on_article_published(article)


# ---------------------------------------------------------------------------
# Concrete Observers
# ---------------------------------------------------------------------------

class LoggingObserver(ArticleObserver):
    """
    Logs an INFO-level message whenever an article is published.

    This is the lightest-weight observer — useful for audit trails and
    debugging without any persistent side effects.
    """

    def on_article_published(self, article) -> None:
        logger.info(
            "Article published: '%s' (slug: %s, published_date: %s)",
            article.title,
            article.slug,
            article.published_date,
        )


class PublicationCounterObserver(ArticleObserver):
    """
    Tracks how many articles have been published since this observer
    was created.

    Useful for lightweight in-process analytics or tests that need to
    assert a specific number of publish events occurred.
    """

    def __init__(self):
        self.count: int = 0

    def on_article_published(self, article) -> None:
        self.count += 1


class EmailNotificationObserver(ArticleObserver):
    """
    Sends an email to all users who opted in to article notifications
    when an article is published.

    Imports are deferred inside the method to avoid circular imports
    between the content and accounts apps.
    """

    def on_article_published(self, article) -> None:
        from django.core.mail import send_mail
        from accounts.models import UserProfile

        emails = list(
            UserProfile.objects
            .filter(notify_on_article_publish=True)
            .exclude(user__email="")
            .select_related("user")
            .values_list("user__email", flat=True)
        )
        if not emails:
            return
        try:
            send_mail(
                subject=f"New article: {article.title}",
                message=f"A new article has been published on Leadership Studies: {article.title}",
                from_email=None,
                recipient_list=emails,
            )
        except Exception:
            logger.exception(
                "EmailNotificationObserver: failed to send notification email for article %r",
                article.slug,
            )


# ---------------------------------------------------------------------------
# Module-level singleton — the shared publisher for the content app.
# ---------------------------------------------------------------------------

article_publisher = ArticlePublisher()
article_publisher.subscribe(LoggingObserver())
article_publisher.subscribe(EmailNotificationObserver())
