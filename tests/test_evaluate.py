"""Tests for retrieval scoring.

The metrics are the point of the harness, so they are tested with hand-checked
numbers rather than trusted. A scoring bug would be worse than no measurement:
it would produce a confident figure to tune the system against, and quote in an
interview.
"""

from __future__ import annotations

import pytest

from cliopedia.evaluate import (
    EvalError,
    Question,
    hit_rate,
    load_questions,
    mean_reciprocal_rank,
    score,
)

Q = Question(ask="What caused the Louisiana Purchase?", pages=(210, 211))


def test_correct_page_first_ranks_one():
    assert score(Q, [210, 400, 500, 600]).rank == 1


def test_correct_page_fourth_ranks_four():
    assert score(Q, [400, 500, 600, 211]).rank == 4


def test_either_expected_page_counts():
    """An answer spanning a page boundary should not be penalised."""
    assert score(Q, [211]).rank == 1
    assert score(Q, [210]).rank == 1


def test_the_earliest_correct_page_sets_the_rank():
    assert score(Q, [400, 211, 210]).rank == 2


def test_a_miss_has_no_rank_and_does_not_count_as_a_hit():
    result = score(Q, [400, 500, 600, 700])
    assert result.rank is None
    assert result.hit is False
    assert result.reciprocal_rank == 0.0


def test_empty_retrieval_is_a_miss_not_a_crash():
    assert score(Q, []).hit is False


def test_hit_rate_is_the_fraction_that_found_anything():
    results = [score(Q, [210]), score(Q, [999]), score(Q, [211]), score(Q, [888])]
    assert hit_rate(results) == 0.5


def test_mrr_rewards_ranking_the_right_page_first():
    """Two runs, same hit rate, different quality — MRR must separate them."""
    ranked_first = [score(Q, [210, 9, 9, 9]), score(Q, [211, 9, 9, 9])]
    ranked_last = [score(Q, [9, 9, 9, 210]), score(Q, [9, 9, 9, 211])]
    assert hit_rate(ranked_first) == hit_rate(ranked_last) == 1.0
    assert mean_reciprocal_rank(ranked_first) == 1.0
    assert mean_reciprocal_rank(ranked_last) == 0.25


def test_mrr_of_a_known_mix():
    """Hand-computed: ranks 1, 2 and a miss → (1 + 0.5 + 0) / 3."""
    results = [score(Q, [210]), score(Q, [9, 211]), score(Q, [9, 9])]
    assert mean_reciprocal_rank(results) == pytest.approx((1 + 0.5 + 0) / 3)


def test_metrics_on_no_questions_are_zero_not_a_division_error():
    assert hit_rate([]) == 0.0
    assert mean_reciprocal_rank([]) == 0.0


def test_the_shipped_question_set_parses():
    """The committed file must always load — it is the harness's only input."""
    questions = load_questions()
    assert questions
    for question in questions:
        assert question.ask.strip()
        assert question.pages
        assert all(isinstance(p, int) and p > 0 for p in question.pages)


def test_a_question_with_no_expected_pages_is_rejected(tmp_path):
    """An entry with no gold page silently scores zero and looks like a failure."""
    bad = tmp_path / "questions.toml"
    bad.write_text('[[question]]\nask = "Something?"\npages = []\n', encoding="utf-8")
    with pytest.raises(EvalError, match="no expected pages"):
        load_questions(bad)


def test_a_missing_question_file_explains_itself(tmp_path):
    with pytest.raises(EvalError, match="hand-written"):
        load_questions(tmp_path / "absent.toml")


def test_a_multiline_value_explains_the_fix(tmp_path):
    """The commonest hand-editing slip: a `why` pasted from a PDF wraps."""
    bad = tmp_path / "questions.toml"
    bad.write_text(
        '[[question]]\nask = "Something?"\npages = [1]\n'
        'why = "a line\nand another line"\n',
        encoding="utf-8",
    )
    with pytest.raises(EvalError, match="triple-quoted"):
        load_questions(bad)


def test_a_triple_quoted_value_parses(tmp_path):
    good = tmp_path / "questions.toml"
    good.write_text(
        '[[question]]\nask = "Something?"\npages = [1]\n'
        "why = '''a line\nand another, with \"quotes\" in it'''\n",
        encoding="utf-8",
    )
    questions = load_questions(good)
    assert len(questions) == 1
    assert "quotes" in questions[0].why
