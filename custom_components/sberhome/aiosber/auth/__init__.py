"""Auth-слой aiosber.

Поток:
1. `pkce.PkceParams` — генерация verifier/challenge для OAuth2 PKCE.
2. `pkce.build_authorize_url()` — URL для редиректа пользователя на id.sber.ru.
3. `oauth.exchange_code_for_tokens()` — обмен authorization_code → SberID токены.
4. `companion.exchange_for_companion_token()` — обмен SberID access → companion token.
5. `manager.AuthManager` — оборачивает всё это + автоматический refresh.
6. `store.TokenStore` (Protocol) — хранилище токенов: in-memory / file / HA config_entry.

Использование (CLI scenario):

    pkce = PkceParams.generate()
    print("Open in browser:", build_authorize_url(client_id, pkce))
    redirect_url = input("Paste redirect URL: ")
    code = extract_code_from_redirect(redirect_url)
    sber_tokens = await exchange_code_for_tokens(http_client, code, pkce.verifier, client_id)
    companion = await exchange_for_companion_token(http_client, sber_tokens.access_token)
    store = InMemoryTokenStore()
    await store.save(companion)
    auth = AuthManager(http_client=http_client, store=store)
    token = await auth.access_token()  # авторefresh при истечении
"""

from __future__ import annotations

from .companion import exchange_for_companion_token
from .manager import AuthManager
from .oauth import exchange_code_for_tokens, refresh_sberid_tokens
from .pkce import PkceParams, build_authorize_url, extract_code_from_redirect
from .store import InMemoryTokenStore, TokenStore
from .tokens import CompanionTokens, SberIdTokens

__all__ = [
    "AuthManager",
    "CompanionTokens",
    "InMemoryTokenStore",
    "PkceParams",
    "SberIdTokens",
    "TokenStore",
    "build_authorize_url",
    "exchange_code_for_tokens",
    "exchange_for_companion_token",
    "extract_code_from_redirect",
    "refresh_sberid_tokens",
]
