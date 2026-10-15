/* Business V3: corpus briefing, editorial quality cues, verified contact selector.
   Email is composed locally; no publication or automatic sending is performed. */
(() => {
'use strict';
const $=id=>document.getElementById(id),make=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
let company=null,db=[],selected=new Set();
const inputs=['releaseTitle','releaseLead','releaseBody','releaseQuote','releaseAbout'];
const getText=()=>inputs.map(id=>$(id).value.trim()).filter(Boolean).join('\n\n');
/* One coherent overview instead of separate AI tiles competing with a chat. */
const overviewTrigger=$('overviewAssistantTrigger'),overviewBackdrop=$('overviewAssistantBackdrop'),
  overviewPanel=$('overviewAssistantPanel'),overviewClose=$('overviewAssistantClose');
let previousFocus=null;
function toggleAssistant(open){
 const shouldOpen=Boolean(open);
 if(shouldOpen&&!company)return;
 if(shouldOpen)previousFocus=document.activeElement;
 overviewPanel.hidden=!shouldOpen;
 overviewBackdrop.hidden=!shouldOpen;
 overviewTrigger.setAttribute('aria-expanded',String(shouldOpen));
 document.body.classList.toggle('overview-assistant-open',shouldOpen);
 if(shouldOpen)$('aiChatInput').focus();
 else if(previousFocus&&document.contains(previousFocus)&&!previousFocus.closest('[hidden]'))previousFocus.focus();
 else overviewTrigger.focus();
}
overviewTrigger.addEventListener('click',()=>toggleAssistant(overviewPanel.hidden));
overviewClose.addEventListener('click',()=>toggleAssistant(false));
overviewBackdrop.addEventListener('click',()=>toggleAssistant(false));
document.addEventListener('keydown',event=>{
 if(overviewPanel.hidden)return;
 if(event.key==='Escape'){event.preventDefault();toggleAssistant(false);return;}
 if(event.key!=='Tab')return;
 const focusable=Array.from(overviewPanel.querySelectorAll('button:not([disabled]),textarea:not([disabled]),a[href]')).filter(el=>el.getClientRects().length);
 if(!focusable.length)return;
 const first=focusable[0],last=focusable[focusable.length-1];
 if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}
 else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}
});
document.addEventListener('ms-tab-open',()=>{overviewTrigger.hidden=false;});
document.addEventListener('ms-business-exit',()=>{toggleAssistant(false);overviewTrigger.hidden=true;});
function askAssistant(question){
 toggleAssistant(true);
 if(question){$('aiChatInput').value=question;$('aiChatForm').requestSubmit();}
}
function openTab(tab){document.querySelector('[data-tab="'+tab+'"]').click();}
function snapshot(){
 const days=company.days;
 const mentions=company.selected;
 const negative=mentions.filter(m=>m.tone==='negative').length;
 const positive=mentions.filter(m=>m.tone==='positive').length;
 const neutral=mentions.filter(m=>m.tone==='neutral').length;
 const total=mentions.length,percent=total?Math.round(positive/total*100):0;
 $('aiSummaryCompany').textContent=company.company;
 $('aiMentionsTotal').textContent=total.toLocaleString('ru-RU');
 $('aiNegativeTotal').textContent='—';
 $('aiTrendTotal').textContent=company.trends.length;
 $('aiMentionsTone').textContent='Без оценки тональности: '+total;
 $('overviewTonePercent').textContent='—';
 $('overviewTonePositive').style.width=(total?100*positive/total:0)+'%';
 $('overviewToneNeutral').style.width=(total?100*neutral/total:0)+'%';
 $('overviewToneNegative').style.width=(total?100*negative/total:0)+'%';
 $('overviewAnalyticsSubtitle').textContent='Совпадения названия за '+days+' дней';
 $('overviewChartPeriod').textContent='Последние '+days+' дней';
 $('aiTopTrend').textContent=company.trends[0]?.title||'Нет тем в собранных материалах';
 // Chart only selected, dated publications; missing periods remain empty.
 const bins=Array.from({length:15},()=>0);
 mentions.forEach(m=>{
   const i=Math.floor((days-1-m.daysAgo)/days*15);
   bins[Math.max(0,Math.min(14,i))]++;
 });
 const max=Math.max(1,...bins);let path='M0 78';
 bins.forEach((value,i)=>{path+=' H'+Math.round((i+1)*400/15)+' V'+Math.round(78-value/max*61);});
 const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg'),line=document.createElementNS(ns,'path');
 svg.setAttribute('viewBox','0 0 400 95');svg.setAttribute('preserveAspectRatio','none');
 line.setAttribute('d',path);line.setAttribute('fill','none');line.setAttribute('stroke','#2589a2');
 line.setAttribute('stroke-width','2.5');line.setAttribute('stroke-linejoin','round');
 svg.append(line);$('aiOverviewChart').replaceChildren(svg);
 $('aiOverviewChart').setAttribute('aria-label','Динамика '+total+' совпадений названия в собранных публикациях за '+days+' дней');
}
function renderSignals(){
 const count=company.selected.filter(m=>m.tone==='negative').length;
 const first=company.trends[0],container=$('overviewSignals');container.replaceChildren();
 const signals=first?[{
  kind:'ВОЗМОЖНОСТЬ',tone:'opportunity',
  title:'Тема в собранных материалах: «'+first.title+'»',
  detail:first.count+' публикаций в текущей выборке. Проверьте первоисточники и наличие у компании подтверждённой экспертизы.',
  label:'Обсудить',act:()=>askAssistant('Как использовать инфоповод «'+first.title+'» для экспертного комментария?')
 }]:[];
 if(count>0)signals.push({
  kind:'ТРЕБУЕТ ВНИМАНИЯ',tone:'attention',
  title:'Проверить отрицательные упоминания',
  detail:'В выбранном периоде '+count+' проверенных негативных сообщений. Сначала изучите первоисточники, затем решайте, нужна ли реакция.',
  label:'Изучить',act:()=>openTab('mentions')
 });
 const relevant=company.trends[1];
 if(relevant)signals.push({
  kind:'ИДЕЯ ДЛЯ КОНТЕНТА',tone:'neutral',
  title:'Экспертный материал о теме «'+relevant.title+'»',
  detail:'Возможный ракурс для собственных каналов. Перед публикацией проверьте данные и сформулируйте полезный для аудитории вывод.',
  label:'Разобрать',act:()=>askAssistant('Предложи план материала для ресурсов компании на тему «'+relevant.title+'».')
 });
 signals.slice(0,3).forEach((s,i)=>{
  const row=make('article',null,'overview-signal overview-signal--'+s.tone),body=make('div',null,'overview-signal-copy'),
   meta=make('div',null,'overview-signal-kicker'),action=make('button',s.label+' ↗','overview-signal-action');
  meta.append(make('span',s.kind),make('span','0'+(i+1),'overview-signal-index'));
  body.append(meta,make('h4',s.title),make('p',s.detail));action.type='button';action.addEventListener('click',s.act);
  row.append(body,action);container.append(row);
 });
 if(!signals.length)container.append(make('p','Пока недостаточно собранных материалов для выбора темы.','business-empty'));
 $('aiContextLabel').textContent='Обновлено: '+new Intl.DateTimeFormat('ru-RU',{timeZone:'Europe/Moscow',dateStyle:'short',timeStyle:'short'}).format(new Date(company.generated_at))+' МСК. Выборка: '+company.coverage.published+' публикаций. Тональность не оценена.'+(company.coverage.limited?' Подборка ограничена.':'');
}
function renderSolutions(){
 const solutions=[
  {icon:'↗',title:'Экспертный комментарий',desc:'Подготовить позицию по отраслевой теме',act:()=>askAssistant('Предложи структуру экспертного комментария по теме «'+(company.trends[0]?.title||'требуется выбрать тему с подтверждёнными источниками')+'».')},
  {icon:'▤',title:'Пресс-релиз',desc:'Написать и проверить новостной материал',act:()=>openTab('pressReleases')},
  {icon:'◎',title:'Реакция на негатив',desc:'Разобрать ситуацию и подготовить ответ',act:()=>askAssistant('Предложи порядок проверки и отработки негативных публикаций о компании.')},
  {icon:'✎',title:'Материал для сайта',desc:'Создать план публикации для собственных каналов',act:()=>askAssistant('Предложи план публикации для сайта компании на основе актуальных отраслевых тем.')}
 ];
 const root=$('overviewSolutions');root.replaceChildren();
 solutions.forEach(s=>{
  const button=make('button',null,'overview-solution'),head=make('span',null,'overview-solution-head'),
    content=make('span',null,'overview-solution-content');
  button.type='button';
  head.append(make('span',s.icon,'overview-solution-icon'),make('span','↗','overview-solution-arrow'));
  content.append(make('strong',s.title),make('small',s.desc));
  button.append(head,content);button.addEventListener('click',s.act);root.append(button);
 });
}
let reviewVersion=0;
const review=$('releaseReview'),distribution=$('releaseDistribution'),outletsPopover=$('releaseOutletsPopover'),outletsToggle=$('releaseOpenOutlets');
function closeOutlets(){
 outletsPopover.hidden=true;
 outletsToggle.setAttribute('aria-expanded','false');
}
function resetEditorialFlow(){
 reviewVersion++;
 review.hidden=true;distribution.hidden=true;closeOutlets();
 Array.from($('releaseChecklist').children).forEach(li=>li.classList.remove('is-complete','is-checking','is-warning','is-optional'));
 $('releaseReviewState').textContent='Проверяем основные элементы материала…';
 $('releaseFeedback').textContent='';
}
inputs.forEach(id=>$(id).addEventListener('input',()=>{cancelImport();resetEditorialFlow();}));
document.addEventListener('ms-release-draft-changed',()=>{cancelImport();resetEditorialFlow();});
outletsToggle.addEventListener('click',()=>{
 const open=outletsPopover.hidden;
 outletsPopover.hidden=!open;outletsToggle.setAttribute('aria-expanded',String(open));
});
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!outletsPopover.hidden)closeOutlets();});
document.addEventListener('click',event=>{
 if(!outletsPopover.hidden&&!distribution.contains(event.target))closeOutlets();
});
const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function checkLogic(){
 const version=++reviewVersion;
 review.hidden=false;distribution.hidden=true;closeOutlets();
 const v=inputs.map(x=>$(x).value.trim());
 const placeholders=/РЕДАКЦИОННЫЕ ЗАМЕТКИ|ТЕЗИСЫ ИЗ WORD|\[(?:Уточните|Заполните|Добавьте|Дополните|Согласуйте)/iu.test(getText());
 const tests=[
  {ok:v[0].length>=15&&v[0].length<=125,required:true},
  {ok:v[1].length>=60,required:true},
  {ok:v[2].length>=180,required:true},
  {ok:Boolean(v[3]),required:false},
  {ok:Boolean(v[4]),required:false}
 ];
 const notes=[];
 if(!tests[0].ok)notes.push('Заголовок: уточните конкретный факт (15–125 символов).');
 if(!tests[1].ok)notes.push('Лид: добавьте кто, что, где, когда и почему это важно.');
 if(!tests[2].ok)notes.push('Основной текст: дополните факты и контекст.');
 if(!v[3])notes.push('Цитата необязательна; при наличии согласуйте её со спикером.');
 if(!v[4])notes.push('Рекомендуем добавить справку о компании и контакты.');
 if(placeholders)notes.push('В документе остались редакционные пометки — замените их фактами.');
 if(/лучший|уникальн|революционн|беспрецедентн/iu.test(v[0]+' '+v[1]))
   notes.push('Проверьте рекламные эпитеты и возможность их подтвердить.');
 notes.push('Орфография проверяется браузером; достоверность, причинно-следственные связи и цитаты требуют ручной проверки.');
 $('releaseReviewState').textContent='Анализируем структуру и полноту…';
 $('releaseFeedback').textContent='';
 const reduced=window.matchMedia('(prefers-reduced-motion: reduce)').matches;
 const items=Array.from($('releaseChecklist').children);
 items.forEach(li=>li.classList.remove('is-complete','is-checking','is-warning','is-optional'));
 for(let i=0;i<items.length;i++){
  if(version!==reviewVersion)return;
  const li=items[i];li.classList.add('is-checking');
  await wait(reduced?0:190);
  if(version!==reviewVersion)return;
  li.classList.remove('is-checking');
  li.classList.add(tests[i].ok?'is-complete':tests[i].required?'is-warning':'is-optional');
 }
 if(version!==reviewVersion)return;
 $('releaseFeedback').textContent=notes.join('\n');
 $('releaseFeedback').style.whiteSpace='pre-line';
 const canProceed=tests.filter(x=>x.required).every(x=>x.ok)&&!placeholders;
 $('releaseReviewState').textContent=canProceed
   ? 'Проверка завершена · можно выбрать редакции'
   : 'Проверка завершена · есть замечания к тексту';
 $('releaseReadinessNote').textContent=canProceed
   ? 'Выберите профильные издания. Письмо будет создано в вашей почтовой программе — без автоматической отправки.'
   : 'Издания можно выбрать сейчас. Перед подготовкой письма исправьте обязательные замечания и удалите служебные пометки.';
 // Editorial comments must never hide the next step. The actual email
 // composition still validates required fields and removes template markers.
 distribution.hidden=false;
 distribution.classList.remove('is-arriving');
 void distribution.offsetWidth;
 distribution.classList.add('is-arriving');
 $('releaseOpenOutlets').focus({preventScroll:true});
 distribution.scrollIntoView({behavior:reduced?'auto':'smooth',block:'nearest'});
}
$('releaseCheck').addEventListener('click',checkLogic);

document.addEventListener('ms-trend-action',event=>{
 if(!company||!event.detail?.trend)return;
 const {trend,destination}=event.detail;
 if(destination==='release'){
  const filled=inputs.some(id=>$(id).value.trim());
  if(filled&&!window.confirm('Заменить текущий текст проектом по выбранному инфоповоду? Несохранённые изменения будут потеряны.'))return;
  cancelImport();
  $('releaseTitle').value='Экспертный комментарий: '+trend.title;
  $('releaseLead').value='[Заполните: кто из экспертов компании комментирует тему, по какому поводу и почему это важно для читателя.]';
  $('releaseBody').value='ПРОЕКТ МАТЕРИАЛА — ТРЕБУЕТ РЕДАКТУРЫ\n\nТема: '+trend.title+'.\nКонтекст собранных публикаций: '+trend.detail+'\nИсточники: '+(trend.evidence||[]).map(item=>item.url).join('\n')+
    '\n\n[Добавьте проверенные факты, дату, предмет события, результаты и подтверждающие ссылки.]\n\n[Опишите собственную экспертизу компании и практический вывод для аудитории.]';
  $('releaseQuote').value='';$('releaseAbout').value='';
  resetEditorialFlow();
  $('releaseStatus').textContent='Проект по инфоповоду · не готов к публикации';
  document.querySelector('[data-tab="pressReleases"]').click();
  $('releaseTitle').focus();
 }else{
  openTab('opportunities');
  askAssistant('Какие PR-действия рекомендуются по инфоповоду «'+trend.title+'»? '+trend.detail);
 }
});
const recipients=()=>db.filter(x=>company&&x.industry===company.industry);
function updateSelect(){
 const items=recipients(),count=items.filter(x=>selected.has(x.id)).length;
 $('releaseSelectionCount').textContent=count+' выбрано';
 $('releaseSelectAll').checked=count>0&&count===items.length;
 $('releaseSelectAll').indeterminate=count>0&&count<items.length;
 $('releaseCompose').disabled=!count;
}
function renderOutlets(){
 const root=$('releaseMediaList');root.replaceChildren();
 if(!company)return;
 $('releaseIndustryHeading').textContent=company.industryLabel+' · редакционные и общие контакты';
 const items=recipients();
 if(!items.length){root.append(make('p','Нет доступных контактов. Проверьте загрузку базы.'));updateSelect();return;}
 items.forEach(x=>{
  const row=make('label',null,'release-media-item'),check=make('input'),info=make('span',null,'release-media-main');
  check.type='checkbox';check.checked=selected.has(x.id);
  check.addEventListener('change',()=>{check.checked?selected.add(x.id):selected.delete(x.id);updateSelect();});
  info.append(make('strong',x.name),make('small',x.type+' · '+x.contactType),make('span',x.email,'release-media-email'));
  if(x.note)info.append(make('small',x.note));
  const a=make('a','Проверить контакт ↗');a.href=x.source;a.target='_blank';a.rel='noopener noreferrer';a.addEventListener('click',e=>e.stopPropagation());info.append(a);
  row.append(check,info);root.append(row);
 });
 updateSelect();
}
$('releaseSelectAll').addEventListener('change',e=>{recipients().forEach(x=>e.target.checked?selected.add(x.id):selected.delete(x.id));renderOutlets();});
async function loadContacts(){
 try{const r=await fetch('media-contacts.json',{cache:'no-store'});if(!r.ok)throw Error('HTTP '+r.status);const j=await r.json();db=j.outlets||[];if(company){selected=new Set(recipients().map(x=>x.id));renderOutlets();}}
 catch(e){$('releaseMediaList').textContent='Контакты не загружены: '+e.message;$('releaseCompose').disabled=true;}
}
$('releaseCompose').addEventListener('click',()=>{
 const outlets=recipients().filter(x=>selected.has(x.id));
 if(!outlets.length){$('releaseMailStatus').textContent='Выберите редакции.';return;}
 const title=$('releaseTitle').value.trim(),lead=$('releaseLead').value.trim(),body=$('releaseBody').value.trim();
 if(title.length<10||lead.length<30||body.length<80){$('releaseMailStatus').textContent='Заполните заголовок, лид и основной текст перед подготовкой письма.';return;}
 if(/РЕДАКЦИОННЫЕ ЗАМЕТКИ|ТЕЗИСЫ ИЗ WORD|\[(?:Уточните|Заполните|Добавьте|Дополните)/iu.test(getText())){
   $('releaseMailStatus').textContent='В тексте остались служебные пометки. Сначала отредактируйте материал.';return;
 }
 const mailBody='Здравствуйте!\n\nНаправляем материал для рассмотрения редакцией:\n\n'+getText()+'\n\nС уважением,\nПресс-служба '+company.company+'\n[Добавьте ваш телефон и контактное лицо]';
 const url='mailto:?bcc='+encodeURIComponent(outlets.map(x=>x.email).join(','))+'&subject='+encodeURIComponent('Пресс-релиз: '+title.slice(0,100))+'&body='+encodeURIComponent(mailBody.slice(0,5700));
 $('releaseMailStatus').textContent='Создан черновик письма: '+outlets.length+' адресатов в BCC. Проверьте текст и контакты в почтовой программе, затем подтвердите отправку. Автоматической отправки нет.';
 window.location.href=url;
});
let importVersion=0,importPending=false;
function cancelImport(){
 importVersion++;
 if(importPending){importPending=false;$('releaseImportStatus').textContent='Импорт отменён: компания или редактор изменились.';}
}
document.addEventListener('ms-business-exit',cancelImport);
async function docxText(file){
 if(!/\.docx$/iu.test(file.name)||file.size>2*1024*1024)throw Error('Нужен .docx до 2 МБ.');
 const buf=await file.arrayBuffer(),v=new DataView(buf);let end=-1;
 for(let i=buf.byteLength-22;i>=Math.max(0,buf.byteLength-65557);i--){if(v.getUint32(i,true)===0x06054b50){end=i;break;}}
 if(end<0)throw Error('Не найден ZIP-каталог документа Word.');
 let at=v.getUint32(end+16,true),num=v.getUint16(end+10,true);
 for(let i=0;i<num;i++){
  if(v.getUint32(at,true)!==0x02014b50)throw Error('Повреждён ZIP-каталог.');
  const size=v.getUint32(at+20,true),method=v.getUint16(at+10,true),n=v.getUint16(at+28,true),ext=v.getUint16(at+30,true),comment=v.getUint16(at+32,true),local=v.getUint32(at+42,true);
  const name=new TextDecoder().decode(new Uint8Array(buf,at+46,n));
  if(name==='word/document.xml'){
   const expandedSize=v.getUint32(at+24,true),maximum=3*1024*1024;
   if(size>maximum||expandedSize>maximum)throw Error('Слишком большой текст в документе.');
   const start=local+30+v.getUint16(local+26,true)+v.getUint16(local+28,true);
   if(start+size>buf.byteLength)throw Error('Архив повреждён.');
   let bytes=new Uint8Array(buf,start,size);
   if(method===8){if(typeof DecompressionStream!=='function')throw Error('Нужен браузер с поддержкой распаковки DOCX.');
    const reader=new Blob([bytes]).stream().pipeThrough(new DecompressionStream('deflate-raw')).getReader();
    const chunks=[];let total=0;
    try{
     while(true){const part=await reader.read();if(part.done)break;
      total+=part.value.byteLength;
      if(total>maximum){await reader.cancel();throw Error('Слишком большой текст в документе.');}
      chunks.push(part.value);
     }
    }finally{reader.releaseLock();}
    bytes=new Uint8Array(total);let offset=0;for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.length;}
   }else if(method!==0)throw Error('Тип сжатия DOCX не поддерживается.');
   if(bytes.length!==expandedSize)throw Error('Некорректный размер текста в документе.');
   const xml=new DOMParser().parseFromString(new TextDecoder().decode(bytes),'application/xml');
   if(xml.getElementsByTagName('parsererror').length)throw Error('Ошибка содержимого Word.');
   const ns='http://schemas.openxmlformats.org/wordprocessingml/2006/main';
   const parts=Array.from(xml.getElementsByTagNameNS(ns,'p')).map(p=>Array.from(p.getElementsByTagNameNS(ns,'t')).map(x=>x.textContent).join('').trim()).filter(Boolean);
   if(!parts.length)throw Error('Нет текстовых абзацев. Сканы не поддерживаются.');
   return parts.join('\n').slice(0,18000);
  }
  at+=46+n+ext+comment;
 }
 throw Error('Не найден word/document.xml.');
}
$('releaseDocx').addEventListener('change',async event=>{
 const file=event.target.files?.[0];if(!file)return;$('releaseImportStatus').textContent='Открываем Word…';
 const version=++importVersion;
 importPending=true;
 try{const text=await docxText(file);if(version!==importVersion)return;const lines=text.split('\n').filter(x=>x.trim());
  $('releaseTitle').value='[Уточните заголовок] '+lines[0].slice(0,180);
  $('releaseLead').value='[Заполните лид: кто, что, где, когда и почему это важно]';
  $('releaseBody').value='ТЕЗИСЫ ИЗ WORD — НЕ ГОТОВЫЙ РЕЛИЗ\n\n'+lines.map((x,i)=>(i+1)+'. '+x).join('\n')+'\n\n[Дополните проверенные факты и контекст]';
  $('releaseQuote').value='';$('releaseAbout').value='';
  $('releaseImportStatus').textContent='Тезисы извлечены из '+file.name+'. Это структурированный редактируемый каркас, а не генерация ИИ.';
  $('releaseStatus').textContent='Требуется редактура';resetEditorialFlow();
 }catch(e){if(version===importVersion)$('releaseImportStatus').textContent='Ошибка чтения: '+e.message;}
 finally{if(version===importVersion){importPending=false;event.target.value='';}}
});
document.addEventListener('ms-business-data',e=>{
 const next=e.detail;if(!next?.company)return;
 const isNew=!company||next.company!==company.company||next.industry!==company.industry;
 if(isNew)cancelImport();
 company=next;snapshot();renderSignals();renderSolutions();
 if(isNew)selected=new Set(recipients().map(x=>x.id));
 renderOutlets();
});
loadContacts();
})();
