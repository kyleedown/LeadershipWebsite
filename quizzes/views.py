from itertools import product as iterproduct

from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .models import (
    AnswerChoice, AttemptDimensionScore, Dimension,
    Question, Quiz, QuizAttempt, ResultCategory,
)



def compute_scores(questions, post_data):
    dimension_scores = {}
    category_scores = {}

    for question in questions:
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
                if choice.category_id:
                    category_scores[choice.category_id] = (
                        category_scores.get(choice.category_id, 0) + points
                    )
                elif question.dimension_id and choice.side:
                    dim_id = question.dimension_id
                    if dim_id not in dimension_scores:
                        dimension_scores[dim_id] = {'left': 0.0, 'right': 0.0}
                    dimension_scores[dim_id][choice.side] += points

        elif question.question_type == Question.SLIDER and question.dimension_id:
            dim_id = question.dimension_id
            try:
                raw = max(-100, min(100, int(post_data.get(f'slider_{question.id}', 0))))
            except (ValueError, TypeError):
                raw = 0
            if dim_id not in dimension_scores:
                dimension_scores[dim_id] = {'left': 0.0, 'right': 0.0}
            choices = list(question.choices.all())
            if choices:
                # Snap slider value to the nearest choice by position index.
                # Choices are ordered: index 0 = leftmost, index n-1 = rightmost.
                n = len(choices)
                idx = round((raw + 100) / 200 * (n - 1))
                choice = choices[max(0, min(n - 1, idx))]
                if choice.side:
                    dimension_scores[dim_id][choice.side] += choice.points
            else:
                value = raw / 100.0
                if value > 0:
                    dimension_scores[dim_id]['right'] += value
                elif value < 0:
                    dimension_scores[dim_id]['left'] += abs(value)

    return dimension_scores, category_scores


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
        dimension_scores, category_scores = compute_scores(questions, request.POST)

        if category_scores and not dimension_scores:
            # Pure category mode: highest-scoring category wins.
            ordered_ids = sorted(category_scores, key=lambda k: category_scores[k], reverse=True)
            all_ranked = [
                rc
                for cat_id in ordered_ids
                for rc in [ResultCategory.objects.filter(id=cat_id).first()]
                if rc
            ]
            # Only surface a runner-up if scores are genuinely tied at the top.
            top_score = category_scores.get(ordered_ids[0], 0) if ordered_ids else 0
            second_score = category_scores.get(ordered_ids[1], 0) if len(ordered_ids) > 1 else -1
            result_categories = all_ranked if top_score == second_score else all_ranked[:1]
        elif category_scores and dimension_scores:
            # Mixed: filter by dimension outcomes, then rank survivors by category score.
            winners = determine_winners(dimension_scores)
            candidates = find_result_categories(quiz, winners)
            result_categories = sorted(
                candidates,
                key=lambda rc: category_scores.get(rc.id, 0),
                reverse=True,
            )
        else:
            winners = determine_winners(dimension_scores)
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
            str(dim_id): s for dim_id, s in dimension_scores.items()
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
                    for dim_id, s in dimension_scores.items()
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


@staff_member_required
def dimension_names_api(request):
    dim_id = request.GET.get('dimension_id')
    if not dim_id:
        return JsonResponse({}, status=400)
    try:
        dim = Dimension.objects.get(pk=dim_id)
    except Dimension.DoesNotExist:
        return JsonResponse({}, status=404)
    return JsonResponse({'left': dim.left_name, 'right': dim.right_name})
