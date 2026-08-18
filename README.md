# Análise de Sentimento de Perfis do Instagram

Sistema que lê um perfil do Instagram **como uma pessoa faria** — abrindo o Chrome,
entrando na conta, percorrendo as publicações com calma — e devolve um laudo
executivo de reputação: nota de 0 a 100, distribuição de sentimento, pontos
positivos e negativos, riscos, fãs, detratores e ranking de temas.

---

## Como funciona

```
Tela inicial          Sessão humana no Chrome         Analista                Painel
(URL + período)  ──►  login · rolagem · leitura  ──►  classificação  ──►  dashboard
                      (somente leitura)               + métricas            executivo
```

1. **Entrada** — o usuário informa a URL do perfil e o intervalo de datas.
2. **Navegação humana** — o sistema abre o Chrome, faz login, acessa o perfil e lê as
   publicações do período com pausas, tempo de leitura proporcional ao texto, mouse em
   curva e rolagem desacelerada.
3. **Leitura** — coleta comentários, respostas e curtidas somente das publicações
   dentro do intervalo informado.
4. **Análise** — um agente especialista classifica cada comentário; as métricas são
   calculadas de forma determinística.
5. **Painel** — dashboard completo, pronto para impressão em PDF.

---

## Instalação

```bash
git clone <este repositório>
cd Teste1

pip install -r requirements.txt
python -m playwright install chromium

cp .env.example .env      # preencha as credenciais
```

### O arquivo `.env`

| Variável | Para que serve |
|---|---|
| `IG_USERNAME` / `IG_PASSWORD` | Conta usada para navegar. **Nunca** é versionada. |
| `ANTHROPIC_API_KEY` | Habilita o agente analista. Sem ela, cai no motor lexical offline. |
| `ANALYST_MODEL` | Modelo do analista (padrão `claude-opus-5`). |
| `HUMAN_PACE` | `calmo`, `normal` ou `apressado`. |
| `HEADLESS` | `false` mantém a janela do Chrome visível — recomendado. |
| `MAX_POSTS` | Teto de publicações lidas por análise. |
| `CHROME_PATH` | Caminho do Chrome, se não estiver no local padrão. |

---

## Uso

**Antes de tudo — veja o painel funcionando**, sem login e sem chave de API:

```bash
python -m sentiment.cli --demo
```

Ou, pela interface, clique em **"Ver o painel com dados de exemplo"** na tela inicial.
Serve para conhecer o formato do laudo antes de configurar qualquer credencial.

**Interface web** (recomendado):

```bash
./run.sh                       # abre em http://localhost:8000
```

**Linha de comando:**

```bash
python -m sentiment.cli --url https://www.instagram.com/perfil/ --dias 30
python -m sentiment.cli --url https://www.instagram.com/perfil/ --inicio 2026-06-01 --fim 2026-08-18
python -m sentiment.cli --captura runs/captura.json     # reanalisa sem navegar de novo
```

Todo relatório é salvo em `runs/` como JSON.

---

## Conduta da sessão: só olhar, não tocar

O requisito de "apenas visualizar" não depende de boa vontade do código. Ele é
imposto na **camada de rede**: um interceptador em `sentiment/collector/guard.py`
aborta qualquer requisição que altere estado antes que ela saia do navegador.

| Bloqueado | Permitido |
|---|---|
| curtir / descurtir | login e autenticação |
| comentar / apagar comentário | leitura de perfil, publicações e comentários |
| seguir / deixar de seguir | rolagem e navegação |
| salvar publicação, mensagens diretas | |
| *mutations* GraphQL | |

Toda tentativa barrada é registrada e aparece no rodapé do relatório. O teste
`tests/test_e2e.py` força uma curtida, um comentário e um follow dentro do navegador
e confirma que **nenhum** chega ao servidor.

O sistema também não copia mídia: lê apenas o texto público já exibido na tela.

---

## Como o sentimento é medido

### Comentários
Cada comentário recebe sentimento, confiança, intensidade, temas, adjetivos e
sinalização de risco. O analista é instruído a tratar ironia pelo sentido real,
a classificar perguntas de preço como **neutras** (são intenção de compra, não elogio)
e a descartar spam do balanço.

### Reações
O Instagram não rotula reações como o Facebook — não existe "amei" ou "raiva"
separados. Um analista sério precisa declarar como converte curtidas em sentimento,
e é isso que o sistema faz:

- **Curtida em comentário** herda o sentimento do comentário curtido — curtir uma
  reclamação é endossar a reclamação.
- **Curtida em publicação** conta **70%** como aprovação (curtir é ato deliberado) e
  **30%** conforme o clima dos comentários daquela publicação.

Os pesos ficam em `sentiment/config.py` e a metodologia aparece no próprio painel.

### Nota de 0 a 100
Três camadas:

1. **Balanço ponderado** de sentimento dos comentários (75%) e das reações (25%).
2. **Encolhimento bayesiano** para 50 quando há pouca amostra — 4 comentários não
   autorizam dizer "reputação 95".
3. **Desconto por risco**, assimétrico de propósito: uma acusação de golpe pesa mais
   do que dez elogios compensam.

| Faixa | Leitura |
|---|---|
| 85–100 | excelente |
| 70–84 | boa |
| 55–69 | estável |
| 40–54 | em alerta |
| 0–39 | crítica |

Os números são calculados por `sentiment/analysis/scoring.py`, não pela IA — duas
execuções sobre os mesmos dados dão exatamente o mesmo resultado. A IA interpreta
e escreve; ela não inventa números.

---

## O que o painel entrega

- Nota 0–100 com síntese de até 3 linhas
- Comentários: total, média por publicação, % bons / ruins / neutros
- Reações: total, média por publicação, % boas / ruins / neutras
- Pontos positivos, negativos e neutros, com adjetivos e volume de recorrência
- Riscos por gravidade, com evidências e **links das publicações** onde se concentram
- Plano de resposta aos riscos, priorizado e com prazo
- Assuntos potenciais e como aproveitá-los
- Os 5 fãs e os 5 detratores, com link do perfil de cada um
- Ranking dos 5 temas mais publicados, com o sentimento que cada um provocou

---

## Estrutura

```
sentiment/
  config.py              parâmetros e constantes do modelo
  models.py              estruturas de dados
  pipeline.py            orquestração ponta a ponta
  server.py              API HTTP e jobs
  cli.py                 uso por linha de comando
  collector/
    humanize.py          pausas, leitura, mouse em curva, rolagem
    guard.py             trava de somente-leitura
    harvest.py           leitura passiva dos JSON já baixados
    instagram.py         a sessão de navegação
  analysis/
    prompts.py           instruções do agente analista
    analyst.py           classificação e síntese
    lexicon.py           motor lexical pt/en/es (offline)
    scoring.py           todas as métricas do painel
web/                     interface e dashboard
tests/
  mock_instagram/        Instagram simulado para validação
  test_e2e.py            teste com navegador real
```

---

## Testes

```bash
pip install python-multipart          # usado só pelo Instagram simulado
python tests/test_e2e.py
```

O teste sobe um Instagram simulado que reproduz o fluxo real (banner de cookies,
formulário de login, grade paginada por rolagem, modal aberto por clique e fechado
com Escape, e as mesmas formas de JSON da API), roda o coletor Playwright de verdade
contra ele e verifica login, coleta, vínculo comentário↔publicação, a trava de
somente-leitura e a consistência das métricas.

---

## Limites honestos

- **Automatizar login e leitura contrapõe os Termos de Uso do Instagram.** Para uso
  continuado e sem risco de bloqueio, o caminho oficial é a *Instagram Graph API*
  com uma conta Business — ela entrega comentários e métricas do próprio perfil sem
  automação de navegador. Este sistema é adequado para análise pontual da própria
  marca; use com parcimônia.
- Rode a partir de uma conexão residencial. Login vindo de datacenter/VPN costuma
  disparar verificação de segurança.
- Na primeira execução, use `HEADLESS=false`: se aparecer 2FA ou desafio, você
  conclui na janela e a sessão fica salva para as próximas.
- Perfis privados só são lidos se a conta usada já seguir o perfil.
- Curtidas e comentários exibidos pelo Instagram são aproximados quando o volume
  é alto; o sistema reporta o que a tela mostra.
