"""Garante que a análise descreve o perfil pedido, e só ele.

Antes de chegar ao perfil, a sessão passa pela página inicial do Instagram, e
o feed de quem está logado traz publicações das contas que ele segue. Sem
filtro por dono, essas publicações entram na análise e o laudo passa a
descrever outro perfil — foi exatamente o que aconteceu numa análise da
@shopee_br feita por uma conta que segue o @flamengo.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from sentiment.collector.instagram import InstagramReader  # noqa: E402
from sentiment.config import Settings  # noqa: E402

AGORA = datetime.now(timezone.utc)


def _ts(dias: int) -> int:
    return int((AGORA - timedelta(days=dias)).timestamp())


def _media(pk: str, code: str, dono: str, dias: int, legenda: str) -> dict:
    return {
        "pk": pk, "code": code, "taken_at": _ts(dias), "like_count": 100,
        "comment_count": 1, "media_type": 1, "caption": {"text": legenda},
        "user": {"username": dono},
    }


def _ok(condicao: bool, texto: str) -> bool:
    print(f"  [{'OK ' if condicao else 'FALHA'}] {texto}")
    return condicao


def main() -> int:
    leitor = InstagramReader(Settings())

    # O feed da pessoa logada, carregado ao abrir o Instagram.
    leitor.harvester.ingest({"items": [
        _media("1", "Fla1", "flamengo", 2, "Equipe de arbitragem para #CRUxFLA"),
        _media("2", "Fla2", "flamengo", 3, "Hoje tem jogo! Qual desses é você? @shopee_br"),
        _media("3", "Out1", "outroperfil", 1, "Publicação de outra conta seguida"),
    ]})
    leitor.harvester.ingest({"comments": [
        {"pk": "c1", "text": "Rossi falhando de novo!", "created_at": _ts(2),
         "comment_like_count": 40, "user": {"username": "torcedor1"}},
    ]}, current_post_id="1")

    # O perfil que o usuário realmente pediu.
    leitor.harvester.ingest({"items": [
        _media("9", "Shp1", "shopee_br", 1, "Frete grátis em toda a loja"),
    ]})
    leitor.harvester.ingest({"comments": [
        {"pk": "c9", "text": "Meu pedido está atrasado, quero reembolso", "created_at": _ts(1),
         "comment_like_count": 30, "user": {"username": "bealvees"}},
    ]}, current_post_id="9")
    leitor.harvester.attach_comments()

    escolhidas = leitor._posts_in_window(AGORA - timedelta(days=7), AGORA, "shopee_br")
    donos = {p.owner for p in escolhidas}
    autores = {c.author for p in escolhidas for c in p.comments}

    print("\nSeparação entre o feed e o perfil analisado")
    checagens = [
        _ok(donos == {"shopee_br"}, f"só publicações do perfil pedido (donos: {donos or 'nenhum'})"),
        _ok(len(escolhidas) == 1, f"as 3 publicações do feed foram descartadas (restaram {len(escolhidas)})"),
        _ok(any("outros perfis" in n for n in leitor.notes), "o descarte fica registrado no laudo"),
        _ok("bealvees" in autores, "comentário do perfil analisado preservado"),
        _ok("torcedor1" not in autores, "comentário de publicação alheia não entra"),
    ]

    # Publicação sem dono identificado não pode ser descartada por engano:
    # nem todo formato do Instagram traz o autor no mesmo lugar.
    leitor2 = InstagramReader(Settings())
    leitor2.harvester.ingest({"items": [
        {"pk": "5", "code": "SemDono", "taken_at": _ts(1), "like_count": 10,
         "comment_count": 0, "media_type": 1, "caption": {"text": "sem autor no payload"}},
    ]})
    sem_dono = leitor2._posts_in_window(AGORA - timedelta(days=7), AGORA, "shopee_br")
    checagens.append(_ok(len(sem_dono) == 1, "publicação sem autor identificado é mantida"))

    falhas = checagens.count(False)
    print(f"\n{'='*58}\n{len(checagens) - falhas}/{len(checagens)} verificações passaram\n{'='*58}\n")
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
