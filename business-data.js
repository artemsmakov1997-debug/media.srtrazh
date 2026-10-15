/* Pure calculations over a bounded public corpus. No profile is sent to a server. */
(() => {
  'use strict';
  const DAY=86400000, legal=new Set(['ооо','пао','ао','оао','зао','нко','ип','llc','inc','ltd']);
  function normalize(value){
    const words=String(value).normalize('NFKC').toLocaleLowerCase('ru-RU').replace(/ё/g,'е').replace(/ß/g,'ss').match(/[\p{L}\p{N}]+/gu)||[];
    while(legal.has(words[0]))words.shift();
    while(legal.has(words[words.length-1]))words.pop();
    return words.join(' ');
  }
  function forms(value){
    const result=new Set([value]),parts=value.split(' '),last=parts.pop();
    if(last?.length>=4&&/^[а-я]+$/.test(last)){
      const tails=/[бвгджзклмнпрстфхцчшщ]$/.test(last)?['а','у','ом','е']:[];
      tails.forEach(tail=>result.add([...parts,last+tail].join(' ')));
    }
    return result;
  }
  function inPeriod(record,days,end=Date.now()){
    const date=Date.parse(record.published_at);
    return Number.isFinite(date)&&date>end-days*DAY&&date<=end;
  }
  function validate(snapshot){
    if(snapshot?.schema_version!=='business-evidence-1.0'||!Array.isArray(snapshot.articles)||!snapshot.coverage||
       !snapshot.topic_definitions||!Number.isFinite(Date.parse(snapshot.generated_at)))throw Error('Некорректный формат аналитических данных');
    const ids=new Set(),urls=new Set();
    for(const article of snapshot.articles){
      if(!article||ids.has(article.id)||urls.has(article.url)||!Array.isArray(article.names)||!Array.isArray(article.topics)||
         !Array.isArray(article.watchlists)||!Number.isFinite(Date.parse(article.published_at))||
         typeof article.title!=='string'||typeof article.excerpt!=='string'||typeof article.source!=='string'||
         !/^https:\/\//i.test(article.url))throw Error('Повреждена запись аналитики');
      const url=new URL(article.url);if(url.username||url.password)throw Error('Некорректный адрес источника');
      ids.add(article.id);
      urls.add(article.url);
    }
    return snapshot;
  }
  function analyze(snapshot,company,industry,days,now=Date.now()){
    if(![7,30,90].includes(days))throw Error('Неизвестный период');
    const aliases=company.split(/[;\n]+/).map(normalize).filter(value=>value.length>=2);
    if(!aliases.length)throw Error('Укажите название компании, а не только её юридическую форму');
    const list=(snapshot.watchlists||[]).find(item=>[item.name,...item.aliases].some(alias=>aliases.includes(normalize(alias))));
    const candidates=new Set(aliases.flatMap(value=>[...forms(value)]));
    const matched=snapshot.articles.filter(article=>list?article.watchlists.includes(list.id):article.names.some(name=>candidates.has(name)));
    const mentions=matched.map(article=>({...article,text:article.excerpt,tone:'unknown',label:'Тональность не оценена',
      daysAgo:Math.floor((now-Date.parse(article.published_at))/DAY)}));
    const selected=mentions.filter(record=>inPeriod(record,days,now));
    const collectionStart=Date.parse(snapshot.coverage.first_collected_at);
    const historyAvailable=!snapshot.coverage.limited&&Number.isFinite(collectionStart)&&collectionStart<=now-2*days*DAY;
    const trends=(snapshot.topic_definitions[industry]||[]).map(topic=>{
      const related=snapshot.articles.filter(article=>article.topics.includes(topic.id));
      const current=related.filter(record=>inPeriod(record,days,now));
      const previous=related.filter(record=>inPeriod(record,days,now-days*DAY));
      const rate=historyAvailable&&previous.length?Math.round(100*(current.length-previous.length)/previous.length):null;
      return {...topic,count:current.length,previous:previous.length,rate,
        growth:rate===null?'—':(rate>0?'+':'')+rate+'%',
        detail:'Совпадения ключевых слов темы в собранных материалах. '+current.length+' публикаций за выбранный период.',
        evidence:current.slice(0,5).map(({title,source,url,excerpt})=>({title:title||excerpt,source,url}))};
    }).filter(topic=>topic.count>0).sort((a,b)=>b.count-a.count||a.title.localeCompare(b.title,'ru'));
    const opportunities=trends.map(topic=>({kind:'ТЕМА ДЛЯ ПРОВЕРКИ',title:topic.title,
      detail:'Проверьте исходные публикации и определите, есть ли у компании подтверждённая экспертиза по этой теме.',evidence:topic.evidence}));
    return {mode:'real',company:list?.name||company,industry,days,now,generated_at:snapshot.generated_at,
      coverage:snapshot.coverage,mentions,selected,sources:[...new Set(mentions.map(record=>record.source))],
      trends,opportunities,actions:opportunities.map(()=>['Прочитайте исходные материалы.','Сформулируйте проверяемую экспертную позицию.','Подтвердите факты перед подготовкой комментария.']),
      tone_assessed:false,watchlist:list?.id||null};
  }
  const api={normalize,inPeriod,validate,analyze};
  if(typeof window!=='undefined')window.MediaStrazhBusiness=api;
  if(typeof module!=='undefined')module.exports=api;
})();
