# Brutos e trilhas

Confirme sempre pelo quadro: esta tabela ajuda a começar, mas o material pode mudar. Atalhos em
`H:\.shortcut-targets-by-id\` só existem enquanto o atalho está no Drive do usuário, então uma pasta listada aqui
pode não estar disponível agora.

## Pastas

| Conteúdo | Caminho |
|---|---|
| Montando seu delivery | `H:\.shortcut-targets-by-id\1AU3iLz-yaUb7pw8R6XuUXq-4g-cjsrak\montando seu delivery` |
| Imagens de apoio | `H:\.shortcut-targets-by-id\1e7x2ToQbdjQp7dahIAzO2BDt2cEa2FUz\imagens de apoio` |
| Combinações delivery | `H:\.shortcut-targets-by-id\1NPzmj7_JLPJJOxBY_LK4OT-yoQoOj4je\combinacoes delivery` |
| JF Sabor (bandeja) | `H:\.shortcut-targets-by-id\1xo3L1tSEa4nuh66Hky6TKD1uCivrwHmC\jf sabor` |
| Drinks | `H:\.shortcut-targets-by-id\1RQTMbdpiTYQv9xNohUvlLHVYdZCnbp9X\apresentacao dos drinks` |
| Atalhos soltos (sobremesa etc.) | `H:\Meu Drive\IMG_90*.MOV` |
| Trilhas | `H:\Meu Drive\CHIMARRON\01_INSTITUCIONAL\_EDIÇÕES\Trilhas` |
| Fontes e logos oficiais | `H:\Meu Drive\CHIMARRON\01_INSTITUCIONAL\c.Fontes` e `a.Logo` |

No Python, monte o caminho das Trilhas com `os.path.join`: `\01` dentro de uma string quebra o caminho.

## Montando seu delivery

Vídeos 4K na vertical com câmera fixa. Cada um traz marmita sendo montada, tampa e sacola.

| Arquivo | Conteúdo | Quadros sem mão (s) |
|---|---|---|
| `IMG_9059.MOV` | **picanha** primeiro, depois couve e salada | vazia 1 · picanha 18 · couve 45 · salada 86 |
| `IMG_9050.mov` | purê e batata, depois **coração** | vazia 2 · purê 25 · batata 52 · coração 68 |
| `IMG_9049.mov` | risoto, **peixe**, salada | vazia 2 · risoto 35 · peixe 57 · salada 118 |
| `IMG_9058.MOV` | arroz, farofa, frango, linguiça | evitar frango e linguiça em destaque |
| `IMG_9069.MOV` | quatro marmitas empilhando (14,8 s) | assentadas em 0,3 · 4,05 · 8,55 · 13,0 |

Proteína em negrito. Confira os instantes na folha antes de usar.

Mão pegando a sacola: `IMG_9059.MOV`, de 110,6 s a 113,2 s, já pronta em `sacola(r)`. Esse é o take padrão de todas
as peças, mesmo vindo depois de outro bruto: o ângulo muda um pouco no corte, e isso já foi aceito.

## Outros brutos

- `imagens de apoio`: `IMG_9068` peixe, `IMG_9064` picanha, `IMG_9062` frango e linguiça (evitar no fim), `IMG_9065` e `IMG_9066` closes.
- `jf sabor`: `IMG_9087` bandeja caindo e voltando; `IMG_9088` molho, `IMG_9089` sobremesa, `IMG_9090` drink, `IMG_9092` conjunto.
- `H:\Meu Drive`: `IMG_9097` sobremesa com casquinha quebrando, `IMG_9083` apresentação da sobremesa.
- Drinks: `IMG_9027` grupo (quadro em 19 s para a câmera contínua). `IMG_8978` spritz, `IMG_8976` soda italiana de maçã verde, `IMG_8982` margarita, `IMG_8981` cosmopolitan.

Nomes dos drinks confirmados: laranja é Aperol; vermelho de frutas é Gin com frutas vermelhas; verde é Soda italiana de
maçã verde; martini vermelho é Cosmopolitan. Rótulos e setas em branco.

## Trilhas já medidas

Todas são blues ou rock. Medidas com `tools/bpm.py`. A coluna "Início" vai em `render(bpm=...)`.

| Trilha | BPM | Início (s) | Usada em |
|---|---|---|---|
| Blues Rock - 15s | 80,7 | 0,232 | marmitas empilhando |
| Blues Rock - 30s | 80,7 | 0,604 | três montagens |
| Driving Blues Rock (extra-short) | 123 | 0,046 | três faixas |
| Driving Blues Rock (short) | 123 | 0,046 | ainda sem uso |
| Those Oil Can Blues | 89,1 | 0,627 | marmita se monta |
| Blues - Version C | não medido | 0,07 | só mais uma colherada |
| Blues Rock 44 | 112,3 | 0,302 | bandeja |
| Blues Rock Background | 80,7 | 0,186 | drinks |

Evite repetir a mesma trilha em peças que vão rodar juntas, e prefira um arquivo com duração maior que a peça.
