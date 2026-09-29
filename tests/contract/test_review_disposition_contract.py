"""审校处置矩阵的离线契约；本轮仅编译，不运行套件。"""
from uuid import uuid4

from edw_api.review.routes import DispositionRequest, disposition_digest, issue_view, same_defect


def test_four_actions_are_distinct_and_idempotent_input_is_stable():
    base = dict(base_version_id=uuid4(), base_revision=2)
    commands = [DispositionRequest(request_key=uuid4(), action=action, **base)
                for action in ('accept', 'reject', 'modify', 'handled')]
    assert len({disposition_digest(command) for command in commands}) == 4
    assert disposition_digest(commands[0]) == disposition_digest(
        commands[0].model_copy(update={'request_key': uuid4()}))


def test_rejection_and_pending_recheck_still_block_critical_issue():
    ast = {'document': {'sections': []}}
    issue = dict(id='issue', category='fact', rule_id='unsupported', severity='critical',
                 section_id=None, block_id=None, claim_id=None, source_id=None,
                 quote='事实', impact='影响', suggestion='建议', details={})
    for action, status in [('reject', 'REJECTED'), ('accept', 'PENDING_RECHECK'),
                           ('modify', 'MODIFY'), (None, 'OPEN')]:
        projected = issue_view(dict(issue, disposition_action=action,
                                    disposition_reason='有争议' if action == 'reject' else None),
                               ast, sources_current=True)
        assert projected['status'] == status and projected['blocking']
    assert issue_view(dict(issue, disposition_action='handled', recheck_version_id='current'), ast,
                      sources_current=True, current_version_id='current')['blocking'] is False
    assert issue_view(dict(issue, disposition_action='handled'), ast,
                      sources_current=True)['blocking'] is True


def test_recheck_must_not_rediscover_the_same_defect():
    original = dict(category='safety', rule_id='unsafe_claim', section_id=uuid4(),
                    block_id=uuid4(), claim_id=uuid4())
    assert same_defect(original, dict(original))
    assert not same_defect(original, dict(original, rule_id='other'))
