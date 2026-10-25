/* Existing reference statuses; evidence and check dates: docs/media-statuses.md. */
'use strict';
window.MediaPublisherStatuses = Object.freeze({
  meduza: {foreignAgent: true, undesirable: true},
  novayagazeta: {foreignAgent: false, undesirable: true},
  currenttime: {foreignAgent: true, undesirable: true},
  dw: {foreignAgent: false, undesirable: true},
  mediazona: {foreignAgent: true, undesirable: null, checkedAt: '13.10.2026'}
});
