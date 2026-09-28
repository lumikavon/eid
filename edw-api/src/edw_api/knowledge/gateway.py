"""Pinned, signed enterprise gateway protocol; unproved capability or ACL fails closed.

Gateway must enforce current per-actor ACL BEFORE searching and independently verify
current ACL/version for each hit. Only a trusted deployment with a pinned key is usable.
No enterprise vector is copied into the local index.
"""
import hashlib
import hmac
import json
from datetime import datetime, timezone
from secrets import token_hex

import httpx


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':'),
                      allow_nan=False).encode('utf8')


def signed(reply, key, nonce, operation):
    try:
        body, signature = reply['body'], reply['signature']
        if (not isinstance(signature, str) or len(signature) != 64
                or not hmac.compare_digest(hmac.new(key.encode(), canonical(body), hashlib.sha256).hexdigest(), signature)
                or body['nonce'] != nonce or body['operation'] != operation):
            return None
        expiry = datetime.fromisoformat(body['expires_at'].replace('Z', '+00:00'))
        if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc) or (expiry-datetime.now(timezone.utc)).total_seconds() > 30:
            return None
        return body
    except (KeyError, TypeError, ValueError, OverflowError):
        return None


def exchange(client, url, key, operation, payload):
    nonce = token_hex(16)
    request = {'nonce': nonce, 'operation': operation, **payload}
    signature = hmac.new(key.encode(), canonical(request), hashlib.sha256).hexdigest()
    reply = client.post(url.rstrip('/') + '/' + operation,
                        json={'body': request, 'signature': signature}).json()
    return signed(reply, key, nonce, operation)


def retrieve(settings, subject, workspace_id, anchor, context, query, category, limit,
             source_version=None, context_version=None):
    """Returns (validated hits, available). Never returns partial enterprise content on failure."""
    url, key = settings.knowledge_gateway_url, settings.knowledge_gateway_key
    if not url.startswith('https://') or len(key) < 32:
        return [], False
    binding = {'subject': subject, 'workspace_id': str(workspace_id),
               'actor_id': context.actor_id, 'policy_epoch': list(context.policy_epoch),
               'project_id': anchor['project_id'], 'classification': context.classification,
               'context_document_id': str(anchor['id']),
               'context_version_id': str(context_version) if context_version else None}
    try:
        with httpx.Client(timeout=2.0, trust_env=False, follow_redirects=False) as client:
            capabilities = exchange(client, url, key, 'capabilities', binding)
            if not capabilities or capabilities.get('binding') != binding or capabilities.get('features') != {
                'acl_prefilter': True, 'current_acl_verify': True, 'exact_locator': True,
                'source_version': True, 'expiry': True, 'keyword': True}:
                return [], False
            request = {**binding, 'query': query, 'category': category, 'limit': limit,
                       'source_version': source_version}
            reply = exchange(client, url, key, 'search', request)
            if not reply or reply.get('binding') != binding or reply.get('query_sha256') != hashlib.sha256(query.encode()).hexdigest():
                return [], False
            rows = reply.get('items')
            if not isinstance(rows, list) or len(rows) > limit:
                return [], False
            output = []
            for item in rows:
                if not isinstance(item, dict) or set(item) != {'source_id','version','chunk_hash','locator',
                        'excerpt','classification','project_id','valid_until','category'}:
                    return [], False
                expiry = datetime.fromisoformat(item['valid_until'].replace('Z', '+00:00'))
                if (not isinstance(item['source_id'], str) or not 1 <= len(item['source_id']) <= 128
                        or not isinstance(item['version'], str) or not 1 <= len(item['version']) <= 128
                        or not isinstance(item['chunk_hash'], str) or len(item['chunk_hash']) != 64
                        or not isinstance(item['locator'], str) or not 1 <= len(item['locator']) <= 512
                        or not isinstance(item['excerpt'], str) or not 1 <= len(item['excerpt']) <= 4000
                        or type(item['classification']) is not int or item['classification'] > context.classification
                        or item['classification'] < 0 or item['project_id'] != anchor['project_id']
                        or (source_version is not None and item['version'] != source_version)
                        or item['category'] not in ('enterprise','golden')
                        or category not in ('all',item['category']) or expiry.tzinfo is None
                        or expiry <= datetime.now(timezone.utc)
                        or hashlib.sha256(item['excerpt'].encode()).hexdigest() != item['chunk_hash']):
                    return [], False
                output.append(item)
            # A distinct call must attest every returned (id, version, hash) under current ACL.
            sources = [{'source_id': x['source_id'], 'version': x['version'],
                        'chunk_hash': x['chunk_hash']} for x in output]
            verification = exchange(client, url, key, 'verify', {**binding, 'sources': sources})
            if (not verification or verification.get('binding') != binding
                    or verification.get('sources') != sources or verification.get('authorized') is not True
                    or verification.get('current') is not True):
                return [], False
            return [{**x, 'chain': 'enterprise', 'policy': 'gateway-current-acl-v1',
                     'keyword_version': 'gateway-declared', 'embedding_version': None} for x in output], True
    except (httpx.HTTPError, KeyError, TypeError, ValueError, OverflowError):
        return [], False


def verify_source(settings, subject, workspace_id, anchor, context, source, context_version=None):
    """Fresh signed excerpt + ACL proof for a pinned enterprise version, outside DB transactions."""
    url, key = settings.knowledge_gateway_url, settings.knowledge_gateway_key
    if not url.startswith('https://') or len(key) < 32:
        return None
    binding = {'subject': subject, 'workspace_id': str(workspace_id),
               'actor_id': context.actor_id, 'policy_epoch': list(context.policy_epoch),
               'project_id': anchor['project_id'], 'classification': context.classification,
               'context_document_id': str(anchor['id']),
               'context_version_id': str(context_version) if context_version else None}
    identity = {field: source[field] for field in ('source_id', 'version', 'chunk_hash', 'locator')}
    try:
        with httpx.Client(timeout=2.0, trust_env=False, follow_redirects=False) as client:
            capabilities = exchange(client, url, key, 'capabilities', binding)
            if not capabilities or capabilities.get('binding') != binding or capabilities.get('features') != {
                'acl_prefilter': True, 'current_acl_verify': True, 'exact_locator': True,
                'source_version': True, 'expiry': True, 'keyword': True}:
                return None
            reply = exchange(client, url, key, 'inspect', {**binding, 'source': identity})
            if not reply or reply.get('binding') != binding or reply.get('source') != identity or reply.get('authorized') is not True:
                return None
            text = reply.get('excerpt')
            expiry = datetime.fromisoformat(reply['valid_until'].replace('Z', '+00:00'))
            if (reply.get('project_id') != anchor['project_id']
                    or reply.get('current') is not True or reply.get('current_version') != source['version']
                    or type(reply.get('classification')) is not int
                    or reply['classification'] != source['classification']
                    or reply['classification'] > context.classification
                    or expiry.tzinfo is None or expiry <= datetime.now(timezone.utc)
                    or (source.get('effective_until') is not None and
                        source['effective_until'] > expiry)
                    or not isinstance(text, str) or not 1 <= len(text) <= 4000
                    or hashlib.sha256(text.encode()).hexdigest() != source['chunk_hash']):
                return None
            return text
    except (httpx.HTTPError, KeyError, TypeError, ValueError, OverflowError):
        return None
