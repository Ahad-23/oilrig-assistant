"""DeepEval Evaluation Gate for Asset Intelligence Copilot.
Validates end-to-end agentic workflows using Gemma 4 with tool calling.
Evaluates citation grounding, negative constraints, contradiction detection,
multi-user privacy isolation, and strict no-emoji enforcement.
"""

import pytest
import re
import sys
from typing import List, Optional
from deepeval.metrics import BaseMetric
from deepeval.test_case import LLMTestCase
from deepeval import assert_test

from src.agent.graph import invoke_copilot
from src.memory.session_store import SessionStore


# Ensure UTF-8 stream encoding on Windows to prevent UnicodeEncodeError in Rich
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


# ---------------------------------------------------------------------------
# Custom DeepEval Metrics
# ---------------------------------------------------------------------------

class NoEmojiMetric(BaseMetric):
    """Verifies that the agent response contains strictly zero emoji characters."""

    def __init__(self, threshold: float = 1.0):
        self.threshold = threshold
        self.score = 0.0
        self.success = False

    def measure(self, test_case: LLMTestCase) -> float:
        text = test_case.actual_output or ""
        emoji_pattern = re.compile(
            "[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F900-\U0001F9FF\U0001FA70-\U0001FAFF]+",
            flags=re.UNICODE
        )
        has_emojis = bool(emoji_pattern.search(text))
        self.score = 0.0 if has_emojis else 1.0
        self.success = self.score >= self.threshold
        return self.score

    async def a_measure(self, test_case: LLMTestCase) -> float:
        return self.measure(test_case)

    def is_successful(self) -> bool:
        return self.success

    @property
    def __name__(self):
        return "Strict No-Emoji Enforcement"


class CitationGroundingMetric(BaseMetric):
    """Verifies that assertions are grounded with bracketed record IDs."""

    def __init__(self, threshold: float = 0.7, expected_prefix: Optional[str] = None):
        self.threshold = threshold
        self.expected_prefix = expected_prefix
        self.score = 0.0
        self.success = False

    def measure(self, test_case: LLMTestCase) -> float:
        text = test_case.actual_output or ""
        citations = re.findall(r"\[(INS-[A-Za-z0-9-]+|MNT-[A-Za-z0-9-]+|CTX-[A-Za-z0-9-]+|SR-[0-9]+|RC-[0-9]+|SOP-[A-Za-z0-9-]+)\]", text)
        if not citations:
            self.score = 0.0
        else:
            if self.expected_prefix:
                matches_prefix = any(c.startswith(self.expected_prefix) for c in citations)
                self.score = 1.0 if matches_prefix else 0.5
            else:
                self.score = 1.0
        self.success = self.score >= self.threshold
        return self.score

    async def a_measure(self, test_case: LLMTestCase) -> float:
        return self.measure(test_case)

    def is_successful(self) -> bool:
        return self.success

    @property
    def __name__(self):
        return "Citation Grounding Metric"


class NegativeConstraintMetric(BaseMetric):
    """Verifies that the agent reports missing data rather than hallucinating root causes."""

    def __init__(self, threshold: float = 1.0):
        self.threshold = threshold
        self.score = 0.0
        self.success = False

    def measure(self, test_case: LLMTestCase) -> float:
        text = (test_case.actual_output or "").lower()
        honest_keywords = [
            "no recorded reason",
            "not documented",
            "not recorded",
            "no reason recorded",
            "no documented reason",
            "no 'root cause' recorded",
            "no root cause recorded",
            "unspecified"
        ]
        has_honest_acknowledgment = (
            any(kw in text for kw in honest_keywords)
            or ("no" in text and ("recorded" in text or "documented" in text))
            or "not recorded" in text
            or "not documented" in text
        )
        self.score = 1.0 if has_honest_acknowledgment else 0.0
        self.success = self.score >= self.threshold
        return self.score

    async def a_measure(self, test_case: LLMTestCase) -> float:
        return self.measure(test_case)

    def is_successful(self) -> bool:
        return self.success

    @property
    def __name__(self):
        return "Negative Constraint Honesty Metric"


class ConflictSurfacingMetric(BaseMetric):
    """Verifies that the agent explicitly flags contradictions between claims and sensors."""

    def __init__(self, threshold: float = 1.0):
        self.threshold = threshold
        self.score = 0.0
        self.success = False

    def measure(self, test_case: LLMTestCase) -> float:
        text = (test_case.actual_output or "").lower()
        conflict_keywords = [
            "conflict",
            "contradict",
            "discrepancy",
            "disagree",
            "mismatch",
            "shut in"
        ]
        detected = any(kw in text for kw in conflict_keywords)
        self.score = 1.0 if detected else 0.0
        self.success = self.score >= self.threshold
        return self.score

    async def a_measure(self, test_case: LLMTestCase) -> float:
        return self.measure(test_case)

    def is_successful(self) -> bool:
        return self.success

    @property
    def __name__(self):
        return "Conflict Surfacing Metric"


# ---------------------------------------------------------------------------
# DeepEval Test Suite
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_deepeval_q1_single_well_status():
    """
    Evaluates Q1: Current status of WELL-0001.
    Verifies delta_T calculation, non-producing evaluation, inspector Ryan Brooks,
    citation grounding, and no-emoji compliance.
    """
    res = await invoke_copilot(
        user_query="What is the current operational status of WELL-0001? Include temperatures and who inspected it.",
        user_id="USR-OP-001",
        session_id="eval_session_q1"
    )
    narrative = res["narrative"]

    test_case = LLMTestCase(
        input="What is the current operational status of WELL-0001? Include temperatures and who inspected it.",
        actual_output=narrative
    )

    metrics = [
        NoEmojiMetric(),
        CitationGroundingMetric(threshold=0.7, expected_prefix="INS-"),
        ConflictSurfacingMetric()
    ]
    for m in metrics:
        m.measure(test_case)

    assert_test(test_case, metrics)
    assert "non-producing" in narrative.lower() or "shut in" in narrative.lower()
    assert "ryan brooks" in narrative.lower()
    assert "3.2" in narrative


@pytest.mark.asyncio
async def test_deepeval_q2_negative_constraint():
    """
    Evaluates Q2: Negative constraint enforcement.
    When asked for the root cause of an unrecorded downtime reason,
    the copilot must explicitly acknowledge that no reason was recorded
    rather than hallucinating causes.
    """
    res = await invoke_copilot(
        user_query="Why was WELL-0001 shut down during its maintenance? What is the root cause recorded in the logs?",
        user_id="USR-OP-001",
        session_id="eval_session_q2"
    )
    narrative = res["narrative"]

    test_case = LLMTestCase(
        input="Why was WELL-0001 shut down during its maintenance? What is the root cause recorded in the logs?",
        actual_output=narrative
    )

    metrics = [
        NoEmojiMetric(),
        NegativeConstraintMetric()
    ]
    for m in metrics:
        m.measure(test_case)

    assert_test(test_case, metrics)


@pytest.mark.asyncio
async def test_deepeval_multi_user_session_isolation():
    """
    Evaluates Q11 vs Q16: Strict privacy and session isolation.
    Turn 1: Michael Turner queries Area 1 downtime and follows up on maintenance costs.
    Turn 2: Jessica Reed in a separate session asks about 'these wells' and must NOT
            inherit Michael Turner's contextual entities.
    """
    store = SessionStore.get_instance()
    store.clear_user_sessions("USR-ENG-001")
    store.clear_user_sessions("USR-OP-002")

    # Michael Turner Turn 1: Top downtime wells in Northeast Block 7 (Q6)
    res_m1 = await invoke_copilot(
        user_query="Which 3 wells in Northeast Block 7 had the most downtime in the last 4 months?",
        user_id="USR-ENG-001",
        session_id="session_michael_turner"
    )
    assert "WELL-" in res_m1["narrative"]

    # Michael Turner Turn 2: Follow-up referencing "these wells" (Q11)
    res_m2 = await invoke_copilot(
        user_query="For the three wells we discussed, what have repairs cost this year?",
        user_id="USR-ENG-001",
        session_id="session_michael_turner"
    )
    # Michael's session should resolve the wells discussed in Turn 1
    assert "cost" in res_m2["narrative"].lower() or "$" in res_m2["narrative"] or "usd" in res_m2["narrative"].lower()

    # Jessica Reed Turn 1: Completely separate user asks about "the three wells we discussed yesterday" (Q16)
    res_j = await invoke_copilot(
        user_query="For the three wells we discussed yesterday, what have repairs cost this year?",
        user_id="USR-OP-002",
        session_id="session_jessica_reed"
    )
    # Jessica has no prior context, so the agent must indicate missing asset context or no prior conversation
    narrative_j = res_j["narrative"].lower()
    assert (
        "no earlier conversation" in narrative_j
        or "no prior conversation" in narrative_j
        or "which wells" in narrative_j
        or "specify" in narrative_j
        or "no wells" in narrative_j
        or "please provide" in narrative_j
        or "not specified" in narrative_j
        or "no record" in narrative_j
    )


@pytest.mark.asyncio
async def test_deepeval_q17_sensor_claim_contradiction():
    """
    Evaluates Q17: Telemetry vs human claim contradiction.
    Tyler Hughes claims WELL-0175 is running, but thermal telemetry shows delta_T of 0.4 C.
    The copilot must detect the contradiction, present both perspectives, and not pick sides.
    """
    res = await invoke_copilot(
        user_query="Tyler Hughes reported that WELL-0175 is running normally. Can you verify this claim?",
        user_id="USR-OP-001",
        session_id="eval_session_q17"
    )
    narrative = res["narrative"]

    test_case = LLMTestCase(
        input="Tyler Hughes reported that WELL-0175 is running normally. Can you verify this claim?",
        actual_output=narrative
    )

    metrics = [
        NoEmojiMetric(),
        ConflictSurfacingMetric(),
        CitationGroundingMetric(threshold=0.5)
    ]
    for m in metrics:
        m.measure(test_case)

    assert_test(test_case, metrics)
    assert "0.4" in narrative or "non-producing" in narrative.lower() or "tyler hughes" in narrative.lower()
