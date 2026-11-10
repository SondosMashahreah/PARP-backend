from typing import Literal
from pydantic import BaseModel, Field, model_validator


class ResearcherEntry(BaseModel):
    full_name: str = Field(default='', max_length=300)
    school: str = Field(default='', max_length=300)
    directorate: str = Field(default='', max_length=300)


class ActionPlanStep(BaseModel):
    objective: str = Field(default='', max_length=300)
    activity: str = Field(default='', max_length=4000)
    date: str = Field(default='', max_length=100)
    assessment_tool: str = Field(default='', max_length=300)


class ResearchInstrument(BaseModel):
    name: str = Field(default='', max_length=300)
    stage: str = Field(default='', max_length=300)
    description: str = Field(default='', max_length=4000)


class DraftContent(BaseModel):
    # Existing legacy research and practice fields remain compatible.
    kind: Literal["research", "practice"] = "research"
    standard_version: Literal['ARDS-1.0'] | None = None
    title: str = Field(default='', max_length=500)
    title_en: str = Field(default='', max_length=500)
    research_field: str = Field(default='', max_length=150)
    problem: str = Field(default='', max_length=12000)
    abstract: str = Field(default='', max_length=12000)
    research_question: str = Field(default='', max_length=12000)
    intervention: str = Field(default='', max_length=12000)
    results: str = Field(default='', max_length=12000)
    recommendations: str = Field(default='', max_length=12000)
    keywords: str | list[str] = Field(default='', max_length=2000)

    # A – Research identification. Each co-author has an independent affiliation.
    researchers: list[ResearcherEntry] = Field(default_factory=list, max_length=100)
    academic_year: str = Field(default='', max_length=30)
    research_language: Literal['', 'ar', 'en', 'both'] = ''
    subject_area: str = Field(default='', max_length=150)
    target_grades: list[str] = Field(default_factory=list, max_length=30)

    # B – Problem.
    research_context: str = Field(default='', max_length=12000)
    evidence_of_problem: str = Field(default='', max_length=12000)
    problem_significance: str = Field(default='', max_length=12000)

    # C – Questions and objectives.
    sub_research_questions: list[str] = Field(default_factory=list, max_length=50)
    research_objectives: list[str] = Field(default_factory=list, max_length=50)
    research_hypothesis: str = Field(default='', max_length=12000)

    # D – Participants and setting.
    target_population: str = Field(default='', max_length=300)
    sample_size: int | None = Field(default=None, ge=1, le=1000000)
    participant_characteristics: str = Field(default='', max_length=12000)
    research_setting: str = Field(default='', max_length=300)
    research_start_date: str = Field(default='', max_length=30)
    research_end_date: str = Field(default='', max_length=30)

    # E – Intervention.
    intervention_strategy: str = Field(default='', max_length=300)
    intervention_description: str = Field(default='', max_length=12000)
    action_plan_steps: list[ActionPlanStep] = Field(default_factory=list, max_length=200)
    learning_activities: list[str] = Field(default_factory=list, max_length=100)
    resources_used: str = Field(default='', max_length=12000)

    # F – Instruments and analysis.
    data_collection_methods: list[str] = Field(default_factory=list, max_length=100)
    research_instruments: list[ResearchInstrument] = Field(default_factory=list, max_length=100)
    data_collection_stages: list[str] = Field(default_factory=list, max_length=100)
    data_analysis_methods: list[str] = Field(default_factory=list, max_length=100)

    # G – Findings.
    key_findings: str = Field(default='', max_length=12000)
    quantitative_results: str = Field(default='', max_length=12000)
    qualitative_results: str = Field(default='', max_length=12000)
    pre_post_comparison: str = Field(default='', max_length=12000)
    supporting_evidence: str = Field(default='', max_length=12000)

    # H – Reflection.
    researcher_reflection: str = Field(default='', max_length=12000)
    implementation_challenges: str = Field(default='', max_length=12000)
    adjustments_during_implementation: str = Field(default='', max_length=12000)
    lessons_learned: str = Field(default='', max_length=12000)

    # I – Conclusions and documentation.
    conclusions: str = Field(default='', max_length=12000)
    future_actions: str = Field(default='', max_length=12000)
    references: list[str] = Field(default_factory=list, max_length=200)
    appendices: str = Field(default='', max_length=12000)


class DraftSave(BaseModel):
    content: DraftContent
    revision: int = Field(ge=1)


class ProgressSave(BaseModel):
    course_key: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=250)
    completed: int = Field(ge=0)
    total: int = Field(ge=1)

    @model_validator(mode='after')
    def validate_progress(self):
        if self.completed > self.total:
            raise ValueError('Completed units cannot exceed total units')
        return self
