"""Single-provider JSON proposal adapter; no tools, redirects, or arbitrary endpoints."""
import ipaddress
import json
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..errors import ApiError
from .policy import PROMPT, input_token_ceiling


class Proposal(BaseModel):
    model_config = ConfigDict(extra='forbid')
    proposal: str = Field(min_length=1, max_length=8192)


def endpoint_for(settings, route):
    if route == 'internal':
        endpoint, key = settings.model_internal_endpoint, settings.model_internal_key
    elif route == 'external':
        endpoint, key = settings.model_external_endpoint, settings.model_external_key
    else:
        raise ApiError(503, 'MODEL_ROUTE_MISSING', '模型路由未配置')
    try:
        parsed = urlsplit(endpoint)
        host, port = parsed.hostname, parsed.port
    except ValueError as exc:
        raise ApiError(503, 'MODEL_ROUTE_MISSING', '模型路由未配置') from exc
    if (not key or not endpoint or parsed.scheme != 'https' or not host
            or parsed.username or parsed.password or parsed.fragment or parsed.query
            or parsed.path != '/generate' or port not in (None, 443)):
        raise ApiError(503, 'MODEL_ROUTE_MISSING', '模型路由未配置')
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if route == 'external' and (address is not None or not settings.model_external_approved_host
                                or host != settings.model_external_approved_host):
        # An independent server-side gateway allowlist is required for external egress.
        raise ApiError(503, 'MODEL_ROUTE_MISSING', '模型外发网关未批准')
    if address is not None and not address.is_global:
        raise ApiError(503, 'MODEL_ROUTE_MISSING', '模型路由未配置')
    # Only a trusted, non-proxied deployment network may resolve hostname endpoints.
    return endpoint, key


def generate(settings, policy, decision, *, schema=Proposal):
    endpoint, key = endpoint_for(settings, decision.route)
    body = {'model': policy.model_id, 'prompt': PROMPT, 'input': decision.safe_input,
            'max_output_tokens': policy.max_output_tokens}
    repair_count = 0
    for index in range(2):
        try:
            with httpx.Client(timeout=policy.timeout_seconds, trust_env=False,
                              follow_redirects=False) as client:
                with client.stream('POST', endpoint, headers={'Authorization': f'Bearer {key}'}, json=body) as response:
                    if response.status_code != 200:
                        raise ApiError(503, 'MODEL_PROVIDER_UNAVAILABLE', '模型服务不可用', retryable=True)
                    chunks = []
                    size = 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > 32768:
                            raise ApiError(422, 'MODEL_OUTPUT_INVALID', '模型响应超过大小上限')
                        chunks.append(chunk)
            content = b''.join(chunks)
            if not content:
                raise ApiError(503, 'MODEL_PROVIDER_UNAVAILABLE', '模型服务不可用', retryable=True)
            raw = json.loads(content)
            if (not isinstance(raw, dict) or raw.get('model') != policy.model_id
                    or not isinstance(raw.get('output'), dict)
                    or not isinstance(raw.get('usage'), dict)):
                raise ValueError('Invalid model response envelope')
            usage = raw['usage']
            if (set(usage) != {'input_tokens', 'output_tokens', 'cost_micros'}
                    or any(type(usage[k]) is not int or usage[k] < 0 for k in usage)
                    or usage['input_tokens'] > input_token_ceiling(decision.safe_input)
                    or usage['output_tokens'] > policy.max_output_tokens
                    or usage['cost_micros'] > policy.max_cost_micros):
                raise ApiError(422, 'MODEL_BUDGET_EXCEEDED', '模型用量超出预算')
            result = schema.model_validate(raw['output'])
            return result.model_dump(), usage, repair_count
        except httpx.HTTPError as exc:
            raise ApiError(503, 'MODEL_PROVIDER_UNAVAILABLE', '模型服务不可用', retryable=True) from exc
        except json.JSONDecodeError as exc:
            if index:
                raise ApiError(422, 'MODEL_OUTPUT_INVALID', '模型响应结构无效',
                               details={'repair_count': 1}) from exc
            repair_count = 1
        except (ValidationError, ValueError) as exc:
            if index:
                raise ApiError(422, 'MODEL_OUTPUT_INVALID', '模型响应结构无效',
                               details={'repair_count': 1}) from exc
            # Retry the exact pinned Prompt once; no unversioned instruction or raw output.
            repair_count = 1
    raise ApiError(422, 'MODEL_OUTPUT_INVALID', '模型响应结构无效')
