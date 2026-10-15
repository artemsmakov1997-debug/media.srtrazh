/* МЕДИА.СТРАЖ PRO: аналитика собранных публикаций, профиль остаётся в браузере. */
(() => {
  'use strict';
  let corpus=null,analytics=null;
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
  function refreshAnalytics(){
    analytics=MediaStrazhBusiness.analyze(corpus,activeCompany,activeIndustry,periodDays());
    $('businessCoverage').textContent='Обновлено: '+dateFormat.format(new Date(corpus.generated_at))+' МСК. В выборке '+corpus.coverage.published+' материалов; '+corpus.coverage.undated_excluded+' без даты исключены.'+(corpus.coverage.limited?' Подборка ограничена.':'');
  }
  function renderMentions(){
    const days=periodDays(),query=$('mentionsSearch').value.trim().toLocaleLowerCase('ru-RU');
    const tone=$('mentionsTone').value,all=analytics.selected;
    $('totalMentions').textContent=say(all.length);
    for(const id of ['positiveCount','negativeCount','neutralCount'])$(id).textContent='—';
    const records=all.filter(m=>(tone==='all'||m.tone===tone)&&(!query||(m.title+' '+m.text+' '+m.source).toLocaleLowerCase('ru-RU').includes(query)));
    $('mentionsCount').textContent=records.length+' из '+all.length;
    const feed=$('mentionsBody');feed.replaceChildren();
    for(const entry of records){
      const article=node('article',null,'mention-item');article.setAttribute('role','listitem');
      const main=node('div',null,'mention-primary'),meta=node('div',null,'mention-source');
      const date=node('time',dateFormat.format(new Date(entry.published_at))+' МСК','mention-source-time');
      date.dateTime=entry.published_at;
      meta.append(node('span',entry.source,'mention-source-name'),date);
      main.append(meta,node('h3',entry.title||entry.text,'mention-title'));
      const aside=node('div',null,'mention-aside');aside.append(node('span',entry.label,'business-sentiment unknown'));
      const action=node('div',null,'mention-source-action'),link=node('a','Показать источник ↗','mention-source-button');
      link.href=entry.url;link.target='_blank';link.rel='noopener noreferrer';action.append(link);
      article.append(main,aside,action);feed.append(article);
    }
    if(!records.length)feed.append(node('p',tone==='all'?'В собранных публикациях за период совпадений названия не найдено. Это не означает отсутствия упоминаний во всех СМИ.':'Оценка тональности пока не подключена. Выберите все публикации.','business-empty'));
    const bins=Array.from({length:Math.min(days,15)},()=>0);
    all.forEach(m=>{const age=(analytics.now-Date.parse(m.published_at))/86400000,index=Math.floor((days-age)/days*bins.length);if(index>=0&&index<bins.length)bins[index]++;});
    const max=Math.max(1,...bins),base=122;
    let d='M 0 '+base;
    bins.forEach((n,i)=>{d+=' H '+(i+1)*420/bins.length+' V '+(base-n/max*100);});
    const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');
    svg.setAttribute('viewBox','0 0 420 136');svg.setAttribute('preserveAspectRatio','none');svg.setAttribute('aria-hidden','true');
    const fill=document.createElementNS(ns,'path');fill.setAttribute('d',d+' V '+base+' H 0 Z');fill.setAttribute('fill','rgba(35,184,208,.09)');svg.append(fill);
    const line=document.createElementNS(ns,'path');line.setAttribute('d',d);line.setAttribute('fill','none');line.setAttribute('stroke','#268ca2');line.setAttribute('stroke-width','2.5');line.setAttribute('stroke-linejoin','round');svg.append(line);
    $('mentionsStairChart').replaceChildren(svg);
    $('mentionsStairChart').setAttribute('aria-label','Совпадения названия в '+all.length+' собранных публикациях за '+days+' дней');
    $('chartFrom').textContent=dateFormat.format(new Date(analytics.now-days*86400000)).split(',')[0];
    $('chartTo').textContent=dateFormat.format(new Date(analytics.now)).split(',')[0];
  }
  function renderTrends(){
    $('trendPeriodLabel').textContent=periodDays()+' дней';
    const grid=$('trendsGrid'),data=analytics.trends;grid.replaceChildren();
    const maximum=Math.max(...data.map(t=>t.count),1);
    data.forEach((trend,i)=>{
      const card=node('article',null,'business-trend');
      card.style.setProperty('--trend-order',String(i));
      card.style.setProperty('--trend-enter-delay',i*90+'ms');
      card.style.setProperty('--trend-bar-delay',(160+i*105)+'ms');
      card.style.setProperty('--trend-metric-delay',(100+i*95)+'ms');
      card.append(node('div',String(i+1).padStart(2,'0'),'business-trend-num'));
      const content=node('div',null,'business-trend-content');content.append(node('h3',trend.title),node('p',trend.detail));
      const bar=node('div',null,'business-trend-bar'),fill=node('div',null,'business-trend-bar-fill');
      fill.style.width=Math.round(trend.count/maximum*100)+'%';bar.append(fill);content.append(bar);
      for(const evidence of trend.evidence.slice(0,2)){
        const link=node('a',evidence.source+' ↗','business-trend-compare');
        link.href=evidence.url;link.target='_blank';link.rel='noopener noreferrer';content.append(link);
      }
      const action=node('button','Использовать возможность ↗','business-trend-action');action.type='button';
      action.setAttribute('aria-label','Использовать возможность: '+trend.title);
      action.addEventListener('click',()=>document.dispatchEvent(new CustomEvent('ms-trend-action',{detail:{trend,destination:i%2===0?'release':'assistant'}})));
      content.append(action);card.append(content);
      const metric=node('div',null,'business-trend-metric');
      metric.append(node('strong',trend.growth,'business-trend-growth'),node('span',say(trend.count)+' публикаций','business-trend-stat'),
        node('span',trend.rate===null?'Нет базы для расчёта роста':'В прошлой выборке: '+say(trend.previous),'business-trend-compare'));
      card.append(metric);grid.append(card);
    });
    if(!data.length)grid.append(node('p','В собранной выборке за период нет материалов по настроенным отраслевым темам.','business-empty'));
  }
  function renderPR(){
    document.dispatchEvent(new CustomEvent('ms-business-data',{detail:{...analytics,industryLabel:$('industry').selectedOptions[0].textContent}}));
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
  const panels=['opportunities','mentions','trends','pressReleases','report'];
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
    'Загружаем собранные публикации',
    'Формируем аналитическую записку'
  ];
  let isPreparing=false;

  function cancelPreparation(){
    isPreparing=false;
    openButton.disabled=false;
    $('companyName').disabled=false;$('industry').disabled=false;
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
    refreshAnalytics();renderMentions();renderTrends();renderPR();
    start.classList.add('business-start--compact');
    $('businessResults').hidden=false;
    $('businessResults').classList.remove('is-opening');
    void $('businessResults').offsetWidth;
    $('businessResults').classList.add('is-opening');
    document.body.classList.add('business-open');
    activateTab('opportunities');
    $('businessResults').scrollIntoView({behavior:'auto',block:'start'});
  }

  let generation=0,controller=null;
  form.addEventListener('submit',async event=>{
    event.preventDefault();if(isPreparing)return;
    activeCompany=$('companyName').value.trim();
    if(!activeCompany){$('companyName').focus();return;}
    activeIndustry=$('industry').value;
    $('businessMobileCompany').textContent=activeCompany;$('railCompany').textContent=activeCompany;
    $('railIndustry').textContent=$('industry').selectedOptions[0].textContent;
    const request=++generation;openButton.disabled=true;isPreparing=true;
    $('companyName').disabled=true;$('industry').disabled=true;
    setLoadingStep(0);loading.hidden=false;start.setAttribute('aria-busy','true');start.classList.add('business-start--loading');
    controller=new AbortController();const currentController=controller;
    const deadline=setTimeout(()=>currentController.abort(),15000);
    try{
      setLoadingStep(1);
      const response=await fetch('data/business.json',{cache:'no-store',signal:currentController.signal});
      if(!response.ok)throw Error('HTTP '+response.status);
      const value=MediaStrazhBusiness.validate(await response.json());
      if(request!==generation)return;
      corpus=value;
      // Validate the entered name before displaying the cabinet.
      MediaStrazhBusiness.analyze(corpus,activeCompany,activeIndustry,periodDays());
      setLoadingStep(2);
      const note=document.querySelector('.business-start-note');
      note.textContent='Данные: '+dateFormat.format(new Date(corpus.generated_at))+' МСК. '+corpus.coverage.published+
        ' собранных публикаций. Совпадение названия требует проверки; одноимённые организации возможны.'+
        (corpus.coverage.limited?' Подборка ограничена.':'');
      showCabinet();
    }catch(error){
      if(request!==generation)return;
      cancelPreparation();
      document.querySelector('.business-start-note').textContent='Не удалось открыть кабинет: '+
        (error.name==='AbortError'?'превышено время ожидания':error.message)+'. Проверьте параметры и повторите загрузку. Демо-данные не подставляются.';
    }finally{clearTimeout(deadline);if(request===generation)controller=null;}
  });
  $('mentionsSearch').addEventListener('input',renderMentions);
  $('mentionsTone').addEventListener('change',renderMentions);
  $('mentionsPeriod').addEventListener('change',()=>{ $('period').value=$('mentionsPeriod').value;refreshAnalytics();renderMentions();renderTrends();renderPR(); });
  $('period').addEventListener('change',()=>{ $('mentionsPeriod').value=$('period').value;
    if($('businessResults').hidden)return;
    refreshAnalytics();renderMentions();renderTrends();renderPR();
    if(activeTab==='opportunities')activateTab('opportunities');
  });
  document.querySelectorAll('[data-open]').forEach(btn=>{
    btn.addEventListener('click',()=>activateTab(btn.dataset.open));
  });
  $('editProfile').addEventListener('click',()=>{
    generation++;if(controller)controller.abort();controller=null;
    cancelPreparation();
    $('businessResults').hidden=true;
    $('businessResults').classList.remove('is-opening');
    start.classList.remove('business-start--compact');
    document.body.classList.remove('business-open');
    setMenu(false);
    document.dispatchEvent(new Event('ms-business-exit'));
    window.scrollTo({top:0,behavior:'auto'});
    $('companyName').focus();
  });
})();
