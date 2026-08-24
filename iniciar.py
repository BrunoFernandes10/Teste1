#!/usr/bin/env python3
"""Instalador e inicializador do sistema — Windows, Mac ou Linux.

Um comando so:  python iniciar.py

Cuida de tudo: instala as dependencias, baixa o navegador, cria o arquivo de
configuracao, pergunta o que falta e abre o sistema no navegador.
"""

from __future__ import annotations

import getpass
import os
import re
import shutil
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
ENV = RAIZ / ".env"
# Copia guardada fora do projeto: baixar o ZIP de novo nao apaga a configuracao
# nem o login salvo, entao nao e preciso digitar tudo outra vez a cada versao.
PESSOAL = Path.home() / ".analise-instagram"
ENV_PESSOAL = PESSOAL / ".env"
PORTA = int(os.getenv("PORTA", "8000"))

VERDE, AMARELO, VERMELHO, AZUL, NEGRITO, FIM = (
    ("\033[92m", "\033[93m", "\033[91m", "\033[94m", "\033[1m", "\033[0m")
    if sys.stdout.isatty() and os.name != "nt"
    else ("", "", "", "", "", "")
)


def titulo(texto: str) -> None:
    print(f"\n{AZUL}{NEGRITO}{texto}{FIM}")


def ok(texto: str) -> None:
    print(f"  {VERDE}OK{FIM}  {texto}")


def aviso(texto: str) -> None:
    print(f"  {AMARELO}!{FIM}   {texto}")


def erro(texto: str) -> None:
    print(f"  {VERMELHO}X{FIM}   {texto}")


def rodar(comando: list[str], descricao: str) -> bool:
    print(f"      {descricao}...", end="", flush=True)
    try:
        resultado = subprocess.run(comando, capture_output=True, text=True, timeout=900)
    except Exception as exc:
        print(f" {VERMELHO}falhou{FIM}")
        erro(str(exc)[:200])
        return False
    if resultado.returncode == 0:
        print(f" {VERDE}pronto{FIM}")
        return True
    print(f" {VERMELHO}falhou{FIM}")
    for linha in (resultado.stderr or resultado.stdout).strip().splitlines()[-4:]:
        print(f"      {linha[:150]}")
    return False


def checar_python() -> bool:
    titulo("1. Verificando o Python")
    if sys.version_info < (3, 9):
        erro(f"Python {sys.version_info.major}.{sys.version_info.minor} encontrado; e preciso 3.9 ou mais novo.")
        print("      Baixe em https://www.python.org/downloads/")
        return False
    ok(f"Python {sys.version_info.major}.{sys.version_info.minor}")
    return True


def instalar_dependencias() -> bool:
    titulo("2. Instalando as bibliotecas")
    try:
        import fastapi, playwright, anthropic  # noqa: F401

        ok("bibliotecas ja instaladas")
        return True
    except ImportError:
        pass
    if rodar(
        [sys.executable, "-m", "pip", "install", "-q", "-r", str(RAIZ / "requirements.txt")],
        "baixando (pode levar 1-2 minutos)",
    ):
        return True

    # Uma unica biblioteca sem versao pronta para este Python derruba o lote
    # inteiro. Instalando uma a uma, o que der certo fica instalado e o
    # diagnostico aponta exatamente a que faltou.
    aviso("a instalacao em bloco falhou; tentando uma biblioteca por vez.")
    essenciais = ["fastapi", "uvicorn", "playwright", "anthropic", "python-dotenv", "pydantic"]
    faltando = [
        nome for nome in essenciais
        if not rodar([sys.executable, "-m", "pip", "install", "-q", nome], f"instalando {nome}")
    ]
    if faltando:
        erro("nao consegui instalar: " + ", ".join(faltando))
        print("      Tente manualmente:")
        print(f"      {sys.executable} -m pip install " + " ".join(faltando))
        return False
    return True


def instalar_navegador() -> bool:
    titulo("3. Preparando o navegador")
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            navegador = pw.chromium.launch(headless=True)
            navegador.close()
        ok("navegador pronto")
        return True
    except Exception:
        pass
    if rodar([sys.executable, "-m", "playwright", "install", "chromium"], "baixando o Chromium (~150 MB)"):
        return True
    aviso("nao consegui baixar o navegador automaticamente.")
    print("      Rode manualmente:  python -m playwright install chromium")
    return False


USUARIO_VALIDO = re.compile(r"^[A-Za-z0-9._]{1,30}$")


def perguntar(rotulo: str, atual: str = "", segredo: bool = False,
              validar=None, ajuda: str = "") -> str:
    """Pergunta um valor. Segredos nao aparecem na tela enquanto sao digitados.

    Quando ha validacao, a pergunta se repete ate vir algo valido. Sem isso um
    comando colado por engano vira "nome de usuario" e a falha so aparece muito
    depois, na tela de login do Instagram, parecendo senha errada.
    """
    sufixo = f" [{'*' * 6 if segredo and atual else atual}]" if atual else ""
    pergunta = f"      {rotulo}{sufixo}: "
    for _ in range(5):
        try:
            resposta = (getpass.getpass(pergunta) if segredo else input(pergunta)).strip()
        except (EOFError, KeyboardInterrupt):
            return atual
        valor = resposta or atual
        if not valor or validar is None or validar(valor):
            return valor
        erro(f"valor invalido: {resposta[:40]!r}")
        if ajuda:
            print(f"      {ajuda}")
    return atual


def perfil_chrome_padrao() -> str:
    """Onde o Chrome guarda os perfis, conforme o sistema."""
    candidatos = []
    if os.name == "nt":
        base = os.getenv("LOCALAPPDATA", "")
        if base:
            candidatos.append(Path(base) / "Google" / "Chrome" / "User Data")
    elif sys.platform == "darwin":
        candidatos.append(Path.home() / "Library" / "Application Support" / "Google" / "Chrome")
    else:
        candidatos.append(Path.home() / ".config" / "google-chrome")
    for caminho in candidatos:
        if caminho.exists():
            return str(caminho)
    return ""


def ler_env() -> dict[str, str]:
    valores: dict[str, str] = {}
    if ENV.exists():
        for linha in ENV.read_text(encoding="utf-8").splitlines():
            if "=" in linha and not linha.strip().startswith("#"):
                chave, _, valor = linha.partition("=")
                valores[chave.strip()] = valor.strip()
    return valores


def configurar(interativo: bool) -> dict[str, str]:
    titulo("4. Configuração")
    if not ENV.exists():
        if ENV_PESSOAL.exists():
            shutil.copy(ENV_PESSOAL, ENV)
            ok("configuração anterior recuperada — não precisa digitar de novo")
        else:
            shutil.copy(RAIZ / ".env.example", ENV)
            ok("arquivo .env criado")
    valores = ler_env()

    if not interativo:
        return valores

    print("\n      Deixe em branco para pular — dá para editar o arquivo .env depois.")
    print("      As senhas não aparecem na tela enquanto você digita.\n")
    atual_usuario = valores.get("IG_USERNAME", "")
    if atual_usuario and not USUARIO_VALIDO.match(atual_usuario):
        aviso(f"o usuário salvo está inválido ({atual_usuario[:40]!r}) e será substituído.")
        atual_usuario = ""
    valores["IG_USERNAME"] = perguntar(
        "Usuário do Instagram (sem @)", atual_usuario,
        validar=lambda v: bool(USUARIO_VALIDO.match(v.lstrip("@"))),
        ajuda="Só o nome da conta: letras, números, ponto e sublinhado. Sem espaços e sem comandos.",
    ).lstrip("@")
    valores["IG_PASSWORD"] = perguntar("Senha do Instagram", valores.get("IG_PASSWORD", ""), segredo=True)
    # Aproveitar o Chrome do dia a dia dispensa o login por completo — e o
    # Instagram costuma recusar login automatizado mesmo com a senha correta.
    perfil = perfil_chrome_padrao()
    if perfil:
        print()
        print("      Encontrei o seu Chrome. Se você já está logado no Instagram nele,")
        print("      o sistema aproveita essa sessão e nem passa pela tela de login.")
        print("      Ele trabalha sobre uma cópia, então pode deixar o Chrome aberto.")
        usar = perguntar("Usar o seu Chrome? (s/n)", "s" if valores.get("CHROME_PROFILE") else "n")
        valores["CHROME_PROFILE"] = perfil if usar.lower().startswith("s") else ""

    print()
    print("      A chave da Anthropic melhora muito a análise (entende ironia e sarcasmo).")
    print("      Pegue em https://console.anthropic.com  — ou deixe em branco por ora.")
    valores["ANTHROPIC_API_KEY"] = perguntar("Chave da Anthropic", valores.get("ANTHROPIC_API_KEY", ""), segredo=True)

    linhas = []
    for linha in ENV.read_text(encoding="utf-8").splitlines():
        if "=" in linha and not linha.strip().startswith("#"):
            chave = linha.split("=", 1)[0].strip()
            if chave in valores:
                linhas.append(f"{chave}={valores[chave]}")
                continue
        linhas.append(linha)
    conteudo = "\n".join(linhas) + "\n"
    ENV.write_text(conteudo, encoding="utf-8")
    try:  # guarda a copia pessoal para a proxima versao do projeto
        PESSOAL.mkdir(parents=True, exist_ok=True)
        ENV_PESSOAL.write_text(conteudo, encoding="utf-8")
    except Exception:
        pass
    ok("configuração salva em .env")
    return valores


def diagnostico(valores: dict[str, str]) -> None:
    titulo("5. Situação")
    if valores.get("IG_USERNAME") and valores.get("IG_PASSWORD"):
        ok(f"conta do Instagram configurada: @{valores['IG_USERNAME']}")
    else:
        aviso("sem conta configurada — só o modo demonstração vai funcionar")
        print("      Preencha IG_USERNAME e IG_PASSWORD no arquivo .env")

    if valores.get("CHROME_PROFILE"):
        ok("vai usar a sessão do seu Chrome (pode deixá-lo aberto)")
    elif valores.get("IG_SESSIONID"):
        ok("vai usar o cookie de sessão informado")

    if valores.get("ANTHROPIC_API_KEY"):
        ok("analista de IA ativo")
    else:
        aviso("sem chave da Anthropic — análise pelo motor lexical (mais raso em ironia)")

    sessoes = PESSOAL / "sessions"
    if any(sessoes.glob("*.json")) if sessoes.exists() else False:
        ok("login do Instagram já salvo — não deve pedir de novo")

    try:
        import urllib.request

        urllib.request.urlopen("https://www.instagram.com/", timeout=12)
        ok("Instagram acessível a partir desta máquina")
    except Exception as exc:
        aviso(f"não consegui alcançar o Instagram agora ({type(exc).__name__})")
        print("      Verifique sua internet. VPN ou proxy corporativo costumam atrapalhar.")


def subir_servidor() -> None:
    titulo("6. Abrindo o sistema")
    print(f"\n      {NEGRITO}http://localhost:{PORTA}{FIM}\n")
    print("      Na tela inicial você pode:")
    print("        • clicar em 'Ver o painel com dados de exemplo' (não precisa de nada)")
    print("        • ou informar a URL do perfil e o período para a análise real\n")
    print(f"      Para encerrar: {NEGRITO}Ctrl+C{FIM}\n")

    def abrir():
        time.sleep(2.5)
        try:
            webbrowser.open(f"http://localhost:{PORTA}")
        except Exception:
            pass

    import threading

    threading.Thread(target=abrir, daemon=True).start()

    import uvicorn

    sys.path.insert(0, str(RAIZ))
    uvicorn.run("sentiment.server:app", host="127.0.0.1", port=PORTA, log_level="warning")


def main() -> int:
    print(f"\n{NEGRITO}Análise de Sentimento de Perfis do Instagram{FIM}")
    print("Instalação e inicialização automática\n" + "─" * 52)

    if not checar_python():
        return 1
    if not instalar_dependencias():
        erro("não foi possível instalar as bibliotecas.")
        print(f"      Tente manualmente: {sys.executable} -m pip install -r requirements.txt")
        return 1
    instalar_navegador()

    interativo = sys.stdin.isatty() and "--sem-perguntas" not in sys.argv
    valores = configurar(interativo)
    diagnostico(valores)

    try:
        subir_servidor()
    except KeyboardInterrupt:
        print("\n\nEncerrado. Rode 'python iniciar.py' quando quiser voltar.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
