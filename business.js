/* МЕДИА.СТРАЖ PRO / Бизнес: интерактивный прототип без внешних данных и API. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const samples = {
    medtech: {
      trends: [
        {title:'Импортозамещение в медтехнике', count:98, growth:'+164%', detail:'Редакции обсуждают отечественные компоненты, регистрацию и закупки медицинских изделий.'},
        {title:'Сервис медицинского оборудования', count:76, growth:'+112%', detail:'В центре внимания — доступность ремонта, запасных частей и сопровождения техники.'},
        {title:'ИИ и автоматизация диагностики', count:64, growth:'+87%', detail:'Развиваются дискуссии о внедрении технологий и практических ограничениях.'}
      ],
      opportunities: [
        {kind:'КОММЕНТАРИЙ ЭКСПЕРТА', title:'Прокомментировать изменения рынка медтехники', detail:'Расскажите, какие изменения видит ваша компания на практике. Подойдут экспертная колонка или комментарий, если есть подтверждённая фактура.'},
        {kind:'КЕЙС / КОЛОНКА', title:'Показать опыт эксплуатации и сервиса', detail:'Подготовьте конкретный кейс: задача, решение, результат и подтверждающие показатели, которые можно опубликовать.'},
        {kind:'ИССЛЕДОВАНИЕ', title:'Собрать собственные данные об отрасли', detail:'Проведите небольшой опрос специалистов и предложите редакциям результаты с прозрачной методикой.'},
        {kind:'ПРАКТИЧЕСКИЙ РАЗБОР', title:'Объяснить внедрение новых технологий', detail:'Предложите материал о применении новых решений с понятными ограничениями и проверяемыми примерами.'}
      ]
    },
    industry: {
      trends: [
        {title:'Локализация производств', count:132, growth:'+73%', detail:'На первый план выходят цепочки поставок и российские производственные мощности.'},
        {title:'Промышленная автоматизация', count:83, growth:'+56%', detail:'Интерес вызывают роботизация, датчики и повышение эффективности процессов.'},
        {title:'Кадры для производства', count:61, growth:'+41%', detail:'СМИ обсуждают подготовку инженеров и специалистов технических профессий.'}
      ],
      opportunities: [
        {kind:'КОММЕНТАРИЙ ЭКСПЕРТА', title:'Оценить изменения производственных цепочек', detail:'Подготовьте экспертный комментарий о реальных сложностях, возможностях и подтверждаемых результатах.'},
        {kind:'КЕЙС', title:'Показать результат внедрения технологии', detail:'Подойдёт кейс с исходной задачей, описанием внедрения и измеримыми итогами.'},
        {kind:'ИССЛЕДОВАНИЕ', title:'Собрать данные о спросе на специалистов', detail:'Уместны результаты собственного опроса или аналитики вакансий с описанной методикой.'},
        {kind:'ОБЗОР', title:'Объяснить экономику сервисного обслуживания', detail:'Расскажите об изменениях затрат и сроков обслуживания без неподтверждённых обобщений.'}
      ]
    },
    hospitality: {
      trends: [
        {title:'Короткие городские поездки', count:91, growth:'+68%', detail:'СМИ обсуждают поездки на выходные, культурные события и новые сценарии отдыха.'},
        {title:'Путешествия с питомцами', count:54, growth:'+49%', detail:'Растёт интерес к pet-friendly сервисам и организации поездок с животными.'},
        {title:'Персонализация гостиничного сервиса', count:46, growth:'+35%', detail:'Обсуждаются цифровые инструменты и новые способы заботы о гостях.'}
      ],
      opportunities: [
        {kind:'ЭКСПЕРТНЫЙ КОММЕНТАРИЙ', title:'Рассказать о новых привычках путешественников', detail:'Поделитесь наблюдениями за предпочтениями гостей, подкрепив их собственными данными.'},
        {kind:'ИСТОРИЯ / КЕЙС', title:'Показать pet-friendly опыт', detail:'Опишите конкретные услуги и опыт гостей, не приписывая им несуществующих отзывов.'},
        {kind:'ИССЛЕДОВАНИЕ', title:'Проанализировать спрос на короткие поездки', detail:'Подготовьте статистику бронирований с корректным периодом и методикой подсчёта.'},
        {kind:'КОЛОНКА', title:'Объяснить ценность персонального сервиса', detail:'Предложите практическую колонку об обслуживании гостей и операционных решениях.'}
      ]
    }
  };

  const trendsGrid = $('trendsGrid');
  const opportunitiesGrid = $('opportunitiesGrid');
  const form = $('profileForm');
  const releaseOverlay = $('releaseOverlay');
  const headline = $('releaseHeadline');
  const body = $('releaseBody');
  let activeIndustry = 'medtech';
  let activeCompany = 'Демо-компания';
  let previousFocus = null;
  let previousOverflow = '';
  let toastTimer = null;

  function elt(tag, text, className) {
    const node = document.createElement(tag);
    if (text != null) node.textContent = text;
    if (className) node.className = className;
    return node;
  }

  function render() {
    const data = samples[activeIndustry];
    trendsGrid.replaceChildren();
    opportunitiesGrid.replaceChildren();

    for (const [index, trend] of data.trends.entries()) {
      const card = elt('article', null, 'business-trend');
      const top = elt('div', null, 'business-trend-top');
      top.append(elt('span', String(index + 1).padStart(2,'0') + ' / ТЕМА', 'business-trend-num'),
                 elt('span', trend.growth, 'business-trend-growth'));
      const bottom = elt('div', null, 'business-trend-stat');
      bottom.append(elt('strong', String(trend.count)), document.createTextNode(' публикаций · условные данные'));
      const link = elt('a', 'Посмотреть PR-возможности ↗', 'business-inline-link');
      link.href = '#opportunities';
      card.append(top, elt('h3', trend.title), elt('p', trend.detail), bottom, link);
      trendsGrid.append(card);
    }

    for (const [index, opportunity] of data.opportunities.entries()) {
      const card = elt('article', null, 'business-opportunity');
      const actions = elt('div', null, 'business-opportunity-actions');
      const draft = elt('button', 'Подготовить релиз ↗', 'business-btn business-btn--gold');
      draft.type = 'button';
      draft.dataset.draft = String(index);
      const sources = elt('a', 'Подбор СМИ', 'business-btn business-btn--secondary');
      sources.href = '#media';
      actions.append(draft, sources);
      card.append(elt('small', opportunity.kind), elt('h3', opportunity.title),
                  elt('p', opportunity.detail), actions);
      opportunitiesGrid.append(card);
    }
  }

  function notify(message) {
    const toast = $('businessToast');
    clearTimeout(toastTimer);
    toast.textContent = message;
    toast.hidden = false;
    toastTimer = setTimeout(() => { toast.hidden = true; }, 3600);
  }

  form.addEventListener('submit', event => {
    event.preventDefault();
    activeCompany = $('companyName').value.trim() || 'Демо-компания';
    activeIndustry = $('industry').value;
    $('companyDisplay').textContent = '«' + activeCompany + '»';
    $('profileStatus').textContent = 'Показан демонстрационный сценарий для выбранной отрасли. Мониторинг «' +
      activeCompany + '» не запускался; показатели и публикации остаются условными.';
    render();
    notify('Демонстрационный сценарий обновлён');
  });

  const extraMentions = [...document.querySelectorAll('[data-extra-mention]')];
  $('toggleMentions').addEventListener('click', () => {
    const show = extraMentions.some(entry => entry.hidden);
    extraMentions.forEach(entry => { entry.hidden = !show; });
    $('toggleMentions').textContent = show ? 'Свернуть примеры ↑' : 'Показать ещё 3 примера ↓';
    $('toggleMentions').setAttribute('aria-expanded', String(show));
  });

  function openDraft(index, trigger) {
    const idea = samples[activeIndustry].opportunities[index];
    if (!idea) return;
    previousFocus = trigger;
    previousOverflow = document.body.style.overflow;
    headline.value = activeCompany + ': [добавьте подтверждённый информационный повод]';
    body.value = 'Возможная тема: ' + idea.title + '\n\n' +
      'Компания: ' + activeCompany + '\n\n' +
      '[Укажите, что произошло, где и когда. Не используйте вымышленные события.]\n\n' +
      '[Добавьте факты, цифры и независимые подтверждения.]\n\n' +
      '[Приведите согласованную цитату представителя компании, если она есть.]\n\n' +
      '[Укажите контакты пресс-службы.]\n\n' +
      'Рекомендация к подготовке: ' + idea.detail;
    releaseOverlay.hidden = false;
    document.body.style.overflow = 'hidden';
    $('closeRelease').focus();
  }

  function closeDraft() {
    if (releaseOverlay.hidden) return;
    releaseOverlay.hidden = true;
    document.body.style.overflow = previousOverflow;
    if (previousFocus && previousFocus.isConnected) previousFocus.focus();
  }

  opportunitiesGrid.addEventListener('click', event => {
    const btn = event.target.closest('button[data-draft]');
    if (btn) openDraft(Number(btn.dataset.draft), btn);
  });
  $('closeRelease').addEventListener('click', closeDraft);
  $('cancelRelease').addEventListener('click', closeDraft);
  releaseOverlay.addEventListener('click', event => { if (event.target === releaseOverlay) closeDraft(); });
  document.addEventListener('keydown', event => {
    if (releaseOverlay.hidden) return;
    if (event.key === 'Escape') {
      event.preventDefault(); closeDraft();
    } else if (event.key === 'Tab') {
      const focusables = [...releaseOverlay.querySelectorAll('button:not([disabled]),input,textarea')];
      if (!focusables.length) return;
      const first = focusables[0], last = focusables[focusables.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }
  });

  $('copyRelease').addEventListener('click', async () => {
    const draft = headline.value + '\n\n' + body.value;
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(draft);
      } else {
        // Clipboard API may be unavailable on local, non-secure test pages.
        body.focus(); body.select();
        if (!document.execCommand('copy')) throw new Error('Copy unavailable');
      }
      notify('Черновик скопирован — проверьте и дополните фактуру');
    } catch (_) {
      notify('Копирование недоступно: выделите текст и скопируйте вручную');
    }
  });

  render();
})();
