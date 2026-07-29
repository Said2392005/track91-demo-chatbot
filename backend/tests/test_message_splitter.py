"""Unit tests for the splitter's mechanics — see test_splitter_eval.py for whether it's
actually trustworthy on realistic input (it currently is not; not wired into the main
pipeline)."""

from app.nlu.message_splitter import split_conjunctions


def test_no_conjunction_returns_single_fragment_list():
    assert split_conjunctions("Where is MH12AB1234?") == ["Where is MH12AB1234?"]


def test_splits_on_and():
    assert split_conjunctions("list my drivers and show vehicle locations") == [
        "list my drivers",
        "show vehicle locations",
    ]


def test_splits_on_also():
    assert split_conjunctions("list my drivers also show vehicle locations") == [
        "list my drivers",
        "show vehicle locations",
    ]


def test_splits_on_multiple_conjunctions():
    fragments = split_conjunctions("show drivers and show vehicles and check alerts")
    assert fragments == ["show drivers", "show vehicles", "check alerts"]


def test_word_boundary_does_not_match_inside_other_words():
    """"brand" contains the letters "and" but must not be treated as a conjunction."""
    assert split_conjunctions("What's the brand of MH12AB1234?") == ["What's the brand of MH12AB1234?"]


def test_case_insensitive():
    assert split_conjunctions("show drivers AND show vehicles") == ["show drivers", "show vehicles"]


def test_strips_whitespace_and_punctuation_from_fragments():
    assert split_conjunctions("show drivers, and also show vehicles.") == ["show drivers", "show vehicles"]


def test_trailing_conjunction_with_nothing_after_it_falls_back_to_unsplit():
    """Splitting would leave only one non-empty fragment — same as no split happening at all,
    so the original utterance is returned unmodified rather than a lossy single fragment."""
    assert split_conjunctions("show drivers and") == ["show drivers and"]
