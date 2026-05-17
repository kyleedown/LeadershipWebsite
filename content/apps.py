from django.apps import AppConfig


class ContentConfig(AppConfig):
    name = "content"

    def ready(self):
        """
        Wire Django's save signals into the Observer pattern.

        We use two signals together to detect the specific moment an article
        *transitions* from unpublished → published, rather than firing on
        every save:

          pre_save  — snapshot the article's previous is_published state
                      before the database write.
          post_save — after the write, compare current vs. previous state;
                      only call article_publisher.notify() on a true
                      unpublished → published transition.

        This avoids duplicate notifications when an already-published article
        is edited and re-saved.
        """
        from django.db.models.signals import pre_save, post_save
        from .models import Article
        from .observers import article_publisher

        def on_article_pre_save(sender, instance, **kwargs):
            """Capture the previous published state before the DB write."""
            if instance.pk:
                try:
                    instance._was_published = (
                        Article.objects.get(pk=instance.pk).is_published
                    )
                except Article.DoesNotExist:
                    instance._was_published = False
            else:
                # Brand-new article — no previous state
                instance._was_published = False

        def on_article_post_save(sender, instance, created, **kwargs):
            """Notify observers only on unpublished → published transitions."""
            was_published = getattr(instance, "_was_published", False)
            if instance.is_published and not was_published:
                article_publisher.notify(instance)

        # weak=False is required here because on_article_pre_save and
        # on_article_post_save are local functions. Django connects signals
        # with weak references by default, which means local functions would
        # be garbage-collected immediately after ready() returns, leaving
        # dead references that never fire. weak=False keeps them alive.
        pre_save.connect(on_article_pre_save, sender=Article, weak=False)
        post_save.connect(on_article_post_save, sender=Article, weak=False)
