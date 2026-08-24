"""Modelos de dados: captura, classificacao e relatorio final."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Literal, Optional

Sentiment = Literal["positivo", "neutro", "negativo"]
SENTIMENTS: tuple[Sentiment, ...] = ("positivo", "neutro", "negativo")


def _dt(value: Any) -> Optional[datetime]:
    """Converte epoch/ISO em datetime aware (UTC). Tolerante a lixo."""
    if value in (None, "", 0):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


# ---------------------------------------------------------------------------
# Camada de captura
# ---------------------------------------------------------------------------


@dataclass
class Comment:
    """Um comentario lido em uma publicacao (ou uma resposta a outro)."""

    id: str
    post_id: str
    author: str
    text: str
    created_at: Optional[datetime] = None
    like_count: int = 0
    is_reply: bool = False
    parent_id: Optional[str] = None

    def __post_init__(self) -> None:
        self.created_at = _dt(self.created_at)
        self.author = str(self.author or "").lstrip("@")
        self.like_count = int(self.like_count or 0)

    @property
    def author_url(self) -> str:
        return f"https://www.instagram.com/{self.author.lstrip('@')}/"

    def to_dict(self) -> dict:
        data = asdict(self)
        data["created_at"] = _iso(self.created_at)
        data["author_url"] = self.author_url
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Comment":
        return cls(
            id=str(data.get("id", "")),
            post_id=str(data.get("post_id", "")),
            author=str(data.get("author", "")).lstrip("@"),
            text=str(data.get("text", "")),
            created_at=_dt(data.get("created_at")),
            like_count=int(data.get("like_count") or 0),
            is_reply=bool(data.get("is_reply")),
            parent_id=data.get("parent_id"),
        )


@dataclass
class Post:
    """Uma publicacao lida do perfil."""

    id: str
    shortcode: str
    url: str
    created_at: Optional[datetime] = None
    caption: str = ""
    like_count: int = 0
    comment_count: int = 0
    media_type: str = "imagem"
    is_pinned: bool = False
    owner: str = ""          # quem publicou — separa o perfil analisado do feed
    comments: list[Comment] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.created_at = _dt(self.created_at)
        self.like_count = int(self.like_count or 0)
        self.comment_count = int(self.comment_count or 0)

    @property
    def comment_likes(self) -> int:
        return sum(c.like_count for c in self.comments)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "shortcode": self.shortcode,
            "url": self.url,
            "created_at": _iso(self.created_at),
            "caption": self.caption,
            "like_count": self.like_count,
            "comment_count": self.comment_count,
            "media_type": self.media_type,
            "is_pinned": self.is_pinned,
            "owner": self.owner,
            "comments": [c.to_dict() for c in self.comments],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Post":
        return cls(
            id=str(data.get("id", "")),
            shortcode=str(data.get("shortcode", "")),
            url=str(data.get("url", "")),
            created_at=_dt(data.get("created_at")),
            caption=str(data.get("caption") or ""),
            like_count=int(data.get("like_count") or 0),
            comment_count=int(data.get("comment_count") or 0),
            media_type=str(data.get("media_type") or "imagem"),
            is_pinned=bool(data.get("is_pinned")),
            owner=str(data.get("owner") or "").lstrip("@"),
            comments=[Comment.from_dict(c) for c in data.get("comments", [])],
        )


@dataclass
class Profile:
    username: str
    url: str
    full_name: str = ""
    biography: str = ""
    followers: int = 0
    following: int = 0
    posts_total: int = 0
    is_private: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Profile":
        return cls(
            username=str(data.get("username", "")).lstrip("@"),
            url=str(data.get("url", "")),
            full_name=str(data.get("full_name") or ""),
            biography=str(data.get("biography") or ""),
            followers=int(data.get("followers") or 0),
            following=int(data.get("following") or 0),
            posts_total=int(data.get("posts_total") or 0),
            is_private=bool(data.get("is_private")),
        )


@dataclass
class Capture:
    """Resultado bruto da sessao de leitura."""

    profile: Profile
    posts: list[Post]
    window_start: datetime
    window_end: datetime
    notes: list[str] = field(default_factory=list)
    captured_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        self.window_start = _dt(self.window_start) or datetime.now(timezone.utc)
        self.window_end = _dt(self.window_end) or datetime.now(timezone.utc)
        self.captured_at = _dt(self.captured_at) or datetime.now(timezone.utc)

    @property
    def all_comments(self) -> list[Comment]:
        return [c for p in self.posts for c in p.comments]

    def to_dict(self) -> dict:
        return {
            "profile": self.profile.to_dict(),
            "posts": [p.to_dict() for p in self.posts],
            "window_start": _iso(self.window_start),
            "window_end": _iso(self.window_end),
            "notes": self.notes,
            "captured_at": _iso(self.captured_at),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Capture":
        return cls(
            profile=Profile.from_dict(data.get("profile", {})),
            posts=[Post.from_dict(p) for p in data.get("posts", [])],
            window_start=_dt(data.get("window_start")) or datetime.now(timezone.utc),
            window_end=_dt(data.get("window_end")) or datetime.now(timezone.utc),
            notes=list(data.get("notes", [])),
            captured_at=_dt(data.get("captured_at")) or datetime.now(timezone.utc),
        )


# ---------------------------------------------------------------------------
# Camada de classificacao
# ---------------------------------------------------------------------------


@dataclass
class CommentInsight:
    """Saida do analista para um comentario."""

    comment_id: str
    sentiment: Sentiment = "neutro"
    confidence: float = 0.5
    intensity: float = 0.5
    themes: list[str] = field(default_factory=list)
    adjectives: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    risk_severity: float = 0.0
    language: str = "pt"
    is_spam: bool = False
    rationale: str = ""

    @property
    def weight(self) -> float:
        """Peso do comentario no balanco de sentimento."""
        return max(0.1, self.confidence) * (0.5 + self.intensity)

    def to_dict(self) -> dict:
        return asdict(self)


def normalize_sentiment(value: Any) -> Sentiment:
    """Aceita rotulos em pt/en e devolve o rotulo canonico."""
    text = str(value or "").strip().lower()
    if text in {"positivo", "positive", "pos", "bom", "good"}:
        return "positivo"
    if text in {"negativo", "negative", "neg", "ruim", "bad"}:
        return "negativo"
    return "neutro"


def clamp(value: Any, low: float = 0.0, high: float = 1.0, default: float = 0.5) -> float:
    try:
        return max(low, min(high, float(value)))
    except (TypeError, ValueError):
        return default


def pct(part: float, total: float) -> float:
    """Percentual com 1 casa; 0 quando nao ha base."""
    if not total:
        return 0.0
    return round(100.0 * part / total, 1)


def distribute(counts: dict[str, float]) -> dict[str, float]:
    """Converte contagens por sentimento em percentuais que somam ~100."""
    total = sum(counts.values())
    return {key: pct(value, total) for key, value in counts.items()}


def top_n(items: Iterable[tuple[str, float]], n: int) -> list[tuple[str, float]]:
    return sorted(items, key=lambda kv: (-kv[1], kv[0]))[:n]
