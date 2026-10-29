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
    cancel();
    currentChannel = name;
    Object.entries(stages).forEach(([key, stage]) => {
      stage.hidden = key !== name;
      if (key === name) stage.scrollTop = 0;
    });
    tabs.forEach(button => {
      button.setAttribute('aria-pressed', String(button.dataset.aboutChannel === name));
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
