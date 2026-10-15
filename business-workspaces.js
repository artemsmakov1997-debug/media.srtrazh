/* Self-contained demo workspace. No network requests or AI provider connections. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const make = (tag, text, cls) => {
    const el = document.createElement(tag);
    if (text !== undefined && text !== null) el.textContent = text;
    if (cls) el.className = cls;
    return el;
  };
  let data = null;
  let currentCompany = '';
  let drafts = [];
  let activeDraft = null;
  const inputs = {
    title: $('releaseTitle'), lead: $('releaseLead'), body: $('releaseBody'),
    quote: $('releaseQuote'), about: $('releaseAbout')
  };
  const storageKey = () => 'media-strazh-release-drafts-v1:' +
    encodeURIComponent((data.company + ':' + data.industry).toLocaleLowerCase('ru-RU'));
  const nowLabel = () => new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit'
  }).format(new Date());
  const mentionCounts = () => {
    const selected = data.mentions.filter(m => m.daysAgo <= data.days);
    return {
      total: selected.length,
      negative: selected.filter(m => m.tone === 'negative').length,
      positive: selected.filter(m => m.tone === 'positive').length
    };
  };
  const addChat = (role, text) => {
    const bubble = make('div', text, 'ai-message ai-message--' + role);
    $('aiChatMessages').append(bubble);
    $('aiChatMessages').scrollTop = $('aiChatMessages').scrollHeight;
  };
  function resetChat() {
    $('aiChatMessages').replaceChildren();
    addChat('assistant', 'Здравствуйте! Я демонстрационный PR-ассистент. Покажу идеи продвижения для «' +
      data.company + '» по условным упоминаниям и отраслевым темам. Можно выбрать карточку или задать вопрос.');
  }
  function answer(text) {
    const q = text.toLocaleLowerCase('ru-RU');
    const counts = mentionCounts(), trends = data.trends, ideas = data.opportunities;
    if (/негатив|репутац|кризис|отрицател|жалоб/.test(q))
      return 'За ' + data.days + ' дней в демонстрационной выборке ' + counts.negative +
        ' отрицательных упоминаний. Проверьте первоисточники и наличие фактических ошибок; подготовьте согласованный комментарий и ответственные контакты. Не реагируйте публично, пока не подтверждена фактура.';
    if (/план|стратег|шаг|недел|действ/.test(q))
      return 'Предварительный PR-план (демо):\n1. Проверить исходные публикации и цифры.\n2. Выбрать тему «' +
        trends[0].title + '» и сформировать экспертную позицию.\n3. Подготовить материал «' +
        ideas[0].title + '».\n4. Согласовать факты и предложить его профильным редакциям.\n5. Отслеживать публикации и реакцию аудитории.';
    if (/пресс|релиз|текст|напис|материал/.test(q))
      return 'Начать можно с темы «' + ideas[0].title +
        '». Нажмите «В черновик» на карточке — тема и редакционные ориентиры перенесутся в раздел «Пресс-релизы». Факты, цифры и цитаты необходимо добавить самостоятельно.';
    if (/инфоповод|тема|тренд|сми|публикац/.test(q))
      return 'В демонстрационной отраслевой повестке выделяются темы: ' +
        trends.map(t => '«' + t.title + '»').join(', ') +
        '. Это условные примеры, а не результат реального мониторинга. Для первого питча рекомендую проверить тему «' + trends[0].title + '».';
    return 'В этой версии доступен сценарный диалог без подключения языковой модели. Попробуйте спросить о PR-плане, негативе, инфоповодах или пресс-релизе. Рекомендации основаны только на демонстрационных данных.';
  }
  const submitChat = text => {
    const clean = text.trim();
    if (!clean || !data) return;
    addChat('user', clean);
    addChat('assistant', answer(clean));
  };
  $('aiChatForm').addEventListener('submit', event => {
    event.preventDefault();
    const input = $('aiChatInput');
    submitChat(input.value);
    input.value = '';
  });
  $('aiChatInput').addEventListener('keydown', event => {
    if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      $('aiChatForm').requestSubmit();
    }
  });
  document.querySelectorAll('[data-ai-prompt]').forEach(btn => btn.addEventListener('click', () => {
    submitChat(btn.dataset.aiPrompt);
  }));
  function renderCards() {
    const list = $('assistantCards');
    list.replaceChildren();
    const counts = mentionCounts();
    $('aiContextLabel').textContent = 'Условные данные: ' + counts.total +
      ' упоминаний за ' + data.days + ' дней · отрасль «' + data.industryLabel + '»';
    data.opportunities.slice(0, 3).forEach((idea, i) => {
      const trend = data.trends[i];
      const card = make('article', null, 'ai-card');
      const top = make('div', null, 'ai-card-top');
      top.append(make('span', idea.kind, 'ai-card-kind'), make('span', '0' + (i + 1), 'ai-card-index'));
      const title = make('h3', idea.title), description = make('p', idea.detail);
      const evidence = make('div', null, 'ai-card-source');
      evidence.append(make('b', 'Основание (демо): '),
        document.createTextNode('тема «' + trend.title + '»; ' + counts.total + ' условных упоминаний в выбранном периоде.'));
      const actions = make('div', null, 'ai-card-actions');
      const discuss = make('button', 'Обсудить идею ↗');
      const draft = make('button', 'В черновик →', 'ai-card-primary');
      discuss.type = 'button'; draft.type = 'button';
      discuss.addEventListener('click', () => {
        addChat('user', 'Как реализовать идею «' + idea.title + '»?');
        addChat('assistant', 'Предлагаемый порядок действий (демо):\n' +
          data.actions[i].map((step, number) => (number + 1) + '. ' + step).join('\n') +
          '\nПеред публикацией проверьте факты и первоисточники.');
        $('aiChatInput').focus();
      });
      draft.addEventListener('click', () => startFromIdea(i));
      actions.append(discuss, draft);
      card.append(top, title, description, evidence, actions);
      list.append(card);
    });
  }
  const fields = () => Object.fromEntries(Object.entries(inputs).map(([k, el]) => [k, el.value.trim()]));
  function fill(draft) {
    for (const [key, input] of Object.entries(inputs)) input.value = draft[key] || '';
    activeDraft = draft.id || null;
    $('releaseStatus').textContent = activeDraft ? 'Черновик · ' + (draft.updated || 'сохранён') : 'Новый черновик';
    updateChecklist();
    renderDraftList();
  }
  const blank = () => ({id:null,title:'',lead:'',body:'',quote:'',about:''});
  function readDrafts() {
    try {
      const value = JSON.parse(localStorage.getItem(storageKey()) || '[]');
      drafts = Array.isArray(value) ? value.filter(x => x && typeof x.id === 'string').slice(0,50) : [];
    } catch (_) { drafts = []; }
  }
  function persistDrafts() {
    try { localStorage.setItem(storageKey(), JSON.stringify(drafts));return true; }
    catch (_) { return false; }
  }
  function renderDraftList() {
    const container = $('releaseDrafts'); container.replaceChildren();
    if (!drafts.length) container.append(make('p','Черновиков пока нет.','release-storage-note'));
    drafts.forEach(d => {
      const btn = make('button',null,'release-draft' + (d.id === activeDraft ? ' is-active' : ''));
      btn.type = 'button';
      btn.append(make('span',d.title || 'Без названия'),make('small',d.updated || 'Черновик'));
      btn.addEventListener('click',() => fill(d));
      container.append(btn);
    });
  }
  const setStatus = text => { $('releaseStatus').textContent = text; };
  function updateChecklist() {
    const value = fields();
    ['title','lead','body','quote','about'].forEach((name,i) =>
      $('releaseChecklist').children[i].classList.toggle('is-complete',Boolean(value[name])));
  }
  Object.values(inputs).forEach(input => input.addEventListener('input', () => {
    setStatus('Не сохранено');
    updateChecklist();
  }));
  $('releaseNew').addEventListener('click', () => {fill(blank());$('releaseTitle').focus();});
  $('releaseSave').addEventListener('click', () => {
    if (!data) return;
    const value = fields();
    const draft = {...value,id:activeDraft || ('draft-' + Date.now()),updated:nowLabel()};
    drafts = [draft,...drafts.filter(d => d.id !== draft.id)].slice(0,50);
    const saved = persistDrafts();
    fill(draft);
    if (!saved) setStatus('Не удалось сохранить: хранилище браузера недоступно');
  });
  function startFromIdea(index) {
    const idea = data.opportunities[index], trend = data.trends[index];
    fill({
      id:null,title:'',
      lead:'',
      body:'РЕДАКЦИОННЫЕ ЗАМЕТКИ — НЕ ДЛЯ ПУБЛИКАЦИИ\nТема: ' + idea.title +
        '\nОснование (демо): ' + trend.title + '.\nРакурс: ' + idea.detail +
        '\n\n[Добавьте подтверждённую новость, дату, место, факты и цифры.]\n[Согласуйте цитаты и контакт пресс-службы.]',
      quote:'',about:''
    });
    $('releaseFeedback').textContent = 'Тема перенесена из ИИ-ассистента. Это редакционные заметки, не готовый пресс-релиз.';
    $('releaseStatus').textContent = 'На основе идеи · не сохранено';
    document.querySelector('[data-tab="pressReleases"]').click();
    $('releaseTitle').focus();
  }
  // The staged editorial review is owned by business-v3.js.
  const fullText = () => {
    const d = fields();
    return [d.title,d.lead,d.body,d.quote ? 'Цитата: ' + d.quote : '',d.about ? 'О компании: ' + d.about : ''].filter(Boolean).join('\n\n');
  };
  $('releaseCopy').addEventListener('click', async () => {
    if (!fullText()) { $('releaseFeedback').textContent='Сначала заполните хотя бы одно поле.';return; }
    try { await navigator.clipboard.writeText(fullText());$('releaseFeedback').textContent='Текст скопирован.'; }
    catch (_) { $('releaseFeedback').textContent='Копирование недоступно в этом браузере. Выделите текст в редакторе.'; }
  });

  /* Minimal valid OOXML (.docx) using an uncompressed ZIP archive; no dependencies or external services. */
  const utf8 = text => new TextEncoder().encode(text);
  const xml = text => String(text).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  const concat = arrays => {
    const out = new Uint8Array(arrays.reduce((size,item) => size + item.length,0));
    let offset=0;arrays.forEach(part => {out.set(part,offset);offset+=part.length;});return out;
  };
  const crc32 = bytes => {
    let c=0xffffffff;
    for(const byte of bytes){c ^= byte;for(let i=0;i<8;i++)c = (c>>>1) ^ (c&1 ? 0xedb88320 : 0);}
    return (c^0xffffffff)>>>0;
  };
  const zipStore = files => {
    let pos=0;
    const local=[],central=[];
    for (const [name,text] of files) {
      const fn=utf8(name),bytes=utf8(text),crc=crc32(bytes);
      const head=new Uint8Array(30+fn.length),h=new DataView(head.buffer);
      h.setUint32(0,0x04034b50,true);h.setUint16(4,20,true);
      h.setUint32(14,crc,true);h.setUint32(18,bytes.length,true);h.setUint32(22,bytes.length,true);
      h.setUint16(26,fn.length,true);head.set(fn,30);
      const cen=new Uint8Array(46+fn.length),v=new DataView(cen.buffer);
      v.setUint32(0,0x02014b50,true);v.setUint16(4,20,true);v.setUint16(6,20,true);
      v.setUint32(16,crc,true);v.setUint32(20,bytes.length,true);v.setUint32(24,bytes.length,true);
      v.setUint16(28,fn.length,true);v.setUint32(42,pos,true);cen.set(fn,46);
      central.push(cen);local.push(head,bytes);pos+=head.length+bytes.length;
    }
    const center=concat(central),end=new Uint8Array(22),view=new DataView(end.buffer);
    view.setUint32(0,0x06054b50,true);view.setUint16(8,central.length,true);
    view.setUint16(10,central.length,true);view.setUint32(12,center.length,true);view.setUint32(16,pos,true);
    return new Blob([concat([...local,center,end])],{type:'application/vnd.openxmlformats-officedocument.wordprocessingml.document'});
  };
  function buildDocx(){
    const paragraphs = fullText().split(/\r?\n/).map(line =>
      '<w:p><w:r><w:t xml:space="preserve">' + xml(line) + '</w:t></w:r></w:p>').join('');
    return zipStore([
      ['[Content_Types].xml','<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>'],
      ['_rels/.rels','<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>'],
      ['word/document.xml','<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>' + paragraphs + '<w:sectPr/></w:body></w:document>']
    ]);
  }
  $('releaseDownload').addEventListener('click', () => {
    if(!fullText()){ $('releaseFeedback').textContent='Заполните материал перед экспортом.';return;}
    const blob=buildDocx(),url=URL.createObjectURL(blob),link=document.createElement('a');
    const safe=(fields().title || 'press-release').slice(0,65).replace(/[\\/:*?"<>|]/g,'_');
    link.href=url;link.download=safe+'.docx';document.body.append(link);link.click();link.remove();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
  });

  document.addEventListener('ms-business-data', event => {
    const next=event.detail;
    if (!next || !next.company || !next.trends || !next.opportunities) return;
    const key = next.company + '::' + next.industry;
    const changed = key !== currentCompany;
    data=next;
    if(changed){
      currentCompany=key;
      readDrafts();
      fill(blank());
      resetChat();
      $('releaseFeedback').textContent='Проверка структуры не заменяет редакторскую проверку фактов и источников.';
    }
    renderCards();
  });
})();
