"""ARDS 1.0 submission rules; legacy and practice records remain valid.

The form is stored within ResearchDraft.content and ResearchVersion.form_data JSON.
Do not add student names or other identifiable student-level records to metadata.
"""
from app.domain.errors import ApplicationError

VERSION = "ARDS-1.0"


def validate_standard_submission(content: dict) -> None:
    """Require a complete standard record at submission, never at draft save."""
    if content.get("kind", "research") != "research" or content.get("standard_version") != VERSION:
        return
    researchers = content.get("researchers") or []
    if not researchers or any(
        not all(str(row.get(key) or "").strip() for key in ("full_name", "school", "directorate"))
        for row in researchers
    ):
        raise ApplicationError(422, "Each researcher needs full name, school and directorate")
    if content.get('researchers_mode') == 'linked':
        ids = [row.get('user_id') for row in researchers]
        if any(type(value) is not int or value <= 0 for value in ids) or len(set(ids)) != len(ids):
            raise ApplicationError(422, 'Select distinct registered platform researchers')
    if not str(content.get("research_question") or "").strip():
        raise ApplicationError(422, "Main research question is required")
    if not any(str(item).strip() for item in (content.get("research_objectives") or [])):
        raise ApplicationError(422, "At least one research objective is required")
    if not isinstance(content.get("sample_size"), int) or content["sample_size"] < 1:
        raise ApplicationError(422, "Sample size must be a positive integer")
    if not str(content.get("intervention") or "").strip():
        raise ApplicationError(422, "Intervention summary is required")
    if not any(str(step.get("activity") or "").strip() for step in (content.get("action_plan_steps") or [])):
        raise ApplicationError(422, "At least one action plan step is required")
    if not any(str(item.get("name") or "").strip() for item in (content.get("research_instruments") or [])):
        raise ApplicationError(422, "At least one research instrument is required")
    for key in ("key_findings", "researcher_reflection", "conclusions", "recommendations"):
        if not str(content.get(key) or "").strip():
            raise ApplicationError(422, f"{key} is required to submit ARDS research")
