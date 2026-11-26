/* Playback for the supplied principles/creator films; no network or libraries. */
(() => {
  'use strict';
  const name = document.body.dataset.film;
  const embedded = parent !== window;
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const pauseButton = document.getElementById('pause');
  const speedButton = document.getElementById('spd');
  let running = false, raf = 0, last = 0;
  const sendState = () => {
    if (embedded) parent.postMessage({type:'media-strazh-' + name + '-event',action:'state',running},location.origin);
  };
  function pause(announce = false) {
    running = false; cancelAnimationFrame(raf);
    pauseButton.textContent = 'Продолжить';
    document.getElementById('stage').classList.add('is-paused');
    if (announce) sendState();
  }
  function loop(now) {
    if (!running) return;
    t += Math.min(.1,(now-last)/1000) * speed; last = now;
    if (t >= T) t = 0;
    upd(); raf = requestAnimationFrame(loop);
  }
  function resume(announce = false) {
    if (running) return;
    running = true; last = performance.now(); pauseButton.textContent = 'Пауза';
    document.getElementById('stage').classList.remove('is-paused');
    raf = requestAnimationFrame(loop);
    if (announce) sendState();
  }
  function replay() { pause(); t = 0; upd(); resume(); }
  function present() {
    if (reduced) { pause(); t = Number(document.body.dataset.poster); upd(); }
    else replay();
  }
  function setSpeed(value) {
    value = Number(value);
    if (![.5,1,1.5,2].includes(value)) return;
    speed = value; speedButton.textContent = 'Скорость ×' + value;
  }
  document.getElementById('rep').addEventListener('click',replay);
  pauseButton.addEventListener('click',() => running ? pause(true) : resume(true));
  speedButton.addEventListener('click',() => {
    const rates = [.5,1,1.5,2]; setSpeed(rates[(rates.indexOf(speed)+1)%rates.length]);
  });
  window.mediaFilm = {replay,setSpeed,pause,resume,present,state:() => ({time:t,speed,running})};
  addEventListener('message',event => {
    if (event.source !== parent || event.origin !== location.origin || event.data?.type !== 'media-strazh-' + name + '-control') return;
    const {action,value} = event.data;
    if (action === 'pause') pause();
    if (action === 'resume') resume();
    if (action === 'replay') replay();
    if (action === 'present') present();
    if (action === 'speed') setSpeed(value);
  });
  document.addEventListener('keydown',event => {
    if (event.key === 'Escape' && embedded) {
      event.preventDefault(); parent.postMessage({type:'media-strazh-' + name + '-event',action:'back'},location.origin);
    }
  });
  if (embedded) { document.getElementById('ctl').hidden = true; pause(); upd(); }
  else present();
})();
