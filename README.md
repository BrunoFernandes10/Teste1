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

## Começando (um comando)

```bash
git clone https://github.com/BrunoFernandes10/Teste1
cd Teste1
git checkout claude/instagram-sentiment-analysis-6376qx

python iniciar.py
```

O `iniciar.py` faz tudo sozinho: confere o Python, instala as bibliotecas, baixa o
navegador, pergunta suas credenciais, diagnostica o que estiver faltando e abre o
sistema em `http://localhost:8000`. Funciona em Windows, Mac e Linux.

Se preferir fazer à mão:

```bash
pip install -r requirements.txt
python -m playwright install chromium
cp .env.example .env      # preencha as credenciais
./run.sh
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

## Quando o Instagram recusa o login

O Instagram responde **"as informações de login estão incorretas"** a navegador
automatizado mesmo com a senha correta — é defesa anti-robô, não erro de digitação.
Três saídas, da mais simples para a mais técnica:

**1. Usar o seu próprio Chrome** (recomendado). Se você já está logado no Chrome do
dia a dia, o sistema aproveita essa sessão e não há login a fazer. O `iniciar.py`
detecta o caminho sozinho e pergunta.

O sistema copia apenas os cookies e a chave que os decifra para uma pasta própria,
e trabalha sobre essa cópia. Isso importa por dois motivos: o Chrome tranca a pasta
de quem a abriu primeiro (e o painel do sistema roda dentro do Chrome, então fechá-lo
não é opção), e nada do seu navegador do dia a dia é alterado. Cache e histórico não
são copiados.

```
CHROME_PROFILE=C:\Users\SEU_USUARIO\AppData\Local\Google\Chrome\User Data
```

**2. Entrar à mão uma vez.** Com `LOGIN_MANUAL=true`, o sistema abre a janela e espera
até 15 minutos você entrar normalmente. A sessão fica salva para as próximas.

**3. Colar o cookie de sessão.** No Chrome já logado: `F12` → Application → Cookies →
`instagram.com` → copie o valor de `sessionid`.

```
IG_SESSIONID=o_valor_copiado
```

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

### Vocabulário por ramo

O que o laudo consegue nomear depende do vocabulário. Uma lista pensada para
transporte não enxerga "estorno" nem "saneamento": tudo cai em "assunto geral" e a
análise perde utilidade. Por isso o ramo é escolhido na tela inicial.

| Ramo | O que passa a enxergar |
|---|---|
| Genérico | atendimento, preço, qualidade, comunicação, dúvidas |
| Serviços | pontualidade, conforto, motorista, reserva, segurança |
| E-commerce | entrega e prazo, frete, estorno, produto falsificado, conta bloqueada |
| Política | saúde, educação, segurança pública, obras, corrupção, promessas, mandato |

Cada ramo traz também a sua tabela de riscos. Em política, ameaça à integridade
física e desinformação pesam mais do que qualquer reclamação; discordância de
posicionamento **não** é tratada como risco — crítica é parte do jogo democrático.

Com a chave da Anthropic o vocabulário importa menos: o analista extrai os temas
do próprio texto em vez de procurar palavras de uma lista.

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

python tests/test_e2e.py       # 18 verificações — navegador real
python tests/test_analista.py  # 19 verificações — agente de IA e seus modos de falha
```

`test_analista.py` exercita o agente com um cliente simulado: resposta bem
formada, JSON corrompido, resposta parcial, exceção da API e falha na síntese.
Em todos os casos o relatório precisa sair completo — um painel que some porque
a API oscilou não serve para operação.

`test_e2e.py` sobe um Instagram simulado que reproduz o fluxo real (banner de cookies,
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
