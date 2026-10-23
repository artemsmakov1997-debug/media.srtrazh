/* Presentation-only filters and publication dates; production analysis code is unchanged. */
(() => {
  'use strict';
  const panel = document.getElementById('filterPanel');
  const fields = ['source', 'platform', 'marker'].map(id => document.getElementById(id));
  const reset = document.getElementById('resetFilters');
  const summary = document.getElementById('filterSummary');
  const mobile = matchMedia('(max-width: 760px)');
  function layout() { panel.open = !mobile.matches; }
  function describe() {
    const selected = fields.filter(field => field.value);
    reset.disabled = selected.length === 0;
    summary.textContent = selected.length
      ? selected.map(field => field.selectedOptions[0].textContent).join(' · ')
      : 'Все издания и площадки';
  }
  layout();
  describe();
  mobile.addEventListener('change', layout);
  panel.addEventListener('toggle', () => {
    if (!mobile.matches && !panel.open) panel.open = true;
  });
  fields.forEach(field => field.addEventListener('change', describe));
  reset.addEventListener('click', () => {
    fields.forEach(field => { field.value = ''; });
    fields[0].dispatchEvent(new Event('change'));
    describe();
  });

  function positionDates() {
    for (const article of document.querySelectorAll('#articles .publication')) {
      if (article.querySelector('.publication-header')) continue;
      const source = article.querySelector('.publication-meta');
      const stamp = Array.from(article.children).find(child =>
        child.tagName === 'P' && child.textContent.startsWith('Дата публикации:'));
      if (!source || !stamp) continue;

      // Reuse the viewer's Moscow time verbatim; no parsing or conversion of source dates.
      const value = stamp.textContent.replace(/^Дата публикации:\s*/, '');
      const parts = /^(\d{2}\.\d{2}\.\d{4}),\s*(.+)$/.exec(value);
      const context = document.createElement('span');
      context.className = 'publication-time-context';
      context.textContent = 'Дата публикации: ';
      const date = document.createElement('span');
      date.className = 'publication-time-date';
      date.textContent = parts ? parts[1] : value;
      stamp.replaceChildren(context, date);
      if (parts) {
        const clock = document.createElement('span');
        clock.className = 'publication-time-clock';
        clock.textContent = parts[2];
        stamp.append(document.createTextNode(' '), clock);
      }
      stamp.classList.remove('muted');
      stamp.classList.add('publication-time');
      const header = document.createElement('div');
      header.className = 'publication-header';
      article.insertBefore(header, source);
      header.append(source, stamp);
    }
  }
  new MutationObserver(positionDates).observe(document.getElementById('articles'), {childList: true});
  positionDates();
})();
