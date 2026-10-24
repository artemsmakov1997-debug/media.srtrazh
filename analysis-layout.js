/* Always-visible publication filters and reset; article analysis is unchanged. */
(() => {
  'use strict';
  const fields = ['source', 'platform', 'marker'].map(id => document.getElementById(id));
  const reset = document.getElementById('resetFilters');
  function describe() {
    reset.disabled = fields.every(field => !field.value);
  }
  describe();
  fields.forEach(field => field.addEventListener('change', describe));
  reset.addEventListener('click', () => {
    fields.forEach(field => { field.value = ''; });
    fields[0].dispatchEvent(new Event('change'));
    describe();
  });
})();
