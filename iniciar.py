#!/usr/bin/env python3
"""Instalador e inicializador do sistema — Windows, Mac ou Linux.

Um comando so:  python iniciar.py

Cuida de tudo: instala as dependencias, baixa o navegador, cria o arquivo de
configuracao, pergunta o que falta e abre o sistema no navegador.
"""

from __future__ import annotations

import getpass
import os
import shutil
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
ENV = RAIZ / ".env"
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


def perguntar(rotulo: str, atual: str = "", segredo: bool = False) -> str:
    """Pergunta um valor. Segredos nao aparecem na tela enquanto sao digitados."""
    sufixo = f" [{'*' * 6 if segredo and atual else atual}]" if atual else ""
    pergunta = f"      {rotulo}{sufixo}: "
    try:
        if segredo:
            # Digitacao oculta: nada de senha visivel no terminal (nem em print
            # de tela, nem no historico de rolagem).
            resposta = getpass.getpass(pergunta).strip()
        else:
            resposta = input(pergunta).strip()
    except (EOFError, KeyboardInterrupt):
        return atual
    return resposta or atual


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
        shutil.copy(RAIZ / ".env.example", ENV)
        ok("arquivo .env criado")
    valores = ler_env()

    if not interativo:
        return valores

    print("\n      Deixe em branco para pular — dá para editar o arquivo .env depois.")
    print("      As senhas não aparecem na tela enquanto você digita.\n")
    valores["IG_USERNAME"] = perguntar("Usuário do Instagram (sem @)", valores.get("IG_USERNAME", "")).lstrip("@")
    valores["IG_PASSWORD"] = perguntar("Senha do Instagram", valores.get("IG_PASSWORD", ""), segredo=True)
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
    ENV.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    ok("configuração salva em .env")
    return valores


def diagnostico(valores: dict[str, str]) -> None:
    titulo("5. Situação")
    if valores.get("IG_USERNAME") and valores.get("IG_PASSWORD"):
        ok(f"conta do Instagram configurada: @{valores['IG_USERNAME']}")
    else:
        aviso("sem conta configurada — só o modo demonstração vai funcionar")
        print("      Preencha IG_USERNAME e IG_PASSWORD no arquivo .env")

    if valores.get("ANTHROPIC_API_KEY"):
        ok("analista de IA ativo")
    else:
        aviso("sem chave da Anthropic — análise pelo motor lexical (mais raso em ironia)")

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
