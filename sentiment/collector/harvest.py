"""Colheita passiva dos dados que o proprio navegador ja baixou.

Em vez de raspar o HTML — que muda de nome de classe toda semana — este modulo
escuta as respostas JSON que o Instagram entrega ao navegador enquanto a sessao
humana navega. Nada e requisitado a mais: le-se apenas o que a pagina, aberta
por uma pessoa, ja carregou naturalmente.

O reconhecimento e feito por FORMATO e nao por endpoint, entao continua
funcionando quando a Meta renomeia rotas ou troca doc_ids do GraphQL.
"""

from __future__ import annotations

import json
from typing import Any, Iterator

from ..models import Comment, Post

MEDIA_TYPES = {1: "imagem", 2: "video", 8: "carrossel"}


def _walk(node: Any) -> Iterator[dict]:
    """Percorre recursivamente qualquer JSON devolvendo todos os dicionarios."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item)


def _first(node: dict, *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in node and node[key] not in (None, ""):
            return node[key]
    return default


def _caption(node: dict) -> str:
    caption = node.get("caption")
    if isinstance(caption, dict):
        return str(caption.get("text") or "")
    if isinstance(caption, str):
        return caption
    edges = (node.get("edge_media_to_caption") or {}).get("edges") or []
    if edges:
        return str((edges[0].get("node") or {}).get("text") or "")
    return ""


def _count(node: dict, *keys: str) -> int:
    for key in keys:
        value = node.get(key)
        if isinstance(value, dict) and "count" in value:
            try:
                return int(value["count"])
            except (TypeError, ValueError):
                continue
        if isinstance(value, (int, float)):
            return int(value)
    return 0


def is_media_node(node: dict) -> bool:
    """Um no de publicacao tem identificador, shortcode e data."""
    has_id = bool(_first(node, "pk", "id"))
    has_code = bool(_first(node, "code", "shortcode"))
    has_time = _first(node, "taken_at", "taken_at_timestamp", "device_timestamp") is not None
    return has_id and has_code and has_time


def is_comment_node(node: dict) -> bool:
    """Um comentario tem texto, autor e id — e nao tem shortcode."""
    if _first(node, "code", "shortcode"):
        return False
    if not isinstance(node.get("text"), str) or not node["text"].strip():
        return False
    user = node.get("user") or node.get("owner")
    if not isinstance(user, dict) or not user.get("username"):
        return False
    return bool(_first(node, "pk", "id"))


def _owner_username(node: dict) -> str:
    """Quem publicou. Essencial para nao misturar o feed com o perfil alvo."""
    for chave in ("user", "owner"):
        valor = node.get(chave)
        if isinstance(valor, dict) and valor.get("username"):
            return str(valor["username"]).lstrip("@")
    return ""


def parse_media(node: dict) -> Post:
    shortcode = str(_first(node, "code", "shortcode", default=""))
    media_type = node.get("media_type")
    if isinstance(media_type, int):
        kind = MEDIA_TYPES.get(media_type, "imagem")
    else:
        typename = str(node.get("__typename") or "").lower()
        kind = "video" if "video" in typename else "carrossel" if "sidecar" in typename else "imagem"
    if node.get("product_type") in {"clips", "reels"}:
        kind = "reel"
    prefix = "reel" if kind == "reel" else "p"
    return Post(
        id=str(_first(node, "pk", "id", default=shortcode)),
        shortcode=shortcode,
        url=f"https://www.instagram.com/{prefix}/{shortcode}/",
        created_at=_first(node, "taken_at", "taken_at_timestamp", "device_timestamp"),
        caption=_caption(node),
        like_count=_count(node, "like_count", "edge_liked_by", "edge_media_preview_like"),
        comment_count=_count(node, "comment_count", "edge_media_to_comment", "edge_media_preview_comment"),
        media_type=kind,
        is_pinned=bool(node.get("timeline_pinned_user_ids") or node.get("is_pinned")),
        owner=_owner_username(node),
    )


def parse_comment(node: dict, post_id: str) -> Comment:
    user = node.get("user") or node.get("owner") or {}
    parent = _first(node, "parent_comment_id", "parent_id")
    return Comment(
        id=str(_first(node, "pk", "id", default="")),
        post_id=post_id,
        author=str(user.get("username") or ""),
        text=str(node.get("text") or ""),
        created_at=_first(node, "created_at", "created_at_utc", "created_time"),
        like_count=_count(node, "comment_like_count", "like_count", "edge_liked_by"),
        is_reply=bool(parent),
        parent_id=str(parent) if parent else None,
    )


class Harvester:
    """Acumula publicacoes e comentarios vistos durante a sessao."""

    def __init__(self) -> None:
        self.posts: dict[str, Post] = {}
        self.comments: dict[str, Comment] = {}
        self.profile_nodes: list[dict] = []
        self.payloads_seen = 0

    # -- entrada ----------------------------------------------------------
    def ingest_text(self, body: str, current_post_id: str = "") -> None:
        try:
            data = json.loads(body)
        except (ValueError, TypeError):
            return
        self.ingest(data, current_post_id)

    def ingest(self, data: Any, current_post_id: str = "") -> None:
        """Analisa um payload JSON e extrai tudo que reconhecer."""
        self.payloads_seen += 1
        for node in _walk(data):
            if is_media_node(node):
                post = parse_media(node)
                if post.shortcode:
                    self._merge_post(post)
                    current_post_id = current_post_id or post.id
            elif is_comment_node(node):
                comment = parse_comment(node, current_post_id)
                if comment.id and comment.text.strip():
                    self.comments.setdefault(comment.id, comment)
            elif node.get("username") and ("edge_followed_by" in node or "follower_count" in node):
                self.profile_nodes.append(node)

    def _merge_post(self, post: Post) -> None:
        """Publicacoes chegam em pedacos; mantemos sempre a versao mais rica."""
        existing = self.posts.get(post.shortcode)
        if not existing:
            self.posts[post.shortcode] = post
            return
        existing.like_count = max(existing.like_count, post.like_count)
        existing.comment_count = max(existing.comment_count, post.comment_count)
        existing.caption = existing.caption or post.caption
        existing.created_at = existing.created_at or post.created_at
        existing.is_pinned = existing.is_pinned or post.is_pinned
        existing.owner = existing.owner or post.owner

    # -- saida ------------------------------------------------------------
    def attach_comments(self) -> list[Post]:
        """Liga cada comentario a sua publicacao e devolve a lista pronta."""
        by_id = {p.id: p for p in self.posts.values()}
        for comment in self.comments.values():
            post = by_id.get(comment.post_id)
            if post is None:
                continue
            if all(existing.id != comment.id for existing in post.comments):
                post.comments.append(comment)
        for post in self.posts.values():
            post.comments.sort(key=lambda c: (c.created_at is None, c.created_at))
        return sorted(
            self.posts.values(),
            key=lambda p: (p.created_at is None, p.created_at),
            reverse=True,
        )

    def profile_fields(self) -> dict:
        """Melhor visao do perfil a partir dos payloads observados."""
        best: dict = {}
        for node in self.profile_nodes:
            followers = _count(node, "edge_followed_by", "follower_count")
            if followers >= best.get("followers", -1):
                best = {
                    "username": node.get("username", ""),
                    "full_name": node.get("full_name") or "",
                    "biography": node.get("biography") or "",
                    "followers": followers,
                    "following": _count(node, "edge_follow", "following_count"),
                    "posts_total": _count(node, "edge_owner_to_timeline_media", "media_count"),
                    "is_private": bool(node.get("is_private")),
                }
        return best
