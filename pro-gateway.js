/* Единый выбор PRO: работает в навигации всех публичных страниц. */
(() => {
  'use strict';
  let overlay = null;
  let previousFocus = null;
  let previousOverflow = '';

  function createDialog() {
    if (overlay) return overlay;
    overlay = document.createElement('div');
    overlay.className = 'pro-gateway-overlay';
    overlay.hidden = true;
    overlay.innerHTML = `
      <section class="pro-gateway-dialog" role="dialog" aria-modal="true"
        aria-labelledby="proGatewayTitle" aria-describedby="proGatewayDescription">
        <button type="button" class="pro-gateway-close" aria-label="Закрыть выбор PRO">×</button>
        <p class="pro-gateway-kicker">МЕДИА.СТРАЖ <b>PRO</b></p>
        <h2 class="pro-gateway-title" id="proGatewayTitle">Возможности PRO для ваших задач</h2>
        <p class="pro-gateway-subtitle" id="proGatewayDescription">
          Два направления на основе анализа медиаполя: изучайте медиатексты или находите возможности для продвижения компании.
        </p>
        <div class="pro-gateway-options">
          <a class="pro-gateway-option pro-gateway-option--research" href="analysis.html">
            <span class="pro-gateway-icon" aria-hidden="true">⌕</span>
            <div>
              <h3>Исследования</h3>
              <p class="pro-gateway-audience">Исследователям · журналистам · преподавателям</p>
            </div>
            <ul class="pro-gateway-benefits">
              <li>Глубокое изучение медиатекстов и языковых приёмов воздействия.</li>
              <li>Выделение спорных фрагментов и объяснение найденных маркеров.</li>
              <li>Анализ публикаций СМИ и самостоятельная проверка текстов.</li>
            </ul>
            <span class="pro-gateway-cta">Перейти к исследованиям <span aria-hidden="true">↗</span></span>
          </a>
          <a class="pro-gateway-option pro-gateway-option--business" href="business.html">
            <span class="pro-gateway-icon" aria-hidden="true">↗</span>
            <div>
              <h3>Бизнес</h3>
              <p class="pro-gateway-audience">Предпринимателям · маркетологам · PR-командам</p>
            </div>
            <ul class="pro-gateway-benefits">
              <li>Повышение узнаваемости компании через актуальную медиаповестку.</li>
              <li>Мониторинг упоминаний и поддержка управления репутацией.</li>
              <li>Отраслевые тренды, PR-поводы, подбор СМИ и подготовка релизов.</li>
            </ul>
            <span class="pro-gateway-cta">Открыть бизнес-панель <span aria-hidden="true">↗</span></span>
          </a>
        </div>
        <p class="pro-gateway-footnote">PRO развивается. На бизнес-странице пока представлены демонстрационные данные; оформление подписки ещё не подключено.</p>
      </section>
    `;
    document.body.append(overlay);
    overlay.querySelector('.pro-gateway-close').addEventListener('click', close);
    overlay.addEventListener('click', event => {
      if (event.target === overlay) close();
    });
    overlay.querySelectorAll('a').forEach(link => link.addEventListener('click', close));
    return overlay;
  }

  function open(trigger) {
    const dialog = createDialog();
    if (!dialog.hidden) return;
    previousFocus = trigger || document.activeElement;
    previousOverflow = document.body.style.overflow;
    const nav = document.getElementById('navLinks');
    const burger = document.getElementById('burgerBtn');
    if (nav) nav.classList.remove('open');
    if (burger) burger.setAttribute('aria-expanded', 'false');
    dialog.hidden = false;
    document.body.style.overflow = 'hidden';
    dialog.querySelector('.pro-gateway-close').focus();
  }

  function close() {
    if (!overlay || overlay.hidden) return;
    overlay.hidden = true;
    document.body.style.overflow = previousOverflow;
    if (previousFocus && previousFocus.isConnected) previousFocus.focus();
  }

  document.addEventListener('click', event => {
    const trigger = event.target.closest && event.target.closest('a.pro-nav-link, [data-pro-gateway]');
    if (!trigger || event.defaultPrevented || event.button !== 0 ||
        event.metaKey || event.ctrlKey || event.altKey || event.shiftKey) return;
    event.preventDefault();
    open(trigger);
  });

  document.addEventListener('keydown', event => {
    if (!overlay || overlay.hidden) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      close();
    } else if (event.key === 'Tab') {
      const focusables = [...overlay.querySelectorAll('button:not([disabled]), a[href]')];
      if (!focusables.length) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault(); last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault(); first.focus();
      }
    }
  });
})();
