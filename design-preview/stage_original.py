"""Prepare unchanged public assets for the existing browser regression suite."""
import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from media_strazh.browser import DEFAULT_RUNTIME, engine_bundle, runtime_assets

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', required=True, type=Path)
parser.add_argument('--runtime', default=DEFAULT_RUNTIME, type=Path)
args = parser.parse_args()
output = args.output.resolve()
if output.exists() or output == ROOT or ROOT.is_relative_to(output):
    parser.error('Используйте новый отдельный каталог для проверки.')
runtime = runtime_assets(args.runtime)
output.mkdir(parents=True)
for file in ROOT.iterdir():
    if file.is_file() and (file.suffix.lower() in {'.html', '.css', '.js', '.png', '.svg', '.ico', '.webmanifest'}
                           or file.name == 'media-contacts.json'):
        shutil.copy2(file, output/file.name)
(output/'data').mkdir()
shutil.copy2(ROOT/'design-preview/analysis/snapshot.json', output/'data/analysis.json')
(output/'data/manual-engine.json').write_text(json.dumps(engine_bundle(), ensure_ascii=False))
vendor = output/'vendor/pyodide'
vendor.mkdir(parents=True)
for name, path in runtime.items():
    shutil.copy2(path, vendor/name)
print(output)
