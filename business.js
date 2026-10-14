/* МЕДИА.СТРАЖ PRO / Бизнес: интерактивный прототип без внешних данных и API. */
(() => {
  'use strict';
  const samples = {
    medtech: {
      trends: [
        {title:'Импортозамещение в медтехнике', count:98, growth:'+164%', detail:'Редакции обсуждают отечественные компоненты, регистрацию и закупки медицинских изделий.'},
        {title:'Сервис медицинского оборудования', count:76, growth:'+112%', detail:'В центре внимания — доступность ремонта, запасных частей и сопровождения техники.'},
        {title:'ИИ и автоматизация диагностики', count:64, growth:'+87%', detail:'Развиваются дискуссии о внедрении технологий и практических ограничениях.'}
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
        {title:'Кадры для производства', count:61, growth:'+41%', detail:'СМИ обсуждают подготовку инженеров и специалистов технических профессий.'}
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
        {title:'Персонализация гостиничного сервиса', count:46, growth:'+35%', detail:'Обсуждаются цифровые инструменты и новые способы заботы о гостях.'}
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
  let activeTab='mentions';
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
    const days=periodDays();
    const records=mentions.filter(m=>m.daysAgo<=days);
    const counts={positive:0,negative:0,neutral:0};
    records.forEach(m=>counts[m.tone]++);
    $('totalMentions').textContent=say(records.length);
    $('positiveCount').textContent=say(counts.positive);
    $('negativeCount').textContent=say(counts.negative);
    $('neutralCount').textContent=say(counts.neutral);
    $('mentionsCount').textContent=records.length+' из '+records.length;
    const feed=$('mentionsBody');
    feed.replaceChildren();
    records.forEach((entry,i)=>{
      const article=node('article',null,'mention-item');
      article.setAttribute('role','listitem');
      const main=node('div',null,'mention-primary');
      const meta=node('div',null,'mention-source');
      meta.append(node('span',sources[mentions.indexOf(entry)%sources.length],'mention-source-name'));
      const date=new Date(Date.now()-entry.daysAgo*86400000);
      meta.append(node('time',dateFormat.format(date)+' МСК','mention-source-time'));
      const title=node('h3',entry.title,'mention-title');
      const body=entry.text.replace('Компания',activeCompany).replace('компания',activeCompany);
      main.append(meta,title,node('p',body,'mention-excerpt'));
      const aside=node('div',null,'mention-aside');
      aside.append(node('span',entry.label,'business-sentiment '+entry.tone));
      article.append(main,aside);
      feed.append(article);
    });
    if(!records.length)feed.append(node('p','В демонстрационной подборке нет упоминаний за выбранный период.','business-empty'));
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
      fill.style.width=Math.max(6,Math.round(figures.current/maximum*100))+'%';
      bar.append(fill);content.append(bar);card.append(content);
      const metric=node('div',null,'business-trend-metric');
      metric.append(node('strong','+'+rate+'%','business-trend-growth'),
        node('span',say(figures.current)+' публикаций','business-trend-stat'),
        node('span','было '+say(figures.previous),'business-trend-compare'));
      card.append(metric);
      grid.append(card);
    });
  }

  function renderPR(){
    const data=samples[activeIndustry],pr=$('opportunitiesGrid');
    const days=periodDays();
    pr.replaceChildren();
    data.opportunities.slice(0,3).forEach((idea,i)=>{
      const signal=data.trends[i],figures=trendNumbers(signal,days);
      const rate=growthPercent(figures);
      const card=node('article',null,'business-opportunity');
      const top=node('div',null,'opportunity-top');
      top.append(node('span',idea.kind,'opportunity-kind'),
        node('span',String(i+1).padStart(2,'0')+' / 03','opportunity-index'));
      card.append(top,node('h3',idea.title),node('p',idea.detail));
      const evidence=node('div',null,'opportunity-evidence');
      evidence.append(node('span','ПОВОД','opportunity-evidence-label'),
        node('span',signal.title+' · +'+rate+'% за '+days+' дн. (демо)','opportunity-evidence-text'));
      card.append(evidence);
      const details=node('details',null,'opportunity-action-plan');
      const summary=node('summary','Посмотреть план действий');
      details.append(summary);
      const steps=node('ol');
      prActions[activeIndustry][i].forEach(step=>steps.append(node('li',step)));
      details.append(steps);
      card.append(details);
      pr.append(card);
    });
  }

  const tabs=[...document.querySelectorAll('.business-result-tab')];
  const panels=['mentions','trends','opportunities'];
  function activateTab(name,focus=false){
    if(!panels.includes(name))return;
    activeTab=name;
    tabs.forEach(tab=>{
      const on=tab.dataset.tab===name;
      tab.classList.toggle('business-result-tab--active',on);
      tab.setAttribute('aria-selected',String(on));
      tab.tabIndex=on?0:-1;
      if(on&&focus)tab.focus();
    });
    panels.forEach(panel=>$(panel).hidden=(panel!==name));
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
      if(e.key==='ArrowRight')next=(index+1)%tabs.length;
      if(e.key==='ArrowLeft')next=(index-1+tabs.length)%tabs.length;
      if(e.key==='Home')next=0;
      if(e.key==='End')next=tabs.length-1;
      if(next!==-1){e.preventDefault();activateTab(tabs[next].dataset.tab,true);}
    });
  });
  const form=$('profileForm');
  form.addEventListener('submit',event=>{
    event.preventDefault();
    activeCompany=$('companyName').value.trim();
    if(!activeCompany){$('companyName').focus();return;}
    activeIndustry=$('industry').value;
    $('companyDisplay').textContent=activeCompany;
    $('industryDisplay').textContent=$('industry').selectedOptions[0].textContent;
    renderMentions();renderTrends();renderPR();
    $('businessStart').classList.add('business-start--compact');
    $('businessResults').hidden=false;
    activateTab('mentions');
    $('businessResults').scrollIntoView({behavior:'auto',block:'start'});
  });
  $('period').addEventListener('change',()=>{
    if($('businessResults').hidden)return;
    renderMentions();renderTrends();renderPR();
    if(activeTab==='opportunities')activateTab('opportunities');
  });
  $('editProfile').addEventListener('click',()=>{
    $('businessResults').hidden=true;
    $('businessStart').classList.remove('business-start--compact');
    window.scrollTo({top:0,behavior:'auto'});
    $('companyName').focus();
  });
})();
