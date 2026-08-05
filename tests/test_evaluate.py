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
    bad = tmp_path / "questions.txt"
    bad.write_text("ask: Something?\npages:\n", encoding="utf-8")
    with pytest.raises(EvalError, match="lists no pages"):
        load_questions(bad)


def test_a_missing_question_file_explains_itself(tmp_path):
    with pytest.raises(EvalError, match="hand-written"):
        load_questions(tmp_path / "absent.txt")


def test_quotes_and_apostrophes_need_no_escaping(tmp_path):
    """The whole reason this format is not TOML: pasted prose must just work."""
    path = tmp_path / "questions.txt"
    path.write_text(
        'ask: What did Jefferson want?\n'
        'pages: 210\n'
        'why: Page 210 reads "an empire of liberty", and Jefferson\'s vision\n'
        '  wrapped across lines — with dashes, \'quotes\' and = signs.\n',
        encoding="utf-8",
    )
    question = load_questions(path)[0]
    assert '"an empire of liberty"' in question.why
    assert "Jefferson's vision wrapped across lines" in question.why


def test_a_blank_line_separates_entries(tmp_path):
    path = tmp_path / "questions.txt"
    path.write_text(
        "ask: First?\npages: 1\n\nask: Second?\npages: 2\n", encoding="utf-8"
    )
    questions = load_questions(path)
    assert [q.ask for q in questions] == ["First?", "Second?"]
    assert [q.pages for q in questions] == [(1,), (2,)]


def test_pages_accept_any_sane_separator(tmp_path):
    """A hand-typed list should not care about spaces or commas."""
    path = tmp_path / "questions.txt"
    path.write_text("ask: Q?\npages: 210, 211  212\n", encoding="utf-8")
    assert load_questions(path)[0].pages == (210, 211, 212)


def test_comments_and_trailing_blank_lines_are_ignored(tmp_path):
    path = tmp_path / "questions.txt"
    path.write_text(
        "# a note\n\nask: Q?\npages: 5\n# another note\n\n\n", encoding="utf-8"
    )
    assert len(load_questions(path)) == 1


def test_a_stray_line_before_any_field_is_reported_with_its_number(tmp_path):
    path = tmp_path / "questions.txt"
    path.write_text("this is not a field\nask: Q?\npages: 1\n", encoding="utf-8")
    with pytest.raises(EvalError, match="line 1"):
        load_questions(path)


def test_the_why_field_is_optional(tmp_path):
    path = tmp_path / "questions.txt"
    path.write_text("ask: Q?\npages: 7\n", encoding="utf-8")
    assert load_questions(path)[0].why == ""
