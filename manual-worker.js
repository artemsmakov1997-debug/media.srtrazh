/* Run the existing Python analyser in an isolated browser worker, with local assets. */
'use strict';
let enginePromise = null;

async function engine() {
  if (!enginePromise) {
    enginePromise = (async () => {
      importScripts('vendor/pyodide/pyodide.js');
      const [pyodide, response] = await Promise.all([
        loadPyodide({indexURL: new URL('vendor/pyodide/', self.location.href).href}),
        fetch('data/manual-engine.json', {cache: 'no-store'})
      ]);
      if (!response.ok) throw new Error('Analysis bundle unavailable');
      const bundle = await response.json();
      if (bundle.schema_version !== 'browser-engine-1.0' || bundle.runtime_version !== pyodide.version) {
        throw new Error('Analysis bundle version mismatch');
      }
      const directory = '/home/pyodide/media_strazh';
      pyodide.FS.mkdirTree(directory);
      for (const name of ['__init__.py', 'analysis.py', 'rules.py']) {
        if (typeof bundle.files[name] !== 'string') throw new Error('Analysis source missing');
        pyodide.FS.writeFile(directory + '/' + name, bundle.files[name], {encoding: 'utf8'});
      }
      pyodide.runPython([
        'import sys, json',
        'sys.path.insert(0, "/home/pyodide")',
        'from media_strazh.analysis import analyze, VERSION',
        'def browser_analyze(raw):',
        '    return json.dumps(analyze(json.loads(raw)), ensure_ascii=False)'
      ].join('\n'));
      if (pyodide.runPython('VERSION') !== bundle.algorithm_version) {
        throw new Error('Analysis rule version mismatch');
      }
      return pyodide;
    })().catch(error => { enginePromise = null; throw error; });
  }
  return enginePromise;
}

self.addEventListener('message', async event => {
  const {id, document} = event.data;
  let pyodide;
  try {
    self.postMessage({id, type: 'state', state: enginePromise ? 'analysing' : 'loading'});
    pyodide = await engine();
    self.postMessage({id, type: 'state', state: 'analysing'});
  } catch {
    self.postMessage({id, type: 'error', kind: 'loading',
      message: 'Не удалось загрузить анализатор. Проверьте соединение и повторите попытку.'});
    return;
  }
  try {
    pyodide.globals.set('submission_json', JSON.stringify(document));
    const result = JSON.parse(pyodide.runPython('browser_analyze(submission_json)'));
    self.postMessage({id, type: 'result', result});
  } catch (error) {
    const validation = /ValueError: ([^\n]+)/.exec(String(error));
    self.postMessage({id, type: 'error', kind: validation ? 'validation' : 'analysis',
      message: validation ? validation[1] : 'Не удалось выполнить анализ. Повторите попытку.'});
  } finally {
    pyodide.globals.delete('submission_json');
  }
});
