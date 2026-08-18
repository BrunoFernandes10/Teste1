/* Interface: entrada, acompanhamento ao vivo e renderização do painel. */
'use strict';

const $ = (sel) => document.querySelector(sel);
const criar = (tag, cls, html) => {
  const el = document.createElement(tag);
  if (cls) el.className = cls;
  if (html !== undefined) el.innerHTML = html;
  return el;
};
const esc = (txt) => String(txt ?? '').replace(/[&<>"']/g, (c) =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const num = (v) => Number(v ?? 0).toLocaleString('pt-BR');
const capitalizar = (t) => String(t ?? '').charAt(0).toUpperCase() + String(t ?? '').slice(1);

function mostrarTela(id) {
  document.querySelectorAll('.tela').forEach((t) => t.classList.remove('ativa'));
  $('#' + id).classList.add('ativa');
  window.scrollTo({ top: 0 });
}

/* ------------------------- tela inicial ------------------------- */
function definirPeriodo(dias) {
  const hoje = new Date();
  const antes = new Date(hoje.getTime() - dias * 86400000);
  $('#fim').value = hoje.toISOString().slice(0, 10);
  $('#inicio').value = antes.toISOString().slice(0, 10);
}

$('#atalhos').addEventListener('click', (ev) => {
  const botao = ev.target.closest('button[data-dias]');
  if (!botao) return;
  document.querySelectorAll('#atalhos button').forEach((b) => b.classList.remove('ativo'));
  botao.classList.add('ativo');
  definirPeriodo(Number(botao.dataset.dias));
});
definirPeriodo(30);

fetch('/api/configuracao').then((r) => r.json()).then((cfg) => {
  const avisos = [];
  if (!cfg.conta_configurada) {
    avisos.push('Nenhuma conta configurada: preencha <code>IG_USERNAME</code> e <code>IG_PASSWORD</code> no arquivo <code>.env</code> para que o sistema consiga entrar no Instagram.');
  }
  if (!cfg.analista_ia) {
    avisos.push('Sem <code>ANTHROPIC_API_KEY</code>: a análise usará o motor lexical offline, que é mais raso que o analista de IA.');
  }
  if (avisos.length) {
    $('#aviso-config').innerHTML = avisos.join('<br><br>');
    $('#aviso-config').classList.remove('oculto');
  }
  if (cfg.max_publicacoes) $('#max').value = cfg.max_publicacoes;
}).catch(() => {});

$('#form-analise').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const botao = ev.target.querySelector('button[type=submit]');
  botao.disabled = true;
  botao.textContent = 'Iniciando...';

  const pedido = {
    url: $('#url').value.trim(),
    inicio: $('#inicio').value,
    fim: $('#fim').value,
    ritmo: $('#ritmo').value,
    max_publicacoes: Number($('#max').value) || 40,
    mostrar_navegador: $('#visivel').checked,
  };

  try {
    const resposta = await fetch('/api/analises', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(pedido),
    });
    const dados = await resposta.json();
    if (!resposta.ok) throw new Error(dados.detail || 'Não foi possível iniciar a análise.');
    iniciarAcompanhamento(dados.id, pedido.url);
  } catch (erro) {
    alert(erro.message);
  } finally {
    botao.disabled = false;
    botao.textContent = 'Iniciar análise';
  }
});

/* ------------------------- acompanhamento ------------------------- */
$('#voltar').addEventListener('click', () => mostrarTela('tela-inicial'));

function iniciarAcompanhamento(id, url) {
  mostrarTela('tela-progresso');
  $('#progresso-titulo').textContent = 'Lendo ' + url;
  $('#erro-caixa').classList.add('oculto');
  $('#voltar').classList.add('oculto');
  $('#log').innerHTML = '';

  const timer = setInterval(async () => {
    let estado;
    try {
      estado = await (await fetch('/api/analises/' + id)).json();
    } catch { return; }

    $('#progresso-msg').textContent = estado.mensagem || '';
    $('#barra-preenchida').style.width = (estado.percentual || 0) + '%';
    $('#percentual').textContent = estado.percentual || 0;

    $('#log').innerHTML = '';
    (estado.historico || []).forEach((linha) => {
      const li = criar('li', '', `<time>${esc(linha.hora)}</time><span>${esc(linha.mensagem)}</span>`);
      $('#log').appendChild(li);
    });
    $('#log').scrollTop = $('#log').scrollHeight;

    if (estado.estado === 'concluido') {
      clearInterval(timer);
      const relatorio = await (await fetch(`/api/analises/${id}/relatorio`)).json();
      renderizarPainel(relatorio);
      mostrarTela('tela-dashboard');
    } else if (estado.estado === 'erro') {
      clearInterval(timer);
      $('#progresso-titulo').textContent = 'A análise foi interrompida';
      $('#erro-caixa').textContent = estado.erro || 'Erro desconhecido.';
      $('#erro-caixa').classList.remove('oculto');
      $('#voltar').classList.remove('oculto');
    }
  }, 1500);
}

/* ------------------------- painel ------------------------- */
function corDaNota(nota) {
  if (nota >= 70) return 'var(--pos)';
  if (nota >= 45) return 'var(--neu)';
  return 'var(--neg)';
}

function medidor(nota) {
  const raio = 80, circ = 2 * Math.PI * raio;
  const preenchido = (Math.max(0, Math.min(100, nota)) / 100) * circ;
  return `<div class="medidor">
    <svg width="190" height="190" viewBox="0 0 190 190">
      <circle cx="95" cy="95" r="${raio}" fill="none" stroke="var(--fundo-2)" stroke-width="13"/>
      <circle cx="95" cy="95" r="${raio}" fill="none" stroke="${corDaNota(nota)}" stroke-width="13"
              stroke-linecap="round" stroke-dasharray="${preenchido} ${circ}"/>
    </svg>
    <div class="valor"><b style="color:${corDaNota(nota)}">${nota}</b><span>de 100</span></div>
  </div>`;
}

function barraEmpilhada(pos, neu, neg) {
  const rotulo = (v) => (v >= 8 ? v.toFixed(0) + '%' : '');
  return `<div class="empilhada">
    <div class="p" style="width:${pos}%">${rotulo(pos)}</div>
    <div class="n" style="width:${neu}%">${rotulo(neu)}</div>
    <div class="g" style="width:${neg}%">${rotulo(neg)}</div>
  </div>
  <div class="legenda">
    <span><i style="background:var(--pos)"></i>Positivos ${pos}%</span>
    <span><i style="background:var(--neu)"></i>Neutros ${neu}%</span>
    <span><i style="background:var(--neg)"></i>Negativos ${neg}%</span>
  </div>`;
}

function listaAssuntos(itens, tipo) {
  if (!itens || !itens.length) return '<p class="vazio">Nada recorrente identificado neste grupo.</p>';
  const maximo = Math.max(...itens.map((i) => i.volume), 1);
  return '<ul class="assuntos">' + itens.slice(0, 8).map((item) => {
    const adjetivos = (item.adjetivos || []).length
      ? `<div class="adjetivos">${item.adjetivos.map((a) => `<span>${esc(a)}</span>`).join('')}</div>` : '';
    const exemplo = (item.exemplos || [])[0]
      ? `<div class="citacao">“${esc(item.exemplos[0].texto)}”</div>` : '';
    return `<li>
      <div class="assunto-linha">
        <span class="assunto-nome">${esc(capitalizar(item.assunto))}</span>
        <span class="assunto-vol">${num(item.volume)} menç. · ${item.percentual}%</span>
      </div>
      <div class="trilho ${tipo}"><div style="width:${(item.volume / maximo) * 100}%"></div></div>
      ${adjetivos}${exemplo}
    </li>`;
  }).join('') + '</ul>';
}

function listaPessoas(pessoas, tipo) {
  if (!pessoas || !pessoas.length) {
    return `<p class="vazio">Nenhum perfil se destacou como ${tipo === 'pos' ? 'fã' : 'detrator'} no período.</p>`;
  }
  return pessoas.map((p) => {
    const contagem = tipo === 'pos'
      ? `${p.comentarios_positivos} comentário(s) positivo(s) · ${num(p.curtidas_recebidas)} curtida(s) recebida(s)`
      : `${p.comentarios_negativos} comentário(s) negativo(s) · ${num(p.curtidas_recebidas)} curtida(s) recebida(s)`;
    const citacao = (p.citacoes || [])[0] ? `<div class="citacao">“${esc(p.citacoes[0])}”</div>` : '';
    return `<div class="pessoa">
      <div class="avatar ${tipo}">${esc((p.usuario || '?').slice(0, 2).toUpperCase())}</div>
      <div class="pessoa-info">
        <a href="${esc(p.url_perfil)}" target="_blank" rel="noopener">@${esc(p.usuario)}</a>
        <div class="contagem">${contagem}</div>
        ${citacao}
      </div>
    </div>`;
  }).join('');
}

function renderizarPainel(r) {
  const painel = $('#dashboard');
  const p = r.pontuacao || {};
  const c = r.comentarios || {};
  const x = r.reacoes || {};
  const q = r.qualidade_dos_dados || {};

  const blocos = [];

  /* topo */
  blocos.push(`<div class="painel-topo">
    <div>
      <h2>@${esc(r.perfil?.username || '')}</h2>
      <div class="meta">
        ${esc(r.perfil?.full_name || '')} ·
        ${num(r.perfil?.followers)} seguidores ·
        período de ${esc(r.periodo?.inicio)} a ${esc(r.periodo?.fim)} ·
        ${num(r.publicacoes_analisadas)} publicações lidas
      </div>
    </div>
    <div class="acoes">
      <button class="secundaria" onclick="window.print()">Imprimir / PDF</button>
      <button class="secundaria" id="btn-nova">Nova análise</button>
    </div>
  </div>`);

  /* 1. nota geral + resumo */
  blocos.push(`<div class="bloco">
    <div class="hero">
      ${medidor(p.nota ?? 0)}
      <div class="hero-texto">
        <div class="selos">
          <span class="selo ${p.nota >= 70 ? 'pos' : p.nota >= 45 ? 'neu' : 'neg'}">Reputação ${esc(p.rotulo)}</span>
          <span class="selo">Amostra: ${num(p.amostra)} comentários</span>
          <span class="selo">Confiança amostral: ${Math.round((p.confianca_amostral || 0) * 100)}%</span>
          ${p.penalidade_de_risco ? `<span class="selo neg">Desconto por risco: −${p.penalidade_de_risco}</span>` : ''}
        </div>
        <p class="resumo">${esc(r.resumo)}</p>
        <p class="leitura">${esc(r.leitura_do_periodo)}</p>
      </div>
    </div>
  </div>`);

  /* 2 e 3. comentários e reações */
  blocos.push(`<div class="grade duas">
    <div class="bloco">
      <h3>Comentários</h3>
      <p class="nota-bloco">Volume lido e distribuição de sentimento.</p>
      <div class="kpis">
        <div class="kpi"><b>${num(c.total)}</b><span>Total de comentários</span></div>
        <div class="kpi"><b>${c.media_por_publicacao ?? 0}</b><span>Média por publicação</span></div>
      </div>
      ${barraEmpilhada(c.percentual_positivos || 0, c.percentual_neutros || 0, c.percentual_negativos || 0)}
      <div class="kpis" style="margin-top:16px">
        <div class="kpi pos"><b>${c.percentual_positivos ?? 0}%</b><span>Bons (${num(c.positivos)})</span></div>
        <div class="kpi neu"><b>${c.percentual_neutros ?? 0}%</b><span>Neutros (${num(c.neutros)})</span></div>
        <div class="kpi neg"><b>${c.percentual_negativos ?? 0}%</b><span>Ruins (${num(c.negativos)})</span></div>
      </div>
    </div>
    <div class="bloco">
      <h3>Reações</h3>
      <p class="nota-bloco">${esc(x.metodologia || '')}</p>
      <div class="kpis">
        <div class="kpi"><b>${num(x.total)}</b><span>Total de reações</span></div>
        <div class="kpi"><b>${num(x.media_por_publicacao)}</b><span>Média por publicação</span></div>
      </div>
      ${barraEmpilhada(x.percentual_boas || 0, x.percentual_neutras || 0, x.percentual_ruins || 0)}
      <div class="kpis" style="margin-top:16px">
        <div class="kpi pos"><b>${x.percentual_boas ?? 0}%</b><span>Boas</span></div>
        <div class="kpi neu"><b>${x.percentual_neutras ?? 0}%</b><span>Neutras</span></div>
        <div class="kpi neg"><b>${x.percentual_ruins ?? 0}%</b><span>Ruins</span></div>
      </div>
      <div class="legenda" style="margin-top:12px">
        <span>Em publicações: ${num(x.curtidas_em_publicacoes)}</span>
        <span>Em comentários: ${num(x.curtidas_em_comentarios)}</span>
      </div>
    </div>
  </div>`);

  /* atendimento da marca */
  const a = r.atendimento_da_marca || {};
  const cobertura = a.cobertura_de_resposta_a_negativos ?? 0;
  blocos.push(`<div class="bloco">
    <h3>Atendimento da marca no período</h3>
    <p class="nota-bloco">Responder publicamente a quem reclama é o que mais reduz o dano de um
      comentário negativo — quem lê a thread depois vê a marca presente.</p>
    <div class="kpis">
      <div class="kpi"><b>${num(a.respostas_da_marca)}</b><span>Respostas publicadas</span></div>
      <div class="kpi"><b>${num(a.publicacoes_com_resposta)}</b><span>Publicações com resposta</span></div>
      <div class="kpi ${cobertura >= 70 ? 'pos' : cobertura >= 40 ? 'neu' : 'neg'}">
        <b>${cobertura}%</b><span>Dos ${num(a.comentarios_negativos)} negativos foram respondidos</span></div>
      <div class="kpi"><b>${num(a.negativos_respondidos)}</b><span>Reclamações atendidas</span></div>
    </div>
  </div>`);

  /* 4, 5, 6. pontos positivos, negativos e neutros */
  blocos.push(`<div class="grade tres">
    <div class="bloco"><h3>Pontos positivos</h3>
      <p class="nota-bloco">Assuntos e adjetivos que sustentam a marca.</p>
      ${listaAssuntos(r.pontos_positivos, 'pos')}</div>
    <div class="bloco"><h3>Pontos negativos</h3>
      <p class="nota-bloco">Onde está o atrito com o público.</p>
      ${listaAssuntos(r.pontos_negativos, 'neg')}</div>
    <div class="bloco"><h3>Pontos neutros</h3>
      <p class="nota-bloco">Dúvidas e menções sem carga emocional.</p>
      ${listaAssuntos(r.pontos_neutros, 'neu')}</div>
  </div>`);

  /* 7. riscos */
  const riscos = (r.riscos || []).length
    ? r.riscos.map((risco) => `<div class="risco ${esc(risco.nivel)}">
        <div class="risco-topo">
          <h4>${esc(capitalizar(risco.risco))}</h4>
          <div>
            <span class="nivel ${esc(risco.nivel)}">${esc(risco.nivel)}</span>
            <span class="assunto-vol"> ${num(risco.volume)} ocorrência(s)</span>
          </div>
        </div>
        ${(risco.evidencias || []).slice(0, 2).map((e) =>
          `<div class="citacao">“${esc(e.texto)}” — <a href="${esc(e.url_autor)}" target="_blank" rel="noopener">@${esc(e.autor)}</a></div>`).join('')}
        ${(risco.publicacoes || []).length ? `<div class="links-pub">${risco.publicacoes.map((u, i) =>
          `<a href="${esc(u)}" target="_blank" rel="noopener">Publicação ${i + 1}</a>`).join('')}</div>` : ''}
      </div>`).join('')
    : '<p class="vazio">Nenhum tema de risco relevante identificado no período.</p>';

  const criticas = (r.publicacoes_criticas || []).length
    ? `<h4 style="margin:18px 0 10px;font-size:.9rem">Publicações onde negatividade e risco se concentraram</h4>
       <table class="tabela"><thead><tr><th>Publicação</th><th>Data</th><th>Coment. negativos</th><th>Carga de risco</th></tr></thead><tbody>
       ${r.publicacoes_criticas.map((pub) => `<tr>
         <td><a href="${esc(pub.url)}" target="_blank" rel="noopener">${esc(pub.legenda || pub.url)}</a></td>
         <td>${esc(pub.data)}</td>
         <td class="neg-num">${num(pub.comentarios_negativos)}</td>
         <td class="neg-num">${pub.carga_de_risco}</td></tr>`).join('')}
       </tbody></table>` : '';

  blocos.push(`<div class="bloco"><h3>Análise de riscos</h3>
    <p class="nota-bloco">Temas que podem virar crise, processo ou perda financeira — não é o mesmo que crítica comum.</p>
    ${riscos}${criticas}</div>`);

  /* 8. insights de risco */
  const insights = (r.insights_de_risco || []).length
    ? r.insights_de_risco.map((i) => `<div class="insight">
        <h4>${esc(i.titulo)} <span class="nivel ${i.prioridade === 'alta' ? 'alto' : i.prioridade === 'media' ? 'medio' : 'baixo'}">${esc(i.prioridade)}</span></h4>
        <p><strong>Diagnóstico:</strong> ${esc(i.diagnostico)}</p>
        <p class="acao"><strong>Ação:</strong> ${esc(i.acao)}</p>
        <p><strong>Prazo:</strong> ${esc(i.prazo)}</p>
      </div>`).join('')
    : '<p class="vazio">Sem ações corretivas urgentes no período.</p>';

  const gerais = (r.recomendacoes_gerais || []).length
    ? `<h4 style="margin:16px 0 8px;font-size:.9rem">Recomendações gerais</h4>
       <ul class="assuntos">${r.recomendacoes_gerais.map((g) => `<li>${esc(g)}</li>`).join('')}</ul>` : '';

  blocos.push(`<div class="bloco"><h3>Como lidar com os riscos e sentimentos negativos</h3>
    <p class="nota-bloco">Plano de resposta priorizado.</p>${insights}${gerais}</div>`);

  /* 9. assuntos potenciais */
  const potenciais = (r.assuntos_potenciais || []).length
    ? r.assuntos_potenciais.map((a) => `<div class="insight">
        <h4>${esc(capitalizar(a.assunto))}</h4>
        <p><strong>Por que funciona:</strong> ${esc(a.por_que_funciona)}</p>
        <p class="acao"><strong>Como usar:</strong> ${esc(a.como_usar)}</p>
      </div>`).join('')
    : '<p class="vazio">Nenhum assunto com potencial destacado.</p>';

  blocos.push(`<div class="bloco"><h3>Assuntos potenciais</h3>
    <p class="nota-bloco">Os temas que mais geram sentimento positivo e como aproveitá-los.</p>${potenciais}</div>`);

  /* 10 e 11. fãs e detratores */
  blocos.push(`<div class="grade duas">
    <div class="bloco"><h3>Fãs da marca</h3>
      <p class="nota-bloco">Quem mais apoiou com comentários positivos.</p>
      ${listaPessoas(r.fas, 'pos')}</div>
    <div class="bloco"><h3>Detratores</h3>
      <p class="nota-bloco">Quem mais fez comentários negativos.</p>
      ${listaPessoas(r.detratores, 'neg')}</div>
  </div>`);

  /* 12. ranking de temas */
  const ranking = (r.ranking_temas || []).length
    ? `<table class="tabela">
        <thead><tr><th>#</th><th>Tema</th><th>Publicações</th><th>Comentários</th>
        <th>Distribuição</th><th>Pos.</th><th>Neu.</th><th>Neg.</th></tr></thead>
        <tbody>${r.ranking_temas.map((t) => `<tr>
          <td><span class="posicao">${t.posicao}</span></td>
          <td><span class="tema-nome">${esc(capitalizar(t.tema))}</span></td>
          <td>${num(t.publicacoes)}</td>
          <td>${num(t.comentarios)}</td>
          <td><div class="mini-barra">
            <div class="p" style="width:${t.percentual_positivos}%"></div>
            <div class="n" style="width:${t.percentual_neutros}%"></div>
            <div class="g" style="width:${t.percentual_negativos}%"></div></div></td>
          <td class="pos-num">${t.percentual_positivos}%</td>
          <td class="neu-num">${t.percentual_neutros}%</td>
          <td class="neg-num">${t.percentual_negativos}%</td>
        </tr>`).join('')}</tbody></table>`
    : '<p class="vazio">Sem publicações suficientes para ranquear temas.</p>';

  blocos.push(`<div class="bloco"><h3>Ranking dos temas das publicações</h3>
    <p class="nota-bloco">Os 5 temas mais publicados no período e o sentimento que cada um provocou.</p>
    ${ranking}</div>`);

  /* rodapé técnico */
  const conduta = r.conduta_da_sessao || {};
  blocos.push(`<div class="rodape">
    <strong>Procedência dos dados.</strong>
    Motor de análise: <code>${esc(q.motor_de_analise)}</code> ·
    ${num(q.comentarios_classificados)} comentários classificados ·
    ${num(q.spam_descartado)} descartados como spam ·
    idiomas: ${esc(Object.entries(q.idiomas || {}).map(([k, v]) => `${k} (${v})`).join(', ') || '—')}.<br>
    <strong>Conduta da sessão.</strong> Somente leitura: nenhuma curtida, comentário, seguida ou mensagem.
    Requisições de escrita bloqueadas: ${num(conduta.interacoes_bloqueadas?.requisicoes_de_escrita_bloqueadas ?? 0)}.
    Ritmo de navegação: ${esc(conduta.ritmo || '—')}.<br>
    ${(q.avisos || []).map((a) => esc(a)).join(' · ')}
    ${(q.observacoes || []).map((o) => esc(o)).join(' · ')}<br>
    Relatório gerado em ${esc(r.gerado_em)}.
  </div>`);

  painel.innerHTML = blocos.join('');
  const btn = $('#btn-nova');
  if (btn) btn.addEventListener('click', () => mostrarTela('tela-inicial'));
}

window.renderizarPainel = renderizarPainel;
