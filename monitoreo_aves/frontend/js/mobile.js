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
