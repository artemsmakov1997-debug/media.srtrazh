/* Local PRO pilot. Files, captions and source URLs are never uploaded. */
(() => {
  'use strict';
  const el = id => document.getElementById(id), form = el('photoForm');
  if (!form) return;
  const node = (tag, text, cls) => {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    if (cls) element.className = cls;
    return element;
  };
  const roles = ['publication', 'reference'];
  const names = {publication: 'Publication', reference: 'Reference'};
  const inputs = {publication: el('photoFile'), reference: el('photoReference')};
  const records = {publication: null, reference: null};
  const revisions = {publication: 0, reference: 0};
  const requests = new Map();
  let imageWorker = null, captionWorker = null, sequence = 0, run = 0, working = false, report = null;
  let cancelCaption = null;

  function stopImages() {
    imageWorker?.terminate(); imageWorker = null;
    for (const pending of requests.values()) { clearTimeout(pending.timer); pending.reject(Error('Обработка фото остановлена. Повторите проверку.')); }
    requests.clear();
    for (const role of roles) if (records[role]) records[role].prepared = false;
  }
  function imageJob(action, payload = {}) {
    return new Promise((resolve, reject) => {
      if (!window.Worker || !window.OffscreenCanvas || !window.createImageBitmap) {
        reject(Error('Для проверки фото нужен современный браузер с обработкой изображений. Попробуйте обновить браузер.')); return;
      }
      if (!imageWorker) {
        imageWorker = new Worker('photo-image-worker.js?v=20261128');
        const created = imageWorker;
        imageWorker.addEventListener('message', event => {
          const item = requests.get(event.data.id);
          if (!item) return;
          clearTimeout(item.timer); requests.delete(event.data.id);
          if (event.data.type === 'error') item.reject(Error(event.data.message)); else item.resolve(event.data.result);
        });
        imageWorker.addEventListener('error', () => { if (imageWorker === created) stopImages(); });
      }
      const id = ++sequence;
      const timer = setTimeout(stopImages, 30000);
      requests.set(id, {resolve, reject, timer});
      try { imageWorker.postMessage({id, action, ...payload}); }
      catch { stopImages(); }
    });
  }
  function sync() {
    const loading = roles.some(role => records[role]?.loading);
    el('photoSubmit').disabled = working || loading;
    form.setAttribute('aria-busy', String(working || loading));
    for (const control of form.querySelectorAll('input, textarea, button:not(#photoReset):not(#photoSubmit)')) control.disabled = working;
    if (!working) el('photoState').textContent = loading ? 'Обрабатываем фото на вашем устройстве…' : '';
  }
  function invalidate() {
    report = null; el('photoResult').hidden = true;
    el('photoCueNote').hidden = true;
    el('photoReferencePreview').querySelector('.photo-crop-box').hidden = true;
    el('photoError').hidden = true;
  }
  function release(role) {
    if (records[role]?.url) URL.revokeObjectURL(records[role].url);
    records[role] = null;
    const preview = el('photo' + names[role] + 'Preview');
    preview.hidden = true; preview.querySelector('img').removeAttribute('src');
    el('photo' + names[role] + 'Error').hidden = true;
  }
  async function readFile(role, file) {
    const version = ++revisions[role];
    release(role); invalidate();
    el('photoRemoveReference').hidden = !inputs.reference.files.length;
    if (!file) {
      if (imageWorker) imageWorker.postMessage({id: ++sequence, action: 'clear', role});
      sync(); return;
    }
    const record = {file, loading: true, prepared: false}; records[role] = record; sync();
    try {
      const result = await imageJob('inspect', {role, file});
      if (version !== revisions[role]) return;
      record.summary = result.summary; record.prepared = true;
      record.url = URL.createObjectURL(result.preview);
      const preview = el('photo' + names[role] + 'Preview');
      preview.querySelector('img').src = record.url;
      const m = record.summary;
      preview.style.setProperty('--photo-ratio', String(m.width / m.height));
      preview.querySelector('figcaption').textContent = `${m.file_name} · ${m.format} · ${m.width} × ${m.height} · ${sizeLabel(m.bytes)}`;
      preview.hidden = false;
    } catch (error) {
      if (version !== revisions[role]) return;
      record.error = error.message;
      const target = el('photo' + names[role] + 'Error'); target.textContent = error.message; target.hidden = false;
    } finally {
      if (version === revisions[role]) { record.loading = false; sync(); }
    }
  }
  function sizeLabel(bytes) {
    return bytes >= 1024 * 1024 ? new Intl.NumberFormat('ru-RU', {maximumFractionDigits: 1}).format(bytes / 1024 / 1024) + ' МБ' : Math.max(1, Math.round(bytes / 1024)) + ' КБ';
  }
  function captionAnalysis(text) {
    if (!text.trim()) return Promise.resolve({status: 'not_provided', findings: [], algorithm_version: null});
    const local = PhotoContext.captionCues(text);
    return new Promise(resolve => {
      let timer, settled = false;
      const finish = (status, result = null) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer); captionWorker?.terminate(); captionWorker = null; cancelCaption = null;
        resolve({status, findings: [...(result?.findings || []), ...local], algorithm_version: result?.algorithm_version || null});
      };
      cancelCaption = () => finish('cancelled');
      try {
        captionWorker = new Worker('manual-worker.js');
        const id = ++sequence;
        captionWorker.addEventListener('message', event => {
          if (event.data.id !== id) return;
          if (event.data.type === 'state') el('photoState').textContent = event.data.state === 'loading' ? 'Загружаем локальный анализатор подписи…' : 'Проверяем формулировки в подписи…';
          if (event.data.type === 'result') finish('complete', event.data.result);
          if (event.data.type === 'error') finish('partial');
        });
        captionWorker.addEventListener('error', () => finish('partial'));
        timer = setTimeout(() => finish('partial'), 120000);
        captionWorker.postMessage({id, document: {title: '', text}});
      } catch { finish('partial'); }
    });
  }
  const statusLabels = {observation: 'Наблюдение', needs_review: 'Требует проверки', insufficient_data: 'Недостаточно данных'};
  function status(value) {
    const badge = node('span', statusLabels[value], 'photo-status'); badge.dataset.status = value; return badge;
  }
  function showComparison(result) {
    const descriptions = {
      same_file: ['Загружен один и тот же файл', 'Контрольные суммы двух файлов совпадают. Различия в подписи или контексте публикаций нужно проверять отдельно.'],
      visual_copy: ['Кадры визуально близки', 'После приведения к одному размеру пиксели снимков близки. Это может быть копия с изменённым размером или сжатием; совпадение не подтверждает подлинность и не устанавливает первоисточник.'],
      crop_candidate: ['Найдена возможная общая область', 'Рамка на фото для сравнения показывает область, похожую на кадр из публикации. Проверьте совпадение визуально: алгоритм не устанавливает, какой файл первичен и зачем изменили границы кадра.'],
      no_reference: ['Для сравнения нужен второй снимок', 'По одному кадру нельзя установить намеренный выбор ракурса или понять, что осталось за его границами. Добавьте другой снимок того же события или исходник.'],
      not_matched: ['Совпадающая область не найдена', 'Это не доказывает разные события или отсутствие обработки. Повороты, зеркальные отражения, сильное изменение цвета и наложения могут помешать сопоставлению.'],
      inconclusive: ['Надёжное сопоставление невозможно', result.reason === 'ambiguous_match' ? 'Найдены повторяющиеся похожие области. По ним нельзя уверенно определить границы общего фрагмента.' : 'В снимках недостаточно различимых деталей для надёжного сопоставления.']
    };
    const [title, description] = descriptions[result.kind];
    const target = el('photoComparison'); target.replaceChildren(status(result.status), node('h3', title), node('p', description));
    if (result.kind === 'crop_candidate') {
      const r = result.region, box = el('photoReferencePreview').querySelector('.photo-crop-box');
      box.style.left = r.x * 100 + '%'; box.style.top = r.y * 100 + '%';
      box.style.width = r.width * 100 + '%'; box.style.height = r.height * 100 + '%'; box.hidden = false;
      target.append(node('p', 'Сопоставленная область занимает около ' + Math.round(result.retained_area * 100) + '% площади фото для сравнения. Это доля кадра, а не оценка манипулятивности.'));
      const back = node('button', 'Посмотреть рамку на фото', 'pro-button'); back.type = 'button';
      back.addEventListener('click', () => el('photoReferencePreview').scrollIntoView({behavior: 'auto', block: 'center'})); target.append(back);
    }
  }
  function showCue(findings, mark = null) {
    const note = el('photoCueNote'); note.replaceChildren();
    el('photoCaptionEvidence').querySelectorAll('[aria-expanded=true]').forEach(el => el.setAttribute('aria-expanded', 'false'));
    if (mark) mark.setAttribute('aria-expanded', 'true');
    for (const finding of findings) {
      const section = node('section'); section.append(node('strong', finding.label), node('p', finding.explanation));
      if (finding.status === 'quoted_candidate') section.append(node('p', 'Фрагмент находится в цитате или переданной речи. Проверьте автора высказывания.'));
      note.append(section);
    }
    note.hidden = false;
  }
  function highlightCaption(text, findings) {
    const chars = Array.from(text), ranges = [];
    for (const finding of findings) for (const part of finding.evidence || []) {
      if (part.field === 'text' && Number.isInteger(part.start) && Number.isInteger(part.end) && part.start >= 0 && part.end <= chars.length &&
          part.start < part.end && chars.slice(part.start, part.end).join('') === part.quote) ranges.push({...part, finding});
    }
    const events = new Map();
    for (const range of ranges) {
      for (const [position, add] of [[range.start, true], [range.end, false]]) {
        if (!events.has(position)) events.set(position, []);
        events.get(position).push({range, add});
      }
    }
    const target = el('photoCaptionEvidence'); target.replaceChildren();
    let cursor = 0; const active = new Set();
    function append(end) {
      if (end <= cursor) return;
      const quote = chars.slice(cursor, end).join('');
      if (!active.size) target.append(document.createTextNode(quote));
      else {
        const matches = [...new Set([...active].map(item => item.finding))], mark = node('mark', quote, 'photo-trigger');
        mark.tabIndex = 0; mark.setAttribute('role', 'button'); mark.setAttribute('aria-controls', 'photoCueNote'); mark.setAttribute('aria-expanded', 'false');
        mark.setAttribute('aria-label', quote + ': ' + [...new Set(matches.map(item => item.label))].join(', '));
        mark.title = matches.map(item => item.explanation).join('\n');
        mark.addEventListener('click', () => showCue(matches, mark));
        mark.addEventListener('focus', () => showCue(matches, mark));
        mark.addEventListener('pointerenter', event => { if (event.pointerType === 'mouse') showCue(matches, mark); });
        mark.addEventListener('keydown', event => { if (['Enter', ' '].includes(event.key)) { event.preventDefault(); mark.click(); } });
        target.append(mark);
      }
      cursor = end;
    }
    for (const position of [...events.keys()].sort((a, b) => a - b)) {
      append(position);
      for (const change of events.get(position)) if (change.add) active.add(change.range); else active.delete(change.range);
    }
    append(chars.length); target.hidden = !text;
  }
  function render(value) {
    const facts = el('photoFacts'), image = value.image; facts.replaceChildren();
    for (const [label, text] of [['Разрешение фото', image.width + ' × ' + image.height], ['Формат', image.format], ['Размер файла', sizeLabel(image.bytes)]]) {
      const item = node('dl', undefined, 'photo-fact'); item.append(node('dt', label), node('dd', text)); facts.append(item);
    }
    showComparison(value.comparison);
    const metadata = node('p', image.captured_at ? 'Дата съёмки из EXIF: ' + image.captured_at + '. Часовой пояс не установлен; эта запись может быть изменена.' : 'Дата съёмки в прочитанных метаданных не найдена. Это обычная ситуация для публикаций в интернете и не доказывает обработку.');
    el('photoComparison').append(metadata);
    if (value.date_comparison && Math.abs(value.date_comparison.difference_days) > 1) {
      el('photoComparison').append(node('p', 'Дата в EXIF и указанная дата публикации различаются на ' + Math.abs(value.date_comparison.difference_days) + ' дн. Проверьте историю снимка по источнику: EXIF не подтверждает дату события.'));
    }
    if (image.software) el('photoComparison').append(node('p', 'Поле «Программа» в файле: ' + image.software + '. Такая запись не доказывает монтаж или манипуляцию.'));
    const caption = value.caption, count = caption.findings.length;
    const copy = caption.status === 'not_provided' ? 'Подпись не добавлена. Текст внутри изображения автоматически не считывается.' :
      caption.status === 'partial' ? 'Полный анализатор подписи сейчас недоступен. Применены только специальные правила фотоподписей. Повторите проверку, чтобы применить все правила.' :
      count ? 'Найдены признаки для проверки. Наведите курсор или нажмите на выделение — пояснение появится под подписью.' : 'Совпадений текущих правил не найдено. Это не подтверждает нейтральность подписи.';
    el('photoCaptionStatus').textContent = copy;
    highlightCaption(caption.text, caption.findings);
    const labels = [...new Set(caption.findings.map(item => item.label))], list = node('ul', undefined, 'photo-finding-list');
    labels.forEach(label => list.append(node('li', label)));
    el('photoCaptionFindings').replaceChildren(list);
    if (count) showCue([caption.findings[0]]);
    const source = el('photoSourceLink'); source.replaceChildren();
    if (value.source_url) {
      const anchor = node('a', 'Смотреть источник'); anchor.href = value.source_url; anchor.target = '_blank'; anchor.rel = 'noopener noreferrer'; source.append(anchor);
    }
    el('photoResult').hidden = false; el('photoResultTitle').focus({preventScroll: true});
    el('photoState').textContent = caption.status === 'partial' ? 'Фото проверено. Анализ подписи выполнен частично.' : 'Проверка завершена. Результат ниже.';
  }
  for (const role of roles) inputs[role].addEventListener('change', () => readFile(role, inputs[role].files[0]));
  for (const id of ['photoCaption', 'photoSource', 'photoPublished']) el(id).addEventListener('input', invalidate);
  el('photoRemoveReference').addEventListener('click', () => { inputs.reference.value = ''; readFile('reference', null); });
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (working || roles.some(role => records[role]?.loading)) return;
    invalidate();
    let source = null;
    try {
      if (el('photoSource').value.trim()) {
        const url = new URL(el('photoSource').value.trim());
        if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password) throw Error(); source = url.href;
      }
    } catch {
      el('photoError').textContent = 'Укажите обычную ссылку на публикацию: https://…'; el('photoError').hidden = false; el('photoSource').focus(); return;
    }
    if (!inputs.publication.files[0]) { el('photoError').textContent = 'Добавьте фото из публикации.'; el('photoError').hidden = false; return; }
    const current = ++run;
    working = true; sync(); el('photoState').textContent = 'Сопоставляем изображения…';
    try {
      for (const role of roles) {
        if (inputs[role].files[0] && !records[role]?.prepared) await readFile(role, inputs[role].files[0]);
        if (inputs[role].files[0] && !records[role]?.prepared) throw Error(records[role]?.error || 'Не удалось прочитать фото.');
      }
      if (current !== run) return;
      const comparison = await imageJob('compare');
      if (current !== run) return;
      const text = el('photoCaption').value;
      const caption = await captionAnalysis(text);
      if (current !== run || caption.status === 'cancelled') return;
      const date = el('photoPublished').value || null;
      report = {schema_version: 'photo-context-1.0', created_at: new Date().toISOString(), scope: 'local-pilot',
        affects_rating: false, semantic_image_analysis: false, source_url: source, publication_date: date,
        image: records.publication.summary, reference: records.reference?.summary || null, comparison,
        date_comparison: PhotoContext.captureDateNote(records.publication.summary.captured_at, date), caption: {text, ...caption}};
      working = false; sync(); render(report);
    } catch (error) {
      if (current !== run) return;
      working = false; sync(); el('photoError').textContent = error.message || 'Не удалось завершить проверку. Повторите попытку.'; el('photoError').hidden = false;
    }
  });
  form.addEventListener('reset', () => {
    run++; working = false; cancelCaption?.(); stopImages();
    for (const role of roles) { revisions[role]++; release(role); }
    invalidate(); el('photoRemoveReference').hidden = true; sync();
  });
  document.addEventListener('pro:modechange', event => {
    if (event.detail !== 'photo' && working) {
      run++; cancelCaption?.(); working = false;
      stopImages(); sync(); el('photoState').textContent = 'Проверка остановлена при смене раздела. Можно запустить её снова.';
    }
  });
  el('photoDownload').addEventListener('click', () => {
    if (!report) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], {type: 'application/json;charset=utf-8'}));
    const anchor = node('a'); anchor.href = url; anchor.download = 'media-strazh-photo-context.json'; anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  window.addEventListener('pagehide', () => { run++; working = false; cancelCaption?.(); stopImages(); roles.forEach(release); invalidate(); sync(); });
})();
