/* МЕДИА.СТРАЖ / about — author-supplied HTML film with three TV channels. */
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
  const buttons = [...root.querySelectorAll('[data-about-channel]')];
  const film = document.getElementById('aboutFilm');
  const replay = document.getElementById('aboutFilmReplay');
  const speed = document.getElementById('aboutFilmSpeed');
  const movie = document.getElementById('aboutFilmFrame');
  const featuresMovie = document.getElementById('aboutFeaturesFilmFrame');
  const featuresPause = document.getElementById('aboutFeaturesPause');
  const featuresSpeed = document.getElementById('aboutFeaturesSpeed');
  const featuresReplay = document.getElementById('aboutFeaturesReplay');

  if (!screen || Object.values(stages).some(stage => !stage) ||
      buttons.length !== 3 || !film || !movie || !replay || !speed) return;

  const channelLabels = new Map(buttons.map(button => [button, button.textContent.trim()]));
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const rates = [1, 2, 3];
  let rateIndex = 0;
  let filmRunning = false;

  let activeChannel = 'intro';
  let channelTimer = null;
  let channelRevision = 0;
  let featuresPlaying = false;
  let featuresRateIndex = 1;
  const featuresRates = [.5, 1, 1.5, 2];
  function sectionFilm(channel, capital) {
    const frame = document.getElementById('about' + capital + 'FilmFrame');
    const pause = document.getElementById('about' + capital + 'Pause');
    const speed = document.getElementById('about' + capital + 'Speed');
    const replay = document.getElementById('about' + capital + 'Replay');
    let playing = false, rateIndex = 1;
    const send = (action, value) => frame?.contentWindow?.postMessage(
      {type:'media-strazh-' + channel + '-control',action,value},location.origin);
    const start = (explicit = false) => {
      playing = explicit || !reduceMotion;
      if (pause) pause.textContent = playing ? 'Пауза' : 'Продолжить';
      send('speed',featuresRates[rateIndex]); send(explicit ? 'replay' : 'present');
    };
    frame?.addEventListener('load',() => {
      if (activeChannel === channel && !document.hidden) start(); else send('pause');
    });
    pause?.addEventListener('click',() => {
      playing = !playing; pause.textContent = playing ? 'Пауза' : 'Продолжить'; send(playing ? 'resume' : 'pause');
    });
    speed?.addEventListener('click',() => {
      rateIndex = (rateIndex + 1) % featuresRates.length;
      speed.textContent = 'Скорость ×' + featuresRates[rateIndex];send('speed',featuresRates[rateIndex]);
    });
    replay?.addEventListener('click',() => start(true));
    window.addEventListener('message',event => {
      if (event.source !== frame?.contentWindow || event.origin !== location.origin ||
          event.data?.type !== 'media-strazh-' + channel + '-event' || activeChannel !== channel) return;
      if (event.data.action === 'state' && typeof event.data.running === 'boolean') {
        playing = event.data.running;if (pause) pause.textContent = playing ? 'Пауза' : 'Продолжить';
      }
      if (event.data.action === 'back') {
        show('intro'); buttons.find(button => button.dataset.aboutChannel === channel)?.focus();
      }
    });
    return {channel,start,stop(){playing=false;send('pause');},visibility(){
      if(document.hidden)send('pause');else if(activeChannel===channel&&playing)send('resume');
    }};
  }
  const sectionFilms = [sectionFilm('principles','Principles'),sectionFilm('creator','Creator')];

  function sendFeatures(action, value) {
    featuresMovie?.contentWindow?.postMessage(
      {type: 'media-strazh-features-control', action, value}, window.location.origin);
  }
  function startFeatures(explicit = false) {
    featuresPlaying = explicit || !reduceMotion;
    if (featuresPause) featuresPause.textContent = featuresPlaying ? 'Пауза' : 'Продолжить';
    sendFeatures('speed', featuresRates[featuresRateIndex]);
    sendFeatures(explicit ? 'replay' : 'present');
  }
  featuresMovie?.addEventListener('load', () => {
    if (activeChannel === 'opportunities' && !document.hidden) startFeatures();
    else sendFeatures('pause');
  });
  featuresReplay?.addEventListener('click', () => startFeatures(true));
  featuresPause?.addEventListener('click', () => {
    featuresPlaying = !featuresPlaying;
    featuresPause.textContent = featuresPlaying ? 'Пауза' : 'Продолжить';
    sendFeatures(featuresPlaying ? 'resume' : 'pause');
  });
  featuresSpeed?.addEventListener('click', () => {
    featuresRateIndex = (featuresRateIndex + 1) % featuresRates.length;
    const value = featuresRates[featuresRateIndex];
    featuresSpeed.textContent = 'Скорость ×' + value;
    sendFeatures('speed', value);
  });
  window.addEventListener('message', event => {
    if (event.source !== featuresMovie?.contentWindow || event.origin !== window.location.origin ||
        event.data?.type !== 'media-strazh-features-event' || activeChannel !== 'opportunities') return;
    if (event.data.action === 'state' && typeof event.data.running === 'boolean') {
      featuresPlaying = event.data.running;
      if (featuresPause) featuresPause.textContent = featuresPlaying ? 'Пауза' : 'Продолжить';
    }
    if (event.data.action === 'back') {
      show('intro');
      buttons.find(button => button.dataset.aboutChannel === 'opportunities')?.focus();
    }
  });

  function sendFilm(action, value) {
    if (!movie.contentWindow) return;
    movie.contentWindow.postMessage(
      {type: 'media-strazh-film-control', action, value},
      window.location.origin
    );
  }

  function startFilm() {
    filmRunning = true;
    film.dataset.filmStatus = 'playing';
    sendFilm('replay');
    sendFilm('speed', rates[rateIndex]);
  }

  function stopFilm() {
    filmRunning = false;
    film.dataset.filmStatus = 'ready';
    sendFilm('pause');
  }

  function pauseFilm() {
    if (filmRunning) sendFilm('pause');
  }

  function resumeFilm() {
    if (filmRunning && activeChannel === 'intro') sendFilm('resume');
  }

  speed.addEventListener('click', () => {
    rateIndex = (rateIndex + 1) % rates.length;
    const next = rates[rateIndex];
    speed.textContent = 'Скорость ×' + next;
    speed.setAttribute('aria-label', 'Скорость воспроизведения ×' + next + '. Изменить скорость');
    sendFilm('speed', next);
  });

  replay.addEventListener('click', startFilm);

  window.addEventListener('message', event => {
    if (event.source !== movie.contentWindow || event.origin !== window.location.origin) return;
    if (event.data?.type === 'media-strazh-film-event' && event.data.action === 'complete' &&
        filmRunning && activeChannel === 'intro') film.dataset.filmStatus = 'complete';
  });

  movie.addEventListener('load', () => {
    sendFilm('speed', rates[rateIndex]);
    if (activeChannel === 'intro' && !document.hidden) startFilm();
    else sendFilm('pause');
  });

  function show(channel) {
    if (!Object.prototype.hasOwnProperty.call(stages, channel)) return;
    const previous = activeChannel;
    if (channelTimer !== null) clearTimeout(channelTimer);
    const revision = ++channelRevision;
    const animate = previous !== channel && !reduceMotion;
    activeChannel = channel;
    if (channel !== 'intro') stopFilm();

    Object.entries(stages).forEach(([name, stage]) => {
      stage.classList.remove('is-entering', 'is-leaving');
      if (name === channel) {
        stage.hidden = false;
        stage.inert = false;
        stage.removeAttribute('aria-hidden');
        stage.scrollTop = 0;
      } else if (animate && name === previous) {
        stage.hidden = false;
        stage.inert = true;
        stage.setAttribute('aria-hidden', 'true');
        stage.classList.add('is-leaving');
      } else {
        stage.hidden = true;
        stage.inert = true;
        stage.setAttribute('aria-hidden', 'true');
      }
    });

    if (animate) {
      void stages[channel].offsetWidth;
      stages[channel].classList.add('is-entering');
      channelTimer = setTimeout(() => {
        if (revision !== channelRevision) return;
        stages[previous].hidden = true;
        stages[previous].classList.remove('is-leaving');
        stages[channel].classList.remove('is-entering');
        channelTimer = null;
      }, 480);
    }
    buttons.forEach(button => {
      const selected = button.dataset.aboutChannel === channel;
      const original = channelLabels.get(button);
      button.textContent = selected ? 'Назад' : original;
      button.setAttribute('aria-pressed', String(selected));
      button.setAttribute('aria-label', selected ? 'Назад — ' + original : original);
    });
    screen.dataset.activeChannel = channel;
    if (channel === 'intro' && (previous !== 'intro' || !filmRunning)) startFilm();
    if (channel === 'opportunities') startFeatures();
    else { featuresPlaying = false; sendFeatures('pause'); }
    sectionFilms.forEach(player => player.channel === channel ? player.start() : player.stop());
  }

  buttons.forEach(button => button.addEventListener('click', () => {
    const channel = button.dataset.aboutChannel;
    show(activeChannel === channel ? 'intro' : channel);
  }));

  document.addEventListener('keydown', event => {
    if (event.key !== 'Escape' || activeChannel === 'intro') return;
    if (document.querySelector('.pro-gateway-overlay:not([hidden])')) return;
    show('intro');
  });

  document.addEventListener('visibilitychange', () => {
    if (document.hidden) pauseFilm();
    else resumeFilm();
    if (document.hidden) sendFeatures('pause');
    else if (activeChannel === 'opportunities' && featuresPlaying) sendFeatures('resume');
    sectionFilms.forEach(player => player.visibility());
  });

  show('intro');
})();
