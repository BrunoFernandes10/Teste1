"""Conjunto de dados realista para validar o sistema ponta a ponta.

Reproduz o material de um perfil de servico de transfer em Orlando ao longo de
90 dias: publicacoes com temas distintos e comentarios em pt/en/es misturando
elogio, duvida, reclamacao, ironia, spam e acusacoes graves — exatamente o tipo
de ruido que o analista precisa separar.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

SEED = 20260818

# Ancorado no presente, nao numa data fixa: assim as publicacoes simuladas
# continuam caindo dentro de qualquer janela relativa ("ultimos 90 dias") por
# mais tempo que passe, e as datas do modo demonstracao nunca parecem velhas.
# O SEED continua fixo, entao os textos e volumes seguem reproduziveis.
HOJE = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)

PERFIL = {
    "username": "flashtransfer.orlando",
    "full_name": "Flash Transfer Orlando",
    "biography": "Transfer executivo em Orlando · Aeroporto · Parques · Outlets · Reservas pelo link",
    "followers": 18420,
    "following": 312,
    "posts_total": 486,
}

# (dias atras, legenda, curtidas)
PUBLICACOES = [
    (3,  "Transfer do aeroporto MCO direto para o seu hotel. Reserve com antecedencia e viaje tranquilo!", 842),
    (7,  "Dia de Disney! Levamos sua familia com conforto e no horario certo.", 1310),
    (12, "Promocao de agosto: 15% off no pacote aeroporto + parques. Vagas limitadas.", 623),
    (18, "Conheca nossa frota: vans climatizadas, higienizadas e com espaco para toda a bagagem.", 977),
    (24, "Depoimento da familia Souza depois de 5 dias com a gente em Orlando.", 1489),
    (31, "Outlet day! Premium Outlets ida e volta com motorista aguardando.", 534),
    (38, "Nossa equipe de motoristas: treinados, bilingues e habilitados nos EUA.", 1105),
    (45, "Chegou de madrugada? Atendemos voos em qualquer horario no aeroporto de Orlando.", 712),
    (52, "Universal Studios com transfer porta a porta. Sem estresse com estacionamento.", 866),
    (60, "Duvidas sobre bagagem e cadeirinha para criancas? A gente resolve antes da viagem.", 448),
    (71, "Pacote familia: transfer para parques por 5 dias com valor fechado.", 1024),
    (84, "Obrigado pelos 18 mil seguidores! Seguimos levando voces com seguranca.", 1863),
]

# Comentaristas recorrentes: a base fiel e os criticos de sempre.
FAS = ["mariana.travels", "carlosandrade_", "familia.no.mundo", "paty_orlando", "ju.viajante", "rafa.mcphotos"]
CRITICOS = ["bruno.reclama", "tatiane.sp", "viajante.irritado", "helena.m.costa", "pedro_denuncia"]
NEUTROS = ["ana.clara.p", "lucas.tourist", "marcosviagens", "sofia.trips", "gui.pereira", "camila.rt"]

POSITIVOS = [
    "Motorista pontualissimo, chegou antes do combinado. Servico impecavel!",
    "Melhor transfer de Orlando! Van limpissima e o motorista super atencioso com as criancas.",
    "Usei 3 vezes e sempre perfeito. Recomendo demais, gente de confianca ❤️",
    "Que equipe maravilhosa! Nos ajudaram com as malas e ainda deram dicas dos parques.",
    "Atendimento excelente desde a reserva pelo whatsapp. Tudo muito profissional.",
    "Pontualidade nota 10. Voo atrasou e mesmo assim estavam la esperando a gente.",
    "Van confortavel, ar condicionado otimo e motorista educadissimo. Valeu cada centavo!",
    "Amazing service! The driver was very friendly and the van was spotless.",
    "Excelente servicio, muy puntual y el conductor muy amable. Recomiendo!",
    "Salvou nossa viagem! Chegamos 2h da manha e estavam la, super seguros.",
    "Preco justo pelo que entregam. Vale muito a pena, viajei tranquila com meus pais.",
    "Motorista bilingue fez toda a diferenca pra minha mae que nao fala ingles. Parabens!",
    "Reserva facil, pagamento simples e zero dor de cabeca. Ja e a nossa terceira vez.",
    "Levaram a gente pro outlet e esperaram sem reclamar. Servico impecavel mesmo!",
    "Great experience, punctual and safe. Will book again next trip.",
]

NEGATIVOS = [
    "Atrasou 50 minutos no aeroporto e ninguem avisou nada. Descaso total.",
    "Van estava suja e com cheiro ruim, esperava bem mais pelo preco cobrado.",
    "Motorista foi grosseiro com a minha esposa. Inadmissivel esse tipo de atendimento.",
    "Achei caro demais comparado com os concorrentes, nao vale o valor.",
    "Cancelaram em cima da hora e ficamos sem transporte com duas criancas. Pessimo.",
    "Terrible experience, the driver was late and very rude. Not recommended.",
    "Paguei antecipado e ninguem apareceu no aeroporto. Isso e golpe! Quero meu dinheiro de volta.",
    "Ja estou acionando o Procon, ninguem responde minhas mensagens ha uma semana.",
    "O motorista dirigiu de forma perigosa, quase batemos na I-4. Nunca mais.",
    "Cobraram taxa que nao estava combinada. Propaganda enganosa, cuidado gente!",
    "Ate que enfim responderam, so levou 6 dias. Parabens pelo atendimento nota 1000.",
    "Sumiram com a minha reserva e nao devolveram o estorno ate hoje. Vou procurar um advogado.",
    "Cadeirinha de crianca veio quebrada, coloquei minha filha em risco. Absurdo.",
]

NEUTROS_TXT = [
    "Quanto custa o transfer do aeroporto ate a area da International Drive?",
    "Voces atendem em Kissimmee tambem?",
    "Tem vaga para o dia 12 de setembro pela manha?",
    "Como faco pra reservar? O link nao abre aqui.",
    "How much for 6 people with luggage from MCO?",
    "Voces tem cadeirinha para bebe de 1 ano?",
    "Aceitam pagamento em real ou so em dolar?",
    "Qual o tempo medio de viagem ate a Disney Springs?",
    "Vou em novembro, ja da pra agendar?",
    "Trabalham no feriado de Thanksgiving?",
    "Cuanto cuesta el traslado desde el aeropuerto?",
    "Precisa pagar tudo adiantado ou so uma parte?",
]

SPAM = [
    "SEGUE DE VOLTA que eu sigo tambem 🔥🔥",
    "Ganhe dinheiro rapido, clique no link do meu perfil!",
    "Compre seguidores de verdade, chama no whatsapp +55 11 9....",
]

RESPOSTAS_MARCA = [
    "Obrigado pelo carinho! Foi um prazer levar voces 💙",
    "Oi! Ja te chamamos no direct para resolver isso, tudo bem?",
    "Que bom que gostou! Contamos com voce na proxima viagem.",
]


def gerar() -> dict:
    """Monta a captura completa, deterministica pelo SEED."""
    rng = random.Random(SEED)
    posts = []
    # Contador sequencial em vez de id sorteado: dois comentarios com o mesmo
    # id fariam o coletor deduplicar (corretamente, pois id do Instagram e
    # unico) e o fixture pareceria perder comentario.
    proximo_id = iter(range(900_000, 999_999))

    for indice, (dias, legenda, curtidas) in enumerate(PUBLICACOES):
        criado = HOJE - timedelta(days=dias, hours=rng.randint(0, 10))
        post_id = f"30{indice:02d}"
        shortcode = f"C{chr(97 + indice)}{rng.randint(100000, 999999)}"

        # Cada publicacao tem sua propria temperatura: promocao atrai duvida,
        # depoimento atrai elogio, problema operacional atrai reclamacao.
        if "Promocao" in legenda or "Duvidas" in legenda or "Pacote" in legenda:
            mistura = (0.35, 0.50, 0.15)
        elif "Depoimento" in legenda or "Obrigado pelos" in legenda or "equipe" in legenda:
            mistura = (0.75, 0.18, 0.07)
        elif "madrugada" in legenda or "aeroporto MCO" in legenda:
            mistura = (0.50, 0.20, 0.30)
        else:
            mistura = (0.58, 0.24, 0.18)

        quantidade = rng.randint(9, 26)
        comentarios = []
        for ordem in range(quantidade):
            sorteio = rng.random()
            if sorteio < 0.04:
                autor, texto = rng.choice(NEUTROS), rng.choice(SPAM)
            elif sorteio < 0.04 + mistura[0]:
                autor = rng.choice(FAS if rng.random() < 0.55 else NEUTROS)
                texto = rng.choice(POSITIVOS)
            elif sorteio < 0.04 + mistura[0] + mistura[1]:
                autor, texto = rng.choice(NEUTROS), rng.choice(NEUTROS_TXT)
            else:
                autor = rng.choice(CRITICOS if rng.random() < 0.7 else NEUTROS)
                texto = rng.choice(NEGATIVOS)

            comentarios.append({
                "id": str(next(proximo_id)),
                "post_id": post_id,
                "author": autor,
                "text": texto,
                "created_at": (criado + timedelta(hours=rng.randint(1, 70))).isoformat(),
                "like_count": max(0, int(rng.lognormvariate(0.8, 1.1)) - 1),
                "is_reply": False,
                "parent_id": None,
            })

        # A marca responde alguns comentarios (deve sair de fas/detratores).
        for _ in range(rng.randint(1, 3)):
            alvo = rng.choice(comentarios)
            comentarios.append({
                "id": str(next(proximo_id)),
                "post_id": post_id,
                "author": PERFIL["username"],
                "text": rng.choice(RESPOSTAS_MARCA),
                "created_at": (criado + timedelta(hours=rng.randint(2, 72))).isoformat(),
                "like_count": rng.randint(0, 4),
                "is_reply": True,
                "parent_id": alvo["id"],
            })

        posts.append({
            "id": post_id,
            "shortcode": shortcode,
            "url": f"https://www.instagram.com/p/{shortcode}/",
            "created_at": criado.isoformat(),
            "caption": legenda,
            "like_count": curtidas + rng.randint(-60, 120),
            "comment_count": len(comentarios),
            "media_type": rng.choice(["imagem", "video", "carrossel", "reel"]),
            "is_pinned": indice == 0,
            "comments": comentarios,
        })

    return {
        "profile": {**PERFIL, "url": f"https://www.instagram.com/{PERFIL['username']}/", "is_private": False},
        "posts": posts,
        "window_start": (HOJE - timedelta(days=90)).isoformat(),
        "window_end": HOJE.isoformat(),
        "notes": ["Conjunto simulado para validacao do sistema."],
    }


if __name__ == "__main__":
    import json

    dados = gerar()
    total = sum(len(p["comments"]) for p in dados["posts"])
    print(f"{len(dados['posts'])} publicacoes, {total} comentarios")
    print(json.dumps(dados["posts"][0]["comments"][:2], ensure_ascii=False, indent=1))
