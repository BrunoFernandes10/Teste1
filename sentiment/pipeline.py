"""Orquestracao completa: navegar, ler, classificar, medir e interpretar."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

from .analysis.analyst import Analyst
from .analysis.scoring import build_metrics
from .config import Settings
from .models import Capture
from .collector.instagram import collect, parse_username

Progress = Callable[[str, str, int], None]


def parse_periodo(inicio: str, fim: str) -> tuple[datetime, datetime]:
    """Aceita YYYY-MM-DD e devolve o intervalo fechado em UTC."""
    try:
        d1 = datetime.fromisoformat(str(inicio).strip()).date()
        d2 = datetime.fromisoformat(str(fim).strip()).date()
    except ValueError as exc:
        raise ValueError("Datas devem estar no formato AAAA-MM-DD.") from exc
    if d1 > d2:
        d1, d2 = d2, d1
    start = datetime.combine(d1, time.min, tzinfo=timezone.utc)
    end = datetime.combine(d2, time.max, tzinfo=timezone.utc)
    return start, end


def periodo_relativo(dias: int) -> tuple[datetime, datetime]:
    fim = datetime.now(timezone.utc)
    return fim - timedelta(days=max(1, dias)), fim


def analisar_captura(
    capture: Capture, settings: Settings, progress: Optional[Progress] = None
) -> dict:
    """Classifica, mede e interpreta uma captura ja realizada."""
    say = progress or (lambda *_: None)
    analyst = Analyst(settings)

    # As respostas da propria marca nao entram na classificacao: nao sao
    # opiniao do publico e gastariam chamada de IA a toa.
    dono = (capture.profile.username or "").lower()
    comentarios = [c for c in capture.all_comments if c.author.lower() != dono]
    say("analisando", f"Classificando {len(comentarios)} comentarios do publico...", 92)

    def lote_feito(atual: int, total: int) -> None:
        say("analisando", f"Analisando lote {atual}/{total} de comentarios...", 92)

    insights = analyst.classify(comentarios, on_progress=lote_feito)

    say("analisando", "Consolidando metricas...", 96)
    metrics = build_metrics(capture, insights)

    say("analisando", "Redigindo a leitura executiva...", 98)
    narrativa = analyst.synthesize(capture, metrics)

    idiomas: dict[str, int] = {}
    for insight in insights.values():
        idiomas[insight.language] = idiomas.get(insight.language, 0) + 1

    return {
        "gerado_em": datetime.now(timezone.utc).isoformat(),
        "perfil": capture.profile.to_dict(),
        "periodo": {
            "inicio": capture.window_start.date().isoformat(),
            "fim": capture.window_end.date().isoformat(),
        },
        "resumo": narrativa["resumo"],
        "leitura_do_periodo": narrativa["leitura_do_periodo"],
        "insights_de_risco": narrativa["insights_de_risco"],
        "assuntos_potenciais": narrativa["assuntos_potenciais"],
        "recomendacoes_gerais": narrativa["recomendacoes_gerais"],
        **metrics,
        "qualidade_dos_dados": {
            "motor_de_analise": analyst.engine,
            "comentarios_classificados": len(insights),
            "spam_descartado": sum(1 for i in insights.values() if i.is_spam),
            "idiomas": idiomas,
            "observacoes": capture.notes,
            "avisos": analyst.warnings,
        },
        "conduta_da_sessao": {
            "somente_leitura": True,
            "interacoes_bloqueadas": {"requisicoes_de_escrita_bloqueadas": 0, "amostra": []},
            "ritmo": settings.pace,
        },
        "publicacoes": [
            {
                "url": p.url,
                "data": p.created_at.date().isoformat() if p.created_at else "",
                "legenda": (p.caption or "")[:180],
                "curtidas": p.like_count,
                "comentarios_lidos": len(p.comments),
                "tipo": p.media_type,
            }
            for p in capture.posts
        ],
    }


async def executar_analise(
    profile_url: str,
    inicio: str,
    fim: str,
    settings: Optional[Settings] = None,
    progress: Optional[Progress] = None,
) -> dict:
    """Fluxo completo de ponta a ponta."""
    settings = settings or Settings()
    say = progress or (lambda *_: None)
    start, end = parse_periodo(inicio, fim)
    username = parse_username(profile_url)

    say("iniciando", f"Preparando a leitura de @{username}...", 2)
    sessao = await collect(settings, profile_url, start, end, progress=say)

    relatorio = analisar_captura(sessao.capture, settings, progress=say)
    relatorio["conduta_da_sessao"] = {
        "somente_leitura": True,
        "interacoes_bloqueadas": sessao.guard_report,
        "ritmo": settings.pace,
    }

    say("concluido", "Analise concluida.", 100)
    return relatorio


def salvar_relatorio(relatorio: dict, settings: Optional[Settings] = None) -> Path:
    settings = settings or Settings()
    settings.ensure_dirs()
    perfil = relatorio.get("perfil", {}).get("username", "perfil")
    marca = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    destino = settings.runs_dir / f"{perfil}-{marca}.json"
    destino.write_text(json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8")
    return destino


def carregar_captura(caminho: str | Path) -> Capture:
    dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    return Capture.from_dict(dados)


def rodar(profile_url: str, inicio: str, fim: str, settings: Optional[Settings] = None, progress=None) -> dict:
    """Versao sincrona, para CLI."""
    return asyncio.run(executar_analise(profile_url, inicio, fim, settings, progress))
