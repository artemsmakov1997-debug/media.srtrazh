/* MЕДИА.СТРАЖ PRO: client-only reporting. Real corpus matches; activity is session-local. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const make = (tag, text, cls) => {
    const el = document.createElement(tag);
    if (text != null) el.textContent = text;
    if (cls) el.className = cls;
    return el;
  };
  let data = null;
  let activity = [];
  const stamp = () => new Intl.DateTimeFormat('ru-RU', {
    timeZone:'Europe/Moscow',day: '2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'
  }).format(new Date());
  const storageKey = () => 'media-strazh-report-actions-v1:' +
    encodeURIComponent((data.company+':'+data.industry).toLocaleLowerCase('ru-RU'));
  const draftStorageKey = () => 'media-strazh-release-drafts-v1:' +
    encodeURIComponent((data.company+':'+data.industry).toLocaleLowerCase('ru-RU'));
  function loadActivity() {
    try {
      const entries = JSON.parse(sessionStorage.getItem(storageKey()) || '[]');
      activity = Array.isArray(entries) ? entries.filter(e =>
        e && typeof e.label === 'string' && typeof e.time === 'string'
      ).slice(-25) : [];
    } catch (_) {activity=[];}
  }
  function note(label) {
    if (!data) return;
    activity.push({label:String(label).slice(0,180),time:stamp()});
    activity=activity.slice(-25);
    try {sessionStorage.setItem(storageKey(),JSON.stringify(activity));} catch (_) {}
    if (!$('report').hidden) render();
  }
  const count = n => Number(n).toLocaleString('ru-RU');
  function render() {
    if (!data) return;
    const mentions=data.selected;
    $('reportCompany').textContent=data.company+' · '+data.industryLabel;
    $('reportDate').textContent='Сформировано: '+stamp();
    $('reportPeriod').textContent='Период: '+data.days+' дней';
    $('reportMentions').textContent=count(mentions.length);
    $('reportPositive').textContent='—';
    $('reportNeutral').textContent='—';
    $('reportNegative').textContent='—';

    const ml=$('reportMentionList');ml.replaceChildren();
    if(!mentions.length)ml.append(make('li','В собранных материалах за период совпадений названия нет. Это не означает отсутствия публикаций во всех СМИ.'));
    else mentions.forEach(m=>{
      const li=make('li'),title=make('strong',m.title);
      const source=m.source;
      const link=make('a','Открыть источник ↗');link.href=m.url;link.target='_blank';link.rel='noopener noreferrer';
      li.append(title,make('small',source+' · тональность не оценена · '+new Intl.DateTimeFormat('ru-RU',{timeZone:'Europe/Moscow',dateStyle:'short',timeStyle:'short'}).format(new Date(m.published_at))+' МСК'),link);
      ml.append(li);
    });

    const tl=$('reportTrendList');tl.replaceChildren();
    data.trends.forEach(t=>{
      const li=make('li');
      li.append(make('strong',t.title),make('small',t.count+' публикаций в выборке; изменение: '+t.growth));
      tl.append(li);
    });

    if(!data.trends.length)tl.append(make('li','В выборке нет материалов по настроенным отраслевым темам.'));

    const title=$('releaseTitle').value.trim(),lead=$('releaseLead').value.trim(),
      body=$('releaseBody').value.trim();
    let saved=0;
    try {const d=JSON.parse(localStorage.getItem(draftStorageKey())||'[]');saved=Array.isArray(d)?d.length:0;} catch (_) {}
    const hasDraft=Boolean(title||lead||body);
    $('reportDraftTitle').textContent=hasDraft?(title||'Текущий черновик без заголовка'):'Пресс-релиз не подготовлен';
    $('reportDraftStatus').textContent='Сохранённых черновиков в этом браузере: '+saved;
    $('reportDraftSummary').textContent=hasDraft
      ? (lead||body||'Текст в процессе подготовки').slice(0,460)
      : 'После заполнения редактора сведения о текущем материале появятся здесь.';
    const review=$('releaseReview');
    $('reportReviewStatus').textContent=review.hidden ? 'Не выполнена для текущего текста'
      : $('releaseReviewState').textContent.trim();
    const distribution=$('releaseDistribution');
    const selection=distribution.hidden ? [] :
      [...document.querySelectorAll('#releaseMediaList .release-media-item')].filter(row =>
        row.querySelector('input[type="checkbox"]')?.checked
      ).map(row => row.querySelector('strong')?.textContent.trim()).filter(Boolean);
    $('reportOutletsCount').textContent=count(selection.length);
    $('reportOutlets').textContent=selection.length
      ? 'Выбраны для подготовки письма: '+selection.join('; ')+'. Отправка не подтверждена.'
      : 'Адресаты пока не выбраны после редакторской проверки.';

    const list=$('reportActivity');list.replaceChildren();
    if(!activity.length)list.append(make('li','Действия в этой сессии ещё не зафиксированы.','report-activity-empty'));
    else activity.slice().reverse().forEach(entry=>{
      const li=make('li');li.append(make('span',entry.label),make('small',entry.time));list.append(li);
    });
  }
  document.addEventListener('ms-business-data',event=>{
    const next=event.detail;
    if(!next?.company || !next.mentions || !next.trends) return;
    const different=!data || next.company!==data.company || next.industry!==data.industry;
    data=next;
    if(different)loadActivity();
    if(!$('report').hidden)render();
  });
  document.addEventListener('ms-tab-open',event=>{
    if(event.detail?.name==='report')render();
  });
  document.addEventListener('ms-trend-action',event=>{
    if(event.detail?.trend?.title)note('Выбран инфоповод: '+event.detail.trend.title);
  });
  document.addEventListener('click',event=>{
    const button=event.target instanceof Element ? event.target.closest('button') : null;
    if(!button||!data)return;
    if(button.closest('#overviewSolutions')){
      note('Выбрано готовое решение: '+button.querySelector('strong')?.textContent.trim());
    }else if(button.id==='releaseCheck'){
      note('Запущена редакторская проверка текста');
    }else if(button.id==='releaseOpenOutlets'){
      note('Открыт список отраслевых редакций');
    }else if(button.id==='releaseCompose'){
      note('Запрошена подготовка письма редакциям (отправка не подтверждена)');
    }else if(button.id==='releaseDownload'){
      note('Запрошен экспорт пресс-релиза в DOCX');
    }
  });
  $('releaseDocx').addEventListener('change',event=>{
    if(event.target.files?.length)note('Выбран Word-файл для импорта тезисов');
  });
  $('aiChatForm').addEventListener('submit',()=>note('Запрос к сценарному PR-помощнику'));
  $('reportExport').addEventListener('click',()=>{
    if(!data)return;
    render();
    // Printing uses the browser's native PDF destination for reliable Cyrillic
    // fonts and pagination, with no external libraries or data upload.
    const originalTitle=document.title;
    document.title='Отчёт — '+data.company+' — МЕДИА.СТРАЖ PRO';
    const restore=()=>{document.title=originalTitle;window.removeEventListener('afterprint',restore);};
    window.addEventListener('afterprint',restore);
    try {window.print();}
    catch(error){restore();alert('Не удалось открыть печать. Попробуйте другой браузер.');}
    setTimeout(restore,3000);
  });
})();
