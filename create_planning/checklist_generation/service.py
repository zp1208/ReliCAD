from create_planning.checklist_generation.skills.candidate_generator import generate_candidate_checks
from create_planning.checklist_generation.skills.normalizer import (
    normalize_candidate_checks,
)


def generate_checklist(*, intent, decision, user_input: str = ""):
    candidates = generate_candidate_checks(
        intent=intent,
        decision=decision or {},
        user_input=user_input,
    )
    return normalize_candidate_checks(candidates=candidates)
