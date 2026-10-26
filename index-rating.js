/* Full-corpus rating snapshot. No synthetic outlets, counters or chart points. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const ns = 'http://www.w3.org/2000/svg';
  const motion = matchMedia('(prefers-reduced-motion: reduce)');
  const mobile = () => matchMedia('(max-width: 767px)').matches;
  const desktop = () => matchMedia('(min-width: 1024px)').matches;
  const number = value => value.toLocaleString('ru-RU');
  const percent = value => value === null ? '—' : Math.ceil(value).toLocaleString('ru-RU') + '%';
  const date = value => new Date(value).toLocaleString('ru-RU', {
    timeZone: 'Europe/Moscow', day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit'
  }) + ' МСК';
  const label = level => ({red: 'Высокий показатель', yellow: 'Средний показатель', green: 'Низкий показатель'}[level] || 'Нет данных');
  const levelFor = (flagged, collected) => !collected ? null : flagged * 4 < collected ? 'green' : flagged * 2 > collected ? 'red' : 'yellow';
  const count = value => Number.isSafeInteger(value) && value >= 0;
  const node = (tag, text = '', className = '') => {
    const result = document.createElement(tag);
    result.textContent = text;
    if (className) result.className = className;
    return result;
  };

  // Short fictional examples; highlighted wording does not imply a factual verdict.
  const HERO_EXAMPLES = [
    ['Экономика ', ['рухнула'], ' из-за ', ['бездарного'], ' управления государством'],
    ['Страну ждёт ', ['катастрофа'], ', если не принять меры ', ['срочно'], ''],
    ['Власти ', ['скрывают'], ' истинные масштабы ', ['кризиса'], ''],
    ['Рынок ', ['обвалился'], ' после ', ['провального'], ' решения'],
    ['Реформа ', ['уничтожит'], ' будущее ', ['целого поколения'], ''],
    ['Ситуация ', ['вышла из-под контроля'], '. Действовать нужно ', ['немедленно'], ''],
    [['Все знают'], ', что чиновники ', ['обманывают'], ' население'],
    ['Региону грозит ', ['полный коллапс'], ', предупреждают ', ['эксперты'], ''],
    ['Это ', ['последний шанс'], ' остановить ', ['надвигающийся кризис'], ''],
    ['Решение властей приведёт к ', ['необратимым'], ' последствиям']
  ];

  // Short interpretive names, not verified assessments of published articles.
  // Order follows the highlighted fragments in each fictional sample.
  const HERO_EXPLANATIONS = [
    ['Катастрофизация', 'Оценочная лексика'],
    ['Нагнетание тревоги', 'Маркер срочности'],
    ['Обвинительная формулировка', 'Тревожная лексика'],
    ['Драматизация события', 'Оценочная лексика'],
    ['Категоричное утверждение', 'Обобщение'],
    ['Катастрофизация', 'Маркер срочности'],
    ['Бездоказательное обобщение', 'Обвинительная оценка'],
    ['Катастрофизация', 'Неуточнённый источник'],
    ['Давление срочностью', 'Тревожный прогноз'],
    ['Категоричный прогноз']
  ];
  let heroCalloutTargets = [];
  function positionHeroCallout(callout, mark, preference) {
    const title = $('heroExampleText');
    const stage = title?.parentElement;
    if (!stage || !callout.isConnected || !mark.isConnected) return;
    const area = stage.getBoundingClientRect();
    const headline = title.getBoundingClientRect();
    const source = mark.getBoundingClientRect();
    const bubble = callout.getBoundingClientRect();
    // The desktop homepage is scaled via CSS transform (typically 0.8x).
    // getBoundingClientRect() returns visual pixels, but style.left/top use
    // unscaled layout pixels. Convert before positioning callouts.
    const sx = area.width / (stage.offsetWidth || area.width) || 1;
    const sy = area.height / (stage.offsetHeight || area.height) || 1;
    const stageWidth = stage.offsetWidth;
    const stageHeight = stage.offsetHeight;
    const bubbleWidth = bubble.width / sx;
    const bubbleHeight = bubble.height / sy;
    // Two reserved annotation lanes: ABOVE THE ENTIRE TITLE and BELOW IT.
    const middle = (source.left + source.width / 2 - area.left) / sx;
    const left = Math.max(6, Math.min(middle - bubbleWidth / 2,
      stageWidth - bubbleWidth - 6));
    const titleTop = (headline.top - area.top) / sy;
    const titleBottom = (headline.bottom - area.top) / sy;
    const placeAbove = preference === 'above';
    const top = placeAbove
      ? titleTop - bubbleHeight - 18
      : titleBottom + 18;
    const y = Math.max(3, Math.min(top, stageHeight - bubbleHeight - 3));
    callout.style.left = Math.round(left) + 'px';
    callout.style.top = Math.round(y) + 'px';
    callout.style.setProperty('--callout-pointer-x',
      Math.round(Math.max(12, Math.min(bubbleWidth - 12, middle - left))) + 'px');
    callout.classList.toggle('is-above', placeAbove);
    callout.classList.toggle('is-below', !placeAbove);
  }
  function positionHeroCallouts() {
    for (const {callout,mark,preference} of heroCalloutTargets) {
      positionHeroCallout(callout,mark,preference);
    }
  }
  function clearHeroCallouts() {
    heroCalloutTargets = [];
    $('heroExampleCallouts')?.replaceChildren();
  }
  function showHeroCallout(mark, caption, index, immediate = false) {
    const layer = $('heroExampleCallouts');
    if (!layer) return;
    const bubble = node('span', caption, 'hero-example-callout');
    bubble.dataset.triggerIndex = String(index);
    bubble.setAttribute('aria-hidden', 'true');
    const preference = index % 2 === 0 ? 'above' : 'below';
    layer.append(bubble);
    heroCalloutTargets.push({callout:bubble,mark,preference});
    positionHeroCallout(bubble,mark,preference);
    if (immediate) bubble.classList.add('is-visible');
    else requestAnimationFrame(() => { if (bubble.isConnected) bubble.classList.add('is-visible'); });
  }
  let heroExampleIndex = 0, heroExampleTimer = null, heroExampleRun = 0;
  const exampleFullText = parts => parts.map(p => Array.isArray(p) ? p[0] : p).join('');
  function stopHeroExamples() {
    ++heroExampleRun; clearTimeout(heroExampleTimer); heroExampleTimer = null;
    clearHeroCallouts();
  }
  function scheduleHeroExample(callback, delay, run) {
    heroExampleTimer = setTimeout(() => {
      if (run === heroExampleRun && !document.hidden && !motion.matches) callback();
    }, delay);
  }
  function renderHeroExample(index, instant = false) {
    const target = $('heroExampleText');
    if (!target) return;
    const parts = HERO_EXAMPLES[index];
    target.replaceChildren();
    clearHeroCallouts();
    $('heroExampleCallouts')?.classList.remove('is-exiting');
    target.classList.remove('is-exiting');
    target.dataset.exampleIndex = String(index);
    target.dataset.exampleTotal = String(HERO_EXAMPLES.length);
    target.setAttribute('aria-label', exampleFullText(parts));

    // Reserve the full paragraph's layout before typing a single character.
    // Invisible letters take up space, so the first line and hero height stay
    // fixed even as subsequent lines are revealed.
    const letters = [], marks = [];
    const explanations = HERO_EXPLANATIONS[index];
    const appendWords = (parent, content) => {
      for (const chunk of content.split(/(\s+)/u)) {
        if (!chunk) continue;
        if (/^\s+$/u.test(chunk)) {
          parent.append(document.createTextNode(chunk));
          continue;
        }
        const word = node('span', '', 'hero-example-word');
        for (const character of Array.from(chunk)) {
          const letter = node('span', character, 'hero-example-char');
          word.append(letter);
          letters.push(letter);
        }
        parent.append(word);
      }
    };
    for (const piece of parts) {
      const emph = Array.isArray(piece);
      let content = emph ? piece[0] : piece;
      // Punctuation immediately following a highlighted phrase is a separate
      // data segment. Keep it on the SAME line as the phrase, without putting
      // the punctuation inside its highlighted mark. Applies to all examples.
      if (!emph) {
        const leadingPunctuation = content.match(/^[.,!?;:…]+/u);
        if (leadingPunctuation && target.lastElementChild) {
          const previous = target.lastElementChild;
          const joined = node('span', '', 'hero-example-joined');
          target.replaceChild(joined, previous);
          joined.append(previous);
          const punctuation = node('span', '', 'hero-example-punctuation');
          for (const character of Array.from(leadingPunctuation[0])) {
            const letter = node('span', character, 'hero-example-char');
            punctuation.append(letter);
            letters.push(letter);
          }
          joined.append(punctuation);
          content = content.slice(leadingPunctuation[0].length);
        }
      }
      if (!content) continue;
      const part = node(emph ? 'mark' : 'span', '', emph ? 'hero-trigger' : 'hero-example-segment');
      appendWords(part, content);
      target.append(part);
      if (emph) {
        part.title = explanations[marks.length] || 'Пример возможного маркера';
        part.setAttribute('aria-label', part.title + ': ' + (emph ? piece[0] : piece));
        marks.push(part);
      }
    }
    // Keep the stylesheet's large typography rather than shrinking the
    // message to one line. Reposition labels once web fonts have loaded.
    if (document.fonts?.ready) {
      document.fonts.ready.then(() => {
        if (target.dataset.exampleIndex !== String(index)) return;
        positionHeroCallouts();
      });
    }
    if (instant) {
      letters.forEach(ch => ch.classList.add('is-typed'));
      marks.forEach((mark, i) => {
        mark.classList.add('is-highlighted');
        showHeroCallout(mark, explanations[i], i, true);
      });
      target.dataset.phase = 'highlighted';
      return;
    }
    const run = heroExampleRun;
    let nextLetter = 0;
    target.dataset.phase = 'typing';
    const typeNext = () => {
      if (run !== heroExampleRun) return;
      if (nextLetter < letters.length) {
        letters[nextLetter++].classList.add('is-typed');
        scheduleHeroExample(typeNext, 28, run);
        return;
      }
      target.dataset.phase = 'highlighting';
      let nextMark = 0;
      const highlightNext = () => {
        if (run !== heroExampleRun) return;
        if (nextMark < marks.length) {
          const index = nextMark++;
          const mark = marks[index];
          mark.classList.add('is-highlighted');
          scheduleHeroExample(() => {
            showHeroCallout(mark, explanations[index], index);
            scheduleHeroExample(highlightNext, 820, run);
          }, 390, run);
          return;
        }
        // Hold the complete annotated text long enough to read both labels.
        target.dataset.phase = 'highlighted';
        scheduleHeroExample(() => {
          target.classList.add('is-exiting');
          $('heroExampleCallouts')?.classList.add('is-exiting');
          scheduleHeroExample(() => {
            heroExampleIndex = (heroExampleIndex + 1) % HERO_EXAMPLES.length;
            renderHeroExample(heroExampleIndex);
          }, 460, run);
        }, 4700, run);
      };
      scheduleHeroExample(highlightNext, 380, run);
    };
    scheduleHeroExample(typeNext, 120, run);
  }
  function startHeroExamples() {
    stopHeroExamples();
    renderHeroExample(heroExampleIndex, motion.matches || document.hidden);
  }

  let report = null, media = [], offset = 0, active = 0, cycle = null, loading = false, loadError = false;
  let counterAnimation = null, previousTotal = null;

  function setTotal(target) {
    const desktopCount = $('dailyCounterValue'), mobileCount = $('dailyCounterMobile');
    const final = number(target);
    desktopCount.dataset.digits = String(Math.min(5, String(target).length));
    mobileCount.dataset.digits = String(Math.min(5, String(target).length));
    if (counterAnimation !== null) cancelAnimationFrame(counterAnimation);
    counterAnimation = null;
    if (motion.matches || document.hidden || previousTotal === target) {
      desktopCount.textContent = mobileCount.textContent = final;
      previousTotal = target;
      return;
    }
    const start = previousTotal === null ? 0 : previousTotal;
    previousTotal = target;
    const began = performance.now(), duration = 1100;
    const tick = now => {
      const t = Math.min(1, (now - began) / duration);
      const eased = 1 - Math.pow(1 - t, 4);
      const display = number(Math.round(start + (target - start) * eased));
      desktopCount.textContent = mobileCount.textContent = display;
      if (t < 1) counterAnimation = requestAnimationFrame(tick);
      else { desktopCount.textContent = mobileCount.textContent = final; counterAnimation = null; }
    };
    counterAnimation = requestAnimationFrame(tick);
  }
  let currentModal = null, modalTrigger = null, oldOverflow = '', inertElements = [];

  function validate(data) {
    if (data?.schema_version !== 'rating-snapshot-1.0' || !Array.isArray(data.publishers) ||
        !Number.isFinite(Date.parse(data.generated_at)) || data.window?.hours !== 24 ||
        !Number.isFinite(Date.parse(data.window.start_at)) || !Number.isFinite(Date.parse(data.window.end_at)) ||
        Date.parse(data.window.end_at) - Date.parse(data.window.start_at) !== 86400000 ||
        data.chart?.kind !== 'cumulative_share' || data.publishers.length > 200) throw Error('format');
    const ids = new Set();
    const sums = {collected: 0, analyzed: 0, flagged: 0};
    for (const row of data.publishers) {
      if (!/^[a-z][a-z0-9_]{0,63}$/.test(row.id) || ids.has(row.id) ||
          typeof row.name !== 'string' || !row.name.trim() || row.name.length > 300 ||
          !Array.isArray(row.platforms) || !row.platforms.every(value => ['website', 'telegram'].includes(value)) ||
          !Array.isArray(row.sources) || !Array.isArray(row.series) || row.series.length !== 24 ||
          ![row.collected, row.analyzed, row.flagged].every(count) || row.flagged > row.analyzed || row.analyzed > row.collected) throw Error('outlet');
      ids.add(row.id);
      const expected = row.collected && row.analyzed === row.collected ? 100 * row.flagged / row.collected : null;
      if ((expected === null && (row.score_percent !== null || row.level !== null)) ||
          (expected !== null && (!Number.isFinite(row.score_percent) || Math.abs(row.score_percent - expected) > 0.00001 ||
          row.level !== levelFor(row.flagged, row.collected)))) throw Error('ratio');
      const running = {collected: 0, analyzed: 0, flagged: 0};
      for (const [index, point] of row.series.entries()) {
        if (![point.collected, point.analyzed, point.flagged].every(count) ||
            point.flagged > point.analyzed || point.analyzed > point.collected ||
            Date.parse(point.end_at) !== Date.parse(data.window.start_at) + (index + 1) * 3600000) throw Error('chart');
        for (const key of Object.keys(running)) {
          running[key] += point[key];
          if (point['cumulative_' + key] !== running[key]) throw Error('cumulative');
        }
        const score = running.collected && running.analyzed === running.collected ? 100 * running.flagged / running.collected : null;
        if (score === null ? point.score_percent !== null : !Number.isFinite(point.score_percent) || Math.abs(point.score_percent - score) > 0.00001) throw Error('chart ratio');
      }
      for (const key of Object.keys(sums)) {
        if (running[key] !== row[key]) throw Error('chart totals');
        sums[key] += row[key];
      }
    }
    if (Object.keys(sums).some(key => data.totals?.[key] !== sums[key])) throw Error('totals');
    return data;
  }

  function statusLabels(id) {
    const status = window.MediaPublisherStatuses?.[id];
    return [status?.foreignAgent && 'иноагент', status?.undesirable && 'нежелательная организация'].filter(Boolean);
  }


  // Use supplied publisher logos for BBC and RIA. The files are packaged
  // with the static site, so they do not depend on a third-party favicon API.
  const publisherLogoFiles = Object.freeze({
    bbc: '/bbc-publisher.webp',
    ria: '/ria-publisher.webp'
  });
  // Domains belong to the monitored publishers (not to arbitrary article URLs).
  // Favicons are publisher-provided brand marks; Telegram-only outlets use
  // their public channel avatar. The lettermark remains as an offline fallback.
  const publisherLogoDomains = Object.freeze({
    rt: 'russiatoday.ru',
    tass: 'tass.ru',
    ria: 'ria.ru',
    interfax: 'interfax.ru',
    kommersant: 'kommersant.ru',
    vedomosti: 'vedomosti.ru',
    rbc: 'rbc.ru',
    izvestia: 'iz.ru',
    rg: 'rg.ru',
    lenta: 'lenta.ru',
    meduza: 'meduza.io',
    novayagazeta: 'novayagazeta.eu',
    fontanka: 'fontanka.ru',
    currenttime: 'currenttime.tv',
    dw: 'dw.com',
    bbc: 'bbc.com',
    aif: 'aif.ru',
    inosmi: 'inosmi.ru',
    mediazona: 'zona.media'
  });
  const channelLogoHandles = Object.freeze({
    oldlentach: 'oldlentach',
    smotri: 'smotri_media'
  });

  function publisherLogo(row, initials) {
    const icon = node('span', '', 'logo-icon');
    icon.setAttribute('aria-hidden', 'true');
    icon.append(node('span', initials, 'logo-fallback'));
    const localLogo = publisherLogoFiles[row.id];
    const domain = publisherLogoDomains[row.id];
    const channel = channelLogoHandles[row.id];
    if (!localLogo && !domain && !channel) return icon;

    const image = node('img', '', 'logo-image');
    image.alt = '';
    image.loading = 'lazy';
    image.decoding = 'async';
    image.referrerPolicy = 'no-referrer';
    image.src = localLogo || (domain
      ? 'https://www.google.com/s2/favicons?domain=' + encodeURIComponent(domain) + '&sz=128'
      : 'https://unavatar.io/telegram/' + encodeURIComponent(channel) + '?fallback=false');
    image.addEventListener('load', () => {
      // Missing Google favicon often resolves to a generic 16px globe.
      if (image.naturalWidth <= 16) image.remove();
      else icon.classList.add('has-logo');
    });
    image.addEventListener('error', () => image.remove());
    icon.prepend(image);
    return icon;
  }

  function platformText(row) {
    return row.platforms.map(platform => platform === 'telegram' ? 'Telegram' : 'Сайт').join(' · ');
  }

  function healthText(row) {
    const errors = row.sources.filter(source => ['error', 'partial'].includes(source.state)).length;
    const stale = row.sources.filter(source => source.state === 'stale').length;
    return 'Ограниченная выборка' + (errors ? ` · ошибок сбора: ${errors}` : '') + (stale ? ` · без свежих данных: ${stale}` : '');
  }

  function makeGraph(row, width = 200, height = 36) {
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
    svg.setAttribute('preserveAspectRatio', 'none');
    svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', `${row.name}. Накопительная доля публикаций с признаками за 24 часа, шкала 0–100%. Итог: ${percent(row.score_percent)}.`);
    const color = {red: '#ef4444', yellow: '#eab308', green: '#22c55e'}[row.level] || '#acbdc8';
    const descriptions = [], paths = [];
    let path = '', previous = false;
    row.series.forEach((point, index) => {
      if (point.score_percent === null) {
        if (path) paths.push(path);
        path = ''; previous = false; return;
      }
      const x = 4 + index * (width - 8) / 23;
      const y = 4 + (100 - point.score_percent) * (height - 8) / 100;
      path += previous ? ` H${x.toFixed(2)} V${y.toFixed(2)}` : `M${x.toFixed(2)},${y.toFixed(2)}`;
      previous = true;
      const dot = document.createElementNS(ns, 'circle');
      dot.setAttribute('cx', x.toFixed(2)); dot.setAttribute('cy', y.toFixed(2));
      dot.setAttribute('r', '1.5'); dot.setAttribute('fill', color);
      dot.dataset.score = String(point.score_percent);
      dot.dataset.collected = String(point.cumulative_collected);
      dot.dataset.flagged = String(point.cumulative_flagged);
      dot.dataset.endAt = point.end_at;
      const title = document.createElementNS(ns, 'title');
      title.textContent = `${date(point.end_at)}: ${point.cumulative_flagged} из ${point.cumulative_collected}, ${percent(point.score_percent)}`;
      descriptions.push(title.textContent);
      dot.append(title); svg.append(dot);
    });
    if (path) paths.push(path);
    for (const coordinates of paths) {
      const line = document.createElementNS(ns, 'path');
      line.setAttribute('d', coordinates); line.setAttribute('fill', 'none');
      line.setAttribute('stroke', color); line.setAttribute('stroke-width', '1.5');
      line.setAttribute('stroke-linejoin', 'round'); svg.prepend(line);
    }
    const description = document.createElementNS(ns, 'desc');
    description.textContent = descriptions.join('; '); svg.prepend(description);
    return descriptions.length ? svg : node('span', 'Нет точек для графика', 'rating-graph-empty');
  }


  // Binary signal by Moscow clock hour. A peak means >= 1 flagged publication.
  // The 24 rolling-hour buckets contain each local clock hour once.
  function makeCardGraph(row) {
    if (row.score_percent === null || row.collected === 0) {
      return node('span', 'Нет данных за последние 24 часа', 'rating-graph-empty');
    }
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', '0 0 340 66');
    svg.setAttribute('preserveAspectRatio', 'none');
    svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label',
      row.name + '. Часы Москвы от 00 до 24. Подъём линии означает, что за час найдена хотя бы одна публикация с признаками. '
      + 'Всего за 24 часа: ' + row.flagged + '.');
    const shape = (tag, attrs, value) => {
      const element = document.createElementNS(ns, tag);
      Object.entries(attrs).forEach(([key, attr]) => element.setAttribute(key, String(attr)));
      if (value !== undefined) element.textContent = value;
      return element;
    };
    const color = ({red: '#f87171', yellow: '#efbd42', green: '#36d399'}[row.level] || '#65bee9');
    const left = 16, right = 332, top = 5, bottom = 41;
    const xAt = hour => left + hour * (right - left) / 24;
    // The end hour marks the next bucket; subtract 1 to get the Moscow start hour.
    const byHour = Array(24);
    for (const point of row.series) {
      const hour = (new Date(point.end_at).getUTCHours() + 2) % 24;
      byHour[hour] = point;
    }
    const id = 'rating-signal-fill-' + row.id;
    const defs = shape('defs', {});
    const gradient = shape('linearGradient', {id, x1:'0%', y1:'0%', x2:'0%', y2:'100%'});
    gradient.append(
      shape('stop', {offset:'0%', 'stop-color':color, 'stop-opacity':'.23'}),
      shape('stop', {offset:'100%', 'stop-color':color, 'stop-opacity':'.015'})
    );
    defs.append(gradient);
    svg.append(defs);
    // A binary activity track without vertical tick labels; clock hours are preserved.
    svg.append(shape('line', {x1:left,y1:top,x2:right,y2:top,stroke:'#8caec3',
      'stroke-opacity':'.20','stroke-dasharray':'3 5'}));
    svg.append(shape('line', {x1:left,y1:bottom,x2:right,y2:bottom,stroke:'#7295ab',
      'stroke-opacity':'.44'}));
    for (const hour of [0,6,12,18,24]) {
      const x = xAt(hour);
      if (hour > 0 && hour < 24) svg.append(shape('line', {x1:x,y1:top,x2:x,y2:bottom,
        stroke:'#7f9bb1','stroke-opacity':'.10','stroke-dasharray':'2 5'}));
      svg.append(shape('text', {x,y:60,'text-anchor':hour===0?'start':hour===24?'end':'middle',
        fill:'#9eb4c5','font-family':'Inter, sans-serif','font-size':'10'},
        String(hour).padStart(2, '0')));
    }
    for (let hour=0; hour<24; hour++) {
      const point=byHour[hour];
      const flagged=point?.flagged || 0;
      const x0=xAt(hour), x1=xAt(hour+1), middle=(x0+x1)/2;
      if (flagged) {
        // One rounded pulse per active hour; height means presence, not volume.
        const d='M'+x0+' '+bottom+' C'+(x0+2)+' '+bottom+', '+(x0+2)+' '+top+', '+middle+' '+top
          +' C'+(x1-2)+' '+top+', '+(x1-2)+' '+bottom+', '+x1+' '+bottom;
        svg.append(shape('path', {d:d+' L'+x0+' '+bottom+' Z',fill:'url(#'+id+')'}));
        svg.append(shape('path', {d,fill:'none',stroke:color,'stroke-width':'2.6',
          'stroke-linecap':'round',class:'rating-signal-peak'}));
      }
      const dot=shape('circle',{cx:middle,cy:flagged?top:bottom,r:flagged?'2.6':'1.15',
        fill:flagged?color:'#496577','fill-opacity':flagged?'1':'.55'});
      dot.dataset.hour=String(hour);
      dot.dataset.hourlyFlagged=String(flagged);
      dot.dataset.score=String(point.score_percent);
      dot.dataset.collected=String(point.cumulative_collected);
      dot.dataset.flagged=String(point.cumulative_flagged);
      dot.dataset.endAt=point.end_at;
      dot.append(shape('title',{},String(hour).padStart(2,'0')+':00–'
        +String((hour+1)%24).padStart(2,'0')+':00 МСК: '
        +flagged+' публикаций с признаками; всего '+point.collected+' публикаций за час.'));
      svg.append(dot);
    }
    return svg;
  }

  function examplesLink(row) {
    const link = node('a', 'Смотреть примеры', 'link-button');
    // The archive does not currently support publisher URL filters.
    link.href = '/archive/';
    link.setAttribute('aria-label', 'Смотреть архив публикаций');
    return link;
  }

  function drawCard(row) {
    const card = node('article', '', 'media-card');
    card.dataset.publisher = row.id;

    const header = node('div', '', 'media-card-header');
    const identity = node('div', '', 'media-logo');
    const initials = row.name.trim().split(/\s+/).map(part => part[0]).slice(0, 2).join('').toUpperCase();
    const icon = publisherLogo(row, initials);
    const names = node('div', '', 'media-identity-text');
    const name = node('div', row.name, 'media-name');
    name.title = row.name;
    names.append(name);
    const statuses = statusLabels(row.id);
    if (statuses.length) {
      const legal = node('div', '', 'rating-status-stack');
      legal.setAttribute('aria-label', 'Юридические статусы издания');
      for (const status of statuses) {
        const tag = node('span', status, 'media-status-tag');
        tag.title = status === 'иноагент'
          ? 'Издание включено в реестр иностранных агентов'
          : 'Издание имеет статус нежелательной организации';
        legal.append(tag);
      }
      names.append(legal);
    }
    identity.append(icon, names);
    header.append(identity);
    if (mobile() && media.length > 1) {
      const controls = node('div', '', 'media-card-slider-controls');
      for (const direction of [-1, 1]) {
        const back = direction === -1;
        const button = node('button', back ? '‹' : '›',
          'media-card-arrow ' + (back ? 'media-card-arrow-prev' : 'media-card-arrow-next'));
        button.type = 'button';
        button.setAttribute('aria-label', back ? 'Предыдущее СМИ' : 'Следующее СМИ');
        button.setAttribute('title', back ? 'Предыдущее СМИ' : 'Следующее СМИ');
        button.addEventListener('click', event => {
          event.stopPropagation();
          const keyboard = event.detail === 0;
          active = (active + direction + media.length) % media.length;
          renderCards();
          const replacement = $('mediaGrid').querySelector('.media-card.is-active .' +
            (back ? 'media-card-arrow-prev' : 'media-card-arrow-next'));
          if (keyboard) replacement?.focus({preventScroll:true});
          else replacement?.blur();
          restartCycle();
        });
        controls.append(button);
      }
      header.append(controls);
    }

    // The principal metric is a percentage of the collected sample, not the
    // number of flagged articles. Keep the actual numerator in accessible text.
    const score = node('div', '', 'rating-headline');
    const value = node('strong', percent(row.score_percent),
      'rating-score ' + (row.level || 'no-data') + '-score');
    const description = node('span',
      row.score_percent === null ? 'нет данных за 24 часа' : 'спорных сообщений',
      'rating-headline-label');
    score.setAttribute('aria-label', row.score_percent === null
      ? row.name + ': данных недостаточно для расчёта рейтинга'
      : row.name + ': ' + percent(row.score_percent)
        + ' собранных публикаций с признаками, ' + row.flagged
        + ' из ' + row.collected + ' публикаций за последние 24 часа');
    score.append(value, description);

    const graph = node('div', '', 'small-graph');
    graph.append(makeCardGraph(row));
    graph.tabIndex = 0;
    const footer = node('div', '', 'media-footer');
    footer.append(examplesLink(row));
    card.append(header, score, graph, footer);
    return card;
  }

  function renderCards() {
    $('mediaGrid').replaceChildren(); $('mediaDots').replaceChildren();
    $('mediaGrid').classList.toggle('is-mobile-slider', mobile());
    const count = mobile() ? media.length : Math.min(desktop() ? 3 : 2, media.length);
    for (let index = 0; index < count; index++) {
      const row = media[mobile() ? index : (offset + index) % media.length];
      const card = drawCard(row);
      card.style.setProperty('--card-order', String(index));
      if (mobile()) {
        card.classList.toggle('is-active', index === active);
        card.setAttribute('aria-hidden', String(index !== active));
        card.inert = index !== active;
      }
      $('mediaGrid').append(card);
    }
    if (mobile()) media.forEach((row, index) => {
      const dot = node('button', '', 'media-dot' + (index === active ? ' active' : ''));
      dot.type = 'button'; dot.setAttribute('aria-label', 'Показать ' + row.name);
      dot.setAttribute('aria-pressed', String(index === active));
      dot.addEventListener('click', event => {
        const keyboard = event.detail === 0;
        active = index;
        renderCards();
        const replacement = $('mediaDots').children[index];
        // Keep auto-rotation available after touch activation, but pause on
        // keyboard focus so assistive-navigation users can read the card.
        if (keyboard) replacement?.focus({preventScroll: true});
        else replacement?.blur();
        restartCycle();
      });
      $('mediaDots').append(dot);
    });
  }

  function stopCycle() { clearInterval(cycle); cycle = null; }
  function restartCycle() {
    stopCycle();
    if (motion.matches || currentModal || document.hidden || media.length < 2 ||
        (!mobile() && media.length <= (desktop() ? 3 : 2)) ||
        $('mediaGrid').contains(document.activeElement) || $('mediaDots').contains(document.activeElement)) return;
    cycle = setInterval(() => {
      if (mobile()) active = (active + 1) % media.length;
      else offset = (offset + (desktop() ? 3 : 2)) % media.length;
      renderCards();
    }, mobile() ? 5200 : 8500);
  }

  function filteredMedia() {
    const query = $('modalSearch').value.trim().toLocaleLowerCase('ru-RU');
    const sort = $('modalSort').value;
    return media.filter(row => row.name.toLocaleLowerCase('ru-RU').includes(query)).sort((a, b) => {
      if (sort === 'name-asc') return a.name.localeCompare(b.name, 'ru');
      if (sort === 'name-desc') return b.name.localeCompare(a.name, 'ru');
      if (a.score_percent === null || b.score_percent === null) return Number(a.score_percent === null) - Number(b.score_percent === null) || a.name.localeCompare(b.name, 'ru');
      const ascending = ['rating-asc', 'level-green'].includes(sort);
      return (ascending ? a.score_percent - b.score_percent : b.score_percent - a.score_percent) || a.name.localeCompare(b.name, 'ru');
    });
  }

  function renderFullList() {
    const container = $('fullListContainer'); container.replaceChildren();
    const rows = filteredMedia();
    if (!rows.length) { container.append(node('p', report ? 'Ничего не найдено' : 'Данные рейтинга пока недоступны.', 'modal-empty')); return; }
    for (const item of rows) {
      const row = node('div', '', 'full-list-row'); row.dataset.publisher = item.id;
      const name = node('div', '', 'fli-name');
      name.append(node('div', item.name, 'title'),
                  node('div', `${platformText(item)} · ${item.flagged} из ${item.collected} с признаками · проверено ${item.analyzed}` +
                    (statusLabels(item.id).length ? ' · ' + statusLabels(item.id).join(', ') : ''), 'type'));
      const graph = node('div', '', 'fli-graph'); graph.append(makeGraph(item, 120, 28)); graph.tabIndex = 0;
      row.append(name, graph, node('div', percent(item.score_percent), 'fli-rating ' + (item.level || 'no-data')),
                 node('div', item.rating_state === 'analysis_pending' ? 'Анализ не завершён' : label(item.level), 'fli-badge ' + (item.level || 'no-data')));
      container.append(row);
    }
  }

  function closeModal(restore = true) {
    if (!currentModal) return;
    currentModal.classList.remove('open'); currentModal.setAttribute('aria-hidden', 'true');
    $('appealLink').setAttribute('aria-expanded', 'false');
    document.body.style.overflow = oldOverflow;
    for (const [element, previous] of inertElements) element.inert = previous;
    inertElements = []; currentModal = null;
    if (restore && modalTrigger?.isConnected) modalTrigger.focus();
    modalTrigger = null; restartCycle();
  }

  function openModal(id, trigger) {
    closeModal(false); stopCycle();
    currentModal = $(id); modalTrigger = trigger; oldOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    for (const element of document.body.children) {
      if (element !== currentModal && !['SCRIPT', 'STYLE', 'LINK'].includes(element.tagName)) {
        inertElements.push([element, element.inert]); element.inert = true;
      }
    }
    currentModal.classList.add('open'); currentModal.setAttribute('aria-hidden', 'false');
    if (id === 'fullListModal') {
      $('modalSearch').value = ''; $('modalSort').value = 'rating-desc'; renderFullList(); $('modalSearch').focus();
    } else {
      $('appealLink').setAttribute('aria-expanded', 'true'); $('appealPublisher').focus();
    }
  }

  function updateStatus() {
    if (!report) return;
    // The public rating header is intentionally clean. Show a notice only
    // when reloading has actually failed; sample timestamps remain in data.
    const warning = loadError ? 'Не удалось обновить рейтинг. Показана последняя доступная выборка.' : '';
    $('ratingStatus').hidden = !warning;
    $('ratingStatus').classList.toggle('is-stale', Boolean(warning));
    $('ratingStatus').textContent = warning;
  }

  async function loadRating() {
    if (loading) return;
    loading = true;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch('data/rating.json', {cache: 'no-store', signal: controller.signal});
      if (!response.ok) throw Error('HTTP ' + response.status);
      const next = validate(await response.json());
      const selected = media[active]?.id;
      report = next; media = next.publishers; loadError = false;
      active = Math.max(0, media.findIndex(row => row.id === selected)); offset = 0;
      setTotal(report.totals.flagged);
      $('ratingRetry').hidden = true; updateStatus(); renderCards(); restartCycle();
      $('appealPublishers').replaceChildren(...media.map(row => {
        const option = node('option'); option.value = row.name; return option;
      }));
      if (currentModal?.id === 'fullListModal') renderFullList();
    } catch (_) {
      loadError = true; $('ratingRetry').hidden = false;
      if (report) updateStatus();
      else $('ratingStatus').textContent = 'Рейтинг пока недоступен. Повторите загрузку после обновления данных.';
    } finally { clearTimeout(timer); loading = false; }
  }

  document.querySelectorAll('.show-full-list-trigger').forEach(button => button.addEventListener('click', () => openModal('fullListModal', button)));
  $('appealLink').addEventListener('click', event => { event.preventDefault(); openModal('appealModal', event.currentTarget); });
  $('fullListCloseBtn').addEventListener('click', () => closeModal());
  $('appealCloseBtn').addEventListener('click', () => closeModal());
  for (const id of ['fullListModal', 'appealModal']) $(id).addEventListener('click', event => {
    if (event.target === $(id)) closeModal();
  });
  $('modalSearch').addEventListener('input', renderFullList); $('modalSort').addEventListener('change', renderFullList);
  $('ratingRetry').addEventListener('click', loadRating);
  $('appealForm').addEventListener('input', () => {
    $('appealUrl').setCustomValidity(''); $('appealPublisher').setCustomValidity('');
    $('appealExplanation').setCustomValidity(''); $('appealStatus').textContent = '';
  });
  $('appealForm').addEventListener('reset', () => {
    for (const id of ['appealPublisher', 'appealUrl', 'appealExplanation']) $(id).setCustomValidity('');
    $('appealStatus').textContent = '';
  });
  $('appealForm').addEventListener('submit', event => {
    event.preventDefault();
    const publisher = $('appealPublisher').value.trim(), url = $('appealUrl').value.trim(), explanation = $('appealExplanation').value.trim();
    if (!publisher) $('appealPublisher').setCustomValidity('Укажите СМИ.');
    if (explanation.length < 10) $('appealExplanation').setCustomValidity('Объясните ошибку хотя бы в 10 символах.');
    if (url) {
      try { if (!['https:', 'http:'].includes(new URL(url).protocol)) throw Error(); }
      catch (_) { $('appealUrl').setCustomValidity('Укажите ссылку, начинающуюся с https:// или http://.'); }
    }
    if (!$('appealForm').reportValidity()) return;
    const text = `Апелляция — МЕДИА.СТРАЖ\nСМИ: ${publisher}\nСсылка: ${url || 'Не указана'}\n\nГде ошибся алгоритм и почему:\n${explanation}\n`;
    const blob = URL.createObjectURL(new Blob([text], {type: 'text/plain;charset=utf-8'}));
    const link = node('a'); link.href = blob; link.download = 'media-strazh-appeal.txt'; link.click();
    setTimeout(() => URL.revokeObjectURL(blob), 10000);
    $('appealStatus').textContent = 'Текст апелляции подготовлен для сохранения на устройство. Отправка на почту пока не подключена.';
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
      closeModal(); $('navLinks')?.classList.remove('open'); $('burgerBtn')?.setAttribute('aria-expanded', 'false');
    }
    if (event.key !== 'Tab' || !currentModal) return;
    const controls = [...currentModal.querySelectorAll('a[href],button,input,select,textarea,[tabindex="0"]')].filter(control => !control.disabled && control.getClientRects().length);
    const first = controls[0], last = controls[controls.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  });
  const burger = $('burgerBtn'), navigation = $('navLinks');
  burger?.addEventListener('click', () => burger.setAttribute('aria-expanded', String(navigation.classList.toggle('open'))));
  navigation?.querySelectorAll('a').forEach(link => link.addEventListener('click', () => { navigation.classList.remove('open'); burger.setAttribute('aria-expanded', 'false'); }));
  document.addEventListener('click', event => {
    if (burger && !navigation.contains(event.target) && !burger.contains(event.target)) {
      navigation.classList.remove('open'); burger.setAttribute('aria-expanded', 'false');
    }
  });
  $('mediaGrid').addEventListener('pointerenter', stopCycle); $('mediaGrid').addEventListener('pointerleave', restartCycle);
  $('mediaGrid').addEventListener('focusin', stopCycle); $('mediaGrid').addEventListener('focusout', () => setTimeout(restartCycle, 0));
  document.addEventListener('visibilitychange', () => {
    restartCycle();
    if (!document.hidden) loadRating();
    startHeroExamples();
  });
  motion.addEventListener('change', () => { restartCycle(); startHeroExamples(); });
  let resize = null;
  window.addEventListener('resize', () => {
    clearTimeout(resize);
    resize = setTimeout(() => {
      renderCards();
      restartCycle();
      positionHeroCallouts();
    }, 150);
  });
  setInterval(() => { if (!document.hidden) loadRating(); }, 300000);
  setInterval(updateStatus, 60000);
  renderHeroExample(heroExampleIndex);
  startHeroExamples();
  loadRating();
})();
