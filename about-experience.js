/* About hero: accessible hover/focus/click demonstrations; no external requests. */
(() => {
  'use strict';
  const burger = document.getElementById('burgerBtn');
  const menu = document.getElementById('navLinks');
  if (burger && menu) {
    const close = () => {menu.classList.remove('open');burger.setAttribute('aria-expanded','false');};
    burger.addEventListener('click', () => {
      const open = menu.classList.toggle('open');
      burger.setAttribute('aria-expanded',String(open));
    });
    menu.querySelectorAll('a').forEach(a => a.addEventListener('click',close));
    document.addEventListener('click',event => {
      if (!menu.contains(event.target) && !burger.contains(event.target)) close();
    });
    document.addEventListener('keydown',event => {if(event.key === 'Escape')close();});
  }
  const root = document.querySelector('[data-about-experience]');
  if (!root) return;
  const triggers = Array.from(root.querySelectorAll('[data-about-choose]'));
  const reader = document.getElementById('aboutReaderSentence');
  const percent = document.getElementById('aboutRatingNumber');
  const reduced = window.matchMedia('(prefers-reduced-motion:reduce)').matches;
  const phrase = 'Запад снова пытается дестабилизировать ситуацию в регионе.';
  let token = 0;
  let timer = null;
  let raf = null;
  function cancel() {
    token++;
    if(timer !== null) clearTimeout(timer);
    if(raf !== null) cancelAnimationFrame(raf);
    timer=null;
    raf=null;
  }
  function highlight() {
    reader.replaceChildren();
    reader.append(document.createTextNode('Запад '));
    const mark = document.createElement('mark');
    mark.textContent = 'снова пытается';
    reader.append(mark,document.createTextNode(' дестабилизировать ситуацию в регионе.'));
  }
  function show(which) {
    cancel();
    const active = token;
    root.classList.remove('is-journalist','is-reader');
    void root.offsetHeight; // replay CSS bar/callout animation on consecutive activations
    root.classList.add(which === 'journalist' ? 'is-journalist' : 'is-reader');
    triggers.forEach(b => b.setAttribute('aria-pressed',String(b.dataset.aboutChoose === which)));
    if(which === 'reader') {
      percent.textContent = '36%';
      if(reduced){highlight();return;}
      reader.textContent = '';
      let n=0;
      const tick = () => {
        if(active!==token)return;
        reader.textContent = phrase.slice(0,n);
        if(n<phrase.length){n++;timer=setTimeout(tick,21);}
        else{highlight();}
      };
      tick();
    } else {
      highlight();
      if(reduced){percent.textContent='36%';return;}
      const start = performance.now();
      const count = time => {
        if(active!==token)return;
        const t=Math.min((time-start)/680,1);
        percent.textContent = Math.round(36*(1-Math.pow(1-t,3)))+'%';
        if(t<1)raf=requestAnimationFrame(count);
      };
      percent.textContent='0%';
      raf=requestAnimationFrame(count);
    }
  }
  highlight();
  triggers.forEach(b => {
    const which=b.dataset.aboutChoose;
    b.addEventListener('pointerenter',() => show(which));
    b.addEventListener('focus',() => show(which));
    b.addEventListener('click',() => show(which));
  });
})();
