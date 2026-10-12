/* Manual input remains in this browser; only the runtime and rule sources are fetched. */
(() => {
  'use strict';
  const el = id => document.getElementById(id);
  const maxChars = 200000;
  let worker = null;
  let sequence = 0;
  let pending = null;
  let deadline = null;
  let currentResult = null;
  const tooltip = el('manualTooltip');
  const annotations = new WeakMap();
  let tooltipTarget = null;
  let tooltipPinned = false;
  let tooltipDismissed = false;
  let tooltipTimer = null;

  function busy(value) {
    el('manualSubmit').disabled = value;
    el('manualTitle').readOnly = value;
    el('manualText').readOnly = value;
    el('manualEdit').disabled = value;
    el('manualDownload').disabled = value;
    el('manualForm').setAttribute('aria-busy', String(value));
  }

  function finish() {
    clearTimeout(deadline);
    deadline = null;
    pending = null;
    busy(false);
  }

  function fail(message) {
    finish();
    el('manualState').textContent = '';
    el('manualError').textContent = message;
    el('manualError').hidden = false;
  }

  function stopWorker() {
    if (worker) worker.terminate();
    worker = null;
  }

  function hideTooltip() {
    clearTimeout(tooltipTimer);
    if (tooltipTarget) {
      tooltipTarget.setAttribute('aria-expanded', 'false');
      tooltipTarget.removeAttribute('aria-describedby');
    }
    tooltip.hidden = true;
    tooltip.replaceChildren();
    tooltipTarget = null;
    tooltipPinned = false;
  }

  function showTooltip(target, pinned = false) {
    const findings = annotations.get(target);
    if (!findings) return;
    hideTooltip();
    tooltipDismissed = false;
    tooltipTarget = target;
    tooltipPinned = pinned;
    target.setAttribute('aria-expanded', 'true');
    target.setAttribute('aria-describedby', 'manualTooltip');
    for (const finding of findings) {
      const section = document.createElement('section');
      section.append(node('h3', finding.label), node('p', finding.explanation),
        node('p', statuses[finding.status] || finding.status, 'muted'),
        node('p', finding.review_question));
      tooltip.append(section);
    }
    const viewport = window.visualViewport;
    const edge = 12;
    const leftEdge = (viewport ? viewport.offsetLeft : 0) + edge;
    const topEdge = (viewport ? viewport.offsetTop : 0) + edge;
    const width = (viewport ? viewport.width : innerWidth) - edge * 2;
    const height = (viewport ? viewport.height : innerHeight) - edge * 2;
    tooltip.style.width = Math.max(1, Math.min(330, width)) + 'px';
    tooltip.style.maxHeight = Math.max(1, Math.min(360, height * .65)) + 'px';
    tooltip.style.visibility = 'hidden';
    tooltip.hidden = false;
    const visibleRects = Array.from(target.getClientRects()).filter(rect =>
      rect.bottom > topEdge && rect.top < topEdge + height);
    const rect = visibleRects[0] || target.getBoundingClientRect();
    const preferredHeight = tooltip.getBoundingClientRect().height;
    const above = rect.top - topEdge - 10;
    const reader = target.closest('.manual-annotated').getBoundingClientRect();
    // A long comment remains scrollable and never blocks the form's controls
    // or its own highlighted trigger, including on a short mobile viewport.
    const below = Math.min(topEdge + height, reader.bottom) - rect.bottom - 10;
    const useAbove = above >= Math.min(120, preferredHeight) || above >= below;
    const room = Math.max(1, useAbove ? above : below);
    tooltip.style.maxHeight = Math.max(1, Math.min(360, height * .65, room)) + 'px';
    const box = tooltip.getBoundingClientRect();
    const left = Math.max(leftEdge, Math.min(rect.left + rect.width / 2 - box.width / 2,
      leftEdge + width - box.width));
    let top = useAbove ? rect.top - box.height - 10 : rect.bottom + 10;
    top = Math.max(topEdge, Math.min(top, topEdge + height - box.height));
    tooltip.style.left = left + 'px';
    tooltip.style.top = top + 'px';
    tooltip.style.visibility = '';
  }

  function scheduleTooltipHide() {
    clearTimeout(tooltipTimer);
    tooltipTimer = setTimeout(() => {
      if (!tooltipPinned && document.activeElement !== tooltipTarget) hideTooltip();
    }, 160);
  }

  function dismissTooltip() {
    tooltipDismissed = true;
    hideTooltip();
  }

  function highlight(container, text, findings, field) {
    const characters = Array.from(text);
    const events = new Map();
    const add = (position, event) => {
      if (!events.has(position)) events.set(position, []);
      events.get(position).push(event);
    };
    findings.forEach((finding, index) => {
      for (const item of finding.evidence) {
        if (item.field !== field || !Number.isInteger(item.start) || !Number.isInteger(item.end) ||
            item.start < 0 || item.end <= item.start || item.end > characters.length ||
            characters.slice(item.start, item.end).join('') !== item.quote) continue;
        add(item.start, {index, delta: 1});
        add(item.end, {index, delta: -1});
      }
    });
    const active = new Map();
    const segments = [];
    let cursor = 0;
    for (const position of Array.from(events.keys()).sort((a, b) => a - b)) {
      if (position > cursor) {
        const indexes = Array.from(active.keys()).sort((a, b) => a - b);
        const key = indexes.join(',');
        const previous = segments[segments.length - 1];
        if (previous && previous.key === key) previous.end = position;
        else segments.push({start: cursor, end: position, indexes, key});
      }
      for (const {index, delta} of events.get(position)) {
        const count = (active.get(index) || 0) + delta;
        if (count) active.set(index, count);
        else active.delete(index);
      }
      cursor = position;
    }
    if (cursor < characters.length) segments.push({start: cursor, end: characters.length, indexes: []});
    container.replaceChildren();
    const fragment = document.createDocumentFragment();
    for (const segment of segments) {
      const quote = characters.slice(segment.start, segment.end).join('');
      if (!segment.indexes.length) {
        fragment.append(document.createTextNode(quote));
        continue;
      }
      const matches = segment.indexes.map(index => findings[index]);
      const mark = node('mark', quote, 'manual-trigger');
      mark.tabIndex = 0;
      mark.setAttribute('role', 'button');
      mark.setAttribute('aria-controls', 'manualTooltip');
      mark.setAttribute('aria-expanded', 'false');
      mark.setAttribute('aria-label', quote + ': ' + Array.from(new Set(matches.map(item => item.label))).join(', '));
      mark.dataset.status = matches.every(item => item.status === 'context_only') ? 'context_only' :
        matches.every(item => item.status === 'quoted_candidate') ? 'quoted_candidate' : 'needs_review';
      annotations.set(mark, matches);
      fragment.append(mark);
    }
    container.append(fragment);
  }

  function editView() {
    hideTooltip();
    tooltipDismissed = false;
    currentResult = null;
    el('manualTitle').hidden = false;
    el('manualTitleLabel').hidden = false;
    el('manualText').hidden = false;
    el('manualTitleEvidence').hidden = true;
    el('manualTextEvidence').hidden = true;
    el('manualSubmit').hidden = false;
    el('manualEdit').hidden = true;
    el('manualDownload').hidden = true;
    el('manualResult').hidden = true;
    el('manualNotice').hidden = true;
  }

  function show(result) {
    currentResult = result;
    hideTooltip();
    for (const field of ['title', 'text']) {
      highlight(el(field === 'title' ? 'manualTitleEvidence' : 'manualTextEvidence'),
        result.document[field], result.findings, field);
    }
    el('manualTitle').hidden = true;
    el('manualText').hidden = true;
    el('manualTitleEvidence').hidden = !result.document.title.trim();
    el('manualTitleLabel').hidden = !result.document.title.trim();
    el('manualTextEvidence').hidden = false;
    el('manualSubmit').hidden = true;
    el('manualEdit').hidden = false;
    el('manualDownload').hidden = false;
    const notices = result.warnings.slice(3);
    el('manualNotice').textContent = notices.join(' ');
    el('manualNotice').hidden = !notices.length;
    el('manualResult').hidden = false;
    el('manualState').textContent = result.findings.length ?
      'Готово. Наведите курсор или нажмите на выделенный фрагмент, чтобы прочитать пояснение.' :
      'Совпадений текущих правил не найдено.';
    el('manualTextEvidence').focus({preventScroll: true});
  }

  function getWorker() {
    if (!worker) {
      worker = new Worker('manual-worker.js');
      const created = worker;
      worker.addEventListener('message', event => {
        const message = event.data;
        if (message.id !== pending) return;
        if (message.type === 'state') {
          el('manualState').textContent = message.state === 'loading' ?
            'Загружаем анализатор для первого запуска…' : 'Анализируем…';
        } else if (message.type === 'result') {
          finish();
          show(message.result);
        } else if (message.type === 'error') {
          fail(message.message);
          if (message.kind === 'loading') stopWorker();
        }
      });
      worker.addEventListener('error', () => {
        if (worker !== created || pending === null) return;
        stopWorker();
        fail('Не удалось запустить анализатор в браузере. Обновите страницу и повторите попытку.');
      });
    }
    return worker;
  }

  el('manualForm').addEventListener('submit', event => {
    event.preventDefault();
    if (pending !== null) return;
    editView();
    el('manualError').hidden = true;
    el('manualResult').hidden = true;
    currentResult = null;
    const document = {title: el('manualTitle').value, text: el('manualText').value};
    if (!document.text.trim()) {
      fail('Вставьте текст публикации.');
      el('manualText').focus();
      return;
    }
    if (Array.from(document.title).length + Array.from(document.text).length > maxChars) {
      fail('Заголовок и текст вместе должны содержать не более 200 000 символов.');
      return;
    }
    if (!window.Worker || !window.WebAssembly) {
      fail('Этот браузер не поддерживает ручной анализ. Откройте страницу в современном браузере.');
      return;
    }
    busy(true);
    pending = ++sequence;
    el('manualState').textContent = worker ? 'Анализируем…' : 'Загружаем анализатор для первого запуска…';
    deadline = setTimeout(() => {
      stopWorker();
      fail('Анализ не завершился вовремя. Проверьте соединение или попробуйте более короткий текст.');
    }, 120000);
    try {
      getWorker().postMessage({id: pending, document});
    } catch {
      stopWorker();
      fail('Не удалось запустить анализатор. Обновите страницу и повторите попытку.');
    }
  });

  el('manualForm').addEventListener('reset', () => {
    if (pending !== null) stopWorker();
    finish();
    currentResult = null;
    el('manualState').textContent = '';
    el('manualError').hidden = true;
    el('manualResult').hidden = true;
    editView();
    for (const id of ['manualTitleEvidence', 'manualTextEvidence']) {
      el(id).replaceChildren();
    }
  });

  el('manualEdit').addEventListener('click', () => {
    editView();
    el('manualState').textContent = '';
    el('manualText').focus({preventScroll: true});
  });

  const triggerOf = event => event.target instanceof Element ? event.target.closest('.manual-trigger') : null;
  document.addEventListener('pointerover', event => {
    if (event.pointerType !== 'mouse' || tooltipDismissed) return;
    const trigger = triggerOf(event);
    if (trigger && trigger !== tooltipTarget) showTooltip(trigger);
    else if (trigger || tooltip.contains(event.target)) clearTimeout(tooltipTimer);
    else scheduleTooltipHide();
  });
  document.addEventListener('pointermove', event => {
    if (event.pointerType === 'mouse' && tooltipDismissed && (event.movementX || event.movementY)) {
      tooltipDismissed = false;
      const trigger = triggerOf(event);
      if (trigger) showTooltip(trigger);
    }
  });
  document.addEventListener('pointerout', event => {
    if (event.pointerType === 'mouse' && (triggerOf(event) || tooltip.contains(event.target))) scheduleTooltipHide();
  });
  document.addEventListener('focusin', event => {
    const trigger = triggerOf(event);
    if (trigger && trigger !== tooltipTarget) showTooltip(trigger);
  });
  document.addEventListener('focusout', event => {
    if (triggerOf(event)) scheduleTooltipHide();
  });
  document.addEventListener('click', event => {
    const trigger = triggerOf(event);
    if (trigger) {
      if (tooltipTarget === trigger && tooltipPinned) dismissTooltip();
      else showTooltip(trigger, true);
    } else if (!tooltip.contains(event.target)) hideTooltip();
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') dismissTooltip();
    else if (triggerOf(event) && (event.key === 'Enter' || event.key === ' ')) {
      event.preventDefault();
      triggerOf(event).click();
    }
  });
  document.addEventListener('scroll', event => {
    if (!tooltip.contains(event.target)) dismissTooltip();
  }, {capture: true, passive: true});
  window.addEventListener('resize', dismissTooltip);
  if (window.visualViewport) {
    window.visualViewport.addEventListener('resize', dismissTooltip);
    window.visualViewport.addEventListener('scroll', dismissTooltip);
  }

  el('manualDownload').addEventListener('click', () => {
    if (!currentResult) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(currentResult, null, 2)],
      {type: 'application/json;charset=utf-8'}));
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = 'media-strazh-analysis.json';
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
})();
