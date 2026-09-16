import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import sys
sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('zlib', str(ROOT / 'zotero-library/scripts/zotero_library.py'))
z = importlib.util.module_from_spec(spec)
spec.loader.exec_module(z)
LIB = z.library_spec('user', '12345')
KEY = 'ABCD2345'
COL = 'BCDE3456'

def fixture():
    return {'schema':'zotero-library-snapshot/v1','library':LIB,'scope_collection':None,
            'items':[{'data': {'key':KEY,'version':3,'itemType':'journalArticle','title':'A Review of Imaging',
                'DOI':'10.1234/example','date':'2024','creators':[{'creatorType':'author','lastName':'Smith'}],
                'tags':[{'tag':'人工标签','type':0},{'tag':'自动来源','type':1}], 'collections':[COL]}}],
            'collections':[{'data':{'key':COL,'version':2,'name':'已有分类','parentCollection':False}}]}

def decision(confidence=0.95):
    return {'key':KEY,'tags':['主题/影像'],'collection_paths':[['10 研究主题','影像']],
            'confidence':confidence,'reason':'摘要明确讨论影像研究。'}

class FakeClient:
    def __init__(self):
        self.library, self.prefix = LIB, '/users/12345'
        s = fixture()
        self.items = {z.obj_data(x)['key']: copy.deepcopy(z.obj_data(x)) for x in s['items']}
        self.cols = {z.obj_data(x)['key']: copy.deepcopy(z.obj_data(x)) for x in s['collections']}
        self.writes = []
        self.fail_post = False
        self.fail_patch = False
    def pages(self, suffix, params=None):
        return ([{'data':copy.deepcopy(x)} for x in (self.cols if suffix == '/collections' else self.items).values()], '10')
    def get(self, suffix):
        kind, key = suffix.strip('/').split('/')
        data = (self.cols if kind == 'collections' else self.items).get(key)
        if data is None:
            raise z.ApiError(404)
        return {'data':copy.deepcopy(data)}
    def maybe_get(self, suffix):
        try:
            return self.get(suffix)
        except z.ApiError:
            return None
    def request(self, method, path, params=None, body=None, headers=None):
        self.writes.append((method, copy.deepcopy(body), headers))
        if method == 'POST':
            if self.fail_post:
                return {'successful':{},'failed':{'0':{'code':400,'message':'fixture failure'}}}, {}
            store = self.cols if path.endswith('/collections') else self.items
            saved = copy.deepcopy(body[0])
            self_test = saved['key'] in store
            if self_test:
                return {'successful':{},'failed':{'0':{'code':412}}}, {}
            saved['version'] = 10
            store[saved['key']] = saved
            return {'successful':{'0':{'data':copy.deepcopy(saved)}},'failed':{}}, {}
        key = path.rsplit('/',1)[1]
        if self.fail_patch:
            raise z.ApiError(412)
        if str(self.items[key]['version']) != headers['If-Unmodified-Since-Version']:
            raise z.ApiError(412)
        self.items[key].update(copy.deepcopy(body))
        self.items[key]['version'] += 1
        return '', {}

class Tests(unittest.TestCase):
    def status_client(self, library, access):
        client = z.Client(library, 'fake-secret-token')
        calls = []
        def request(method, path, **kwargs):
            calls.append(method)
            if path == '/keys/current':
                return dict(access, key='fake-secret-token'), {}
            return [], {'Total-Results': '0'}
        client.request = request
        return client, calls

    def test_status_reports_personal_write_without_exposing_secret(self):
        c, calls = self.status_client(LIB, {'userID': 12345, 'access': {'user': {'library': True, 'write': True}}})
        result = z.connection_status(c)
        self.assertTrue(result['key_allows_write'])
        self.assertEqual(result['top_level_item_count'], 0)
        self.assertFalse(result['write_test_performed'])
        self.assertNotIn('fake-secret-token', json.dumps(result))
        self.assertEqual(calls, ['GET', 'GET'])

    def test_status_does_not_confuse_other_user_permissions(self):
        c, _ = self.status_client(LIB, {'userID': 67890, 'access': {'user': {'write': True}}})
        self.assertFalse(z.connection_status(c)['key_allows_write'])

    def test_status_group_specific_permission_overrides_all(self):
        c, _ = self.status_client(z.library_spec('group', '1234567'), {'access': {'groups': {
            'all': {'library': True, 'write': True}, '1234567': {'library': True, 'write': False}}}})
        self.assertFalse(z.connection_status(c)['key_allows_write'])

    def test_status_all_groups_permission(self):
        c, _ = self.status_client(z.library_spec('group', '1234567'), {'access': {'groups': {
            'all': {'library': True, 'write': True}}}})
        self.assertTrue(z.connection_status(c)['key_allows_write'])

    def test_collections_keep_hierarchy_and_never_write(self):
        c = FakeClient()
        c.cols['CDEF4567'] = {'key': 'CDEF4567', 'name': 'Child', 'parentCollection': COL}
        result = z.list_collections(c)
        self.assertEqual(result['count'], 2)
        child = next(row for row in result['collections'] if row['key'] == 'CDEF4567')
        self.assertEqual(child['parent'], COL)
        self.assertEqual(c.writes, [])

    def test_library_type_accepts_setup_capitalization(self):
        self.assertEqual(z.library_spec(' Group ', ' 1234567 '), z.library_spec('group', '1234567'))

    def test_existing_metadata_is_preserved(self):
        client = FakeClient()
        original = copy.deepcopy(client.items[KEY])
        plan = z.organize_plan(fixture(), [decision()])
        with tempfile.TemporaryDirectory() as d:
            result = z.apply_plan(client, plan, Path(d)/'journal.json', True)
            journal = z.read_json(Path(d)/'journal.json')
        self.assertEqual(result['confirmed'], 3)
        after = client.items[KEY]
        self.assertEqual(after['tags'][:2], original['tags'])
        self.assertIn(COL, after['collections'])
        self.assertEqual(after['DOI'], original['DOI'])
        self.assertEqual(after['creators'], original['creators'])
        self.assertEqual(journal['operations'][-1]['before'], original)
        self.assertEqual(journal['status'], 'complete')

    def test_preflight_never_writes(self):
        c = FakeClient()
        result = z.apply_plan(c, z.organize_plan(fixture(), [decision()]))
        self.assertFalse(result['executed'])
        self.assertEqual(c.writes, [])

    def test_stale_version_stops_before_collection_creation(self):
        c = FakeClient()
        c.items[KEY]['version'] += 1
        with self.assertRaises(z.Problem):
            z.apply_plan(c, z.organize_plan(fixture(), [decision()]), execute=True)
        self.assertEqual(c.writes, [])

    def test_low_confidence_is_review_only(self):
        plan = z.organize_plan(fixture(), [decision(0.6)])
        self.assertEqual(len(plan['review']), 1)
        self.assertEqual(plan['changes'], [])
        self.assertEqual(plan['create_collections'], [])

    def test_collection_reuse(self):
        d = decision()
        d['collection_paths'] = [['已有分类']]
        plan = z.organize_plan(fixture(), [d])
        self.assertEqual(plan['create_collections'], [])
        self.assertEqual(plan['changes'][0]['add_collections'], [COL])

    def test_duplicate_decisions_rejected(self):
        with self.assertRaises(z.Problem):
            z.organize_plan(fixture(), [decision(), decision()])

    def test_conflicting_status_rejected(self):
        s = fixture()
        s['items'][0]['data']['tags'].append({'tag':'状态/已读'})
        d = decision()
        d['tags'] = ['状态/待读']
        with self.assertRaises(z.Problem):
            z.organize_plan(s, [d])

    def test_out_of_scope_rejected(self):
        d = decision()
        d['key'] = 'CDEF4567'
        with self.assertRaises(z.Problem):
            z.organize_plan(fixture(), [d])

    def test_import_doi_normalization(self):
        d = {'itemType':'journalArticle','title':'Different title','DOI':'https://doi.org/10.1234/EXAMPLE'}
        p = z.import_plan(fixture(), [d])
        self.assertEqual(len(p['skipped']), 1)
        self.assertEqual(p['create_items'], [])

    def test_title_match_requires_review(self):
        d = {'itemType':'journalArticle','title':'A REVIEW OF IMAGING','DOI':'10.9999/different'}
        p = z.import_plan(fixture(), [d])
        self.assertEqual(len(p['review']), 1)
        self.assertEqual(p['create_items'], [])

    def test_input_duplicates_and_cross_library_keys(self):
        d = {'key':'CDEF4567','version':66,'itemType':'book','title':'A new title','collections':['DEFG5678'],
             'relations':{'dc:relation':'old library'},'dateAdded':'old date'}
        p = z.import_plan(fixture(), [d, d], COL)
        self.assertEqual(len(p['create_items']), 1)
        self.assertEqual(len(p['review']), 1)
        new = p['create_items'][0]
        self.assertNotEqual(new['key'], d['key'])
        self.assertEqual(new['version'], 0)
        self.assertEqual(new['collections'], [COL])
        self.assertEqual(new['relations'], {})
        self.assertNotIn('dateAdded', new)

    def test_import_creation_and_replay_detection(self):
        c = FakeClient()
        p = z.import_plan(fixture(), [{'itemType':'book','title':'A unique book'}])
        with tempfile.TemporaryDirectory() as td:
            r = z.apply_plan(c, p, Path(td)/'j.json', True)
            self.assertEqual(r['confirmed'],1)
            with self.assertRaises(z.Problem):
                z.apply_plan(c, p)

    def test_scoped_import_rejected(self):
        s = fixture()
        s['scope_collection'] = COL
        with self.assertRaises(z.Problem):
            z.import_plan(s, [])

    def test_batch_200_failure_stops_with_journal(self):
        c = FakeClient()
        c.fail_post = True
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)/'j.json'
            with self.assertRaises(z.Problem):
                z.apply_plan(c, z.organize_plan(fixture(), [decision()]), path, True)
            j = z.read_json(path)
            self.assertEqual(j['status'],'stopped')
            self.assertEqual(j['operations'][0]['status'],'pending')
            self.assertEqual(len(c.writes),1)

    def test_patch_conflict_keeps_before_record(self):
        c = FakeClient()
        c.fail_patch = True
        d = decision()
        d['collection_paths'] = []
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)/'j.json'
            with self.assertRaises(z.ApiError):
                z.apply_plan(c, z.organize_plan(fixture(), [d]), path, True)
            j = z.read_json(path)
            self.assertEqual(j['operations'][0]['before']['version'],3)
            self.assertEqual(j['status'],'stopped')

    def test_cross_library_plan_rejected(self):
        p = z.organize_plan(fixture(), [decision()])
        p['library'] = z.library_spec('group','12345')
        with self.assertRaises(z.Problem):
            z.apply_plan(FakeClient(), p)

    def test_pagination_over_200(self):
        c = z.Client(LIB,'fake')
        keys = [z.new_key() for _ in range(205)]
        calls = []
        def request(method,path,params):
            calls.append(params['start'])
            return ([{'key':k} for k in keys[params['start']:params['start']+100]], {'Last-Modified-Version':'25'})
        c.request = request
        items, version = c.pages('/items/top')
        self.assertEqual(len(items),205)
        self.assertEqual(calls,[0,100,200])

    def test_pagination_version_change_rejected(self):
        c = z.Client(LIB,'fake')
        def request(method,path,params):
            return ([{'key':z.new_key()} for _ in range(100 if params['start']==0 else 1)], {'Last-Modified-Version':str(params['start'])})
        c.request = request
        with self.assertRaises(z.Problem):
            c.pages('/items/top')

    def test_file_overwrite_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)/'original.json'
            path.write_text('original')
            with self.assertRaises(z.Problem):
                z.fresh_output(path)
            self.assertEqual(path.read_text(),'original')

    def test_export_csljson_merges_51_records(self):
        c = FakeClient()
        c.items = {z.new_key(): {'itemType':'book','title':'Book '+str(i)} for i in range(51)}
        for key, d in c.items.items(): d['key'] = key
        calls = []
        def request(method,path,params=None,**kw):
            keys = params['itemKey'].split(',')
            calls.append(len(keys))
            return json.dumps([{'id':key,'type':'book'} for key in keys]), {'Last-Modified-Version':'10'}
        c.request = request
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)/'export.json'
            count = z.export_library(c,path,'csljson')
            self.assertEqual(len(z.read_json(path)),51)
            self.assertEqual(count,51)
        self.assertEqual(calls,[50,1])

    def test_export_csv_has_one_header(self):
        c = FakeClient()
        c.items = {z.new_key(): {'itemType':'book','title':'Book '+str(i)} for i in range(51)}
        for key, d in c.items.items(): d['key'] = key
        def request(method,path,params=None,**kw):
            return 'Key,Title\n'+'\n'.join(k+',Example' for k in params['itemKey'].split(',')), {'Last-Modified-Version':'10'}
        c.request = request
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)/'export.csv'
            z.export_library(c,path,'csv')
            content = path.read_text(encoding='utf-8-sig')
            self.assertEqual(content.count('Key,Title'),1)
            self.assertEqual(len(content.splitlines()),52)

    def test_export_stale_data_never_saves(self):
        c = FakeClient()
        c.request = lambda *args,**kw: ('TY  - BOOK\nER  -',{'Last-Modified-Version':'11'})
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)/'export.ris'
            with self.assertRaises(z.Problem): z.export_library(c,path,'ris')
            self.assertFalse(path.exists())

    def test_empty_csl_export_valid_json(self):
        c = FakeClient()
        c.items = {}
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)/'export.json'
            self.assertEqual(z.export_library(c,path,'csljson'),0)
            self.assertEqual(z.read_json(path),[])

    def test_action_schema_references_and_operations(self):
        doc = z.read_json(ROOT/'zotero-library/assets/chatgpt-actions.json')
        refs = []
        def visit(obj):
            if isinstance(obj,dict):
                for k,v in obj.items():
                    if k=='$ref': refs.append(v)
                    visit(v)
            elif isinstance(obj,list):
                for x in obj: visit(x)
        visit(doc)
        for ref in refs:
            self.assertIn(ref.split('/')[-1],doc['components']['schemas'])
        operations = [op['operationId'] for path in doc['paths'].values() for op in path.values()]
        self.assertEqual(len(set(operations)),len(operations))
        self.assertTrue(all('delete' not in path for path in doc['paths'].values()))

if __name__ == '__main__':
    unittest.main(verbosity=2)
