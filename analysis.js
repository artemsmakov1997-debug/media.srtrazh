/* Public snapshot viewer. Publisher text is always inserted as text, never HTML. */
'use strict';

const element = id => document.getElementById(id);

const statuses = {
  needs_review: 'Требует проверки',
  quoted_candidate: 'Цитата или переданная речь — проверьте автора высказывания',
  context_only: 'Отрицание или обсуждение формулировки'
};

let report = null;

// Справочные статусы по указанным в документации источникам и датам проверки.
// Относятся к указанному СМИ/оператору проекта, а не автоматически ко всем его сотрудникам.
// Источники подтверждения приведены в docs/media-statuses.md.
const LEGAL_STATUSES = Object.freeze({
  meduza: {foreignAgent: true, undesirable: true},
  novayagazeta: {foreignAgent: false, undesirable: true},
  currenttime: {foreignAgent: true, undesirable: true},
  dw: {foreignAgent: false, undesirable: true},
  mediazona: {foreignAgent: true, undesirable: null, checkedAt: '13.10.2026'}
});

function legalStatus(publisherId) {
  return LEGAL_STATUSES[publisherId] || null;
}

function statusLabels(publisherId) {
  const status = legalStatus(publisherId);
  if (!status) return [];
  const labels = [];
  if (status.foreignAgent) labels.push('иноагент');
  if (status.undesirable) labels.push('нежелательная организация');
  return labels;
}

function annotatePublisherOptions() {
  for (const option of element('source').options) {
    if (!option.value || option.value === 'other') continue;
    const labels = statusLabels(option.value);
    if (labels.length) option.textContent += ' (' + labels.join(', ') + ')';
  }
}



/* Реестр источников приходит из той же конфигурации, которой пользуется сборщик. */
function sourceOf(item) {
  return report && report.sources.find(source => source.id === item.source_id);
}

function publisherOf(item) {
  const source = sourceOf(item);
  return (source && source.publisher_id) || item.publisher_id || item.source_id;
}

/* Создание DOM-элементов без вставки пользовательского HTML. */
function node(tag, text, className) {
  const result = document.createElement(tag);
  result.textContent = text;

  if (className) {
    result.className = className;
  }

  return result;
}

/* Форматирование даты по московскому времени. */
function date(value) {
  if (!value || !Number.isFinite(Date.parse(value))) {
    return 'не указана';
  }

  return new Date(value).toLocaleString('ru-RU', {
    timeZone: 'Europe/Moscow'
  }) + ' МСК';
}

/* Publication metadata: the visible value stays in Moscow time; machine time stays exact. */
function publicationTime(value) {
  const valid = value && Number.isFinite(Date.parse(value));
  const stamp = node(valid ? 'time' : 'span', '', 'publication-time');
  if (valid) stamp.dateTime = new Date(value).toISOString();
  stamp.append(node('span', 'Дата публикации: ', 'publication-time-context'));
  const formatted = date(value);
  const parts = /^(\d{2}\.\d{2}\.\d{4}),\s*(.+)$/.exec(formatted);
  stamp.append(node('span', parts ? parts[1] : formatted, 'publication-time-date'));
  if (parts) stamp.append(document.createTextNode(' '), node('span', parts[2], 'publication-time-clock'));
  return stamp;
}

/* Определение платформы публикации. */
function platformOf(item) {
  const source = sourceOf(item);
  return (source ? source.platform : item.platform) === 'telegram' ? 'telegram' : 'website';
}

/* Проверка ссылки на оригинал публикации. */
function original(item) {
  try {
    const url = new URL(item.url);
    const platform = platformOf(item);
    const source = sourceOf(item);

    if (
      !source ||
      url.protocol !== 'https:' ||
      url.username ||
      url.password ||
      (url.port && url.port !== '443')
    ) {
      return null;
    }

    if (platform === 'telegram') {
      const post = url.pathname.match(/^\/([^/]+)\/([1-9]\d*)\/?$/);
      if (url.hostname !== 't.me' || !source.channel || !post ||
          post[1].toLowerCase() !== source.channel.toLowerCase() || url.search || url.hash) {
        return null;
      }
    } else {
      if (!Array.isArray(source.allowed_hosts) || !source.allowed_hosts.includes(url.hostname)) {
        return null;
      }
    }

    const link = node(
      'a',
      platform === 'telegram'
        ? 'Открыть публикацию в Telegram →'
        : 'Открыть оригинал публикации →'
    );

    link.href = url.href;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';

    return link;
  } catch {
    return null;
  }
}

/* Отображение контекста с выделением найденного фрагмента. */
function excerpt(evidence) {
  const result = node('div', '', 'context');
  const sentence = evidence.sentence;
  const text = Array.from(sentence.text);

  const start = evidence.start - sentence.start;
  const end = evidence.end - sentence.start;

  if (
    start < 0 ||
    end > text.length ||
    text.slice(start, end).join('') !== evidence.quote
  ) {
    result.textContent = sentence.text;
    return result;
  }

  result.append(
    document.createTextNode(text.slice(0, start).join(''))
  );

  result.append(
    node('mark', text.slice(start, end).join(''))
  );

  result.append(
    document.createTextNode(text.slice(end).join(''))
  );

  return result;
}

/* Карточка отдельного найденного фрагмента. */
function findingCard(finding) {
  const card = node('section', '', 'finding');

  card.append(
    node(
      'p',
      statuses[finding.status] || finding.status,
      'badge'
    )
  );

  card.append(
    node('h3', finding.label),
    node('p', finding.explanation)
  );

  for (const evidence of finding.evidence) {
    card.append(
      node(
        'p',
        evidence.field === 'title'
          ? 'Фрагмент заголовка'
          : 'Фрагмент текста',
        'muted'
      )
    );

    card.append(excerpt(evidence));

    if (evidence.sentence.truncated) {
      card.append(
        node(
          'p',
          'Показан ограниченный фрагмент контекста.',
          'muted'
        )
      );
    }
  }

  card.append(node('p', finding.review_question));

  return card;
}


/* Разбор автоматической публикации в отдельном окне — по образцу Архива.
   Снимок может содержать только контекст найденных фрагментов, а не полный текст. */
const automaticModal = element('automaticModal');
const automaticBody = element('automaticModalBody');
const automaticTooltip = element('automaticTooltip');
let previousModalFocus = null;
let automaticTooltipTarget = null;
let automaticTooltipTimer = null;

function hideAutomaticTooltip() {
  clearTimeout(automaticTooltipTimer);
  if (automaticTooltipTarget) {
    automaticTooltipTarget.setAttribute('aria-expanded', 'false');
    automaticTooltipTarget.removeAttribute('aria-describedby');
  }
  automaticTooltip.hidden = true;
  automaticTooltipTarget = null;
}

function scheduleAutomaticTooltipHide() {
  clearTimeout(automaticTooltipTimer);
  automaticTooltipTimer = setTimeout(() => {
    if (document.activeElement !== automaticTooltipTarget && !automaticTooltip.matches(':hover')) hideAutomaticTooltip();
  }, 160);
}
automaticTooltip.addEventListener('pointerenter', () => clearTimeout(automaticTooltipTimer));
automaticTooltip.addEventListener('pointerleave', scheduleAutomaticTooltipHide);
document.addEventListener('scroll', event => {
  if (!automaticTooltip.contains(event.target)) hideAutomaticTooltip();
}, {capture: true, passive: true});
window.addEventListener('resize', hideAutomaticTooltip);
if (window.visualViewport) {
  window.visualViewport.addEventListener('resize', hideAutomaticTooltip);
  window.visualViewport.addEventListener('scroll', hideAutomaticTooltip);
}

function closeAutomaticModal() {
  automaticModal.hidden = true;
  hideAutomaticTooltip();
  document.body.style.overflow = '';
  if (previousModalFocus && previousModalFocus.isConnected) previousModalFocus.focus();
}

function showAutomaticTooltip(mark) {
  if (automaticTooltipTarget === mark && !automaticTooltip.hidden) {
    clearTimeout(automaticTooltipTimer);
    return;
  }
  const wasVisible = !automaticTooltip.hidden;
  hideAutomaticTooltip();
  automaticTooltipTarget = mark;
  mark.setAttribute('aria-expanded', 'true');
  mark.setAttribute('aria-describedby', 'automaticTooltip');
  automaticTooltip.toggleAttribute('data-instant', wasVisible || mark.matches(':focus-visible'));
  automaticTooltip.replaceChildren(
    node('strong', mark.dataset.label),
    node('div', mark.dataset.explanation)
  );
  const viewport = window.visualViewport;
  const leftEdge = (viewport ? viewport.offsetLeft : 0) + 12;
  const topEdge = (viewport ? viewport.offsetTop : 0) + 12;
  const width = (viewport ? viewport.width : innerWidth) - 24;
  const height = (viewport ? viewport.height : innerHeight) - 24;
  const style = getComputedStyle(automaticTooltip);
  const widthCap = Number(style.getPropertyValue('--tooltip-width')) || 310;
  const heightCap = Number(style.getPropertyValue('--tooltip-height')) || 360;
  automaticTooltip.style.width = Math.max(1, Math.min(widthCap, width)) + 'px';
  automaticTooltip.style.maxHeight = Math.max(1, Math.min(heightCap, height * .65)) + 'px';
  automaticTooltip.style.visibility = 'hidden';
  automaticTooltip.hidden = false;
  const visibleRects = Array.from(mark.getClientRects()).filter(rect => rect.bottom > topEdge && rect.top < topEdge + height);
  const firstRect = visibleRects[0] || mark.getBoundingClientRect();
  const rect = {left: firstRect.left, width: firstRect.width,
    top: visibleRects.length ? Math.max(topEdge, Math.min(...visibleRects.map(rect => rect.top))) : firstRect.top,
    bottom: visibleRects.length ? Math.min(topEdge + height, Math.max(...visibleRects.map(rect => rect.bottom))) : firstRect.bottom};
  const preferredHeight = automaticTooltip.offsetHeight;
  const above = rect.top - topEdge - 10;
  const below = topEdge + height - rect.bottom - 10;
  const useAbove = above >= preferredHeight || (below < preferredHeight && above > below);
  const room = Math.max(1, useAbove ? above : below);
  automaticTooltip.style.maxHeight = Math.max(1, Math.min(heightCap, height * .65, room)) + 'px';
  const tip = {width: automaticTooltip.offsetWidth, height: automaticTooltip.offsetHeight};
  const left = Math.max(leftEdge, Math.min(rect.left + rect.width / 2 - tip.width / 2, leftEdge + width - tip.width));
  const preferredTop = useAbove ? rect.top - tip.height - 10 : rect.bottom + 10;
  const top = Math.max(topEdge, Math.min(preferredTop, topEdge + height - tip.height));
  automaticTooltip.style.left = left + 'px';
  automaticTooltip.style.top = top + 'px';
  automaticTooltip.style.transformOrigin = Math.max(0, Math.min(tip.width, rect.left + rect.width / 2 - left)) +
    'px ' + (useAbove ? 'bottom' : 'top');
  automaticTooltip.style.visibility = '';
}

function modalExcerpt(sentence, evidences) {
  const paragraph = node('p', '', 'auto-modal-excerpt');
  const chars = Array.from(sentence.text);
  const segments = [];
  for (const { finding, evidence } of evidences) {
    const start = evidence.start - sentence.start;
    const end = evidence.end - sentence.start;
    if (start < 0 || end > chars.length || start >= end ||
        chars.slice(start, end).join('') !== evidence.quote) continue;
    segments.push({ start, end, finding });
  }
  const boundaries = [...new Set([0, chars.length, ...segments.flatMap(s => [s.start, s.end])])].sort((a,b) => a-b);
  for (let i = 0; i < boundaries.length - 1; i++) {
    const from = boundaries[i], to = boundaries[i + 1];
    if (from === to) continue;
    const text = chars.slice(from, to).join('');
    const matches = segments.filter(s => s.start <= from && s.end >= to);
    if (!matches.length) { paragraph.append(document.createTextNode(text)); continue; }
    const mark = node('mark', text, 'auto-modal-highlight');
    mark.tabIndex = 0;
    mark.dataset.label = [...new Set(matches.map(s => s.finding.label))].join(' · ');
    mark.dataset.explanation = [...new Set(matches.map(s =>
      (s.finding.evidence?.some(e => e.context?.informational_notice)
        ? 'Информационная отметка — не признак манипуляции'
        : s.finding.rule_id === 'context.quotation_omission'
        ? 'Сокращение цитаты — требуется сверка с оригиналом'
        : statuses[s.finding.status] || s.finding.status) + '. ' + s.finding.explanation))].join(' ');
    mark.dataset.question = [...new Set(matches.map(s => s.finding.review_question))].join(' ');
    mark.setAttribute('aria-label', text + ': ' + mark.dataset.label);
    mark.setAttribute('aria-controls', 'automaticTooltip');
    mark.setAttribute('aria-expanded', 'false');
    mark.addEventListener('pointerenter', event => {
      if (event.pointerType === 'mouse') showAutomaticTooltip(mark);
    });
    mark.addEventListener('pointerleave', event => {
      if (event.pointerType === 'mouse') scheduleAutomaticTooltipHide();
    });
    mark.addEventListener('focus', () => showAutomaticTooltip(mark));
    mark.addEventListener('blur', scheduleAutomaticTooltipHide);
    let closeOnClick = false;
    mark.addEventListener('pointerdown', () => {
      closeOnClick = !automaticTooltip.hidden && automaticTooltipTarget === mark;
    });
    mark.addEventListener('click', () => {
      // Touch focuses the mark before click. Use its pre-focus state so the
      // first tap does not immediately close the tooltip that focus just opened.
      if (closeOnClick) hideAutomaticTooltip();
      else showAutomaticTooltip(mark);
      closeOnClick = false;
    });
    paragraph.append(mark);
  }
  return paragraph;
}

function openAutomaticModal(item) {
  previousModalFocus = document.activeElement;
  hideAutomaticTooltip();
  element('automaticModalTitle').textContent = item.title || item.message_preview || 'Разбор публикации';
  automaticBody.replaceChildren();

  const findings = Array.isArray(item.findings) ? item.findings : [];
  const sections = new Map();
  for (const finding of findings) {
    for (const evidence of finding.evidence || []) {
      if (!evidence.sentence || typeof evidence.sentence.text !== 'string') continue;
      const key = evidence.field + ':' + evidence.sentence.start + ':' + evidence.sentence.text;
      if (!sections.has(key)) sections.set(key, { sentence: evidence.sentence, field: evidence.field, evidences: [] });
      sections.get(key).evidences.push({ finding, evidence });
    }
  }
  const panel = node('section', '', 'auto-modal-section');
  panel.append(node('p', sections.size ? 'Фрагменты публикации с выделенными признаками' : 'Результат анализа', 'auto-modal-section-label'));
  if (sections.size) {
    for (const section of sections.values()) {
      panel.append(modalExcerpt(section.sentence, section.evidences));
    }
  } else {
    panel.append(node('p', findings.length ? 'Контекст найденных признаков недоступен.' :
      'Совпадений текущих правил не найдено. Это не доказывает нейтральность текста.', 'auto-modal-note'));
  }
  automaticBody.append(panel);
  automaticBody.append(node('p', 'Показаны сохранённые фрагменты контекста, а не обязательно полный текст публикации. Наведите курсор на выделение или нажмите на него, чтобы увидеть комментарий. Выявленные признаки требуют проверки.', 'auto-modal-note'));
  if (item.findings_omitted) automaticBody.append(node('p', 'Других меток в результате: ' + item.findings_omitted, 'auto-modal-note'));
  automaticModal.hidden = false;
  document.body.style.overflow = 'hidden';
  element('automaticModalClose').focus();
}
element('automaticModalClose').addEventListener('click', closeAutomaticModal);
automaticModal.addEventListener('click', event => {
  if (event.target === automaticModal) closeAutomaticModal();
  else if (!event.target.closest('.auto-modal-highlight')) hideAutomaticTooltip();
});
document.addEventListener('keydown', event => {
  if (automaticModal.hidden) return;
  if (event.key === 'Escape') { event.preventDefault(); closeAutomaticModal(); }
  if (event.key === 'Tab') {
    const focusable = [...automaticModal.querySelectorAll('button, a[href], [tabindex="0"]')];
    if (!focusable.length) return;
    const first = focusable[0], last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  }
});

/* Все поддерживаемые категории берутся из методики, а не только из текущей выборки.
   Иначе фильтр теряет варианты при смене новостного снимка. */
function refreshMarkers() {
  const select = element('marker');
  const previous = select.value;
  const categories = (report.coverage || []).filter(entry =>
    entry.coverage === 'candidate_rules' || entry.coverage === 'context_notices'
  );
  const options = [new Option('Все маркеры', '')];
  for (const category of categories) {
    options.push(new Option(category.label, category.id));
  }
  select.replaceChildren(...options);
  if (categories.some(entry => entry.id === previous)) select.value = previous;
}

/* Показываем настоящий заголовок, а не текст сообщения.
   Telegram-посты не имеют отдельного заголовка: их message_preview
   (включая метаданные репоста) нельзя выдавать за заголовок. */
function cardHeadline(item) {
  if (platformOf(item) === 'telegram') {
    // An extractive, complete phrase from the original message, if available.
    // Never show an auto-truncated preview or Telegram's "Forwarded from" label.
    const excerpt = String(item.display_excerpt || '').replace(/\s+/g, ' ').trim();
    if (excerpt && !excerpt.endsWith('…') && !/^(?:Forwarded from|Переслано из|Переслано от)\b/i.test(excerpt)) {
      return excerpt;
    }
    return item.forwarded ? 'Пересланная публикация в Telegram' : 'Публикация в Telegram';
  }
  const title = String(item.title || '').replace(/\s+/g, ' ').trim();
  if (title) return title;
  return 'Публикация без заголовка';
}

/* Фильтрация и отрисовка публикаций. */
function render() {
  if (!report) return;
  const articlesContainer = element('articles');

  articlesContainer.replaceChildren();

  const platform = element('platform').value;
  const source = element('source').value;
  const marker = element('marker').value;
  const namedOutlets = new Set(Array.from(element('source').options)
    .map(option => option.value).filter(value => value && value !== 'other'));

  const selected = report.articles.filter(item => {
    const outletMatch =
      !source ||
      publisherOf(item) === source ||
      (source === 'other' && !namedOutlets.has(publisherOf(item)));

    const platformMatch =
      !platform || platformOf(item) === platform;

    const findings = Array.isArray(item.findings) ? item.findings : [];
    // Показываем только материалы с обнаруженными признаками.
    const hasMetrics = findings.length > 0;
    const markerMatch = !marker || findings.some(finding => finding.category === marker);
    return outletMatch && platformMatch && hasMetrics && markerMatch;
  });

  element('selection').textContent =
    'Показано публикаций: ' + selected.length + '.';

  if (!selected.length) {
    const message = 'В этой подборке нет публикаций, соответствующих фильтрам.';

    articlesContainer.append(
      node('p', message, 'muted')
    );
  }

  for (const item of selected) {
    const article = node('article', '', 'publication');

    const publisherMeta = node('p', item.source, 'publication-meta');
    for (const label of statusLabels(publisherOf(item))) {
      const badge = node('span', label, 'legal-status-tag');
      badge.title = 'Статус СМИ или его организации-оператора в РФ; проверка ' +
        (legalStatus(publisherOf(item)).checkedAt || '12.10.2026') + '; сведения справочные';
      publisherMeta.append(badge);
    }
    const header = node('div', '', 'publication-header');
    header.append(publisherMeta, publicationTime(item.published_at));
    article.append(header);

    const headline = node('h2', cardHeadline(item));
    headline.className = 'publication-title';
    article.append(headline);

    const counts = item.summary;
    article.append(
      node(
        'p',
        counts ? 'Найдено фрагментов для проверки: ' + (counts.candidate_fragments ?? counts.review_fragments)
          : 'Анализ текущей версии отсутствует.',
        'badge'
      )
    );

    const actions = node('div', '', 'publication-actions');
    const more = node('button', 'Подробнее', 'auto-details-button');
    more.type = 'button';
    more.addEventListener('click', () => openAutomaticModal(item));
    actions.append(more);

    const link = original(item);
    if (link) {
      link.textContent = 'Смотреть источник';
      link.classList.add('source-link');
      actions.append(link);
    }

    article.append(actions);
    articlesContainer.append(article);
  }
}

/* Загрузка опубликованного снимка анализа. */
async function load() {
  try {
    const response = await fetch(
      'data/analysis.json',
      {
        cache: 'no-store',
        signal: AbortSignal.timeout(20000)
      }
    );

    if (!response.ok) {
      throw new Error('snapshot unavailable');
    }

    report = await response.json();

    if (
      report.schema_version !== 'public-snapshot-1.0' ||
      !Array.isArray(report.articles) ||
      !Array.isArray(report.sources)
    ) {
      throw new Error('invalid snapshot');
    }

    element('updated').textContent =
      'Подборка обновлена: ' +
      date(report.generated_at) +
      '. Версия анализа: ' +
      report.algorithm_version +
      '.';

    const age = Date.now() - Date.parse(report.generated_at);
    const stale = Number.isFinite(age) && age > 90 * 60 * 1000;

    if (
      stale
    ) {
      element('updated').classList.add('error');

      element('updated').append(
        document.createTextNode(
          ' Подборка давно не обновлялась.'
        )
      );
    }

    element('totals').textContent =
      'В подборке: ' +
      report.totals.displayed +
      '. Проанализировано: ' +
      report.totals.analyzed +
      '. С фрагментами для проверки: ' +
      report.totals.with_review_candidates +
      '.';
    if (report.collection) {
      element('totals').append(document.createTextNode(
        ' Полный сохранённый корпус: ' + report.collection.collected +
        '; без даты: ' + report.collection.undated +
        '; ожидают загрузки: ' + report.collection.pending +
        '. Охват ограничен собранной выборкой.'
      ));
    }

    element('sources').replaceChildren();

    for (const source of report.sources) {
      const card = node('section', '', 'source');
      const sourceError = (source.status && source.status.last_error) || source.configuration_error;

      card.append(
        node('h3', source.name),
        node(
          'p',
          'Публикаций в подборке: ' + source.displayed
        )
      );
      if (source.health) {
        const labels = {current: 'Тексты получены недавно', partial: 'Частичный сбор с ошибками',
          error: 'Ошибка сбора', stale: 'Новых текстов давно нет', pending: 'Ожидает проверки'};
        card.append(node('p', (labels[source.health.state] || source.health.state) +
          '. В корпусе: ' + source.health.collected + '; опубликовано за 24 часа: ' + source.health.collected_24h +
          '; без даты: ' + source.health.undated + '; в очереди: ' + source.health.pending + '.', 'muted'));
        card.append(node('p', 'Последний полученный текст: ' + date(source.health.last_text_at), 'muted'));
      }

      card.append(
        node(
          'p',
          source.status
            ? 'Последняя проверка: ' +
                date(source.status.last_attempt_at)
            : 'Источник ещё не проверялся.',
          'muted'
        )
      );

      if (sourceError) {
        card.append(
          node('p', sourceError, 'error')
        );
      }

      element('sources').append(card);
    }

    element('coverage').textContent =
      report.coverage.map(item =>
        item.label +
        ': ' +
        (
          item.coverage === 'candidate_rules'
            ? 'поиск отдельных признаков'
            : item.coverage === 'context_notices' ? 'информационные отметки'
            : 'не проверяется'
        )
      ).join('; ') + '.';

    element('coverageBlock').hidden = false;
    element('controls').hidden = false;

    refreshMarkers();
    render();
  } catch (error) {
    console.error('Не удалось загрузить подборку анализа:', error);

    element('updated').textContent =
      'Подборка пока недоступна.';

    element('error').textContent =
      'Публикации появятся после успешного сбора. Попробуйте обновить страницу позже.';

    element('error').hidden = false;
  }
}

annotatePublisherOptions();

/* Подключение фильтров. */
element('source').addEventListener('change', render);
element('platform').addEventListener('change', render);
element('marker').addEventListener('change', render);

/* Запуск страницы. */
load();
