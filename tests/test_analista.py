"""Valida o agente analista sem gastar chamada de API.

Este e o caminho que entra em uso assim que a ANTHROPIC_API_KEY e configurada,
entao ele precisa estar coberto — inclusive nos modos de falha. Um analista que
quebra o relatorio quando a API oscila e pior do que nao ter analista.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from sentiment.analysis.analyst import Analyst  # noqa: E402
from sentiment.config import Settings  # noqa: E402
from sentiment.models import Capture, Comment, Post, Profile  # noqa: E402
from sentiment.pipeline import analisar_captura  # noqa: E402


class ClienteFalso:
    """Imita o SDK da Anthropic devolvendo respostas pre-programadas."""

    def __init__(self, respostas: list):
        self.respostas = list(respostas)
        self.chamadas = 0
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.chamadas += 1
        resposta = self.respostas.pop(0) if self.respostas else '{"resultados":[]}'
        if isinstance(resposta, Exception):
            raise resposta
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=resposta)])


def _comentarios() -> list[Comment]:
    textos = [
        ("c1", "Motorista pontual e educado, servico impecavel!"),
        ("c2", "Paguei e ninguem apareceu. Isso e golpe, vou no Procon."),
        ("c3", "Quanto custa do aeroporto ate a Disney?"),
        ("c4", "Parabens pelo atendimento nota 1000... esperei 3 horas."),
    ]
    return [Comment(id=i, post_id="p1", author=f"user{n}", text=t, like_count=n)
            for n, (i, t) in enumerate(textos, start=1)]


def _captura(comentarios: list[Comment]) -> Capture:
    agora = datetime.now(timezone.utc)
    post = Post(id="p1", shortcode="Cabc", url="https://www.instagram.com/p/Cabc/",
                created_at=agora - timedelta(days=1), caption="Transfer para a Disney",
                like_count=300, comment_count=len(comentarios), comments=comentarios)
    return Capture(profile=Profile(username="marca", url="https://www.instagram.com/marca/"),
                   posts=[post], window_start=agora - timedelta(days=30), window_end=agora)


def _analista(respostas: list) -> Analyst:
    settings = Settings()
    settings.anthropic_api_key = "chave-de-teste"
    analista = Analyst(settings)
    analista.client = ClienteFalso(respostas)
    analista.engine = "claude-teste"
    return analista


def _ok(condicao: bool, texto: str) -> bool:
    print(f"  [{'OK ' if condicao else 'FALHA'}] {texto}")
    return condicao


def main() -> int:
    checagens: list[bool] = []
    comentarios = _comentarios()

    # 1. Resposta bem formada e aproveitada integralmente.
    print("\n1. Resposta completa do analista")
    resposta_boa = """```json
    {"resultados":[
     {"id":"c1","sentimento":"positivo","confianca":0.95,"intensidade":0.9,
      "temas":["pontualidade"],"adjetivos":["impecavel"],"riscos":[],
      "severidade_risco":0.0,"idioma":"pt","spam":false,"justificativa":"elogio direto"},
     {"id":"c2","sentimento":"negativo","confianca":0.98,"intensidade":1.0,
      "temas":["reserva e pagamento"],"adjetivos":["golpe"],
      "riscos":["fraude ou golpe","ameaca juridica"],"severidade_risco":1.0,
      "idioma":"pt","spam":false,"justificativa":"acusacao grave"},
     {"id":"c3","sentimento":"neutro","confianca":0.9,"intensidade":0.2,
      "temas":["preco e custo"],"adjetivos":[],"riscos":[],"severidade_risco":0.0,
      "idioma":"pt","spam":false,"justificativa":"pergunta de preco"},
     {"id":"c4","sentimento":"negativo","confianca":0.85,"intensidade":0.7,
      "temas":["atendimento"],"adjetivos":["demorado"],"riscos":[],
      "severidade_risco":0.3,"idioma":"pt","spam":false,"justificativa":"ironia"}
    ]}```"""
    analista = _analista([resposta_boa])
    insights = analista.classify(comentarios)
    checagens += [
        _ok(len(insights) == 4, f"os 4 comentarios voltaram classificados ({len(insights)})"),
        _ok(insights["c1"].sentiment == "positivo", "elogio lido como positivo"),
        _ok(insights["c2"].sentiment == "negativo", "acusacao lida como negativa"),
        _ok(insights["c3"].sentiment == "neutro", "pergunta de preco lida como NEUTRA"),
        _ok(insights["c4"].sentiment == "negativo", "IRONIA lida como negativa (o lexical erra aqui)"),
        _ok("fraude ou golpe" in insights["c2"].risks, "risco de fraude capturado"),
        _ok(insights["c1"].rationale != "", "justificativa preservada"),
    ]

    # 2. JSON invalido: nao pode derrubar o relatorio.
    print("\n2. Resposta corrompida da API")
    analista = _analista(["isso aqui nao e json {{{"])
    insights = analista.classify(comentarios)
    checagens += [
        _ok(len(insights) == 4, "todos os comentarios classificados mesmo assim"),
        _ok(all(i.rationale == "classificacao lexical (sem IA)" for i in insights.values()),
            "caiu para o motor lexical automaticamente"),
    ]

    # 3. Resposta parcial: faltam comentarios no retorno.
    print("\n3. Resposta parcial (a IA esqueceu dois)")
    parcial = '{"resultados":[{"id":"c1","sentimento":"positivo","confianca":0.9,"intensidade":0.8,"temas":["x"],"adjetivos":[],"riscos":[],"idioma":"pt","spam":false}]}'
    analista = _analista([parcial])
    insights = analista.classify(comentarios)
    checagens += [
        _ok(len(insights) == 4, "as lacunas foram preenchidas pelo lexical"),
        _ok(insights["c1"].confidence == 0.9, "o que a IA devolveu foi mantido"),
    ]

    # 4. A API cai no meio.
    print("\n4. A API lanca excecao")
    analista = _analista([RuntimeError("503 overloaded")])
    insights = analista.classify(comentarios)
    checagens += [
        _ok(len(insights) == 4, "relatorio continua completo"),
        _ok(any("Falha na chamada" in a for a in analista.warnings), "a falha foi registrada como aviso"),
    ]

    # 5. Sintese executiva.
    print("\n5. Sintese executiva")
    sintese = """{"resumo":"Reputacao pressionada por acusacao de golpe.",
     "leitura_do_periodo":"O periodo teve poucos comentarios porem carga alta de risco.",
     "insights_de_risco":[{"titulo":"Responder a acusacao publica","prioridade":"alta",
       "diagnostico":"Uma acusacao de golpe sem resposta.","acao":"Responder em 24h.","prazo":"imediato"}],
     "assuntos_potenciais":[{"assunto":"pontualidade","por_que_funciona":"elogio recorrente",
       "como_usar":"depoimento em video"}],
     "recomendacoes_gerais":["Criar rotina diaria de resposta"]}"""
    analista = _analista([resposta_boa, sintese])
    captura = _captura(comentarios)
    insights = analista.classify(comentarios)
    from sentiment.analysis.scoring import build_metrics

    metrics = build_metrics(captura, insights)
    narrativa = analista.synthesize(captura, metrics)
    checagens += [
        _ok("golpe" in narrativa["resumo"], "resumo veio do analista"),
        _ok(narrativa["insights_de_risco"][0]["prioridade"] == "alta", "plano de acao preservado"),
        _ok(len(narrativa["resumo"].splitlines()) <= 3, "resumo cabe em 3 linhas"),
    ]

    # 6. Sintese falha, metricas continuam.
    print("\n6. A sintese falha")
    analista = _analista([resposta_boa, "resposta truncad"])
    insights = analista.classify(comentarios)
    narrativa = analista.synthesize(captura, build_metrics(captura, insights))
    checagens += [
        _ok(bool(narrativa["resumo"]), "resumo alternativo gerado"),
        _ok(bool(narrativa["insights_de_risco"]), "plano de acao alternativo gerado"),
    ]

    # 7. Lote grande: precisa ser dividido em varias chamadas.
    print("\n7. Divisao em lotes")
    muitos = [Comment(id=f"m{i}", post_id="p1", author="u", text="otimo servico") for i in range(95)]
    analista = _analista(['{"resultados":[]}'] * 3)
    analista.classify(muitos)
    checagens.append(_ok(analista.client.chamadas == 3, f"95 comentarios viraram 3 chamadas ({analista.client.chamadas})"))

    falhas = checagens.count(False)
    print(f"\n{'='*58}\n{len(checagens) - falhas}/{len(checagens)} verificacoes passaram\n{'='*58}\n")
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
