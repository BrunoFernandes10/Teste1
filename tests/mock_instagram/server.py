"""Instagram simulado para validar o coletor de verdade.

Reproduz o fluxo real: banner de cookies, formulario de login, dialogo de
"salvar informacoes", grade paginada por rolagem, modal de publicacao aberto
por clique e fechado com Escape, e as MESMAS formas de JSON que o Instagram
entrega (api/v1 e GraphQL). Assim o Playwright, o motor humano, a trava de
somente-leitura e a colheita passiva sao exercitados de ponta a ponta.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi import FastAPI, Form, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data import gerar  # noqa: E402

DADOS = gerar()
PERFIL = DADOS["profile"]
POSTS = DADOS["posts"]
POR_CODIGO = {p["shortcode"]: p for p in POSTS}
PAGINA = 4  # publicacoes entregues por rolagem

USUARIO_OK = "flashtransfer.orlando"
SENHA_OK = "senha-de-teste"

app = FastAPI()
TENTATIVAS: list[dict] = []   # registra o que o sistema tentou fazer


def _autenticado(request: Request) -> bool:
    return request.cookies.get("sessionid") == "mock-session"


def _ts(iso: str) -> int:
    from datetime import datetime

    return int(datetime.fromisoformat(iso).timestamp())


def _media_json(post: dict) -> dict:
    """Forma api/v1 do Instagram."""
    tipos = {"imagem": 1, "video": 2, "carrossel": 8, "reel": 2}
    return {
        "pk": post["id"],
        "code": post["shortcode"],
        "taken_at": _ts(post["created_at"]),
        "like_count": post["like_count"],
        "comment_count": post["comment_count"],
        "media_type": tipos.get(post["media_type"], 1),
        "product_type": "clips" if post["media_type"] == "reel" else "feed",
        "caption": {"text": post["caption"]},
        "user": {"username": PERFIL["username"]},
    }


def _comment_json(c: dict) -> dict:
    return {
        "pk": c["id"],
        "text": c["text"],
        "created_at": _ts(c["created_at"]),
        "comment_like_count": c["like_count"],
        "user": {"username": c["author"]},
        **({"parent_comment_id": c["parent_id"]} if c["parent_id"] else {}),
    }


CSS = """<style>
body{font-family:system-ui;background:#000;color:#fff;margin:0}
nav{display:flex;gap:18px;padding:14px 24px;border-bottom:1px solid #262626}
nav a{color:#fff;text-decoration:none}
.grade{display:grid;grid-template-columns:repeat(3,1fr);gap:4px;max-width:940px;margin:24px auto;padding:0 16px}
.grade a{display:block;aspect-ratio:1;background:#1a1a1a;color:#8e8e8e;padding:14px;
  text-decoration:none;font-size:12px;overflow:hidden}
header.perfil{max-width:940px;margin:30px auto;padding:0 16px;display:flex;gap:30px}
.modal{position:fixed;inset:0;background:rgba(0,0,0,.92);display:none;overflow-y:auto;padding:40px}
.modal.aberto{display:block}
.modal .caixa{max-width:760px;margin:0 auto;background:#000;border:1px solid #262626;padding:24px}
.coment{padding:10px 0;border-bottom:1px solid #1a1a1a;font-size:14px}
.coment b{color:#fff}
button{background:#0095f6;color:#fff;border:0;padding:9px 18px;border-radius:8px;cursor:pointer;font-size:14px}
input{padding:10px;background:#121212;border:1px solid #363636;color:#fff;border-radius:6px;width:260px}
.banner{position:fixed;bottom:0;left:0;right:0;background:#262626;padding:20px;text-align:center}
</style>"""


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    if not _autenticado(request):
        return RedirectResponse("/accounts/login/")
    return HTMLResponse(f"""<!doctype html><html lang="pt"><head><meta charset="utf-8">
    <title>Instagram</title>{CSS}</head><body>
    <nav><a href="/">Início</a><a href="/explore/">Explorar</a><a href="/direct/inbox/">Mensagens</a></nav>
    <p style="padding:24px">Feed</p></body></html>""")


@app.get("/accounts/login/", response_class=HTMLResponse)
def login_page():
    return HTMLResponse(f"""<!doctype html><html lang="pt"><head><meta charset="utf-8">
    <title>Entrar • Instagram</title>{CSS}</head><body>
    <div id="banner" class="banner">
      Usamos cookies. <button onclick="document.getElementById('banner').remove()">Permitir todos os cookies</button>
    </div>
    <div style="max-width:340px;margin:80px auto;text-align:center">
      <h1 style="font-size:28px">Instagram</h1>
      <form id="f" style="display:grid;gap:10px;justify-items:center">
        <input name="username" placeholder="Telefone, nome de usuário ou email" autocomplete="off">
        <input name="password" type="password" placeholder="Senha" autocomplete="off">
        <button type="submit">Entrar</button>
      </form>
      <p id="erro" style="color:#ed4956;font-size:14px"></p>
    </div>
    <div id="salvar" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.8)">
      <div style="max-width:380px;margin:22vh auto;background:#262626;padding:30px;text-align:center;border-radius:12px">
        <h2 style="font-size:20px">Salvar suas informações de login?</h2>
        <button style="margin-top:16px" onclick="location.href='/'">Salvar informações</button>
        <button style="background:none;color:#0095f6;margin-top:10px"
                onclick="location.href='/'">Agora não</button>
      </div>
    </div>
    <script>
    document.getElementById('f').addEventListener('submit', async (e) => {{
      e.preventDefault();
      const dados = new FormData(e.target);
      const r = await fetch('/accounts/login/ajax/', {{ method:'POST', body: dados }});
      const j = await r.json();
      if (j.authenticated) {{ document.getElementById('salvar').style.display='block'; }}
      else {{ document.getElementById('erro').textContent = 'Sua senha estava incorreta.'; }}
    }});
    </script></body></html>""")


@app.post("/accounts/login/ajax/")
def login_ajax(username: str = Form(""), password: str = Form("")):
    TENTATIVAS.append({"rota": "login", "usuario": username})
    if username == USUARIO_OK and password == SENHA_OK:
        resposta = JSONResponse({"authenticated": True, "user": True, "status": "ok"})
        resposta.set_cookie("sessionid", "mock-session", httponly=True)
        return resposta
    return JSONResponse({"authenticated": False, "status": "fail"})


# --- rotas de escrita: existem so para provar que sao bloqueadas ------------
@app.post("/web/likes/{media_id}/like/")
def curtir(media_id: str):
    TENTATIVAS.append({"rota": "curtir", "media": media_id})
    return JSONResponse({"status": "ok"})


@app.post("/api/v1/media/{media_id}/comment/")
def comentar(media_id: str):
    TENTATIVAS.append({"rota": "comentar", "media": media_id})
    return JSONResponse({"status": "ok"})


@app.post("/web/friendships/{user_id}/follow/")
def seguir(user_id: str):
    TENTATIVAS.append({"rota": "seguir", "usuario": user_id})
    return JSONResponse({"status": "ok"})


# --- APIs de leitura --------------------------------------------------------
@app.get("/api/v1/users/web_profile_info/")
def web_profile_info(username: str = ""):
    return JSONResponse({"data": {"user": {
        "username": PERFIL["username"],
        "full_name": PERFIL["full_name"],
        "biography": PERFIL["biography"],
        "edge_followed_by": {"count": PERFIL["followers"]},
        "edge_follow": {"count": PERFIL["following"]},
        "edge_owner_to_timeline_media": {"count": PERFIL["posts_total"],
                                         "edges": [{"node": _media_json(p)} for p in POSTS[:PAGINA]]},
        "is_private": PERFIL["is_private"],
    }}})


@app.get("/api/v1/feed/user/{user_id}/")
def feed(user_id: str, pagina: int = 1):
    inicio = pagina * PAGINA
    return JSONResponse({"items": [_media_json(p) for p in POSTS[inicio: inicio + PAGINA]],
                         "more_available": inicio + PAGINA < len(POSTS)})


@app.get("/api/v1/media/{media_id}/comments/")
def comments(media_id: str):
    post = next((p for p in POSTS if p["id"] == media_id), None)
    if not post:
        return JSONResponse({"comments": []})
    return JSONResponse({
        "comments": [_comment_json(c) for c in post["comments"]],
        "comment_count": post["comment_count"],
        "caption": {"text": post["caption"]},
    })


# --- paginas ----------------------------------------------------------------
@app.get("/{username}/", response_class=HTMLResponse)
def perfil(username: str, request: Request):
    if not _autenticado(request):
        return RedirectResponse("/accounts/login/")
    celulas = "".join(
        f'<a href="/p/{p["shortcode"]}/" data-id="{p["id"]}" '
        f'onclick="abrir(event,\'{p["shortcode"]}\',\'{p["id"]}\')">{p["caption"][:70]}</a>'
        for p in POSTS
    )
    return HTMLResponse(f"""<!doctype html><html lang="pt"><head><meta charset="utf-8">
    <title>{PERFIL['full_name']} (@{username}) • Instagram</title>{CSS}</head><body>
    <nav><a href="/">Início</a><a href="/explore/">Explorar</a><a href="/direct/inbox/">Mensagens</a></nav>
    <header class="perfil">
      <div><h2>{username}</h2>
      <p>{PERFIL['posts_total']} publicações · {PERFIL['followers']} seguidores · {PERFIL['following']} seguindo</p>
      <p><b>{PERFIL['full_name']}</b><br>{PERFIL['biography']}</p></div>
    </header>
    <div class="grade">{celulas}</div>
    <div style="height:700px"></div>
    <div id="modal" class="modal"><div class="caixa">
      <h3 id="m-legenda"></h3><div id="m-coments"></div>
      <button id="mais" style="margin-top:14px">Carregar mais comentários</button>
    </div></div>
    <script>
    // Carrega o perfil e depois pagina conforme a pessoa rola — igual ao real.
    fetch('/api/v1/users/web_profile_info/?username={username}');
    let pagina = 1, carregando = false;
    window.addEventListener('scroll', async () => {{
      if (carregando || pagina > 3) return;
      if (window.scrollY + window.innerHeight < document.body.scrollHeight - 400) return;
      carregando = true;
      await fetch('/api/v1/feed/user/1/?pagina=' + pagina);
      pagina++; carregando = false;
    }});

    let mostrados = 0, todos = [];
    async function abrir(ev, codigo, id) {{
      ev.preventDefault();
      const r = await fetch('/api/v1/media/' + id + '/comments/');
      const j = await r.json();
      todos = j.comments; mostrados = 0;
      document.getElementById('m-legenda').textContent = j.caption.text;
      document.getElementById('m-coments').innerHTML = '';
      render();
      document.getElementById('modal').classList.add('aberto');
      history.pushState({{}}, '', '/p/' + codigo + '/');
    }}
    function render() {{
      const lote = todos.slice(mostrados, mostrados + 8);
      mostrados += lote.length;
      document.getElementById('m-coments').insertAdjacentHTML('beforeend',
        lote.map(c => `<div class="coment"><b>${{c.user.username}}</b> ${{c.text}}
          <div style="color:#8e8e8e;font-size:12px">${{c.comment_like_count}} curtidas</div></div>`).join(''));
      document.getElementById('mais').style.display = mostrados < todos.length ? 'inline-block' : 'none';
    }}
    document.getElementById('mais').addEventListener('click', render);
    document.addEventListener('keydown', (e) => {{
      if (e.key === 'Escape') {{ document.getElementById('modal').classList.remove('aberto');
        history.pushState({{}}, '', '/{username}/'); }}
    }});
    </script></body></html>""")


@app.get("/p/{shortcode}/", response_class=HTMLResponse)
def publicacao(shortcode: str, request: Request):
    if not _autenticado(request):
        return RedirectResponse("/accounts/login/")
    post = POR_CODIGO.get(shortcode)
    if not post:
        return HTMLResponse("<h1>404</h1>", status_code=404)
    return HTMLResponse(f"""<!doctype html><html lang="pt"><head><meta charset="utf-8">
    <title>Publicação</title>{CSS}</head><body>
    <nav><a href="/">Início</a><a href="/explore/">Explorar</a></nav>
    <div class="caixa" style="max-width:760px;margin:30px auto">
      <h3>{post['caption']}</h3><div id="c"></div>
    </div>
    <script>
    fetch('/api/v1/media/{post["id"]}/comments/').then(r => r.json()).then(j => {{
      document.getElementById('c').innerHTML = j.comments.map(c =>
        `<div class="coment"><b>${{c.user.username}}</b> ${{c.text}}</div>`).join('');
    }});
    </script></body></html>""")


@app.get("/_tentativas")
def tentativas():
    return {"tentativas": TENTATIVAS}
