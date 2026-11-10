import unittest
from pydantic import ValidationError
from app.domain.action_research import validate_standard_submission
from app.domain.errors import ApplicationError
from app.schemas.researcher import DraftContent


class ActionResearchStandardTests(unittest.TestCase):
    def content(self):
        return DraftContent(
            standard_version='ARDS-1.0', kind='research',
            title='Learning intervention', research_field='Mathematics',
            problem='Learning gap', abstract='Research abstract',
            researchers=[{'full_name': 'Teacher A', 'school': 'School A', 'directorate': 'Directorate A'},
                         {'full_name': 'Teacher B', 'school': 'School B', 'directorate': 'Directorate B'}],
            research_question='What changes?', research_objectives=['Improve understanding'],
            sample_size=35, intervention='Drama lessons',
            action_plan_steps=[{'activity': 'Run drama activities'}],
            research_instruments=[{'name': 'Observation checklist'}],
            key_findings='Better understanding', researcher_reflection='I learned to adapt',
            conclusions='Intervention helped', recommendations='Continue practice',
        ).model_dump()

    def test_complete_record_has_independent_researcher_affiliations(self):
        content = self.content()
        self.assertEqual(content['researchers'][0]['school'], 'School A')
        self.assertEqual(content['researchers'][1]['directorate'], 'Directorate B')
        validate_standard_submission(content)

    def test_draft_can_be_incomplete_but_submission_cannot(self):
        draft = DraftContent(standard_version='ARDS-1.0', title='Unfinished')
        with self.assertRaises(ApplicationError) as err:
            validate_standard_submission(draft.model_dump())
        self.assertEqual(err.exception.status_code, 422)

    def test_legacy_and_practice_not_forced_into_new_standard(self):
        validate_standard_submission(DraftContent(title='Legacy').model_dump())
        validate_standard_submission(DraftContent(kind='practice', title='Practice').model_dump())

    def test_missing_researcher_directorate_rejected(self):
        content = self.content()
        content['researchers'][1]['directorate'] = ''
        with self.assertRaises(ApplicationError):
            validate_standard_submission(content)

    def test_input_limits_are_validated(self):
        with self.assertRaises(ValidationError):
            DraftContent(standard_version='ARDS-1.0', sample_size=-2)
        with self.assertRaises(ValidationError):
            DraftContent(researchers=[{'full_name':'X' * 301}])


if __name__ == '__main__':
    unittest.main()
