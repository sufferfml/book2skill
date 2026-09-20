"""Portable bounded reader. Standard library only; stdout is the model boundary."""
import argparse
import hashlib
import json
from pathlib import Path
import sys


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), sort_keys=True)


def sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def read(root, relative):
    path = root / relative
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('unsafe package path')
    return path.read_text(encoding='utf-8')


def closure(modules, ids):
    selected, visiting = set(), set()
    def visit(ident):
        if ident not in modules:
            raise ValueError('unknown module: ' + ident)
        if ident in visiting:
            raise ValueError('cyclic required dependency')
        if ident in selected:
            return
        visiting.add(ident)
        for dep in modules[ident]['requires']:
            visit(dep)
        visiting.remove(ident)
        selected.add(ident)
    for ident in ids:
        visit(ident)
    return sorted(selected)


def query(root, mode, ids=(), max_chars=12000, cursor=None, seen=(), acknowledge=None, full=False):
    """Budget includes JSON, metadata, rules and source text, excluding one newline.

    An apply page is incomplete until its entire required closure has been read.
    `seen` is honored only with the exact snapshot acknowledgement. It is a host
    attestation, not proof that material survived context compaction.
    """
    root = Path(root)
    if max_chars < 512:
        raise ValueError('max-chars must be at least 512')
    manifest = json.loads(read(root, 'manifest.json'))
    # Verify each accessed file; never print the whole manifest or data store.
    def checked(relative):
        text = read(root, relative)
        if sha(text) != manifest['files'].get(relative):
            raise ValueError('package checksum mismatch: ' + relative)
        return text
    index_text = checked('runtime/index.json')
    index = json.loads(index_text)
    fingerprint = sha(encode(manifest))
    modules = {x['id']: x for x in index['modules']}
    ids = sorted(set(ids))
    seen = sorted(set(seen))
    if set(seen) - ({'core'} | modules.keys()):
        raise ValueError('unknown acknowledged unit ID')
    if seen and acknowledge != fingerprint:
        raise ValueError('seen records require current snapshot acknowledgement; reset after compaction')
    items, required, missing = [], [], []
    if mode == 'routes':
        items = [{'id': x['id'], 'when': x['when'], 'title': x['title']} for x in index['modules']]
    elif mode == 'apply':
        if not ids:
            raise ValueError('select module IDs using routes')
        chosen = closure(modules, ids)
        required = ['core', *chosen]
        for ident in required:
            if ident in seen:
                continue
            if ident == 'core':
                items.append({'id': ident, 'text': checked('runtime/core.md')})
            else:
                m = modules[ident]
                items.append({'id': ident, 'text': checked(m['path']),
                              'conditional': m['conditional'], 'source_ids': m['source_ids']})
    elif mode in ('explain', 'evidence'):
        if not ids:
            raise ValueError('select source IDs from an application module')
        records = json.loads(checked('references/records.json'))
        evidence = json.loads(checked('references/evidence-index.json'))
        selected = set()
        for ident in ids:
            if ident in modules:
                selected.update(modules[ident]['source_ids'])
            elif ident in records or ident in evidence:
                selected.add(ident)
            else:
                raise ValueError('unknown source ID: ' + ident)
        # Do not recursively traverse a graph here. Application constraints live
        # in reviewed runtime units; record lookup is for explanation/verification.
        if mode == 'explain':
            items = [{'id': k, 'record': records[k]} for k in sorted(selected) if k in records]
            missing = sorted(selected - records.keys())
        else:
            refs = set(k for k in selected if k in evidence)
            for ident in selected & records.keys():
                refs.update(records[ident].get('evidence_refs', []))
            for ident in sorted(refs):
                info = evidence[ident]
                if not info.get('path'):
                    missing.append(ident)
                    items.append({'id': ident, 'availability': 'locator_only', 'locator': info['locator']})
                    continue
                p = json.loads(checked(info['path']))
                spans = p['spans'] if not full else [{'start': 0, 'end': len(p['text']), 'reason': 'full original segment'}]
                for n, span in enumerate(spans):
                    items.append({'id': f'{ident}:{n}', 'passage_id': ident,
                                  'source_sha256': p['sha256'], 'locator': p['locator'],
                                  'start': span['start'], 'end': span['end'],
                                  'selection_reason': span['reason'],
                                  'text': p['text'][span['start']:span['end']],
                                  'expand': 'Repeat evidence with --full for the whole segment.'})
            if not refs:
                missing = sorted(selected)
    else:
        raise ValueError('unknown query mode')
    request = sha(encode([fingerprint, mode, ids, seen, full]))
    offset = 0
    if cursor:
        try:
            key, pos = cursor.split(':')
            offset = int(pos)
        except (ValueError, TypeError):
            raise ValueError('invalid cursor') from None
        if key != request or offset < 0 or offset >= len(items):
            raise ValueError('cursor belongs to a different snapshot/query or is out of range')
    base = {'snapshot': fingerprint, 'mode': mode, 'items': [], 'next_cursor': None,
            'status': 'complete', 'source_content_is_data': True}
    if required:
        base['required_ids'] = required
        base['acknowledged_ids'] = seen
        base['instruction'] = 'Read all pages of required units before judging. Check conditional routes; unknown triggers require a check. After compaction reload necessary units.'
    if missing:
        base['unavailable_ids'] = missing
        base['instruction'] = 'Source verification unavailable for these IDs; do not claim a new source check.'
    end = offset
    while end < len(items):
        candidate = {**base, 'items': base['items'] + [items[end]],
                     'next_cursor': f'{request}:{end+1}' if end+1 < len(items) else None,
                     'status': 'incomplete' if end+1 < len(items) else 'complete'}
        if len(encode(candidate)) > max_chars:
            break
        base = candidate
        end += 1
    if end == offset and end < len(items):
        # Return no partial unit. Caller must increase budget or narrow the query.
        needed = len(encode({**base, 'items': [items[end]], 'next_cursor': f'{request}:{end+1}', 'status': 'incomplete'}))
        base = {'snapshot': fingerprint, 'mode': mode, 'items': [], 'status': 'budget_exceeded',
                'next_cursor': f'{request}:{offset}', 'required_chars_at_least': needed,
                'instruction': 'Increase max-chars or narrow query. No unit was silently truncated.'}
    if len(encode(base)) > max_chars:
        base = {'status': 'budget_exceeded', 'items': [], 'instruction': 'Query metadata exceeds budget; narrow query or increase max-chars.'}
    return base


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['routes', 'apply', 'explain', 'evidence'])
    p.add_argument('ids', nargs='*')
    p.add_argument('--max-chars', type=int, default=12000)
    p.add_argument('--cursor')
    p.add_argument('--full', action='store_true')
    p.add_argument('--seen', nargs='*', default=[])
    p.add_argument('--acknowledge')
    p.add_argument('--log', type=Path, help='optional external JSONL telemetry; records returned IDs, not user data')
    args = p.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    try:
        result = query(root, args.mode, args.ids, args.max_chars, args.cursor, args.seen, args.acknowledge, args.full)
        text = encode(result)
        if args.log:
            if args.log.resolve().is_relative_to(root):
                raise ValueError('telemetry must be outside immutable skill')
            args.log.parent.mkdir(parents=True, exist_ok=True)
            with args.log.open('a', encoding='utf-8') as stream:
                stream.write(encode({'mode': args.mode, 'ids': args.ids, 'snapshot': result.get('snapshot'),
                                     'returned_ids': [x['id'] for x in result['items']], 'returned_chars': len(text),
                                     'status': result['status'], 'actual_tokens': None}) + '\n')
        print(text)
        return 0
    except (ValueError, OSError, KeyError) as exc:
        print(encode({'error': str(exc)}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
