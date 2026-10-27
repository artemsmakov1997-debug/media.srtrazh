/* Shared marker comments for automatic analysis and the archive. */
'use strict';
window.PublicationTooltip = class PublicationTooltip {
  constructor(tooltip) {
    this.tooltip = tooltip;
    this.target = null;
    this.timer = null;
    tooltip.addEventListener('pointerenter', () => clearTimeout(this.timer));
    tooltip.addEventListener('pointerleave', () => this.scheduleHide());
    document.addEventListener('scroll', event => {
      if (!tooltip.contains(event.target)) this.hide();
    }, {capture: true, passive: true});
    window.addEventListener('resize', () => this.hide());
    if (window.visualViewport) {
      window.visualViewport.addEventListener('resize', () => this.hide());
      window.visualViewport.addEventListener('scroll', () => this.hide());
    }
  }
  hide() {
    clearTimeout(this.timer);
    if (this.target) {
      this.target.setAttribute('aria-expanded', 'false');
      this.target.removeAttribute('aria-describedby');
    }
    this.tooltip.hidden = true;
    this.target = null;
  }
  scheduleHide() {
    clearTimeout(this.timer);
    this.timer = setTimeout(() => {
      if (document.activeElement !== this.target && !this.tooltip.matches(':hover')) this.hide();
    }, 160);
  }
  show(mark) {
    const tooltip = this.tooltip;
    if (this.target === mark && !tooltip.hidden) {clearTimeout(this.timer); return;}
    const wasVisible = !tooltip.hidden;
    this.hide(); this.target = mark;
    mark.setAttribute('aria-expanded', 'true'); mark.setAttribute('aria-describedby', tooltip.id);
    tooltip.toggleAttribute('data-instant', wasVisible || mark.matches(':focus-visible'));
    const label = document.createElement('strong'), explanation = document.createElement('div');
    label.textContent = mark.dataset.label; explanation.textContent = mark.dataset.explanation;
    tooltip.replaceChildren(label, explanation);
    const viewport = window.visualViewport;
    const leftEdge = (viewport ? viewport.offsetLeft : 0) + 12;
    const topEdge = (viewport ? viewport.offsetTop : 0) + 12;
    const width = (viewport ? viewport.width : innerWidth) - 24;
    const height = (viewport ? viewport.height : innerHeight) - 24;
    const style = getComputedStyle(tooltip);
    const widthCap = Number(style.getPropertyValue('--tooltip-width')) || 310;
    const heightCap = Number(style.getPropertyValue('--tooltip-height')) || 360;
    tooltip.style.visibility = 'hidden'; tooltip.hidden = false;
    const visibleRects = Array.from(mark.getClientRects()).filter(rect => rect.bottom > topEdge && rect.top < topEdge + height);
    const firstRect = visibleRects[0] || mark.getBoundingClientRect();
    const rect = {left:firstRect.left, width:firstRect.width,
      top:visibleRects.length ? Math.max(topEdge, Math.min(...visibleRects.map(r => r.top))) : firstRect.top,
      bottom:visibleRects.length ? Math.min(topEdge + height, Math.max(...visibleRects.map(r => r.bottom))) : firstRect.bottom};
    const place = (left, top, availableWidth, availableHeight) => {
      tooltip.style.width = Math.max(1, Math.min(widthCap, availableWidth)) + 'px';
      tooltip.style.maxHeight = Math.max(1, Math.min(heightCap, availableHeight * .65)) + 'px';
      const preferredHeight = tooltip.offsetHeight;
      const above = rect.top - top - 10, below = top + availableHeight - rect.bottom - 10;
      const useAbove = above >= preferredHeight || (below < preferredHeight && above > below);
      const room = Math.max(1, useAbove ? above : below);
      tooltip.style.maxHeight = Math.max(1, Math.min(heightCap, availableHeight * .65, room)) + 'px';
      const size = {width:tooltip.offsetWidth, height:tooltip.offsetHeight};
      const x = Math.max(left, Math.min(rect.left + rect.width / 2 - size.width / 2, left + availableWidth - size.width));
      const preferredTop = useAbove ? rect.top - size.height - 10 : rect.bottom + 10;
      return {...size, x, y:Math.max(top, Math.min(preferredTop, top + availableHeight - size.height)), useAbove};
    };
    let tip = place(leftEdge, topEdge, width, height);
    const close = mark.closest('[role="dialog"]')?.querySelector('.auto-modal-close, .message-close');
    if (close) {
      const control = close.getBoundingClientRect();
      if (tip.x < control.right && tip.x + tip.width > control.left &&
          tip.y < control.bottom && tip.y + tip.height > control.top) {
        // Prefer moving beside the close control: moving below it could cover
        // the next marker. Reflow long comments only when they collide.
        const leftRoom = control.left - 8 - leftEdge;
        const rightRoom = leftEdge + width - control.right - 8;
        if (Math.max(leftRoom, rightRoom) >= Math.min(160, width)) {
          tip = leftRoom >= rightRoom ? place(leftEdge, topEdge, leftRoom, height)
            : place(control.right + 8, topEdge, rightRoom, height);
        } else {
          const safeTop = Math.min(topEdge + height - 1, Math.max(topEdge, control.bottom + 8));
          tip = place(leftEdge, safeTop, width, topEdge + height - safeTop);
        }
      }
    }
    tooltip.style.left = tip.x + 'px';
    tooltip.style.top = tip.y + 'px';
    tooltip.style.transformOrigin = Math.max(0, Math.min(tip.width, rect.left + rect.width / 2 - tip.x)) + 'px ' + (tip.useAbove ? 'bottom' : 'top');
    tooltip.style.visibility = '';
  }
  bind(mark) {
    mark.tabIndex = 0;
    mark.setAttribute('aria-controls', this.tooltip.id); mark.setAttribute('aria-expanded', 'false');
    mark.addEventListener('pointerenter', event => {if (event.pointerType === 'mouse') this.show(mark);});
    mark.addEventListener('pointerleave', event => {if (event.pointerType === 'mouse') this.scheduleHide();});
    mark.addEventListener('focus', () => this.show(mark));
    mark.addEventListener('blur', () => this.scheduleHide());
    let closeOnClick = false;
    mark.addEventListener('pointerdown', () => {closeOnClick = !this.tooltip.hidden && this.target === mark;});
    mark.addEventListener('click', () => {
      if (closeOnClick) this.hide(); else this.show(mark);
      closeOnClick = false;
    });
  }
};
