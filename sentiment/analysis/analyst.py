"""Agente analista: classificacao em lote e sintese executiva via Claude.

Se a chave de API nao existir ou a chamada falhar, o sistema NAO quebra: cai
para o motor lexical e sinaliza isso no relatorio. Um painel que some porque a
API oscilou nao serve para operacao.
"""

from __future__ import annotations

import json
import re
from typing import Optional

from ..config import Settings
from ..models import Capture, Comment, CommentInsight, clamp, normalize_sentiment
from . import lexicon
from .prompts import CLASSIFICACAO, SINTESE

LOTE = 40  # comentarios por chamada: cabe no contexto e mantem a latencia baixa


def _extract_json(text: str) -> Optional[dict]:
    """Le o JSON da resposta mesmo se vier cercado de texto ou cercas markdown."""
    if not text:
        return None
    candidate = text.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", candidate, re.S)
    if fence:
        candidate = fence.group(1).strip()
    try:
        return json.loads(candidate)
    except ValueError:
        pass
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(candidate[start : end + 1])
        except ValueError:
            return None
    return None


class Analyst:
    """Classifica comentarios e escreve a interpretacao do periodo."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = None
        self.engine = "lexical-offline"
        self.warnings: list[str] = []
        if settings.analyst_enabled:
            try:
                from anthropic import Anthropic

                self.client = Anthropic(api_key=settings.anthropic_api_key)
                self.engine = settings.analyst_model
            except Exception as exc:  # pragma: no cover
                self.warnings.append(f"SDK da Anthropic indisponivel ({exc}); usando motor lexical.")
        else:
            self.warnings.append(
                "ANTHROPIC_API_KEY nao definida: analise feita pelo motor lexical offline."
            )

    # -- chamada base -----------------------------------------------------
    def _ask(self, system: str, user: str, max_tokens: int = 8000) -> Optional[dict]:
        if not self.client:
            return None
        try:
            response = self.client.messages.create(
                model=self.settings.analyst_model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            text = "".join(block.text for block in response.content if block.type == "text")
            return _extract_json(text)
        except Exception as exc:
            self.warnings.append(f"Falha na chamada ao analista: {exc}")
            return None

    # -- classificacao ----------------------------------------------------
    def classify(self, comments: list[Comment], on_progress=None) -> dict[str, CommentInsight]:
        insights: dict[str, CommentInsight] = {}
        if not comments:
            return insights

        lotes = [comments[i : i + LOTE] for i in range(0, len(comments), LOTE)]
        for indice, lote in enumerate(lotes, start=1):
            if on_progress:
                on_progress(indice, len(lotes))
            resultado = self._classify_batch(lote) if self.client else None
            if resultado is None:
                for comment in lote:  # rede de seguranca
                    insights[comment.id] = lexicon.analisar_texto(comment.id, comment.text)
            else:
                insights.update(resultado)
        return insights

    def _classify_batch(self, lote: list[Comment]) -> Optional[dict[str, CommentInsight]]:
        payload = [
            {"id": c.id, "texto": c.text[:600], "curtidas": c.like_count, "resposta": c.is_reply}
            for c in lote
        ]
        pedido = (
            "Classifique os comentarios abaixo, extraidos de publicacoes de um perfil "
            "no Instagram.\n\nCOMENTARIOS:\n"
            + json.dumps(payload, ensure_ascii=False, indent=1)
        )
        data = self._ask(CLASSIFICACAO, pedido)
        if not data or "resultados" not in data:
            return None

        por_id = {c.id: c for c in lote}
        insights: dict[str, CommentInsight] = {}
        for item in data.get("resultados", []):
            comment_id = str(item.get("id", ""))
            if comment_id not in por_id:
                continue
            insights[comment_id] = CommentInsight(
                comment_id=comment_id,
                sentiment=normalize_sentiment(item.get("sentimento")),
                confidence=clamp(item.get("confianca"), default=0.7),
                intensity=clamp(item.get("intensidade"), default=0.5),
                themes=[str(t).strip().lower() for t in (item.get("temas") or [])][:3],
                adjectives=[str(a).strip().lower() for a in (item.get("adjetivos") or [])][:5],
                risks=[str(r).strip().lower() for r in (item.get("riscos") or [])],
                risk_severity=clamp(item.get("severidade_risco"), default=0.0),
                language=str(item.get("idioma") or "pt")[:2],
                is_spam=bool(item.get("spam")),
                rationale=str(item.get("justificativa") or "")[:160],
            )

        # Nenhum comentario pode ficar sem classificacao.
        for comment in lote:
            if comment.id not in insights:
                insights[comment.id] = lexicon.analisar_texto(comment.id, comment.text)
        return insights

    # -- sintese ----------------------------------------------------------
    def synthesize(self, capture: Capture, metrics: dict) -> dict:
        base = self._fallback_narrative(capture, metrics)
        if not self.client:
            return base

        evidencias = {
            "perfil": capture.profile.username,
            "periodo": {
                "inicio": capture.window_start.date().isoformat(),
                "fim": capture.window_end.date().isoformat(),
            },
            "publicacoes_analisadas": metrics["publicacoes_analisadas"],
            "pontuacao": metrics["pontuacao"],
            "comentarios": metrics["comentarios"],
            "reacoes": {k: v for k, v in metrics["reacoes"].items() if k != "metodologia"},
            "pontos_positivos": [
                {"assunto": p["assunto"], "volume": p["volume"], "exemplos": [e["texto"] for e in p["exemplos"][:2]]}
                for p in metrics["pontos_positivos"][:6]
            ],
            "pontos_negativos": [
                {"assunto": p["assunto"], "volume": p["volume"], "exemplos": [e["texto"] for e in p["exemplos"][:2]]}
                for p in metrics["pontos_negativos"][:6]
            ],
            "pontos_neutros": [
                {"assunto": p["assunto"], "volume": p["volume"]} for p in metrics["pontos_neutros"][:6]
            ],
            "riscos": [
                {
                    "risco": r["risco"],
                    "volume": r["volume"],
                    "nivel": r["nivel"],
                    "evidencias": [e["texto"] for e in r["evidencias"][:3]],
                }
                for r in metrics["riscos"][:6]
            ],
            "ranking_temas": metrics["ranking_temas"],
        }
        pedido = (
            "Escreva a camada interpretativa do relatorio a partir destes dados ja "
            "apurados.\n\nDADOS:\n" + json.dumps(evidencias, ensure_ascii=False, indent=1)
        )
        data = self._ask(SINTESE, pedido, max_tokens=4000)
        if not data:
            return base

        return {
            "resumo": str(data.get("resumo") or base["resumo"]).strip(),
            "leitura_do_periodo": str(data.get("leitura_do_periodo") or base["leitura_do_periodo"]).strip(),
            "insights_de_risco": data.get("insights_de_risco") or base["insights_de_risco"],
            "assuntos_potenciais": data.get("assuntos_potenciais") or base["assuntos_potenciais"],
            "recomendacoes_gerais": data.get("recomendacoes_gerais") or base["recomendacoes_gerais"],
        }

    # -- narrativa sem IA -------------------------------------------------
    def _fallback_narrative(self, capture: Capture, metrics: dict) -> dict:
        pontuacao = metrics["pontuacao"]
        comentarios = metrics["comentarios"]
        positivos = metrics["pontos_positivos"]
        negativos = metrics["pontos_negativos"]
        riscos = metrics["riscos"]

        destaque_bom = positivos[0]["assunto"] if positivos else "nenhum tema dominante"
        destaque_ruim = negativos[0]["assunto"] if negativos else "nenhuma reclamacao recorrente"

        resumo = (
            f"Reputacao {pontuacao['rotulo']} ({pontuacao['nota']}/100) em "
            f"{metrics['publicacoes_analisadas']} publicacoes e {comentarios['total']} comentarios. "
            f"O que mais sustenta a marca e '{destaque_bom}'; o principal atrito e '{destaque_ruim}'. "
            + (
                f"Ha {len(riscos)} tema(s) de risco exigindo resposta."
                if riscos
                else "Nao ha tema de risco relevante no periodo."
            )
        )

        atendimento = metrics.get("atendimento_da_marca", {})
        cobertura = atendimento.get("cobertura_de_resposta_a_negativos", 100.0)
        insights = []
        if atendimento.get("comentarios_negativos") and cobertura < 60:
            insights.append(
                {
                    "titulo": "Fechar a lacuna de resposta publica",
                    "prioridade": "alta" if cobertura < 30 else "media",
                    "diagnostico": (
                        f"Apenas {cobertura}% dos {atendimento['comentarios_negativos']} comentarios "
                        "negativos receberam resposta. Reclamacao sem resposta fica como versao unica "
                        "para quem le depois."
                    ),
                    "acao": (
                        "Definir rotina diaria de varredura dos comentarios e responder toda reclamacao "
                        "em ate 24h, com reconhecimento, prazo e encaminhamento para canal privado."
                    ),
                    "prazo": "imediato",
                }
            )
        insights += [
            {
                "titulo": f"Conter '{r['risco']}'",
                "prioridade": "alta" if r["nivel"] == "alto" else "media",
                "diagnostico": f"{r['volume']} comentario(s) com esse teor no periodo.",
                "acao": (
                    "Responder publicamente com reconhecimento e prazo, levar o caso para canal "
                    "privado e registrar a tratativa."
                ),
                "prazo": "imediato" if r["nivel"] == "alto" else "curto prazo",
            }
            for r in riscos[:5]
        ]

        potenciais = [
            {
                "assunto": p["assunto"],
                "por_que_funciona": f"{p['volume']} manifestacoes positivas espontaneas.",
                "como_usar": "Transformar em prova social: depoimento, bastidor ou serie recorrente.",
            }
            for p in positivos[:5]
        ]

        return {
            "resumo": resumo,
            "leitura_do_periodo": (
                f"Foram lidas {metrics['publicacoes_analisadas']} publicacoes entre "
                f"{capture.window_start.date()} e {capture.window_end.date()}, somando "
                f"{comentarios['total']} comentarios e {metrics['reacoes']['total']} reacoes. "
                f"A distribuicao ficou em {comentarios['percentual_positivos']}% positivos, "
                f"{comentarios['percentual_neutros']}% neutros e "
                f"{comentarios['percentual_negativos']}% negativos."
            ),
            "insights_de_risco": insights,
            "assuntos_potenciais": potenciais,
            "recomendacoes_gerais": [
                "Responder todos os comentarios negativos em ate 24h.",
                f"Produzir conteudo explorando '{destaque_bom}', o tema de melhor retorno.",
                "Registrar as duvidas recorrentes e transformar em conteudo fixo no perfil.",
            ],
        }
