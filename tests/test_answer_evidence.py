from unittest.mock import Mock

import pytest

from app.agent import eval_agent
from app.agent.contracts import EvalScores
from app.agent.evidence_context import AnswerCitationError
from app.agent.rag import nodes
from app.agent.rag.state import RAGState
from app.agent.seed_patient import get_case


@pytest.mark.parametrize("case_key", ["case_a", "case_b", "case_c"])
def test_evaluation_receives_same_evidence_and_entire_answer(monkeypatch, case_key):
    patient = get_case(case_key)
    chunks = [nodes._build_patient_summary_chunk(patient, patient["patient_id"])]
    prompts = []

    def evaluate(messages, **kwargs):
        prompts.append(messages[1]["content"])
        return EvalScores(faithfulness=0.9).model_dump(), "test-model"

    monkeypatch.setattr(eval_agent.settings, "openrouter_api_key", "test-key")
    monkeypatch.setattr(eval_agent, "call_llm_json", evaluate)
    answer = "A detailed answer. " * 150 + "Last claim must also be evaluated [1]."
    result = eval_agent.run_eval("Summarise labs", answer, chunks)
    assert not result["skipped"]
    assert nodes._format_chunks(chunks) in prompts[0]
    assert answer in prompts[0]
    for lab in patient["summary"]["lab_results"]:
        assert f"{lab['test_name']}: {lab['value']}" in prompts[0]


def answer_state():
    return RAGState(question="Summarise labs", context_sufficient=True, all_chunks=[
        {"text": "BNP: 1840 pg/mL", "source_doc": "labs.txt"},
        {"text": "Creatinine: 138 µmol/L", "source_doc": "follow-up.txt"},
    ])


@pytest.mark.parametrize("initial", ["BNP is high.", "BNP is high [99].", "BNP is high [0][1]."])
def test_missing_or_invalid_citations_get_one_repair(monkeypatch, initial):
    generate = Mock(side_effect=[initial, "BNP is high [1]."])
    monkeypatch.setattr(nodes, "_groq_text", generate)
    result = nodes.generator_node(answer_state())
    assert result["raw_answer"] == "BNP is high [1]."
    assert [c["source_doc"] for c in result["citations"]] == ["labs.txt"]
    assert generate.call_count == 2
    assert generate.call_args_list[0].kwargs["system"] == generate.call_args_list[1].kwargs["system"]


@pytest.mark.parametrize("answer", ["BNP is high.", "BNP is high [1][99]."])
def test_uncited_or_invented_sources_never_become_an_answer(monkeypatch, answer):
    generate = Mock(return_value=answer)
    monkeypatch.setattr(nodes, "_groq_text", generate)
    with pytest.raises(AnswerCitationError, match="could not be linked"):
        nodes.generator_node(answer_state())
    assert generate.call_count == 2


def test_valid_citations_map_to_original_source_numbers_once(monkeypatch):
    generate = Mock(return_value="Creatinine is elevated [2]. BNP is elevated [1][2].")
    monkeypatch.setattr(nodes, "_groq_text", generate)
    result = nodes.generator_node(answer_state())
    assert [c["ref"] for c in result["citations"]] == [1, 2]
    assert [c["source_doc"] for c in result["citations"]] == ["labs.txt", "follow-up.txt"]
    assert generate.call_count == 1
