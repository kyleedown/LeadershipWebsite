from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class Quiz(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    is_published = models.BooleanField(default=False)
    published_date = models.DateTimeField(default=timezone.now)
    article = models.ForeignKey(
        'content.Article', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='quizzes',
    )

    def __str__(self):
        return self.title


class Dimension(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='dimensions')
    name = models.CharField(max_length=100)
    left_name = models.CharField(max_length=100)
    right_name = models.CharField(max_length=100)
    left_label = models.CharField(max_length=200)
    right_label = models.CharField(max_length=200)

    def __str__(self):
        return f"{self.quiz.title} — {self.name}"


class ResultCategory(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='result_categories')
    name = models.CharField(max_length=200)
    slug = models.SlugField()
    description = models.TextField()
    article_1 = models.ForeignKey(
        'content.Article', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+',
    )
    article_2 = models.ForeignKey(
        'content.Article', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+',
    )

    class Meta:
        unique_together = [('quiz', 'slug')]

    def __str__(self):
        return f"{self.quiz.title} — {self.name}"


class DimensionResult(models.Model):
    result_category = models.ForeignKey(
        ResultCategory, on_delete=models.CASCADE, related_name='dimension_results',
    )
    dimension = models.ForeignKey(
        Dimension, on_delete=models.CASCADE, related_name='dimension_results',
    )
    side = models.CharField(max_length=5, choices=[('left', 'Left'), ('right', 'Right')])

    class Meta:
        unique_together = [('result_category', 'dimension')]

    def __str__(self):
        return f"{self.result_category.name} — {self.dimension.name}: {self.side}"


class Question(models.Model):
    RANK = 'rank'
    SLIDER = 'slider'
    QUESTION_TYPES = [(RANK, 'Rank'), (SLIDER, 'Slider')]

    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='questions')
    text = models.TextField()
    order = models.PositiveIntegerField(default=0)
    question_type = models.CharField(max_length=6, choices=QUESTION_TYPES)
    dimension = models.ForeignKey(Dimension, on_delete=models.CASCADE, related_name='questions')

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"Q{self.order}: {self.text[:50]}"


class AnswerChoice(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='choices')
    text = models.CharField(max_length=200)
    side = models.CharField(max_length=5, choices=[('left', 'Left'), ('right', 'Right')])

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.text} ({self.side})"


class QuizAttempt(models.Model):
    user = models.ForeignKey(
        User, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='quiz_attempts',
    )
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='attempts')
    result_category = models.ForeignKey(
        ResultCategory, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='attempts',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Attempt by {self.user} on {self.quiz.title}"


class AttemptDimensionScore(models.Model):
    attempt = models.ForeignKey(
        QuizAttempt, on_delete=models.CASCADE, related_name='dimension_scores',
    )
    dimension = models.ForeignKey(
        Dimension, on_delete=models.CASCADE, related_name='attempt_scores',
    )
    left_score = models.FloatField(default=0.0)
    right_score = models.FloatField(default=0.0)

    class Meta:
        unique_together = [('attempt', 'dimension')]

    def __str__(self):
        return f"{self.dimension.name}: L={self.left_score} R={self.right_score}"
