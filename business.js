/* МЕДИА.СТРАЖ PRO / Бизнес: интерактивный прототип без внешних данных и API. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
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
  const excerpts = [
    ['positive','Положительное','Компания представила проект и сообщила о результатах, которые планирует развивать.'],
    ['neutral','Нейтральное','Участники рынка обсудили новые решения; среди упомянутых организаций названа компания.'],
    ['negative','Отрицательное','В материале приведены вопросы к срокам обслуживания и комментарии участников рынка.'],
    ['neutral','Нейтральное','Издание опубликовало обзор текущих предложений отрасли и упомянуло производителя.'],
    ['positive','Положительное','Эксперты отметили перспективность подхода, который использует компания.'],
    ['neutral','Нейтральное','На отраслевом мероприятии обсуждались технологии и планы предприятий.']
  ];
  let activeIndustry='medtech';
  let activeCompany='';
  const $table=$('mentionsBody');
  function node(tag,text,klass) {
    const n=document.createElement(tag); if(text!==undefined)n.textContent=text;
    if(klass)n.className=klass;return n;
  }
  function renderMentions() {
    const days=Number($('period').value);
    // Fixed relative demo dates, strictly illustrative — no network/API calls.
    const records=excerpts.map((entry,i)=>({entry,i,daysAgo:[1,4,11,18,38,68][i]})).filter(x=>x.daysAgo<=days);
    $table.replaceChildren();
    for(const {entry,i,daysAgo} of records) {
      const tr=node('tr');
      const mention=node('td');
      mention.append(node('strong','Пример упоминания №'+(i+1)),
        node('p',entry[2].replace('Компания',activeCompany).replace('компания',activeCompany),'business-excerpt'));
      const source=node('td',sources[i%sources.length]);
      const sentiment=node('td');
      sentiment.append(node('span',entry[1],'business-sentiment '+entry[0]));
      const date=new Date(Date.now()-daysAgo*24*60*60*1000);
      const datetime=node('td',date.toLocaleString('ru-RU',{timeZone:'Europe/Moscow',day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'})+' МСК','business-datetime');
      tr.append(mention,source,sentiment,datetime); $table.append(tr);
    }
    $('mentionsCount').textContent='Показано '+records.length+' демонстрационных упоминаний за '+days+' дней. Тональность иллюстративная.';
  }
  function renderTrendsAndPR() {
    const data=samples[activeIndustry];
    const trends=$('trendsGrid'),pr=$('opportunitiesGrid');
    trends.replaceChildren();pr.replaceChildren();
    data.trends.forEach((trend,i)=>{
      const card=node('article',undefined,'business-trend');
      const top=node('div',undefined,'business-trend-top');
      top.append(node('span',String(i+1).padStart(2,'0')+' / ИНФОПОВОД','business-trend-num'),
        node('span','ДЕМО','business-trend-growth'));
      card.append(top,node('h3',trend.title),node('p',trend.detail));
      const foot=node('div','Пример: '+trend.count+' публикаций · рост '+trend.growth,'business-trend-stat');
      card.append(foot);trends.append(card);
    });
    data.opportunities.slice(0,3).forEach(idea=>{
      const card=node('article',undefined,'business-opportunity');
      card.append(node('small',idea.kind),node('h3',idea.title),node('p',idea.detail));
      const label=node('span','Идея для проверки PR-командой','business-prototype-label');
      card.append(label);pr.append(card);
    });
  }
  const form=$('profileForm');
  form.addEventListener('submit',event=>{
    event.preventDefault();
    activeCompany=$('companyName').value.trim();
    if(!activeCompany){$('companyName').focus();return;}
    activeIndustry=$('industry').value;
    $('companyDisplay').textContent=activeCompany;
    $('industryDisplay').textContent=$('industry').selectedOptions[0].textContent;
    renderMentions();renderTrendsAndPR();
    $('businessStart').classList.add('business-start--compact');
    $('businessResults').hidden=false;
    $('businessResults').scrollIntoView({behavior:'auto',block:'start'});
  });
  $('period').addEventListener('change',()=>{if(!$('businessResults').hidden)renderMentions();});
  document.querySelectorAll('.business-result-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.business-result-tab').forEach(other => other.classList.remove('business-result-tab--active'));
      tab.classList.add('business-result-tab--active');
    });
  });
  $('editProfile').addEventListener('click',()=>{
    $('businessResults').hidden=true;
    $('businessStart').classList.remove('business-start--compact');
    window.scrollTo({top:0,behavior:'auto'});
    $('companyName').focus();
  });
})();
