/* About: one screen, switchable journalist/reader demonstrations. */
(() => {
  'use strict';
  const burger = document.getElementById('burgerBtn');
  const menu = document.getElementById('navLinks');
  if (burger && menu) {
    const close = () => { menu.classList.remove('open'); burger.setAttribute('aria-expanded', 'false'); };
    burger.addEventListener('click', () => {
      const open = menu.classList.toggle('open');
      burger.setAttribute('aria-expanded', String(open));
    });
    menu.querySelectorAll('a').forEach(a => a.addEventListener('click', close));
    document.addEventListener('click', event => {
      if (!menu.contains(event.target) && !burger.contains(event.target)) close();
    });
    document.addEventListener('keydown', event => { if (event.key === 'Escape') close(); });
  }

  const root = document.querySelector('[data-about-experience]');
  if (!root) return;
  const stages = {
    intro: document.getElementById('aboutStageIntro'),
    journalist: document.getElementById('aboutStageJournalist'),
    reader: document.getElementById('aboutStageReader')
  };
  const triggers = Array.from(root.querySelectorAll('[data-about-choose]'));
  const reader = document.getElementById('aboutReaderSentence');
  const readerNote = document.getElementById('aboutReaderNote');
  const percent = document.getElementById('aboutRatingNumber');
  const bar = document.getElementById('aboutRatingFill');
  if (Object.values(stages).some(stage => !stage) ||
      !reader || !readerNote || !percent || !bar || triggers.length !== 2) return;

  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const phrase = 'Запад снова пытается дестабилизировать ситуацию в регионе.';
  let current = 'intro';
  let serial = 0;
  let timer = null;
  let animationFrame = null;

  function cancelAnimations() {
    serial++;
    if (timer !== null) clearTimeout(timer);
    if (animationFrame !== null) cancelAnimationFrame(animationFrame);
    timer = null;
    animationFrame = null;
  }

  function highlightPhrase() {
    reader.replaceChildren(document.createTextNode('Запад '));
    const mark = document.createElement('mark');
    mark.textContent = 'снова пытается';
    reader.append(mark, document.createTextNode(' дестабилизировать ситуацию в регионе.'));
  }

  function animateJournalist(version) {
    percent.textContent = '0%';
    bar.style.width = '0%';
    if (reducedMotion) {
      percent.textContent = '36%';
      bar.style.width = '36%';
      return;
    }
    const started = performance.now();
    const step = now => {
      if (serial !== version) return;
      const t = Math.min((now - started) / 840, 1);
      percent.textContent = Math.round(36 * (1 - Math.pow(1 - t, 3))) + '%';
      if (t < 1) animationFrame = requestAnimationFrame(step);
    };
    animationFrame = requestAnimationFrame(() => {
      if (serial !== version) return;
      bar.style.width = '36%';
      animationFrame = requestAnimationFrame(step);
    });
  }

  function animateReader(version) {
    readerNote.hidden = true;
    if (reducedMotion) {
      highlightPhrase();
      readerNote.hidden = false;
      return;
    }
    reader.textContent = '';
    let index = 0;
    function typeNext() {
      if (serial !== version) return;
      reader.textContent = phrase.slice(0, index);
      if (index < phrase.length) {
        index++;
        timer = setTimeout(typeNext, 22);
      } else {
        timer = setTimeout(() => {
          if (serial !== version) return;
          highlightPhrase();
          readerNote.hidden = false;
        }, 240);
      }
    }
    typeNext();
  }

  function show(view) {
    if (!Object.hasOwn(stages, view)) return;
    cancelAnimations();
    current = view;
    Object.entries(stages).forEach(([name, element]) => {
      element.hidden = name !== view;
    });
    triggers.forEach(button => {
      button.setAttribute('aria-pressed', String(button.dataset.aboutChoose === view));
    });
    const version = serial;
    if (view === 'journalist') animateJournalist(version);
    if (view === 'reader') animateReader(version);
  }

  triggers.forEach(button => {
    button.addEventListener('click', () => {
      const view = button.dataset.aboutChoose;
      show(current === view ? 'intro' : view);
    });
  });
  root.querySelectorAll('[data-about-reset]').forEach(button => {
    button.addEventListener('click', () => {
      const oldView = current;
      show('intro');
      triggers.find(el => el.dataset.aboutChoose === oldView)?.focus({preventScroll:true});
    });
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && current !== 'intro') show('intro');
  });
  show('intro');
})();
