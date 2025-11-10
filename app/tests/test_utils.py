from app.core.utils import slugify, weighted_choice


def test_slugify_basic():
    assert slugify("Família Real") == "familia-real"
    assert slugify("Coroas 2025!") == "coroas-2025"


def test_weighted_choice_empty():
    assert weighted_choice([]) is None

