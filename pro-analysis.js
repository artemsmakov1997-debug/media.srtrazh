(() => {
  const node = (tag, text, cls) => {
    const el = document.createElement(tag);
    if (text !== undefined) el.textContent = text;
    if (cls) el.className = cls;
    return el;
  };
  const format = value => {
    const d = new Date(value);
    return Number.isFinite(d.getTime()) ? new Intl.DateTimeFormat('ru-RU', {
      timeZone: 'Europe/Moscow', dateStyle: 'short', timeStyle: 'short'
    }).format(d) + ' МСК' : 'Время не сохранено';
  };
  const link = url => {
    const a = node('a', 'Смотреть источник');
    try {
      const u = new URL(url);
      if (u.protocol !== 'https:') return node('span', 'Ссылка недоступна');
      a.href = u.href; a.target = '_blank'; a.rel = 'noopener noreferrer';
    } catch { return node('span', 'Ссылка недоступна'); }
    return a;
  };
  const button = (text, action, cls = '') => {
    const el = node('button', text, 'pro-button ' + cls);
    el.type = 'button'; el.addEventListener('click', action);
    return el;
  };
  const empty = (target, text) => target.replaceChildren(node('p', text, 'pro-empty'));
  const comparisonNote = 'Отличающаяся формулировка заголовка. Проверьте её смысл и факты по источнику; различие не доказывает манипуляцию.';
  function renderSegments(parent, segments, tag, note) {
    for (const part of segments || []) {
      const el = node(part.changed ? tag : 'span', part.text);
      if (part.changed && tag === 'mark') {
        el.title = part.explanation || comparisonNote;
        el.tabIndex = 0;
        const explain = () => { if (note) note.textContent = el.title; };
        el.addEventListener('click', explain);
        el.addEventListener('focus', explain);
        el.addEventListener('keydown', event => {
          if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); explain(); }
        });
      }
      parent.append(el);
    }
  }
  // Separate native dialogs allow returning from a publication to the full story.
  // Escape applies to the topmost native dialog; keep Tab within its controls.
  const dialogs = [];
  let previousOverflow;
  let scrollLocked = false;
  function restoreScroll() {
    if (scrollLocked && !dialogs.some(item => item.open)) {
      document.body.style.overflow = previousOverflow;
      scrollLocked = false;
    }
  }
  function closeDialog(dialog) { dialog.close(); restoreScroll(); }
  function createDialog(id) {
    const dialog = node('dialog', undefined, 'pro-dialog');
    dialog.id = id;
    const head = node('header', undefined, 'pro-dialog-head');
    const title = node('h2'); title.id = id + 'Title';
    dialog.setAttribute('aria-labelledby', title.id);
    const close = button('×', () => closeDialog(dialog), 'pro-dialog-close');
    close.setAttribute('aria-label', 'Закрыть окно');
    head.append(title, close);
    const body = node('div', undefined, 'pro-dialog-body');
    dialog.append(head, body); document.body.append(dialog); dialogs.push(dialog);
    dialog.addEventListener('keydown', event => {
      if (event.key !== 'Tab') return;
      const controls = [...dialog.querySelectorAll('button, a[href], [tabindex="0"]')]
        .filter(el => !el.disabled && el.getClientRects().length);
      const first = controls[0], last = controls.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    });
    dialog.addEventListener('click', event => {
      const rect = dialog.getBoundingClientRect();
      if (event.target === dialog && (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom)) closeDialog(dialog);
    });
    dialog.addEventListener('cancel', event => { event.preventDefault(); closeDialog(dialog); });
    dialog.addEventListener('close', restoreScroll);
    return {dialog, title, body, close};
  }
  function show(view) {
    if (!scrollLocked) previousOverflow = document.body.style.overflow;
    view.body.scrollTop = 0;
    view.dialog.showModal(); scrollLocked = true; document.body.style.overflow = 'hidden'; view.close.focus();
  }
  const allView = createDialog('proStoryModal');
  const detailView = createDialog('proPublicationModal');
  function openPublication(item) {
    detailView.title.textContent = item.title || 'Публикация';
    const meta = node('div', undefined, 'pro-meta');
    meta.append(node('span', item.source), node('time', format(item.published_at)));
    const note = node('p', 'Подсвечены формулировки из сравнения заголовков, встречающиеся в сохранённом тексте. Выделение само по себе не доказывает манипуляцию.', 'pro-explanation');
    note.setAttribute('aria-live', 'polite');
    const headline = node('h3', undefined, 'pro-detail-headline');
    renderSegments(headline, item.phrases || [{text: item.title, changed: false}], 'mark', note);
    const body = node('div', undefined, 'pro-publication-text');
    if (item.text) {
      if (Array.isArray(item.text_phrases) && item.text_phrases.map(p => p.text).join('') === item.text) renderSegments(body, item.text_phrases, 'mark', note);
      else body.textContent = item.text;
    } else body.append(node('p', 'Текст публикации пока не сохранён. Доступны заголовок и ссылка на источник.', 'pro-empty'));
    const footer = node('footer', undefined, 'pro-source-actions'); footer.append(link(item.url));
    detailView.body.replaceChildren(meta, headline, note, node('p', 'Доступный сохранённый текст', 'eyebrow'), body, footer);
    show(detailView);
  }
  function headlineCard(item) {
    const cell = node('article', undefined, 'pro-headline');
    const meta = node('div', undefined, 'pro-meta');
    meta.append(node('span', item.source), node('time', format(item.published_at)));
    const title = node('h3', item.title || (item.phrases || []).map(p => p.text).join(''));
    const more = button('Подробнее', () => openPublication(item), 'pro-publication-more');
    more.setAttribute('aria-haspopup', 'dialog');
    cell.append(meta, title, more);
    return cell;
  }
  function openStory(story) {
    allView.title.textContent = story.title;
    const grid = node('div', undefined, 'pro-grid');
    for (const item of story.items) grid.append(headlineCard(item));
    allView.body.replaceChildren(grid); show(allView);
  }
  const stories = document.getElementById('storiesContent');
  const history = document.getElementById('historyContent');
  async function load() {
    try {
      const response = await fetch('data/pro.json', {cache: 'no-store'});
      if (!response.ok) throw Error();
      const data = await response.json();
      if (data.schema_version !== 'pro-evidence-1.0' || !Array.isArray(data.stories) || !Array.isArray(data.history)) throw Error();
      stories.replaceChildren();
      for (const story of data.stories) {
        const card = node('article', undefined, 'pro-story');
        const head = node('header', undefined, 'pro-story-heading');
        const meta = node('div', undefined, 'pro-meta');
        if (story.topic) meta.append(node('span', story.topic, 'eyebrow'));
        meta.append(node('span', '', 'pro-story-count'));
        // Russian publication forms, independent of browser unit translations.
        const count = story.items.length, last = count % 10, hundred = count % 100;
        meta.lastChild.textContent = count + ' ' + (last === 1 && hundred !== 11 ? 'публикация' : last >= 2 && last <= 4 && !(hundred >= 12 && hundred <= 14) ? 'публикации' : 'публикаций');
        head.append(meta, node('h3', story.title));
        const grid = node('div', undefined, 'pro-grid');
        for (const item of story.items.slice(0, 3)) grid.append(headlineCard(item));
        card.append(head, grid);
        if (story.items.length > 3) {
          const actions = node('div', undefined, 'pro-story-actions');
          const all = button('Показать все', () => openStory(story), 'pro-show-all');
          all.setAttribute('aria-haspopup', 'dialog'); actions.append(all); card.append(actions);
        }
        stories.append(card);
      }
      if (!data.stories.length) empty(stories, 'Пока нет подходящих политических сюжетов с содержательно разными заголовками. Подборка обновляется при сборе новых публикаций.');
      const filters = node('div', undefined, 'pro-filter'), source = node('select'), kind = node('select');
      source.id = 'historySource'; kind.id = 'historyKind';
      for (const [select, label, options] of [
        [source, 'Издание', [['', 'Все издания'], ...[...new Set(data.history.map(x => x.source))].map(x => [x, x])]],
        [kind, 'Что изменилось', [['', 'Все правки'], ['title', 'Изменён заголовок'], ['text', 'Уточнён текст']]]
      ]) {
        const field = node('label', label);
        for (const [value, text] of options) { const opt = node('option', text); opt.value = value; select.append(opt); }
        field.append(select); filters.append(field);
      }
      const list = node('div'); history.replaceChildren(filters, list);
      const pair = v => {
        const row = node('div', undefined, 'pro-diff');
        for (const [key, label, tag] of [['before', 'Было', 'del'], ['after', 'Стало', 'ins']]) {
          const col = node('div', undefined, 'pro-version'), time = node('p', format(v[key + '_at']));
          time.title = 'Время фиксации версии сборщиком, а не точный момент правки редакцией';
          col.append(node('strong', label), time);
          const body = node('p'); renderSegments(body, v[key], tag); col.append(body); row.append(col);
        }
        return row;
      };
      function renderHistory() {
        list.replaceChildren();
        for (const item of data.history) {
          const versions = item.versions.filter(v => !kind.value || v.kind === kind.value);
          if ((source.value && item.source !== source.value) || !versions.length) continue;
          const current = versions.at(-1), card = node('article', undefined, 'pro-revision'), meta = node('div', undefined, 'pro-meta');
          meta.append(node('span', item.source + ' · ' + (current.kind === 'title' ? 'Изменён заголовок' : 'Уточнён текст')), node('time', format(current.after_at)));
          card.append(meta, node('h3', current.title), pair(current));
          if (versions.length > 1) {
            const details = node('details'); details.append(node('summary', 'История версий'));
            for (const version of versions.slice(0, -1).reverse()) details.append(pair(version));
            card.append(details);
          }
          const actions = node('footer', undefined, 'pro-source-actions'); actions.append(link(item.url)); card.append(actions); list.append(card);
        }
        if (!list.children.length) empty(list, 'Зафиксированных правок по выбранным условиям пока нет. Здесь появятся отличающиеся версии одной публикации, сохранённые сборщиком.');
      }
      source.addEventListener('change', renderHistory); kind.addEventListener('change', renderHistory); renderHistory();
    } catch {
      for (const target of [stories, history]) {
        empty(target, 'Данные сейчас недоступны. Повторить загрузку можно кнопкой ниже.');
        target.append(button('Повторить загрузку', load));
      }
    }
  }
  load();
})();
