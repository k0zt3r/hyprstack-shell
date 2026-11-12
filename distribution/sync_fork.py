#!/usr/bin/env python3
"""Merge upstream and personal changes without rewriting either history."""
import argparse
from datetime import datetime, timezone
import fcntl
import os
from pathlib import Path
import subprocess
import sys
import tarfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--apply', action='store_true', help='Сохранить правки и объединить обновления')
    parser.add_argument('--push', action='store_true', help='Отправить результат в форк (требует --apply)')
    parser.add_argument('--install', action='store_true', help='Запустить штатный update.sh --no-pull после объединения')
    parser.add_argument('--upstream', default='origin')
    parser.add_argument('--upstream-branch', default='main')
    parser.add_argument('--fork', default='fork')
    parser.add_argument('--include', action='append', default=[], metavar='PATH', help='Добавить конкретный новый файл в коммит; можно повторять')
    args = parser.parse_args()
    if (args.push or args.install or args.include) and not args.apply:
        parser.error('--push, --install и --include требуют --apply')
    repo = args.repo.resolve()

    def git(*words, capture=False, timeout=120):
        result = subprocess.run(['git', '-C', str(repo), *words], check=True,
                                stdout=subprocess.PIPE if capture else None,
                                text=capture, timeout=timeout)
        return result.stdout.strip() if capture else None

    branch = git('symbolic-ref', '--quiet', '--short', 'HEAD', capture=True)
    git('check-ref-format', '--branch', branch, capture=True)
    git('check-ref-format', '--branch', args.upstream_branch, capture=True)
    for remote in (args.upstream, args.fork):
        if remote.startswith('-'):
            raise ValueError('Недопустимое имя remote')
        print(f'{remote}: {git("remote", "get-url", remote, capture=True)}', flush=True)
    if args.upstream == args.fork:
        raise ValueError('Оригинал и форк должны быть разными remote')
    git_dir = Path(git('rev-parse', '--absolute-git-dir', capture=True))
    for marker in ('MERGE_HEAD', 'CHERRY_PICK_HEAD', 'REVERT_HEAD', 'rebase-merge', 'rebase-apply'):
        if (git_dir / marker).exists():
            raise ValueError('Сначала завершите текущую операцию Git: ' + marker)
    print(f'Ветка: {branch}. Локальные изменения:', flush=True)
    git('status', '--short')
    if not args.apply:
        print('Проверка без изменений и доступа к сети. Для синхронизации: --apply; отправка: --apply --push.')
        return

    # One updater per worktree. Git also protects individual index/ref operations.
    with (git_dir / 'hyprstack-sync.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = Path(os.environ.get('XDG_STATE_HOME', str(Path.home() / '.local/state')))
        backup = state / 'hyprstack/fork-sync' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
        backup.mkdir(parents=True, mode=0o700)
        (backup / 'head.txt').write_text(git('rev-parse', 'HEAD', capture=True) + '\n')
        with (backup / 'changes.patch').open('wb') as output:
            subprocess.run(['git', '-C', str(repo), 'diff', '--binary', 'HEAD'], stdout=output, check=True)
        untracked = subprocess.check_output(['git', '-C', str(repo), 'ls-files', '--others', '--exclude-standard', '-z'])
        config = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config')))
        with tarfile.open(backup / 'local-files.tar.gz', 'w:gz', dereference=False) as archive:
            for raw in untracked.split(b'\0'):
                if raw:
                    name = os.fsdecode(raw)
                    archive.add(repo / name, arcname='untracked/' + name)
            for name in ('hyprstack', 'hypr', 'xdg-desktop-portal'):
                if (config / name).exists():
                    archive.add(config / name, arcname='config/' + name)
        print(f'Локальная резервная копия: {backup}', flush=True)
        # Fetch before changing the working tree: network failures leave edits alone.
        git('fetch', '--no-tags', args.upstream,
            f'+refs/heads/{args.upstream_branch}:refs/remotes/{args.upstream}/{args.upstream_branch}')
        # Fetch all fork heads so a newly created local branch is supported too.
        git('fetch', '--no-tags', args.fork,
            f'+refs/heads/*:refs/remotes/{args.fork}/*')
        git('add', '-u', '--', '.')
        if args.include:
            git('add', '--', *args.include)
        if subprocess.run(['git', '-C', str(repo), 'diff', '--cached', '--quiet']).returncode == 1:
            git('commit', '-m', 'Preserve local Hyprstack improvements before upstream sync')
        fork_ref = f'refs/remotes/{args.fork}/{branch}'
        if subprocess.run(['git', '-C', str(repo), 'show-ref', '--verify', '--quiet', fork_ref]).returncode == 0:
            git('merge', '--no-edit', fork_ref)
        git('merge', '--no-edit', f'refs/remotes/{args.upstream}/{args.upstream_branch}')
        if args.install:
            subprocess.run([str(repo / 'update.sh'), '--no-pull'], cwd=repo, check=True)
        if args.push:
            git('push', args.fork, f'HEAD:refs/heads/{branch}')
        print('Готово. История оригинала и ваши коммиты сохранены. Настройки находятся только в локальной копии.')
        if not args.install:
            print('Установка не менялась. Для сборки и установки из TTY: ./update.sh --no-pull')


if __name__ == '__main__':
    try:
        main()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError, ValueError) as error:
        print(f'Синхронизация остановлена: {error}', file=sys.stderr)
        print('При конфликте: git status, исправьте файлы, git add <файлы>, git merge --continue.\n'
              'Для отмены незавершённого merge: git merge --abort. Затем повторите команду.', file=sys.stderr)
        sys.exit(1)
