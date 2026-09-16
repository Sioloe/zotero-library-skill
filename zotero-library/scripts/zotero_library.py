#!/usr/bin/env python3
"""Zotero Web API helper. Standard library only, Python 3.7+."""
import argparse
import copy
import csv
import io
import json
import os
import re
import secrets
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, unquote
from urllib.request import Request, build_opener, HTTPRedirectHandler

BASE = 'https://api.zotero.org'
SCHEMA = 'zotero-library-plan/v1'
EXCLUDED = {'attachment', 'note', 'annotation'}
KEY_RE = re.compile(r'^[23456789ABCDEFGHIJKLMNPQRSTUVWXYZ]{8}$')


class Problem(Exception):
    pass


class ApiError(Problem):
    def __init__(self, status, retry_after=None):
        self.status = status
        suffix = (' Retry-After: {}.'.format(retry_after)) if retry_after else ''
        super().__init__('Zotero HTTP {}. Stop; inspect current state before retrying.{}'.format(status, suffix))


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Metadata endpoints do not require redirection. Never forward credentials.
        return None


def now():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(str(tmp), str(path))


def fresh_output(path):
    if Path(path).exists():
        raise Problem('Output already exists; choose a new path: {}'.format(path))


def obj_data(obj):
    return obj.get('data', obj)


def valid_key(key):
    if not isinstance(key, str) or not KEY_RE.fullmatch(key):
        raise Problem('Invalid Zotero key: {}'.format(key))
    return key


def new_key():
    return ''.join(secrets.choice('23456789ABCDEFGHIJKLMNPQRSTUVWXYZ') for _ in range(8))


def library_spec(kind, ident):
    kind = str(kind).strip().casefold()
    ident = str(ident).strip()
    if kind not in ('user', 'group') or not re.fullmatch(r'[1-9][0-9]*', str(ident)):
        raise Problem('Use library type user/group and a positive numeric library ID.')
    return {'type': kind, 'id': str(ident), 'base_url': BASE}


def unprotect_windows_secret(value):
    import ctypes
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]
    raw = bytes.fromhex(value)
    buffer = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
    source, dest = Blob(len(raw), buffer), Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    crypt.CryptUnprotectData.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                                        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    crypt.CryptUnprotectData.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if not crypt.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(dest)):
        raise Problem('Cannot decrypt Zotero credentials. Run under the same Windows user that configured them; an agent sandbox may need authorized local access. Reconfigure only if the user or machine changed.')
    try:
        return ctypes.string_at(dest.data, dest.size).decode('utf-16-le')
    finally:
        ctypes.memset(dest.data, 0, dest.size)
        kernel.LocalFree(dest.data)


def load_config():
    if os.environ.get('ZOTERO_API_KEY'):
        return (library_spec(os.environ.get('ZOTERO_LIBRARY_TYPE', 'user'),
                             os.environ.get('ZOTERO_LIBRARY_ID', '')),
                os.environ['ZOTERO_API_KEY'])
    path = os.environ.get('ZOTERO_CONFIG') or str(Path(os.environ.get('LOCALAPPDATA', '.')) / 'ZoteroCodex' / 'config.json')
    if os.name != 'nt' or not Path(path).is_file():
        raise Problem('No credentials. Run setup.ps1 in your own terminal, or configure ZOTERO_* environment variables. Do not paste secrets into chat.')
    cfg = read_json(path)
    spec = library_spec(cfg['library_type'], cfg['library_id'])
    return spec, unprotect_windows_secret(cfg['protected_api_key'])


class Client:
    def __init__(self, library, token):
        self.library = library
        self.prefix = '/{}/{}'.format('users' if library['type'] == 'user' else 'groups', library['id'])
        self.token = token
        self.opener = build_opener(NoRedirect())
        self.pause_until = 0

    def request(self, method, path, params=None, body=None, headers=None):
        if not path.startswith('/') or path.startswith('//'):
            raise Problem('Expected an API path.')
        url = BASE + path + (('?' + urlencode(params)) if params else '')
        hdr = {'Zotero-API-Key': self.token, 'Zotero-API-Version': '3', 'User-Agent': 'ZoteroLibrarySkill/1.0'}
        if headers:
            hdr.update(headers)
        payload = None if body is None else json.dumps(body, ensure_ascii=False).encode('utf-8')
        if payload is not None:
            hdr['Content-Type'] = 'application/json'
        delay = self.pause_until - time.monotonic()
        if delay > 30:
            raise Problem('Zotero asked for a longer backoff. Wait and rerun after {:.0f} seconds.'.format(delay))
        if delay > 0:
            time.sleep(delay)
        try:
            with self.opener.open(Request(url, data=payload, headers=hdr, method=method), timeout=30) as response:
                raw = response.read().decode('utf-8-sig')
                meta = dict(response.headers.items())
                backoff = response.headers.get('Backoff')
                if backoff:
                    self.pause_until = time.monotonic() + float(backoff)
                content_type = response.headers.get('Content-Type', '')
                value = json.loads(raw) if raw and 'json' in content_type else raw
                return value, meta
        except HTTPError as exc:
            raise ApiError(exc.code, exc.headers.get('Retry-After')) from None
        except (URLError, TimeoutError, OSError):
            raise Problem('Network result uncertain; no automatic write retry. Read back the object before rerunning.') from None

    def get(self, suffix):
        return self.request('GET', self.prefix + suffix)[0]

    def maybe_get(self, suffix):
        try:
            return self.get(suffix)
        except ApiError as exc:
            if exc.status == 404:
                return None
            raise

    def pages(self, suffix, params=None):
        result, version = [], None
        params = dict(params or {})
        params.update({'format': 'json', 'limit': 100, 'sort': 'dateModified', 'direction': 'asc'})
        start = 0
        while True:
            params['start'] = start
            page, headers = self.request('GET', self.prefix + suffix, params=params)
            current = next((v for k, v in headers.items() if k.lower() == 'last-modified-version'), None)
            if version is not None and current != version:
                raise Problem('Library changed during pagination. Fetch a fresh snapshot.')
            version = current
            if not isinstance(page, list):
                raise Problem('Expected a paginated Zotero JSON array.')
            result.extend(page)
            if len(page) < 100:
                break
            start += len(page)
        keys = [obj_data(x).get('key') for x in result]
        if len(set(keys)) != len(keys):
            raise Problem('Pagination returned duplicate keys; fetch a fresh snapshot.')
        return result, version


def connection_status(client):
    """Report selected-library access, never the raw key metadata response."""
    metadata, _ = client.request('GET', '/keys/current')
    access = metadata.get('access', {})
    if client.library['type'] == 'user':
        permission = access.get('user', {}) if str(metadata.get('userID')) == client.library['id'] else {}
    else:
        groups = access.get('groups', {})
        permission = groups.get(client.library['id'], groups.get('all', {}))
    items, headers = client.request('GET', client.prefix + '/items/top', params={'limit': 1, 'format': 'json'})
    total = next((int(v) for k, v in headers.items() if k.lower() == 'total-results'), None)
    return {'connected': True, 'library': client.library, 'sample_count': len(items),
            'top_level_item_count': total, 'key_allows_library': bool(permission.get('library')),
            'key_allows_write': bool(permission.get('write')),
            'write_test_performed': False}


def list_collections(client):
    objects, version = client.pages('/collections')
    rows = []
    for obj in objects:
        data = obj_data(obj)
        rows.append({'key': data['key'], 'name': data['name'],
                     'parent': data.get('parentCollection') or None,
                     'num_items': obj.get('meta', {}).get('numItems')})
    rows.sort(key=lambda row: (row['name'].casefold(), row['key']))
    return {'library': client.library, 'library_version': version,
            'count': len(rows), 'collections': rows}


def snapshot(client, collection=None):
    suffix = '/items/top' if not collection else '/collections/{}/items/top'.format(valid_key(collection))
    items, v1 = client.pages(suffix)
    collections, v2 = client.pages('/collections')
    if v1 != v2:
        raise Problem('Library changed during snapshot. Fetch it again.')
    return {'schema': 'zotero-library-snapshot/v1', 'library': client.library,
            'created_at': now(), 'library_version': v1, 'scope_collection': collection,
            'items': [x for x in items if obj_data(x).get('itemType') not in EXCLUDED],
            'collections': collections, 'attachments_included': False}


def empty_plan(snap):
    return {'schema': SCHEMA, 'library': snap['library'], 'created_at': now(),
            'create_collections': [], 'create_items': [], 'changes': [], 'review': [], 'skipped': []}


def strings(values, label):
    if not isinstance(values, list) or any(not isinstance(x, str) or not x.strip() for x in values):
        raise Problem('{} must be a list of nonempty strings.'.format(label))
    return list(dict.fromkeys(x.strip() for x in values))


def organize_plan(snap, decisions):
    plan = empty_plan(snap)
    items = {obj_data(x)['key']: obj_data(x) for x in snap['items']}
    mapping = {}
    for obj in snap['collections']:
        d = obj_data(obj)
        pair = (d.get('parentCollection') or False, d['name'])
        if pair in mapping:
            raise Problem('Ambiguous collection names under the same parent; use a clearer existing hierarchy first.')
        mapping[pair] = d['key']
    seen = set()
    for decision in decisions:
        key = valid_key(decision['key'])
        if key in seen or key not in items:
            raise Problem('Duplicate or out-of-scope decision key: ' + key)
        seen.add(key)
        d = items[key]
        if d.get('itemType') in EXCLUDED:
            raise Problem('Cannot classify attachments, notes or annotations.')
        confidence = decision.get('confidence')
        if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            raise Problem('Each decision needs confidence in [0,1].')
        if not decision.get('reason', '').strip():
            raise Problem('Each decision needs an evidence-based reason.')
        if confidence < 0.8:
            plan['review'].append(decision)
            continue
        tags = strings(decision.get('tags', []), 'tags')
        old = [t['tag'] for t in d.get('tags', [])]
        for prefix in ('状态/', '优先级/'):
            if len(set(t for t in tags + old if t.startswith(prefix))) > 1:
                raise Problem('Conflicting exclusive tags for {}: {}'.format(key, prefix))
        memberships = []
        paths = decision.get('collection_paths', [])
        if not isinstance(paths, list):
            raise Problem('collection_paths must be an array of arrays.')
        for path in paths:
            if not isinstance(path, list) or not path or any(not isinstance(p, str) or not p.strip() for p in path):
                raise Problem('Each collection path must contain nonempty names.')
            parent = False
            for raw_name in path:
                name = raw_name.strip()
                pair = (parent, name)
                if pair not in mapping:
                    ck = new_key()
                    mapping[pair] = ck
                    plan['create_collections'].append({'key': ck, 'version': 0, 'name': name, 'parentCollection': parent})
                parent = mapping[pair]
            memberships.append(parent)
        plan['changes'].append({'key': key, 'expected_version': d['version'],
                                'add_tags': tags, 'add_collections': list(dict.fromkeys(memberships)),
                                'reason': decision['reason'], 'confidence': confidence})
    return plan


def normalize_doi(value):
    text = unquote(str(value or '').strip()).casefold()
    return re.sub(r'^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)', '', text).strip()


def normalized_title(d):
    value = unicodedata.normalize('NFKC', d.get('title', '')).casefold()
    return ''.join(c for c in value if c.isalnum())


def import_plan(snap, raw_items, collection=None):
    if snap.get('scope_collection'):
        raise Problem('Import duplicate detection requires a full-library snapshot.')
    if not isinstance(raw_items, list):
        raise Problem('Import expects an array of Zotero API editable JSON objects.')
    plan = empty_plan(snap)
    existing = [obj_data(x) for x in snap['items']]
    collection_keys = {obj_data(x)['key'] for x in snap['collections']}
    if collection and collection not in collection_keys:
        raise Problem('Import collection is absent from target snapshot.')
    for raw in raw_items:
        d = copy.deepcopy(obj_data(raw))
        if d.get('itemType') in EXCLUDED or not d.get('itemType') or not d.get('title', '').strip():
            raise Problem('Import bibliographic records with itemType and title; attachments/notes are not supported.')
        if any(k in d for k in ('attachments', 'notes', 'itemID', 'uri')):
            raise Problem('This appears to be translator JSON, not API editable JSON. Convert and verify it first.')
        doi, title = normalize_doi(d.get('DOI')), normalized_title(d)
        same_doi = [x for x in existing if doi and normalize_doi(x.get('DOI')) == doi]
        same_title = [x for x in existing if title and normalized_title(x) == title]
        if same_doi:
            plan['skipped'].append({'title': d['title'], 'reason': 'same DOI', 'keys': [x['key'] for x in same_doi]})
            continue
        if same_title:
            plan['review'].append({'title': d['title'], 'reason': 'same normalized title; compare year and authors', 'keys': [x['key'] for x in same_title]})
            continue
        for field in ('key', 'version', 'dateAdded', 'dateModified', 'deleted', 'parentItem'):
            d.pop(field, None)
        d.update({'key': new_key(), 'version': 0, 'collections': [collection] if collection else [], 'relations': {}})
        d.setdefault('tags', [])
        d.setdefault('creators', [])
        plan['create_items'].append(d)
        existing.append(d)
    return plan


def merged_patch(current, change):
    tags = copy.deepcopy(current.get('tags', []))
    present = {x['tag'] for x in tags}
    for tag in strings(change.get('add_tags', []), 'add_tags'):
        if tag not in present:
            tags.append({'tag': tag, 'type': 0})
            present.add(tag)
    for prefix in ('状态/', '优先级/'):
        before = {x['tag'] for x in current.get('tags', []) if x['tag'].startswith(prefix)}
        after = {x['tag'] for x in tags if x['tag'].startswith(prefix)}
        if len(after) > 1 and after != before:
            raise Problem('Cannot add a conflicting exclusive tag: ' + prefix)
    cols = list(current.get('collections', []))
    for key in change.get('add_collections', []):
        valid_key(key)
        if key not in cols:
            cols.append(key)
    return {k: v for k, v in {'tags': tags, 'collections': cols}.items() if current.get(k, []) != v}


def check_plan(client, plan):
    if plan.get('schema') != SCHEMA or plan.get('library') != client.library:
        raise Problem('Plan schema/library differs from active connection.')
    create_cols = plan.get('create_collections', [])
    create_items = plan.get('create_items', [])
    create_keys = [valid_key(x['key']) for x in create_cols + create_items]
    change_keys = [valid_key(x['key']) for x in plan.get('changes', [])]
    if len(set(create_keys + change_keys)) != len(create_keys + change_keys):
        raise Problem('Plan contains duplicate object keys.')
    collections, _ = client.pages('/collections')
    available = {obj_data(x)['key'] for x in collections}
    for obj in create_cols:
        if set(obj) - {'key', 'version', 'name', 'parentCollection'} or obj.get('version') != 0 or not obj.get('name'):
            raise Problem('Invalid new collection payload.')
        if obj.get('parentCollection') and obj['parentCollection'] not in available:
            raise Problem('Collection parent is missing or out of order.')
        if obj['key'] in available:
            raise Problem('Collection key already exists. Rebuild the plan from a fresh snapshot.')
        if any(obj_data(x).get('name') == obj['name'] and (obj_data(x).get('parentCollection') or False) == (obj.get('parentCollection') or False) for x in collections):
            raise Problem('Collection with this name now exists. Rebuild the plan to reuse it.')
        available.add(obj['key'])
        collections.append(obj)
    for obj in create_items:
        if obj.get('version') != 0 or obj.get('itemType') in EXCLUDED or not obj.get('itemType') or not obj.get('title') or obj.get('deleted') or obj.get('parentItem'):
            raise Problem('Invalid new bibliographic record.')
        if any(k not in available for k in obj.get('collections', [])):
            raise Problem('New item references missing collection.')
        if client.maybe_get('/items/' + obj['key']) is not None:
            raise Problem('Import key already exists. Read the journal and rebuild; do not replay blindly.')
    if create_items:
        all_items, _ = client.pages('/items/top')
        existing = [obj_data(x) for x in all_items]
        for obj in create_items:
            doi, title = normalize_doi(obj.get('DOI')), normalized_title(obj)
            if any((doi and normalize_doi(x.get('DOI')) == doi) or (title and normalized_title(x) == title) for x in existing):
                raise Problem('An import candidate already exists by DOI/title. Rebuild the import plan.')
            existing.append(obj)
    for change in plan.get('changes', []):
        if set(change) - {'key', 'expected_version', 'add_tags', 'add_collections', 'reason', 'confidence'}:
            raise Problem('Changes may only add tags/collections.')
        if any(k not in available for k in change.get('add_collections', [])):
            raise Problem('Change references a missing collection.')
        current = obj_data(client.get('/items/' + change['key']))
        if current.get('itemType') in EXCLUDED or current.get('deleted'):
            raise Problem('Refusing changes to attachments/notes/annotations/trashed items.')
        if current['version'] != change['expected_version']:
            raise Problem('Version conflict for {}. Rebuild from fresh data.'.format(change['key']))
        merged_patch(current, change)


def apply_plan(client, plan, journal_path=None, execute=False):
    check_plan(client, plan)
    summary = {k: len(plan.get(k, [])) for k in ('create_collections', 'create_items', 'changes', 'review', 'skipped')}
    if not execute:
        return {'preflight': 'passed', 'executed': False, 'counts': summary}
    if not journal_path:
        raise Problem('--journal is required for execution.')
    fresh_output(journal_path)
    journal = {'schema': 'zotero-library-journal/v1', 'library': client.library,
               'started_at': now(), 'status': 'running', 'plan': plan, 'operations': []}
    save_json(journal_path, journal)
    try:
        for kind, objects in (('collections', plan.get('create_collections', [])), ('items', plan.get('create_items', []))):
            for obj in objects:
                entry = {'operation': 'create', 'kind': kind, 'key': obj['key'], 'before': None, 'requested': obj, 'status': 'pending'}
                journal['operations'].append(entry)
                save_json(journal_path, journal)
                response, _ = client.request('POST', client.prefix + '/' + kind, body=[obj])
                if not isinstance(response, dict) or response.get('failed') or not (response.get('successful') or response.get('success')):
                    raise Problem('Create did not return a confirmed success. Inspect object and journal.')
                after = obj_data(client.get('/{}/{}'.format(kind, obj['key'])))
                if kind == 'collections' and (after.get('name') != obj['name'] or (after.get('parentCollection') or False) != (obj.get('parentCollection') or False)):
                    raise Problem('Created collection verification failed.')
                if kind == 'items' and (after.get('title') != obj['title'] or after.get('itemType') != obj['itemType'] or not set(obj.get('collections', [])).issubset(after.get('collections', [])) or not {t['tag'] for t in obj.get('tags', [])}.issubset({t['tag'] for t in after.get('tags', [])})):
                    raise Problem('Created item verification failed.')
                entry.update({'status': 'confirmed', 'after': after})
                save_json(journal_path, journal)
        for change in plan.get('changes', []):
            current = obj_data(client.get('/items/' + change['key']))
            if current['version'] != change['expected_version']:
                raise Problem('Item changed after preflight: ' + change['key'])
            patch = merged_patch(current, change)
            entry = {'operation': 'update', 'kind': 'items', 'key': change['key'], 'before': current,
                     'requested': patch, 'status': 'pending' if patch else 'unchanged'}
            journal['operations'].append(entry)
            save_json(journal_path, journal)
            if patch:
                client.request('PATCH', client.prefix + '/items/' + change['key'], body=patch,
                               headers={'If-Unmodified-Since-Version': str(current['version'])})
                after = obj_data(client.get('/items/' + change['key']))
                if any(after.get(k) != v for k, v in patch.items()):
                    raise Problem('Read-back differs from requested fields: ' + change['key'])
                entry.update({'status': 'confirmed', 'after': after})
                save_json(journal_path, journal)
        journal['status'] = 'complete'
    except Exception as exc:
        journal['status'] = 'stopped'
        journal['error'] = str(exc) if isinstance(exc, Problem) else 'Unexpected local error; inspect journal.'
        save_json(journal_path, journal)
        raise
    save_json(journal_path, journal)
    return {'executed': True, 'confirmed': sum(x['status'] == 'confirmed' for x in journal['operations']),
            'unchanged': sum(x['status'] == 'unchanged' for x in journal['operations']),
            'review': len(plan.get('review', [])), 'skipped': len(plan.get('skipped', [])), 'journal': str(journal_path)}


def export_library(client, path, fmt, collection=None):
    fresh_output(path)
    snap = snapshot(client, collection)
    if fmt == 'json':
        save_json(path, snap)
        return len(snap['items'])
    keys = [obj_data(x)['key'] for x in snap['items']]
    chunks = []
    for start in range(0, len(keys), 50):
        value, headers = client.request('GET', client.prefix + '/items', params={
            'itemKey': ','.join(keys[start:start + 50]), 'format': fmt, 'limit': 50})
        version = next((v for k, v in headers.items() if k.lower() == 'last-modified-version'), None)
        if version != snap['library_version']:
            raise Problem('Library changed during export. Export again; output was not saved.')
        chunks.append(value)
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if fmt == 'csljson':
        combined = []
        for chunk in chunks:
            combined.extend(json.loads(chunk) if isinstance(chunk, str) else chunk)
        save_json(out, combined)
    elif fmt == 'csv':
        rows, fieldnames = [], []
        for chunk in chunks:
            reader = csv.DictReader(io.StringIO(chunk))
            for field in reader.fieldnames or []:
                if field not in fieldnames:
                    fieldnames.append(field)
            rows.extend(reader)
        with out.open('w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
    else:
        out.write_text('\n\n'.join(chunks), encoding='utf-8')
    return len(keys)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('status')
    p = sub.add_parser('collections')
    p.add_argument('--out')
    p = sub.add_parser('template')
    p.add_argument('--item-type', default='journalArticle')
    p.add_argument('--out', required=True)
    for name in ('snapshot', 'export'):
        p = sub.add_parser(name)
        p.add_argument('--out', required=True)
        p.add_argument('--collection')
        if name == 'export':
            p.add_argument('--format', choices=['json', 'bibtex', 'biblatex', 'ris', 'csljson', 'csv'], default='json')
    for name in ('plan-organize', 'plan-import'):
        p = sub.add_parser(name)
        p.add_argument('--snapshot', required=True)
        p.add_argument('--input', required=True)
        p.add_argument('--out', required=True)
        if name == 'plan-import':
            p.add_argument('--collection')
    p = sub.add_parser('apply')
    p.add_argument('--plan', required=True)
    p.add_argument('--execute', action='store_true')
    p.add_argument('--journal')
    args = parser.parse_args(argv)
    if args.command in ('plan-organize', 'plan-import'):
        fresh_output(args.out)
        snap, decisions = read_json(args.snapshot), read_json(args.input)
        plan = organize_plan(snap, decisions) if args.command == 'plan-organize' else import_plan(snap, decisions, args.collection)
        save_json(args.out, plan)
        result = {'plan': args.out, 'counts': {k: len(plan[k]) for k in ('changes', 'create_collections', 'create_items', 'review', 'skipped')}}
    else:
        spec, token = load_config()
        client = Client(spec, token)
        if args.command == 'status':
            result = connection_status(client)
        elif args.command == 'collections':
            if args.out:
                fresh_output(args.out)
            result = list_collections(client)
            if args.out:
                save_json(args.out, result)
        elif args.command == 'template':
            fresh_output(args.out)
            value, _ = client.request('GET', '/items/new', params={'itemType': args.item_type})
            save_json(args.out, value)
            result = {'template': args.out}
        elif args.command == 'snapshot':
            fresh_output(args.out)
            value = snapshot(client, args.collection)
            save_json(args.out, value)
            result = {'snapshot': args.out, 'items': len(value['items']), 'collections': len(value['collections'])}
        elif args.command == 'export':
            count = export_library(client, args.out, args.format, args.collection)
            result = {'export': args.out, 'format': args.format, 'items': count, 'pdf_files_included': False}
        else:
            result = apply_plan(client, read_json(args.plan), args.journal, args.execute)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (Problem, KeyError, ValueError, TypeError, OSError) as exc:
        message = str(exc) if isinstance(exc, Problem) else 'Invalid input or local file error ({}); inspect the input structure and file paths.'.format(type(exc).__name__)
        print(json.dumps({'error': message}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
