"""Extrai os cookies de sessao do Instagram diretamente do Chrome.

Copiar a pasta do perfil nao funciona: o Chrome guarda os cookies cifrados com
uma chave presa ao usuario do Windows (DPAPI), e nao os reconstroi numa copia
solta. Aqui fazemos o que o proprio navegador faz por dentro — ler o banco
SQLite de cookies e decifrar cada valor com essa chave — para entregar ao
Playwright a sessao ja autenticada, sem passar por nenhuma tela de login.

So le; nunca escreve nada no perfil do Chrome. Roda apenas na mesma conta de
usuario que abriu o Chrome, porque a chave DPAPI e daquele usuario.
"""

from __future__ import annotations

import base64
import json
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Optional

COOKIES_ALVO = {"sessionid", "ds_user_id", "csrftoken", "mid", "rur", "ig_did"}


class CookiesIndisponiveis(RuntimeError):
    """Nao foi possivel obter os cookies do Chrome (motivo no texto)."""


def _dpapi_unprotect(dados: bytes) -> bytes:
    """Desfaz a protecao DPAPI do Windows (usada na chave mestra)."""
    import ctypes
    import ctypes.wintypes as wt

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    entrada = BLOB(len(dados), ctypes.cast(ctypes.create_string_buffer(dados, len(dados)),
                                           ctypes.POINTER(ctypes.c_char)))
    saida = BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(entrada), None, None, None, None, 0, ctypes.byref(saida)
    ):
        raise CookiesIndisponiveis("Windows recusou a chave dos cookies (usuário diferente?).")
    buffer = ctypes.string_at(saida.pbData, saida.cbData)
    ctypes.windll.kernel32.LocalFree(saida.pbData)
    return buffer


def _chave_mestra(user_data_dir: Path) -> bytes:
    estado = user_data_dir / "Local State"
    if not estado.exists():
        raise CookiesIndisponiveis(f"'Local State' não encontrado em {user_data_dir}.")
    dados = json.loads(estado.read_text(encoding="utf-8"))
    cifrada = base64.b64decode(dados["os_crypt"]["encrypted_key"])
    if cifrada[:5] != b"DPAPI":
        raise CookiesIndisponiveis("Formato inesperado da chave do Chrome.")
    return _dpapi_unprotect(cifrada[5:])


def _decifrar(valor: bytes, chave: bytes) -> str:
    if not valor:
        return ""
    prefixo = valor[:3]
    if prefixo in (b"v10", b"v11"):
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        nonce, corpo = valor[3:15], valor[15:]
        aberto = AESGCM(chave).decrypt(nonce, corpo, None)
        return aberto.decode("utf-8", "ignore")
    if prefixo == b"v20":
        raise CookiesIndisponiveis(
            "Este Chrome usa App-Bound Encryption (versão 127+), que bloqueia a leitura "
            "dos cookies por outro programa. Use a opção do cookie sessionid manual."
        )
    # Chrome antigo: DPAPI direto no valor
    return _dpapi_unprotect(valor).decode("utf-8", "ignore")


def extrair_cookies(user_data_dir: str | Path, perfil: str = "Default") -> list[dict]:
    """Devolve os cookies do instagram.com prontos para o Playwright."""
    if sys.platform != "win32":
        raise CookiesIndisponiveis("A extração automática de cookies só está disponível no Windows.")

    base = Path(user_data_dir).expanduser()
    banco = base / perfil / "Network" / "Cookies"
    if not banco.exists():
        banco = base / perfil / "Cookies"  # layout antigo
    if not banco.exists():
        raise CookiesIndisponiveis(f"Arquivo de cookies não encontrado no perfil '{perfil}'.")

    chave = _chave_mestra(base)

    # O Chrome mantem o banco aberto; lemos de uma copia para nao concorrer.
    with tempfile.TemporaryDirectory() as tmp:
        copia = Path(tmp) / "Cookies"
        shutil.copy2(banco, copia)
        conexao = sqlite3.connect(str(copia))
        try:
            linhas = conexao.execute(
                "SELECT name, encrypted_value, host_key, path, is_secure, is_httponly, expires_utc "
                "FROM cookies WHERE host_key LIKE '%instagram.com%'"
            ).fetchall()
        finally:
            conexao.close()

    cookies, achou_sessao = [], False
    for nome, cifrado, host, caminho, secure, httponly, expira in linhas:
        if nome not in COOKIES_ALVO:
            continue
        try:
            valor = _decifrar(cifrado, chave)
        except CookiesIndisponiveis:
            raise
        except Exception:
            continue
        if not valor:
            continue
        if nome == "sessionid":
            achou_sessao = True
        cookies.append({
            "name": nome,
            "value": valor,
            "domain": host if host.startswith(".") else "." + host.lstrip("."),
            "path": caminho or "/",
            "secure": bool(secure),
            "httpOnly": bool(httponly),
        })

    if not achou_sessao:
        raise CookiesIndisponiveis(
            "Não encontrei uma sessão ativa do Instagram neste Chrome. "
            "Abra o instagram.com no Chrome, confirme que está logado e tente de novo."
        )
    return cookies
