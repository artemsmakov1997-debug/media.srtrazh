/* Manual demo browsing and accessible full-list dialog. No backend/rating calculation added. */
(() => {
  'use strict';
  function describeRange() {
    const label = isMobile()
      ? `${mobileIndex + 1} из ${mediaData.length}`
      : `${offset + 1}–${Math.min(offset + cardsCount, mediaData.length)} из ${mediaData.length}`;
    document.getElementById('ratingRange').textContent = label;
  }
  function shift(direction) {
    if (isMobile()) {
      mobileIndex = (mobileIndex + direction + mediaData.length) % mediaData.length;
      offset = 0;
    } else {
      const last = Math.max(0, mediaData.length - cardsCount);
      offset = direction > 0
        ? (offset >= last ? 0 : Math.min(offset + cardsCount, last))
        : (offset === 0 ? last : Math.max(0, offset - cardsCount));
    }
    updateCards();
    updateMobileSliderState();
    describeRange();
  }
  document.getElementById('ratingPrev').addEventListener('click', () => shift(-1));
  document.getElementById('ratingNext').addEventListener('click', () => shift(1));
  window.addEventListener('resize', () => setTimeout(describeRange, 200));
  describeRange();

  let opener = null;
  let wasOpen = false;
  const modal = document.getElementById('fullListModal');
  const background = [...document.querySelectorAll('body > header, body > main, body > footer')];
  let previousInert = [];
  document.querySelectorAll('.show-full-list-trigger').forEach(button => {
    button.addEventListener('click', () => { opener = button; }, true);
  });
  new MutationObserver(() => {
    const open = modal.classList.contains('open');
    if (open === wasOpen) return;
    wasOpen = open;
    if (open) {
      previousInert = background.map(element => element.inert);
      background.forEach(element => { element.inert = true; });
    } else {
      background.forEach((element,index) => { element.inert = previousInert[index] || false; });
      if (opener?.isConnected) opener.focus({preventScroll:true});
    }
  }).observe(modal, {attributes:true, attributeFilter:['class']});
  modal.addEventListener('keydown', event => {
    if (event.key !== 'Tab') return;
    const focusable = [...modal.querySelectorAll('button,a[href],input,select,[tabindex="0"]')]
      .filter(element => !element.disabled && element.getBoundingClientRect().width > 0);
    const first = focusable[0], last = focusable[focusable.length-1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault(); last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault(); first.focus();
    }
  });
})();
