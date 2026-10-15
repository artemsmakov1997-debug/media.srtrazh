/* МЕДИА.СТРАЖ PRO / Бизнес: интерактивный прототип без внешних данных и API. */
(() => {
  'use strict';
  const samples = {
    medtech: {
      trends: [
        {title:'Импортозамещение в медтехнике', count:98, growth:'+164%', detail:'Редакции обсуждают отечественные компоненты, регистрацию и закупки медицинских изделий.'},
        {title:'Сервис медицинского оборудования', count:76, growth:'+112%', detail:'В центре внимания — доступность ремонта, запасных частей и сопровождения техники.'},
        {title:'ИИ и автоматизация диагностики', count:64, growth:'+87%', detail:'Развиваются дискуссии о внедрении технологий и практических ограничениях.'},
        {title:'Кибербезопасность медицинского оборудования', count:47, growth:'+61%', detail:'Обсуждаются защита подключённых медицинских устройств, обновления и ответственность за данные.'},
        {title:'Дистанционная техническая поддержка медтехники', count:36, growth:'+43%', detail:'В фокусе — удалённая диагностика неисправностей и сопровождение оборудования.'}
      ],
      opportunities: [
        {kind:'КОММЕНТАРИЙ ЭКСПЕРТА', title:'Прокомментировать изменения рынка медтехники', detail:'Расскажите, какие изменения видит ваша компания на практике. Подойдут экспертная колонка или комментарий, если есть подтверждённая фактура.'},
        {kind:'КЕЙС / КОЛОНКА', title:'Показать опыт эксплуатации и сервиса', detail:'Подготовьте конкретный кейс: задача, решение, результат и подтверждающие показатели, которые можно опубликовать.'},
        {kind:'ИССЛЕДОВАНИЕ', title:'Собрать собственные данные об отрасли', detail:'Проведите небольшой опрос специалистов и предложите редакциям результаты с прозрачной методикой.'},
        {kind:'ПРАКТИЧЕСКИЙ РАЗБОР', title:'Объяснить внедрение новых технологий', detail:'Предложите материал о применении новых решений с понятными ограничениями и проверяемыми примерами.'}
      ]
    },
    industry: {
      trends: [
        {title:'Локализация производств', count:132, growth:'+73%', detail:'На первый план выходят цепочки поставок и российские производственные мощности.'},
        {title:'Промышленная автоматизация', count:83, growth:'+56%', detail:'Интерес вызывают роботизация, датчики и повышение эффективности процессов.'},
        {title:'Кадры для производства', count:61, growth:'+41%', detail:'СМИ обсуждают подготовку инженеров и специалистов технических профессий.'},
        {title:'Энергоэффективность предприятий', count:48, growth:'+37%', detail:'В повестке — снижение потерь ресурсов и практические результаты модернизации.'},
        {title:'Ремонт и продление срока службы оборудования', count:39, growth:'+29%', detail:'Обсуждаются сервисные программы, капитальный ремонт и управление ресурсом оборудования.'}
      ],
      opportunities: [
        {kind:'КОММЕНТАРИЙ ЭКСПЕРТА', title:'Оценить изменения производственных цепочек', detail:'Подготовьте экспертный комментарий о реальных сложностях, возможностях и подтверждаемых результатах.'},
        {kind:'КЕЙС', title:'Показать результат внедрения технологии', detail:'Подойдёт кейс с исходной задачей, описанием внедрения и измеримыми итогами.'},
        {kind:'ИССЛЕДОВАНИЕ', title:'Собрать данные о спросе на специалистов', detail:'Уместны результаты собственного опроса или аналитики вакансий с описанной методикой.'},
        {kind:'ОБЗОР', title:'Объяснить экономику сервисного обслуживания', detail:'Расскажите об изменениях затрат и сроков обслуживания без неподтверждённых обобщений.'}
      ]
    },
    hospitality: {
      trends: [
        {title:'Короткие городские поездки', count:91, growth:'+68%', detail:'СМИ обсуждают поездки на выходные, культурные события и новые сценарии отдыха.'},
        {title:'Путешествия с питомцами', count:54, growth:'+49%', detail:'Растёт интерес к pet-friendly сервисам и организации поездок с животными.'},
        {title:'Персонализация гостиничного сервиса', count:46, growth:'+35%', detail:'Обсуждаются цифровые инструменты и новые способы заботы о гостях.'},
        {title:'Гастрономические впечатления в путешествиях', count:38, growth:'+32%', detail:'Гостиницы и рестораны объединяют локальную кухню, события и отдых в городе.'},
        {title:'Деловые поездки и события в городах', count:31, growth:'+24%', detail:'СМИ обсуждают конгрессы, командировки и дополнительные сервисы для деловых гостей.'}
      ],
      opportunities: [
        {kind:'ЭКСПЕРТНЫЙ КОММЕНТАРИЙ', title:'Рассказать о новых привычках путешественников', detail:'Поделитесь наблюдениями за предпочтениями гостей, подкрепив их собственными данными.'},
        {kind:'ИСТОРИЯ / КЕЙС', title:'Показать pet-friendly опыт', detail:'Опишите конкретные услуги и опыт гостей, не приписывая им несуществующих отзывов.'},
        {kind:'ИССЛЕДОВАНИЕ', title:'Проанализировать спрос на короткие поездки', detail:'Подготовьте статистику бронирований с корректным периодом и методикой подсчёта.'},
        {kind:'КОЛОНКА', title:'Объяснить ценность персонального сервиса', detail:'Предложите практическую колонку об обслуживании гостей и операционных решениях.'}
      ]
    }
  };

  const sources = ['Деловой вестник (демо)', 'Отраслевой обзор (демо)', 'Городские новости (демо)', 'Экспертный журнал (демо)', 'Бизнес-лента (демо)'];
  // All of these are artificial examples. The numbers below are *only*
  // exact counts within the chosen demo sample, not live monitoring results.
  const mentions = [
    {tone:'positive',label:'Положительное',daysAgo:1,title:'Компания представила отраслевое решение',text:'Компания представила проект и сообщила о результатах, которые планирует развивать.'},
    {tone:'neutral',label:'Нейтральное',daysAgo:4,title:'Участники рынка обсудили новые технологии',text:'Участники рынка обсудили новые решения; среди упомянутых организаций названа компания.'},
    {tone:'negative',label:'Отрицательное',daysAgo:11,title:'Вопросы к срокам обслуживания',text:'В материале приведены вопросы к срокам обслуживания и комментарии участников рынка.'},
    {tone:'neutral',label:'Нейтральное',daysAgo:18,title:'Обзор предложений на отраслевом рынке',text:'Издание опубликовало обзор текущих предложений отрасли и упомянуло производителя.'},
    {tone:'positive',label:'Положительное',daysAgo:38,title:'Эксперты оценили перспективы нового подхода',text:'Эксперты отметили перспективность подхода, который использует компания.'},
    {tone:'neutral',label:'Нейтральное',daysAgo:68,title:'Итоги отраслевого мероприятия',text:'На отраслевом мероприятии обсуждались технологии и планы предприятий.'}
  ];
  const prActions = {
    medtech: [
      ['Подготовить короткую экспертную позицию по теме изменений в отрасли.',
       'Проверить фактуру: нормативные документы, практические последствия, сроки.',
       'Предложить комментарий отраслевым редакциям с конкретными примерами.'],
      ['Выбрать завершённый сервисный кейс с подтверждаемыми результатами.',
       'Согласовать возможность раскрытия деталей проекта и показателей.',
       'Подготовить структуру колонки: проблема, решение, проверяемый эффект.'],
      ['Определить узкий вопрос для опроса сервисных и клинических специалистов.',
       'Собрать данные и описать методику получения результатов.',
       'Предложить журналистам цифры и практические выводы исследования.']
    ],
    industry: [
      ['Сформулировать позицию предприятия о поставках и локализации.',
       'Подтвердить тезисы собственными примерами и данными.',
       'Подготовить адресный питч в профильные редакции.'],
      ['Выбрать внедрение с измеримыми производственными результатами.',
       'Согласовать раскрытие фактуры, цифр и цитат специалистов.',
       'Собрать кейс для отраслевой публикации.'],
      ['Выделить несколько ключевых кадровых вопросов.',
       'Провести собственное исследование или опрос с описанной методикой.',
       'Предложить редакциям результаты и экспертный комментарий.']
    ],
    hospitality: [
      ['Собрать наблюдения о поведении гостей и динамике спроса.',
       'Выбрать 2–3 подтверждаемые тенденции в поездках.',
       'Предложить комментарий о новых сценариях отдыха.'],
      ['Найти законченный пример работы с гостями и питомцами.',
       'Согласовать детали, фотографии и подтверждаемые результаты.',
       'Подготовить историю для туристических и городских СМИ.'],
      ['Определить сопоставимые периоды коротких городских поездок.',
       'Проанализировать обезличенные данные бронирований.',
       'Подготовить небольшое исследование с прозрачной методикой.']
    ]
  };
  const $ = id => document.getElementById(id);
  const node = (tag,text,cls) => {
    const n=document.createElement(tag);
    if(text!==undefined && text!==null)n.textContent=text;
    if(cls)n.className=cls;
    return n;
  };
  const say = n => Number(n).toLocaleString('ru-RU');
  const dateFormat = new Intl.DateTimeFormat('ru-RU',{timeZone:'Europe/Moscow',day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'});
  let activeIndustry='medtech';
  let activeCompany='';
  let activeTab='opportunities';
  const periodDays=()=>Number($('period').value);
  // Synthetic demo trend counts, with a previous period to calculate growth
  // mathematically for each filter. No real article data or live AI is used.
  function trendNumbers(trend,days){
    const rise=parseInt(trend.growth,10)/100;
    if(days===7){
      const current=Math.max(6,Math.round(trend.count*.3));
      return {current,previous:Math.max(1,Math.round(current/(1+rise*.55)))};
    }
    if(days===90){
      const current=Math.round(trend.count*2.65);
      return {current,previous:Math.max(1,Math.round(current/(1+rise*.43)))};
    }
    return {current:trend.count,previous:Math.max(1,Math.round(trend.count/(1+rise)))};
  }
  const growthPercent = totals => Math.round((totals.current-totals.previous)/totals.previous*100);

  function renderMentions(){
    const days=Number($('mentionsPeriod').value);
    const query=$('mentionsSearch').value.trim().toLocaleLowerCase('ru-RU');
    const tone=$('mentionsTone').value;
    const all=mentions.filter(m=>m.daysAgo<=days);
    const counts={positive:0,negative:0,neutral:0};
    all.forEach(m=>counts[m.tone]++);
    $('totalMentions').textContent=say(all.length);
    $('positiveCount').textContent=say(counts.positive);
    $('negativeCount').textContent=say(counts.negative);
    $('neutralCount').textContent=say(counts.neutral);
    const records=all.filter(m=>(tone==='all'||m.tone===tone)&&(!query||(m.title+' '+m.text+' '+sources[mentions.indexOf(m)%sources.length]).toLocaleLowerCase('ru-RU').includes(query)));
    $('mentionsCount').textContent=records.length+' из '+all.length;
    const feed=$('mentionsBody');
    feed.replaceChildren();
    records.forEach(entry=>{
      const article=node('article',null,'mention-item');
      article.setAttribute('role','listitem');
      const main=node('div',null,'mention-primary');
      const meta=node('div',null,'mention-source');
      meta.append(node('span',sources[mentions.indexOf(entry)%sources.length],'mention-source-name'));
      const date=new Date(Date.now()-entry.daysAgo*86400000);
      meta.append(node('time',dateFormat.format(date)+' МСК','mention-source-time'));
      main.append(meta,node('h3',entry.title,'mention-title'));
      const aside=node('div',null,'mention-aside');
      aside.append(node('span',entry.label,'business-sentiment '+entry.tone));
      const action=node('div',null,'mention-source-action');
      if(entry.url && /^https:\/\//.test(entry.url)){
        const link=node('a','Показать источник ↗','mention-source-button');
        link.href=entry.url;link.target='_blank';link.rel='noopener noreferrer';
        action.append(link);
      }else{
        const button=node('button','Показать источник','mention-source-button');
        button.type='button';button.disabled=true;button.title='Демонстрационная запись: ссылки на реальную публикацию нет';
        action.append(button);
      }
      article.append(main,aside,action);
      feed.append(article);
    });
    if(!records.length)feed.append(node('p','По заданным параметрам публикаций не найдено.','business-empty'));
    const bins=Array.from({length:Math.min(days,15)},()=>0);
    all.forEach(m=>{const index=Math.min(bins.length-1,Math.floor((days-1-m.daysAgo)/days*bins.length));if(index>=0)bins[index]++;});
    const max=Math.max(1,...bins),width=420,height=136,base=height-14;
    let d='M 0 '+base;
    bins.forEach((n,i)=>{const x=(i+1)*width/bins.length,y=base-(n/max)*(height-36);d+=' H '+x+' V '+y;});
    const area=d+' V '+base+' H 0 Z';
    const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');
    svg.setAttribute('viewBox','0 0 420 136');svg.setAttribute('preserveAspectRatio','none');svg.setAttribute('aria-hidden','true');
    const baseline=document.createElementNS(ns,'line');baseline.setAttribute('x1','0');baseline.setAttribute('x2','420');baseline.setAttribute('y1',String(base));baseline.setAttribute('y2',String(base));baseline.setAttribute('stroke','#ccd8da');svg.append(baseline);
    const fill=document.createElementNS(ns,'path');fill.setAttribute('d',area);fill.setAttribute('fill','rgba(35,184,208,.09)');svg.append(fill);
    const line=document.createElementNS(ns,'path');line.setAttribute('d',d);line.setAttribute('fill','none');line.setAttribute('stroke','#268ca2');line.setAttribute('stroke-width','2.5');line.setAttribute('stroke-linejoin','round');svg.append(line);
    $('mentionsStairChart').replaceChildren(svg);
    $('mentionsStairChart').setAttribute('aria-label','Динамика '+all.length+' демонстрационных упоминаний за '+days+' дней');
    $('chartFrom').textContent=days+' дней назад';
    $('chartTo').textContent='Сегодня';
  }

  function renderTrends(){
    const days=periodDays();
    $('trendPeriodLabel').textContent=days===7?'7 дней':days===30?'30 дней':'90 дней';
    const grid=$('trendsGrid'),data=samples[activeIndustry].trends;
    grid.replaceChildren();
    const totals=data.map(t=>trendNumbers(t,days));
    const maximum=Math.max(...totals.map(t=>t.current),1);
    data.forEach((trend,i)=>{
      const figures=totals[i],rate=growthPercent(figures);
      const card=node('article',null,'business-trend');
      card.append(node('div',String(i+1).padStart(2,'0'),'business-trend-num'));
      const content=node('div',null,'business-trend-content');
      content.append(node('h3',trend.title),node('p',trend.detail));
      const bar=node('div',null,'business-trend-bar'),fill=node('div',null,'business-trend-bar-fill');
      card.style.setProperty('--trend-order',String(i));
      card.style.setProperty('--trend-enter-delay',i*90+'ms');
      card.style.setProperty('--trend-bar-delay',(160+i*105)+'ms');
      card.style.setProperty('--trend-metric-delay',(100+i*95)+'ms');
      fill.style.width=Math.max(6,Math.round(figures.current/maximum*100))+'%';
      bar.append(fill);content.append(bar);
      const action=node('button','Использовать возможность ↗','business-trend-action');
      action.type='button';
      action.setAttribute('aria-label','Использовать возможность: '+trend.title);
      action.addEventListener('click',()=>{
        document.dispatchEvent(new CustomEvent('ms-trend-action',{detail:{
          trend:{title:trend.title,detail:trend.detail},destination:i%2===0?'release':'assistant'
        }}));
      });
      content.append(action);card.append(content);
      const metric=node('div',null,'business-trend-metric');
      metric.append(node('strong','+'+rate+'%','business-trend-growth'),
        node('span',say(figures.current)+' публикаций','business-trend-stat'),
        node('span','было '+say(figures.previous),'business-trend-compare'));
      card.append(metric);
      grid.append(card);
    });
  }

  function renderPR(){
    // Send the same demo evidence shown in Mentions and Trends to the new
    // editorial workspaces. No server-side model is connected at this stage.
    document.dispatchEvent(new CustomEvent('ms-business-data',{detail:{
      company:activeCompany,
      industry:activeIndustry,
      industryLabel:$('industry').selectedOptions[0].textContent,
      days:periodDays(),
      mentions, sources,
      trends:samples[activeIndustry].trends,
      opportunities:samples[activeIndustry].opportunities,
      actions:prActions[activeIndustry]
    }}));
  }

  const menuToggle=$('businessMenuToggle'),menuBackdrop=$('businessMenuBackdrop'),rail=$('businessRail');
  function setMenu(open){
    const on=Boolean(open);
    document.body.classList.toggle('business-menu-open',on);
    menuToggle.setAttribute('aria-expanded',String(on));
    menuToggle.setAttribute('aria-label',on?'Закрыть меню':'Открыть меню');
    menuBackdrop.hidden=!on;
    if(on)rail.querySelector('.business-result-tab--active')?.focus();
    else if(document.activeElement && rail.contains(document.activeElement))menuToggle.focus();
  }
  menuToggle.addEventListener('click',()=>setMenu(!document.body.classList.contains('business-menu-open')));
  menuBackdrop.addEventListener('click',()=>setMenu(false));
  document.addEventListener('keydown',e=>{if(e.key==='Escape' && document.body.classList.contains('business-menu-open'))setMenu(false);});
  window.addEventListener('resize',()=>{if(window.innerWidth>720 && document.body.classList.contains('business-menu-open'))setMenu(false);});
  const tabs=[...document.querySelectorAll('.business-result-tab')];
  const panels=['opportunities','mentions','trends','pressReleases'];
  function activateTab(name,focus=false){
    if(!panels.includes(name))return;
    activeTab=name;
    $('businessResults').classList.toggle('is-mentions',name==='mentions');
    document.dispatchEvent(new CustomEvent('ms-tab-open',{detail:{name}}));
    tabs.forEach(tab=>{
      const on=tab.dataset.tab===name;
      tab.classList.toggle('business-result-tab--active',on);
      tab.setAttribute('aria-selected',String(on));
      tab.tabIndex=on?0:-1;
      if(on&&focus)tab.focus();
    });
    panels.forEach(panel=>$(panel).hidden=(panel!==name));
    setMenu(false);
    const label= tabs.find(tab=>tab.dataset.tab===name);
    $('paperLocation').textContent=label?label.textContent.trim().toUpperCase():'ОБЗОР';
    const pr=$('opportunities');
    if(name==='opportunities'){
      pr.classList.remove('is-revealing');
      // Reset purely illustrative motion on every intentional tab opening.
      void pr.offsetWidth;
      pr.classList.add('is-revealing');
    }else{pr.classList.remove('is-revealing');}
  }
  tabs.forEach((tab,index)=>{
    tab.addEventListener('click',()=>activateTab(tab.dataset.tab));
    tab.addEventListener('keydown',e=>{
      let next=-1;
      if(e.key==='ArrowRight'||e.key==='ArrowDown')next=(index+1)%tabs.length;
      if(e.key==='ArrowLeft'||e.key==='ArrowUp')next=(index-1+tabs.length)%tabs.length;
      if(e.key==='Home')next=0;
      if(e.key==='End')next=tabs.length-1;
      if(next!==-1){e.preventDefault();activateTab(tabs[next].dataset.tab,true);}
    });
  });
  const form=$('profileForm');
  const start=$('businessStart');
  const loading=$('businessLoading');
  const openButton=form.querySelector('button[type="submit"]');
  const loadingStages=[
    'Проверяем параметры компании',
    'Подготавливаем демонстрационную выборку публикаций',
    'Формируем аналитическую записку'
  ];
  let loadingTimeouts=[];
  let isPreparing=false;

  function cancelPreparation(){
    loadingTimeouts.forEach(clearTimeout);
    loadingTimeouts=[];
    isPreparing=false;
    openButton.disabled=false;
    start.classList.remove('business-start--loading');
    start.removeAttribute('aria-busy');
    loading.hidden=true;
  }

  function setLoadingStep(index){
    $('loadingStage').textContent=loadingStages[index];
    document.querySelectorAll('[data-load-step]').forEach(el=>{
      const step=Number(el.dataset.loadStep);
      el.classList.toggle('is-current',step===index);
      el.classList.toggle('is-done',step<index);
    });
  }

  function showCabinet(){
    if(!isPreparing)return;
    cancelPreparation();
    renderMentions();renderTrends();renderPR();
    start.classList.add('business-start--compact');
    $('businessResults').hidden=false;
    $('businessResults').classList.remove('is-opening');
    void $('businessResults').offsetWidth;
    $('businessResults').classList.add('is-opening');
    document.body.classList.add('business-open');
    activateTab('opportunities');
    $('businessResults').scrollIntoView({behavior:'auto',block:'start'});
  }

  form.addEventListener('submit',event=>{
    event.preventDefault();
    if(isPreparing)return;
    activeCompany=$('companyName').value.trim();
    if(!activeCompany){$('companyName').focus();return;}
    activeIndustry=$('industry').value;
    $('businessMobileCompany').textContent=activeCompany;
    $('railCompany').textContent=activeCompany;
    $('railIndustry').textContent=$('industry').selectedOptions[0].textContent;
    openButton.disabled=true;
    isPreparing=true;
    setLoadingStep(0);
    loading.hidden=false;
    start.setAttribute('aria-busy','true');
    start.classList.add('business-start--loading');

    // This is a visual transition between static demo data and its local
    // rendering. No news retrieval or AI work happens during these stages.
    const reducedMotion=window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if(reducedMotion){
      loadingTimeouts.push(setTimeout(showCabinet,220));
      return;
    }
    loadingTimeouts.push(
      setTimeout(()=>setLoadingStep(1),820),
      setTimeout(()=>setLoadingStep(2),1640),
      setTimeout(showCabinet,2480)
    );
  });
  $('mentionsSearch').addEventListener('input',renderMentions);
  $('mentionsTone').addEventListener('change',renderMentions);
  $('mentionsPeriod').addEventListener('change',()=>{ $('period').value=$('mentionsPeriod').value;renderMentions();renderTrends();renderPR(); });
  $('period').addEventListener('change',()=>{ $('mentionsPeriod').value=$('period').value;
    if($('businessResults').hidden)return;
    renderMentions();renderTrends();renderPR();
    if(activeTab==='opportunities')activateTab('opportunities');
  });
  document.querySelectorAll('[data-open]').forEach(btn=>{
    btn.addEventListener('click',()=>activateTab(btn.dataset.open));
  });
  $('editProfile').addEventListener('click',()=>{
    cancelPreparation();
    $('businessResults').hidden=true;
    $('businessResults').classList.remove('is-opening');
    start.classList.remove('business-start--compact');
    document.body.classList.remove('business-open');
    setMenu(false);
    window.scrollTo({top:0,behavior:'auto'});
    $('companyName').focus();
  });
})();
