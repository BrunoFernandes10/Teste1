---
name: reels-chimarron
description: Produz e ajusta Reels, anúncios em vídeo e adaptações para feed (9:16 e 4:5) da Chimarron com ffmpeg e Python, seguindo as regras de marca e o padrão de edição já aprovados pelo cliente (logo fixo, trilhas do Drive, fechamento, mão pegando a sacola). Use sempre que o pedido envolver editar, montar, cortar, reenquadrar ou trocar trilha de um vídeo da Chimarron ou do Chima, mesmo sem dizer "Reels": marmita, delivery, Little Chima, sacola, drinks, sobremesa, bandeja, fechamento, stop motion, "faz o 4x5", "adapta pro feed", "troca a trilha", "o logo está piscando" ou feedback sobre uma versão já entregue. Não use para escrever roteiro sem editar, nem para copy, campanha ou mídia paga sem vídeo a montar.
---

# Reels da Chimarron

Edição de vídeo por código para a Chimarron, churrascaria de Juiz de Fora. As ferramentas ficam em
`C:\Users\PICHAU\Claude\chimarron-delivery-video`; a saída vai para `out/<peça>_<versão>[_4x5].mp4`.

Fale em português com o usuário e sem jargão técnico: ele avalia assistindo, normalmente pelo celular.

## Como trabalhar

**Analise antes de renderizar quando há dúvida.** Com um briefing claro, execute. Depois de uma versão que
errou, ou com um pedido ou feedback que dá para ler de mais de um jeito, diga o que entendeu e o plano em poucas
linhas e espere a resposta. O usuário já precisou pedir "analisa o que eu digo, antes de sair fazendo", porque uma
versão inteira foi jogada fora por interpretar errado.

**Um pedido de ajuste mexe só no que foi pedido.** Não refaça o que já foi aprovado. Peças prontas não mudam
quando uma regra nova chega, a não ser que ele peça.

**Formato: 9:16 primeiro.** O 4:5 só vem depois que o 9:16 for aprovado, ou se ele pedir direto.

## Regras da marca

Cada uma veio de uma correção do cliente.

**Logo**
- Use o logo escrito "chimarron" (`render(icon=True)`), branco, no topo central. Nunca o selo redondo.
- Em fundo claro, marrom (`icon="dark"`).
- Fixo do primeiro ao último quadro, sem piscar e sem sumir no fechamento.
- Não pode cobrir comida, preço nem texto.

**Texto**
- Só fontes da marca. AH SuperDuper (`style="head"`) não tem acentos, então serve apenas para títulos sem
  acento, como "LITTLE CHIMA". Frases usam Landasans (`style="body"`). O kit troca sozinho se houver acento.
- Destaque, como o preço, em âmbar (`AMBER`).
- Entrada suave (o kit já faz) e composição leve, com pouco texto. Dose o letreiro de acordo com o que está na
  tela: "Escolha sua proteína." quando a proteína entra, "+ dois acompanhamentos." quando eles entram.
- A frase se lê nessa ordem: proteína primeiro, acompanhamentos depois. "+ dois acompanhamentos." sozinho antes
  não faz sentido. Se o bruto põe os acompanhamentos antes da proteína (9050, 9049), abra com um bruto em que a
  proteína vem primeiro (9059), ou, numa peça de marmita única, mostre as duas linhas juntas.
- Fica abaixo do logo: `y` a partir de cerca de 290 no 9:16.
- A oferta ("LITTLE CHIMA", preço) termina quando a sacola entra (`r.text(..., tb, ...)`): por cima da sacola, ela
  encobre a alça e a mão. Se a marmita e a sacola vêm direto, segure a oferta na marmita pronta por 3 tempos ou mais.
- O preço fica em `OFERTA`, em `delivery.py`. Não invente outro.

**Trilha**
- Sempre da pasta do Drive (`trilha("nome.wav")`), meça com `tools/bpm.py` e corte na batida.
- Nunca use o áudio de um vídeo de referência como trilha. Ele traz cliques e efeitos embutidos, e foi isso
  que estragou a v7 dos drinks. Referência serve para entender o ritmo, nada mais.
- Sem trilha sintetizada, salvo pedido.

**Fechamento**
- Toda peça termina com `closing=True, closing_sound=True`: véu escuro, assinatura animada e a música mais baixa
  até sumir. O fim não fica mudo.

**Delivery**
- Termina na mão pegando a sacola e levando embora. Use `sacola(r)`. Sacola parada não serve.
- O último corte em câmera lenta não foca frango nem linguiça: use peixe, picanha ou coraçãozinho.
- Na montagem, use quadros congelados (`still`) escolhidos sem mão e sem migalha caindo. Vídeo corrido deixava
  aparecer a mão.

**Sons**
- Discretos e com função: um som por evento, na batida (`snap` no item que entra, `knock` na marmita assentando,
  `click` no nome do drink). Nada de `whoosh` em cada transição.

**Zoom**
- Comida ganha zoom só quando a peça pede detalhe, e usando trecho nítido. Nas montagens, o usuário preferiu
  sem zoom, com a marmita inteira.

## Adaptação para 4:5

O 4:5 não é o 9:16 cortado no centro. Isso deixa tudo perto demais, e a comida quase encosta no logo.

1. Reenquadre cena a cena com `f45=dict(y=...)`: `y` é o topo do corte de 1350 px dentro do 9:16, de 0 a 570. Veja
   na folha onde o assunto está, escolha o `y` que o deixa mais baixo e o topo livre para logo e título, e tire os
   zooms extras do 9:16 (`f45=dict(y=..., zoom=(1, 1))` quando a cena tem zoom).
   Valores que já funcionaram: montagens `y=420`, pilha `y=330` a `360`, sacola `y=330`.
2. Posicione cada texto com `y45=`. Valores que já funcionaram: frase `185`, título `128` a `135`, preço `240` a
   `262`, frase de baixo `1185`.
3. Se uma cena não funciona em 4:5, troque por outro take (`f45=dict(file=..., start=...)`) ou tire a cena.
   Pular corte é melhor do que forçar.
4. **Nunca use blur, bordas desfocadas nem preenchimento de imagem.** O kit ainda tem a opção `shrink`: não use,
   o usuário proibiu. O limite é o recorte sem zoom. Se ficar apertado, avise em vez de inventar imagem.
5. Para adaptar uma peça pronta, acrescente `f45` e `y45` à função dela e rode com `FMT=45`, que renderiza só o
   4:5. Confira a pilha e o preço na folha: é onde mais aperta.

## Fluxo de uma peça nova

1. **Ache os brutos no Drive.** Leia direto do `H:`, sem copiar para o `C:`. Pastas e mapa do que já se sabe
   estão em `references/brutos-e-trilhas.md`. O link do Drive traz o id da pasta:
   `H:\.shortcut-targets-by-id\<id>\...`. Se a pasta não aparecer ou o `H:` não estiver montado, peça ao usuário
   para adicionar o atalho ou ligar o Drive.
2. **Veja o material antes de escrever qualquer código.** Rode `scripts/folha.py` para ver o que tem em cada
   vídeo e depois para escolher os instantes exatos. Identifique pelo quadro, nunca pelo nome do arquivo.
3. **Escolha a trilha e meça:** `python -I tools/bpm.py "<arquivo>"`. Use a batida como unidade de duração
   (`beat = 60 / bpm`) e o primeiro tempo como `render(bpm=<início em s>)`, assim os cortes caem na música.
   Referência de ritmo, com batida de cerca de 0,75 s: 1 tempo por item, 2 na marmita pronta, 3 na pilha com
   oferta. Em trilha mais rápida, aumente os tempos para manter a duração na tela. As peças entregues têm de 9 a
   18 s de conteúdo, mais 4,8 s de fechamento.
4. **Escreva a peça** como uma função em `tools/delivery.py`, seguindo as vizinhas. A API e os modelos estão em
   `references/kit.md`; leia antes de escrever.
5. **Renderize em segundo plano:** dentro de `tools/`, `V=v1 FMT=916 python -I delivery.py <peça>`. Vídeo 4K
   vindo do Drive demora.
6. **Confira antes de entregar**, com `scripts/conferir.py` e olhando a folha de quadros:
   - logo presente em todos os quadros, inclusive no fechamento (logo marrom sobre o véu escuro, só a olho);
   - áudio em 48 kHz (o loudnorm sobe para 96 kHz e o celular fica mudo);
   - texto sem encostar no logo nem na comida;
   - último take com a mão levando a sacola, se for delivery.
7. **Entregue** com `SendUserFile` e explique em poucas linhas o que foi feito. O app do Claude no celular não
   toca o áudio de vídeo: ele precisa baixar para ouvir, então avise quando houver dúvida sobre som.
8. **Registre** na memória (`project_chimarron_videos.md`) a peça, a versão e qualquer regra nova. Regra que vale
   para todas as peças entra também nesta skill.

## O que você não faz

Não publique anúncios nem posts: o usuário é quem publica, e no Meta só ficam rascunhos. Não digite senhas. Se
precisar do navegador, use o Brave pelo Claude in Chrome e peça autorização lá.
