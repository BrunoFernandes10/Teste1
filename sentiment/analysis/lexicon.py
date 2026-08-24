"""Motor lexical multilingue (pt/en/es).

Serve a dois propositos: funcionar sozinho quando nao ha chave de API — o
sistema nunca fica sem resposta — e servir de rede de seguranca quando o
analista de IA falha em algum lote. Trata negacao, intensificadores, emojis,
pontuacao enfatica e caixa alta, que sao os sinais que mais enganam contadores
de palavras ingenuos.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Iterable

from ..models import CommentInsight

# --- pesos de palavra (1.0 = forte, 0.6 = moderado) -------------------------
POSITIVAS = {
    # portugues
    "otimo": 1.0, "excelente": 1.0, "maravilhoso": 1.0, "perfeito": 1.0, "amei": 1.0,
    "adorei": 1.0, "incrivel": 1.0, "sensacional": 1.0, "impecavel": 1.0, "top": 0.8,
    "bom": 0.6, "boa": 0.6, "legal": 0.6, "gostei": 0.7, "recomendo": 0.9,
    "parabens": 0.8, "obrigado": 0.6, "obrigada": 0.6, "atencioso": 0.8, "atenciosa": 0.8,
    "pontual": 0.8, "rapido": 0.6, "confiavel": 0.9, "seguro": 0.7, "educado": 0.8,
    "simpatico": 0.8, "eficiente": 0.8, "capricho": 0.7, "show": 0.7, "lindo": 0.7,
    "linda": 0.7, "sucesso": 0.7, "melhor": 0.8, "vale": 0.5, "salvou": 0.8,
    "nota": 0.4, "profissional": 0.7, "limpo": 0.6, "confortavel": 0.7, "pratico": 0.6,
    "surpreendeu": 0.7, "gentil": 0.8, "prestativo": 0.8, "abencoado": 0.6,
    # vida publica: elogio a mandato e a conduta
    "guerreira": 0.8, "guerreiro": 0.8, "trabalhadora": 0.8, "trabalhador": 0.8,
    "honesta": 0.9, "honesto": 0.9, "competente": 0.8, "corajosa": 0.8, "corajoso": 0.8,
    "presente": 0.6, "atuante": 0.7, "digna": 0.8, "digno": 0.8, "orgulho": 0.8,
    "apoio": 0.7, "forca": 0.5, "merece": 0.6,
    # ingles
    "great": 0.9, "amazing": 1.0, "excellent": 1.0, "perfect": 1.0, "love": 0.9,
    "loved": 0.9, "awesome": 0.9, "good": 0.6, "nice": 0.6, "best": 0.8,
    "recommend": 0.9, "reliable": 0.9, "friendly": 0.8, "clean": 0.6, "helpful": 0.8,
    "professional": 0.7, "smooth": 0.7, "comfortable": 0.7, "thanks": 0.5, "thank": 0.5,
    "wonderful": 1.0, "outstanding": 1.0, "punctual": 0.8, "safe": 0.7,
    # espanhol
    "excelente_es": 1.0, "buenisimo": 0.9, "genial": 0.9, "gracias": 0.5,
    "recomiendo": 0.9, "puntual": 0.8, "amable": 0.8, "comodo": 0.7, "rapido_es": 0.6,
}

NEGATIVAS = {
    # portugues
    "pessimo": 1.0, "horrivel": 1.0, "terrivel": 1.0, "ruim": 0.8, "odiei": 1.0,
    "detestei": 1.0, "decepcionado": 0.9, "decepcionada": 0.9, "decepcao": 0.9,
    "atrasou": 0.8, "atraso": 0.8, "atrasado": 0.8, "sumiu": 0.8, "cancelou": 0.7,
    "cancelamento": 0.6, "golpe": 1.0, "fraude": 1.0, "estelionato": 1.0,
    "roubo": 1.0, "roubaram": 1.0, "ladrao": 1.0, "enganou": 1.0, "enganacao": 1.0,
    "mentira": 0.9, "mentiroso": 0.9, "picareta": 1.0, "caloteiro": 1.0,
    "descaso": 0.9, "despreparado": 0.8, "grosseiro": 0.9, "mal": 0.6, "sujo": 0.8,
    "caro": 0.6, "abusivo": 0.9, "reembolso": 0.7, "estorno": 0.7, "prejuizo": 0.8,
    "processo": 0.8, "procon": 1.0, "advogado": 0.7, "denuncia": 1.0, "denunciar": 1.0,
    "perigoso": 0.9, "inseguro": 0.9, "acidente": 0.9, "quebrado": 0.7, "falha": 0.7,
    "problema": 0.6, "reclamacao": 0.7, "vergonha": 0.9, "absurdo": 0.9, "lixo": 1.0,
    "nunca": 0.5, "demorou": 0.7, "demora": 0.7, "ignorou": 0.8, "abandonou": 0.9,
    "sumiram": 0.8, "cuidado": 0.7, "evitem": 0.9, "furada": 0.9,
    # vida publica: cobranca e descredito
    "cade": 0.6, "farsa": 0.9, "demagogia": 0.9, "demagogo": 0.9, "hipocrita": 0.9,
    "incompetente": 0.9, "omissa": 0.8, "omisso": 0.8, "sumida": 0.7, "sumido": 0.7,
    "esqueceu": 0.7, "abandonada": 0.8, "abandonado": 0.8, "traiu": 0.9,
    "vagabunda": 1.0, "vagabundo": 1.0, "corrupta": 1.0, "corrupto": 1.0,
    # ingles
    "terrible": 1.0, "awful": 1.0, "horrible": 1.0, "bad": 0.8, "worst": 1.0,
    "scam": 1.0, "fraud": 1.0, "stole": 1.0, "rude": 0.9, "late": 0.7,
    "delay": 0.7, "delayed": 0.8, "refund": 0.7, "cancelled": 0.7, "canceled": 0.7,
    "dirty": 0.8, "unsafe": 0.9, "dangerous": 0.9, "disappointed": 0.9, "expensive": 0.6,
    "never": 0.4, "avoid": 0.9, "lawsuit": 0.9, "complaint": 0.7, "unprofessional": 0.9,
    # espanhol
    "pesimo": 1.0, "horrible_es": 1.0, "estafa": 1.0, "tarde": 0.6, "sucio": 0.8,
    "grosero": 0.9, "reembolso_es": 0.7, "peligroso": 0.9,
}

INTENSIFICADORES = {
    "muito": 1.35, "super": 1.4, "extremamente": 1.6, "demais": 1.35, "bastante": 1.2,
    "totalmente": 1.4, "completamente": 1.5, "absurdamente": 1.6, "mega": 1.35,
    "very": 1.35, "really": 1.3, "extremely": 1.6, "so": 1.2, "totally": 1.4,
    "absolutely": 1.5, "muy": 1.35, "demasiado": 1.4,
}

# A negacao e especifica de cada idioma: em portugues "no" e contracao de
# "em o" ("vou no Procon"), nao negacao. Misturar as listas inverte o sinal de
# frases graves — por isso escolhemos o conjunto depois de detectar o idioma.
NEGADORES_PT = {"nao", "nunca", "jamais", "nenhum", "nenhuma", "sem", "tampouco", "nada"}
NEGADORES_EN = {"not", "no", "never", "dont", "didnt", "doesnt", "isnt", "wasnt", "cant", "without", "nothing"}
NEGADORES_ES = {"no", "nunca", "jamas", "ningun", "ninguna", "sin", "nada", "tampoco"}
NEGADORES_POR_IDIOMA = {"pt": NEGADORES_PT, "en": NEGADORES_EN, "es": NEGADORES_ES}

# Conjuncoes adversativas: o que vem DEPOIS do "mas" e o que a pessoa
# realmente quis dizer ("nao foi ruim, mas esperava mais").
ADVERSATIVAS = {"mas", "porem", "contudo", "entretanto", "todavia", "so_que", "but", "however", "although", "pero", "aunque"}

EMOJIS_POSITIVOS = "❤️💚💙💜🧡💛🤍😍🥰😊😁😄😃🙏👏👍🥳🤩💯✨🔥😻💖💗🫶😘☺️🤗"
EMOJIS_NEGATIVOS = "😡🤬😠👎💔😤😖😩😢😭🤮🤢😒🙄😑⚠️🚨❌😞😔"

# --- riscos ----------------------------------------------------------------
# Risco nao e o mesmo que negatividade: e o que pode virar crise, processo,
# dano fisico ou perda financeira. A lista tambem muda com o segmento — em
# politica, ameaca e desinformacao pesam mais que qualquer reclamacao.

RISCOS_COMUNS = {
    "fraude ou golpe": [
        "golpe", "fraude", "estelionato", "picareta", "caloteiro", "roubo", "roubaram",
        "enganou", "scam", "estafa", "ladrao", "mentiroso", "propaganda enganosa",
    ],
    "ameaça jurídica": ["procon", "advogado", "processo", "processar", "denuncia", "denunciar", "justica", "juizado", "ministerio publico"],
    "atendimento hostil": ["grosseiro", "mal educado", "rude", "destratou", "ignorou", "descaso", "humilhou"],
    "concorrente ou spam": ["segue de volta", "compre seguidores", "ganhe dinheiro", "clique no link", "promotion", "whatsapp +"],
}

RISCOS_POR_SEGMENTO = {
    "servicos": {
        "pedido de reembolso": ["reembolso", "estorno", "devolver o dinheiro", "chargeback", "meu dinheiro"],
        "segurança física": ["perigoso", "inseguro", "acidente", "risco de vida", "quase bati", "peligroso"],
        "falha operacional grave": ["sumiu", "abandonou", "nao apareceu", "me deixou", "cancelou em cima", "ficamos sem"],
        "higiene e conservação": ["sujo", "fedido", "quebrado", "mal cuidado"],
        "preço abusivo": ["abusivo", "caro demais", "cobranca indevida", "cobrou a mais"],
    },
    "ecommerce": {
        "pedido de reembolso": ["reembolso", "estorno", "devolver o dinheiro", "chargeback", "meu dinheiro", "ressarcimento"],
        "produto não entregue": ["nao chegou", "nunca chegou", "extraviado", "sumiu o pedido", "nao recebi"],
        "produto falsificado": ["falsificado", "replica", "pirata", "original nao e", "imitacao"],
        "conta bloqueada": ["conta banida", "banimento", "bloquearam minha conta", "banindo as contas", "conta suspensa"],
        "cobrança indevida": ["cobranca indevida", "cobrou a mais", "cobrado duas vezes",
                              "cobraram duas vezes", "cobranca duplicada", "debito indevido"],
    },
    "politica": {
        "ameaça ou violência": ["vou te pegar", "sabemos onde", "morre", "morra", "bala", "te matar", "acabar com voce", "ameaca"],
        "acusação de corrupção": ["corrupto", "corrupcao", "propina", "desvio", "roubou", "superfaturamento", "rachadinha", "caixa dois", "lavagem"],
        "desinformação": ["fake news", "mentira", "montagem", "falso", "inventaram", "distorceram", "fora de contexto"],
        "discurso de ódio": ["racista", "homofobico", "misogino", "preconceito", "xenofobo", "nazista"],
        "processo ou investigação": ["indiciado", "investigado", "inquerito", "cassacao", "improbidade", "tce", "condenado"],
        "promessa não cumprida": ["prometeu e nao", "nao cumpriu", "cade a obra", "so promessa", "esqueceu de nos", "so aparece em eleicao"],
        "ataque coordenado": ["robo", "perfil fake", "milicia digital", "ataque organizado", "disparo em massa"],
    },
    "generico": {},
}

SEVERIDADE = {
    # comuns
    "fraude ou golpe": 1.0, "ameaça jurídica": 0.95,
    "atendimento hostil": 0.65, "concorrente ou spam": 0.2,
    # servicos
    "segurança física": 1.0, "pedido de reembolso": 0.7,
    "falha operacional grave": 0.8, "higiene e conservação": 0.55, "preço abusivo": 0.5,
    # ecommerce
    "produto não entregue": 0.85, "produto falsificado": 0.9,
    "conta bloqueada": 0.85, "cobrança indevida": 0.8,
    # politica
    "ameaça ou violência": 1.0, "acusação de corrupção": 0.95,
    "desinformação": 0.8, "discurso de ódio": 0.9,
    "processo ou investigação": 0.85, "promessa não cumprida": 0.5,
    "ataque coordenado": 0.7,
}

RISCOS = {**RISCOS_COMUNS, **RISCOS_POR_SEGMENTO["servicos"]}  # padrao historico

# --- temas -----------------------------------------------------------------
# O vocabulario decide o que o laudo consegue nomear. Uma lista pensada para
# transporte nao enxerga "estorno" nem "saneamento": tudo cai na cesta generica
# e a analise perde utilidade. Por isso ha um nucleo comum e um complemento por
# segmento, escolhido na tela inicial.

TEMAS_COMUNS = {
    "atendimento": ["atendimento", "atendeu", "suporte", "equipe", "funcionario", "service", "staff", "resposta"],
    "preço e custo": ["preco", "caro", "barato", "valor", "custo", "price", "expensive", "vale a pena", "promocao"],
    "qualidade": ["qualidade", "servico", "experiencia", "capricho", "bem feito", "malfeito"],
    "comunicação e informação": ["informacao", "respondeu", "duvida", "contato", "whatsapp", "mensagem", "avisou", "explicou"],
    "recomendação": ["recomendo", "indico", "recommend", "voltarei", "de novo", "sempre uso", "melhor"],
    "dúvida ou pergunta": ["quanto", "como faco", "tem vaga", "voces atendem", "qual o valor", "how much", "quando", "onde"],
}

TEMAS_POR_SEGMENTO = {
    "servicos": {
        "pontualidade": ["pontual", "horario", "atrasou", "atraso", "esperei", "on time", "late", "chegou na hora"],
        "conforto e estrutura": ["confortavel", "conforto", "espaco", "limpo", "carro", "veiculo", "van", "assento", "clean"],
        "segurança": ["seguro", "seguranca", "safe", "confianca", "tranquilo", "perigo"],
        "motorista e condução": ["motorista", "driver", "conducao", "dirigiu", "guia", "condutor"],
        "reserva e pagamento": ["reserva", "agendamento", "pagamento", "pagar", "cartao", "booking", "paguei", "cobranca"],
        "viagem e passeio": ["disney", "parque", "viagem", "passeio", "orlando", "aeroporto", "trip", "hotel", "outlet"],
    },
    "ecommerce": {
        "entrega e prazo": ["entrega", "entregou", "chegou", "prazo", "atrasado", "atraso", "correio", "transportadora", "rastreio", "rastreamento", "extraviado"],
        "frete": ["frete", "frete gratis", "custo de envio", "envio"],
        "estorno e reembolso": ["estorno", "reembolso", "devolucao", "devolver", "cancelamento", "meu dinheiro", "ressarcimento"],
        "produto e qualidade": ["produto", "chegou quebrado", "danificado", "defeito", "original", "falsificado", "replica", "veio errado"],
        "vendedor e loja": ["vendedor", "loja", "seller", "anuncio", "descricao do produto"],
        "aplicativo e site": ["aplicativo", "app", "site", "carrinho", "checkout", "bug", "travando", "conta banida", "banimento"],
        "cupom e promoção": ["cupom", "desconto", "promocao", "oferta", "black friday", "frete gratis"],
    },
    "politica": {
        "saúde": ["saude", "hospital", "posto de saude", "upa", "sus", "medico", "remedio", "fila do sus", "vacina"],
        "educação": ["educacao", "escola", "creche", "professor", "merenda", "universidade", "matricula"],
        "segurança pública": ["seguranca", "policia", "violencia", "assalto", "roubo", "trafico", "milicia", "delegacia", "criminalidade"],
        "emprego e economia": ["emprego", "desemprego", "salario", "renda", "trabalho", "economia", "imposto", "carestia", "inflacao"],
        "obras e infraestrutura": ["obra", "asfalto", "buraco", "saneamento", "esgoto", "iluminacao", "transporte publico", "onibus", "enchente"],
        "corrupção e transparência": ["corrupcao", "corrupto", "desvio", "propina", "superfaturamento", "transparencia", "prestacao de contas", "cpi"],
        "promessas e cobrança": ["prometeu", "promessa", "cade", "cumpriu", "nao fez nada", "so aparece em eleicao", "esqueceu"],
        "mandato e atuação": ["projeto de lei", "votou", "votacao", "mandato", "camara", "assembleia", "sessao", "emenda", "indicacao"],
        "apoio e militância": ["apoio", "estamos juntos", "conte comigo", "meu voto", "votei", "vote", "parabens pelo trabalho", "orgulho"],
        "presença e proximidade": ["visitou", "esteve", "presente", "bairro", "comunidade", "ouviu", "atendeu o povo", "de perto"],
        "posicionamento político": ["direita", "esquerda", "partido", "governo", "oposicao", "aliado", "base", "ideologia"],
    },
    "generico": {},
}

TEMAS = {**TEMAS_COMUNS, **TEMAS_POR_SEGMENTO["servicos"]}  # padrao historico

# Ordem de utilidade para o laudo: o atributo concreto pesa mais que o cenario.
PRIORIDADE_TEMA = {
    "pontualidade": 0, "atendimento": 0, "motorista e condução": 0,
    "entrega e prazo": 0, "saúde": 0, "educação": 0, "segurança pública": 0,
    "corrupção e transparência": 0, "estorno e reembolso": 0,
    "qualidade": 1, "conforto e estrutura": 1, "segurança": 1,
    "preço e custo": 1, "reserva e pagamento": 1, "comunicação e informação": 1,
    "produto e qualidade": 1, "frete": 1, "vendedor e loja": 1, "aplicativo e site": 1,
    "emprego e economia": 1, "obras e infraestrutura": 1, "promessas e cobrança": 1,
    "mandato e atuação": 1, "cupom e promoção": 1,
    "dúvida ou pergunta": 2, "recomendação": 2, "apoio e militância": 2,
    "presença e proximidade": 2, "posicionamento político": 2,
    "viagem e passeio": 3, "assunto geral": 4,
}

_PONTUACAO = re.compile(r"[^\w\s@#]", re.UNICODE)
_ESPACOS = re.compile(r"\s+")


def normalizar(texto: str) -> str:
    """Minusculas sem acento — casa 'ótimo' com 'otimo'."""
    base = unicodedata.normalize("NFKD", str(texto or ""))
    base = "".join(ch for ch in base if not unicodedata.combining(ch))
    return base.lower()


def tokenizar(texto: str) -> list[str]:
    limpo = _PONTUACAO.sub(" ", normalizar(texto))
    return [t for t in _ESPACOS.sub(" ", limpo).strip().split(" ") if t]


def _emoji_score(texto: str) -> float:
    positivos = sum(texto.count(e) for e in EMOJIS_POSITIVOS)
    negativos = sum(texto.count(e) for e in EMOJIS_NEGATIVOS)
    return (positivos * 0.55) - (negativos * 0.75)


def vocabulario(segmento: str = "servicos") -> tuple[dict, dict]:
    """Temas e riscos ativos para um segmento."""
    temas = {**TEMAS_COMUNS, **TEMAS_POR_SEGMENTO.get(segmento, {})}
    riscos = {**RISCOS_COMUNS, **RISCOS_POR_SEGMENTO.get(segmento, {})}
    return temas, riscos


def detectar_riscos(texto: str, segmento: str = "servicos") -> list[str]:
    _, riscos = vocabulario(segmento)
    plano = normalizar(texto)
    return [nome for nome, termos in riscos.items() if any(termo in plano for termo in termos)]


# Um comentario costuma acionar varios temas ao mesmo tempo ("o motorista
# atrasou no aeroporto"). O rotulo util para decisao e o atributo do servico,
# nao o cenario — entao os temas de contexto ficam por ultimo.
PRIORIDADE_TEMA = {
    "pontualidade": 0, "atendimento": 0, "motorista e condução": 0,
    "qualidade do serviço": 1, "conforto e estrutura": 1, "segurança": 1,
    "preço e custo": 1, "reserva e pagamento": 1, "comunicação e informação": 1,
    "dúvida ou pergunta": 2, "recomendação": 2,
    "viagem e passeio": 3, "assunto geral": 4,
}


def detectar_temas(texto: str, segmento: str = "servicos") -> list[str]:
    temas, _ = vocabulario(segmento)
    plano = normalizar(texto)
    achados = [nome for nome, termos in temas.items() if any(termo in plano for termo in termos)]
    if not achados:
        return ["assunto geral"]
    achados.sort(key=lambda nome: PRIORIDADE_TEMA.get(nome, 2))
    return achados[:3]


def adjetivos_presentes(tokens: Iterable[str]) -> list[str]:
    return [t for t in tokens if t in POSITIVAS or t in NEGATIVAS]


def detectar_idioma(tokens: list[str]) -> str:
    marcas_pt = {"nao", "muito", "voces", "obrigado", "otimo", "que", "com", "para"}
    marcas_en = {"the", "you", "very", "thanks", "was", "with", "great"}
    marcas_es = {"muy", "gracias", "pero", "para", "con", "esta"}
    pt = len(marcas_pt.intersection(tokens))
    en = len(marcas_en.intersection(tokens))
    es = len(marcas_es.intersection(tokens))
    if en > pt and en >= es:
        return "en"
    if es > pt and es > en:
        return "es"
    return "pt"


def analisar_texto(comment_id: str, texto: str, segmento: str = "servicos") -> CommentInsight:
    """Classifica um comentario isolado com o motor lexical."""
    tokens = tokenizar(texto)
    idioma = detectar_idioma(tokens)
    negadores = NEGADORES_POR_IDIOMA.get(idioma, NEGADORES_PT)

    # Posicao da adversativa: o trecho final pesa mais que o inicial.
    corte = next((i for i, t in enumerate(tokens) if t in ADVERSATIVAS), None)

    pontuacao = 0.0
    encontrados = 0

    for indice, token in enumerate(tokens):
        peso = POSITIVAS.get(token, 0.0) or -NEGATIVAS.get(token, 0.0)
        if not peso:
            continue
        encontrados += 1
        janela = tokens[max(0, indice - 3) : indice]
        for anterior in janela:
            if anterior in INTENSIFICADORES:
                peso *= INTENSIFICADORES[anterior]
        if any(anterior in negadores for anterior in janela):
            # Negar um extremo nao cria o extremo oposto: "nao foi ruim" e morno.
            peso *= -0.5
        if corte is not None:
            peso *= 0.6 if indice < corte else 1.5
        pontuacao += peso

    pontuacao += _emoji_score(texto)

    bruto = str(texto or "")
    if bruto.count("!") >= 2:
        pontuacao *= 1.15
    letras = [c for c in bruto if c.isalpha()]
    if len(letras) >= 8 and sum(1 for c in letras if c.isupper()) / len(letras) > 0.7:
        pontuacao *= 1.2  # GRITO reforca a emocao, seja qual for

    riscos = detectar_riscos(texto, segmento)
    if riscos:
        pontuacao -= 0.8 * max(SEVERIDADE.get(r, 0.4) for r in riscos)

    # Spam de terceiros nao e elogio a marca: sai do balanco como neutro.
    spam = "concorrente ou spam" in riscos
    if spam and pontuacao > -0.45:
        pontuacao = 0.0

    if pontuacao >= 0.45:
        sentimento = "positivo"
    elif pontuacao <= -0.45:
        sentimento = "negativo"
    else:
        sentimento = "neutro"

    intensidade = min(1.0, abs(pontuacao) / 2.2)
    sinais = encontrados + (1 if _emoji_score(texto) else 0)
    confianca = 0.35 + min(0.5, 0.14 * sinais)
    if sentimento == "neutro" and sinais == 0:
        confianca = 0.5

    severidade = max((SEVERIDADE.get(r, 0.4) for r in riscos), default=0.0)

    return CommentInsight(
        comment_id=comment_id,
        sentiment=sentimento,
        confidence=round(confianca, 2),
        intensity=round(max(0.15, intensidade), 2),
        themes=detectar_temas(texto, segmento),
        adjectives=adjetivos_presentes(tokens)[:5],
        risks=riscos,
        risk_severity=round(severidade, 2),
        language=idioma,
        is_spam=spam,
        rationale="classificacao lexical (sem IA)",
    )
