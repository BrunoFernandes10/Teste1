"""API HTTP e entrega do painel."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import ROOT, Settings
from .pipeline import executar_analise, parse_periodo, salvar_relatorio
from .collector.instagram import LoginRequired, parse_username

WEB_DIR = ROOT / "web"


class PedidoAnalise(BaseModel):
    url: str = Field(..., description="URL do perfil no Instagram")
    inicio: str = Field(..., description="Data inicial AAAA-MM-DD")
    fim: str = Field(..., description="Data final AAAA-MM-DD")
    ritmo: Optional[str] = Field(None, description="calmo | normal | apressado")
    max_publicacoes: Optional[int] = None
    mostrar_navegador: Optional[bool] = None


@dataclass
class Job:
    id: str
    perfil: str
    inicio: str
    fim: str
    estado: str = "na fila"
    etapa: str = "iniciando"
    mensagem: str = "Aguardando inicio..."
    percentual: int = 0
    erro: Optional[str] = None
    relatorio: Optional[dict] = None
    arquivo: Optional[str] = None
    criado_em: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    historico: list[dict] = field(default_factory=list)

    def registrar(self, etapa: str, mensagem: str, percentual: int) -> None:
        self.etapa = etapa
        self.mensagem = mensagem
        self.percentual = max(self.percentual, min(100, percentual))
        marca = datetime.now(timezone.utc).strftime("%H:%M:%S")
        if not self.historico or self.historico[-1]["mensagem"] != mensagem:
            self.historico.append({"hora": marca, "etapa": etapa, "mensagem": mensagem})
        del self.historico[:-40]

    def resumo(self) -> dict:
        return {
            "id": self.id,
            "perfil": self.perfil,
            "periodo": {"inicio": self.inicio, "fim": self.fim},
            "estado": self.estado,
            "etapa": self.etapa,
            "mensagem": self.mensagem,
            "percentual": self.percentual,
            "erro": self.erro,
            "criado_em": self.criado_em,
            "historico": self.historico[-12:],
            "tem_relatorio": self.relatorio is not None,
        }


JOBS: dict[str, Job] = {}

app = FastAPI(title="Analise de Sentimento — Instagram", version="1.0.0")


@app.get("/api/configuracao")
def configuracao() -> dict:
    settings = Settings()
    return {
        "conta_configurada": bool(settings.ig_username and settings.ig_password),
        "conta": settings.ig_username or None,
        "analista": settings.analyst_model if settings.analyst_enabled else "motor lexical offline",
        "analista_ia": settings.analyst_enabled,
        "ritmo": settings.pace,
        "navegador_visivel": not settings.headless,
        "max_publicacoes": settings.max_posts,
    }


@app.post("/api/analises")
async def criar_analise(pedido: PedidoAnalise) -> JSONResponse:
    try:
        perfil = parse_username(pedido.url)
        parse_periodo(pedido.inicio, pedido.fim)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job = Job(id=uuid.uuid4().hex[:12], perfil=perfil, inicio=pedido.inicio, fim=pedido.fim)
    JOBS[job.id] = job
    asyncio.create_task(_executar(job, pedido))
    return JSONResponse({"id": job.id, "estado": job.estado}, status_code=202)


async def _executar(job: Job, pedido: PedidoAnalise) -> None:
    settings = Settings()
    if pedido.ritmo:
        settings.pace = pedido.ritmo
    if pedido.max_publicacoes:
        settings.max_posts = int(pedido.max_publicacoes)
    if pedido.mostrar_navegador is not None:
        settings.headless = not pedido.mostrar_navegador

    job.estado = "em andamento"
    job.registrar("iniciando", "Abrindo o navegador...", 1)

    def progresso(etapa: str, mensagem: str, percentual: int) -> None:
        job.registrar(etapa, mensagem, percentual)

    try:
        relatorio = await executar_analise(
            pedido.url, pedido.inicio, pedido.fim, settings=settings, progress=progresso
        )
        job.relatorio = relatorio
        job.arquivo = str(salvar_relatorio(relatorio, settings))
        job.estado = "concluido"
        job.registrar("concluido", "Analise concluida.", 100)
    except LoginRequired as exc:
        job.estado = "erro"
        job.erro = str(exc)
        job.registrar("erro", str(exc), job.percentual)
    except Exception as exc:  # noqa: BLE001 - a UI precisa ver qualquer falha
        job.estado = "erro"
        job.erro = f"{type(exc).__name__}: {exc}"
        job.registrar("erro", job.erro, job.percentual)


@app.get("/api/analises/{job_id}")
def status(job_id: str) -> dict:
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Analise nao encontrada.")
    return job.resumo()


@app.get("/api/analises/{job_id}/relatorio")
def relatorio(job_id: str) -> Any:
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Analise nao encontrada.")
    if not job.relatorio:
        raise HTTPException(status_code=409, detail=f"Relatorio ainda nao disponivel (estado: {job.estado}).")
    return job.relatorio


@app.get("/api/analises")
def listar() -> dict:
    return {"analises": [j.resumo() for j in sorted(JOBS.values(), key=lambda j: j.criado_em, reverse=True)]}


@app.get("/")
def home() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")
