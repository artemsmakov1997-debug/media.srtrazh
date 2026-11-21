/* Legacy entry points remain ordinary links to PRO; no chooser or overlay. */
(() => {
  document.querySelectorAll('a.pro-nav-link, a[data-pro-gateway]').forEach(link => {
    link.href='/analysis/';
    link.removeAttribute('aria-haspopup');
    link.removeAttribute('data-pro-gateway');
  });
})();
