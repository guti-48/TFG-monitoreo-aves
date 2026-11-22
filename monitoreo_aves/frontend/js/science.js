// Pestañas del Analisis cientifico (compartido por la web y el movil).
// Envuelve renderScienceView sin reescribirla: "Resumen" es la vista de siempre y "Sonido" muestra
// como evolucionan los indices acusticos en el tiempo (datos de /analytics/acoustic-series).
(() => {
  if (typeof renderScienceView !== 'function') return;
  const originalRender = renderScienceView;

  const TABS = [
    ['resumen', 'Resumen', 'bi-speedometer2'],
    ['sonido', 'Sonido', 'bi-soundwave'],
    ['actividad', 'Actividad', 'bi-bar-chart'],
    ['diversidad', 'Diversidad', 'bi-flower1'],
    ['fiabilidad', 'Fiabilidad', 'bi-patch-check']
  ];
  const GREEN = '#2f6f4f';
  let activeTab = 'resumen';
  let charts = [];
  let request = 0;

  const number = (value, decimals = 2) => (value === null || value === undefined ? '–' : Number(value).toLocaleString('es-ES', { maximumFractionDigits: decimals }));
  const dayNumber = (iso) => Math.round(Date.parse(`${iso}T00:00:00Z`) / 86400000);
  const dayLabel = (n) => new Date(n * 86400000).toLocaleDateString('es-ES', { day: '2-digit', month: 'short', timeZone: 'UTC' });
  const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const destroyCharts = () => { charts.forEach((chart) => chart.destroy()); charts = []; };

  window.renderScienceView = async function (container) {
    destroyCharts();
    request += 1;
    container.innerHTML = `
      <div class="science-tabs" role="tablist" aria-label="Secciones del análisis">
        ${TABS.map(([id, label, icon]) => `<button type="button" role="tab" class="science-tab" data-tab="${id}" aria-selected="false"><i class="bi ${icon}" aria-hidden="true"></i><span>${label}</span></button>`).join('')}
      </div>
      <div id="science-panel-resumen" class="science-panel" role="tabpanel"></div>
      <div id="science-panel-sonido" class="science-panel" role="tabpanel" hidden></div>
      <div id="science-panel-actividad" class="science-panel" role="tabpanel" hidden></div>
      <div id="science-panel-diversidad" class="science-panel" role="tabpanel" hidden></div>
      <div id="science-panel-fiabilidad" class="science-panel" role="tabpanel" hidden></div>`;
    const panels = {
      resumen: container.querySelector('#science-panel-resumen'),
      sonido: container.querySelector('#science-panel-sonido'),
      actividad: container.querySelector('#science-panel-actividad'),
      diversidad: container.querySelector('#science-panel-diversidad'),
      fiabilidad: container.querySelector('#science-panel-fiabilidad')
    };
    let soundLoaded = false;
    let activityLoaded = false;
    let diversityLoaded = false;
    let reliabilityLoaded = false;

    const show = (tab) => {
      activeTab = tab;
      container.querySelectorAll('.science-tab').forEach((button) => button.setAttribute('aria-selected', String(button.dataset.tab === tab)));
      Object.entries(panels).forEach(([id, panel]) => { panel.hidden = id !== tab; });
      if (tab === 'sonido' && !soundLoaded) { soundLoaded = true; loadSound(panels.sonido); }
      if (tab === 'actividad' && !activityLoaded) { activityLoaded = true; loadActivity(panels.actividad); }
      if (tab === 'diversidad' && !diversityLoaded) { diversityLoaded = true; loadDiversity(panels.diversidad); }
      if (tab === 'fiabilidad' && !reliabilityLoaded) { reliabilityLoaded = true; loadReliability(panels.fiabilidad); }
      window.dispatchEvent(new Event('resize')); // graficos y mapa se reajustan al volver a mostrarse
    };
    container.querySelector('.science-tabs').addEventListener('click', (event) => {
      const button = event.target.closest('.science-tab');
      if (button) show(button.dataset.tab);
    });

    // El resumen se renderiza visible (Chart.js y el mapa necesitan medir su contenedor) y despues se vuelve a la pestana activa.
    const wanted = activeTab;
    show('resumen');
    await originalRender(panels.resumen);
    if (wanted !== 'resumen' && panels.resumen.isConnected) show(wanted);
  };

  async function loadSound(panel) {
    const ticket = ++request;
    panel.innerHTML = '<div class="science-loading"><div class="spinner-border spinner-border-sm" role="status"></div><span>Cargando la serie de índices…</span></div>';
    let data;
    try {
      const params = selectedScienceDeviceId ? { device_id: selectedScienceDeviceId } : {};
      const response = await fetch(locationAwareUrl('/analytics/acoustic-series', params), { cache: 'no-store' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      data = await response.json();
    } catch (error) {
      if (ticket === request && panel.isConnected) panel.innerHTML = `<div class="alert alert-warning">No se pudo cargar la serie de índices: ${escapeHtml(error.message)}</div>`;
      return;
    }
    if (ticket !== request || !panel.isConnected) return;
    if (!data.available) {
      const legacy = data.legacy_excluded ? ` Hay ${number(data.legacy_excluded, 0)} muestras del método antiguo, que no se pueden comparar.` : '';
      panel.innerHTML = `<div class="alert alert-secondary">${escapeHtml(data.reason || 'Sin datos')}.${legacy}</div>`;
      return;
    }
    renderSound(panel, data);
  }

  async function loadActivity(panel) {
    const ticket = ++request;
    panel.innerHTML = '<div class="science-loading"><div class="spinner-border spinner-border-sm" role="status"></div><span>Cargando la actividad por hora...</span></div>';
    let data;
    try {
      const params = selectedScienceDeviceId ? { device_id: selectedScienceDeviceId } : {};
      const response = await fetch(locationAwareUrl('/analytics/activity', params), { cache: 'no-store' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      data = await response.json();
    } catch (error) {
      if (ticket === request && panel.isConnected) panel.innerHTML = `<div class="alert alert-warning">No se pudo cargar la actividad: ${escapeHtml(error.message)}</div>`;
      return;
    }
    if (ticket !== request || !panel.isConnected) return;
    if (!data.available) {
      panel.innerHTML = `<div class="alert alert-secondary">${escapeHtml(data.reason || 'Sin datos')}.</div>`;
      return;
    }
    renderActivity(panel, data);
  }

  function renderActivity(panel, data) {
    panel.innerHTML = `
      <section class="science-sound">
        <header class="science-sound-head">
          <h4>Actividad de aves por hora</h4>
          <p>${number(data.total, 0)} detecciones · ${data.days} días</p>
        </header>
        <figure class="science-figure">
          <div class="science-canvas"><canvas id="science-activity-chart" role="img" aria-label="Detecciones y especies distintas por hora del día"></canvas></div>
          <figcaption>Fig. 1 — Detecciones (barras, eje izquierdo) y especies distintas (línea, eje derecho) por hora del día.</figcaption>
        </figure>
      </section>`;

    destroyCharts();
    const animation = reducedMotion() ? false : { duration: 300 };
    const grid = { color: 'rgba(95, 111, 101, .15)' };
    const font = { family: "'DM Sans', system-ui, sans-serif" };

    charts.push(new Chart(panel.querySelector('#science-activity-chart'), {
      type: 'bar',
      data: {
        labels: data.hourly.map((row) => `${row.hour}`),
        datasets: [
          {
            label: 'Detecciones',
            data: data.hourly.map((row) => row.detections),
            backgroundColor: 'rgba(47, 111, 79, .65)',
            yAxisID: 'y',
          },
          {
            type: 'line',
            label: 'Especies distintas',
            data: data.hourly.map((row) => row.species),
            borderColor: '#b5651d',
            backgroundColor: '#b5651d',
            borderWidth: 2,
            pointRadius: 3,
            tension: 0.3,
            yAxisID: 'y1',
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation,
        plugins: {
          legend: { display: true, labels: { font } },
          tooltip: { callbacks: { title: (items) => `${items[0].label}:00 h` } },
        },
        scales: {
          x: { grid: { display: false }, title: { display: true, text: 'Hora del día', font }, ticks: { font, maxTicksLimit: 12 } },
          y: { beginAtZero: true, grid, title: { display: true, text: 'Detecciones', font }, ticks: { font, precision: 0 } },
          y1: { beginAtZero: true, position: 'right', grid: { drawOnChartArea: false }, title: { display: true, text: 'Especies', font }, ticks: { font, precision: 0 } },
        },
      },
    }));
  }

  async function loadDiversity(panel) {
    const ticket = ++request;
    panel.innerHTML = '<div class="science-loading"><div class="spinner-border spinner-border-sm" role="status"></div><span>Cargando la diversidad semanal...</span></div>';
    let data;
    try {
      const params = selectedScienceDeviceId ? { device_id: selectedScienceDeviceId } : {};
      const response = await fetch(locationAwareUrl('/analytics/diversity', params), { cache: 'no-store' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      data = await response.json();
    } catch (error) {
      if (ticket === request && panel.isConnected) panel.innerHTML = `<div class="alert alert-warning">No se pudo cargar la diversidad: ${escapeHtml(error.message)}</div>`;
      return;
    }
    if (ticket !== request || !panel.isConnected) return;
    if (!data.available) {
      panel.innerHTML = `<div class="alert alert-secondary">${escapeHtml(data.reason || 'Sin datos')}.</div>`;
      return;
    }
    renderDiversity(panel, data);
  }

  function renderDiversity(panel, data) {
    panel.innerHTML = `
      <section class="science-sound">
        <header class="science-sound-head">
          <h4>Diversidad de aves por semana</h4>
          <p>${number(data.total, 0)} detecciones · ${data.species} especies · ${data.weeks} semanas con datos</p>
        </header>
        <figure class="science-figure">
          <div class="science-canvas"><canvas id="science-diversity-chart" role="img" aria-label="Índice de Shannon y riqueza de especies por semana"></canvas></div>
          <figcaption>Fig. 1 — Índice de Shannon H′ (eje izquierdo) y número de especies (eje derecho) por semana. Un punto hueco indica menos de ${data.min_detections_per_week} detecciones esa semana, por lo que el valor es poco fiable; la línea discontinua une semanas separadas por huecos sin datos.</figcaption>
        </figure>
        <p class="science-index-note">Se han observado ${data.species} especies; el estimador Chao1 calcula unas ${number(data.chao1, 1)} en total, así que el muestreo recoge aproximadamente el ${Math.round((100 * data.species) / data.chao1)} % de las especies presentes. ${data.singletons} especies se detectaron una sola vez: pueden ser raras de verdad o falsos positivos del modelo, y ambas cosas elevan la estimación. Es un indicador del esfuerzo de muestreo, no un censo.</p>
        <figure class="science-figure">
          <div class="science-canvas"><canvas id="science-accumulation-chart" role="img" aria-label="Curva de acumulación de especies frente a la estimación Chao1"></canvas></div>
          <figcaption>Fig. 2 — Especies distintas acumuladas según los días de muestreo con detecciones (no días de calendario). Si la curva se aplana, apenas quedan especies por descubrir; la línea discontinua es la estimación Chao1 del total.</figcaption>
        </figure>
      </section>`;

    destroyCharts();
    const animation = reducedMotion() ? false : { duration: 300 };
    const grid = { color: 'rgba(95, 111, 101, .15)' };
    const font = { family: "'DM Sans', system-ui, sans-serif" };
    const ORANGE = '#b5651d';

    const weekly = data.weekly.map((row) => ({ x: dayNumber(row.week), shannon: row.shannon, richness: row.richness, n: row.detections, low: row.low_sample }));
    const gap = { borderDash: (ctx) => (ctx.p1.parsed.x - ctx.p0.parsed.x > 7.5 ? [4, 4] : undefined) }; // semanas consecutivas distan 7 días

    const serie = (label, key, color, axis) => ({
      label,
      data: weekly.map((row) => ({ x: row.x, y: row[key], n: row.n, low: row.low })),
      borderColor: color,
      borderWidth: 2,
      pointRadius: 4,
      pointBackgroundColor: (ctx) => (ctx.raw?.low ? '#ffffff' : color),
      pointBorderColor: color,
      segment: gap,
      yAxisID: axis,
    });

    charts.push(new Chart(panel.querySelector('#science-diversity-chart'), {
      type: 'line',
      data: { datasets: [serie("Shannon H′", 'shannon', GREEN, 'y'), serie('Especies', 'richness', ORANGE, 'y1')] },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation,
        plugins: {
          legend: { display: true, labels: { font, usePointStyle: true, pointStyle: 'line' } },
          tooltip: {
            callbacks: {
              title: (items) => `Semana del ${dayLabel(items[0].parsed.x)}`,
              label: (item) => `${item.dataset.label}: ${number(item.parsed.y, 3)} (${item.raw.n} detecciones)`,
            },
          },
        },
        scales: {
          x: {
            type: 'linear',
            bounds: 'data',
            grid,
            afterBuildTicks: (scale) => {
              const count = window.innerWidth < 600 ? 4 : 7;
              scale.ticks = Array.from({ length: count }, (_, i) => ({ value: Math.round(scale.min + ((scale.max - scale.min) * i) / (count - 1)) }));
            },
            ticks: { maxRotation: 0, callback: (value) => dayLabel(value), font },
          },
          y: { beginAtZero: true, grid, title: { display: true, text: "Shannon H′", font }, ticks: { font } },
          y1: { beginAtZero: true, position: 'right', grid: { drawOnChartArea: false }, title: { display: true, text: 'Especies', font }, ticks: { font, precision: 0 } },
        },
      },
    }));

    const curve = data.accumulation.map((point) => ({ x: point.day, y: point.species, date: point.date }));
    const lastDay = curve[curve.length - 1].x;
    charts.push(new Chart(panel.querySelector('#science-accumulation-chart'), {
      type: 'line',
      data: {
        datasets: [
          {
            label: 'Especies observadas',
            data: curve,
            borderColor: GREEN,
            backgroundColor: 'rgba(47, 111, 79, .14)',
            fill: 'start',
            borderWidth: 2,
            pointRadius: 2,
          },
          {
            label: `Estimación Chao1 (${number(data.chao1, 1)})`,
            data: [{ x: 1, y: data.chao1 }, { x: lastDay, y: data.chao1 }],
            borderColor: ORANGE,
            borderDash: [6, 4],
            borderWidth: 2,
            pointRadius: 0,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation,
        plugins: {
          legend: { display: true, labels: { font, usePointStyle: true, pointStyle: 'line' } },
          tooltip: {
            filter: (item) => item.datasetIndex === 0,
            callbacks: {
              title: (items) => `Día de muestreo ${items[0].parsed.x} (${items[0].raw.date})`,
              label: (item) => `${item.parsed.y} especies acumuladas`,
            },
          },
        },
        scales: {
          x: { type: 'linear', min: 1, max: lastDay, grid, title: { display: true, text: 'Días de muestreo con detecciones', font }, ticks: { font, precision: 0, maxTicksLimit: 8 } },
          y: { beginAtZero: true, grid, title: { display: true, text: 'Especies acumuladas', font }, ticks: { font, precision: 0 } },
        },
      },
    }));
  }

  async function loadReliability(panel) {
    const ticket = ++request;
    panel.innerHTML = '<div class="science-loading"><div class="spinner-border spinner-border-sm" role="status"></div><span>Cargando la fiabilidad de BirdNET...</span></div>';
    let data;
    try {
      const params = selectedScienceDeviceId ? { device_id: selectedScienceDeviceId } : {};
      const response = await fetch(locationAwareUrl('/analytics/reliability', params), { cache: 'no-store' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      data = await response.json();
    } catch (error) {
      if (ticket === request && panel.isConnected) panel.innerHTML = `<div class="alert alert-warning">No se pudo cargar la fiabilidad: ${escapeHtml(error.message)}</div>`;
      return;
    }
    if (ticket !== request || !panel.isConnected) return;
    if (!data.available) {
      panel.innerHTML = `<div class="alert alert-secondary">${escapeHtml(data.reason || 'Sin datos')}.</div>`;
      return;
    }
    if (!data.decided) {
      panel.innerHTML = '<div class="alert alert-secondary">Aún no hay detecciones revisadas en este alcance: valida o descarta detecciones para medir la fiabilidad.</div>';
      return;
    }
    renderReliability(panel, data);
  }

  function renderReliability(panel, data) {
    const pct = (value) => (value === null || value === undefined ? '–' : `${Math.round(value * 100)} %`);
    panel.innerHTML = `
      <section class="science-sound">
        <header class="science-sound-head">
          <h4>Fiabilidad de BirdNET</h4>
          <p>${number(data.reviewed, 0)} de ${number(data.detections, 0)} detecciones revisadas · precisión ${pct(data.precision)} (IC 95 %: ${pct(data.ci_low)}–${pct(data.ci_high)})</p>
        </header>
        <figure class="science-figure">
          <div class="science-canvas"><canvas id="science-reliability-bins" role="img" aria-label="Precisión de BirdNET por tramo de confianza"></canvas></div>
          <figcaption>Fig. 1 — Porcentaje de detecciones que resultaron correctas según la confianza que dio BirdNET. La barra fina es el intervalo de confianza del 95 % (Wilson): cuanto más larga, menos revisiones hay detrás.</figcaption>
        </figure>
        ${data.species.length ? `
        <figure class="science-figure">
          <div class="science-canvas" style="height: ${Math.max(220, 34 * data.species.length + 80)}px"><canvas id="science-reliability-species" role="img" aria-label="Precisión de BirdNET por especie"></canvas></div>
          <figcaption>Fig. 2 — Precisión por especie, de peor a mejor. Solo especies con al menos ${data.min_reviews_per_species} revisiones decididas.</figcaption>
        </figure>` : `<p class="science-index-note">Ninguna especie tiene todavía ${data.min_reviews_per_species} revisiones decididas, así que no se muestra la precisión por especie.</p>`}
        <p class="science-index-note">Precisión = validadas ÷ (validadas + ruido + corregidas); las dudosas y las no revisadas no cuentan. Ten en cuenta: el nodo descarta todo lo que BirdNET puntúa por debajo de 0,65, así que esto mide cuántos aciertos hay entre lo que se guarda, no cuántas aves se escapan; las revisiones no son una muestra aleatoria (se revisa lo que llama la atención), y las hace una sola persona.</p>
      </section>`;

    destroyCharts();
    const animation = reducedMotion() ? false : { duration: 300 };
    const grid = { color: 'rgba(95, 111, 101, .15)' };
    const font = { family: "'DM Sans', system-ui, sans-serif" };
    const ORANGE = '#b5651d';

    // Barra ancha = precision; barra fina superpuesta [ci_low, ci_high] = intervalo de confianza.
    const precisionChart = (canvas, rows, labelKey, horizontal) => new Chart(canvas, {
      type: 'bar',
      data: {
        labels: rows.map((row) => row[labelKey]),
        datasets: [
          {
            label: 'Precisión',
            data: rows.map((row) => (row.precision === null ? null : row.precision * 100)),
            backgroundColor: 'rgba(47, 111, 79, .65)',
            grouped: false,
            order: 2,
          },
          {
            label: 'IC 95 %',
            data: rows.map((row) => (row.ci_low === null ? null : [row.ci_low * 100, row.ci_high * 100])),
            backgroundColor: ORANGE,
            grouped: false,
            barPercentage: 0.12,
            order: 1,
          },
        ],
      },
      options: {
        indexAxis: horizontal ? 'y' : 'x',
        responsive: true,
        maintainAspectRatio: false,
        animation,
        plugins: {
          legend: { display: true, labels: { font } },
          tooltip: {
            filter: (item) => item.datasetIndex === 0,
            callbacks: {
              label: (item) => {
                const row = rows[item.dataIndex];
                return `${pct(row.precision)} correctas (IC ${pct(row.ci_low)}–${pct(row.ci_high)}) · ${row.validated} de ${row.decided} revisiones`;
              },
            },
          },
        },
        scales: {
          [horizontal ? 'y' : 'x']: { grid: { display: false }, ticks: { font, autoSkip: false } },
          [horizontal ? 'x' : 'y']: { min: 0, max: 100, grid, title: { display: true, text: 'Precisión (%)', font }, ticks: { font, callback: (value) => `${value} %` } },
        },
      },
    });

    charts.push(precisionChart(panel.querySelector('#science-reliability-bins'), data.bins, 'label', false));
    if (data.species.length) charts.push(precisionChart(panel.querySelector('#science-reliability-species'), data.species, 'species', true));
  }

  function renderSound(panel, data) {
    const legacy = data.legacy_excluded ? ` · ${number(data.legacy_excluded, 0)} muestras antiguas excluidas (unidades no comparables)` : '';
    panel.innerHTML = `
      <section class="science-sound">
        <header class="science-sound-head">
          <h4>Paisaje sonoro en el tiempo</h4>
          <p>${number(data.samples, 0)} muestras · ${data.days} días · método ${escapeHtml(data.metrics_version)}${legacy}</p>
        </header>
        <div class="science-chips" role="radiogroup" aria-label="Índice acústico">
          ${data.indices.map((index) => `<button type="button" role="radio" class="science-chip" data-key="${escapeHtml(index.key)}" aria-checked="false" title="${escapeHtml(index.description)}">${escapeHtml(index.label)}</button>`).join('')}
        </div>
        <p class="science-index-note" id="science-index-note"></p>
        <figure class="science-figure">
          <div class="science-canvas"><canvas id="science-daily-chart" role="img"></canvas></div>
          <figcaption id="science-daily-caption"></figcaption>
        </figure>
        <figure class="science-figure">
          <div class="science-canvas"><canvas id="science-hourly-chart" role="img"></canvas></div>
          <figcaption id="science-hourly-caption"></figcaption>
        </figure>
      </section>`;

    const chips = panel.querySelectorAll('.science-chip');
    const select = (key) => {
      chips.forEach((chip) => chip.setAttribute('aria-checked', String(chip.dataset.key === key)));
      drawIndex(panel, data, key);
    };
    panel.querySelector('.science-chips').addEventListener('click', (event) => {
      const chip = event.target.closest('.science-chip');
      if (chip) select(chip.dataset.key);
    });
    select(data.indices.some((index) => index.key === 'bio') ? 'bio' : data.indices[0].key);
  }

  function drawIndex(panel, data, key) {
    destroyCharts();
    const index = data.indices.find((item) => item.key === key);
    const fixedRange = key === 'ndsi' ? { min: -1, max: 1 } : {}; // el NDSI esta definido entre -1 y 1
    const animation = reducedMotion() ? false : { duration: 300 };
    const grid = { color: 'rgba(95, 111, 101, .15)' };
    const font = { family: "'DM Sans', system-ui, sans-serif" };

    const daily = data.daily.filter((row) => row[key] !== null).map((row) => ({ x: dayNumber(row.date), y: row[key], n: row.n, low: row.low_sample }));
    const hourly = Array.from({ length: 24 }, (_, hour) => data.hourly.find((row) => row.hour === hour) || { hour, n: 0, [key]: null });

    const values = hourly.filter((row) => row[key] !== null);
    const peak = values.reduce((best, row) => (row[key] > best[key] ? row : best), values[0]);
    const trough = values.reduce((worst, row) => (row[key] < worst[key] ? row : worst), values[0]);
    panel.querySelector('#science-index-note').textContent = `${index.description} Por hora, el máximo es a las ${peak.hour} h (${number(peak[key])}) y el mínimo a las ${trough.hour} h (${number(trough[key])}).`;
    panel.querySelector('#science-daily-caption').textContent = `Fig. 1 — Media diaria de ${index.label}. Un punto hueco indica menos de ${data.min_samples_per_day} muestras ese día; la línea discontinua une días separados por huecos sin datos.`;
    panel.querySelector('#science-hourly-caption').textContent = `Fig. 2 — Perfil medio de ${index.label} por hora del día (hora local del nodo), con todas las muestras del periodo.`;
    panel.querySelector('#science-daily-chart').setAttribute('aria-label', `Evolución diaria de ${index.label} entre ${data.daily[0].date} y ${data.daily[data.daily.length - 1].date}`);
    panel.querySelector('#science-hourly-chart').setAttribute('aria-label', `Perfil por hora de ${index.label}`);

    charts.push(new Chart(panel.querySelector('#science-daily-chart'), {
      type: 'line',
      data: {
        datasets: [{
          data: daily,
          borderColor: GREEN,
          borderWidth: 2,
          pointRadius: 3,
          pointBackgroundColor: (ctx) => (ctx.raw?.low ? '#ffffff' : GREEN),
          pointBorderColor: GREEN,
          segment: { borderDash: (ctx) => (ctx.p1.parsed.x - ctx.p0.parsed.x > 1.5 ? [4, 4] : undefined) },
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation,
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { title: (items) => dayLabel(items[0].parsed.x), label: (item) => `${index.label}: ${number(item.parsed.y, 3)} (${item.raw.n} muestras)` } },
        },
        scales: {
          x: {
            type: 'linear',
            bounds: 'data',
            grid,
            // Ticks a intervalos iguales entre el primer y el ultimo dia: el automatico acababa pisando la ultima etiqueta.
            afterBuildTicks: (scale) => {
              const count = window.innerWidth < 600 ? 4 : 7;
              scale.ticks = Array.from({ length: count }, (_, i) => ({ value: Math.round(scale.min + ((scale.max - scale.min) * i) / (count - 1)) }));
            },
            ticks: { maxRotation: 0, callback: (value) => dayLabel(value), font },
          },
          y: { ...fixedRange, grid, title: { display: true, text: index.label, font }, ticks: { font } },
        },
      },
    }));

    charts.push(new Chart(panel.querySelector('#science-hourly-chart'), {
      type: 'line',
      data: {
        labels: hourly.map((row) => `${row.hour}`),
        datasets: [{
          data: hourly.map((row) => row[key]),
          borderColor: GREEN,
          backgroundColor: 'rgba(47, 111, 79, .14)',
          fill: 'start', // hacia el borde inferior del eje, no hacia el cero (con valores negativos engañaria)
          tension: 0.3,
          borderWidth: 2,
          pointRadius: 2,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation,
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { title: (items) => `${items[0].label}:00 h`, label: (item) => `${index.label}: ${number(item.parsed.y, 3)} (${hourly[item.dataIndex].n} muestras)` } },
        },
        scales: {
          x: { grid: { display: false }, title: { display: true, text: 'Hora del día', font }, ticks: { font, maxTicksLimit: 12 } },
          y: { ...fixedRange, grid, title: { display: true, text: index.label, font }, ticks: { font } },
        },
      },
    }));
  }
})();
