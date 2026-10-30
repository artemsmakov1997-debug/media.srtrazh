/* МЕДИА.СТРАЖ — interactive three-channel TV and narrated demo. */
(() => {
  'use strict';
  const burger = document.getElementById('burgerBtn');
  const menu = document.getElementById('navLinks');
  if (burger && menu) {
    const closeMenu = () => {
      menu.classList.remove('open');
      burger.setAttribute('aria-expanded', 'false');
    };
    burger.addEventListener('click', () => {
      burger.setAttribute('aria-expanded', String(menu.classList.toggle('open')));
    });
    menu.querySelectorAll('a').forEach(link => link.addEventListener('click', closeMenu));
    document.addEventListener('click', event => {
      if (!menu.contains(event.target) && !burger.contains(event.target)) closeMenu();
    });
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape') closeMenu();
    });
  }

  const root = document.querySelector('[data-about-experience]');
  if (!root) return;
  const screen = document.getElementById('aboutMonitorScreen');
  const stages = {
    intro: document.getElementById('aboutStageIntro'),
    principles: document.getElementById('aboutStagePrinciples'),
    opportunities: document.getElementById('aboutStageOpportunities'),
    creator: document.getElementById('aboutStageCreator')
  };
  const buttons = Array.from(root.querySelectorAll('[data-about-channel]'));
  const story = document.getElementById('aboutStory');
  const speedButton = document.getElementById('storySpeed');
  const replayButton = document.getElementById('storyReplay');
  const scanFill = document.getElementById('storyScanFill');
  const scanPercent = document.getElementById('storyScanPercent');
  const ratingFill = document.getElementById('storyRatingFill');
  const ratingNumber = document.getElementById('storyRatingNumber');
  const status = document.getElementById('aboutStoryStatus');

  if (!screen || !story || !speedButton || !replayButton || !scanFill ||
      !scanPercent || !ratingFill || !ratingNumber || !status ||
      Object.values(stages).some(value => !value) || buttons.length !== 3) return;

  const channelLabels = new Map(buttons.map(b => [b,b.textContent.trim()]));
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const phases = [
    {time:0, name:'logo',label:'МЕДИА.СТРАЖ / Запуск'},
    {time:1500,name:'news',label:'01 / Новость опубликована на сайте издания'},
    {time:3700,name:'collect',label:'02 / Алгоритм получает сообщение'},
    {time:5400,name:'scan',label:'03 / Сканирование формулировок'},
    {time:7800,name:'found',label:'03 / Найдены два спорных маркера'},
    {time:10100,name:'rating',label:'04 / Пересчёт показателя'},
    {time:12300,name:'done',label:'04 / Рейтинг обновлён · Демонстрационный пример'}
  ];
  const totalDuration = phases[phases.length - 1].time;
  const speeds = [1,2,3];
  let speedIndex=0;
  let storyFrame=null;
  let storyElapsed=0;
  let storyAnchor=0;
  let playing=false;
  let activeChannel='intro';
  let channelTimer=null;
  let channelRevision=0;

  function setStoryVisual(elapsed) {
    let phase=phases[0];
    for (const candidate of phases) {
      if (elapsed>=candidate.time) phase=candidate;
      else break;
    }
    if (story.dataset.step!==phase.name) {
      story.dataset.step=phase.name;
      status.textContent=phase.label;
    }
    const scanProgress=Math.min(1,Math.max(0,(elapsed-5400)/(7800-5400)));
    scanFill.style.width=Math.round(scanProgress*100)+'%';
    scanPercent.textContent=Math.round(scanProgress*100)+'%';
    const ratingProgress=Math.min(1,Math.max(0,(elapsed-10100)/(12300-10100)));
    ratingFill.style.width=(ratingProgress*36).toFixed(1)+'%';
    ratingNumber.textContent=Math.round(ratingProgress*36)+'%';
    const phaseIndex=phases.indexOf(phase);
    story.querySelectorAll('[data-story-part]').forEach((element,index) => {
      const range=[1,2,3,5];
      element.classList.toggle('is-complete',phaseIndex>range[index]);
    });
  }
  function pauseStory() {
    if (storyFrame!==null)cancelAnimationFrame(storyFrame);
    storyFrame=null;
    playing=false;
  }
  function tick(now) {
    if (!playing || activeChannel!=='intro')return;
    const elapsed=Math.min(totalDuration,storyElapsed+(now-storyAnchor)*speeds[speedIndex]);
    setStoryVisual(elapsed);
    if (elapsed>=totalDuration) {
      storyElapsed=totalDuration;
      playing=false;
      storyFrame=null;
      return;
    }
    storyFrame=requestAnimationFrame(tick);
  }
  function playFromStart() {
    pauseStory();
    storyElapsed=0;
    story.style.setProperty('--story-transition',(560/speeds[speedIndex]).toFixed(0)+'ms');
    if (reducedMotion) {
      setStoryVisual(totalDuration);
      return;
    }
    setStoryVisual(0);
    storyAnchor=performance.now();
    playing=true;
    storyFrame=requestAnimationFrame(tick);
  }
  function changeSpeed() {
    if (playing) {
      const now=performance.now();
      storyElapsed=Math.min(totalDuration,storyElapsed+(now-storyAnchor)*speeds[speedIndex]);
      storyAnchor=now;
    }
    speedIndex=(speedIndex+1)%speeds.length;
    speedButton.textContent='Скорость ×'+speeds[speedIndex];
    speedButton.setAttribute('aria-label','Скорость воспроизведения ×'+speeds[speedIndex]+'. Нажмите для изменения');
    story.style.setProperty('--story-transition',(560/speeds[speedIndex]).toFixed(0)+'ms');
    setStoryVisual(storyElapsed);
  }
  speedButton.addEventListener('click',changeSpeed);
  replayButton.addEventListener('click',playFromStart);

  function show(channel) {
    if (!Object.prototype.hasOwnProperty.call(stages,channel))return;
    const previous=activeChannel;
    if (channelTimer!==null)clearTimeout(channelTimer);
    const revision=++channelRevision;
    const animate=previous!==channel&&!reducedMotion;
    activeChannel=channel;
    if (channel!=='intro')pauseStory();
    for (const [name,stage] of Object.entries(stages)) {
      stage.classList.remove('is-entering','is-leaving');
      if (name===channel) {
        stage.hidden=false;
        stage.inert=false;
        stage.removeAttribute('aria-hidden');
        stage.scrollTop=0;
      } else if (animate&&name===previous) {
        stage.hidden=false;
        stage.inert=true;
        stage.setAttribute('aria-hidden','true');
        stage.classList.add('is-leaving');
      } else {
        stage.hidden=true;
        stage.inert=true;
        stage.setAttribute('aria-hidden','true');
      }
    }
    if (animate) {
      void stages[channel].offsetWidth;
      stages[channel].classList.add('is-entering');
      channelTimer=setTimeout(() => {
        if (channelRevision!==revision)return;
        stages[previous].hidden=true;
        stages[previous].classList.remove('is-leaving');
        stages[channel].classList.remove('is-entering');
        channelTimer=null;
      },480);
    }
    buttons.forEach(button => {
      const selected=button.dataset.aboutChannel===channel;
      const original=channelLabels.get(button);
      button.textContent=selected?'Назад':original;
      button.setAttribute('aria-pressed',String(selected));
      button.setAttribute('aria-label',selected?'Назад — '+original:original);
    });
    screen.dataset.activeChannel=channel;
    if (channel==='intro' && (previous!=='intro'||!story.dataset.step))playFromStart();
  }
  buttons.forEach(button => button.addEventListener('click',() => {
    const channel=button.dataset.aboutChannel;
    show(activeChannel===channel?'intro':channel);
  }));
  document.addEventListener('keydown',event => {
    if (event.key!=='Escape'||activeChannel==='intro')return;
    if (document.querySelector('.pro-gateway-overlay:not([hidden])'))return;
    show('intro');
  });
  document.addEventListener('visibilitychange',() => {
    if (document.hidden&&playing) {
      storyElapsed=Math.min(totalDuration,storyElapsed+(performance.now()-storyAnchor)*speeds[speedIndex]);
      pauseStory();
    } else if (!document.hidden&&activeChannel==='intro'&&!playing&&storyElapsed<totalDuration&&!reducedMotion) {
      storyAnchor=performance.now();
      playing=true;
      storyFrame=requestAnimationFrame(tick);
    }
  });
  show('intro');
  playFromStart();
})();
