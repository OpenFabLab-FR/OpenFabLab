"""Run every local suite in isolation; never import the application unconfigured."""
import ast
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reuse-plugin',action='store_true',help='Audit the unchanged plugin ZIP without rebuilding it')
    options=parser.parse_args()
    node = shutil.which('node')
    php = os.environ.get('PHP_TEST_COMMAND') or shutil.which('php')
    if not php:
        candidate = ROOT/'node_modules/.bin/php-wasm-cli'
        php = str(candidate) if candidate.is_file() else None
    if not node or not php:
        raise SystemExit('Install Node.js, npm ci and PHP 8.1+ (or the bundled PHP WASM tool).')
    with tempfile.TemporaryDirectory(prefix='openfablab-public-checks-') as directory:
        temporary = Path(directory)
        env = os.environ.copy()
        for key in list(env):
            if key.startswith(('OPENFABLAB_', 'COMPTEUR_')):
                del env[key]
        env.update(COMPTEUR_DATABASE=str(temporary/'import.db'),
                   COMPTEUR_SECRET_KEY_FILE=str(temporary/'import.secret'),
                   OPENFABLAB_ENABLE_SCHEDULER='0', COMPTEUR_ENABLE_SCHEDULER='0',
                   OPENFABLAB_ENABLE_WEATHER='0', COMPTEUR_ENABLE_WEATHER='0',
                   OPENFABLAB_BACKUP_ROOT=str(temporary/'backups'),
                   PYTHONDONTWRITEBYTECODE='1', PHP='8.1', PHP_TEST_COMMAND=php,
                   TEST_PYTHON=sys.executable, TMPDIR=str(temporary))
        env.pop('PYTHONPATH', None)
        totals = {'Python':0, 'PHP':0, 'JavaScript':0}
        def run(label, command):
            result = subprocess.run(command, cwd=ROOT, env=env, text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            print(result.stdout, end='', flush=True)
            if result.returncode:
                raise SystemExit(label + ' FAILED (no production action was performed)')
            if label in totals:
                count = (re.findall(r'Ran (\d+) tests?',result.stdout) if label=='Python'
                         else re.findall(r'(\d+)\s[^\n]*?(?:checks|tests) passed\b',result.stdout))
                if not count:
                    raise SystemExit('No test count reported by ' + str(command[-1]))
                totals[label] += int(count[-1])
        run('Python',[sys.executable,'-m','unittest','discover','-s','tests','-p','test_*.py'])
        for path in sorted((ROOT/'tests').glob('test_wordpress_*.php')):
            run('PHP',[php,str(path)])
        for path in sorted((ROOT/'tests').glob('test_*.js')):
            run('JavaScript',[node,str(path)])
        python_files = list(ROOT.glob('*.py')) + list((ROOT/'openfablab').glob('*.py')) + list((ROOT/'tests').glob('*.py')) + list((ROOT/'tools').glob('*.py'))
        for path in python_files:
            compile(path.read_text(),str(path),'exec')
        js_files = list((ROOT/'static').rglob('*.js')) + list((ROOT/'wordpress').rglob('*.js')) + list((ROOT/'tests').glob('*.js'))
        for path in js_files:
            run('JS syntax',[node,'--check',str(path)])
        php_files = list((ROOT/'wordpress').rglob('*.php')) + list((ROOT/'tests').glob('*.php'))
        for path in php_files:
            run('PHP syntax',[php,'-l',str(path)])
        if shutil.which('zsh'):
            run('macOS launcher syntax',['zsh','-n',str(ROOT/'AppStart.command')])
        run('Application package',[sys.executable,'build_openfablab.py'])
        if not options.reuse_plugin:
            run('Plugin package',[sys.executable,'build_wordpress_plugin.py'])
        run('Archives',[sys.executable,'tests/check_v26_archives.py']+(['--reuse-plugin'] if options.reuse_plugin else []))
        run('Public manifest',[sys.executable,'tools/check_public_tree.py'])
        print('TOTALS=' + str(totals))
        print(f'SYNTAX=Python:{len(python_files)} JS:{len(js_files)} PHP:{len(php_files)}')


if __name__ == '__main__':
    main()
