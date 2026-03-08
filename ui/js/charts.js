/**
 * Chart helpers — thin wrappers around Chart.js with a consistent dark theme.
 */

const Charts = (() => {
  // Shared defaults for the dark theme
  const COLORS = [
    '#4f7df9', '#2ecc71', '#e74c3c', '#f39c12', '#1abc9c',
    '#9b59b6', '#e67e22', '#3498db', '#e84393', '#00cec9',
  ];

  const GRID_COLOR = 'rgba(45,49,72,.5)';
  const TICK_COLOR = '#8b8fa3';

  const baseOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { labels: { color: TICK_COLOR, font: { size: 11 } } },
      tooltip: {
        backgroundColor: '#1a1d27',
        titleColor: '#e4e6f0',
        bodyColor: '#e4e6f0',
        borderColor: '#2d3148',
        borderWidth: 1,
        callbacks: {
          label: (ctx) => {
            const val = ctx.parsed.y ?? ctx.parsed;
            if (typeof val === 'number') return `${ctx.dataset.label}: ${formatCrores(val)}`;
            return `${ctx.dataset.label}: ${val}`;
          },
        },
      },
    },
    scales: {
      x: { ticks: { color: TICK_COLOR, font: { size: 10 } }, grid: { color: GRID_COLOR } },
      y: {
        ticks: {
          color: TICK_COLOR,
          font: { size: 10 },
          callback: (v) => formatCompact(v),
        },
        grid: { color: GRID_COLOR },
      },
    },
  };

  function formatCrores(v) {
    if (v == null) return 'N/A';
    if (Math.abs(v) >= 100000) return `₹${(v / 100000).toFixed(1)}L Cr`;
    if (Math.abs(v) >= 1000) return `₹${(v / 1000).toFixed(1)}K Cr`;
    return `₹${v.toFixed(0)} Cr`;
  }

  function formatCompact(v) {
    if (Math.abs(v) >= 100000) return `${(v / 100000).toFixed(0)}L`;
    if (Math.abs(v) >= 1000) return `${(v / 1000).toFixed(0)}K`;
    return `${v}`;
  }

  /** Destroy an existing chart on a canvas if present. */
  function destroy(canvasId) {
    const existing = Chart.getChart(canvasId);
    if (existing) existing.destroy();
  }

  /**
   * Line chart for time series (e.g. revenue trend).
   * @param {string} canvasId
   * @param {string[]} labels   – fiscal years
   * @param {object[]} datasets – [{ label, data: number[] }, ...]
   */
  function line(canvasId, labels, datasets) {
    destroy(canvasId);
    const ctx = document.getElementById(canvasId).getContext('2d');
    return new Chart(ctx, {
      type: 'line',
      data: {
        labels,
        datasets: datasets.map((ds, i) => ({
          label: ds.label,
          data: ds.data,
          borderColor: COLORS[i % COLORS.length],
          backgroundColor: COLORS[i % COLORS.length] + '22',
          borderWidth: 2,
          pointRadius: 3,
          tension: 0.3,
          fill: datasets.length === 1,
        })),
      },
      options: baseOptions,
    });
  }

  /**
   * Bar chart (e.g. rankings, comparisons).
   * @param {string} canvasId
   * @param {string[]} labels
   * @param {number[]} values
   * @param {string}   label
   */
  function bar(canvasId, labels, values, label = 'Value') {
    destroy(canvasId);
    const ctx = document.getElementById(canvasId).getContext('2d');
    const colors = values.map((_, i) => COLORS[i % COLORS.length]);
    return new Chart(ctx, {
      type: 'bar',
      data: {
        labels,
        datasets: [{
          label,
          data: values,
          backgroundColor: colors.map(c => c + 'bb'),
          borderColor: colors,
          borderWidth: 1,
          borderRadius: 4,
        }],
      },
      options: {
        ...baseOptions,
        plugins: { ...baseOptions.plugins, legend: { display: false } },
        indexAxis: labels.length > 8 ? 'y' : 'x',
      },
    });
  }

  /**
   * Grouped bar for comparisons.
   */
  function groupedBar(canvasId, labels, datasets) {
    destroy(canvasId);
    const ctx = document.getElementById(canvasId).getContext('2d');
    return new Chart(ctx, {
      type: 'bar',
      data: {
        labels,
        datasets: datasets.map((ds, i) => ({
          label: ds.label,
          data: ds.data,
          backgroundColor: COLORS[i % COLORS.length] + 'bb',
          borderColor: COLORS[i % COLORS.length],
          borderWidth: 1,
          borderRadius: 4,
        })),
      },
      options: baseOptions,
    });
  }

  return { line, bar, groupedBar, destroy, formatCrores, COLORS };
})();
