/* The archive reads the same bounded public snapshot as analysis.html. */
'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const list = $('archiveList'), overlay = $('messageModalOverlay');
  const fields = ['source', 'platform', 'marker'].map(id => $(id));
  const comments = new window.PublicationTooltip($('archiveTooltip'));
  const countedStatuses = new Set(['needs_review', 'quoted_candidate', 'context_only']);
  const shortLabels = {emotional_evaluation: 'Оценочная лексика', euphemism_dysphemism: 'Дисфемизмы',
    appeal_to_authority: 'Авторитет', vague_source: 'Размытый источник'};
  const requestedPublisher = new URLSearchParams(location.search).get('publisher') || '';
  let report = null, messages = [], search = '', previousFocus = null, loading = false, refreshFailed = false, filtersInitialized = false;
  function node(tag, text = '', className = '') {
    const result = document.createElement(tag);
    result.textContent = text;
    if (className) result.className = className;
    return result;
  }
  function date(value) {
    return value && Number.isFinite(Date.parse(value))
      ? new Date(value).toLocaleString('ru-RU', {timeZone: 'Europe/Moscow', day: '2-digit',
          month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit'}) + ' МСК'
      : 'Дата не указана';
  }
  function labels(item) {
    const status = window.MediaPublisherStatuses?.[item.publisher] || {};
    return [status.foreignAgent && 'иноагент', status.undesirable && 'нежелательная организация'].filter(Boolean);
  }
  function publisherElement(item, className) {
    const result = node('div', '', className);
    result.append(node('span', item.media));
    for (const label of labels(item)) {
      const line = node('small', label, 'archive-publisher-status');
      const checkedAt = window.MediaPublisherStatuses[item.publisher].checkedAt || '12.10.2026';
      line.title = 'Справочный статус в РФ, проверен ' + checkedAt + '. Не влияет на оценку текста.';
      result.append(line);
    }
    return result;
  }
  function original(item) {
    try {
      const url = new URL(item.raw.url), source = item.source;
      if (url.protocol !== 'https:' || url.username || url.password || (url.port && url.port !== '443')) return null;
      if (source.platform === 'telegram') {
        const post = url.pathname.match(/^\/([^/]+)\/([1-9]\d*)\/?$/);
        if (url.hostname !== 't.me' || !post || !source.channel ||
            post[1].toLowerCase() !== source.channel.toLowerCase() || url.search || url.hash) return null;
      } else if (!source.allowed_hosts?.includes(url.hostname)) return null;
      const link = node('a', 'Смотреть источник', 'source-link');
      link.href = url.href; link.target = '_blank'; link.rel = 'noopener noreferrer';
      return link;
    } catch { return null; }
  }
  function adapt(data) {
    if (data?.schema_version !== 'public-snapshot-1.0' || !Array.isArray(data.articles) ||
        data.articles.length > 100 || !Array.isArray(data.sources) || data.sources.length > 200 ||
        !Array.isArray(data.coverage) || !Number.isFinite(Date.parse(data.generated_at))) throw Error('format');
    const sources = new Map(data.sources.map(source => [source.id, source]));
    const types = new Set(data.coverage.map(type => type.id));
    return data.articles.map(raw => {
      const source = sources.get(raw.source_id);
      if (!source || typeof raw.source !== 'string' || !Array.isArray(raw.findings) || raw.findings.length > 40) throw Error('article');
      const active = raw.findings.filter(f => types.has(f.category) && countedStatuses.has(f.status));
      const categories = [...new Map(active.map(f => [f.category, shortLabels[f.category] || f.label])).values()];
      const publisher = source.publisher_id || raw.publisher_id || raw.source_id;
      const website = data.sources.find(s => s.id === publisher);
      const media = website?.name || raw.source.replace(/\s*·\s*Telegram$/, '');
      const title = raw.title || raw.display_excerpt || raw.message_preview || 'Публикация в Telegram';
      const hasCandidates = active.length > 0 || (raw.summary?.marker_fragments ?? raw.summary?.candidate_fragments) > 0;
      const status = !raw.summary ? 'pending' : hasCandidates ? 'danger' : raw.findings.length ? 'risky' : 'neutral';
      const category = status === 'pending' ? 'Не проверено' : !categories.length
        ? status === 'danger' ? 'Есть признаки' : status === 'risky' ? 'Контекст' : 'Не найдены'
        : categories[0] + (categories.length > 1 ? ' +' + (categories.length - 1) : '');
      return {raw, source, publisher, media, title, active, status, category};
    });
  }
  function populateFilters(data) {
    const previousSource = filtersInitialized ? $('source').value : requestedPublisher;
    const previousMarker = $('marker').value;
    const publishers = new Map();
    for (const source of data.sources) {
      const id = source.publisher_id || source.id;
      const website = data.sources.find(s => s.id === id);
      if (!publishers.has(id)) publishers.set(id, website?.name || source.name.replace(/\s*·\s*Telegram$/, ''));
    }
    $('source').replaceChildren(new Option('Все издания', ''), ...[...publishers].map(([id, name]) => {
      const legal = labels({publisher:id});
      return new Option(name + (legal.length ? ' (' + legal.join(', ') + ')' : ''), id);
    }));
    if (publishers.has(previousSource)) $('source').value = previousSource;
    const categories = data.coverage.filter(c => c.coverage === 'candidate_rules' || c.coverage === 'context_notices');
    $('marker').replaceChildren(new Option('Все маркеры', ''), ...categories.map(c => new Option(c.label, c.id)));
    if (categories.some(c => c.id === previousMarker)) $('marker').value = previousMarker;
    filtersInitialized = true;
  }
  function publicationTime(value) {
    const valid = value && Number.isFinite(Date.parse(value));
    const time = node(valid ? 'time' : 'span', '', 'cell-time publication-time');
    if (valid) {
      time.dateTime = value;
      const stamp = new Date(value);
      time.append(node('span', stamp.toLocaleTimeString('ru-RU', {timeZone:'Europe/Moscow'}) + ' МСК', 'publication-time-clock'),
        node('span', stamp.toLocaleDateString('ru-RU', {timeZone:'Europe/Moscow'}), 'publication-time-date'));
    } else time.textContent = 'Дата не указана';
    return time;
  }
  function excerpt(group) {
    const p = node('p'), chars = Array.from(group.sentence.text), spans = [];
    for (const {finding, evidence} of group.evidences) {
      const start = evidence.start - group.sentence.start, end = evidence.end - group.sentence.start;
      if (start < 0 || start >= end || end > chars.length || chars.slice(start, end).join('') !== evidence.quote) continue;
      spans.push({start, end, finding});
    }
    const points = [...new Set([0, chars.length, ...spans.flatMap(s => [s.start, s.end])])].sort((a,b) => a-b);
    for (let i = 1; i < points.length; i++) {
      const start = points[i-1], end = points[i], text = chars.slice(start, end).join('');
      const matches = spans.filter(s => s.start <= start && s.end >= end);
      if (!matches.length) {p.append(document.createTextNode(text)); continue;}
      const mark = node('mark', text, 'auto-modal-highlight');
      mark.dataset.label = [...new Set(matches.map(s => s.finding.label))].join(' · ');
      mark.dataset.explanation = [...new Set(matches.map(s => {
        const f = s.finding;
        const prefix = f.evidence?.some(e => e.context?.informational_notice) ? 'Информационная отметка — не признак манипуляции. '
          : f.status === 'context_only' ? 'Контекст или обсуждение. '
          : f.status === 'quoted_candidate' ? 'Цитата или переданная речь — проверьте автора высказывания. ' : 'Требует проверки. ';
        return prefix + f.explanation + ' ' + f.review_question;
      }))].join(' ');
      mark.setAttribute('aria-label', text + ': ' + mark.dataset.label);
      comments.bind(mark);
      p.append(mark);
    }
    return p;
  }
  function openModal(item, trigger) {
    previousFocus = trigger || document.activeElement;
    comments.hide();
    $('messageModalTitle').textContent = item.title;
    $('modalMedia').replaceChildren(publisherElement(item, ''));
    $('modalTime').textContent = date(item.raw.published_at);
    $('modalCategory').textContent = [...new Set(item.raw.findings.map(f => f.label))].join(' · ') || item.category;
    const body = $('modalFullText'); body.replaceChildren();
    const groups = new Map();
    for (const finding of item.raw.findings) for (const evidence of finding.evidence || []) {
      if (typeof evidence.sentence?.text !== 'string') continue;
      const key = evidence.field + ':' + evidence.sentence.start + ':' + evidence.sentence.text;
      if (!groups.has(key)) groups.set(key, {sentence: evidence.sentence, evidences: []});
      groups.get(key).evidences.push({finding, evidence});
    }
    for (const group of groups.values()) body.append(excerpt(group));
    if (!groups.size) body.append(node('p', item.raw.message_preview || item.title));
    body.append(node('p', 'Показаны сохранённые фрагменты, а не полный текст публикации. Полный материал доступен у источника.', 'archive-context-note'));
    if (item.raw.findings_omitted) body.append(node('p', 'Других сохранённых меток: ' + item.raw.findings_omitted + '.', 'archive-context-note'));
    body.append(node('p', 'Найденные признаки требуют проверки; они не доказывают манипуляцию, намерение автора или ложность фактов.', 'archive-context-note'));
    body.append(node('p', 'Отсутствие признаков не означает нейтральность текста.', 'archive-context-note'));
    overlay.classList.add('open'); overlay.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden'; $('messageCloseBtn').focus();
  }
  function closeModal() {
    if (!overlay.classList.contains('open')) return;
    comments.hide();
    overlay.classList.remove('open'); overlay.setAttribute('aria-hidden', 'true'); document.body.style.overflow = '';
    if (previousFocus?.isConnected) previousFocus.focus();
  }
  function createItem(item) {
    const article = node('article', '', 'archive-item');
    article.dataset.id = String(item.raw.id); article.dataset.publisher = item.publisher; article.dataset.status = item.status;
    const row = node('div', '', 'archive-summary');
    row.append(publisherElement(item, 'cell-media'));
    row.append(publicationTime(item.raw.published_at), node('div', item.title, 'cell-title'));
    const summary = item.raw.summary;
    row.append(node('p', summary ? 'Найдено фрагментов для проверки: ' + (summary.marker_fragments ?? summary.candidate_fragments ?? summary.review_fragments)
      : 'Анализ текущей версии отсутствует.', 'cell-count'));
    const cell = node('div', '', 'cell-button'), button = node('button', 'Подробнее', 'more-btn');
    button.type = 'button'; button.setAttribute('aria-label', 'Разбор: ' + item.title);
    button.addEventListener('click', () => openModal(item, button));
    row.addEventListener('click', event => {if (!event.target.closest('button,a')) openModal(item, button);});
    cell.append(button); row.append(cell);
    const sourceCell = node('div', '', 'cell-original');
    sourceCell.append(original(item) || node('span', 'Источник недоступен', 'source-unavailable'));
    row.append(sourceCell); article.append(row); return article;
  }
  function render() {
    const term = search.trim().toLocaleLowerCase('ru');
    const source = $('source').value, platform = $('platform').value, marker = $('marker').value;
    $('resetFilters').disabled = fields.every(field => !field.value) && !term;
    const selected = messages.filter(item => (!source || item.publisher === source) &&
      (!platform || item.source.platform === platform) && (!marker || item.raw.findings.some(f => f.category === marker)) && (!term ||
        [item.media, item.title, item.raw.message_preview, ...item.raw.findings.flatMap(f =>
          [f.label, f.explanation, ...f.evidence.map(e => e.quote)])].join(' ').toLocaleLowerCase('ru').includes(term)));
    const visible = selected.slice(0, 10);
    list.replaceChildren(...visible.map(createItem));
    if (!visible.length) list.append(node('div', 'Публикации по заданным условиям не найдены.', 'empty-state'));
    if (report) {
      const stale = Date.now() - Date.parse(report.generated_at) > 2 * 3600000;
      const publisherName = source && (messages.find(item => item.publisher === source)?.media ||
        report.sources.find(s => s.publisher_id === source)?.name);
      $('rtText').textContent = (refreshFailed ? 'Не удалось обновить. Данные от ' : 'Обновлено: ') + date(report.generated_at) +
        '. Показано: ' + visible.length + (publisherName ? '. Фильтр СМИ: ' + publisherName : '') +
        '. Часть собранных публикаций; полный охват СМИ не гарантирован.' + (stale ? ' Данные не обновлялись более двух часов.' : '');
    }
  }
  async function load() {
    if (loading) return;
    loading = true;
    const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch('data/analysis.json', {cache: 'no-store', signal: controller.signal});
      if (!response.ok) throw Error('http');
      const text = await response.text(); if (text.length > 8000000) throw Error('size');
      const next = JSON.parse(text), items = adapt(next);
      populateFilters(next); report = next; messages = items; refreshFailed = false; render();
    } catch {
      refreshFailed = true;
      if (!report) list.replaceChildren(node('div', 'Не удалось загрузить реальные публикации. Попробуйте обновить страницу позже.', 'empty-state'));
      $('rtText').textContent = report ? 'Не удалось обновить подборку. Показаны данные от ' + date(report.generated_at) + '.'
        : 'Данные анализа недоступны.';
    } finally { clearTimeout(timeout); loading = false; }
  }
  fields.forEach(field => field.addEventListener('change', render));
  $('resetFilters').addEventListener('click', () => {
    fields.forEach(field => {field.value = '';});
    $('searchInput').value = ''; search = ''; render();
  });
  $('searchInput').addEventListener('input', event => {search = event.target.value; render();});
  function placeholder() {
    $('searchInput').placeholder = matchMedia('(max-width:767px)').matches ? 'Поиск: СМИ, заголовок, приём' : 'Найти по СМИ, заголовку или типу манипуляции';
  }
  placeholder(); window.addEventListener('resize', placeholder, {passive: true});
  $('messageCloseBtn').addEventListener('click', closeModal);
  overlay.addEventListener('click', event => {
    if (event.target === overlay) closeModal();
    else if (!event.target.closest('.auto-modal-highlight')) comments.hide();
  });
  const burger = $('burgerBtn'), nav = $('navLinks');
  function closeNav() {nav.classList.remove('open'); burger.setAttribute('aria-expanded', 'false');}
  burger.addEventListener('click', () => {const open = nav.classList.toggle('open'); burger.setAttribute('aria-expanded', String(open));});
  nav.querySelectorAll('a').forEach(a => a.addEventListener('click', closeNav));
  document.addEventListener('click', event => {if (!nav.contains(event.target) && !burger.contains(event.target)) closeNav();});
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') {closeModal(); closeNav();}
    if (event.key !== 'Tab' || !overlay.classList.contains('open')) return;
    const controls = [...overlay.querySelectorAll('button,a[href],[tabindex="0"]')].filter(el => el.getClientRects().length);
    const first = controls[0], last = controls[controls.length-1];
    if (event.shiftKey && document.activeElement === first) {event.preventDefault(); last.focus();}
    else if (!event.shiftKey && document.activeElement === last) {event.preventDefault(); first.focus();}
  });
  list.append(node('div', 'Загружаем реальные публикации…', 'empty-state'));
  load(); setInterval(() => {if (!document.hidden && !overlay.classList.contains('open')) load();}, 300000);
})();
