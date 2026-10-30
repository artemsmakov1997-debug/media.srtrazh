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
  });

  show('intro');
})();
