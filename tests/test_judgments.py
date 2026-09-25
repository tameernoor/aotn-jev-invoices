from fakes import answers

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
