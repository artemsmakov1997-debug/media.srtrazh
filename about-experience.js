/* МЕДИА.СТРАЖ / about — five TV channels, one screen. */
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
    menu.querySelectorAll('a').forEach(a => a.addEventListener('click', closeMenu));
    document.addEventListener('click', e => {
      if (!menu.contains(e.target) && !burger.contains(e.target)) closeMenu();
    });
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape') closeMenu();
    });
  }

  const root = document.querySelector('[data-about-experience]');
  if (!root) return;
  const screen = document.getElementById('aboutMonitorScreen');
  const stages = {
    intro: document.getElementById('aboutStageIntro'),
    journalist: document.getElementById('aboutStageJournalist'),
    reader: document.getElementById('aboutStageReader'),
    principles: document.getElementById('aboutStagePrinciples'),
    opportunities: document.getElementById('aboutStageOpportunities'),
    creator: document.getElementById('aboutStageCreator')
  };
  const tabs = Array.from(root.querySelectorAll('[data-about-channel]'));
  const percent = document.getElementById('aboutRatingNumber');
  const fill = document.getElementById('aboutRatingFill');
  const sentence = document.getElementById('aboutReaderSentence');
  const note = document.getElementById('aboutReaderNote');
  if (!screen || Object.values(stages).some(stage => !stage) ||
      tabs.length !== 5 || !percent || !fill || !sentence || !note) return;

  const phrase = 'Запад снова пытается дестабилизировать ситуацию в регионе.';
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  let currentChannel = 'intro';
  let generation = 0;
  let timeoutId = null;
  let frameId = null;
  let channelTimer = null;
  let channelSerial = 0;
  const channelLabels = new Map(tabs.map(button => [button, button.textContent.trim()]));

  function cancel() {
    generation++;
    if (timeoutId !== null) clearTimeout(timeoutId);
    if (frameId !== null) cancelAnimationFrame(frameId);
    timeoutId = null;
    frameId = null;
  }

  function highlight() {
    const mark = document.createElement('mark');
    mark.textContent = 'снова пытается';
    sentence.replaceChildren(
      document.createTextNode('Запад '), mark,
      document.createTextNode(' дестабилизировать ситуацию в регионе.')
    );
  }

  function animateRating(sequence) {
    percent.textContent = '0%';
    fill.style.transition = 'none';
    fill.style.width = '0%';
    if (reducedMotion) {
      percent.textContent = '36%';
      fill.style.width = '36%';
      return;
    }
    const start = performance.now();
    const frame = time => {
      if (sequence !== generation) return;
      const progress = Math.min((time - start) / 850, 1);
      percent.textContent = Math.round(36 * (1 - (1 - progress) ** 3)) + '%';
      if (progress < 1) frameId = requestAnimationFrame(frame);
    };
    frameId = requestAnimationFrame(() => {
      if (sequence !== generation) return;
      fill.style.transition = '';
      fill.style.width = '36%';
      frameId = requestAnimationFrame(frame);
    });
  }

  function animateReader(sequence) {
    sentence.textContent = '';
    note.hidden = true;
    if (reducedMotion) {
      highlight();
      note.hidden = false;
      return;
    }
    let index = 0;
    const type = () => {
      if (sequence !== generation) return;
      sentence.textContent = phrase.slice(0, index);
      if (index < phrase.length) {
        index++;
        timeoutId = setTimeout(type, 20);
      } else {
        timeoutId = setTimeout(() => {
          if (sequence !== generation) return;
          highlight();
          note.hidden = false;
        }, 260);
      }
    };
    type();
  }

  function show(name) {
    if (!Object.prototype.hasOwnProperty.call(stages, name)) return;
    const previous = currentChannel;
    cancel();
    if (channelTimer !== null) {
      clearTimeout(channelTimer);
      channelTimer = null;
    }
    const transaction = ++channelSerial;
    const animate = previous !== name && !reducedMotion;
    currentChannel = name;

    Object.entries(stages).forEach(([key, stage]) => {
      stage.classList.remove('is-entering', 'is-leaving');
      if (key === name) {
        stage.hidden = false;
        stage.inert = false;
        stage.removeAttribute('aria-hidden');
        stage.scrollTop = 0;
      } else if (animate && key === previous) {
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
      const entering = stages[name];
      // Restart the entrance animation even during rapid channel switching.
      void entering.offsetWidth;
      entering.classList.add('is-entering');
      channelTimer = setTimeout(() => {
        if (transaction !== channelSerial) return;
        const leaving = stages[previous];
        if (leaving !== entering) {
          leaving.hidden = true;
          leaving.classList.remove('is-leaving');
        }
        entering.classList.remove('is-entering');
        channelTimer = null;
      }, 480);
    }

    tabs.forEach(button => {
      const selected = button.dataset.aboutChannel === name;
      const original = channelLabels.get(button);
      button.setAttribute('aria-pressed', String(selected));
      button.textContent = selected ? 'Назад' : original;
      button.setAttribute('aria-label', selected ? 'Назад — ' + original : original);
    });
    screen.dataset.activeChannel = name;
    const sequence = generation;
    if (name === 'journalist') animateRating(sequence);
    if (name === 'reader') animateReader(sequence);
  }

  tabs.forEach(button => {
    button.addEventListener('click', () => {
      const chosen = button.dataset.aboutChannel;
      show(chosen === currentChannel ? 'intro' : chosen);
    });
  });
  document.addEventListener('keydown', event => {
    if (event.key !== 'Escape' || currentChannel === 'intro') return;
    if (document.querySelector('.pro-gateway-overlay:not([hidden])')) return;
    show('intro');
  });
  show('intro');
})();
