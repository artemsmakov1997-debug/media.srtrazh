/* Presentation-only adapter. Uses the unchanged production viewer and Python engine. */
(() => {
  'use strict';
  const byId = id => document.getElementById(id);
  const modes = Array.from(document.querySelectorAll('[data-mode]'));
  modes.forEach(button => button.addEventListener('click', () => {
    const manual = button.dataset.mode === 'manual';
    byId('automaticPanel').hidden = manual;
    byId('manualPanel').hidden = !manual;
    modes.forEach(item => {
      const active = item === button;
      item.classList.toggle('active', active);
      item.setAttribute('aria-pressed', String(active));
    });
  }));

  const filters = ['source', 'platform', 'marker'].map(byId);
  const filterPanel = byId('filterPanel');
  const narrow = matchMedia('(max-width: 700px)');
  const setFilterLayout = () => { filterPanel.open = !narrow.matches; };
  setFilterLayout();
  narrow.addEventListener('change', setFilterLayout);
  filterPanel.addEventListener('toggle', () => {
    // Native details keeps the phone's disclosure keyboard/touch accessible.
    if (!narrow.matches && !filterPanel.open) filterPanel.open = true;
  });
  function describeFilters() {
    const selected = filters.filter(item => item.value);
    byId('resetFilters').disabled = !selected.length;
    byId('filterSummary').textContent = selected.length
      ? selected.map(item => item.selectedOptions[0].textContent).join(' · ')
      : 'Все издания и площадки';
  }
  filters.forEach(item => item.addEventListener('change', describeFilters));
  byId('resetFilters').addEventListener('click', () => {
    filters.forEach(item => { item.value = ''; });
    // One production change handler filters the entire data set; no new analysis rules.
    filters[0].dispatchEvent(new Event('change'));
    describeFilters();
  });
  describeFilters();

  byId('sourceDetailsToggle').addEventListener('click', () => {
    const hidden = !byId('sourceDetails').hidden;
    byId('sourceDetails').hidden = hidden;
    byId('sourceDetailsToggle').setAttribute('aria-expanded', String(!hidden));
  });
  function refreshSnapshotStatus() {
    const updated = byId('updated');
    const text = updated.textContent;
    const compact = text.match(/Подборка обновлена: (.+?)\. Версия анализа:/);
    byId('previewUpdated').textContent = compact ? 'Обновлено ' + compact[1] : text;
    byId('previewUpdated').classList.toggle('error', updated.classList.contains('error'));
    if (updated.classList.contains('error')) byId('previewUpdated').textContent += ' · данные могут быть устаревшими';
  }
  new MutationObserver(refreshSnapshotStatus).observe(byId('updated'), {childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ['class']});
  refreshSnapshotStatus();

  let visibleCount = 12;
  function paginate() {
    const cards = Array.from(byId('articles').querySelectorAll('.publication'));
    cards.forEach((card, index) => { card.hidden = index >= visibleCount; });
    byId('listPagination').hidden = !cards.length;
    byId('shownCounter').textContent = 'На экране ' + Math.min(cards.length, visibleCount) + ' из ' + cards.length;
    byId('previewMore').hidden = visibleCount >= cards.length;
    if (byId('articles').querySelector('.loading-message')) return;
    byId('articles').setAttribute('aria-busy', 'false');
  }
  new MutationObserver(() => { visibleCount = 12; paginate(); }).observe(byId('articles'), {childList: true});
  byId('previewMore').addEventListener('click', () => {
    const next = byId('articles').querySelectorAll('.publication')[visibleCount];
    visibleCount += 12;
    paginate();
    if (next) { next.tabIndex = -1; next.focus({preventScroll: true}); }
  });
  paginate();
  function reflectError() {
    const failed = !byId('error').hidden;
    byId('loadError').hidden = !failed;
    if (failed) {
      byId('articles').setAttribute('aria-busy', 'false');
      byId('articles').querySelector('.loading-message')?.remove();
    }
  }
  new MutationObserver(reflectError).observe(byId('error'), {attributes: true, attributeFilter: ['hidden']});
  byId('retrySnapshot').addEventListener('click', () => location.reload());
  reflectError();
})();
