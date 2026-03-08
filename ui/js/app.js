/**
 * Main UI application for the Indian Equity Financial Data Platform.
 */

document.addEventListener('DOMContentLoaded', () => {
  // ============================================================
  // Navigation
  // ============================================================
  const navLinks  = document.querySelectorAll('.nav-link');
  const views     = document.querySelectorAll('.view');
  const sidebar   = document.getElementById('sidebar');
  const menuToggle= document.getElementById('menu-toggle');

  function switchView(viewId) {
    views.forEach(v => v.classList.remove('active'));
    navLinks.forEach(l => l.classList.remove('active'));
    const target = document.getElementById(`view-${viewId}`);
    if (target) target.classList.add('active');
    const link = document.querySelector(`.nav-link[data-view="${viewId}"]`);
    if (link) link.classList.add('active');
    sidebar.classList.remove('open');
  }

  navLinks.forEach(link => {
    link.addEventListener('click', (e) => {
      e.preventDefault();
      switchView(link.dataset.view);
    });
  });

  menuToggle.addEventListener('click', () => sidebar.classList.toggle('open'));

  // ============================================================
  // Load DB stats
  // ============================================================
  API.health().then(data => {
    document.getElementById('stat-companies').textContent = data.total_companies.toLocaleString();
    document.getElementById('stat-records').textContent = data.total_records.toLocaleString();
  }).catch(() => {});

  // ============================================================
  // QUERY VIEW
  // ============================================================
  const chatHistory = document.getElementById('chat-history');
  const queryForm   = document.getElementById('query-form');
  const queryInput  = document.getElementById('query-input');
  const querySubmit = document.getElementById('query-submit');
  let chatChartCounter = 0;

  function addUserMessage(text) {
    // Remove welcome on first message
    const welcome = chatHistory.querySelector('.chat-welcome');
    if (welcome) welcome.remove();

    const div = document.createElement('div');
    div.className = 'chat-msg user-msg';
    div.textContent = text;
    chatHistory.appendChild(div);
    chatHistory.scrollTop = chatHistory.scrollHeight;
  }

  function addLoadingMessage() {
    const div = document.createElement('div');
    div.className = 'chat-msg bot-msg loading-msg';
    div.innerHTML = '<div class="loading-dots"><span></span><span></span><span></span></div>';
    chatHistory.appendChild(div);
    chatHistory.scrollTop = chatHistory.scrollHeight;
    return div;
  }

  function addBotMessage(result) {
    const div = document.createElement('div');
    div.className = 'chat-msg bot-msg';

    let html = '';
    if (result.intent) {
      html += `<span class="intent-tag">${result.intent}</span>`;
    }
    html += `<div class="answer">${escapeHtml(result.answer)}</div>`;

    // Add chart if we have chartable data
    const chartId = `chat-chart-${++chatChartCounter}`;
    const chartData = extractChartData(result);
    if (chartData) {
      html += `<div class="chart-container"><canvas id="${chartId}"></canvas></div>`;
    }

    // Add suggestion chips
    if (result.suggestions && result.suggestions.length) {
      html += '<div class="chat-suggestions">';
      result.suggestions.forEach(s => {
        html += `<button class="chip" data-q="${escapeAttr(s)}">${escapeHtml(s)}</button>`;
      });
      html += '</div>';
    }

    div.innerHTML = html;
    chatHistory.appendChild(div);
    chatHistory.scrollTop = chatHistory.scrollHeight;

    // Render chart after DOM insertion
    if (chartData) {
      setTimeout(() => renderChatChart(chartId, chartData, result), 50);
    }

    // Bind suggestion clicks
    div.querySelectorAll('.chip').forEach(chip => {
      chip.addEventListener('click', () => submitQuery(chip.dataset.q));
    });
  }

  function extractChartData(result) {
    if (!result.data) return null;

    // Trend / lookup with multiple years
    if ((result.intent === 'trend' || result.intent === 'lookup') && Array.isArray(result.data)) {
      const rows = result.data.filter(r => r.fiscal_year);
      if (rows.length >= 2) return { type: 'trend', rows };
    }

    // Rank
    if (result.intent === 'rank' && Array.isArray(result.data) && result.data.length > 0) {
      return { type: 'rank', rows: result.data };
    }

    // Compare
    if (result.intent === 'compare' && Array.isArray(result.data)) {
      const valid = result.data.filter(d => d.financials && d.financials.length > 0);
      if (valid.length >= 2) return { type: 'compare', companies: valid };
    }

    // Overview — show P&L trend
    if (result.intent === 'overview' && result.data && result.data.profit_loss) {
      const rows = result.data.profit_loss;
      if (rows.length >= 2) return { type: 'overview', rows };
    }

    return null;
  }

  function renderChatChart(canvasId, chartData, result) {
    if (chartData.type === 'trend' || chartData.type === 'overview') {
      const rows = chartData.rows;
      const labels = rows.map(r => r.fiscal_year);
      // Try to pick the metric the user asked about
      const numericKeys = Object.keys(rows[0]).filter(
        k => k !== 'fiscal_year' && k !== 'id' && k !== 'company_id' && k !== 'is_consolidated' && k !== 'created_at' && typeof rows[0][k] === 'number'
      );
      const datasets = numericKeys.slice(0, 3).map(key => ({
        label: key.replace(/_/g, ' '),
        data: rows.map(r => r[key]),
      }));
      Charts.line(canvasId, labels, datasets);
    } else if (chartData.type === 'rank') {
      const rows = chartData.rows;
      const labels = rows.map(r => r.nse_symbol || r.name || `#${r.rank}`);
      const values = rows.map(r => r.value ?? r.market_cap_crores ?? 0);
      const metricLabel = result.data[0].value !== undefined ? 'Value' : 'Market Cap';
      Charts.bar(canvasId, labels, values, metricLabel);
    } else if (chartData.type === 'compare') {
      const companies = chartData.companies;
      // Find a common numeric key
      const sampleRow = companies[0].financials[companies[0].financials.length - 1];
      const numericKeys = Object.keys(sampleRow).filter(
        k => !['id','company_id','fiscal_year','is_consolidated','created_at'].includes(k) && typeof sampleRow[k] === 'number'
      );
      const keyToChart = numericKeys.slice(0, 4);
      const labels = keyToChart.map(k => k.replace(/_/g, ' '));
      const datasets = companies.map(c => ({
        label: c.nse_symbol || c.name,
        data: keyToChart.map(k => {
          const latest = c.financials[c.financials.length - 1];
          return latest ? latest[k] : 0;
        }),
      }));
      Charts.groupedBar(canvasId, labels, datasets);
    }
  }

  async function submitQuery(question) {
    if (!question || question.length < 3) return;
    addUserMessage(question);
    queryInput.value = '';
    querySubmit.disabled = true;

    const loader = addLoadingMessage();
    try {
      const result = await API.ask(question);
      loader.remove();
      addBotMessage(result);
    } catch (err) {
      loader.remove();
      addBotMessage({
        intent: 'error',
        answer: `Something went wrong: ${err.message}`,
        suggestions: ['Top 10 companies by revenue', 'Show Reliance financials'],
      });
    }
    querySubmit.disabled = false;
    queryInput.focus();
  }

  queryForm.addEventListener('submit', (e) => {
    e.preventDefault();
    submitQuery(queryInput.value.trim());
  });

  // Initial suggestion chips
  document.querySelectorAll('#initial-suggestions .chip').forEach(chip => {
    chip.addEventListener('click', () => submitQuery(chip.dataset.q));
  });

  // ============================================================
  // COMPANIES VIEW
  // ============================================================
  const companySearch  = document.getElementById('company-search');
  const companiesList  = document.getElementById('companies-list');
  const companyPagination = document.getElementById('companies-pagination');
  const companyModal   = document.getElementById('company-modal');
  let companiesPage = 1;
  let companiesDebounce = null;

  async function loadCompanies(q = '', page = 1) {
    companiesPage = page;
    try {
      const data = await API.listCompanies({ q: q || undefined, page, page_size: 20 });
      renderCompanyGrid(data.companies);
      renderPagination(data.total, data.page, data.page_size);
    } catch (err) {
      companiesList.innerHTML = `<p class="text-muted">Error loading companies: ${escapeHtml(err.message)}</p>`;
    }
  }

  function renderCompanyGrid(companies) {
    if (!companies.length) {
      companiesList.innerHTML = '<p class="text-muted">No companies found.</p>';
      return;
    }
    companiesList.innerHTML = companies.map(c => `
      <div class="company-card" data-symbol="${escapeAttr(c.nse_symbol)}">
        <div class="cc-symbol">${escapeHtml(c.nse_symbol)}</div>
        <div class="cc-name">${escapeHtml(c.name)}</div>
        <div class="cc-mcap">${c.market_cap_crores ? '₹' + Number(c.market_cap_crores).toLocaleString() + ' Cr' : ''}</div>
      </div>
    `).join('');

    companiesList.querySelectorAll('.company-card').forEach(card => {
      card.addEventListener('click', () => openCompanyDetail(card.dataset.symbol));
    });
  }

  function renderPagination(total, page, pageSize) {
    const totalPages = Math.ceil(total / pageSize);
    if (totalPages <= 1) { companyPagination.innerHTML = ''; return; }

    let html = '';
    const maxVisible = 7;
    let start = Math.max(1, page - Math.floor(maxVisible / 2));
    let end = Math.min(totalPages, start + maxVisible - 1);
    if (end - start < maxVisible - 1) start = Math.max(1, end - maxVisible + 1);

    if (page > 1) html += `<button data-page="${page - 1}">Prev</button>`;
    for (let i = start; i <= end; i++) {
      html += `<button data-page="${i}" class="${i === page ? 'active' : ''}">${i}</button>`;
    }
    if (page < totalPages) html += `<button data-page="${page + 1}">Next</button>`;

    companyPagination.innerHTML = html;
    companyPagination.querySelectorAll('button').forEach(btn => {
      btn.addEventListener('click', () => loadCompanies(companySearch.value.trim(), +btn.dataset.page));
    });
  }

  companySearch.addEventListener('input', () => {
    clearTimeout(companiesDebounce);
    companiesDebounce = setTimeout(() => loadCompanies(companySearch.value.trim(), 1), 300);
  });

  // Load companies on first visit
  loadCompanies();

  // ---- Company Detail Modal ----
  async function openCompanyDetail(symbol) {
    const detailDiv = document.getElementById('company-detail');
    detailDiv.innerHTML = '<div class="loading-dots"><span></span><span></span><span></span></div>';
    companyModal.classList.remove('hidden');

    try {
      const data = await API.getFinancials(symbol);
      renderCompanyDetail(data, detailDiv);
    } catch (err) {
      detailDiv.innerHTML = `<p class="text-muted">Error: ${escapeHtml(err.message)}</p>`;
    }
  }

  function renderCompanyDetail(data, container) {
    const c = data.company;
    const chartId = 'detail-chart';

    let html = `
      <div class="detail-header">
        <h3>${escapeHtml(c.nse_symbol)} — ${escapeHtml(c.name)}</h3>
        <div class="detail-meta">
          ${c.market_cap_crores ? `<span>Market Cap: ₹${Number(c.market_cap_crores).toLocaleString()} Cr</span>` : ''}
          ${c.sector ? `<span>Sector: ${escapeHtml(c.sector)}</span>` : ''}
          ${c.industry ? `<span>Industry: ${escapeHtml(c.industry)}</span>` : ''}
        </div>
      </div>
      <div class="detail-tabs">
        <button class="detail-tab active" data-tab="pnl">Profit &amp; Loss</button>
        <button class="detail-tab" data-tab="bs">Balance Sheet</button>
        <button class="detail-tab" data-tab="cf">Cash Flow</button>
      </div>
      <div id="detail-tab-pnl" class="detail-tab-content">
        ${renderFinancialTable(data.profit_loss, ['fiscal_year','sales','expenses','operating_profit','opm_percent','net_profit','eps'])}
      </div>
      <div id="detail-tab-bs" class="detail-tab-content hidden">
        ${renderFinancialTable(data.balance_sheet, ['fiscal_year','equity_capital','reserves','borrowings','total_liabilities','fixed_assets','investments','total_assets'])}
      </div>
      <div id="detail-tab-cf" class="detail-tab-content hidden">
        ${renderFinancialTable(data.cash_flow, ['fiscal_year','cash_from_operating','cash_from_investing','cash_from_financing','net_cash_flow'])}
      </div>
      <div class="detail-chart-container"><canvas id="${chartId}"></canvas></div>
    `;

    container.innerHTML = html;

    // Tab switching
    container.querySelectorAll('.detail-tab').forEach(tab => {
      tab.addEventListener('click', () => {
        container.querySelectorAll('.detail-tab').forEach(t => t.classList.remove('active'));
        container.querySelectorAll('.detail-tab-content').forEach(t => t.classList.add('hidden'));
        tab.classList.add('active');
        document.getElementById(`detail-tab-${tab.dataset.tab}`).classList.remove('hidden');
        renderDetailChart(chartId, data, tab.dataset.tab);
      });
    });

    // Initial chart
    renderDetailChart(chartId, data, 'pnl');
  }

  function renderDetailChart(canvasId, data, tab) {
    let rows, datasets;
    if (tab === 'pnl') {
      rows = data.profit_loss;
      datasets = [
        { label: 'Revenue', data: rows.map(r => r.sales) },
        { label: 'Net Profit', data: rows.map(r => r.net_profit) },
      ];
    } else if (tab === 'bs') {
      rows = data.balance_sheet;
      datasets = [
        { label: 'Total Assets', data: rows.map(r => r.total_assets) },
        { label: 'Borrowings', data: rows.map(r => r.borrowings) },
        { label: 'Reserves', data: rows.map(r => r.reserves) },
      ];
    } else {
      rows = data.cash_flow;
      datasets = [
        { label: 'Operating', data: rows.map(r => r.cash_from_operating) },
        { label: 'Investing', data: rows.map(r => r.cash_from_investing) },
        { label: 'Financing', data: rows.map(r => r.cash_from_financing) },
      ];
    }
    const labels = rows.map(r => r.fiscal_year);
    Charts.line(canvasId, labels, datasets);
  }

  function renderFinancialTable(rows, columns) {
    if (!rows || !rows.length) return '<p class="text-muted">No data available.</p>';
    const headers = columns.map(c => `<th>${formatColumnName(c)}</th>`).join('');
    const body = rows.map(r => {
      const cells = columns.map(c => {
        const v = r[c];
        if (c === 'fiscal_year') return `<td>${escapeHtml(String(v))}</td>`;
        if (v == null) return '<td class="text-muted">—</td>';
        return `<td>${formatNumber(v)}</td>`;
      }).join('');
      return `<tr>${cells}</tr>`;
    }).join('');
    return `<div class="detail-table-wrap"><table class="detail-table"><thead><tr>${headers}</tr></thead><tbody>${body}</tbody></table></div>`;
  }

  // Close modal
  companyModal.querySelector('.modal-close').addEventListener('click', () => companyModal.classList.add('hidden'));
  companyModal.querySelector('.modal-backdrop').addEventListener('click', () => companyModal.classList.add('hidden'));

  // ============================================================
  // COMPARE VIEW
  // ============================================================
  const compareInput  = document.getElementById('compare-input');
  const compareAC     = document.getElementById('compare-autocomplete');
  const compareSelected = document.getElementById('compare-selected');
  const compareBtn    = document.getElementById('compare-btn');
  const compareResults = document.getElementById('compare-results');
  let selectedCompanies = [];
  let allSymbols = [];

  // Load symbols for autocomplete
  API.getSymbols().then(syms => { allSymbols = syms; }).catch(() => {});

  compareInput.addEventListener('input', () => {
    const q = compareInput.value.trim().toUpperCase();
    if (q.length < 1) { compareAC.classList.add('hidden'); return; }
    const matches = allSymbols.filter(s => s.includes(q)).slice(0, 8);
    if (!matches.length) { compareAC.classList.add('hidden'); return; }
    compareAC.innerHTML = matches.map(s =>
      `<div class="autocomplete-item"><span class="ac-symbol">${escapeHtml(s)}</span></div>`
    ).join('');
    compareAC.classList.remove('hidden');
    compareAC.querySelectorAll('.autocomplete-item').forEach(item => {
      item.addEventListener('click', () => {
        addCompareChip(item.querySelector('.ac-symbol').textContent);
        compareInput.value = '';
        compareAC.classList.add('hidden');
      });
    });
  });

  compareInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      const val = compareInput.value.trim().toUpperCase();
      if (val && allSymbols.includes(val)) addCompareChip(val);
      compareInput.value = '';
      compareAC.classList.add('hidden');
    }
  });

  document.addEventListener('click', (e) => {
    if (!compareAC.contains(e.target) && e.target !== compareInput) {
      compareAC.classList.add('hidden');
    }
  });

  function addCompareChip(symbol) {
    if (selectedCompanies.includes(symbol) || selectedCompanies.length >= 5) return;
    selectedCompanies.push(symbol);
    renderCompareChips();
    compareBtn.disabled = selectedCompanies.length < 2;
  }

  function renderCompareChips() {
    compareSelected.innerHTML = selectedCompanies.map(s =>
      `<span class="selected-chip">${escapeHtml(s)} <span class="remove-chip" data-sym="${escapeAttr(s)}">&times;</span></span>`
    ).join('');
    compareSelected.querySelectorAll('.remove-chip').forEach(btn => {
      btn.addEventListener('click', () => {
        selectedCompanies = selectedCompanies.filter(s => s !== btn.dataset.sym);
        renderCompareChips();
        compareBtn.disabled = selectedCompanies.length < 2;
      });
    });
  }

  compareBtn.addEventListener('click', async () => {
    if (selectedCompanies.length < 2) return;
    compareBtn.disabled = true;
    compareResults.innerHTML = '<div class="loading-dots"><span></span><span></span><span></span></div>';
    const table = document.getElementById('compare-table').value;
    try {
      const data = await API.compare(selectedCompanies, table);
      renderCompareResults(data, table);
    } catch (err) {
      compareResults.innerHTML = `<p class="text-muted">Error: ${escapeHtml(err.message)}</p>`;
    }
    compareBtn.disabled = selectedCompanies.length < 2;
  });

  function renderCompareResults(data, table) {
    const companies = data.companies.filter(c => !c.error && c.financials && c.financials.length);
    if (!companies.length) {
      compareResults.innerHTML = '<p class="text-muted">No comparable data found.</p>';
      return;
    }

    // Determine columns from the first company's latest row
    const sampleRow = companies[0].financials[companies[0].financials.length - 1];
    const skipCols = ['id', 'company_id', 'is_consolidated', 'created_at'];
    const columns = Object.keys(sampleRow).filter(k => !skipCols.includes(k));

    // Build table
    let html = '<div class="compare-table-wrap"><table class="detail-table"><thead><tr><th>Metric</th>';
    companies.forEach(c => { html += `<th>${escapeHtml(c.nse_symbol)}</th>`; });
    html += '</tr></thead><tbody>';

    columns.forEach(col => {
      html += `<tr><td>${formatColumnName(col)}</td>`;
      companies.forEach(c => {
        const latest = c.financials[c.financials.length - 1];
        const v = latest[col];
        html += col === 'fiscal_year'
          ? `<td>${escapeHtml(String(v))}</td>`
          : `<td>${v != null ? formatNumber(v) : '<span class="text-muted">—</span>'}</td>`;
      });
      html += '</tr>';
    });
    html += '</tbody></table></div>';

    // Chart
    const chartId = 'compare-chart';
    html += `<div class="detail-chart-container" style="height:300px;"><canvas id="${chartId}"></canvas></div>`;

    compareResults.innerHTML = html;

    // Render grouped bar chart
    const numericCols = columns.filter(k => k !== 'fiscal_year' && typeof sampleRow[k] === 'number').slice(0, 5);
    const labels = numericCols.map(formatColumnName);
    const datasets = companies.map(c => ({
      label: c.nse_symbol,
      data: numericCols.map(k => {
        const latest = c.financials[c.financials.length - 1];
        return latest ? latest[k] : 0;
      }),
    }));
    setTimeout(() => Charts.groupedBar(chartId, labels, datasets), 50);
  }

  // ============================================================
  // RANKINGS VIEW
  // ============================================================
  const rankBtn     = document.getElementById('rank-btn');
  const rankResults = document.getElementById('rank-results');

  // Update metric options when table changes
  const metricsByTable = {
    profit_loss:   [['net_profit','Net Profit'],['sales','Revenue'],['operating_profit','Operating Profit'],['opm_percent','OPM %'],['eps','EPS'],['profit_before_tax','PBT']],
    balance_sheet: [['total_assets','Total Assets'],['borrowings','Borrowings'],['reserves','Reserves'],['total_liabilities','Total Liabilities'],['equity_capital','Equity Capital'],['investments','Investments']],
    cash_flow:     [['cash_from_operating','Operating CF'],['cash_from_investing','Investing CF'],['cash_from_financing','Financing CF'],['net_cash_flow','Net Cash Flow']],
  };

  document.getElementById('rank-table').addEventListener('change', (e) => {
    const sel = document.getElementById('rank-metric');
    const options = metricsByTable[e.target.value] || metricsByTable.profit_loss;
    sel.innerHTML = options.map(([v, l]) => `<option value="${v}">${l}</option>`).join('');
  });

  rankBtn.addEventListener('click', async () => {
    rankBtn.disabled = true;
    rankResults.innerHTML = '<div class="loading-dots"><span></span><span></span><span></span></div>';
    const table  = document.getElementById('rank-table').value;
    const metric = document.getElementById('rank-metric').value;
    const order  = document.getElementById('rank-order').value;
    const limit  = +document.getElementById('rank-limit').value;

    try {
      const data = await API.rank(metric, table, order, limit);
      renderRankResults(data);
    } catch (err) {
      rankResults.innerHTML = `<p class="text-muted">Error: ${escapeHtml(err.message)}</p>`;
    }
    rankBtn.disabled = false;
  });

  function renderRankResults(data) {
    const results = data.results;
    if (!results.length) {
      rankResults.innerHTML = '<p class="text-muted">No results.</p>';
      return;
    }

    let html = '<table class="rank-table"><thead><tr><th>#</th><th>Company</th><th>Fiscal Year</th><th>Value</th></tr></thead><tbody>';
    results.forEach(r => {
      const badge = r.rank <= 3 ? `<span class="rank-badge rank-${r.rank}">${r.rank}</span>` : r.rank;
      html += `<tr>
        <td>${badge}</td>
        <td><strong>${escapeHtml(r.nse_symbol)}</strong> <span class="text-muted">${escapeHtml(r.name || '')}</span></td>
        <td>${escapeHtml(r.fiscal_year)}</td>
        <td>${r.value != null ? formatNumber(r.value) : '—'}</td>
      </tr>`;
    });
    html += '</tbody></table>';

    const chartId = 'rank-chart';
    html += `<div class="rank-chart-container"><canvas id="${chartId}"></canvas></div>`;

    rankResults.innerHTML = html;

    const labels = results.map(r => r.nse_symbol || `#${r.rank}`);
    const values = results.map(r => r.value || 0);
    setTimeout(() => Charts.bar(chartId, labels, values, formatColumnName(data.metric)), 50);
  }

  // Load initial rankings
  setTimeout(() => rankBtn.click(), 500);

  // ============================================================
  // Utility functions
  // ============================================================
  function escapeHtml(s) {
    if (!s) return '';
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }
  function escapeAttr(s) {
    return escapeHtml(s).replace(/'/g, '&#39;');
  }
  function formatColumnName(col) {
    return col.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
  }
  function formatNumber(v) {
    if (v == null) return '—';
    if (typeof v !== 'number') return String(v);
    return v.toLocaleString('en-IN', { maximumFractionDigits: 2 });
  }
});
