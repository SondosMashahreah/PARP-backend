import test_excellence as fixtures
import unittest
from unittest.mock import patch
from app.main import app
from app.routers.dependencies import get_current_user
from app.models.news import NewsArticle
from app.services.assistant_data import read_platform, summary

class NewsTests(unittest.TestCase):
    def setUp(self):
        fixtures.ExcellenceTests.setUp(self)
        self.news_upload = patch('app.services.news._upload').start()
        self.news_delete = patch('app.services.news.delete_object').start()
        patch('app.services.news.presigned_avatar_url', side_effect=lambda n: 'https://images.test/news.webp' if n else None).start()
    def tearDown(self):
        fixtures.ExcellenceTests.tearDown(self)
        patch.stopall()
    png = fixtures.ExcellenceTests.png
    def payload(self, **changes):
        return dict(title='خبر المنصة', body='النص الكامل\nفقرة ثانية', excerpt='ملخص الخبر', **changes)
    def create(self):
        r = self.client.post('/api/news/admin', json=self.payload())
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()['id']
    def publish(self, id):
        r = self.client.post(f'/api/news/admin/{id}/image', files={'file': ('image.png', self.png(), 'image/png')})
        self.assertEqual(r.status_code, 200, r.text)
        r = self.client.put(f'/api/news/admin/{id}', json=self.payload(published=True))
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()
    def test_guest_reads_full_published_article_and_never_drafts(self):
        id = self.create()
        app.dependency_overrides.pop(get_current_user)
        self.assertEqual(self.client.get('/api/news').json()['total'], 0)
        self.assertEqual(self.client.get(f'/api/news/{id}').status_code, 404)
        app.dependency_overrides[get_current_user] = lambda: self.admin
        published = self.publish(id)
        app.dependency_overrides.pop(get_current_user)
        data = self.client.get(f'/api/news/{id}').json()
        self.assertEqual(data['body'], self.payload()['body'])
        self.assertEqual(data['published_at'], published['published_at'])
        self.assertNotIn('created_by', data)
        self.assertNotIn('image_object', data)
        self.assertEqual(self.client.get('/api/news?q=فقرة').json()['total'], 1)
        self.assertEqual(self.client.get('/api/news?q=%25').json()['total'], 0)
        self.assertEqual(self.client.get('/api/news?offset=1').json()['items'], [])
    def test_all_mutations_and_drafts_are_admin_only(self):
        id = self.create()
        for user, status in [(None, 401), (self.teacher, 403)]:
            if user: app.dependency_overrides[get_current_user] = lambda: user
            else: app.dependency_overrides.pop(get_current_user, None)
            for method, url, kwargs in [
                ('get', '/api/news/admin', {}), ('get', f'/api/news/admin/{id}', {}),
                ('post', '/api/news/admin', {'json': self.payload()}),
                ('put', f'/api/news/admin/{id}', {'json': self.payload()}),
                ('post', f'/api/news/admin/{id}/image', {'files': {'file': ('x.png', self.png(), 'image/png')}}),
                ('delete', f'/api/news/admin/{id}', {})]:
                self.assertEqual(getattr(self.client, method)(url, **kwargs).status_code, status)
    def test_validation_and_failed_upload_preserve_existing_image(self):
        self.assertEqual(self.client.post('/api/news/admin', json={'title':'  ', 'body':'x'}).status_code, 422)
        self.assertEqual(self.client.post('/api/news/admin', json=self.payload(published=True)).status_code, 422)
        id = self.create()
        self.assertEqual(self.client.put(f'/api/news/admin/{id}', json=self.payload(published=True)).status_code, 422)
        self.assertEqual(self.client.post(f'/api/news/admin/{id}/image', files={'file':('x.png', b'<svg/>', 'image/png')}).status_code, 422)
        self.publish(id)
        previous = self.db.get(NewsArticle, id).image_object
        self.news_upload.side_effect = RuntimeError('storage offline')
        self.assertEqual(self.client.post(f'/api/news/admin/{id}/image', files={'file':('x.png', self.png(), 'image/png')}).status_code, 503)
        self.assertEqual(self.db.get(NewsArticle, id).image_object, previous)
    def test_edit_unpublish_republish_and_delete(self):
        id = self.create()
        published = self.publish(id)
        edited = self.payload(published=True); edited['body'] = 'Updated text <script>plain text only</script>'
        r = self.client.put(f'/api/news/admin/{id}', json=edited)
        self.assertEqual(r.json()['published_at'], published['published_at'])
        self.assertEqual(self.client.get(f'/api/news/{id}').json()['body'], edited['body'])
        edited['published'] = False
        self.assertEqual(self.client.put(f'/api/news/admin/{id}', json=edited).status_code, 200)
        self.assertEqual(self.client.get(f'/api/news/{id}').status_code, 404)
        self.assertEqual(self.client.get('/api/news').json()['total'], 0)
        self.publish(id)
        self.assertEqual(self.client.delete(f'/api/news/admin/{id}').status_code, 200)
        self.news_delete.assert_called()
        self.assertEqual(self.client.get(f'/api/news/{id}').status_code, 404)
    def test_assistant_has_live_counts_and_respects_draft_scope(self):
        id = self.create()
        self.assertEqual(read_platform(self.db, None, {'dataset':'news','visibility':'workspace'})[0]['total'], 0)
        self.assertEqual(read_platform(self.db, self.teacher, {'dataset':'news','visibility':'workspace'})[0]['total'], 0)
        self.assertEqual(read_platform(self.db, self.admin, {'dataset':'news','visibility':'workspace'})[0]['total'], 1)
        self.publish(id)
        self.assertEqual(summary(self.db, None)['public_platform']['published_news'], 1)
        data, url = read_platform(self.db, None, {'dataset':'news','record_id':str(id)})
        self.assertEqual(data['body'], self.payload()['body'])
        self.assertEqual(url, f'/news?article={id}')
