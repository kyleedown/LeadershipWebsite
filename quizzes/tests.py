import logging
from datetime import timedelta
from itertools import product as iterproduct
from unittest.mock import MagicMock

from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserProfile
from content.models import Article
from .models import (
    AnswerChoice, AttemptDimensionScore, Dimension, DimensionResult,
    Question, Quiz, QuizAttempt, ResultCategory,
)
from .observers import (
    EmailNotificationObserver, LoggingObserver,
    QuizObserver, QuizPublisher, quiz_publisher,
)
from .views import compute_scores, determine_winners, find_result_categories


# ---------------------------------------------------------------------------
# Shared fixture helper
# ---------------------------------------------------------------------------

def make_quiz(slug='leadership-quiz', published=True):
    quiz = Quiz.objects.create(
        title='Leadership Quiz', slug=slug,
        is_published=published, published_date=timezone.now(),
    )
    dim1 = Dimension.objects.create(
        quiz=quiz, name='Style',
        left_name='Transactional', right_name='Transformational',
        left_label='Transactional', right_label='Transformational',
    )
    dim2 = Dimension.objects.create(
        quiz=quiz, name='Focus',
        left_name='Task', right_name='People',
        left_label='Task-oriented', right_label='People-oriented',
    )
    rc_tt = ResultCategory.objects.create(
        quiz=quiz, name='Transactional Task',
        slug='transactional-task', description='TT type.',
    )
    rc_tp = ResultCategory.objects.create(
        quiz=quiz, name='Transactional People',
        slug='transactional-people', description='TP type.',
    )
    rc_rt = ResultCategory.objects.create(
        quiz=quiz, name='Transformational Task',
        slug='transformational-task', description='RT type.',
    )
    rc_rp = ResultCategory.objects.create(
        quiz=quiz, name='Transformational People',
        slug='transformational-people', description='RP type.',
    )
    DimensionResult.objects.create(result_category=rc_tt, dimension=dim1, side='left')
    DimensionResult.objects.create(result_category=rc_tt, dimension=dim2, side='left')
    DimensionResult.objects.create(result_category=rc_tp, dimension=dim1, side='left')
    DimensionResult.objects.create(result_category=rc_tp, dimension=dim2, side='right')
    DimensionResult.objects.create(result_category=rc_rt, dimension=dim1, side='right')
    DimensionResult.objects.create(result_category=rc_rt, dimension=dim2, side='left')
    DimensionResult.objects.create(result_category=rc_rp, dimension=dim1, side='right')
    DimensionResult.objects.create(result_category=rc_rp, dimension=dim2, side='right')
    return quiz, dim1, dim2, rc_tt, rc_tp, rc_rt, rc_rp


# ---------------------------------------------------------------------------
# Task 1: Model tests
# ---------------------------------------------------------------------------

class QuizModelTests(TestCase):

    def test_quiz_str_returns_title(self):
        quiz = Quiz(title='My Quiz', slug='my-quiz')
        self.assertEqual(str(quiz), 'My Quiz')

    def test_quiz_is_published_defaults_false(self):
        quiz = Quiz.objects.create(title='Draft', slug='draft')
        self.assertFalse(quiz.is_published)

    def test_quiz_published_date_defaults_to_now(self):
        before = timezone.now()
        quiz = Quiz.objects.create(title='Timed', slug='timed')
        after = timezone.now()
        self.assertGreaterEqual(quiz.published_date, before)
        self.assertLessEqual(quiz.published_date, after)

    def test_dimension_str(self):
        quiz = Quiz.objects.create(title='Q', slug='q')
        dim = Dimension.objects.create(
            quiz=quiz, name='Style',
            left_name='A', right_name='B',
            left_label='A Label', right_label='B Label',
        )
        self.assertIn('Style', str(dim))
        self.assertIn('Q', str(dim))

    def test_result_category_unique_together_quiz_slug(self):
        quiz, *_ = make_quiz()
        with self.assertRaises(Exception):
            ResultCategory.objects.create(
                quiz=quiz, name='Dup', slug='transactional-task', description='d',
            )

    def test_question_ordering_by_order_field(self):
        quiz, dim1, *_ = make_quiz()
        q3 = Question.objects.create(quiz=quiz, text='Third', order=3,
                                      question_type=Question.SLIDER, dimension=dim1)
        q1 = Question.objects.create(quiz=quiz, text='First', order=1,
                                      question_type=Question.SLIDER, dimension=dim1)
        q2 = Question.objects.create(quiz=quiz, text='Second', order=2,
                                      question_type=Question.SLIDER, dimension=dim1)
        qs = list(Question.objects.filter(quiz=quiz))
        self.assertEqual(qs, [q1, q2, q3])

    def test_attempt_dimension_score_defaults_zero(self):
        quiz, dim1, dim2, rc_tt, *_ = make_quiz()
        user = User.objects.create_user('u', 'u@example.com', 'pw')
        attempt = QuizAttempt.objects.create(user=user, quiz=quiz, result_category=rc_tt)
        score = AttemptDimensionScore.objects.create(attempt=attempt, dimension=dim1)
        self.assertEqual(score.left_score, 0.0)
        self.assertEqual(score.right_score, 0.0)

    def test_quiz_attempt_allows_multiple_per_user(self):
        quiz, dim1, dim2, rc_tt, *_ = make_quiz()
        user = User.objects.create_user('u2', 'u2@example.com', 'pw')
        QuizAttempt.objects.create(user=user, quiz=quiz, result_category=rc_tt)
        QuizAttempt.objects.create(user=user, quiz=quiz, result_category=rc_tt)
        self.assertEqual(QuizAttempt.objects.filter(user=user).count(), 2)


# ---------------------------------------------------------------------------
# Task 2: Observer tests
# ---------------------------------------------------------------------------

class QuizPublisherTests(TestCase):

    def setUp(self):
        self.publisher = QuizPublisher()
        self.mock_quiz = MagicMock()
        self.mock_quiz.title = 'Test Quiz'
        self.mock_quiz.slug = 'test-quiz'

    def test_subscribe_registers_observer(self):
        obs = MagicMock(spec=QuizObserver)
        self.publisher.subscribe(obs)
        self.publisher.notify(self.mock_quiz)
        obs.on_quiz_published.assert_called_once_with(self.mock_quiz)

    def test_unsubscribe_removes_observer(self):
        obs = MagicMock(spec=QuizObserver)
        self.publisher.subscribe(obs)
        self.publisher.unsubscribe(obs)
        self.publisher.notify(self.mock_quiz)
        obs.on_quiz_published.assert_not_called()

    def test_duplicate_subscribe_is_ignored(self):
        obs = MagicMock(spec=QuizObserver)
        self.publisher.subscribe(obs)
        self.publisher.subscribe(obs)
        self.publisher.notify(self.mock_quiz)
        obs.on_quiz_published.assert_called_once_with(self.mock_quiz)

    def test_notify_calls_all_observers(self):
        obs1 = MagicMock(spec=QuizObserver)
        obs2 = MagicMock(spec=QuizObserver)
        self.publisher.subscribe(obs1)
        self.publisher.subscribe(obs2)
        self.publisher.notify(self.mock_quiz)
        obs1.on_quiz_published.assert_called_once_with(self.mock_quiz)
        obs2.on_quiz_published.assert_called_once_with(self.mock_quiz)

    def test_notify_with_no_observers_does_not_raise(self):
        try:
            self.publisher.notify(self.mock_quiz)
        except Exception as exc:
            self.fail(f"notify() raised an unexpected exception: {exc}")

    def test_observer_count_reflects_subscriptions(self):
        self.assertEqual(self.publisher.observer_count, 0)
        obs = MagicMock(spec=QuizObserver)
        self.publisher.subscribe(obs)
        self.assertEqual(self.publisher.observer_count, 1)
        self.publisher.unsubscribe(obs)
        self.assertEqual(self.publisher.observer_count, 0)


class LoggingObserverTests(TestCase):

    def test_logging_observer_emits_info_log(self):
        observer = LoggingObserver()
        mock_quiz = MagicMock()
        mock_quiz.slug = 'my-quiz'
        with self.assertLogs('quizzes.observers', level='INFO') as log_ctx:
            observer.on_quiz_published(mock_quiz)
        self.assertTrue(
            any('my-quiz' in line for line in log_ctx.output),
            'Expected quiz slug in log output.',
        )


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class EmailNotificationObserverTests(TestCase):

    def setUp(self):
        self.publisher = QuizPublisher()
        self.observer = EmailNotificationObserver()
        self.publisher.subscribe(self.observer)
        self.mock_quiz = MagicMock()
        self.mock_quiz.title = 'New Quiz'
        self.mock_quiz.slug = 'new-quiz'

    def test_sends_email_to_opted_in_user(self):
        user = User.objects.create_user('notified', 'notified@example.com', 'pw')
        UserProfile.objects.create(user=user, notify_on_quiz_publish=True)
        self.publisher.notify(self.mock_quiz)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('notified@example.com', mail.outbox[0].to)

    def test_does_not_send_to_opted_out_user(self):
        user = User.objects.create_user('quiet', 'quiet@example.com', 'pw')
        UserProfile.objects.create(user=user, notify_on_quiz_publish=False)
        self.publisher.notify(self.mock_quiz)
        self.assertEqual(len(mail.outbox), 0)

    def test_does_not_send_to_user_without_profile(self):
        User.objects.create_user('noprofile', 'np@example.com', 'pw')
        self.publisher.notify(self.mock_quiz)
        self.assertEqual(len(mail.outbox), 0)

    def test_sends_to_all_opted_in_users_in_one_email(self):
        for i in range(3):
            u = User.objects.create_user(f'user{i}', f'user{i}@example.com', 'pw')
            UserProfile.objects.create(user=u, notify_on_quiz_publish=True)
        self.publisher.notify(self.mock_quiz)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(len(mail.outbox[0].to), 3)

    def test_email_subject_contains_quiz_title(self):
        user = User.objects.create_user('notified2', 'notified2@example.com', 'pw')
        UserProfile.objects.create(user=user, notify_on_quiz_publish=True)
        self.publisher.notify(self.mock_quiz)
        self.assertIn('New Quiz', mail.outbox[0].subject)

    def test_sends_no_email_when_no_opted_in_users(self):
        self.publisher.notify(self.mock_quiz)
        self.assertEqual(len(mail.outbox), 0)

    def test_send_mail_failure_does_not_propagate(self):
        from unittest.mock import patch
        user = User.objects.create_user('notified3', 'notified3@example.com', 'pw')
        UserProfile.objects.create(user=user, notify_on_quiz_publish=True)
        with patch('django.core.mail.send_mail', side_effect=Exception('SMTP error')):
            try:
                self.publisher.notify(self.mock_quiz)
            except Exception as exc:
                self.fail(f"on_quiz_published raised an unexpected exception: {exc}")


# ---------------------------------------------------------------------------
# Task 3: Signal wiring tests
# ---------------------------------------------------------------------------

class QuizPublishSignalTests(TestCase):

    def setUp(self):
        self.counter_obs = MagicMock(spec=QuizObserver)
        quiz_publisher.subscribe(self.counter_obs)

    def tearDown(self):
        quiz_publisher.unsubscribe(self.counter_obs)

    def test_creating_published_quiz_notifies_observers(self):
        Quiz.objects.create(title='Published', slug='published-new', is_published=True)
        self.counter_obs.on_quiz_published.assert_called_once()

    def test_creating_draft_does_not_notify(self):
        Quiz.objects.create(title='Draft', slug='draft-new', is_published=False)
        self.counter_obs.on_quiz_published.assert_not_called()

    def test_draft_to_published_transition_notifies(self):
        quiz = Quiz.objects.create(title='Becoming', slug='becoming', is_published=False)
        self.counter_obs.on_quiz_published.assert_not_called()
        quiz.is_published = True
        quiz.save()
        self.counter_obs.on_quiz_published.assert_called_once()

    def test_re_saving_published_quiz_does_not_re_notify(self):
        quiz = Quiz.objects.create(title='Already', slug='already', is_published=True)
        self.counter_obs.on_quiz_published.assert_called_once()
        quiz.title = 'Already (Edited)'
        quiz.save()
        self.counter_obs.on_quiz_published.assert_called_once()


# ---------------------------------------------------------------------------
# Task 5: quiz_list view tests
# ---------------------------------------------------------------------------

class QuizListViewTests(TestCase):

    def test_quiz_list_ordered_newest_first(self):
        Quiz.objects.create(title='Older', slug='older',
                             is_published=True,
                             published_date=timezone.now() - timedelta(days=1))
        Quiz.objects.create(title='Newer', slug='newer',
                             is_published=True, published_date=timezone.now())
        response = self.client.get(reverse('quiz_list'))
        content = response.content.decode()
        self.assertLess(content.index('Newer'), content.index('Older'))

    def test_quiz_list_returns_200(self):
        response = self.client.get(reverse('quiz_list'))
        self.assertEqual(response.status_code, 200)

    def test_quiz_list_uses_correct_template(self):
        response = self.client.get(reverse('quiz_list'))
        self.assertTemplateUsed(response, 'quizzes/quiz_list.html')

    def test_quiz_list_shows_published_quizzes(self):
        quiz, *_ = make_quiz(slug='published-quiz', published=True)
        response = self.client.get(reverse('quiz_list'))
        self.assertContains(response, quiz.title)

    def test_quiz_list_hides_unpublished_quizzes(self):
        quiz, *_ = make_quiz(slug='draft-quiz', published=False)
        response = self.client.get(reverse('quiz_list'))
        self.assertNotContains(response, quiz.title)

    def test_quiz_list_links_to_detail(self):
        Quiz.objects.create(title='Linked', slug='linked-quiz', is_published=True)
        response = self.client.get(reverse('quiz_list'))
        self.assertContains(response, 'href="/quizzes/linked-quiz/"')


# ---------------------------------------------------------------------------
# Task 6: Quiz detail GET tests
# ---------------------------------------------------------------------------

class QuizDetailGetTests(TestCase):

    def setUp(self):
        self.quiz, self.dim1, self.dim2, *_ = make_quiz()
        self.rank_q = Question.objects.create(
            quiz=self.quiz, text='Rank this', order=1,
            question_type=Question.RANK, dimension=self.dim1,
        )
        AnswerChoice.objects.create(question=self.rank_q, text='Choice A', side='right')
        AnswerChoice.objects.create(question=self.rank_q, text='Choice B', side='left')
        self.slider_q = Question.objects.create(
            quiz=self.quiz, text='Slide this', order=2,
            question_type=Question.SLIDER, dimension=self.dim2,
        )

    def test_detail_returns_200_for_published_quiz(self):
        response = self.client.get(reverse('quiz_detail', kwargs={'slug': self.quiz.slug}))
        self.assertEqual(response.status_code, 200)

    def test_detail_shows_quiz_title(self):
        response = self.client.get(reverse('quiz_detail', kwargs={'slug': self.quiz.slug}))
        self.assertContains(response, 'Leadership Quiz')

    def test_detail_shows_rank_question_choices(self):
        response = self.client.get(reverse('quiz_detail', kwargs={'slug': self.quiz.slug}))
        self.assertContains(response, 'Choice A')
        self.assertContains(response, 'Choice B')

    def test_detail_shows_slider_question_labels(self):
        response = self.client.get(reverse('quiz_detail', kwargs={'slug': self.quiz.slug}))
        self.assertContains(response, 'Task-oriented')
        self.assertContains(response, 'People-oriented')

    def test_detail_returns_404_for_unpublished_quiz(self):
        draft = Quiz.objects.create(title='Draft', slug='draft-quiz', is_published=False)
        response = self.client.get(reverse('quiz_detail', kwargs={'slug': draft.slug}))
        self.assertEqual(response.status_code, 404)

    def test_detail_returns_404_for_nonexistent_slug(self):
        response = self.client.get(reverse('quiz_detail', kwargs={'slug': 'no-such-quiz'}))
        self.assertEqual(response.status_code, 404)

    def test_detail_uses_correct_template(self):
        response = self.client.get(reverse('quiz_detail', kwargs={'slug': self.quiz.slug}))
        self.assertTemplateUsed(response, 'quizzes/quiz_detail.html')


# ---------------------------------------------------------------------------
# Task 7: Scoring helper tests
# ---------------------------------------------------------------------------

class ScoringHelperTests(TestCase):

    def setUp(self):
        self.quiz, self.dim1, self.dim2, self.rc_tt, self.rc_tp, self.rc_rt, self.rc_rp = make_quiz()

    def _make_rank_question(self):
        q = Question.objects.create(
            quiz=self.quiz, text='Rank Q', order=1,
            question_type=Question.RANK, dimension=self.dim1,
        )
        c_r1 = AnswerChoice.objects.create(question=q, text='Right A', side='right')
        c_l1 = AnswerChoice.objects.create(question=q, text='Left B', side='left')
        c_r2 = AnswerChoice.objects.create(question=q, text='Right C', side='right')
        c_l2 = AnswerChoice.objects.create(question=q, text='Left D', side='left')
        return q, c_r1, c_l1, c_r2, c_l2

    def test_rank_question_awards_correct_points(self):
        q, c_r1, c_l1, c_r2, c_l2 = self._make_rank_question()
        questions = Question.objects.filter(pk=q.pk).prefetch_related('choices')
        # Order: c_r1(rank1=4pts,right), c_l1(rank2=3pts,left),
        #         c_r2(rank3=2pts,right), c_l2(rank4=1pt,left)
        post = {f'rank_{q.id}': f'{c_r1.id},{c_l1.id},{c_r2.id},{c_l2.id}'}
        scores = compute_scores(questions, post)
        self.assertAlmostEqual(scores[self.dim1.id]['right'], 6.0)
        self.assertAlmostEqual(scores[self.dim1.id]['left'], 4.0)

    def test_rank_question_reversed_order(self):
        q, c_r1, c_l1, c_r2, c_l2 = self._make_rank_question()
        questions = Question.objects.filter(pk=q.pk).prefetch_related('choices')
        # Reversed: c_l2(4pts,left), c_l1(3pts,left), c_r2(2pts,right), c_r1(1pt,right)
        post = {f'rank_{q.id}': f'{c_l2.id},{c_l1.id},{c_r2.id},{c_r1.id}'}
        scores = compute_scores(questions, post)
        self.assertAlmostEqual(scores[self.dim1.id]['right'], 3.0)
        self.assertAlmostEqual(scores[self.dim1.id]['left'], 7.0)

    def test_slider_positive_adds_to_right(self):
        q = Question.objects.create(
            quiz=self.quiz, text='Slider Q', order=1,
            question_type=Question.SLIDER, dimension=self.dim2,
        )
        questions = Question.objects.filter(pk=q.pk).prefetch_related('choices')
        scores = compute_scores(questions, {f'slider_{q.id}': '70'})
        self.assertAlmostEqual(scores[self.dim2.id]['right'], 0.70)
        self.assertAlmostEqual(scores[self.dim2.id]['left'], 0.0)

    def test_slider_negative_adds_to_left(self):
        q = Question.objects.create(
            quiz=self.quiz, text='Slider Q', order=1,
            question_type=Question.SLIDER, dimension=self.dim2,
        )
        questions = Question.objects.filter(pk=q.pk).prefetch_related('choices')
        scores = compute_scores(questions, {f'slider_{q.id}': '-50'})
        self.assertAlmostEqual(scores[self.dim2.id]['left'], 0.50)
        self.assertAlmostEqual(scores[self.dim2.id]['right'], 0.0)

    def test_slider_zero_contributes_nothing(self):
        q = Question.objects.create(
            quiz=self.quiz, text='Slider Q', order=1,
            question_type=Question.SLIDER, dimension=self.dim2,
        )
        questions = Question.objects.filter(pk=q.pk).prefetch_related('choices')
        scores = compute_scores(questions, {f'slider_{q.id}': '0'})
        self.assertAlmostEqual(scores[self.dim2.id]['left'], 0.0)
        self.assertAlmostEqual(scores[self.dim2.id]['right'], 0.0)

    def test_determine_winners_right_wins(self):
        scores = {self.dim1.id: {'left': 2.0, 'right': 5.0}}
        winners = determine_winners(scores)
        self.assertEqual(winners[self.dim1.id], 'right')

    def test_determine_winners_left_wins(self):
        scores = {self.dim1.id: {'left': 5.0, 'right': 2.0}}
        winners = determine_winners(scores)
        self.assertEqual(winners[self.dim1.id], 'left')

    def test_determine_winners_tie(self):
        scores = {self.dim1.id: {'left': 3.0, 'right': 3.0}}
        winners = determine_winners(scores)
        self.assertEqual(winners[self.dim1.id], 'tie')

    def test_find_result_categories_no_tie(self):
        # dim1=right, dim2=right → Transformational People
        winners = {self.dim1.id: 'right', self.dim2.id: 'right'}
        result = find_result_categories(self.quiz, winners)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].slug, 'transformational-people')

    def test_find_result_categories_all_combinations(self):
        for (s1, s2), expected_slug in [
            (('left', 'left'), 'transactional-task'),
            (('left', 'right'), 'transactional-people'),
            (('right', 'left'), 'transformational-task'),
            (('right', 'right'), 'transformational-people'),
        ]:
            winners = {self.dim1.id: s1, self.dim2.id: s2}
            result = find_result_categories(self.quiz, winners)
            self.assertEqual(len(result), 1, f"Expected 1 result for {s1}/{s2}")
            self.assertEqual(result[0].slug, expected_slug)

    def test_find_result_categories_with_dim1_tie_returns_two(self):
        # dim1=tie, dim2=right → should return rc_tp and rc_rp
        winners = {self.dim1.id: 'tie', self.dim2.id: 'right'}
        result = find_result_categories(self.quiz, winners)
        self.assertEqual(len(result), 2)
        slugs = {r.slug for r in result}
        self.assertIn('transactional-people', slugs)
        self.assertIn('transformational-people', slugs)

    def test_find_result_categories_unscored_dimension_treated_as_flexible(self):
        # dim2 absent from winners (no questions answered for it) →
        # should behave like a tie and return both right-side matches for dim1
        winners = {self.dim1.id: 'right'}  # dim2 not in winners at all
        result = find_result_categories(self.quiz, winners)
        self.assertEqual(len(result), 2)
        slugs = {r.slug for r in result}
        self.assertIn('transformational-task', slugs)
        self.assertIn('transformational-people', slugs)

    def test_find_result_categories_all_dimensions_unscored_returns_all(self):
        # No dimensions in winners → all result categories should be returned
        result = find_result_categories(self.quiz, {})
        self.assertEqual(len(result), 4)


# ---------------------------------------------------------------------------
# Task 8: Quiz detail POST tests
# ---------------------------------------------------------------------------

class QuizDetailPostTests(TestCase):

    def setUp(self):
        self.quiz, self.dim1, self.dim2, self.rc_tt, self.rc_tp, self.rc_rt, self.rc_rp = make_quiz()
        # One slider per dimension so we can control scores cleanly
        self.q1 = Question.objects.create(
            quiz=self.quiz, text='Style slider', order=1,
            question_type=Question.SLIDER, dimension=self.dim1,
        )
        self.q2 = Question.objects.create(
            quiz=self.quiz, text='Focus slider', order=2,
            question_type=Question.SLIDER, dimension=self.dim2,
        )

    def _post_data(self, s1=50, s2=50):
        """POST data pushing both sliders right → Transformational People."""
        return {
            f'slider_{self.q1.id}': str(s1),
            f'slider_{self.q2.id}': str(s2),
        }

    def test_post_redirects_to_quiz_result(self):
        response = self.client.post(
            reverse('quiz_detail', kwargs={'slug': self.quiz.slug}),
            self._post_data(),
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('/quizzes/', response['Location'])
        self.assertIn('/result/', response['Location'])

    def test_post_redirects_to_correct_result_category(self):
        response = self.client.post(
            reverse('quiz_detail', kwargs={'slug': self.quiz.slug}),
            self._post_data(s1=50, s2=50),
        )
        self.assertRedirects(
            response,
            reverse('quiz_result', kwargs={
                'slug': self.quiz.slug,
                'result_slug': 'transformational-people',
            }),
            fetch_redirect_response=False,
        )

    def test_post_saves_attempt_for_logged_in_user(self):
        user = User.objects.create_user('u', 'u@example.com', 'pw')
        self.client.force_login(user)
        self.client.post(
            reverse('quiz_detail', kwargs={'slug': self.quiz.slug}),
            self._post_data(),
        )
        self.assertEqual(QuizAttempt.objects.filter(user=user, quiz=self.quiz).count(), 1)

    def test_post_saves_dimension_scores_for_logged_in_user(self):
        user = User.objects.create_user('u2', 'u2@example.com', 'pw')
        self.client.force_login(user)
        self.client.post(
            reverse('quiz_detail', kwargs={'slug': self.quiz.slug}),
            self._post_data(s1=70, s2=60),
        )
        attempt = QuizAttempt.objects.get(user=user, quiz=self.quiz)
        self.assertEqual(attempt.dimension_scores.count(), 2)

    def test_post_does_not_save_attempt_for_anonymous_user(self):
        self.client.post(
            reverse('quiz_detail', kwargs={'slug': self.quiz.slug}),
            self._post_data(),
        )
        self.assertEqual(QuizAttempt.objects.count(), 0)

    def test_post_stores_scores_in_session(self):
        self.client.post(
            reverse('quiz_detail', kwargs={'slug': self.quiz.slug}),
            self._post_data(s1=50, s2=50),
        )
        session = self.client.session
        self.assertIn(f'quiz_{self.quiz.id}_scores', session)

    def test_post_tie_redirects_with_also_param(self):
        # s1=0 (tie on dim1), s2=50 (right wins on dim2)
        # → both rc_tp (left/right) and rc_rp (right/right) match dim2=right
        response = self.client.post(
            reverse('quiz_detail', kwargs={'slug': self.quiz.slug}),
            self._post_data(s1=0, s2=50),
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('also=', response['Location'])


# ---------------------------------------------------------------------------
# Task 9: Quiz result view tests
# ---------------------------------------------------------------------------

class QuizResultViewTests(TestCase):

    def setUp(self):
        self.quiz, self.dim1, self.dim2, self.rc_tt, self.rc_tp, self.rc_rt, self.rc_rp = make_quiz()
        self.url = reverse('quiz_result', kwargs={
            'slug': self.quiz.slug,
            'result_slug': self.rc_rp.slug,
        })

    def _set_session_scores(self, left1=2.0, right1=5.0, left2=1.0, right2=4.0):
        session = self.client.session
        session[f'quiz_{self.quiz.id}_scores'] = {
            str(self.dim1.id): {'left': left1, 'right': right1},
            str(self.dim2.id): {'left': left2, 'right': right2},
        }
        session.save()

    def test_result_returns_200(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_result_shows_category_name(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'Transformational People')

    def test_result_shows_category_description(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'RP type.')

    def test_result_shows_dimension_scores_from_session(self):
        self._set_session_scores()
        response = self.client.get(self.url)
        self.assertContains(response, 'Transformational')
        self.assertContains(response, 'People')

    def test_result_shows_tie_notice_when_also_param_present(self):
        response = self.client.get(
            self.url + f'?also={self.rc_tp.slug}'
        )
        self.assertContains(response, 'Tie detected')
        self.assertContains(response, self.rc_tp.name)

    def test_result_no_tie_notice_without_also_param(self):
        response = self.client.get(self.url)
        self.assertNotContains(response, 'Tie detected')

    def test_result_returns_404_for_unknown_result_slug(self):
        url = reverse('quiz_result', kwargs={
            'slug': self.quiz.slug,
            'result_slug': 'no-such-result',
        })
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_result_returns_404_for_unknown_quiz_slug(self):
        url = reverse('quiz_result', kwargs={
            'slug': 'no-such-quiz',
            'result_slug': self.rc_rp.slug,
        })
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_result_shows_article_link_when_present(self):
        article = Article.objects.create(
            title='Leadership Article', slug='leadership-article',
            body='Body', is_published=True,
        )
        self.rc_rp.article_1 = article
        self.rc_rp.save()
        response = self.client.get(self.url)
        self.assertContains(response, 'Leadership Article')

    def test_result_uses_attempt_scores_when_no_session_and_logged_in(self):
        user = User.objects.create_user('scorer', 'scorer@example.com', 'pw')
        attempt = QuizAttempt.objects.create(
            user=user, quiz=self.quiz, result_category=self.rc_rp,
        )
        AttemptDimensionScore.objects.create(
            attempt=attempt, dimension=self.dim1, left_score=1.0, right_score=9.0,
        )
        AttemptDimensionScore.objects.create(
            attempt=attempt, dimension=self.dim2, left_score=2.0, right_score=8.0,
        )
        self.client.force_login(user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        score_data = response.context['score_data']
        dim1_entry = next(s for s in score_data if s['dimension'] == self.dim1)
        self.assertAlmostEqual(dim1_entry['right_score'], 9.0)
        dim2_entry = next(s for s in score_data if s['dimension'] == self.dim2)
        self.assertAlmostEqual(dim2_entry['right_score'], 8.0)


# ---------------------------------------------------------------------------
# Admin: QuestionInline dimension filtering
# ---------------------------------------------------------------------------

class QuestionInlineAdminTests(TestCase):

    def setUp(self):
        self.superuser = User.objects.create_superuser('admin', 'admin@example.com', 'pw')
        self.client.force_login(self.superuser)
        self.quiz_a, self.dim_a1, self.dim_a2, *_ = make_quiz(slug='quiz-a')
        self.quiz_b, self.dim_b1, self.dim_b2, *_ = make_quiz(slug='quiz-b')

    def test_question_inline_dimension_dropdown_only_shows_current_quiz_dimensions(self):
        url = f'/admin/quizzes/quiz/{self.quiz_a.pk}/change/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        inline_formsets = response.context['inline_admin_formsets']
        question_formset = next(
            fs for fs in inline_formsets
            if fs.opts.model.__name__ == 'Question'
        )
        dim_field = question_formset.formset.empty_form.fields['dimension']
        dim_ids = set(dim_field.queryset.values_list('id', flat=True))
        self.assertIn(self.dim_a1.id, dim_ids)
        self.assertIn(self.dim_a2.id, dim_ids)
        self.assertNotIn(self.dim_b1.id, dim_ids)
        self.assertNotIn(self.dim_b2.id, dim_ids)

    def test_question_inline_has_no_extra_forms_to_prevent_validation_interference(self):
        # extra=1 caused empty form with question_type='rank' pre-selected →
        # has_changed()=True → text required validation fails → quiz save aborted.
        url = f'/admin/quizzes/quiz/{self.quiz_a.pk}/change/'
        response = self.client.get(url)
        inline_formsets = response.context['inline_admin_formsets']
        question_formset = next(
            fs for fs in inline_formsets
            if fs.opts.model.__name__ == 'Question'
        )
        self.assertEqual(len(question_formset.formset.extra_forms), 0)

    def test_adding_second_dimension_via_admin_succeeds(self):
        # Create a simple quiz with 1 dimension (no result categories).
        quiz = Quiz.objects.create(title='SimpleQ', slug='simple-q', is_published=False)
        dim1 = Dimension.objects.create(
            quiz=quiz, name='D1',
            left_name='L1', right_name='R1',
            left_label='LL1', right_label='RL1',
        )
        url = f'/admin/quizzes/quiz/{quiz.pk}/change/'

        # GET the page to discover prefixes AND simulate what the browser
        # actually sends (including any extra forms the admin renders).
        get_response = self.client.get(url)
        self.assertEqual(get_response.status_code, 200)
        inline_formsets = get_response.context['inline_admin_formsets']

        dim_fs = next(fs for fs in inline_formsets if fs.opts.model.__name__ == 'Dimension')
        q_fs = next(fs for fs in inline_formsets if fs.opts.model.__name__ == 'Question')
        rc_fs = next(fs for fs in inline_formsets if fs.opts.model.__name__ == 'ResultCategory')

        dim_prefix = dim_fs.formset.prefix
        q_prefix = q_fs.formset.prefix
        rc_prefix = rc_fs.formset.prefix

        # Use actual TOTAL_FORMS from admin rendering so this test catches
        # the extra=1 bug (pre-selected question_type causes has_changed=True →
        # text-required validation failure → entire save aborted).
        q_total = len(q_fs.formset.forms)
        q_initial = q_fs.formset.initial_form_count()

        post_data = {
            'title': quiz.title,
            'slug': quiz.slug,
            'description': '',
            'is_published': '',
            'published_date_0': '2026-05-18',
            'published_date_1': '00:00:00',
            'article': '',
            # DimensionInline: keep dim1, add dim2
            f'{dim_prefix}-TOTAL_FORMS': '2',
            f'{dim_prefix}-INITIAL_FORMS': '1',
            f'{dim_prefix}-MIN_NUM_FORMS': '0',
            f'{dim_prefix}-MAX_NUM_FORMS': '1000',
            f'{dim_prefix}-0-id': str(dim1.pk),
            f'{dim_prefix}-0-quiz': str(quiz.pk),
            f'{dim_prefix}-0-name': dim1.name,
            f'{dim_prefix}-0-left_name': dim1.left_name,
            f'{dim_prefix}-0-right_name': dim1.right_name,
            f'{dim_prefix}-0-left_label': dim1.left_label,
            f'{dim_prefix}-0-right_label': dim1.right_label,
            f'{dim_prefix}-1-id': '',
            f'{dim_prefix}-1-name': 'D2',
            f'{dim_prefix}-1-left_name': 'L2',
            f'{dim_prefix}-1-right_name': 'R2',
            f'{dim_prefix}-1-left_label': 'LL2',
            f'{dim_prefix}-1-right_label': 'RL2',
            # ResultCategoryInline: none
            f'{rc_prefix}-TOTAL_FORMS': '0',
            f'{rc_prefix}-INITIAL_FORMS': '0',
            f'{rc_prefix}-MIN_NUM_FORMS': '0',
            f'{rc_prefix}-MAX_NUM_FORMS': '1000',
            # QuestionInline: use actual admin-rendered count.
            # With extra=1 this includes an empty form with question_type
            # pre-selected to 'rank', which the browser always submits.
            f'{q_prefix}-TOTAL_FORMS': str(q_total),
            f'{q_prefix}-INITIAL_FORMS': str(q_initial),
            f'{q_prefix}-MIN_NUM_FORMS': '0',
            f'{q_prefix}-MAX_NUM_FORMS': '1000',
        }
        # Simulate browser submitting each extra question form with the
        # pre-selected question_type value and blank text/dimension.
        for i in range(q_initial, q_total):
            post_data[f'{q_prefix}-{i}-text'] = ''
            post_data[f'{q_prefix}-{i}-order'] = '0'
            post_data[f'{q_prefix}-{i}-question_type'] = 'rank'
            post_data[f'{q_prefix}-{i}-dimension'] = ''

        response = self.client.post(url, post_data)
        self.assertEqual(response.status_code, 302,
            msg='Admin save should succeed (redirect). A 200 means form errors.')
        quiz.refresh_from_db()
        self.assertEqual(quiz.dimensions.count(), 2)


# ---------------------------------------------------------------------------
# Admin: DimensionResultInline dimension filtering
# ---------------------------------------------------------------------------

class DimensionResultInlineAdminTests(TestCase):

    def setUp(self):
        self.superuser = User.objects.create_superuser('admin2', 'admin2@example.com', 'pw')
        self.client.force_login(self.superuser)
        self.quiz_a, self.dim_a1, self.dim_a2, _, _, _, self.rc_rp_a = make_quiz(slug='dim-quiz-a')
        self.quiz_b, self.dim_b1, self.dim_b2, *_ = make_quiz(slug='dim-quiz-b')

    def test_dimension_result_inline_only_shows_quiz_dimensions(self):
        """DimensionResult inline on ResultCategory page must not show dimensions from other quizzes."""
        url = f'/admin/quizzes/resultcategory/{self.rc_rp_a.pk}/change/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        inline_formsets = response.context['inline_admin_formsets']
        dr_formset = next(
            fs for fs in inline_formsets
            if fs.opts.model.__name__ == 'DimensionResult'
        )
        dim_field = dr_formset.formset.empty_form.fields['dimension']
        dim_ids = set(dim_field.queryset.values_list('id', flat=True))
        self.assertIn(self.dim_a1.id, dim_ids)
        self.assertIn(self.dim_a2.id, dim_ids)
        self.assertNotIn(self.dim_b1.id, dim_ids)
        self.assertNotIn(self.dim_b2.id, dim_ids)
