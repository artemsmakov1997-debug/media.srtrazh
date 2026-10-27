/* The archive reads the same bounded public snapshot as analysis.html. */
'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const list = $('archiveList'), overlay = $('messageModalOverlay');
  const chips = [...document.querySelectorAll('.chip')];
  const countedStatuses = new Set(['needs_review', 'quoted_candidate']);
  const shortLabels = {emotional_evaluation: 'Оценочная лексика', euphemism_dysphemism: 'Дисфемизмы',
    appeal_to_authority: 'Авторитет', vague_source: 'Размытый источник'};
  const requestedPublisher = new URLSearchParams(location.search).get('publisher') || '';
  let report = null, messages = [], filter = 'all', search = '', previousFocus = null, loading = false;
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
    result.append(node('small', item.platform === 'telegram' ? 'Telegram' : 'Сайт', 'archive-platform'));
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
      const link = node('a', 'Смотреть источник ↗', 'archive-original-link');
      link.href = url.href; link.target = '_blank'; link.rel = 'noopener noreferrer';
      return link;
    } catch { return null; }
  }
  function adapt(data) {
    if (data?.schema_version !== 'public-snapshot-1.0' || !Array.isArray(data.articles) ||
        data.articles.length > 100 || !Array.isArray(data.sources) || data.sources.length > 200 ||
        !Array.isArray(data.coverage) || !Number.isFinite(Date.parse(data.generated_at))) throw Error('format');
    const sources = new Map(data.sources.map(source => [source.id, source]));
    const types = new Set(data.coverage.filter(type => type.coverage !== 'context_notices').map(type => type.id));
    return data.articles.map(raw => {
      const source = sources.get(raw.source_id);
      if (!source || typeof raw.source !== 'string' || !Array.isArray(raw.findings) || raw.findings.length > 40) throw Error('article');
      const active = raw.findings.filter(f => types.has(f.category) && countedStatuses.has(f.status) &&
        !f.evidence?.some(e => e.context?.informational_notice));
      const categories = [...new Map(active.map(f => [f.category, shortLabels[f.category] || f.label])).values()];
      const publisher = source.publisher_id || raw.publisher_id || raw.source_id;
      const website = data.sources.find(s => s.id === publisher);
      const media = website?.name || raw.source.replace(/\s*·\s*Telegram$/, '');
      const title = raw.title || raw.display_excerpt || raw.message_preview || 'Публикация в Telegram';
      const hasCandidates = active.length > 0 || raw.summary?.candidate_fragments > 0;
      const status = !raw.summary ? 'pending' : hasCandidates ? 'danger' : raw.findings.length ? 'risky' : 'neutral';
      const category = status === 'pending' ? 'Не проверено' : !categories.length
        ? status === 'danger' ? 'Есть признаки' : status === 'risky' ? 'Контекст' : 'Не найдены'
        : categories[0] + (categories.length > 1 ? ' +' + (categories.length - 1) : '');
      return {raw, source, publisher, media, title, platform: source.platform, active, status, category};
    });
  }
  function explain(item) {
    const box = $('modalExplain'); box.replaceChildren();
    if (!item.raw.summary) box.append(node('p', 'Для публикации ещё нет анализа текущей версии.'));
    else if (!item.raw.findings.length) box.append(node('p', 'Совпадений текущих правил не найдено.'));
    for (const finding of item.raw.findings) {
      const p = node('p');
      const prefix = finding.evidence?.some(e => e.context?.informational_notice) ? 'Справочная отметка. '
        : finding.status === 'context_only' ? 'Контекст или обсуждение. '
        : finding.status === 'quoted_candidate' ? 'Цитата или переданная речь. ' : 'Требует проверки. ';
      p.append(node('strong', finding.label + ': '), document.createTextNode(prefix + finding.explanation + ' ' + finding.review_question));
      box.append(p);
    }
    if (item.raw.findings_omitted) box.append(node('p', 'Других сохранённых меток: ' + item.raw.findings_omitted + '.'));
    box.append(node('p', 'Найденные признаки требуют проверки; они не доказывают манипуляцию, намерение автора или ложность фактов.'));
    box.append(node('p', 'Отсутствие признаков не означает нейтральность текста.'));
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
      const mark = node('mark', text, 'highlight-word');
      const description = [...new Set(matches.map(s => s.finding.label + ': ' + s.finding.explanation))].join(' ');
      mark.title = description; mark.tabIndex = 0; mark.setAttribute('aria-label', text + '. ' + description);
      // Touch and keyboard users can read the same comment below the excerpt.
      const show = () => { $('archiveMarkerNote').textContent = description; };
      mark.addEventListener('click', show); mark.addEventListener('focus', show);
      p.append(mark);
    }
    return p;
  }
  function openModal(item, trigger) {
    previousFocus = trigger || document.activeElement;
    $('messageModalTitle').textContent = item.title;
    $('modalMedia').replaceChildren(publisherElement(item, ''));
    $('modalTime').textContent = date(item.raw.published_at);
    $('modalCategory').textContent = item.category;
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
    const note = node('p', '', 'archive-context-note'); note.id = 'archiveMarkerNote'; body.append(note);
    $('modalOriginal').replaceChildren();
    const link = original(item); if (link) $('modalOriginal').append(link);
    explain(item);
    overlay.classList.add('open'); overlay.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden'; $('messageCloseBtn').focus();
  }
  function closeModal() {
    if (!overlay.classList.contains('open')) return;
    overlay.classList.remove('open'); overlay.setAttribute('aria-hidden', 'true'); document.body.style.overflow = '';
    if (previousFocus?.isConnected) previousFocus.focus();
  }
  function createItem(item) {
    const article = node('article', '', 'archive-item');
    article.dataset.id = String(item.raw.id); article.dataset.publisher = item.publisher; article.dataset.status = item.status;
    const row = node('div', '', 'archive-summary');
    row.append(publisherElement(item, 'cell-media'));
    const time = node(item.raw.published_at && Number.isFinite(Date.parse(item.raw.published_at)) ? 'time' : 'span', date(item.raw.published_at), 'cell-time');
    if (time.tagName === 'TIME') time.dateTime = item.raw.published_at;
    row.append(time, node('div', item.title, 'cell-title'));
    const category = node('div', item.category, 'cell-category ' + item.status);
    category.title = [...new Set(item.active.map(f => f.label))].join(' · ') || item.category;
    row.append(category);
    const cell = node('div', '', 'cell-button'), button = node('button', 'Подробнее', 'more-btn');
    button.type = 'button'; button.setAttribute('aria-label', 'Разбор: ' + item.title);
    button.addEventListener('click', () => openModal(item, button));
    row.addEventListener('click', event => {if (!event.target.closest('button,a')) openModal(item, button);});
    cell.append(button); row.append(cell); article.append(row); return article;
  }
  function render() {
    const term = search.trim().toLocaleLowerCase('ru');
    const selected = messages.filter(item => (!requestedPublisher || item.publisher === requestedPublisher) &&
      (filter === 'all' || item.status === filter) && (!term ||
        [item.media, item.title, item.raw.message_preview, ...item.raw.findings.flatMap(f =>
          [f.label, f.explanation, ...f.evidence.map(e => e.quote)])].join(' ').toLocaleLowerCase('ru').includes(term)));
    list.replaceChildren(...selected.map(createItem));
    if (!selected.length) list.append(node('div', 'Публикации по заданным условиям не найдены.', 'empty-state'));
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
      report = next; messages = items; render();
      const stale = Date.now() - Date.parse(next.generated_at) > 2 * 3600000;
      const publisherName = requestedPublisher && (messages.find(item => item.publisher === requestedPublisher)?.media ||
        next.sources.find(source => source.publisher_id === requestedPublisher)?.name);
      $('rtText').textContent = 'Обновлено: ' + date(next.generated_at) + '. В подборке: ' + messages.length +
        (publisherName ? '. Фильтр СМИ: ' + publisherName : '') +
        '. Часть собранных публикаций; полный охват СМИ не гарантирован.' + (stale ? ' Данные не обновлялись более двух часов.' : '');
    } catch {
      if (!report) list.replaceChildren(node('div', 'Не удалось загрузить реальные публикации. Попробуйте обновить страницу позже.', 'empty-state'));
      $('rtText').textContent = report ? 'Не удалось обновить подборку. Показаны данные от ' + date(report.generated_at) + '.'
        : 'Данные анализа недоступны.';
    } finally { clearTimeout(timeout); loading = false; }
  }
  chips.forEach(chip => chip.addEventListener('click', () => {
    filter = chip.dataset.status;
    chips.forEach(button => {button.classList.toggle('chip-active', button === chip); button.setAttribute('aria-pressed', String(button === chip));});
    render();
  }));
  $('searchInput').addEventListener('input', event => {search = event.target.value; render();});
  function placeholder() {
    $('searchInput').placeholder = matchMedia('(max-width:767px)').matches ? 'Поиск: СМИ, заголовок, приём' : 'Найти по СМИ, заголовку или типу манипуляции';
  }
  placeholder(); window.addEventListener('resize', placeholder, {passive: true});
  $('messageCloseBtn').addEventListener('click', closeModal);
  overlay.addEventListener('click', event => {if (event.target === overlay) closeModal();});
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
