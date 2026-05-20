import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class QuizObserver(ABC):
    @abstractmethod
    def on_quiz_published(self, quiz) -> None: ...


class QuizPublisher:
    def __init__(self):
        self._observers: list[QuizObserver] = []

    def subscribe(self, observer: QuizObserver) -> None:
        if observer not in self._observers:
            self._observers.append(observer)

    def unsubscribe(self, observer: QuizObserver) -> None:
        self._observers.remove(observer)

    @property
    def observer_count(self) -> int:
        return len(self._observers)

    def notify(self, quiz) -> None:
        for observer in list(self._observers):
            observer.on_quiz_published(quiz)


class LoggingObserver(QuizObserver):
    def on_quiz_published(self, quiz) -> None:
        logger.info("Quiz published: %s", quiz.slug)


class EmailNotificationObserver(QuizObserver):
    def on_quiz_published(self, quiz) -> None:
        from django.core.mail import send_mail
        from accounts.models import UserProfile

        emails = list(
            UserProfile.objects
            .filter(notify_on_quiz_publish=True)
            .exclude(user__email='')
            .values_list('user__email', flat=True)
        )
        if not emails:
            return
        try:
            send_mail(
                subject=f"New quiz: {quiz.title}",
                message=f"A new quiz has been published: {quiz.title}",
                from_email=None,
                recipient_list=emails,
            )
        except Exception:
            logger.exception(
                "EmailNotificationObserver: failed for quiz %r", quiz.slug
            )


quiz_publisher = QuizPublisher()
quiz_publisher.subscribe(LoggingObserver())
quiz_publisher.subscribe(EmailNotificationObserver())
