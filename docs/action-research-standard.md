# PARP Action Research Digital Standard — ARDS 1.0

ARDS 1.0 is a **platform data contract**, not an externally accredited academic standard. English field keys are canonical and are displayed using Arabic/English labels in the PARP frontend.

## Sections and fields

| Section | Field keys | Required for a completed ARDS submission |
| --- | --- | --- |
| A. Research identification | `title`, `title_en`, `research_field`, `subject_area`, `academic_year`, `research_language`, `target_grades`, `keywords`, `researchers` | title, research_field, researchers |
| B. Research problem | `problem`, `research_context`, `evidence_of_problem`, `problem_significance` | problem |
| C. Questions and objectives | `research_question`, `sub_research_questions`, `research_objectives`, `research_hypothesis` | research_question, research_objectives |
| D. Participants and setting | `target_population`, `sample_size`, `participant_characteristics`, `research_setting`, `research_start_date`, `research_end_date` | sample_size |
| E. Action and intervention | `intervention_strategy`, `intervention`, `intervention_description`, `action_plan_steps`, `learning_activities`, `resources_used` | intervention, action_plan_steps |
| F. Data collection and analysis | `data_collection_methods`, `research_instruments`, `data_collection_stages`, `data_analysis_methods` | research_instruments |
| G. Results | `abstract`, `results`, `key_findings`, `quantitative_results`, `qualitative_results`, `pre_post_comparison`, `supporting_evidence` | abstract, key_findings |
| H. Reflection | `researcher_reflection`, `implementation_challenges`, `adjustments_during_implementation`, `lessons_learned` | researcher_reflection |
| I. Conclusions | `conclusions`, `recommendations`, `future_actions`, `references`, `appendices` | conclusions, recommendations |

`researchers` is a *single repeatable array* of independent objects:

```json
{
  "researchers": [
    {"full_name": "Teacher A", "school": "School A", "directorate": "Directorate A"},
    {"full_name": "Teacher B", "school": "School B", "directorate": "Directorate B"}
  ]
}
```

`action_plan_steps` is an array of `{objective, activity, date, assessment_tool}`; `research_instruments` is an array of `{name, stage, description}`. Questions, objectives, methods, activities, stages, target grades, and references are repeatable string arrays. The research PDF/Word is uploaded separately using the pre-existing secure file flow.

## Lifecycle and compatibility

- **Draft:** incomplete ARDS records may be saved. The draft's `content` JSON stores `standard_version: "ARDS-1.0"` and full structured metadata.
- **Submission:** ARDS-required fields are checked server-side. Owner's approved school/directorate affiliation, PDF/Word file requirement, review permissions, and existing storage workflows remain unchanged.
- **Versioning:** the same structured data is preserved within `ResearchVersion.form_data`. Resubmissions merge prior metadata and only update actual ORM summary columns. No DB migration is required for ARDS 1.0.
- **Access control:** the full `standard_data` and file remain private according to existing workflow permissions. Published studies expose author affiliations and non-sensitive catalog metadata; their full-text files remain private unless the existing system explicitly permits access.
- **Legacy:** research records and practices without `standard_version: "ARDS-1.0"` stay usable through existing editing paths. They are not silently converted or marked complete.

**Important:** never enter personally identifiable student names, contact information, assessment records, or sensitive individual learner data into research metadata. Keep evidence anonymized.

## Future improvements

Consider linked school/directorate catalog IDs, multilingual controlled vocabularies for subjects and grades, secure supporting-evidence uploads, legacy PDF extraction with human review, import/export JSON Schema, and an admin-controlled migration process. These are not part of ARDS 1.0.
