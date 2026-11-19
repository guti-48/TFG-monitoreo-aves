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

// Oculta la pantalla de arranque nativa (plugin SplashScreen de Capacitor) en cuanto carga el dashboard.
window.addEventListener('load', () => { window.Capacitor?.Plugins?.SplashScreen?.hide?.(); });

// Vibracion al tocar (plugin Haptics de Capacitor). Fuera de la app nativa el plugin no existe y no pasa nada.
(() => {
  const buzz = (kind) => {
    const haptics = window.Capacitor?.Plugins?.Haptics;
    if (!haptics) return;
    const call = ['success', 'warning', 'error'].includes(kind)
      ? haptics.notification({ type: kind.toUpperCase() })
      : haptics.impact({ style: 'LIGHT' });
    Promise.resolve(call).catch(() => {});
  };
  window.__bmBuzz = buzz;

  document.addEventListener('click', (e) => {
    const button = e.target.closest('button');
    if (!button) return;
    const onclick = button.getAttribute('onclick') || '';
    // Las revisiones vibran cuando el servidor confirma (ver el bloque de avisos), no al pulsar.
    if (/quickReviewDetection\(/.test(onclick)) return;
    if (button.closest('#bottom-nav') || button.closest('#action-sheet') || button.id === 'history-load-more'
      || /correctDetectionSpecies|applyLearnedSuggestion/.test(onclick)) buzz('light');
  }, true);
})();

// Avisos tipo notificacion (arriba), hoja de acciones "Revisar" y fin del alert() en movil.
// No toca dashboard.js: envuelve patchDetectionReview (global) para saber cuando el servidor confirma.
(() => {
  const MOBILE = '(max-width: 767.98px), (orientation: landscape) and (max-height: 500px)';
  const isMobile = () => window.matchMedia(MOBILE).matches;
  const buzz = (kind) => window.__bmBuzz?.(kind);
  const root = document.getElementById('main-content');

  // ---- Aviso superior ----
  const ICONS = { success: 'bi-check-circle-fill', warning: 'bi-exclamation-circle-fill', error: 'bi-x-circle-fill', info: 'bi-info-circle-fill' };
  let toastEl; let toastTimer;
  const toast = (message, kind = 'success', action = null) => {
    clearTimeout(toastTimer);
    toastEl?.remove();
    const el = document.createElement('div');
    el.className = `app-toast app-toast-${kind}${action ? ' has-action' : ''}`;
    el.setAttribute('role', kind === 'error' ? 'alert' : 'status');
    const icon = document.createElement('i');
    icon.className = `bi ${ICONS[kind] || ICONS.info}`;
    icon.setAttribute('aria-hidden', 'true');
    const text = document.createElement('span');
    text.textContent = message; // textContent: el mensaje puede incluir texto del servidor
    el.append(icon, text);
    if (action) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'app-toast-action';
      button.textContent = action.label;
      button.addEventListener('click', () => { button.disabled = true; action.onClick(); });
      el.appendChild(button);
    }
    document.body.appendChild(el);
    toastEl = el;
    requestAnimationFrame(() => el.classList.add('show'));
    toastTimer = setTimeout(() => { el.classList.remove('show'); setTimeout(() => el.remove(), 260); }, kind === 'error' ? 4500 : action ? 5500 : 2400);
  };
  window.__bmToast = toast;

  // El alert() del navegador tapa toda la pantalla: en movil pasa a ser un aviso.
  const nativeAlert = window.alert.bind(window);
  window.alert = (message) => {
    if (!isMobile()) return nativeAlert(message);
    const kind = /^(no se pudo|error)/i.test(String(message)) ? 'error' : 'info';
    toast(String(message), kind);
    buzz(kind === 'error' ? 'error' : 'light');
  };

  const reviewMessages = {
    validated: ['Detección validada', 'success'],
    noise: ['Marcada como ruido', 'warning'],
    doubtful: ['Marcada como dudosa', 'info'],
    discarded: ['Detección descartada', 'warning'],
    corrected: ['Especie corregida', 'success'],
  };
  const original = window.patchDetectionReview;
  // Estado de la revision antes del cambio, para poder volver a el. detectionCache es un const global de dashboard.js.
  const snapshot = (id) => {
    if (typeof detectionCache === 'undefined' || !detectionCache.has(id)) return null;
    const review = detectionCache.get(id).review;
    return { status: review?.status || 'unreviewed', corrected_species: review?.corrected_species ?? null, note: review?.note ?? null };
  };
  const undoReview = async (id, previous) => {
    try {
      await original.call(window, id, { ...previous, reviewer: 'dashboard' });
      if (typeof refreshCurrentDetectionView === 'function') await refreshCurrentDetectionView();
      toast('Revisión deshecha', 'info');
      buzz('light');
    } catch (e) {
      toast(`No se pudo deshacer: ${e.message}`, 'error');
      buzz('error');
    }
  };
  if (typeof original === 'function') {
    window.patchDetectionReview = async function (...args) {
      const [id, payload] = args;
      const previous = snapshot(id);
      const result = await original.apply(this, args); // si falla, dashboard.js captura y llama a alert() (ya es un aviso rojo)
      if (isMobile()) {
        const [text, kind] = reviewMessages[payload?.status] || ['Revisión guardada', 'success'];
        toast(text, kind, previous ? { label: 'Deshacer', onClick: () => undoReview(id, previous) } : null);
        buzz(kind === 'info' ? 'light' : kind);
      }
      return result;
    };
  }

  if (!root) return;

  // ---- Hoja de acciones "Revisar" ----
  const describe = (button) => {
    const c = button.getAttribute('onclick') || '';
    if (/'validated'/.test(c)) return ['Validar detección', 'bi-check-lg', ''];
    if (/'noise'/.test(c)) return ['Marcar como ruido', 'bi-volume-mute', ''];
    if (/'doubtful'/.test(c)) return ['Marcar como dudosa', 'bi-question-lg', ''];
    if (/'discarded'/.test(c)) return ['Descartar detección', 'bi-x-lg', 'danger'];
    if (/correctDetectionSpecies/.test(c)) return ['Corregir especie', 'bi-pencil', ''];
    if (/applyLearnedSuggestion/.test(c)) return ['Aplicar sugerencia aprendida', 'bi-stars', ''];
    return [button.title || 'Acción', 'bi-three-dots', ''];
  };

  const closeSheet = () => {
    const sheet = document.getElementById('action-sheet');
    if (!sheet) return;
    sheet.classList.remove('show');
    setTimeout(() => sheet.remove(), 260);
  };

  // Hoja inferior generica: secciones con filas; la de "Revisar" y la del contexto la reutilizan.
  const showSheet = (title, sections) => {
    closeSheet();
    const sheet = document.createElement('div');
    sheet.id = 'action-sheet';
    sheet.setAttribute('role', 'dialog');
    sheet.setAttribute('aria-modal', 'true');
    sheet.setAttribute('aria-label', title);
    const panel = document.createElement('div');
    panel.className = 'sheet-panel';
    panel.innerHTML = '<div class="sheet-grip" aria-hidden="true"></div><p class="sheet-title"></p>';
    panel.querySelector('.sheet-title').textContent = title;
    sections.forEach(({ heading, items }) => {
      if (heading) {
        const h = document.createElement('p');
        h.className = 'sheet-heading';
        h.textContent = heading;
        panel.appendChild(h);
      }
      items.forEach(({ label, icon, tone, selected, onSelect }) => {
        const item = document.createElement('button');
        item.type = 'button';
        item.className = ['sheet-item', tone, selected ? 'selected' : ''].filter(Boolean).join(' ');
        if (icon) {
          const i = document.createElement('i');
          i.className = `bi ${icon}`;
          i.setAttribute('aria-hidden', 'true');
          item.appendChild(i);
        }
        const span = document.createElement('span');
        span.textContent = label;
        item.appendChild(span);
        if (selected) {
          const check = document.createElement('i');
          check.className = 'bi bi-check2 sheet-check';
          check.setAttribute('aria-hidden', 'true');
          item.appendChild(check);
        }
        item.addEventListener('click', () => { closeSheet(); onSelect(); });
        panel.appendChild(item);
      });
    });
    const cancel = document.createElement('button');
    cancel.type = 'button';
    cancel.className = 'sheet-cancel';
    cancel.textContent = 'Cancelar';
    cancel.addEventListener('click', closeSheet);
    panel.appendChild(cancel);
    sheet.appendChild(panel);
    sheet.addEventListener('click', (e) => { if (e.target === sheet) closeSheet(); });
    document.body.appendChild(sheet);
    requestAnimationFrame(() => sheet.classList.add('show'));
  };

  // Reutiliza los botones originales (ocultos): asi no se duplica la logica de dashboard.js.
  const openSheet = (group, title) => showSheet(title || 'Revisar detección', [{
    items: [...group.querySelectorAll('button')].map((original) => {
      const [label, icon, tone] = describe(original);
      return { label, icon, tone, onSelect: () => original.click() };
    }),
  }]);
  window.__bmSheet = showSheet;
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeSheet(); });

  const injectReviewButtons = () => {
    root.querySelectorAll('table .review-actions').forEach((group) => {
      if (group.previousElementSibling?.classList.contains('review-open')) return;
      const open = document.createElement('button');
      open.type = 'button';
      open.className = 'btn review-open';
      open.innerHTML = '<i class="bi bi-clipboard2-check" aria-hidden="true"></i><span>Revisar</span>';
      group.before(open);
    });
  };
  root.addEventListener('click', (e) => {
    const open = e.target.closest('.review-open');
    if (!open) return;
    const species = open.closest('tr')?.querySelector('td[data-label="Especie"]')?.innerText.trim();
    openSheet(open.nextElementSibling, species);
  });

  let queued = false;
  new MutationObserver(() => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => { queued = false; injectReviewButtons(); });
  }).observe(root, { childList: true, subtree: true });
  injectReviewButtons();
})();

// Chip de contexto en la cabecera (movil vertical): sustituye a los dos selectores, que ocupaban ~100 px fijos.
// Reutiliza los selectores originales: elegir una opcion dispara su evento change, asi se ejecuta la logica de dashboard.js.
(() => {
  const topbar = document.getElementById('topbar');
  const switcher = document.getElementById('location-switcher');
  const siteSelect = document.getElementById('location-site-select');
  const deploymentSelect = document.getElementById('location-deployment-select');
  const openSheet = window.__bmSheet;
  if (!topbar || !switcher || !siteSelect || !deploymentSelect || !openSheet) return;

  const chip = document.createElement('button');
  chip.type = 'button';
  chip.className = 'location-chip';
  chip.setAttribute('aria-haspopup', 'dialog');
  chip.innerHTML = '<i class="bi bi-geo-alt-fill" aria-hidden="true"></i><span></span><i class="bi bi-chevron-down" aria-hidden="true"></i>';
  topbar.insertBefore(chip, switcher);

  const selectedText = (select) => select.selectedOptions[0]?.textContent.trim() || '';
  const refreshChip = () => {
    const site = selectedText(siteSelect).replace(/\s*·\s*activa$/i, '');
    const campaign = deploymentSelect.value !== '' ? selectedText(deploymentSelect).split('·')[0].trim() : '';
    chip.querySelector('span').textContent = [site, campaign].filter(Boolean).join(' · ') || 'Ubicación';
    chip.setAttribute('aria-label', `Datos de ${selectedText(siteSelect)}, ${selectedText(deploymentSelect)}. Pulsa para cambiar.`);
    chip.classList.toggle('is-static', siteSelect.disabled && deploymentSelect.disabled);
  };
  [siteSelect, deploymentSelect].forEach((select) => {
    new MutationObserver(refreshChip).observe(select, { childList: true, subtree: true, attributes: true, attributeFilter: ['disabled'] });
  });
  refreshChip();

  const section = (select, heading) => ({
    heading,
    items: [...select.options].map((option) => ({
      label: option.textContent.trim(),
      selected: option.selected,
      onSelect: () => { select.value = option.value; select.dispatchEvent(new Event('change', { bubbles: true })); },
    })),
  });
  chip.addEventListener('click', () => {
    const sections = [];
    if (!siteSelect.disabled) sections.push(section(siteSelect, 'Ubicación'));
    if (!deploymentSelect.disabled) sections.push(section(deploymentSelect, 'Campaña'));
    if (sections.length) openSheet('Datos que estás viendo', sections);
  });
})();
