import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / 'zotero-library/assets/chatgpt-actions.json'
def ref(name):
    return {'$ref': '#/components/schemas/' + name}

def parameter(name, schema, where='query', required=False, description=None):
    p = {'name': name, 'in': where, 'required': required, 'schema': schema}
    if description:
        p['description'] = description
    return p

key = {'type': 'string', 'pattern': '^[23456789ABCDEFGHIJKLMNPQRSTUVWXYZ]{8}$'}
tag = {'type': 'object', 'properties': {'tag': {'type': 'string'}, 'type': {'type': 'integer', 'enum': [0, 1]}}, 'required': ['tag']}
creator = {'type': 'object', 'properties': {k: {'type': 'string'} for k in ['creatorType','name','firstName','lastName']}, 'required': ['creatorType']}
item = {'type': 'object', 'properties': {
    'key': key, 'version': {'type': 'integer', 'minimum': 0, 'description': 'Current item version for updates; 0 with a new key for creation.'},
    'itemType': {'type': 'string'}, 'title': {'type': 'string'}, 'creators': {'type': 'array', 'items': creator},
    'tags': {'type': 'array', 'items': tag}, 'collections': {'type': 'array', 'items': key},
    'relations': {'type': 'object', 'properties': {}, 'additionalProperties': True}}, 'additionalProperties': True}
for field in ['abstractNote','date','DOI','ISBN','ISSN','url','publicationTitle','volume','issue','pages','publisher','place','language','extra']:
    item['properties'][field] = {'type': 'string'}
envelope = {'type': 'object', 'properties': {'key': key, 'version': {'type': 'integer'}, 'data': ref('ItemData')}, 'additionalProperties': True}
collection = {'type': 'object', 'properties': {'key': key, 'version': {'type': 'integer'}, 'name': {'type': 'string'}, 'parentCollection': {'oneOf': [key, {'type': 'boolean', 'enum': [False]}]}}, 'required': ['name'], 'additionalProperties': False}
schemas = {'ItemData': item, 'ItemEnvelope': envelope, 'CollectionData': collection,
    'CollectionEnvelope': {'type': 'object', 'properties': {'key': key,'version': {'type': 'integer'},'data': ref('CollectionData')}, 'additionalProperties': True},
    'WriteResult': {'type': 'object', 'properties': {
        'successful': {'type': 'object', 'properties': {}, 'additionalProperties': True},
        'unchanged': {'type': 'object', 'properties': {}, 'additionalProperties': {'type': 'string'}},
        'failed': {'type': 'object', 'properties': {}, 'additionalProperties': True}}}}
scope = [parameter('libraryType', {'type': 'string','enum': ['users','groups']}, 'path', True),
         parameter('libraryID', {'type':'string','pattern':'^[1-9][0-9]*$'}, 'path', True)]
v = parameter('v', {'type':'integer','enum':[3],'default':3})
paging = [v, parameter('limit', {'type':'integer','minimum':1,'maximum':100,'default':25}), parameter('start', {'type':'integer','minimum':0,'default':0})]
query = paging + [parameter('q', {'type':'string'}), parameter('qmode', {'type':'string','enum':['titleCreatorYear','everything']}),
    parameter('tag', {'type':'string'}), parameter('itemKey', {'type':'string'}, description='Comma-separated item keys, at most 50.'),
    parameter('sort', {'type':'string','enum':['dateAdded','dateModified','title','creator','date'],'default':'title'}),
    parameter('direction', {'type':'string','enum':['asc','desc'],'default':'asc'}),
    parameter('format', {'type':'string','enum':['json','bibtex','biblatex','ris','csljson','csv'],'default':'json'})]
def responses(schema):
    return {'200': {'description': 'Zotero response; inspect individual write failures when present.', 'content': {'application/json': {'schema': schema}}},
            '401': {'description':'Missing or invalid credentials.'}, '403': {'description':'Insufficient library permission.'},
            '412': {'description':'Version conflict. Fetch current data before deciding how to continue.'},
            '429': {'description':'Rate limited. Respect the retry delay.'}}

def get(op, description, params, schema, export=False):
    result = {'operationId':op, 'description':description, 'parameters':params, 'responses':responses(schema)}
    if export:
        result['responses']['200']['content']['text/plain'] = {'schema': {'type':'string'}}
    return result

prefix = '/{libraryType}/{libraryID}'
paths = {
    prefix + '/items/top': {'get': get('listTopItems','Read or export bibliographic items. Paginate; results exclude child items.', scope + query, {'type':'array','items':ref('ItemEnvelope')}, True)},
    prefix + '/collections': {'get': get('listCollections','Read library collections and their parents. Paginate all results.', scope + paging, {'type':'array','items':ref('CollectionEnvelope')})},
    prefix + '/collections/{collectionKey}/items/top': {'get': get('listCollectionItems','Read/export direct items in a collection. Subcollections require separate requests.', scope + [parameter('collectionKey',key,'path',True)] + query, {'type':'array','items':ref('ItemEnvelope')}, True)},
    prefix + '/items/{itemKey}': {'get': get('getItem','Read current complete item data and version before editing or verifying a write.', scope + [parameter('itemKey',key,'path',True),v], ref('ItemEnvelope'))},
    '/items/new': {'get': get('getItemTemplate','Get an editable Zotero item template before importing metadata.', [parameter('itemType',{'type':'string'},required=True),v], ref('ItemData'))}
}
paths['/items/new']['get']['security'] = []
for suffix, op, schema, description in [
    ('/items','upsertItems',ref('ItemData'),'Create or update up to 50 items. Updates require current key/version. Tags and collections replace whole arrays; merge existing values first. Check failed results.'),
    ('/collections','createCollections',ref('CollectionData'),'Create collections only after checking parent/name duplicates. Use a fresh key and version=0; parent must exist. Check failed results.')]:
    paths.setdefault(prefix + suffix,{})['post'] = {'operationId':op, 'description':description, 'parameters':scope + [v],
        'x-openai-isConsequential': True,
        'requestBody': {'required':True,'content':{'application/json':{'schema':{'type':'array','minItems':1,'maxItems':50,'items':schema}}}},
        'responses':responses(ref('WriteResult'))}

doc = {'openapi':'3.1.0','info':{'title':'Zotero Library Companion','version':'1.0.0','description':'Personal Zotero metadata import/export, collections and tags. No deletion or binary file upload.'},
       'servers':[{'url':'https://api.zotero.org'}], 'security':[{'ZoteroBearer':[]}], 'paths':paths,
       'components':{'securitySchemes':{'ZoteroBearer':{'type':'http','scheme':'bearer'}},'schemas':schemas}}
OUT.write_text(json.dumps(doc,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(OUT)
