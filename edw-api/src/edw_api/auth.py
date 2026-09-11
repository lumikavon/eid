from dataclasses import dataclass

import jwt
from fastapi import Header
from jwt import PyJWKClient

from .config import Settings
from .errors import ApiError

OIDC_JWKS_TIMEOUT_SECONDS = 2.0


@dataclass(frozen=True)
class Actor:
    subject: str


class OidcVerifier:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.jwks = PyJWKClient(
            settings.oidc_jwks_url,
            cache_jwk_set=True,
            lifespan=300,
            timeout=OIDC_JWKS_TIMEOUT_SECONDS,
        )

    def verify(self, token: str) -> Actor:
        try:
            key = self.jwks.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                key.key,
                algorithms=["RS256"],
                audience=self.settings.oidc_audience,
                issuer=self.settings.oidc_issuer,
                options={"require": ["exp", "iat", "sub"]},
                leeway=0,
            )
        except jwt.PyJWTError as exc:
            raise ApiError(401, "INVALID_TOKEN", "身份令牌无效或已过期") from exc
        if claims.get("typ") != "Bearer":
            raise ApiError(401, "INVALID_TOKEN", "身份令牌无效或已过期")
        return Actor(subject=str(claims["sub"]))


def bearer_token(authorization: str | None = Header(default=None)) -> str:
    if not authorization:
        raise ApiError(401, "AUTHENTICATION_REQUIRED", "需要 Bearer 身份令牌")
    scheme, separator, credentials = authorization.partition(" ")
    if not separator or scheme.casefold() != "bearer":
        raise ApiError(401, "AUTHENTICATION_REQUIRED", "需要 Bearer 身份令牌")
    token = credentials.strip()
    if not token:
        raise ApiError(401, "AUTHENTICATION_REQUIRED", "需要 Bearer 身份令牌")
    return token
