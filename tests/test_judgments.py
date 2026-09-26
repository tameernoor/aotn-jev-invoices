from fakes import answers, level

from jev_invoices.rules.judgments import Judgments


def test_attribute_access_reads_a_noul_as_yes():
    j = Judgments(answers(alcohol=0.93, food=0.1))
    assert j.alcohol is True
    assert j.food is False
    assert j.read == ["alcohol", "food"]


def test_middle_values_are_recorded_as_uncertain_once():
    j = Judgments(answers(alcohol=0.5))
    assert j.yes("alcohol") is False
    assert j.no("alcohol") is False
    assert j.uncertain == ["alcohol"]
    assert j.read == ["alcohol"]


def test_thresholds_are_inclusive():
    j = Judgments(answers(a=0.8, b=0.2))
    assert j.yes("a") is True
    assert j.no("b") is True
    assert j.uncertain == []


def test_unread_answers_are_not_recorded():
    j = Judgments(answers(alcohol=0.5, food=0.95))
    assert j.food is True
    assert j.read == ["food"]
    assert j.uncertain == []


def test_choice_is_read():
    j = Judgments(answers(category="food"))
    assert j.choice("category") == "food"
    assert j.read == ["category"]


def test_low_confidence_choice_is_uncertain():
    j = Judgments(
        answers(
            document_kind={
                "type": "choice",
                "value": "invoice",
                "probabilities": {"invoice": 0.5, "reminder": 0.5},
                "confidence": 0.5,
            }
        )
    )
    assert j.choice("document_kind") == "invoice"
    assert j.uncertain == ["document_kind"]
    assert j.read == ["document_kind"]


def test_high_confidence_choice_is_not_uncertain():
    j = Judgments(answers(category="food"))
    assert j.choice("category") == "food"
    assert j.uncertain == []


def test_score_is_read_and_not_marked_uncertain():
    j = Judgments(answers(purpose_detail=level(2)))
    assert j.score("purpose_detail") == 2.0
    assert j.read == ["purpose_detail"]
    assert j.uncertain == []


def test_score_with_middling_probability_of_level_zero_is_uncertain():
    j = Judgments(
        {"purpose_detail": {"type": "score", "value": 1.0, "probabilities": {"0": 0.45, "1": 0.55}}}
    )
    assert j.score("purpose_detail") == 1.0
    assert j.uncertain == ["purpose_detail"]


def test_score_with_high_probability_of_level_zero_is_not_uncertain():
    j = Judgments({"purpose_detail": {"type": "score", "value": 0.0, "probabilities": {"0": 0.97}}})
    assert j.score("purpose_detail") == 0.0
    assert j.uncertain == []


def test_score_with_low_probability_of_level_zero_is_not_uncertain():
    j = Judgments(
        {"purpose_detail": {"type": "score", "value": 1.0, "probabilities": {"0": 0.03, "1": 0.97}}}
    )
    assert j.score("purpose_detail") == 1.0
    assert j.uncertain == []


def test_score_without_probabilities_is_not_uncertain():
    j = Judgments({"purpose_detail": {"type": "score", "value": 1.0}})
    assert j.score("purpose_detail") == 1.0
    assert j.uncertain == []
