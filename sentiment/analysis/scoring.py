"""Metricas determinísticas do dashboard.

Tudo que e numero sai daqui — nao da IA. A IA interpreta e escreve; o calculo
fica reproduzivel, auditavel e identico entre duas execucoes sobre os mesmos
dados. Isso importa: um numero de reputacao que muda sozinho nao serve para
tomar decisao.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Iterable

from ..config import LIKE_AFFIRMATIVE_BASE, LIKE_CONTEXT_WEIGHT, MAX_RISK_PENALTY, SCORE_PRIOR_STRENGTH
from ..models import Capture, Comment, CommentInsight, Post, SENTIMENTS, pct
from .lexicon import SEVERIDADE, detectar_temas


def _shares(counts: dict[str, float]) -> dict[str, float]:
    total = sum(counts.values()) or 1.0
    return {k: v / total for k, v in counts.items()}


def comment_metrics(posts: list[Post], insights: dict[str, CommentInsight]) -> dict:
    """Volume de comentarios e distribuicao de sentimento."""
    counts = {s: 0 for s in SENTIMENTS}
    for post in posts:
        for comment in post.comments:
            insight = insights.get(comment.id)
            if insight:
                counts[insight.sentiment] += 1
    total = sum(counts.values())
    posts_count = len(posts) or 1
    return {
        "total": total,
        "media_por_publicacao": round(total / posts_count, 1),
        "positivos": counts["positivo"],
        "neutros": counts["neutro"],
        "negativos": counts["negativo"],
        "percentual_positivos": pct(counts["positivo"], total),
        "percentual_neutros": pct(counts["neutro"], total),
        "percentual_negativos": pct(counts["negativo"], total),
    }


def reaction_metrics(posts: list[Post], insights: dict[str, CommentInsight]) -> dict:
    """Volume de reacoes e a que sentimento elas pertencem.

    O Instagram nao rotula reacoes como o Facebook — nao existe "raiva" ou
    "amei" separados. Entao um analista serio precisa declarar como converte
    curtidas em sentimento, e e isso que este metodo faz:

      * curtida em COMENTARIO herda o sentimento do comentario curtido —
        curtir uma reclamacao e endossar a reclamacao;
      * curtida em PUBLICACAO e um ato deliberado de aprovacao, entao 70% dela
        conta como positiva por definicao; os 30% restantes seguem o clima dos
        comentarios daquela publicacao (contagio de contexto).
    """
    buckets = {s: 0.0 for s in SENTIMENTS}
    post_likes_total = 0
    comment_likes_total = 0

    for post in posts:
        local = {s: 0.0 for s in SENTIMENTS}
        for comment in post.comments:
            insight = insights.get(comment.id)
            if not insight:
                continue
            local[insight.sentiment] += 1
            if comment.like_count:
                buckets[insight.sentiment] += comment.like_count
                comment_likes_total += comment.like_count

        likes = max(0, post.like_count)
        post_likes_total += likes
        if not likes:
            continue
        if sum(local.values()):
            mix = _shares(local)
            buckets["positivo"] += likes * (LIKE_AFFIRMATIVE_BASE + LIKE_CONTEXT_WEIGHT * mix["positivo"])
            buckets["neutro"] += likes * LIKE_CONTEXT_WEIGHT * mix["neutro"]
            buckets["negativo"] += likes * LIKE_CONTEXT_WEIGHT * mix["negativo"]
        else:
            # Sem comentarios nao ha contexto: curtida vira aprovacao com reserva.
            buckets["positivo"] += likes * LIKE_AFFIRMATIVE_BASE
            buckets["neutro"] += likes * LIKE_CONTEXT_WEIGHT

    total = post_likes_total + comment_likes_total
    posts_count = len(posts) or 1
    return {
        "total": total,
        "media_por_publicacao": round(total / posts_count, 1),
        "curtidas_em_publicacoes": post_likes_total,
        "curtidas_em_comentarios": comment_likes_total,
        "percentual_boas": pct(buckets["positivo"], total),
        "percentual_neutras": pct(buckets["neutro"], total),
        "percentual_ruins": pct(buckets["negativo"], total),
        "metodologia": (
            "Curtida em comentário herda o sentimento do comentário curtido. "
            f"Curtida em publicação conta {int(LIKE_AFFIRMATIVE_BASE * 100)}% como aprovação "
            f"e {int(LIKE_CONTEXT_WEIGHT * 100)}% conforme o clima dos comentários daquela publicação."
        ),
    }


def _post_url_index(posts: list[Post]) -> dict[str, str]:
    index = {}
    for post in posts:
        for comment in post.comments:
            index[comment.id] = post.url
    return index


def topic_blocks(
    posts: list[Post], insights: dict[str, CommentInsight], comments_by_id: dict[str, Comment]
) -> dict[str, list[dict]]:
    """Assuntos e adjetivos recorrentes, separados por sentimento."""
    url_of = _post_url_index(posts)
    blocos: dict[str, list[dict]] = {}

    for sentimento in SENTIMENTS:
        volume: Counter = Counter()
        adjetivos: dict[str, Counter] = defaultdict(Counter)
        exemplos: dict[str, list[dict]] = defaultdict(list)
        urls: dict[str, Counter] = defaultdict(Counter)
        textos_vistos: dict[str, set[str]] = defaultdict(set)

        for insight in insights.values():
            if insight.sentiment != sentimento:
                continue
            comment = comments_by_id.get(insight.comment_id)
            # Cada comentario conta UMA vez, no seu tema principal. Contar em
            # todos os temas inflaria assuntos de cenario ("viagem") sobre os
            # atributos de servico que de fato explicam o sentimento — e faria
            # o percentual medir mencoes, nao comentarios.
            tema = (insight.themes or ["assunto geral"])[0]
            volume[tema] += 1
            for adjetivo in insight.adjectives:
                adjetivos[tema][adjetivo] += 1
            if comment:
                assinatura = " ".join(comment.text.lower().split())[:120]
                if len(exemplos[tema]) < 3 and assinatura not in textos_vistos[tema]:
                    textos_vistos[tema].add(assinatura)
                    exemplos[tema].append(
                        {
                            "texto": comment.text[:220],
                            "autor": comment.author,
                            "url_publicacao": url_of.get(comment.id, ""),
                        }
                    )
                urls[tema][url_of.get(comment.id, "")] += 1

        total = sum(volume.values()) or 1
        blocos[sentimento] = [
            {
                "assunto": tema,
                "volume": quantidade,
                "percentual": pct(quantidade, total),
                "adjetivos": [a for a, _ in adjetivos[tema].most_common(5)],
                "exemplos": exemplos[tema],
                "publicacoes": [u for u, _ in urls[tema].most_common(3) if u],
            }
            for tema, quantidade in volume.most_common(10)
        ]
    return blocos


def risk_blocks(
    posts: list[Post], insights: dict[str, CommentInsight], comments_by_id: dict[str, Comment]
) -> list[dict]:
    """Temas de risco, volume, gravidade e onde eles se concentram."""
    url_of = _post_url_index(posts)
    volume: Counter = Counter()
    evidencias: dict[str, list[dict]] = defaultdict(list)
    urls: dict[str, Counter] = defaultdict(Counter)
    severidade: dict[str, float] = {}
    # Duas pessoas podem escrever quase a mesma frase; mostrar a citacao
    # repetida da falsa impressao de volume. Guardamos so as distintas.
    vistas: dict[str, set[str]] = defaultdict(set)

    for insight in insights.values():
        for risco in insight.risks or []:
            volume[risco] += 1
            # A gravidade e do TIPO de risco. Um comentario que acusa golpe e
            # pede reembolso nao torna "pedido de reembolso" tao grave quanto
            # "fraude" — cada rotulo mantem a propria escala.
            canonica = SEVERIDADE.get(risco)
            if canonica is None:  # rotulo novo, vindo do analista de IA
                canonica = insight.risk_severity or 0.5
            severidade[risco] = max(severidade.get(risco, 0.0), canonica)
            comment = comments_by_id.get(insight.comment_id)
            if comment:
                urls[risco][url_of.get(comment.id, "")] += 1
                assinatura = " ".join(comment.text.lower().split())[:120]
                if len(evidencias[risco]) < 4 and assinatura not in vistas[risco]:
                    vistas[risco].add(assinatura)
                    evidencias[risco].append(
                        {
                            "texto": comment.text[:240],
                            "autor": comment.author,
                            "url_autor": comment.author_url,
                            "url_publicacao": url_of.get(comment.id, ""),
                        }
                    )

    resultado = []
    for risco, quantidade in volume.most_common():
        grave = severidade.get(risco, 0.5)
        resultado.append(
            {
                "risco": risco,
                "volume": quantidade,
                "severidade": round(grave, 2),
                "nivel": "alto" if grave >= 0.8 else "medio" if grave >= 0.5 else "baixo",
                "prioridade": round(quantidade * grave, 2),
                "evidencias": evidencias[risco],
                "publicacoes": [u for u, _ in urls[risco].most_common(3) if u],
            }
        )
    resultado.sort(key=lambda r: -r["prioridade"])
    return resultado


def hotspot_posts(posts: list[Post], insights: dict[str, CommentInsight], limit: int = 5) -> list[dict]:
    """Publicacoes onde negatividade e risco mais se concentraram."""
    linhas = []
    for post in posts:
        negativos = 0
        risco = 0.0
        for comment in post.comments:
            insight = insights.get(comment.id)
            if not insight:
                continue
            if insight.sentiment == "negativo":
                negativos += 1
            risco += insight.risk_severity or 0.0
        if negativos or risco:
            linhas.append(
                {
                    "url": post.url,
                    "data": post.created_at.date().isoformat() if post.created_at else "",
                    "legenda": (post.caption or "")[:120],
                    "comentarios_negativos": negativos,
                    "carga_de_risco": round(risco, 2),
                    "total_comentarios": len(post.comments),
                }
            )
    linhas.sort(key=lambda r: (-r["carga_de_risco"], -r["comentarios_negativos"]))
    return linhas[:limit]


def people_blocks(
    posts: list[Post], insights: dict[str, CommentInsight], comments_by_id: dict[str, Comment], owner: str, limit: int = 5
) -> dict[str, list[dict]]:
    """Fas e detratores — quem sustenta e quem ataca a marca."""
    owner = (owner or "").lower().lstrip("@")
    perfis: dict[str, dict] = defaultdict(
        lambda: {"positivos": 0, "negativos": 0, "neutros": 0, "peso": 0.0, "curtidas": 0, "citacoes": []}
    )

    for insight in insights.values():
        comment = comments_by_id.get(insight.comment_id)
        if not comment or not comment.author:
            continue
        if comment.author.lower() == owner:  # a propria marca respondendo
            continue
        if insight.is_spam:
            continue
        dados = perfis[comment.author]
        dados[insight.sentiment + "s"] += 1
        dados["curtidas"] += comment.like_count
        sinal = 1 if insight.sentiment == "positivo" else -1 if insight.sentiment == "negativo" else 0
        dados["peso"] += sinal * insight.weight
        if sinal and len(dados["citacoes"]) < 3:
            dados["citacoes"].append(comment.text[:200])

    def montar(usuario: str, dados: dict) -> dict:
        return {
            "usuario": usuario,
            "url_perfil": f"https://www.instagram.com/{usuario}/",
            "comentarios_positivos": dados["positivos"],
            "comentarios_negativos": dados["negativos"],
            "comentarios_neutros": dados["neutros"],
            "curtidas_recebidas": dados["curtidas"],
            "intensidade": round(abs(dados["peso"]), 2),
            "citacoes": dados["citacoes"],
        }

    fas = [
        montar(u, d)
        for u, d in sorted(
            perfis.items(), key=lambda kv: (-kv[1]["positivos"], -kv[1]["peso"], -kv[1]["curtidas"])
        )
        if d["positivos"] > 0 and d["positivos"] > d["negativos"]
    ][:limit]

    detratores = [
        montar(u, d)
        for u, d in sorted(
            perfis.items(), key=lambda kv: (-kv[1]["negativos"], kv[1]["peso"], -kv[1]["curtidas"])
        )
        if d["negativos"] > 0 and d["negativos"] >= d["positivos"]
    ][:limit]

    return {"fas": fas, "detratores": detratores}


def post_theme_ranking(posts: list[Post], insights: dict[str, CommentInsight],
                       limit: int = 5, segmento: str = "generico") -> list[dict]:
    """Rank dos temas das PUBLICACOES, com o sentimento que cada um provocou."""
    temas: dict[str, dict] = defaultdict(
        lambda: {"publicacoes": 0, "positivo": 0, "neutro": 0, "negativo": 0, "urls": [], "reacoes": 0}
    )
    for post in posts:
        # Uma publicacao pertence ao seu tema principal, para o rank somar
        # exatamente o numero de publicacoes lidas.
        tema = detectar_temas(post.caption or "", segmento)[0]
        dados = temas[tema]
        dados["publicacoes"] += 1
        dados["reacoes"] += post.like_count
        if len(dados["urls"]) < 3:
            dados["urls"].append(post.url)
        for comment in post.comments:
            insight = insights.get(comment.id)
            if insight:
                dados[insight.sentiment] += 1

    ranking = []
    for tema, dados in temas.items():
        total = dados["positivo"] + dados["neutro"] + dados["negativo"]
        ranking.append(
            {
                "tema": tema,
                "publicacoes": dados["publicacoes"],
                "comentarios": total,
                "reacoes": dados["reacoes"],
                "percentual_positivos": pct(dados["positivo"], total),
                "percentual_neutros": pct(dados["neutro"], total),
                "percentual_negativos": pct(dados["negativo"], total),
                "publicacoes_exemplo": dados["urls"],
            }
        )
    ranking.sort(key=lambda t: (-t["publicacoes"], -t["comentarios"]))
    for posicao, item in enumerate(ranking[:limit], start=1):
        item["posicao"] = posicao
    return ranking[:limit]


def overall_score(
    insights: Iterable[CommentInsight], reactions: dict, risks: list[dict]
) -> dict:
    """Nota 0-100 da reputacao no periodo.

    Tres camadas: (1) balanco ponderado de sentimento dos comentarios, (2)
    encolhimento bayesiano para 50 quando ha pouca amostra — 4 comentarios nao
    autorizam dizer "reputacao 95" — e (3) desconto por risco reputacional, que
    e assimetrico de proposito: uma acusacao de golpe pesa mais do que dez
    elogios compensam.
    """
    insights = list(insights)
    peso_pos = sum(i.weight for i in insights if i.sentiment == "positivo" and not i.is_spam)
    peso_neg = sum(i.weight for i in insights if i.sentiment == "negativo" and not i.is_spam)
    peso_neu = sum(i.weight for i in insights if i.sentiment == "neutro" and not i.is_spam)

    base_total = peso_pos + peso_neg + (peso_neu * 0.35)
    balanco = (peso_pos - peso_neg) / base_total if base_total else 0.0
    bruto_comentarios = 50 + 50 * balanco

    # As reacoes entram com peso menor: sao sinal raso, porem de volume alto.
    bruto_reacoes = 50 + 0.5 * (reactions.get("percentual_boas", 0.0) - reactions.get("percentual_ruins", 0.0))
    bruto = 0.75 * bruto_comentarios + 0.25 * bruto_reacoes

    amostra = len([i for i in insights if not i.is_spam])
    confianca = amostra / (amostra + SCORE_PRIOR_STRENGTH) if amostra else 0.0
    ajustado = 50 + (bruto - 50) * confianca

    penalidade = min(MAX_RISK_PENALTY, sum(r["volume"] * r["severidade"] for r in risks) * 0.6)
    nota = max(0.0, min(100.0, ajustado - penalidade))

    if nota >= 85:
        rotulo = "excelente"
    elif nota >= 70:
        rotulo = "boa"
    elif nota >= 55:
        rotulo = "estável"
    elif nota >= 40:
        rotulo = "em alerta"
    else:
        rotulo = "crítica"

    return {
        "nota": round(nota),
        "rotulo": rotulo,
        "confianca_amostral": round(confianca, 2),
        "amostra": amostra,
        "penalidade_de_risco": round(penalidade, 1),
        "componente_comentarios": round(bruto_comentarios, 1),
        "componente_reacoes": round(bruto_reacoes, 1),
    }


def brand_metrics(capture: Capture, insights: dict[str, CommentInsight]) -> dict:
    """Quanto a marca respondeu — e se respondeu a quem reclamou.

    Cobertura de resposta a comentario negativo e um dos indicadores mais
    preditivos de recuperacao de reputacao: quem reclama e recebe resposta
    publica costuma reduzir o tom, e quem le a thread ve a marca presente.
    """
    dono = (capture.profile.username or "").lower()
    respostas = [c for c in capture.all_comments if c.author.lower() == dono]
    respondidos = {c.parent_id for c in respostas if c.parent_id}

    negativos = [
        c for c in capture.all_comments
        if c.author.lower() != dono and (insights.get(c.id) or CommentInsight(c.id)).sentiment == "negativo"
    ]
    negativos_respondidos = [c for c in negativos if c.id in respondidos]

    return {
        "respostas_da_marca": len(respostas),
        "publicacoes_com_resposta": len({c.post_id for c in respostas}),
        "comentarios_negativos": len(negativos),
        "negativos_respondidos": len(negativos_respondidos),
        "cobertura_de_resposta_a_negativos": pct(len(negativos_respondidos), len(negativos)),
    }


def build_metrics(capture: Capture, insights: dict[str, CommentInsight],
                  segmento: str = "generico") -> dict:
    """Reune todos os blocos numericos do dashboard.

    As respostas da propria marca sao retiradas do balanco: elas nao sao
    sentimento do publico, e mante-las inflaria o volume neutro e positivo.
    Elas voltam adiante, como indicador de atendimento.
    """
    dono = (capture.profile.username or "").lower()
    marca = {c.id for c in capture.all_comments if c.author.lower() == dono}
    atendimento = brand_metrics(capture, insights)

    posts = [
        Post(
            id=p.id, shortcode=p.shortcode, url=p.url, created_at=p.created_at,
            caption=p.caption, like_count=p.like_count, comment_count=p.comment_count,
            media_type=p.media_type, is_pinned=p.is_pinned,
            comments=[c for c in p.comments if c.id not in marca],
        )
        for p in capture.posts
    ]
    insights = {k: v for k, v in insights.items() if k not in marca}
    comments_by_id = {c.id: c for c in capture.all_comments if c.id not in marca}

    comentarios = comment_metrics(posts, insights)
    reacoes = reaction_metrics(posts, insights)
    riscos = risk_blocks(posts, insights, comments_by_id)
    blocos = topic_blocks(posts, insights, comments_by_id)
    pessoas = people_blocks(posts, insights, comments_by_id, capture.profile.username)

    return {
        "atendimento_da_marca": atendimento,
        "pontuacao": overall_score(insights.values(), reacoes, riscos),
        "comentarios": comentarios,
        "reacoes": reacoes,
        "pontos_positivos": blocos["positivo"],
        "pontos_negativos": blocos["negativo"],
        "pontos_neutros": blocos["neutro"],
        "riscos": riscos,
        "publicacoes_criticas": hotspot_posts(posts, insights),
        "fas": pessoas["fas"],
        "detratores": pessoas["detratores"],
        "ranking_temas": post_theme_ranking(posts, insights, segmento=segmento),
        "publicacoes_analisadas": len(posts),
    }
