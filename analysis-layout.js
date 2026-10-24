/* Native mobile filter disclosure and reset; article analysis is unchanged. */
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
})();
