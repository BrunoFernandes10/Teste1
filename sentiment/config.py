"""Configuracao central do sistema, lida do ambiente (.env)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:  # carregamento opcional do .env
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv e conveniencia, nao requisito
    pass

ROOT = Path(__file__).resolve().parent.parent


def preparar_plataforma() -> None:
    """Ajustes obrigatorios por sistema operacional.

    No Windows, abrir um subprocesso (o navegador) so funciona sob o
    ProactorEventLoop. Alguns servidores selecionam o SelectorEventLoop, e ai o
    Playwright falha com NotImplementedError na hora de subir o Chrome.
    """
    if os.name != "nt":
        return
    import asyncio

    politica = getattr(asyncio, "WindowsProactorEventLoopPolicy", None)
    if politica and not isinstance(asyncio.get_event_loop_policy(), politica):
        asyncio.set_event_loop_policy(politica())


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "sim", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


# Ritmos de navegacao. Cada valor e um multiplicador aplicado sobre as pausas
# base do motor de comportamento humano.
PACES = {"calmo": 1.6, "normal": 1.0, "apressado": 0.6}


@dataclass
class Settings:
    """Parametros de execucao do sistema."""

    ig_username: str = field(default_factory=lambda: os.getenv("IG_USERNAME", "").lstrip("@"))
    ig_password: str = field(default_factory=lambda: os.getenv("IG_PASSWORD", ""))

    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    analyst_model: str = field(default_factory=lambda: os.getenv("ANALYST_MODEL", "claude-opus-5"))

    pace: str = field(default_factory=lambda: os.getenv("HUMAN_PACE", "normal").strip().lower())
    # Entrar a mao na janela do Chrome em vez de preencher o formulario. O
    # Instagram costuma recusar login automatizado mesmo com a senha correta;
    # entrando a mao uma vez, a sessao fica salva e as proximas sao diretas.
    login_manual: bool = field(default_factory=lambda: _bool("LOGIN_MANUAL", False))
    headless: bool = field(default_factory=lambda: _bool("HEADLESS", False))
    max_posts: int = field(default_factory=lambda: _int("MAX_POSTS", 40))
    max_comments_per_post: int = field(default_factory=lambda: _int("MAX_COMMENTS_PER_POST", 150))
    # Caminho explicito do executavel do Chrome/Chromium. Util quando o
    # navegador nao esta no local padrao do sistema.
    chrome_path: str = field(default_factory=lambda: os.getenv("CHROME_PATH", "").strip())
    session_dir: Path = field(
        default_factory=lambda: Path(os.getenv("SESSION_DIR", str(ROOT / "sessions"))).expanduser()
    )
    runs_dir: Path = field(default_factory=lambda: ROOT / "runs")

    # Base URL alternativa — usada pelos testes para apontar o coletor a um
    # Instagram simulado local. Em producao permanece vazia.
    base_url: str = field(default_factory=lambda: os.getenv("IG_BASE_URL", "https://www.instagram.com").rstrip("/"))

    @property
    def pace_factor(self) -> float:
        return PACES.get(self.pace, 1.0)

    @property
    def analyst_enabled(self) -> bool:
        return bool(self.anthropic_api_key)

    def ensure_dirs(self) -> None:
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    def redacted(self) -> dict:
        """Versao segura para log/telemetria: nunca expoe segredos."""
        return {
            "ig_username": self.ig_username or "(nao definido)",
            "ig_password": "***" if self.ig_password else "(nao definido)",
            "analyst": self.analyst_model if self.analyst_enabled else "lexical-offline",
            "pace": self.pace,
            "headless": self.headless,
            "max_posts": self.max_posts,
            "max_comments_per_post": self.max_comments_per_post,
        }


# ---------------------------------------------------------------------------
# Constantes do modelo analitico (documentadas no README e no dashboard).
# ---------------------------------------------------------------------------

# Peso afirmativo base de uma curtida em publicacao. Curtir e um ato deliberado
# de aprovacao; os 30% restantes sao distribuidos pelo clima dos comentarios
# daquela publicacao (contagio de contexto).
LIKE_AFFIRMATIVE_BASE = 0.70
LIKE_CONTEXT_WEIGHT = 1.0 - LIKE_AFFIRMATIVE_BASE

# Forca do encolhimento bayesiano da nota para 50 quando ha poucos dados.
SCORE_PRIOR_STRENGTH = 30

# Teto de penalidade de risco aplicada a nota final.
MAX_RISK_PENALTY = 15.0
