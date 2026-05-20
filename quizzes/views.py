from itertools import product as iterproduct

from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .models import (
    AnswerChoice, AttemptDimensionScore, Dimension,
    Question, Quiz, QuizAttempt, ResultCategory,
)


def compute_scores(questions, post_data):
    scores = {}
    for question in questions:
        dim_id = question.dimension_id
        if dim_id not in scores:
            scores[dim_id] = {'left': 0.0, 'right': 0.0}

        if question.question_type == Question.RANK:
            order_str = post_data.get(f'rank_{question.id}', '')
            if not order_str:
                continue
            try:
                choice_ids = [int(x) for x in order_str.split(',') if x.strip()]
            except ValueError:
                continue
            choices_by_id = {c.id: c for c in question.choices.all()}
            n = len(choice_ids)
            for rank_pos, choice_id in enumerate(choice_ids, 1):
                choice = choices_by_id.get(choice_id)
                if not choice:
                    continue
                points = n - rank_pos + 1
                scores[dim_id][choice.side] += points

        elif question.question_type == Question.SLIDER:
            try:
                raw = max(-100, min(100, int(post_data.get(f'slider_{question.id}', 0))))
            except (ValueError, TypeError):
                raw = 0
            value = raw / 100.0
            if value > 0:
                scores[dim_id]['right'] += value
            elif value < 0:
                scores[dim_id]['left'] += abs(value)

    return scores


def determine_winners(scores):
    return {
        dim_id: (
            'right' if s['right'] > s['left']
            else 'left' if s['left'] > s['right']
            else 'tie'
        )
        for dim_id, s in scores.items()
    }


def find_result_categories(quiz, winners):
    dimensions = list(quiz.dimensions.all())
    # Dimensions with no score (absent from winners) are treated like ties —
    # they don't restrict the result lookup.
    non_tied = [(d.id, winners[d.id]) for d in dimensions if winners.get(d.id) in ('left', 'right')]
    tied_dim_ids = [d.id for d in dimensions if winners.get(d.id) not in ('left', 'right')]

    qs = quiz.result_categories.all()
    for dim_id, side in non_tied:
        qs = qs.filter(
            dimension_results__dimension_id=dim_id,
            dimension_results__side=side,
        )

    if not tied_dim_ids:
        return list(qs)

    results = []
    seen_pks = set()
    for combo in iterproduct(['left', 'right'], repeat=len(tied_dim_ids)):
        combo_qs = qs
        for dim_id, side in zip(tied_dim_ids, combo):
            combo_qs = combo_qs.filter(
                dimension_results__dimension_id=dim_id,
                dimension_results__side=side,
            )
        for rc in combo_qs:
            if rc.pk not in seen_pks:
                results.append(rc)
                seen_pks.add(rc.pk)
    return results


def quiz_list(request):
    quizzes = Quiz.objects.filter(is_published=True).order_by('-published_date')
    return render(request, 'quizzes/quiz_list.html', {'quizzes': quizzes})


def quiz_detail(request, slug):
    quiz = get_object_or_404(Quiz, slug=slug, is_published=True)
    questions = (
        quiz.questions
        .select_related('dimension')
        .prefetch_related('choices')
    )

    if request.method == 'POST':
        scores = compute_scores(questions, request.POST)
        winners = determine_winners(scores)
        result_categories = find_result_categories(quiz, winners)

        if not result_categories:
            return render(request, 'quizzes/quiz_detail.html', {
                'quiz': quiz,
                'questions': questions,
                'error': 'Could not determine your result. Please try again.',
            })

        primary = result_categories[0]
        secondary = result_categories[1] if len(result_categories) > 1 else None

        request.session[f'quiz_{quiz.id}_scores'] = {
            str(dim_id): s for dim_id, s in scores.items()
        }

        if request.user.is_authenticated:
            with transaction.atomic():
                attempt = QuizAttempt.objects.create(
                    user=request.user,
                    quiz=quiz,
                    result_category=primary,
                )
                AttemptDimensionScore.objects.bulk_create([
                    AttemptDimensionScore(
                        attempt=attempt,
                        dimension_id=dim_id,
                        left_score=s['left'],
                        right_score=s['right'],
                    )
                    for dim_id, s in scores.items()
                ])

        url = reverse('quiz_result', kwargs={'slug': quiz.slug, 'result_slug': primary.slug})
        if secondary:
            url += f'?also={secondary.slug}'
        return redirect(url)

    return render(request, 'quizzes/quiz_detail.html', {'quiz': quiz, 'questions': questions})


def quiz_result(request, slug, result_slug):
    quiz = get_object_or_404(Quiz, slug=slug, is_published=True)
    result_category = get_object_or_404(ResultCategory, quiz=quiz, slug=result_slug)

    session_scores = request.session.get(f'quiz_{quiz.id}_scores', {})
    if not session_scores and request.user.is_authenticated:
        attempt = (
            QuizAttempt.objects
            .filter(user=request.user, result_category=result_category)
            .order_by('-created_at')
            .first()
        )
        if attempt:
            session_scores = {
                str(s.dimension_id): {'left': s.left_score, 'right': s.right_score}
                for s in attempt.dimension_scores.all()
            }

    score_data = []
    for dim in quiz.dimensions.all():
        s = session_scores.get(str(dim.id), {'left': 0.0, 'right': 0.0})
        left = float(s.get('left', 0.0))
        right = float(s.get('right', 0.0))
        total = left + right
        bar_pct = int(abs(right - left) / total * 50) if total > 0 else 0
        winner = 'right' if right > left else 'left' if left > right else 'tie'
        net = right - left
        score_data.append({
            'dimension': dim,
            'left_score': left,
            'right_score': right,
            'bar_pct': bar_pct,
            'winner': winner,
            'net': net,
        })

    also_category = None
    also_slug = request.GET.get('also')
    if also_slug:
        also_category = ResultCategory.objects.filter(quiz=quiz, slug=also_slug).first()

    return render(request, 'quizzes/quiz_result.html', {
        'quiz': quiz,
        'result_category': result_category,
        'score_data': score_data,
        'also_category': also_category,
    })
