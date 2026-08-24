"""Validacao ponta a ponta com navegador real.

Sobe o Instagram simulado, roda o coletor Playwright de verdade contra ele e
confere: o login aconteceu, as publicacoes do periodo foram lidas, os
comentarios ficaram amarrados as publicacoes certas e a trava de somente-leitura
barra escrita mesmo quando alguem tenta forcar.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

PORTA = 8799
BASE = f"http://127.0.0.1:{PORTA}"

os.environ.setdefault("CHROME_PATH", "/opt/pw-browsers/chromium")
os.environ.update(
    IG_BASE_URL=BASE,
    IG_USERNAME="flashtransfer.orlando",
    IG_PASSWORD="senha-de-teste",
    HEADLESS="true",
    HUMAN_PACE="apressado",
    MAX_POSTS="12",
    SESSION_DIR=str(RAIZ / "runs" / "sessao-teste"),
)

from sentiment.config import Settings          # noqa: E402
from sentiment.collector.instagram import collect  # noqa: E402
from sentiment.pipeline import analisar_captura    # noqa: E402


def _subir_mock():
    import threading
    import uvicorn

    sys.path.insert(0, str(RAIZ / "tests" / "mock_instagram"))
    import server  # noqa: E402

    config = uvicorn.Config(server.app, host="127.0.0.1", port=PORTA, log_level="error")
    servidor = uvicorn.Server(config)
    thread = threading.Thread(target=servidor.run, daemon=True)
    thread.start()
    for _ in range(60):
        if servidor.started:
            return servidor, server
        time.sleep(0.25)
    raise RuntimeError("mock nao subiu")


def _ok(condicao: bool, texto: str) -> bool:
    print(f"  [{'OK ' if condicao else 'FALHA'}] {texto}")
    return condicao


async def principal() -> int:
    servidor, mock = _subir_mock()
    print(f"\nInstagram simulado no ar em {BASE}\n")

    settings = Settings()
    # Sessao limpa: queremos exercitar o login de verdade.
    for antigo in Path(settings.session_dir).glob("*.json"):
        antigo.unlink()

    fim = datetime.now(timezone.utc)
    inicio = fim - timedelta(days=90)

    # Quanto o fixture coloca dentro desta janela — nao um numero cravado, que
    # envelheceria junto com o calendario.
    esperado_posts = sum(
        1 for p in mock.POSTS
        if inicio <= datetime.fromisoformat(p["created_at"]) <= fim
    )
    esperado_comentarios = sum(
        len(p["comments"]) for p in mock.POSTS
        if inicio <= datetime.fromisoformat(p["created_at"]) <= fim
    )
    respostas_da_marca = sum(
        1 for p in mock.POSTS for c in p["comments"]
        if c["author"] == mock.PERFIL["username"]
        and inicio <= datetime.fromisoformat(p["created_at"]) <= fim
    )

    etapas: list[str] = []
    resultado = await collect(
        settings, f"{BASE}/flashtransfer.orlando/", inicio, fim,
        progress=lambda etapa, msg, pct: etapas.append(f"{pct:3d}% {msg}"),
    )
    captura = resultado.capture

    print("Progresso relatado pelo sistema:")
    for linha in etapas:
        print("   ", linha)

    total_comentarios = len(captura.all_comments)
    orfaos = [c for c in captura.all_comments if not c.post_id]
    tentativas = {t["rota"] for t in mock.TENTATIVAS}

    print("\nVerificacoes da coleta:")
    checagens = [
        _ok("login" in tentativas, "o sistema fez login de verdade no formulario"),
        _ok(captura.profile.username == "flashtransfer.orlando", "perfil identificado"),
        _ok(captura.profile.followers == 18420, f"dados do perfil lidos (seguidores={captura.profile.followers})"),
        _ok(len(captura.posts) == esperado_posts,
            f"todas as {esperado_posts} publicacoes do periodo foram lidas (obtidas: {len(captura.posts)})"),
        _ok(total_comentarios == esperado_comentarios,
            f"todos os {esperado_comentarios} comentarios foram lidos (obtidos: {total_comentarios})"),
        _ok(not orfaos, f"todo comentario ligado a sua publicacao (orfaos: {len(orfaos)})"),
        _ok(all(p.created_at for p in captura.posts), "todas as publicacoes tem data"),
        _ok(all(p.url.startswith("https://www.instagram.com/") for p in captura.posts),
            "URLs das publicacoes normalizadas para o dominio real"),
        _ok(tentativas == {"login"}, f"nenhuma interacao alem do login (rotas tocadas: {sorted(tentativas)})"),
    ]

    # Prova ativa da trava: forcamos uma curtida e ela precisa ser barrada.
    print("\nProva da trava de somente-leitura (tentativa forcada de curtir):")
    from playwright.async_api import async_playwright
    from sentiment.collector.guard import ReadOnlyGuard

    guard = ReadOnlyGuard()
    async with async_playwright() as pw:
        navegador = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
            **({"executable_path": os.environ["CHROME_PATH"]} if os.environ.get("CHROME_PATH") else {}),
        )
        contexto = await navegador.new_context()
        await guard.install(contexto)
        pagina = await contexto.new_page()
        await pagina.goto(f"{BASE}/accounts/login/")
        respostas = await pagina.evaluate(
            """async (base) => {
                const saidas = [];
                for (const rota of ['/web/likes/3000/like/', '/api/v1/media/3000/comment/',
                                    '/web/friendships/77/follow/']) {
                    try { const r = await fetch(base + rota, {method:'POST'}); saidas.push(r.status); }
                    catch (e) { saidas.push('bloqueado'); }
                }
                return saidas;
            }""",
            BASE,
        )
        await navegador.close()

    tentativas_depois = {t["rota"] for t in mock.TENTATIVAS}
    checagens += [
        _ok(all(r == "bloqueado" for r in respostas), f"curtir/comentar/seguir barrados no navegador: {respostas}"),
        _ok(len(guard.blocked) == 3, f"trava registrou as 3 tentativas ({len(guard.blocked)})"),
        _ok(tentativas_depois == {"login"}, "nenhuma escrita chegou ao servidor"),
    ]

    # A analise roda sobre o material realmente coletado.
    print("\nAnalise sobre o material coletado:")
    relatorio = analisar_captura(captura, settings)
    p = relatorio["pontuacao"]
    c = relatorio["comentarios"]
    soma = c["percentual_positivos"] + c["percentual_neutros"] + c["percentual_negativos"]
    checagens += [
        _ok(0 <= p["nota"] <= 100, f"nota dentro de 0-100: {p['nota']}"),
        _ok(abs(soma - 100) < 0.5, f"percentuais de comentarios somam 100 ({soma})"),
        # As respostas da propria marca saem do balanco de sentimento de
        # proposito: nao sao opiniao do publico.
        _ok(c["total"] == total_comentarios - respostas_da_marca,
            f"todo comentario do publico classificado ({c['total']} = "
            f"{total_comentarios} - {respostas_da_marca} respostas da marca)"),
        _ok(relatorio["atendimento_da_marca"]["respostas_da_marca"] == respostas_da_marca,
            f"respostas da marca contabilizadas a parte ({respostas_da_marca})"),
        _ok(len(relatorio["ranking_temas"]) > 0, "ranking de temas gerado"),
        _ok(len(relatorio["riscos"]) > 0, f"riscos detectados: {len(relatorio['riscos'])}"),
    ]

    servidor.should_exit = True
    falhas = checagens.count(False)
    print(f"\n{'='*60}\n{len(checagens) - falhas}/{len(checagens)} verificacoes passaram\n{'='*60}\n")

    import json
    destino = RAIZ / "runs" / "captura-e2e.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(captura.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Captura salva em {destino}")
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(principal()))
