"""Trava de somente-leitura.

O requisito e categorico: o sistema pode ver, mas nao pode tocar. Confiar
apenas em "nao chamar a funcao de curtir" e fraco — um clique acidental, um
duplo-clique na foto ou um atalho de teclado ja bastaria. Entao a garantia e
posta na camada de rede: qualquer requisicao que altere estado no Instagram e
abortada antes de sair do navegador, e o incidente fica registrado.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Endpoints que MODIFICAM estado. Se algum destes for chamado, abortamos.
MUTATION_PATTERNS = [
    r"/web/likes/\d+/(un)?like/",
    r"/api/v1/media/[^/]+/(un)?like/",
    r"/web/comments/\d+/(add|delete)/",
    r"/api/v1/media/[^/]+/comment/",
    r"/api/v1/media/[^/]+/comment/[^/]+/delete/",
    r"/web/friendships/\d+/(un)?follow/",
    r"/api/v1/friendships/(create|destroy)/",
    r"/api/v1/media/[^/]+/(save|unsave)/",
    r"/web/save/\d+/(un)?save/",
    r"/direct_v2/",
    r"/api/v1/direct_v2/",
    r"/create/configure/",
    r"/api/v1/media/configure",
    r"/stories/reel/seen",
    r"/api/v1/story_interactions/",
    r"/logging_client_events",  # telemetria de interacao: desnecessaria
]

# Palavras que denunciam uma mutacao GraphQL mesmo sem rota reveladora.
GRAPHQL_MUTATION_HINTS = (
    "uselikemediamutation",
    "usefollowmutation",
    "commentcreate",
    "mediaLike",
    "mutation",
)

# Rotas de autenticacao que PRECISAM passar (login e um POST legitimo).
AUTH_ALLOWLIST = [
    r"/accounts/login/ajax/",
    r"/api/v1/web/accounts/login/",
    r"/api/v1/accounts/login/",
    r"/challenge/",
    r"/api/v1/web/accounts/two_factor",
    r"/accounts/two_factor",
    r"/ajax/bz",
]

_MUTATION_RE = [re.compile(p, re.I) for p in MUTATION_PATTERNS]
_AUTH_RE = [re.compile(p, re.I) for p in AUTH_ALLOWLIST]


@dataclass
class ReadOnlyGuard:
    """Instala o bloqueio em um contexto Playwright e audita o que barrou."""

    blocked: list[str] = field(default_factory=list)
    allowed_auth: list[str] = field(default_factory=list)

    def classify(self, url: str, method: str, post_data: str | None = None) -> str:
        """Devolve 'permitir' ou 'bloquear' para uma requisicao."""
        if any(rx.search(url) for rx in _AUTH_RE):
            return "permitir"
        if any(rx.search(url) for rx in _MUTATION_RE):
            return "bloquear"
        if method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
            body = (post_data or "").lower()
            if any(hint.lower() in body for hint in GRAPHQL_MUTATION_HINTS):
                return "bloquear"
            if any(hint.lower() in url.lower() for hint in GRAPHQL_MUTATION_HINTS):
                return "bloquear"
        return "permitir"

    async def install(self, context) -> None:
        """Registra a rota de interceptacao no contexto do navegador."""

        async def _route(route, request):
            try:
                decision = self.classify(request.url, request.method, request.post_data)
            except Exception:
                decision = "permitir"
            if decision == "bloquear":
                self.blocked.append(f"{request.method} {request.url}")
                await route.abort()
                return
            if any(rx.search(request.url) for rx in _AUTH_RE):
                self.allowed_auth.append(f"{request.method} {request.url}")
            await route.continue_()

        await context.route("**/*", _route)

    def report(self) -> dict:
        return {
            "requisicoes_de_escrita_bloqueadas": len(self.blocked),
            "amostra": self.blocked[:10],
        }
