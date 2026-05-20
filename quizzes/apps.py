from django.apps import AppConfig


class QuizzesConfig(AppConfig):
    name = "quizzes"

    def ready(self):
        from django.db.models.signals import pre_save, post_save
        from .models import Quiz
        from .observers import quiz_publisher

        def on_quiz_pre_save(sender, instance, **kwargs):
            if instance.pk:
                try:
                    instance._was_published = (
                        Quiz.objects.get(pk=instance.pk).is_published
                    )
                except Quiz.DoesNotExist:
                    instance._was_published = False
            else:
                instance._was_published = False

        def on_quiz_post_save(sender, instance, created, **kwargs):
            was_published = getattr(instance, '_was_published', False)
            if instance.is_published and not was_published:
                quiz_publisher.notify(instance)

        pre_save.connect(on_quiz_pre_save, sender=Quiz, weak=False)
        post_save.connect(on_quiz_post_save, sender=Quiz, weak=False)
