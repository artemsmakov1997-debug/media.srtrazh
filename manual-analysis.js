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

  function busy(value) {
    el('manualSubmit').disabled = value;
    el('manualTitle').readOnly = value;
    el('manualText').readOnly = value;
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

  function highlight(container, text, evidence) {
    const characters = Array.from(text);
    const spans = evidence.map(item => [item.start, item.end]).sort((a, b) => a[0] - b[0]);
    const merged = [];
    for (const span of spans) {
      const previous = merged[merged.length - 1];
      if (previous && span[0] <= previous[1]) previous[1] = Math.max(previous[1], span[1]);
      else merged.push([...span]);
    }
    container.replaceChildren();
    let cursor = 0;
    for (const [start, end] of merged) {
      container.append(document.createTextNode(characters.slice(cursor, start).join('')));
      container.append(node('mark', characters.slice(start, end).join('')));
      cursor = end;
    }
    container.append(document.createTextNode(characters.slice(cursor).join('')));
  }

  function show(result) {
    currentResult = result;
    const counts = result.summary;
    el('manualVersion').textContent = 'Версия анализа: ' + result.algorithm_version + '.';
    el('manualSummary').textContent = 'Фрагментов для проверки: ' + counts.review_fragments +
      '. Меток приёмов: ' + counts.review_candidates +
      '. В цитатах или переданной речи: ' + counts.quoted_candidates +
      '. В отрицании или обсуждении: ' + counts.context_only + '.';
    el('manualWarnings').replaceChildren(...result.warnings.map(text => node('p', text, 'muted')));
    for (const field of ['title', 'text']) {
      const evidence = result.findings.flatMap(finding => finding.evidence.filter(item => item.field === field));
      highlight(el(field === 'title' ? 'manualTitleEvidence' : 'manualTextEvidence'),
        result.document[field], evidence);
    }
    el('manualFindings').replaceChildren(...result.findings.map(findingCard));
    if (!result.findings.length) el('manualFindings').append(node('p',
      'Совпадений текущих правил не найдено. Это не доказывает нейтральность текста.', 'muted'));
    el('manualCoverage').textContent = result.coverage.map(item => item.label + ': ' +
      (item.coverage === 'candidate_rules' ? 'поиск отдельных признаков' : 'не проверяется')).join('; ') + '.';
    el('manualResult').hidden = false;
    el('manualState').textContent = 'Готово';
    el('manualResultTitle').focus();
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
    for (const id of ['manualTitleEvidence', 'manualTextEvidence', 'manualFindings', 'manualWarnings']) {
      el(id).replaceChildren();
    }
  });

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
