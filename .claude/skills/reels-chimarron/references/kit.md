# API do kit (`tools/kit.py`) e modelos de peça

Peças ficam em `tools/delivery.py` como funções, chamadas por `python -I delivery.py <função>` dentro de `tools/`.
Ambiente: `V` é a versão (`v1`), `FMT` é o formato (`916`, `45` ou `916,45`). Quadro de trabalho: 1080x1920, 24 fps.

## Reel

```python
r = Reel("nome_da_peca")          # temporários em work/<nome>, saída em out/<nome>_<versão>.mp4
t0 = r.clip(src, start, length)   # devolve o instante em que o trecho começa no vídeo final
t1 = r.still(src, at, length)     # quadro congelado
```

| Chamada | Para que serve | Parâmetros úteis |
|---|---|---|
| `clip` | trecho filmado | `speed`, `zoom=(z0,z1)`, `center=(x,y)`, `hold` (congela no fim), `keep_audio=True` (só com `speed=1`), `reverse`, `f45` |
| `still` | quadro congelado, base do stop motion | `zoom`, `center`, `f45` |
| `raw` | clipe já pronto em 1080x1920 | `path45` |
| `text` | letreiro | `y`, `y45`, `size`, `style`, `accent` (índice da linha em âmbar), `pos` |
| `label` | nome com seta, usado nos drinks | `point` (ponta), `anchor` (texto), `color` |
| `image` | imagem fixa com transparência | `width`, `top`, `white` |
| `overlay_video` | vídeo com alfa | `start` |
| `sound` | efeito sonoro | `kind`: `snap`, `knock`, `click`, `crunch`, `air`, `pop`, `tick`, `ding`, `whoosh` |

Uma linha de `text` pode misturar estilos na mesma base:
`[("a partir de", "body", 76, WHITE), ("R$32", "head", 132, AMBER)]`.

`f45` aceita `y` (topo do corte 1080x1350 dentro do 9:16), `zoom`, `center` e, só em `clip`, `file`/`start`/`speed`
para outro take. As opções `shrink`, `subj`, `cy` e `bg` são o preenchimento proibido: não use.

No 4:5 o kit reduz títulos (×0,86) e logo (×0,82, topo em 45).

## render

```python
r.render(bpm=<1º tempo em s>, style=trilha("arquivo.wav"), music_gain=0.85, formats=FORMATS, version=VERSION,
         closing=True, icon=True, closing_sound=True)
```

- `bpm`: com trilha de arquivo, é o **início no arquivo em segundos**, apesar do nome.
- `icon`: `True` para logo branco, `"dark"` para marrom em fundo claro.
- `music_at`: a trilha entra depois (som original em destaque no começo).
- `duck`: quanto a trilha baixa sob `keep_audio`.
- `r.music_mute = [(a, b)]`: pausa na música. `r.orig_gain`: volume do som original.

Em peça sem `render(icon=True)`, o logo fixo pode ser posto com `r.image(0, r.t, LOGO, width=280, top=120, white=True)`.
Com início em 0 e fim em `r.t` ele fica sem fade e continua pelo fechamento.

## Modelos para copiar

Leia a função em `delivery.py` antes de começar uma peça parecida:

| Função | Quando usar como base |
|---|---|
| `tres_montagens` | várias montagens em stop motion, depois pilha e sacola; letreiro dosado |
| `monta_sozinha` | uma montagem só; tem exemplo completo de `f45` e `y45` |
| `empilhando` | marmitas assentando na batida, com oferta |
| `faixas` | composição em tiras (`faixas_track`, com `Writer`/`decode`) |
| `colherada` | som original em destaque, trilha entrando depois, logo marrom |
| `bandeja` | rampa de velocidade numa tomada só, em vez de corte seco quando a câmera se mexe; pausa na música |
| `drinks_v8` | câmera contínua sobre um quadro (`Writer`), nomes com seta e clique |

Constantes em `delivery.py`: `TRILHAS`, `MONTAGEM`, `APOIO`, `JF`, `OFERTA`, `sacola(r)`, `trilha(nome)`, `p(pasta, arquivo)`.

## Problemas já resolvidos

Não desfaça estas soluções ao mexer no kit:

- **Logo piscando:** a base é emendada pelo filtro `concat` com `setpts=N/(24*TB)`; o concat demuxer com `-c copy`
  perdia e embaralhava quadros. Logo de duração total entra sem `fade` nem `enable`.
- **Celular mudo:** o loudnorm sobe o áudio para 96 kHz; a saída é forçada com `-ar 48000`.
- **Rastros verticais em tiras expandindo:** erro de um pixel no limite do recorte; veja `faixas_track`.
- **Transição abrupta com câmera em movimento:** rampa de velocidade na mesma tomada (`bandeja`), não corte seco.
