"""Read-only source contracts for review authorization and stale result eligibility."""
from types import SimpleNamespace
from edw_api.review.routes import eligible, input_hash, view
from edw_api.review.rules import CATEGORIES, RULE_VERSION


def test_old_run_cannot_certify_new_head():
    row = {'id': 'old', 'document_version_id': 'old', 'document_revision': 1,
           'template_version_id': 'template', 'rule_version': 'local-review-1', 'model_version': 'none',
           'content_hash': 'a' * 64, 'state': 'COMPLETED', 'created_at': None, 'error_code': None}
    head = {'head_version_id': 'new', 'revision': 2, 'content_hash': 'b' * 64}
    result = view(row, head)
    assert result['state'] == 'STALE'
    assert result['current_eligible'] is False


def test_missing_required_result_and_revoked_epoch_never_certify():
    row = {'state': 'COMPLETED', 'document_version_id': 'v1', 'document_revision': 1,
           'content_hash': 'a' * 64, 'policy_epoch': [1, 1, 1], 'rule_version': RULE_VERSION,
           'model_version': 'none'}
    head = {'head_version_id': 'v1', 'revision': 1, 'content_hash': 'a' * 64}
    results = [{'category': category, 'state': 'COMPLETED', 'rule_version': RULE_VERSION,
                'model_version': 'none'} for category in CATEGORIES]
    assert eligible(row, head, SimpleNamespace(policy_epoch=(1, 1, 1)), results)
    assert not eligible(row, head, SimpleNamespace(policy_epoch=(2, 1, 1)), results)
    assert not eligible(row, head, SimpleNamespace(policy_epoch=(1, 1, 1)), results[:-1])
    results[0]['state'] = 'FAILED'
    assert not eligible(row, head, SimpleNamespace(policy_epoch=(1, 1, 1)), results)


def test_review_input_digest_changes_when_claim_or_source_changes():
    baseline = input_hash([{'status': 'supported'}], [], [])
    assert baseline != input_hash([{'status': 'unknown'}], [], [])
    assert baseline != input_hash([{'status': 'supported'}], [{'key': '客户', 'value': '甲'}], [])
