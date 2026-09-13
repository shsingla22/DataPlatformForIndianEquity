/**
 * API client for the Indian Equity Financial Data Platform.
 *
 * All functions return Promises that resolve to JSON.
 * Can be used by human-facing UI or by AI agents via import.
 */

const API = (() => {
  const BASE = '/api';

  async function _fetch(path, options = {}) {
    const res = await fetch(`${BASE}${path}`, {
      headers: { 'Content-Type': 'application/json', ...options.headers },
      ...options,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
  }

  return {
    // ---- System ----
    health:  ()          => _fetch('/health'),
    stats:   ()          => _fetch('/stats'),

    // ---- Companies ----
    listCompanies: (params = {}) => {
      const qs = new URLSearchParams();
      if (params.q)               qs.set('q', params.q);
      if (params.sector)          qs.set('sector', params.sector);
      if (params.min_market_cap)  qs.set('min_market_cap', params.min_market_cap);
      if (params.max_market_cap)  qs.set('max_market_cap', params.max_market_cap);
      if (params.page)            qs.set('page', params.page);
      if (params.page_size)       qs.set('page_size', params.page_size);
      return _fetch(`/companies?${qs}`);
    },
    getCompany: (symbol)  => _fetch(`/companies/${encodeURIComponent(symbol)}`),
    getSymbols: ()        => _fetch('/companies/symbols'),

    // ---- Financials ----
    getFinancials:  (symbol, year) => {
      const qs = year ? `?year=${encodeURIComponent(year)}` : '';
      return _fetch(`/financials/${encodeURIComponent(symbol)}${qs}`);
    },
    getProfitLoss:  (symbol, year) => {
      const qs = year ? `?year=${encodeURIComponent(year)}` : '';
      return _fetch(`/financials/${encodeURIComponent(symbol)}/profit-loss${qs}`);
    },
    getBalanceSheet:(symbol, year) => {
      const qs = year ? `?year=${encodeURIComponent(year)}` : '';
      return _fetch(`/financials/${encodeURIComponent(symbol)}/balance-sheet${qs}`);
    },
    getCashFlow:    (symbol, year) => {
      const qs = year ? `?year=${encodeURIComponent(year)}` : '';
      return _fetch(`/financials/${encodeURIComponent(symbol)}/cash-flow${qs}`);
    },

    // ---- Compare / Rank ----
    compare: (symbols, table = 'profit_loss', year = null) => {
      const qs = new URLSearchParams({ symbols: symbols.join(','), table });
      if (year) qs.set('year', year);
      return _fetch(`/compare?${qs}`);
    },
    rank: (metric, table = 'profit_loss', order = 'DESC', limit = 10, year = null) => {
      const qs = new URLSearchParams({ metric, table, order, limit });
      if (year) qs.set('year', year);
      return _fetch(`/rank?${qs}`);
    },

    // ---- Natural Language Query ----
    ask: (question) => _fetch('/query', {
      method: 'POST',
      body: JSON.stringify({ question }),
    }),
  };
})();
