/* Public snapshot viewer. Publisher text is always inserted as text, never HTML. */
'use strict';

const element = id => document.getElementById(id);

const statuses = {
  needs_review: 'Требует проверки',
  quoted_candidate: 'Цитата или переданная речь — проверьте автора высказывания',
  context_only: 'Отрицание или обсуждение формулировки'
};

const publishers = {
  rt: 'russian.rt.com',
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
  bbc: 'bbc.com'
};

let report = null;

/* Создание DOM-элементов без вставки пользовательского HTML. */
function node(tag, text, className) {
  const result = document.createElement(tag);
  result.textContent = text;

  if (className) {
    result.className = className;
  }

  return result;
}

/* Форматирование даты по московскому времени. */
function date(value) {
  if (!value || !Number.isFinite(Date.parse(value))) {
    return 'не указана';
  }

  return new Date(value).toLocaleString('ru-RU', {
    timeZone: 'Europe/Moscow'
  }) + ' МСК';
}

/* Определение платформы публикации. */
function platformOf(item) {
  if (
    item.platform === 'telegram' ||
    item.source_type === 'telegram'
  ) {
    return 'telegram';
  }

  try {
    const host = new URL(item.url).hostname.toLowerCase();

    if (
      host === 't.me' ||
      host.endsWith('.t.me') ||
      host === 'telegram.me'
    ) {
      return 'telegram';
    }
  } catch {
    // Если URL некорректен, используем значение по умолчанию.
  }

  return 'website';
}

/* Проверка ссылки на оригинал публикации. */
function original(item) {
  try {
    const url = new URL(item.url);
    const platform = platformOf(item);

    if (
      url.protocol !== 'https:' ||
      url.username ||
      url.password ||
      (url.port && url.port !== '443')
    ) {
      return null;
    }

    if (platform === 'telegram') {
      const isTelegram =
        url.hostname === 't.me' ||
        url.hostname.endsWith('.t.me') ||
        url.hostname === 'telegram.me';

      if (!isTelegram) {
        return null;
      }
    } else {
      const expectedHost = publishers[item.source_id];

      if (!expectedHost || url.hostname !== expectedHost) {
        return null;
      }
    }

    const link = node(
      'a',
      platform === 'telegram'
        ? 'Открыть публикацию в Telegram →'
        : 'Открыть оригинал публикации →'
    );

    link.href = url.href;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';

    return link;
  } catch {
    return null;
  }
}

/* Отображение контекста с выделением найденного фрагмента. */
function excerpt(evidence) {
  const result = node('div', '', 'context');
  const sentence = evidence.sentence;
  const text = Array.from(sentence.text);

  const start = evidence.start - sentence.start;
  const end = evidence.end - sentence.start;

  if (
    start < 0 ||
    end > text.length ||
    text.slice(start, end).join('') !== evidence.quote
  ) {
    result.textContent = sentence.text;
    return result;
  }

  result.append(
    document.createTextNode(text.slice(0, start).join(''))
  );

  result.append(
    node('mark', text.slice(start, end).join(''))
  );

  result.append(
    document.createTextNode(text.slice(end).join(''))
  );

  return result;
}

/* Карточка отдельного найденного фрагмента. */
function findingCard(finding) {
  const card = node('section', '', 'finding');

  card.append(
    node(
      'p',
      statuses[finding.status] || finding.status,
      'badge'
    )
  );

  card.append(
    node('h3', finding.label),
    node('p', finding.explanation)
  );

  for (const evidence of finding.evidence) {
    card.append(
      node(
        'p',
        evidence.field === 'title'
          ? 'Фрагмент заголовка'
          : 'Фрагмент текста',
        'muted'
      )
    );

    card.append(excerpt(evidence));

    if (evidence.sentence.truncated) {
      card.append(
        node(
          'p',
          'Показан ограниченный фрагмент контекста.',
          'muted'
        )
      );
    }
  }

  card.append(node('p', finding.review_question));

  return card;
}

/* Фильтрация и отрисовка публикаций. */
function render() {
  const articlesContainer = element('articles');

  articlesContainer.replaceChildren();

  const platform = element('platform').value;
  const source = element('source').value;
  const candidatesOnly = element('candidates').checked;

  const selected = report.articles.filter(item => {
    const outletMatch =
      !source ||
      item.source_id === source ||
      (
        source === 'other' &&
        !Object.prototype.hasOwnProperty.call(
          publishers,
          item.source_id
        )
      );

    const platformMatch =
      !platform || platformOf(item) === platform;

    const candidateMatch =
      !candidatesOnly ||
      (
        item.summary &&
        item.summary.review_fragments > 0
      );

    return outletMatch && platformMatch && candidateMatch;
  });

  element('selection').textContent =
    'Показано публикаций: ' + selected.length + '.';

  if (!selected.length) {
    const message = platform === 'telegram'
      ? 'В текущей подборке нет публикаций из Telegram. Для их появления нужно подключить сбор Telegram-каналов.'
      : 'В этой подборке нет публикаций, соответствующих фильтрам.';

    articlesContainer.append(
      node('p', message, 'muted')
    );
  }

  for (const item of selected) {
    const article = node('article', '', 'publication');

    article.append(
      node('p', item.source, 'publication-meta')
    );

    article.append(
      node('h2', item.title)
    );

    article.append(
      node(
        'p',
        'Дата получения: ' + date(item.retrieved_at),
        'muted'
      )
    );

    const counts = item.summary;
    const fragmentCount = counts
      ? counts.review_fragments
      : 0;

    article.append(
      node(
        'p',
        'Найдено фрагментов для проверки: ' + fragmentCount,
        'badge'
      )
    );

    const details = document.createElement('details');
    details.append(
      node('summary', 'Подробнее')
    );

    if (!counts) {
      details.append(
        node('p', 'Анализ текущей версией ещё не сохранён.', 'muted')
      );
    } else if (!item.findings.length) {
      details.append(
        node(
          'p',
          'Совпадений текущих правил не найдено. Это не доказывает нейтральность текста.',
          'muted'
        )
      );
    } else {
      for (const finding of item.findings) {
        details.append(findingCard(finding));
      }

      if (item.findings_omitted) {
        details.append(
          node(
            'p',
            'Других меток в результате: ' +
              item.findings_omitted +
              '. Подборка ограничена.',
            'muted'
          )
        );
      }
    }

    if (counts && counts.findings_truncated) {
      details.append(
        node(
          'p',
          'Полный результат ограничен первыми 500 совпадениями; сводка неполная.',
          'muted'
        )
      );
    }

    const actions = node('div', '', 'publication-actions');
    actions.append(details);

    const link = original(item);
    if (link) {
      link.textContent = 'Смотреть источник';
      link.classList.add('source-link');
      actions.append(link);
    }

    article.append(actions);
    articlesContainer.append(article);
  }
}

/* Загрузка опубликованного снимка анализа. */
async function load() {
  try {
    const response = await fetch(
      'data/analysis.json',
      {
        cache: 'no-store',
        signal: AbortSignal.timeout(20000)
      }
    );

    if (!response.ok) {
      throw new Error('snapshot unavailable');
    }

    report = await response.json();

    if (
      report.schema_version !== 'public-snapshot-1.0' ||
      !Array.isArray(report.articles)
    ) {
      throw new Error('invalid snapshot');
    }

    element('updated').textContent =
      'Подборка обновлена: ' +
      date(report.generated_at) +
      '. Версия анализа: ' +
      report.algorithm_version +
      '.';

    const age = Date.now() - Date.parse(report.generated_at);

    if (
      Number.isFinite(age) &&
      age > 90 * 60 * 1000
    ) {
      element('updated').classList.add('error');

      element('updated').append(
        document.createTextNode(
          ' Подборка давно не обновлялась.'
        )
      );
    }

    element('totals').textContent =
      'В подборке: ' +
      report.totals.displayed +
      '. Проанализировано: ' +
      report.totals.analyzed +
      '. С фрагментами для проверки: ' +
      report.totals.with_review_candidates +
      '.';

    element('sources').replaceChildren();

    for (const source of report.sources) {
      const card = node('section', '', 'source');

      card.append(
        node('h3', source.name),
        node(
          'p',
          'Публикаций в подборке: ' + source.displayed
        )
      );

      card.append(
        node(
          'p',
          source.status
            ? 'Последняя проверка: ' +
                date(source.status.last_attempt_at)
            : 'Источник ещё не проверялся.',
          'muted'
        )
      );

      if (source.status && source.status.last_error) {
        card.append(
          node('p', source.status.last_error, 'error')
        );
      }

      element('sources').append(card);
    }

    element('coverage').textContent =
      report.coverage.map(item =>
        item.label +
        ': ' +
        (
          item.coverage === 'candidate_rules'
            ? 'поиск отдельных признаков'
            : 'не проверяется'
        )
      ).join('; ') + '.';

    element('coverageBlock').hidden = false;
    element('controls').hidden = false;

    render();
  } catch (error) {
    console.error('Не удалось загрузить подборку анализа:', error);

    element('updated').textContent =
      'Подборка пока недоступна.';

    element('error').textContent =
      'Публикации появятся после успешного сбора. Попробуйте обновить страницу позже.';

    element('error').hidden = false;
  }
}

/* Подключение фильтров. */
element('source').addEventListener('change', render);
element('platform').addEventListener('change', render);
element('candidates').addEventListener('change', render);

/* Запуск страницы. */
load();
