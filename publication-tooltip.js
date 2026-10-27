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
    tooltip.style.width = Math.max(1, Math.min(widthCap, width)) + 'px';
    tooltip.style.maxHeight = Math.max(1, Math.min(heightCap, height * .65)) + 'px';
    tooltip.style.visibility = 'hidden'; tooltip.hidden = false;
    const visibleRects = Array.from(mark.getClientRects()).filter(rect => rect.bottom > topEdge && rect.top < topEdge + height);
    const firstRect = visibleRects[0] || mark.getBoundingClientRect();
    const rect = {left:firstRect.left, width:firstRect.width,
      top:visibleRects.length ? Math.max(topEdge, Math.min(...visibleRects.map(r => r.top))) : firstRect.top,
      bottom:visibleRects.length ? Math.min(topEdge + height, Math.max(...visibleRects.map(r => r.bottom))) : firstRect.bottom};
    const preferredHeight = tooltip.offsetHeight;
    const above = rect.top - topEdge - 10, below = topEdge + height - rect.bottom - 10;
    const useAbove = above >= preferredHeight || (below < preferredHeight && above > below);
    const room = Math.max(1, useAbove ? above : below);
    tooltip.style.maxHeight = Math.max(1, Math.min(heightCap, height * .65, room)) + 'px';
    const tip = {width:tooltip.offsetWidth, height:tooltip.offsetHeight};
    const left = Math.max(leftEdge, Math.min(rect.left + rect.width / 2 - tip.width / 2, leftEdge + width - tip.width));
    const preferredTop = useAbove ? rect.top - tip.height - 10 : rect.bottom + 10;
    tooltip.style.left = left + 'px';
    tooltip.style.top = Math.max(topEdge, Math.min(preferredTop, topEdge + height - tip.height)) + 'px';
    tooltip.style.transformOrigin = Math.max(0, Math.min(tip.width, rect.left + rect.width / 2 - left)) + 'px ' + (useAbove ? 'bottom' : 'top');
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
