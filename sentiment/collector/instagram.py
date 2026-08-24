"""Sessao de leitura do Instagram conduzida como uma pessoa fisica.

Regras de conduta gravadas neste modulo:
  * abre o Chrome, entra na conta e navega — sem atalhos de API;
  * le com calma, com pausa entre publicacoes e tempo de leitura proporcional;
  * NAO curte, NAO comenta, NAO segue, NAO salva, NAO manda mensagem;
  * NAO copia midia: apenas texto publico ja exibido na tela.
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse

from playwright.async_api import async_playwright

from ..config import Settings
from ..models import Capture, Post, Profile
from .guard import ReadOnlyGuard
from .harvest import Harvester
from .humanize import build_human

Progress = Callable[[str, str, int], None]


class LoginRequired(RuntimeError):
    """A conta exigiu verificacao manual (2FA, desafio de seguranca)."""


class CollectionError(RuntimeError):
    """Falha irrecuperavel durante a coleta."""


# Textos dos botoes em pt/en/es — o Instagram varia conforme o idioma da conta.
COOKIE_BUTTONS = [
    "Permitir todos os cookies", "Allow all cookies", "Permitir todas las cookies",
    "Aceitar tudo", "Aceitar todos", "Accept all", "Allow essential and optional cookies",
    "Permitir cookies essenciais e opcionais", "Recusar cookies opcionais",
    "Decline optional cookies", "Only allow essential cookies",
]

# O campo de usuario ja apareceu com varios nomes e rotulos. Tentamos todos
# antes de concluir que a pagina de login nao carregou.
CAMPOS_USUARIO = [
    "input[name='username']",
    "input[name='email']",
    "input[aria-label*='usuário' i]",
    "input[aria-label*='usuario' i]",
    "input[aria-label*='username' i]",
    "form input[type='text']",
]
CAMPOS_SENHA = [
    "input[name='password']",
    "input[type='password']",
    "input[aria-label*='senha' i]",
]
DISMISS_BUTTONS = ["Agora não", "Not now", "Ahora no", "Not Now", "Cancelar", "Fechar"]
MORE_COMMENTS = [
    "Carregar mais comentários", "Load more comments", "Cargar más comentarios",
    "Ver mais comentários", "View more comments",
]
MORE_REPLIES = ["Ver respostas", "View replies", "Ver todas as respostas", "Ver respuestas"]


_MEDIA_ID_RE = re.compile(r"/media/([0-9_]+)/(?:comments|info)")


def _media_id_from_url(url: str) -> str:
    """Extrai o id da publicacao de rotas do tipo /api/v1/media/<id>/comments/."""
    achado = _MEDIA_ID_RE.search(url or "")
    return achado.group(1) if achado else ""


# Primeiro segmento de caminho que nunca e um nome de usuario.
CAMINHOS_RESERVADOS = {
    "p", "reel", "reels", "tv", "stories", "explore", "accounts", "direct",
    "challenge", "s", "web", "api", "graphql",
}


def parse_username(profile_url: str) -> str:
    """Extrai o @usuario de uma URL, @handle ou nome solto.

    Aceita qualquer host (instagram.com, m.instagram.com ou um servidor local
    de teste) e ignora caminhos extras como /reels/ ou /tagged/.
    """
    texto = (profile_url or "").strip()
    if not texto:
        raise ValueError("URL do perfil vazia.")

    if "://" in texto or texto.lower().startswith("www.") or "instagram.com" in texto.lower():
        if "://" not in texto:
            texto = "https://" + texto
        caminho = urlparse(texto).path
    else:
        caminho = texto.split("?")[0].split("#")[0]

    partes = [parte for parte in caminho.split("/") if parte]
    usuario = (partes[0] if partes else "").lstrip("@").strip()

    if not usuario or usuario.lower() in CAMINHOS_RESERVADOS or not re.fullmatch(r"[A-Za-z0-9._]{1,30}", usuario):
        raise ValueError(
            f"Nao consegui identificar o usuario em: {profile_url!r}. "
            "Use algo como https://www.instagram.com/nomedoperfil/"
        )
    return usuario


@dataclass
class SessionResult:
    capture: Capture
    guard_report: dict


class InstagramReader:
    """Conduz a sessao de navegacao e devolve o material lido."""

    def __init__(self, settings: Settings, progress: Optional[Progress] = None) -> None:
        self.settings = settings
        self.human = build_human(settings.pace_factor)
        self.harvester = Harvester()
        self.guard = ReadOnlyGuard()
        self._progress = progress or (lambda stage, msg, pct: None)
        self._current_post_id = ""
        self.notes: list[str] = []

    def say(self, stage: str, message: str, percent: int) -> None:
        self._progress(stage, message, percent)

    # ------------------------------------------------------------------
    # Ciclo de vida do navegador
    # ------------------------------------------------------------------
    async def run(self, profile_url: str, start: datetime, end: datetime) -> SessionResult:
        username = parse_username(profile_url)
        self.settings.ensure_dirs()
        state_file = self.settings.session_dir / f"{self.settings.ig_username or 'anon'}.json"

        async with async_playwright() as pw:
            browser = None
            if self.settings.chrome_profile:
                context = await self._abrir_perfil_real(pw)
            else:
                browser = await self._launch(pw)
                context = await self._new_context(browser, state_file)

            await self.guard.install(context)
            await self._injetar_sessao(context)
            page = context.pages[0] if context.pages else await context.new_page()
            page.on("response", self._on_response)

            try:
                await self._open_instagram(page)
                await self._ensure_login(page, context, state_file)
                posts = await self._read_profile(page, username, start, end)
                profile = self._build_profile(username)
            finally:
                try:
                    await context.storage_state(path=str(state_file))
                except Exception:
                    pass
                try:
                    await context.close()
                except Exception:
                    pass
                if browser is not None:
                    await browser.close()

        capture = Capture(
            profile=profile,
            posts=posts,
            window_start=start,
            window_end=end,
            notes=self.notes,
        )
        return SessionResult(capture=capture, guard_report=self.guard.report())

    async def _abrir_perfil_real(self, pw):
        """Abre o Chrome no perfil de verdade da pessoa.

        E o caminho mais limpo: se ela ja esta logada no Instagram no navegador
        do dia a dia, nao ha login a fazer e nao ha formulario para o Instagram
        recusar. O preco e que o Chrome precisa estar fechado, porque o perfil
        fica travado por quem o abriu primeiro.
        """
        origem = Path(self.settings.chrome_profile).expanduser()
        if not origem.exists():
            raise CollectionError(
                f"Perfil do Chrome nao encontrado em: {origem}\n"
                "Confira o valor de CHROME_PROFILE no arquivo .env."
            )

        # Trabalhamos sobre uma COPIA do perfil, nunca sobre o original.
        # O Chrome tranca a pasta de quem a abriu primeiro: usar o original
        # exigiria fechar o Chrome — impossivel, ja que o painel do sistema
        # roda dentro dele. A copia tambem garante que nada do navegador do
        # dia a dia seja alterado por esta sessao.
        caminho = self._copiar_perfil(origem)

        args = ["--disable-blink-features=AutomationControlled", "--no-first-run"]
        if self.settings.chrome_profile_name:
            args.append(f"--profile-directory={self.settings.chrome_profile_name}")
        try:
            contexto = await pw.chromium.launch_persistent_context(
                user_data_dir=str(caminho),
                headless=False,  # perfil real so faz sentido com janela visivel
                channel="chrome",
                args=args,
                viewport={"width": 1440, "height": 900},
                locale="pt-BR",
            )
        except Exception as exc:
            raise CollectionError(
                "Nao consegui abrir a copia do seu perfil do Chrome.\n"
                f"Detalhe: {str(exc).splitlines()[0]}"
            ) from exc
        self.notes.append("Sessao aproveitada de uma copia do perfil do Chrome.")
        await contexto.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        )
        return contexto

    def _copiar_perfil(self, origem: Path) -> Path:
        """Copia o minimo do perfil do Chrome para uma pasta propria.

        Interessa apenas o que carrega a sessao: a chave de criptografia em
        "Local State" e os cookies do perfil. Copiar a pasta inteira levaria
        gigabytes de cache e historico sem necessidade.
        """
        destino = self.settings.session_dir / "chrome-copia"
        perfil = self.settings.chrome_profile_name or "Default"
        destino_perfil = destino / perfil
        destino_perfil.mkdir(parents=True, exist_ok=True)

        # A chave que decifra os cookies fica na raiz e e presa ao usuario do
        # Windows — por isso a copia so funciona na mesma conta, que e o caso.
        for nome in ("Local State",):
            fonte = origem / nome
            if fonte.exists():
                shutil.copy2(fonte, destino / nome)

        alvos = [
            Path("Network") / "Cookies",
            Path("Cookies"),          # Chrome antigo guardava fora de Network
            Path("Preferences"),
            Path("Local Storage") / "leveldb",
        ]
        copiados = 0
        for alvo in alvos:
            fonte = origem / perfil / alvo
            if not fonte.exists():
                continue
            destino_item = destino_perfil / alvo
            destino_item.parent.mkdir(parents=True, exist_ok=True)
            try:
                if fonte.is_dir():
                    shutil.copytree(fonte, destino_item, dirs_exist_ok=True)
                else:
                    shutil.copy2(fonte, destino_item)
                copiados += 1
            except Exception:
                continue  # arquivo em uso pelo Chrome: seguimos com o resto

        if not copiados:
            raise CollectionError(
                f"Nao encontrei os dados de sessao em: {origem / perfil}\n"
                "Confira CHROME_PROFILE e CHROME_PROFILE_NAME no arquivo .env."
            )
        self.notes.append(f"Copia do perfil preparada ({copiados} item(ns)).")
        return destino

    async def _injetar_sessao(self, context) -> None:
        """Instala o cookie de sessao copiado de um navegador ja autenticado."""
        if not self.settings.ig_sessionid:
            return
        try:
            await context.add_cookies([
                {
                    "name": "sessionid",
                    "value": self.settings.ig_sessionid,
                    "domain": ".instagram.com",
                    "path": "/",
                    "httpOnly": True,
                    "secure": True,
                    "sameSite": "Lax",
                }
            ])
            self.notes.append("Sessao instalada a partir do cookie informado.")
        except Exception as exc:
            self.notes.append(f"Nao consegui instalar o cookie de sessao: {exc}")

    async def _launch(self, pw):
        args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-features=IsolateOrigins,site-per-process",
            "--no-first-run",
            "--no-default-browser-check",
        ]
        # --no-sandbox só é necessário em Linux rodando como root (contêineres).
        # os.geteuid não existe no Windows, por isso a checagem é defensiva.
        if os.name == "posix" and getattr(os, "geteuid", lambda: -1)() == 0:
            args += ["--no-sandbox", "--disable-dev-shm-usage"]

        # Ordem de preferencia: executavel indicado pelo usuario, Chrome
        # instalado na maquina e, por fim, o Chromium do proprio Playwright.
        tentativas: list[dict] = []
        if self.settings.chrome_path:
            tentativas.append({"executable_path": self.settings.chrome_path})
        tentativas += [{"channel": "chrome"}, {}]

        erros = []
        for opcoes in tentativas:
            try:
                return await pw.chromium.launch(headless=self.settings.headless, args=args, **opcoes)
            except Exception as exc:
                erros.append(f"{opcoes or 'chromium padrao'}: {str(exc).splitlines()[0]}")
        raise CollectionError(
            "Nao foi possivel abrir o Chrome/Chromium. Rode 'python -m playwright install chromium' "
            "ou defina CHROME_PATH com o caminho do executavel.\nDetalhes: " + " | ".join(erros)
        )

    async def _new_context(self, browser, state_file: Path):
        options = dict(
            viewport={"width": 1440, "height": 900},
            locale="pt-BR",
            timezone_id="America/New_York",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
            ),
        )
        if state_file.exists():
            options["storage_state"] = str(state_file)
            self.notes.append("Sessao anterior reaproveitada (evita login repetido).")
        context = await browser.new_context(**options)
        # Remove o sinal mais obvio de automacao.
        await context.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        )
        return context

    def _on_response(self, response) -> None:
        """Le passivamente os JSON que a pagina ja baixou."""
        try:
            ctype = (response.headers or {}).get("content-type", "")
            if "json" not in ctype.lower():
                return
            url = response.url
        except Exception:
            return
        # A publicacao dona dos comentarios sai da propria URL sempre que
        # possivel; so caimos no estado da sessao quando a rota nao revela.
        dono = _media_id_from_url(url) or self._current_post_id
        asyncio.ensure_future(self._consume(response, dono))

    async def _consume(self, response, post_id: str) -> None:
        try:
            body = await response.text()
        except Exception:
            return
        if len(body) > 6_000_000:  # payload absurdo: ignora
            return
        try:
            self.harvester.ingest_text(body, post_id)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------
    async def _open_instagram(self, page) -> None:
        self.say("navegando", "Abrindo o Instagram no Chrome...", 5)
        await page.goto(f"{self.settings.base_url}/", wait_until="domcontentloaded", timeout=60000)
        await self.human.pause("media")
        await self._click_any(page, COOKIE_BUTTONS)

    async def _click_any(self, page, labels: list[str]) -> bool:
        """Clica no primeiro botao visivel cujo texto bata com a lista."""
        for label in labels:
            for locator in (
                page.get_by_role("button", name=label, exact=False),
                page.locator(f"button:has-text('{label}')"),
                page.locator(f"div[role='button']:has-text('{label}')"),
            ):
                try:
                    element = locator.first
                    if await element.is_visible(timeout=1200):
                        await self.human.click(element, page)
                        return True
                except Exception:
                    continue
        return False

    async def _is_logged_in(self, page) -> bool:
        try:
            if await page.locator("input[name='username']").first.is_visible(timeout=1500):
                return False
        except Exception:
            pass
        if "/accounts/login" in page.url:
            return False
        for selector in ("nav a[href='/explore/']", "svg[aria-label='Início']", "svg[aria-label='Home']", "a[href*='/direct/']"):
            try:
                if await page.locator(selector).first.is_visible(timeout=1500):
                    return True
            except Exception:
                continue
        return False

    async def _ensure_login(self, page, context, state_file: Path) -> None:
        if await self._is_logged_in(page):
            self.say("login", "Sessão já autenticada — seguindo direto.", 15)
            return

        visivel = not self.settings.headless
        marca_de_falha = self.settings.session_dir / f"{self.settings.ig_username or 'anon'}.sem-auto"

        # Situacoes em que preencher o formulario e so perder tempo e chamar
        # atencao: o Instagram recusa login automatizado, e cada tentativa
        # recusada aumenta a suspeita sobre a conta.
        motivo = None
        if self.settings.login_manual:
            motivo = "configurado para entrar à mão"
        elif self.settings.chrome_profile or self.settings.ig_sessionid:
            motivo = "a sessão configurada não estava mais válida"
        elif marca_de_falha.exists():
            motivo = "o login automático já foi recusado antes nesta conta"

        if motivo and visivel:
            self.say("login", f"Entre na janela do Chrome — {motivo}.", 9)
            return await self._login_manual(page, context, state_file)

        if not self.settings.ig_username or not self.settings.ig_password:
            if visivel:
                self.say("login", "Sem credenciais salvas — entre na janela do Chrome.", 9)
                return await self._login_manual(page, context, state_file)
            raise LoginRequired(
                "Defina IG_USERNAME e IG_PASSWORD no arquivo .env, ou rode com HEADLESS=false "
                "para entrar a mão na janela do Chrome."
            )

        try:
            await self._login_automatico(page, context, state_file)
        except LoginRequired:
            raise
        except Exception as exc:
            # Qualquer imprevisto no formulario: com a janela aberta na frente
            # da pessoa, insistir na automacao e pior do que pedir ajuda.
            arquivo = await self._diagnostico(page, "falha-no-login-automatico")
            try:  # nao repetir a tentativa recusada na proxima execucao
                marca_de_falha.write_text("o login automático foi recusado", encoding="utf-8")
            except Exception:
                pass
            if visivel:
                self.notes.append(f"Login automático falhou ({type(exc).__name__}); concluído à mão.")
                self.say("login", "O login automático não passou — assuma na janela do Chrome.", 9)
                return await self._login_manual(page, context, state_file)
            raise LoginRequired(
                f"Falha no login automático: {exc}"
                + (f"\nGuardei o que apareceu em: {arquivo}" if arquivo else "")
            )

    async def _login_automatico(self, page, context, state_file: Path) -> None:
        """Preenche o formulário de login imitando uma pessoa digitando."""
        self.say("login", "Entrando na conta como uma pessoa faria...", 8)
        if "/accounts/login" not in page.url:
            await page.goto(
                f"{self.settings.base_url}/accounts/login/", wait_until="domcontentloaded", timeout=60000
            )
            await self.human.pause("media")
            await self._click_any(page, COOKIE_BUTTONS)

        user_field = await self._achar_campo(page, CAMPOS_USUARIO, 25000)
        if user_field is None:
            # O Instagram nao mostrou o formulario. Pode ser consentimento,
            # tela de "entrar ou cadastrar", bloqueio temporario ou desafio.
            arquivo = await self._diagnostico(page, "sem-formulario-de-login")
            if not self.settings.headless:
                self.say("login", "Formulario nao apareceu — assuma na janela do Chrome.", 9)
                return await self._login_manual(page, context, state_file)
            raise LoginRequired(
                "O Instagram nao exibiu o formulario de login. Isso costuma ser tela de "
                "consentimento, verificacao de seguranca ou bloqueio temporario do IP.\n"
                "Rode com HEADLESS=false para ver a janela e concluir o login a mao."
                + (f"\nGuardei o que apareceu na tela em: {arquivo}" if arquivo else "")
            )

        pass_field = await self._achar_campo(page, CAMPOS_SENHA, 8000)
        if pass_field is None:
            pass_field = page.locator("input[type='password']").first

        await self.human.pause("curta")
        await self.human.type_text(user_field, self.settings.ig_username, page)
        await self.human.type_text(pass_field, self.settings.ig_password, page)
        await self.human.pause("curta")

        if not await self._clicar_entrar(page, pass_field):
            arquivo = await self._diagnostico(page, "sem-botao-entrar")
            if not self.settings.headless:
                return await self._login_manual(page, context, state_file)
            raise LoginRequired(
                "Nao encontrei o botao de entrar na tela do Instagram."
                + (f"\nGuardei o que apareceu em: {arquivo}" if arquivo else "")
            )
        self.say("login", "Aguardando a confirmacao do Instagram...", 12)

        try:
            await page.wait_for_load_state("networkidle", timeout=45000)
        except Exception:
            pass
        await self.human.pause("longa")

        await self._check_login_problems(page)
        await self._click_any(page, DISMISS_BUTTONS)  # "Salvar informacoes de login?"
        await self.human.pause("curta")
        await self._click_any(page, DISMISS_BUTTONS)  # "Ativar notificacoes?"

        if not await self._is_logged_in(page):
            await self.human.pause("media")
            if not await self._is_logged_in(page):
                arquivo = await self._diagnostico(page, "login-nao-concluido")
                if not self.settings.headless:
                    self.say("login", "O Instagram pediu algo a mais — resolva na janela do Chrome.", 10)
                    return await self._login_manual(page, context, state_file)
                raise LoginRequired(
                    "O login nao foi concluido. Verifique usuario e senha, ou rode com "
                    "HEADLESS=false para concluir a verificacao na janela do Chrome."
                    + (f"\nGuardei o que apareceu na tela em: {arquivo}" if arquivo else "")
                )
        try:
            await context.storage_state(path=str(state_file))
        except Exception:
            pass
        # Deu certo: a marca de recusa nao vale mais.
        try:
            (self.settings.session_dir / f"{self.settings.ig_username or 'anon'}.sem-auto").unlink(missing_ok=True)
        except Exception:
            pass
        self.say("login", "Conta autenticada.", 15)

    async def _clicar_entrar(self, page, campo_senha) -> bool:
        """Aciona o envio do formulario.

        O botao ja apareceu como <button type=submit>, como <div role=button> e
        so com o rotulo textual. Apertar Enter no campo de senha funciona em
        todas as variantes, entao ele fica como ultimo recurso.
        """
        for seletor in (
            "button[type='submit']",
            "button:has-text('Entrar')",
            "button:has-text('Log in')",
            "div[role='button']:has-text('Entrar')",
            "div[role='button']:has-text('Log in')",
        ):
            try:
                botao = page.locator(seletor).first
                if await botao.is_visible(timeout=1500):
                    await self.human.click(botao, page)
                    return True
            except Exception:
                continue
        try:
            await campo_senha.press("Enter")
            return True
        except Exception:
            return False

    async def _achar_campo(self, page, seletores: list[str], timeout: int):
        """Devolve o primeiro campo visivel entre varios seletores possiveis.

        O tempo total e respeitado no conjunto, nao por seletor: tentar seis
        seletores com 25s cada faria a espera passar de dois minutos.
        """
        limite = time.monotonic() + timeout / 1000
        while time.monotonic() < limite:
            for seletor in seletores:
                try:
                    campo = page.locator(seletor).first
                    if await campo.is_visible(timeout=600):
                        return campo
                except Exception:
                    continue
            await self._descartar_dialogos(page)
            await asyncio.sleep(0.6)
        return None

    async def _descartar_dialogos(self, page) -> None:
        """Tenta fechar o que estiver por cima do formulario."""
        await self._click_any(page, COOKIE_BUTTONS)

    async def _diagnostico(self, page, motivo: str) -> str:
        """Guarda o que estava na tela quando algo deu errado.

        Sem isso o navegador fecha junto com a falha e resta apenas uma
        mensagem tecnica, sem a informacao que resolveria o caso.
        """
        try:
            self.settings.ensure_dirs()
            marca = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            base = self.settings.runs_dir / f"diagnostico-{motivo}-{marca}"
            await page.screenshot(path=f"{base}.png", full_page=True)
            try:
                texto = await page.inner_text("body", timeout=4000)
            except Exception:
                texto = ""
            Path(f"{base}.txt").write_text(
                f"URL: {page.url}\nMotivo: {motivo}\n\n{texto[:6000]}", encoding="utf-8"
            )
            self.notes.append(f"Diagnostico salvo em {base}.png")
            return f"{base}.png"
        except Exception:
            return ""

    async def _login_manual(self, page, context, state_file: Path, espera: int = 900) -> None:
        """Entrega o volante para a pessoa concluir o login na janela aberta.

        Desafio de seguranca, 2FA e telas novas do Instagram nao se resolvem por
        automacao — e nem deveriam. Como a janela ja esta visivel, o caminho
        honesto e pedir que a pessoa conclua e apenas aguardar.
        """
        self.say(
            "login",
            "Conclua o login na janela do Chrome que está aberta (código, captcha ou confirmação). "
            f"Aguardo até {espera // 60} minutos.",
            10,
        )
        limite = time.monotonic() + espera
        while time.monotonic() < limite:
            await asyncio.sleep(3)
            try:
                if await self._is_logged_in(page):
                    try:
                        await context.storage_state(path=str(state_file))
                    except Exception:
                        pass
                    self.notes.append("Login concluído manualmente na janela do navegador.")
                    self.say("login", "Login concluído. Seguindo com a leitura.", 15)
                    return
            except Exception:
                continue
            restante = int(limite - time.monotonic())
            if restante % 30 < 3:
                self.say("login", f"Aguardando o login na janela do Chrome... {restante}s restantes.", 10)
        raise LoginRequired(
            "O login nao foi concluido dentro do tempo. Deixe a janela do Chrome aberta, "
            "conclua o que o Instagram pedir e rode a analise de novo — a sessao fica salva."
        )

    async def _check_login_problems(self, page) -> None:
        if "/challenge/" in page.url or "/auth_platform/" in page.url:
            raise LoginRequired(
                "O Instagram pediu verificacao de seguranca (desafio/2FA). Rode com HEADLESS=false, "
                "conclua a verificacao na janela do Chrome e execute de novo — a sessao fica salva."
            )
        try:
            body = (await page.inner_text("body", timeout=5000)).lower()
        except Exception:
            return
        if "senha incorreta" in body or "incorrect password" in body or "sua senha estava incorreta" in body:
            raise LoginRequired("Senha incorreta para a conta informada.")
        if "código de segurança" in body or "security code" in body or "two-factor" in body:
            raise LoginRequired(
                "A conta usa autenticacao em dois fatores. Rode com HEADLESS=false e digite o codigo "
                "na janela do Chrome; a sessao autenticada fica salva para as proximas analises."
            )

    # ------------------------------------------------------------------
    # Leitura do perfil
    # ------------------------------------------------------------------
    async def _read_profile(self, page, username: str, start: datetime, end: datetime) -> list[Post]:
        self.say("perfil", f"Abrindo o perfil @{username}...", 20)
        await page.goto(
            f"{self.settings.base_url}/{username}/", wait_until="domcontentloaded", timeout=60000
        )
        await self.human.pause("longa")

        try:
            header = await page.inner_text("header", timeout=8000)
            await self.human.read(header, minimum=2.5)  # le a bio com calma
        except Exception:
            await self.human.pause("media")

        if await self._looks_private(page):
            self.notes.append(
                "Perfil privado ou sem acesso: so foi possivel ler o que estava visivel para esta conta."
            )

        await self._scroll_grid(page, start)
        candidates = self._posts_in_window(start, end, username)
        self.say(
            "perfil",
            f"{len(candidates)} publicacao(oes) dentro do periodo. Comecando a leitura.",
            35,
        )
        if not candidates:
            return []

        limit = min(len(candidates), self.settings.max_posts)
        for index, post in enumerate(candidates[:limit], start=1):
            share = 35 + int(55 * index / limit)
            self.say("lendo", f"Lendo publicacao {index}/{limit} ({post.shortcode})...", share)
            await self._read_post(page, post)
            await self.human.pause("media")
            await self.human.maybe_distract()  # a pessoa se distrai de vez em quando

        posts = self.harvester.attach_comments()
        selected = {p.shortcode for p in candidates[:limit]}
        return [p for p in posts if p.shortcode in selected]

    async def _looks_private(self, page) -> bool:
        try:
            body = (await page.inner_text("body", timeout=5000)).lower()
        except Exception:
            return False
        return "esta conta é privada" in body or "this account is private" in body

    async def _scroll_grid(self, page, start: datetime) -> None:
        """Rola a grade ate cobrir o periodo pedido.

        As fixadas aparecem no topo mesmo sendo antigas, entao so paramos apos
        varias publicacoes seguidas anteriores ao inicio do intervalo.
        """
        self.say("perfil", "Percorrendo as publicacoes do perfil...", 25)
        stale_rounds = 0
        previous_total = 0
        for _ in range(40):
            await self.human.scroll(page, distance=self.human.rng.randint(600, 1100))
            await self.human.pause("curta")
            total = len(self.harvester.posts)
            dated = [p for p in self.harvester.posts.values() if p.created_at and not p.is_pinned]
            older = [p for p in dated if p.created_at < start]
            if len(older) >= 3:
                break
            if total == previous_total:
                stale_rounds += 1
                if stale_rounds >= 3:  # nao carrega mais nada: fim do perfil
                    break
            else:
                stale_rounds = 0
            previous_total = total
            if total >= self.settings.max_posts * 3:
                break

    def _posts_in_window(self, start: datetime, end: datetime, username: str) -> list[Post]:
        """Publicacoes do perfil pedido dentro do periodo.

        O filtro por dono e indispensavel: antes de chegar ao perfil, a sessao
        passa pela pagina inicial, e o feed de quem esta logado traz
        publicacoes de contas que ele segue. Sem este filtro, elas entram na
        analise e o laudo passa a descrever outro perfil.
        """
        alvo = (username or "").lower().lstrip("@")
        selected = []
        descartadas = 0
        for post in self.harvester.posts.values():
            if not post.created_at or not (start <= post.created_at <= end):
                continue
            if post.owner and post.owner.lower() != alvo:
                descartadas += 1
                continue
            selected.append(post)
        if descartadas:
            self.notes.append(
                f"{descartadas} publicação(ões) de outros perfis (vistas no feed) foram descartadas."
            )
        selected.sort(key=lambda p: p.created_at, reverse=True)
        return selected

    async def _read_post(self, page, post: Post) -> None:
        """Abre uma publicacao, le a legenda e os comentarios, e fecha."""
        self._current_post_id = post.id
        opened_modal = False
        try:
            thumb = page.locator(f"a[href*='/{post.shortcode}/']").first
            if await thumb.is_visible(timeout=2500):
                await self.human.click(thumb, page)
                opened_modal = True
        except Exception:
            opened_modal = False

        if not opened_modal:
            await page.goto(post.url, wait_until="domcontentloaded", timeout=60000)

        await self.human.pause("longa")
        await self.human.read(post.caption or "", minimum=2.0)

        await self._expand_comments(page, post)

        if opened_modal:
            try:
                await page.keyboard.press("Escape")
            except Exception:
                pass
        else:
            try:
                await page.go_back(wait_until="domcontentloaded", timeout=30000)
            except Exception:
                pass
        await self.human.pause("curta")
        self._current_post_id = ""

    async def _expand_comments(self, page, post: Post) -> None:
        """Abre as respostas e carrega mais comentarios, lendo enquanto rola."""
        target = min(post.comment_count or 0, self.settings.max_comments_per_post)
        rounds = 0
        while rounds < 12:
            rounds += 1
            loaded = len([c for c in self.harvester.comments.values() if c.post_id == post.id])
            if target and loaded >= target:
                break
            await self.human.scroll(page, distance=self.human.rng.randint(300, 620))
            expanded = await self._click_any(page, MORE_COMMENTS)
            if not expanded:
                expanded = await self._click_plus_button(page)
            await self._click_any(page, MORE_REPLIES)
            # tempo de leitura dos comentarios que acabaram de aparecer
            await self.human.pause("curta")
            new_loaded = len([c for c in self.harvester.comments.values() if c.post_id == post.id])
            if new_loaded > loaded:
                fresh = new_loaded - loaded
                await asyncio.sleep(min(6.0, fresh * 0.45 * self.settings.pace_factor))
            elif not expanded:
                break

    async def _click_plus_button(self, page) -> bool:
        """O botao '+' redondo que carrega mais comentarios (sem rotulo textual)."""
        for selector in (
            "button svg[aria-label*='Carregar mais']",
            "button svg[aria-label*='Load more']",
            "button:has(svg[aria-label*='mais comentários'])",
        ):
            try:
                element = page.locator(selector).first
                if await element.is_visible(timeout=1200):
                    await self.human.click(element, page)
                    return True
            except Exception:
                continue
        return False

    def _build_profile(self, username: str) -> Profile:
        fields = self.harvester.profile_fields()
        return Profile(
            username=fields.get("username") or username,
            url=f"https://www.instagram.com/{username}/",
            full_name=fields.get("full_name", ""),
            biography=fields.get("biography", ""),
            followers=fields.get("followers", 0),
            following=fields.get("following", 0),
            posts_total=fields.get("posts_total", 0),
            is_private=fields.get("is_private", False),
        )


async def collect(
    settings: Settings, profile_url: str, start: datetime, end: datetime, progress: Optional[Progress] = None
) -> SessionResult:
    reader = InstagramReader(settings, progress)
    return await reader.run(profile_url, start, end)
