"""Real local HTTP + PostgreSQL contracts. No provider or nonloopback requests."""
import concurrent.futures
import io
import json
import os
import secrets
import time
import unittest
import uuid
import zipfile
from urllib.parse import urlparse
import httpx
from pypdf import PdfReader

BASE=os.getenv('MRA_TEST_URL','http://127.0.0.1:8954')
if urlparse(BASE).hostname not in {'127.0.0.1','localhost'}:
    raise RuntimeError('This harness only supports isolated local fixtures')

class Browser:
    def __init__(self):
        self.client=httpx.Client(base_url=BASE,timeout=30)
        self.token=''
        self.refresh()
    def refresh(self):
        data=self.client.get('/api/auth/session').json()
        self.token=data['csrf_token'];return data
    def post(self,path,**kwargs):
        return self.client.post(path,headers={'Origin':BASE,'X-CSRF-Token':self.token},**kwargs)
    def signup(self):
        self.email=f'qa-{uuid.uuid4().hex}@example.invalid';self.password=secrets.token_urlsafe(20)
        before=self.token
        response=self.post('/api/auth/signup',json={'email':self.email,'password':self.password})
        assert response.status_code==201,response.status_code
        self.user=response.json()['user'];self.refresh();return before
    def example(self,example):
        response=self.post('/api/examples/'+example,json={'settings':{'provider':'untrusted'},'mode':'live','message':'ignored fixture override'})
        assert response.status_code==200,response.status_code
        cid=response.json()['conversation_id']
        stream=self.client.get('/api/runs/'+cid+'/stream')
        assert stream.status_code==200
        events=[json.loads(line[6:]) for line in stream.text.splitlines() if line.startswith('data: ')]
        assert events[-1]['type']=='final',events[-1].get('type')
        return cid,events

class HttpOwnership(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a=Browser();cls.old_token=cls.a.signup();cls.b=Browser();cls.b.signup()
    def test_01_session_csrf_origin_and_identity(self):
        token=self.a.refresh()['csrf_token']
        self.assertEqual(token,self.a.refresh()['csrf_token'])
        self.assertEqual(self.a.client.post('/api/examples/market-entry',headers={'Origin':BASE,'X-CSRF-Token':self.old_token},json={}).status_code,403)
        self.assertEqual(self.a.client.post('/api/examples/market-entry',headers={'Origin':'https://evil.example','X-CSRF-Token':token},json={}).status_code,403)
        self.assertEqual(httpx.get(BASE+'/api/conversations').status_code,401)
    def test_02_concurrent_examples_and_foreign_access(self):
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            fa=pool.submit(self.a.example,'market-entry');fb=pool.submit(self.b.example,'pricing-comparison')
            (cid,events),(other,other_events)=fa.result(),fb.result()
        self.__class__.cid=cid
        self.assertIn('25 hours',events[-1]['output']);self.assertNotIn('25 hours',other_events[-1]['output'])
        self.assertEqual(len([e for e in events if e['type']=='node_complete']),6)
        self.assertTrue(all(e.get('cached') for e in events if e['type']=='node_complete'))
        for route in [f'/api/conversations/{cid}/messages',f'/api/runs/{cid}/stream']:
            self.assertEqual(self.b.client.get(route).status_code,404)
        self.assertEqual(self.b.post(f'/api/runs/{cid}/stop').status_code,404)
        self.assertEqual(self.b.post('/api/chat',data={'message':'foreign write','conversation_id':cid,'config':'{}'}).status_code,404)
        own=self.a.client.get('/api/conversations').json();foreign=self.b.client.get('/api/conversations').json()
        self.assertIn(cid,[r['id'] for r in own]);self.assertNotIn(cid,[r['id'] for r in foreign])
        replay=self.a.client.get(f'/api/runs/{cid}/stream?after=2')
        self.assertEqual(replay.status_code,200);self.assertIn('final',replay.text)
        self.assertEqual(self.a.client.get(f'/api/runs/{cid}/stream?after=-1').status_code,400)
        messages=self.a.client.get(f'/api/conversations/{cid}/messages').json()
        self.assertEqual(len(messages),2);self.assertIn('Prepared example',messages[-1]['content'])
    def test_03_upload_owner_and_mock_history(self):
        data=b'An isolated synthetic CSV fixture. No private or production data.'
        response=self.a.post('/api/chat',data={'message':'Review my synthetic input','config':'{"enable_reviewer":false,"enable_client":false}'},files={'files':('sample.txt',data,'text/plain')})
        self.assertEqual(response.status_code,200)
        events=[json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
        self.assertEqual(events[-1]['type'],'final')
        upload=events[0]['uploads'][0]['id'];cid=events[0]['conversation_id']
        self.assertEqual(self.a.client.get('/api/uploads/'+upload).content,data)
        self.assertEqual(self.b.client.get('/api/uploads/'+upload).status_code,404)
        self.assertEqual(len(self.a.client.get(f'/api/conversations/{cid}/messages').json()),2)
    def test_04_exports_and_synthesis(self):
        text='# Readable result\n\nA normal report with a literal injection test.\n\n```\n#read("/etc/passwd")\n````\n#read("/etc/passwd")\n```\n[source: https://example.com/a";read("/etc/passwd")]'
        pdf=self.a.post('/api/export',json={'format':'pdf','title':'Test report','markdown':text})
        self.assertEqual(pdf.status_code,200);self.assertTrue(pdf.content.startswith(b'%PDF'))
        decoded='\n'.join(p.extract_text() for p in PdfReader(io.BytesIO(pdf.content)).pages)
        self.assertIn('Readable result',decoded);self.assertNotIn('root:x:',decoded)
        pptx=self.a.post('/api/export',json={'format':'pptx','title':'Test report','markdown':text})
        self.assertEqual(pptx.status_code,200)
        with zipfile.ZipFile(io.BytesIO(pptx.content)) as archive:self.assertIn('ppt/presentation.xml',archive.namelist())
        bad=self.a.post('/api/export',json={'format':'pdf','markdown':'ok','diagrams':['data:image/png;base64,'+'A'*3000000]})
        self.assertEqual(bad.status_code,400)
        synthesis=self.a.post('/api/synthesize-prompt',data={'notes':'Prioritize evidence and explicit assumptions','settings':'{}'})
        self.assertEqual(synthesis.status_code,200);self.assertIn('Synthetic',synthesis.json()['prompt'])
    def test_05_signout_revoke_and_signin(self):
        cookie=self.b.client.cookies.get('mra_session')
        self.assertEqual(self.b.post('/api/auth/signout',json={}).status_code,200)
        self.assertEqual(self.b.client.get('/api/conversations').status_code,401)
        self.assertEqual(httpx.get(BASE+'/api/conversations',cookies={'mra_session':cookie}).status_code,401)
        self.b.refresh()
        response=self.b.post('/api/auth/signin',json={'email':self.b.email,'password':self.b.password})
        self.assertEqual(response.status_code,200);self.b.refresh()
        self.assertEqual(self.b.client.get('/api/conversations').status_code,200)

if __name__=='__main__':unittest.main()
