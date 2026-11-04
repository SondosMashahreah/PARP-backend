"""Only distinct institutions linked to published research appear in new admin metrics."""
import unittest
import test_excellence as fixtures
from app.models.workflow import ResearchSubmission
from app.services.dashboard import summary


class PublishedInstitutionTests(unittest.TestCase):
    def setUp(self):
        fixtures.ExcellenceTests.setUp(self)

    def tearDown(self):
        fixtures.ExcellenceTests.tearDown(self)

    def test_distinct_published_research_institutions(self):
        before = summary(self.db, self.admin)['education']
        cases = [
            ('published', 'research', 'd-test-a', 's-test-a'),
            ('published', 'research', 'd-test-a', 's-test-b'),
            ('submitted', 'research', 'd-test-b', 's-test-c'),
            ('published', 'practice', 'd-test-c', 's-test-d'),
        ]
        for index, (status, kind, directorate, school) in enumerate(cases):
            self.db.add(ResearchSubmission(
                researcher_id=self.teacher.id, title=f'New publication {index}',
                research_field='Education', problem='A research problem',
                status=status, publication_type=kind,
                directorate_id=directorate, school_id=school,
            ))
        self.db.commit()
        after = summary(self.db, self.admin)['education']
        self.assertEqual(after['published_directorates'], before['published_directorates'] + 1)
        self.assertEqual(after['published_schools'], before['published_schools'] + 2)


if __name__ == '__main__':
    unittest.main()
