"""Uso por linha de comando.

    python -m sentiment.cli --url https://instagram.com/perfil --dias 30
    python -m sentiment.cli --captura runs/captura.json      # reanalisa sem navegar
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from .config import ROOT, Settings, preparar_plataforma
from .pipeline import (
    analisar_captura,
    carregar_captura,
    periodo_relativo,
    rodar,
    salvar_relatorio,
)


preparar_plataforma()

def _progresso(etapa: str, mensagem: str, percentual: int) -> None:
    barra = "█" * (percentual // 4) + "·" * (25 - percentual // 4)
    sys.stderr.write(f"\r[{barra}] {percentual:3d}% {mensagem[:60]:<60}")
    sys.stderr.flush()
    if percentual >= 100:
        sys.stderr.write("\n")


def _imprimir(relatorio: dict) -> None:
    p = relatorio["pontuacao"]
    c = relatorio["comentarios"]
    x = relatorio["reacoes"]
    print("\n" + "=" * 74)
    print(f"  @{relatorio['perfil']['username']}  |  "
          f"{relatorio['periodo']['inicio']} a {relatorio['periodo']['fim']}")
    print("=" * 74)
    print(f"\n  NOTA GERAL: {p['nota']}/100  ({p['rotulo']})")
    print(f"  {relatorio['resumo']}\n")
    print(f"  Publicacoes lidas .... {relatorio['publicacoes_analisadas']}")
    print(f"  Comentarios .......... {c['total']} (media {c['media_por_publicacao']}/publicacao)")
    print(f"     positivos {c['percentual_positivos']}% | neutros {c['percentual_neutros']}% "
          f"| negativos {c['percentual_negativos']}%")
    print(f"  Reacoes .............. {x['total']} (media {x['media_por_publicacao']}/publicacao)")
    print(f"     boas {x['percentual_boas']}% | neutras {x['percentual_neutras']}% "
          f"| ruins {x['percentual_ruins']}%")

    def secao(titulo: str, itens: list, campo: str = "assunto") -> None:
        print(f"\n  {titulo}")
        if not itens:
            print("     (nada relevante)")
        for item in itens[:5]:
            print(f"     - {item[campo]}: {item['volume']}")

    secao("PONTOS POSITIVOS", relatorio["pontos_positivos"])
    secao("PONTOS NEGATIVOS", relatorio["pontos_negativos"])
    secao("PONTOS NEUTROS", relatorio["pontos_neutros"])
    secao("RISCOS", relatorio["riscos"], campo="risco")

    print("\n  FAS")
    for f in relatorio["fas"] or []:
        print(f"     - @{f['usuario']} ({f['comentarios_positivos']} positivos) {f['url_perfil']}")
    if not relatorio["fas"]:
        print("     (nenhum)")

    print("\n  DETRATORES")
    for d in relatorio["detratores"] or []:
        print(f"     - @{d['usuario']} ({d['comentarios_negativos']} negativos) {d['url_perfil']}")
    if not relatorio["detratores"]:
        print("     (nenhum)")

    print("\n  RANKING DE TEMAS DAS PUBLICACOES")
    for t in relatorio["ranking_temas"]:
        print(f"     {t['posicao']}. {t['tema']} — {t['publicacoes']} pub. | "
              f"pos {t['percentual_positivos']}% neu {t['percentual_neutros']}% neg {t['percentual_negativos']}%")
    print("=" * 74 + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analise de sentimento de perfis do Instagram")
    parser.add_argument("--url", help="URL do perfil")
    parser.add_argument("--inicio", help="Data inicial AAAA-MM-DD")
    parser.add_argument("--fim", help="Data final AAAA-MM-DD")
    parser.add_argument("--dias", type=int, help="Atalho: ultimos N dias")
    parser.add_argument("--captura", help="Analisa um arquivo de captura ja existente")
    parser.add_argument("--demo", action="store_true",
                        help="Roda com dados simulados, sem login e sem API — so para ver o painel")
    parser.add_argument("--json", action="store_true", help="Imprime o relatorio em JSON")
    parser.add_argument("--ritmo", choices=["calmo", "normal", "apressado"])
    args = parser.parse_args(argv)

    settings = Settings()
    if args.ritmo:
        settings.pace = args.ritmo

    if args.demo:
        from .models import Capture
        import sys as _sys
        _sys.path.insert(0, str(ROOT / "tests" / "mock_instagram"))
        from data import gerar  # type: ignore

        print("Modo demonstracao: dados simulados, nenhum acesso ao Instagram.\n", file=sys.stderr)
        capture = Capture.from_dict(gerar())
        relatorio = analisar_captura(capture, settings, progress=_progresso)
    elif args.captura:
        capture = carregar_captura(args.captura)
        relatorio = analisar_captura(capture, settings, progress=_progresso)
    else:
        if not args.url:
            parser.error("informe --url, --captura ou --demo")
        if args.dias:
            inicio, fim = periodo_relativo(args.dias)
            inicio_s, fim_s = inicio.date().isoformat(), fim.date().isoformat()
        elif args.inicio and args.fim:
            inicio_s, fim_s = args.inicio, args.fim
        else:
            parser.error("informe --dias ou --inicio e --fim")
        relatorio = rodar(args.url, inicio_s, fim_s, settings, progress=_progresso)

    destino = salvar_relatorio(relatorio, settings)
    if args.json:
        # stdout fica so com o JSON, para poder ser encadeado com jq e afins.
        print(json.dumps(relatorio, ensure_ascii=False, indent=2))
        print(f"Relatorio salvo em: {destino}", file=sys.stderr)
    else:
        _imprimir(relatorio)
        print(f"Relatorio salvo em: {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
