#!/usr/bin/env python3
"""Copy the skill to a personal skills directory, without replacing it."""
import argparse
import os
import shutil
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    default = Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex') / 'skills'
    parser.add_argument('--skills-dir', type=Path, default=default)
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[1] / 'zotero-library'
    target = args.skills_dir.expanduser().resolve() / 'zotero-library'
    if target.exists():
        parser.error('Skill already exists at {}. Back it up or choose another directory.'.format(target))
    if source in target.parents:
        parser.error('Choose a skills directory outside the source skill.')
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(str(source), str(target), ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    print('Installed: {}'.format(target))


if __name__ == '__main__':
    main()
