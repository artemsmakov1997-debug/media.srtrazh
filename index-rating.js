/* Full-corpus rating snapshot. No synthetic outlets, counters or chart points. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const ns = 'http://www.w3.org/2000/svg';
  const motion = matchMedia('(prefers-reduced-motion: reduce)');
  const mobile = () => matchMedia('(max-width: 767px)').matches;
  const desktop = () => matchMedia('(min-width: 1024px)').matches;
  const number = value => value.toLocaleString('ru-RU');
  const percent = value => value === null ? '—' : value.toLocaleString('ru-RU', {maximumFractionDigits: 2}) + '%';
  const date = value => new Date(value).toLocaleString('ru-RU', {
    timeZone: 'Europe/Moscow', day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit'
  }) + ' МСК';
  const label = level => ({red: 'Высокий показатель', yellow: 'Средний показатель', green: 'Низкий показатель'}[level] || 'Нет данных');
  const levelFor = (flagged, collected) => !collected ? null : flagged * 4 < collected ? 'green' : flagged * 2 > collected ? 'red' : 'yellow';
  const count = value => Number.isSafeInteger(value) && value >= 0;
  const node = (tag, text = '', className = '') => {
    const result = document.createElement(tag);
    result.textContent = text;
    if (className) result.className = className;
    return result;
  };
  let report = null, media = [], offset = 0, active = 0, cycle = null, loading = false, loadError = false;
  let currentModal = null, modalTrigger = null, oldOverflow = '', inertElements = [];

  function validate(data) {
    if (data?.schema_version !== 'rating-snapshot-1.0' || !Array.isArray(data.publishers) ||
        !Number.isFinite(Date.parse(data.generated_at)) || data.window?.hours !== 24 ||
        !Number.isFinite(Date.parse(data.window.start_at)) || !Number.isFinite(Date.parse(data.window.end_at)) ||
        Date.parse(data.window.end_at) - Date.parse(data.window.start_at) !== 86400000 ||
        data.chart?.kind !== 'cumulative_share' || data.publishers.length > 200) throw Error('format');
    const ids = new Set();
    const sums = {collected: 0, analyzed: 0, flagged: 0};
    for (const row of data.publishers) {
      if (!/^[a-z][a-z0-9_]{0,63}$/.test(row.id) || ids.has(row.id) ||
          typeof row.name !== 'string' || !row.name.trim() || row.name.length > 300 ||
          !Array.isArray(row.platforms) || !row.platforms.every(value => ['website', 'telegram'].includes(value)) ||
          !Array.isArray(row.sources) || !Array.isArray(row.series) || row.series.length !== 24 ||
          ![row.collected, row.analyzed, row.flagged].every(count) || row.flagged > row.analyzed || row.analyzed > row.collected) throw Error('outlet');
      ids.add(row.id);
      const expected = row.collected && row.analyzed === row.collected ? 100 * row.flagged / row.collected : null;
      if ((expected === null && (row.score_percent !== null || row.level !== null)) ||
          (expected !== null && (!Number.isFinite(row.score_percent) || Math.abs(row.score_percent - expected) > 0.00001 ||
          row.level !== levelFor(row.flagged, row.collected)))) throw Error('ratio');
      const running = {collected: 0, analyzed: 0, flagged: 0};
      for (const [index, point] of row.series.entries()) {
        if (![point.collected, point.analyzed, point.flagged].every(count) ||
            point.flagged > point.analyzed || point.analyzed > point.collected ||
            Date.parse(point.end_at) !== Date.parse(data.window.start_at) + (index + 1) * 3600000) throw Error('chart');
        for (const key of Object.keys(running)) {
          running[key] += point[key];
          if (point['cumulative_' + key] !== running[key]) throw Error('cumulative');
        }
        const score = running.collected && running.analyzed === running.collected ? 100 * running.flagged / running.collected : null;
        if (score === null ? point.score_percent !== null : !Number.isFinite(point.score_percent) || Math.abs(point.score_percent - score) > 0.00001) throw Error('chart ratio');
      }
      for (const key of Object.keys(sums)) {
        if (running[key] !== row[key]) throw Error('chart totals');
        sums[key] += row[key];
      }
    }
    if (Object.keys(sums).some(key => data.totals?.[key] !== sums[key])) throw Error('totals');
    return data;
  }

  function statusLabels(id) {
    const status = window.MediaPublisherStatuses?.[id];
    return [status?.foreignAgent && 'иноагент', status?.undesirable && 'нежелательная организация'].filter(Boolean);
  }

  function platformText(row) {
    return row.platforms.map(platform => platform === 'telegram' ? 'Telegram' : 'Сайт').join(' · ');
  }

  function healthText(row) {
    const errors = row.sources.filter(source => ['error', 'partial'].includes(source.state)).length;
    const stale = row.sources.filter(source => source.state === 'stale').length;
    return 'Ограниченная выборка' + (errors ? ` · ошибок сбора: ${errors}` : '') + (stale ? ` · без свежих данных: ${stale}` : '');
  }

  function makeGraph(row, width = 200, height = 36) {
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
    svg.setAttribute('preserveAspectRatio', 'none');
    svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', `${row.name}. Накопительная доля публикаций с признаками за 24 часа, шкала 0–100%. Итог: ${percent(row.score_percent)}.`);
    const color = {red: '#ef4444', yellow: '#eab308', green: '#22c55e'}[row.level] || '#acbdc8';
    const descriptions = [], paths = [];
    let path = '', previous = false;
    row.series.forEach((point, index) => {
      if (point.score_percent === null) {
        if (path) paths.push(path);
        path = ''; previous = false; return;
      }
      const x = 4 + index * (width - 8) / 23;
      const y = 4 + (100 - point.score_percent) * (height - 8) / 100;
      path += previous ? ` H${x.toFixed(2)} V${y.toFixed(2)}` : `M${x.toFixed(2)},${y.toFixed(2)}`;
      previous = true;
      const dot = document.createElementNS(ns, 'circle');
      dot.setAttribute('cx', x.toFixed(2)); dot.setAttribute('cy', y.toFixed(2));
      dot.setAttribute('r', '1.5'); dot.setAttribute('fill', color);
      dot.dataset.score = String(point.score_percent);
      dot.dataset.collected = String(point.cumulative_collected);
      dot.dataset.flagged = String(point.cumulative_flagged);
      dot.dataset.endAt = point.end_at;
      const title = document.createElementNS(ns, 'title');
      title.textContent = `${date(point.end_at)}: ${point.cumulative_flagged} из ${point.cumulative_collected}, ${percent(point.score_percent)}`;
      descriptions.push(title.textContent);
      dot.append(title); svg.append(dot);
    });
    if (path) paths.push(path);
    for (const coordinates of paths) {
      const line = document.createElementNS(ns, 'path');
      line.setAttribute('d', coordinates); line.setAttribute('fill', 'none');
      line.setAttribute('stroke', color); line.setAttribute('stroke-width', '1.5');
      line.setAttribute('stroke-linejoin', 'round'); svg.prepend(line);
    }
    const description = document.createElementNS(ns, 'desc');
    description.textContent = descriptions.join('; '); svg.prepend(description);
    return descriptions.length ? svg : node('span', 'Нет точек для графика', 'rating-graph-empty');
  }

  function examplesLink(row) {
    const link = node('a', 'Смотреть примеры', 'link-button');
    link.href = '/analysis/?source=' + encodeURIComponent(row.id);
    return link;
  }

  function drawCard(row) {
    const card = node('article', '', 'media-card');
    card.dataset.publisher = row.id;

    const header = node('div', '', 'media-card-header');
    const identity = node('div', '', 'media-logo');
    const initials = row.name.trim().split(/\s+/).map(part => part[0]).slice(0, 2).join('').toUpperCase();
    const icon = node('div', initials, 'logo-icon');
    icon.setAttribute('aria-hidden', 'true');

    const names = node('div', '', 'media-identity-text');
    names.append(node('div', row.name, 'media-name'));
    const statuses = statusLabels(row.id);
    if (statuses.length) {
      const legal = node('div', '', 'media-legal-status');
      for (const status of statuses) {
        const tag = node('span', status, 'media-status-tag');
        tag.title = status === 'иноагент'
          ? 'Издание включено в реестр иностранных агентов'
          : 'Издание имеет статус нежелательной организации';
        legal.append(tag);
      }
      names.append(legal);
    }
    identity.append(icon, names);

    const score = node('div', '', 'rating-block');
    const value = node('div', percent(row.score_percent), 'rating-score ' + (row.level || 'no-data') + '-score');
    value.setAttribute('aria-label', 'Доля собранных публикаций с признаками: ' + percent(row.score_percent));
    score.append(value);
    header.append(identity, score);

    const graph = node('div', '', 'small-graph');
    graph.append(makeGraph(row));
    graph.tabIndex = 0;

    const footer = node('div', '', 'media-footer');
    footer.append(examplesLink(row));
    card.append(header, graph, footer);
    return card;
  }

  function renderCards() {
    $('mediaGrid').replaceChildren(); $('mediaDots').replaceChildren();
    $('mediaGrid').classList.toggle('is-mobile-slider', mobile());
    const count = mobile() ? media.length : Math.min(desktop() ? 3 : 4, media.length);
    for (let index = 0; index < count; index++) {
      const row = media[mobile() ? index : (offset + index) % media.length];
      const card = drawCard(row);
      if (mobile()) {
        card.classList.toggle('is-active', index === active);
        card.setAttribute('aria-hidden', String(index !== active));
        card.inert = index !== active;
      }
      $('mediaGrid').append(card);
    }
    if (mobile()) media.forEach((row, index) => {
      const dot = node('button', '', 'media-dot' + (index === active ? ' active' : ''));
      dot.type = 'button'; dot.setAttribute('aria-label', 'Показать ' + row.name);
      dot.setAttribute('aria-pressed', String(index === active));
      dot.addEventListener('click', () => {
        active = index; renderCards(); $('mediaDots').children[index]?.focus({preventScroll: true}); restartCycle();
      });
      $('mediaDots').append(dot);
    });
  }

  function stopCycle() { clearInterval(cycle); cycle = null; }
  function restartCycle() {
    stopCycle();
    if (motion.matches || currentModal || document.hidden || media.length < 2 ||
        $('mediaGrid').contains(document.activeElement) || $('mediaDots').contains(document.activeElement)) return;
    cycle = setInterval(() => {
      if (mobile()) active = (active + 1) % media.length;
      else offset = (offset + (desktop() ? 3 : 4)) % media.length;
      renderCards();
    }, mobile() ? 4200 : 5000);
  }

  function filteredMedia() {
    const query = $('modalSearch').value.trim().toLocaleLowerCase('ru-RU');
    const sort = $('modalSort').value;
    return media.filter(row => row.name.toLocaleLowerCase('ru-RU').includes(query)).sort((a, b) => {
      if (sort === 'name-asc') return a.name.localeCompare(b.name, 'ru');
      if (sort === 'name-desc') return b.name.localeCompare(a.name, 'ru');
      if (a.score_percent === null || b.score_percent === null) return Number(a.score_percent === null) - Number(b.score_percent === null) || a.name.localeCompare(b.name, 'ru');
      const ascending = ['rating-asc', 'level-green'].includes(sort);
      return (ascending ? a.score_percent - b.score_percent : b.score_percent - a.score_percent) || a.name.localeCompare(b.name, 'ru');
    });
  }

  function renderFullList() {
    const container = $('fullListContainer'); container.replaceChildren();
    const rows = filteredMedia();
    if (!rows.length) { container.append(node('p', report ? 'Ничего не найдено' : 'Данные рейтинга пока недоступны.', 'modal-empty')); return; }
    for (const item of rows) {
      const row = node('div', '', 'full-list-row'); row.dataset.publisher = item.id;
      const name = node('div', '', 'fli-name');
      name.append(node('div', item.name, 'title'),
                  node('div', `${platformText(item)} · ${item.flagged} из ${item.collected} с признаками · проверено ${item.analyzed}` +
                    (statusLabels(item.id).length ? ' · ' + statusLabels(item.id).join(', ') : ''), 'type'));
      const graph = node('div', '', 'fli-graph'); graph.append(makeGraph(item, 120, 28)); graph.tabIndex = 0;
      row.append(name, graph, node('div', percent(item.score_percent), 'fli-rating ' + (item.level || 'no-data')),
                 node('div', item.rating_state === 'analysis_pending' ? 'Анализ не завершён' : label(item.level), 'fli-badge ' + (item.level || 'no-data')));
      container.append(row);
    }
  }

  function closeModal(restore = true) {
    if (!currentModal) return;
    currentModal.classList.remove('open'); currentModal.setAttribute('aria-hidden', 'true');
    $('appealLink').setAttribute('aria-expanded', 'false');
    document.body.style.overflow = oldOverflow;
    for (const [element, previous] of inertElements) element.inert = previous;
    inertElements = []; currentModal = null;
    if (restore && modalTrigger?.isConnected) modalTrigger.focus();
    modalTrigger = null; restartCycle();
  }

  function openModal(id, trigger) {
    closeModal(false); stopCycle();
    currentModal = $(id); modalTrigger = trigger; oldOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    for (const element of document.body.children) {
      if (element !== currentModal && !['SCRIPT', 'STYLE', 'LINK'].includes(element.tagName)) {
        inertElements.push([element, element.inert]); element.inert = true;
      }
    }
    currentModal.classList.add('open'); currentModal.setAttribute('aria-hidden', 'false');
    if (id === 'fullListModal') {
      $('modalSearch').value = ''; $('modalSort').value = 'rating-desc'; renderFullList(); $('modalSearch').focus();
    } else {
      $('appealLink').setAttribute('aria-expanded', 'true'); $('appealPublisher').focus();
    }
  }

  function updateStatus() {
    if (!report) return;
    const stale = Date.now() - Date.parse(report.generated_at) > 2 * 3600000;
    const warning = loadError
      ? 'Не удалось обновить рейтинг. Показана последняя доступная выборка.'
      : stale ? 'Данные рейтинга могут быть устаревшими.' : '';
    $('ratingStatus').hidden = !warning;
    $('ratingStatus').classList.toggle('is-stale', Boolean(warning));
    $('ratingStatus').textContent = warning;
  }

  async function loadRating() {
    if (loading) return;
    loading = true;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch('data/rating.json', {cache: 'no-store', signal: controller.signal});
      if (!response.ok) throw Error('HTTP ' + response.status);
      const next = validate(await response.json());
      const selected = media[active]?.id;
      report = next; media = next.publishers; loadError = false;
      active = Math.max(0, media.findIndex(row => row.id === selected)); offset = 0;
      $('dailyCounterValue').textContent = $('dailyCounterMobile').textContent = number(report.totals.flagged);
      $('ratingRetry').hidden = true; updateStatus(); renderCards(); restartCycle();
      $('appealPublishers').replaceChildren(...media.map(row => {
        const option = node('option'); option.value = row.name; return option;
      }));
      if (currentModal?.id === 'fullListModal') renderFullList();
    } catch (_) {
      loadError = true; $('ratingRetry').hidden = false;
      if (report) updateStatus();
      else $('ratingStatus').textContent = 'Рейтинг пока недоступен. Повторите загрузку после обновления данных.';
    } finally { clearTimeout(timer); loading = false; }
  }

  document.querySelectorAll('.show-full-list-trigger').forEach(button => button.addEventListener('click', () => openModal('fullListModal', button)));
  $('appealLink').addEventListener('click', event => { event.preventDefault(); openModal('appealModal', event.currentTarget); });
  $('fullListCloseBtn').addEventListener('click', () => closeModal());
  $('appealCloseBtn').addEventListener('click', () => closeModal());
  for (const id of ['fullListModal', 'appealModal']) $(id).addEventListener('click', event => {
    if (event.target === $(id)) closeModal();
  });
  $('modalSearch').addEventListener('input', renderFullList); $('modalSort').addEventListener('change', renderFullList);
  $('ratingRetry').addEventListener('click', loadRating);
  $('appealForm').addEventListener('input', () => {
    $('appealUrl').setCustomValidity(''); $('appealPublisher').setCustomValidity('');
    $('appealExplanation').setCustomValidity(''); $('appealStatus').textContent = '';
  });
  $('appealForm').addEventListener('reset', () => {
    for (const id of ['appealPublisher', 'appealUrl', 'appealExplanation']) $(id).setCustomValidity('');
    $('appealStatus').textContent = '';
  });
  $('appealForm').addEventListener('submit', event => {
    event.preventDefault();
    const publisher = $('appealPublisher').value.trim(), url = $('appealUrl').value.trim(), explanation = $('appealExplanation').value.trim();
    if (!publisher) $('appealPublisher').setCustomValidity('Укажите СМИ.');
    if (explanation.length < 10) $('appealExplanation').setCustomValidity('Объясните ошибку хотя бы в 10 символах.');
    if (url) {
      try { if (!['https:', 'http:'].includes(new URL(url).protocol)) throw Error(); }
      catch (_) { $('appealUrl').setCustomValidity('Укажите ссылку, начинающуюся с https:// или http://.'); }
    }
    if (!$('appealForm').reportValidity()) return;
    const text = `Апелляция — МЕДИА.СТРАЖ\nСМИ: ${publisher}\nСсылка: ${url || 'Не указана'}\n\nГде ошибся алгоритм и почему:\n${explanation}\n`;
    const blob = URL.createObjectURL(new Blob([text], {type: 'text/plain;charset=utf-8'}));
    const link = node('a'); link.href = blob; link.download = 'media-strazh-appeal.txt'; link.click();
    setTimeout(() => URL.revokeObjectURL(blob), 10000);
    $('appealStatus').textContent = 'Текст апелляции подготовлен для сохранения на устройство. Отправка на почту пока не подключена.';
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') { closeModal(); $('navLinks')?.classList.remove('open'); $('burgerBtn')?.setAttribute('aria-expanded', 'false'); }
    if (event.key !== 'Tab' || !currentModal) return;
    const controls = [...currentModal.querySelectorAll('a[href],button,input,select,textarea,[tabindex="0"]')].filter(control => !control.disabled && control.getClientRects().length);
    const first = controls[0], last = controls[controls.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  });
  const burger = $('burgerBtn'), navigation = $('navLinks');
  burger?.addEventListener('click', () => burger.setAttribute('aria-expanded', String(navigation.classList.toggle('open'))));
  navigation?.querySelectorAll('a').forEach(link => link.addEventListener('click', () => { navigation.classList.remove('open'); burger.setAttribute('aria-expanded', 'false'); }));
  document.addEventListener('click', event => {
    if (burger && !navigation.contains(event.target) && !burger.contains(event.target)) {
      navigation.classList.remove('open'); burger.setAttribute('aria-expanded', 'false');
    }
  });
  $('mediaGrid').addEventListener('pointerenter', stopCycle); $('mediaGrid').addEventListener('pointerleave', restartCycle);
  $('mediaGrid').addEventListener('focusin', stopCycle); $('mediaGrid').addEventListener('focusout', () => setTimeout(restartCycle, 0));
  document.addEventListener('visibilitychange', () => { restartCycle(); if (!document.hidden) loadRating(); });
  motion.addEventListener('change', restartCycle);
  let resize = null;
  window.addEventListener('resize', () => { clearTimeout(resize); resize = setTimeout(() => { renderCards(); restartCycle(); }, 150); });
  setInterval(() => { if (!document.hidden) loadRating(); }, 300000);
  setInterval(updateStatus, 60000);
  loadRating();
})();
