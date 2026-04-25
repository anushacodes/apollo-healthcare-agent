import pytest
from app.agent.seed_patient import get_case


@pytest.fixture
def case_a():
    return get_case("case_a")


@pytest.fixture
def case_b():
    return get_case("case_b")
