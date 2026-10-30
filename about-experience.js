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
  const finale = film?.querySelector('.about-film-tag');

  if (!screen || Object.values(stages).some(stage => !stage) ||
      buttons.length !== 3 || !film || !replay || !speed || !finale) return;

  const channelLabels = new Map(buttons.map(button => [button, button.textContent.trim()]));
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const rates = [1, 2, 3];
  const filmDuration = 12000;  // Original author-supplied loop: 12 seconds.
  let rateIndex = 0;
  let filmTimer = null;
  let filmStart = 0;
  let filmElapsed = 0; // Media milliseconds elapsed at the last (re)base.
  let filmRunning = false;
  let filmPaused = false;
  let filmRevision = 0;

  let activeChannel = 'intro';
  let channelTimer = null;
  let channelRevision = 0;

  function cancelFilmTimer() {
    if (filmTimer !== null) clearTimeout(filmTimer);
    filmTimer = null;
  }
  function filmAnimations() {
    return film.getAnimations({subtree:true});
  }
  function playAllFilmAnimations() {
    for (const animation of filmAnimations()) {
      animation.playbackRate = rates[rateIndex];
      animation.play();
    }
  }
  function scheduleFilmLoop(revision) {
    cancelFilmTimer();
    if (reduceMotion || !filmRunning || filmPaused) return;
    const remaining = Math.max(1, (filmDuration - filmElapsed) / rates[rateIndex]);
    filmTimer = setTimeout(() => {
      if (revision === filmRevision && activeChannel === 'intro' && !document.hidden)
        startFilm();
    }, remaining);
  }
  function startFilm() {
    cancelFilmTimer();
    const revision = ++filmRevision;
    filmRunning = true;
    filmPaused = false;
    filmElapsed = 0;
    film.classList.remove('is-playing');
    // Reflow is deliberate: every CSS keyframe must replay from the start.
    void film.offsetWidth;
    film.classList.add('is-playing');
    film.dataset.filmStatus = reduceMotion ? 'complete' : 'playing';
    if (reduceMotion) return;
    playAllFilmAnimations();
    filmStart = performance.now();
    scheduleFilmLoop(revision);
  }
  function stopFilm() {
    cancelFilmTimer();
    ++filmRevision;
    filmRunning = false;
    filmPaused = false;
    filmElapsed = 0;
    film.classList.remove('is-playing');
    film.dataset.filmStatus = 'ready';
  }
  function pauseFilm() {
    if (reduceMotion || !filmRunning || filmPaused) return;
    filmElapsed = Math.min(filmDuration,
      filmElapsed + (performance.now() - filmStart) * rates[rateIndex]);
    filmPaused = true;
    cancelFilmTimer();
    for (const animation of filmAnimations()) animation.pause();
  }
  function resumeFilm() {
    if (reduceMotion || !filmRunning || !filmPaused || activeChannel !== 'intro') return;
    filmPaused = false;
    filmStart = performance.now();
    playAllFilmAnimations();
    scheduleFilmLoop(filmRevision);
  }

  speed.addEventListener('click', () => {
    if (filmRunning && !filmPaused && !reduceMotion) {
      filmElapsed = Math.min(filmDuration,
        filmElapsed + (performance.now() - filmStart) * rates[rateIndex]);
      filmStart = performance.now();
    }
    rateIndex = (rateIndex + 1) % rates.length;
    const next = rates[rateIndex];
    speed.textContent = 'Скорость ×' + next;
    speed.setAttribute('aria-label', 'Скорость воспроизведения ×' + next + '. Изменить скорость');
    if (!reduceMotion) {
      for (const animation of filmAnimations()) animation.playbackRate = next;
      scheduleFilmLoop(filmRevision);
    }
  });

  replay.addEventListener('click', startFilm);

  finale.addEventListener('animationend', event => {
    if (event.target !== finale || event.animationName !== 'about-film-up') return;
    if (filmRunning && activeChannel === 'intro') film.dataset.filmStatus = 'complete';
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
