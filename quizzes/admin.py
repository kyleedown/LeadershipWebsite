from django.contrib import admin
from django_summernote.admin import SummernoteModelAdmin

from .models import (
    AnswerChoice, AttemptDimensionScore, Dimension, DimensionResult,
    Question, Quiz, QuizAttempt, ResultCategory,
)


class DimensionInline(admin.StackedInline):
    model = Dimension
    extra = 1
    fields = ('name', 'left_name', 'right_name', 'left_label', 'right_label')
    verbose_name_plural = 'Dimensions — save the quiz first, then add questions below'


class ResultCategoryInline(admin.TabularInline):
    model = ResultCategory
    extra = 1
    fields = ('name', 'slug', 'description', 'article_1', 'article_2')
    show_change_link = True
    verbose_name_plural = (
        'Result Categories — after saving, click "Change" on each category '
        'to assign which dimension outcomes (left/right per dimension) map to it'
    )


class QuestionInline(admin.TabularInline):
    model = Question
    extra = 0
    fields = ('text', 'order', 'question_type', 'dimension')
    show_change_link = True
    verbose_name_plural = 'Questions — add dimensions first and save, then add questions here'

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'dimension':
            quiz_id = request.resolver_match.kwargs.get('object_id')
            if quiz_id:
                kwargs['queryset'] = Dimension.objects.filter(quiz_id=quiz_id)
            else:
                kwargs['queryset'] = Dimension.objects.none()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Quiz)
class QuizAdmin(SummernoteModelAdmin):
    summernote_fields = ('description',)
    inlines = [DimensionInline, ResultCategoryInline, QuestionInline]
    prepopulated_fields = {'slug': ('title',)}
    list_display = ('title', 'is_published', 'published_date')


class DimensionResultInline(admin.TabularInline):
    model = DimensionResult
    extra = 1
    verbose_name = 'Dimension Outcome Mapping'
    verbose_name_plural = (
        'Dimension Outcome Mappings — add one row per dimension; '
        'choose which side (left or right) of that dimension triggers this result'
    )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'dimension':
            rc_id = request.resolver_match.kwargs.get('object_id')
            if rc_id:
                try:
                    quiz_id = ResultCategory.objects.values_list(
                        'quiz_id', flat=True
                    ).get(pk=rc_id)
                    kwargs['queryset'] = Dimension.objects.filter(quiz_id=quiz_id)
                except ResultCategory.DoesNotExist:
                    kwargs['queryset'] = Dimension.objects.none()
            else:
                kwargs['queryset'] = Dimension.objects.none()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(ResultCategory)
class ResultCategoryAdmin(SummernoteModelAdmin):
    summernote_fields = ('description',)
    inlines = [DimensionResultInline]
    prepopulated_fields = {'slug': ('name',)}
    list_display = ('name', 'quiz')


class AnswerChoiceInline(admin.TabularInline):
    model = AnswerChoice
    extra = 1


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    inlines = [AnswerChoiceInline]
    list_display = ('text', 'quiz', 'question_type', 'dimension', 'order')
    list_filter = ('quiz', 'question_type')


@admin.register(QuizAttempt)
class QuizAttemptAdmin(admin.ModelAdmin):
    list_display = ('quiz', 'user', 'result_category', 'created_at')
    list_filter = ('quiz',)
    readonly_fields = ('created_at',)
