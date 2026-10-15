/* Business V3: demo briefing, editorial quality cues, verified contact selector.
   Email is composed locally; no publication or automatic sending is performed. */
(() => {
'use strict';
const $=id=>document.getElementById(id),make=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
let company=null,db=[],selected=new Set();
const inputs=['releaseTitle','releaseLead','releaseBody','releaseQuote','releaseAbout'];
const getText=()=>inputs.map(id=>$(id).value.trim()).filter(Boolean).join('\n\n');
function snapshot(){
  const mentions=company.mentions.filter(m=>m.daysAgo<30), negative=mentions.filter(m=>m.tone==='negative').length;
  $('aiSummaryCompany').textContent=company.company;
  $('aiMentionsTotal').textContent=mentions.length;
  $('aiNegativeTotal').textContent=negative;
  $('aiTrendTotal').textContent=company.trends.length;
  $('aiPublishedTotal').textContent='Нет данных';
  const plus=mentions.filter(m=>m.tone==='positive').length;
  $('aiMentionsTone').textContent=plus+' полож. · '+negative+' отриц.';
  $('aiTopTrend').textContent=company.trends[0]?.title||'Не определён';
  const bins=Array.from({length:15},()=>0);
  mentions.forEach(m=>{let i=Math.floor((29-m.daysAgo)/2);bins[Math.max(0,Math.min(14,i))]++;});
  const max=Math.max(1,...bins);let d='M0 80';
  bins.forEach((v,i)=>{d+=' H'+Math.round((i+1)*400/15)+' V'+Math.round(80-v/max*65);});
  const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg'),line=document.createElementNS(ns,'path');
  svg.setAttribute('viewBox','0 0 400 95');svg.setAttribute('preserveAspectRatio','none');
  line.setAttribute('d',d);line.setAttribute('fill','none');line.setAttribute('stroke','#2589a2');line.setAttribute('stroke-width','2.4');
  svg.append(line);$('aiOverviewChart').replaceChildren(svg);
}
function renderActions(){
 const neg=company.mentions.filter(m=>m.daysAgo<company.days&&m.tone==='negative').length;
 const topics=company.trends[0]?.title||'отраслевые новости';
 const list=[
 ['ЭКСПЕРТНЫЙ КОММЕНТАРИЙ','Предложить комментарий по теме «'+topics+'»','Подготовьте подтверждённую экспертную позицию для профильных СМИ.','План комментария','chat'],
 ['РЕПУТАЦИЯ','Проверить негативные сообщения',neg?'Условно отрицательных сообщений за период: '+neg+'. Сверьте первоисточники и подготовьте ответ.':'В демонстрационной выборке негатив отсутствует. Подготовьте сценарий реакции заранее.','Отработка негатива','chat'],
 ['ПРЕСС-РЕЛИЗ','Подготовить пресс-релиз','Если у организации есть подтверждённый новостной повод, подготовьте текст и выберите адресатов.','Перейти в редактор','release'],
 ['СОБСТВЕННЫЕ РЕСУРСЫ','Опубликовать экспертный материал','Используйте отраслевой контекст для блога, сайта или социальной сети компании.','План публикации','chat']
 ];
 const cards=$('assistantCards');cards.replaceChildren();
 list.forEach(([kind,title,description,label,mode],i)=>{
  const card=make('article',null,'ai-card'),top=make('div',null,'ai-card-top'),actions=make('div',null,'ai-card-actions'),b=make('button',label+' ↗','ai-card-primary');
  top.append(make('span',kind,'ai-card-kind'),make('span','0'+(i+1),'ai-card-index'));
  b.type='button';b.addEventListener('click',()=>{
   if(mode==='release'){document.querySelector('[data-tab="pressReleases"]').click();$('releaseTitle').focus();}
   else{const value=mode==='chat'&&i===1?'Как отработать негатив?':(i===0?'Предложи PR-план для экспертного комментария':'Предложи PR-план для публикации на ресурсах компании');
    $('aiChatInput').value=value;$('aiChatForm').requestSubmit();}
  });
  actions.append(b);card.append(top,make('h3',title),make('p',description),make('div','Основание: условные упоминания и демонстрационная отраслeвая повестка.','ai-card-source'),actions);cards.append(card);
 });
 $('aiContextLabel').textContent='Рекомендации по условной выборке · '+company.industryLabel;
}
function checkLogic(){
 const v=inputs.map(x=>$(x).value.trim()),notes=[];
 if(v[0].length<15)notes.push('Заголовок: укажите конкретное событие вместо общего заявления.');
 if(v[0].length>125)notes.push('Рассмотрите сокращение слишком длинного заголовка.');
 if(v[1].length<60)notes.push('Лид: укажите кто, что, где, когда и почему событие важно.');
 if(v[2].length<180)notes.push('Основной текст: дополните фактуру, условия и контекст.');
 if(/лучший|уникальн|революционн|беспрецедентн/iu.test(v[0]+' '+v[1]))notes.push('Удалите неподтверждённые оценочные эпитеты.');
 if(!v[4])notes.push('Добавьте справку о компании и контакт для уточнения информации.');
 if(!v[3])notes.push('Цитата отсутствует — это допустимо, но прямую речь нельзя придумывать.');
 notes.push('Орфография: проверьте подчёркивания браузера через контекстное меню.');
 notes.push('Смысл, достоверность фактов, цитаты, причинно-следственные связи и правовые требования нужно проверить вручную.');
 $('releaseFeedback').textContent=notes.join('\n');$('releaseFeedback').style.whiteSpace='pre-line';
}
$('releaseCheck').addEventListener('click',checkLogic);
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
   if(size>3*1024*1024)throw Error('Слишком большой текст в документе.');
   const start=local+30+v.getUint16(local+26,true)+v.getUint16(local+28,true);
   if(start+size>buf.byteLength)throw Error('Архив повреждён.');
   let bytes=new Uint8Array(buf,start,size);
   if(method===8){if(typeof DecompressionStream!=='function')throw Error('Нужен браузер с поддержкой распаковки DOCX.');
    bytes=new Uint8Array(await new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('deflate-raw'))).arrayBuffer());
   }else if(method!==0)throw Error('Тип сжатия DOCX не поддерживается.');
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
 try{const text=await docxText(file),lines=text.split('\n').filter(x=>x.trim());
  $('releaseTitle').value='[Уточните заголовок] '+lines[0].slice(0,180);
  $('releaseLead').value='[Заполните лид: кто, что, где, когда и почему это важно]';
  $('releaseBody').value='ТЕЗИСЫ ИЗ WORD — НЕ ГОТОВЫЙ РЕЛИЗ\n\n'+lines.map((x,i)=>(i+1)+'. '+x).join('\n')+'\n\n[Дополните проверенные факты и контекст]';
  $('releaseQuote').value='';$('releaseAbout').value='';
  $('releaseImportStatus').textContent='Тезисы извлечены из '+file.name+'. Это структурированный редактируемый каркас, а не генерация ИИ.';
  $('releaseStatus').textContent='Требуется редактура';checkLogic();
 }catch(e){$('releaseImportStatus').textContent='Ошибка чтения: '+e.message;}
 finally{event.target.value='';}
});
document.addEventListener('ms-business-data',e=>{
 const next=e.detail;if(!next?.company)return;
 const isNew=!company||next.company!==company.company||next.industry!==company.industry;
 company=next;snapshot();renderActions();
 if(isNew)selected=new Set(recipients().map(x=>x.id));
 renderOutlets();
});
loadContacts();
})();
