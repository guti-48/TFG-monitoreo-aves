// Capa movil: etiqueta cada celda con el texto de su cabecera para que mobile.css pinte tarjetas.
// Los atributos son inertes en escritorio. No toca dashboard.js ni la API.
(() => {
  const root = document.getElementById('main-content');
  if (!root) return;

  const labelTables = () => {
    root.querySelectorAll('table').forEach((table) => {
      const heads = [...table.querySelectorAll('thead th')].map((th) => th.textContent.trim());
      table.querySelectorAll('tbody tr').forEach((tr) => {
        [...tr.children].forEach((td, i) => {
          if (td.colSpan === 1 && heads[i] && td.dataset.label !== heads[i]) td.dataset.label = heads[i];
        });
      });
    });
  };

  let queued = false;
  new MutationObserver(() => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => { queued = false; labelTables(); });
  }).observe(root, { childList: true, subtree: true });
  labelTables();
})();

// Visor de espectrograma: pantalla completa, pellizco para ampliar, arrastrar y doble toque. Solo en movil.
// shortcut: el limite de arrastre es aproximado; afinar si el espectrograma se sale de la pantalla.
(() => {
  const MOBILE = '(max-width: 767.98px), (orientation: landscape) and (max-height: 500px)';

  const open = (src) => {
    const viewer = document.createElement('div');
    viewer.id = 'spectro-viewer';
    viewer.setAttribute('role', 'dialog');
    viewer.setAttribute('aria-modal', 'true');
    viewer.setAttribute('aria-label', 'Espectrograma ampliado');
    viewer.innerHTML = '<button type="button" class="spectro-close" aria-label="Cerrar"><i class="bi bi-x-lg" aria-hidden="true"></i></button>'
      + '<img alt="Espectrograma ampliado"><p class="spectro-hint">Pellizca para ampliar · doble toque para ajustar</p>';
    const img = viewer.querySelector('img');
    img.src = src;
    document.body.appendChild(viewer);

    let scale = 1, x = 0, y = 0, startDist = 0, startScale = 1, lastTap = 0;
    const pts = new Map();
    const dist = () => { const [a, b] = [...pts.values()]; return Math.hypot(a.x - b.x, a.y - b.y); };
    const apply = () => {
      scale = Math.min(6, Math.max(1, scale));
      const maxX = (scale - 1) * img.clientWidth / 2, maxY = (scale - 1) * img.clientHeight / 2;
      x = scale === 1 ? 0 : Math.min(maxX, Math.max(-maxX, x));
      y = scale === 1 ? 0 : Math.min(maxY, Math.max(-maxY, y));
      img.style.transform = `translate(${x}px, ${y}px) scale(${scale})`;
    };

    const close = () => { viewer.remove(); document.removeEventListener('keydown', onKey); };
    const onKey = (e) => { if (e.key === 'Escape') close(); };
    document.addEventListener('keydown', onKey);
    viewer.querySelector('.spectro-close').addEventListener('click', close);
    viewer.addEventListener('click', (e) => { if (e.target === viewer && scale === 1) close(); });

    viewer.addEventListener('pointerdown', (e) => {
      if (e.target.closest('.spectro-close')) return;
      pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (pts.size === 2) { startDist = dist(); startScale = scale; }
      if (pts.size === 1) {
        const now = Date.now();
        if (now - lastTap < 300) { scale = scale > 1 ? 1 : 3; x = y = 0; apply(); }
        lastTap = now;
      }
    });
    viewer.addEventListener('pointermove', (e) => {
      const p = pts.get(e.pointerId);
      if (!p) return;
      if (pts.size === 2) {
        pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
        scale = startScale * dist() / startDist;
      } else if (scale > 1) {
        x += e.clientX - p.x; y += e.clientY - p.y;
      }
      pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
      apply();
    });
    const release = (e) => pts.delete(e.pointerId);
    viewer.addEventListener('pointerup', release);
    viewer.addEventListener('pointercancel', release);
    viewer.querySelector('.spectro-close').focus();
  };

  document.addEventListener('click', (e) => {
    const img = e.target.closest('#main-content .spectrogram-img');
    if (img && window.matchMedia(MOBILE).matches) open(img.currentSrc || img.src);
  });
})();

// Barra de navegacion inferior (solo visible en movil vertical, ver mobile.css). Reutiliza switchView y el menu lateral.
(() => {
  const root = document.getElementById('main-content');
  const wrapper = document.getElementById('page-content-wrapper');
  if (!root || !wrapper) return;

  const tabs = [
    ['dashboard', 'bi-activity', 'Resumen'],
    ['live', 'bi-broadcast-pin', 'Directo'],
    ['history', 'bi-database-fill', 'Histórico'],
    ['science', 'bi-bar-chart-line-fill', 'Análisis'],
    ['more', 'bi-three-dots', 'Más'],
  ];
  const nav = document.createElement('nav');
  nav.id = 'bottom-nav';
  nav.setAttribute('aria-label', 'Navegación inferior');
  nav.innerHTML = tabs.map(([view, icon, text]) =>
    `<button type="button" data-view="${view}"><i class="bi ${icon}" aria-hidden="true"></i><span>${text}</span></button>`).join('');
  wrapper.appendChild(nav);

  nav.addEventListener('click', (e) => {
    const view = e.target.closest('button')?.dataset.view;
    if (view === 'more') document.getElementById('mobile-menu-toggle')?.click();
    else if (view) switchView(view);
  });

  // "Mas" queda activa en las vistas que solo estan en el menu lateral.
  const sync = () => {
    const view = [...root.classList].find((c) => c.startsWith('view-'))?.slice(5);
    nav.querySelectorAll('button').forEach((b) => {
      const on = b.dataset.view === view || (b.dataset.view === 'more' && (view === 'nodes' || view === 'daily'));
      if (on) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current');
    });
  };
  new MutationObserver(sync).observe(root, { attributes: true, attributeFilter: ['class'] });
  sync();
})();
