"""Bounded indexing of canonical parser chunks; no source text in broker payloads/logs."""
import hashlib
import os

import httpx

from .task_store import call

try:
    import jieba
except ImportError:  # Index stays keyword-only until dictionary support is deployed.
    jieba = None


def embedding(text: str):
    endpoint = os.getenv('EID_BGE_M3_ENDPOINT', '')
    if not endpoint.startswith('https://'):
        return None
    try:
        with httpx.Client(timeout=2.0, trust_env=False) as client:
            response = client.post(endpoint, json={'model': 'bge-m3-v1', 'text': text})
            response.raise_for_status()
            data = response.json()
        values = data['embedding']
        if data['model'] != 'bge-m3-v1' or not isinstance(values, list) or len(values) != 1024:
            return None
        import math
        if any(type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 100 for v in values):
            return None
        return '[' + ','.join(str(v) for v in values) + ']'
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return None


def index_once():
    rows = call('SELECT eid_search_pending_v1(%s,%s)',
                (os.getenv('EID_BGE_M3_ENDPOINT', '').startswith('https://'), jieba is not None))
    if not isinstance(rows, list):
        return
    for row in rows:
        try:
            text = row['text']
            if hashlib.sha256(text.encode('utf-8')).hexdigest() != row['hash']:
                continue
            vector = embedding(text)
            terms = ' '.join(jieba.cut(text[:4000]))[:10000] if jieba is not None else None
            call('SELECT eid_search_index_v1(%s,%s,%s,%s,%s,%s,%s)',
                 (row['attachment_id'], row['page'], row['ordinal'], row['hash'],
                  vector, 'bge-m3-v1' if vector else None, terms))
        except Exception:
            # Never let framework exception logging render a SQL parameter containing a passage.
            continue


def register(app):
    @app.task(name='eid.knowledge.index.v1', queue='retrieval', ignore_result=True)
    def index_attachments():
        index_once()
