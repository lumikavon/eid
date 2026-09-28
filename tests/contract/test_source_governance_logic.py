"""Deterministic ranking/applicability cases (deferred execution)."""
from datetime import datetime, timedelta, timezone
from edw_api.knowledge.governance import AUTHORITY, applicable, decorate, side

NOW = datetime.now(timezone.utc)
ANCHOR = {'project_id': 'P-1', 'product_id': 'model-a', 'customer_id': 'C-1'}


class FakeConnection:
    def __init__(self, assertions):
        self.assertions = assertions

    def execute(self, sql, params):
        if 'FROM knowledge_assertion' in sql:
            return self
        if 'FROM knowledge_conflict' in sql:
            return Empty()
        raise AssertionError(sql)

    def fetchall(self):
        return self.assertions


class Empty:
    def fetchall(self):
        return []


def source(level, version):
    return dict(id=version, chain='enterprise', source_id=version, version=version,
                chunk_hash='a'*64, locator='section 1', authority=level,
                effective_from=NOW-timedelta(days=1), effective_until=NOW+timedelta(days=1),
                project_id='P-1', product_id='model-a', customer_id='C-1')


def hit(row):
    return {k: row[k] for k in ('chain', 'source_id', 'version', 'chunk_hash', 'locator')}


def test_nine_tiers_do_not_infer_from_classification():
    assert len(AUTHORITY) == 9 and AUTHORITY[8] == 'llm_general'
    rows = [source(level, str(level)) for level in range(8, 0, -1)]
    result = decorate(FakeConnection(rows), ANCHOR, [dict(hit(r), classification=3 if r['authority']==1 else 0) for r in rows], 'w')
    assert [item['governance'][0]['authority'] for item in result] == list(range(1, 9))


def test_expired_or_inapplicable_source_is_not_reexposed_by_a_hit():
    expired = source(1, 'old')
    expired['effective_until'] = NOW-timedelta(seconds=1)
    assert not applicable(expired, ANCHOR)
    assert decorate(FakeConnection([expired]), ANCHOR, [hit(expired)], 'w') == []
    assert not applicable(source(1, 'law'), {**ANCHOR, 'product_id': 'different'})


def test_other_scope_assertion_does_not_expire_an_authorized_hit():
    other = source(1, 'shared-source')
    other['product_id'] = 'model-b'
    result = decorate(FakeConnection([other]), ANCHOR, [hit(other)], 'w')
    assert len(result) == 1 and result[0]['governance'] == []

def test_enterprise_side_never_uses_stored_statement_as_access():
    row = dict(source(1, 'law'), classification=0, statement='limit 10 kW',
               value='10', unit='kW', conditions='test', workspace_id='w')
    actor = type('Actor', (), {'classification': 0})()
    assert side(None, None, 'user', 'w', ANCHOR, actor, row, {}) == {'state': 'forbidden'}
    assert side(None, None, 'user', 'w', ANCHOR, actor, row, {'law': 'limit 10 kW'})['state'] == 'current'
    row['effective_until'] = NOW-timedelta(seconds=1)
    assert side(None, None, 'user', 'w', ANCHOR, actor, row, {'law': 'limit 10 kW'}) == {'state': 'forbidden'}
