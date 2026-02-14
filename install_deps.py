#!/usr/bin/env python3
import subprocess
import sys
import os

def get_installed():
    result = subprocess.run(
        [sys.executable, '-m', 'pip', 'list', '--format=columns'],
        capture_output=True, text=True
    )
    installed = set()
    for line in result.stdout.strip().split('\n')[2:]:
        parts = line.split()
        if parts:
            installed.add(parts[0].lower().replace('-', '_').replace('.', '_'))
    return installed

def install_requirements():
    req_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'requirements.txt')
    if not os.path.exists(req_file):
        print("[install_deps] requirements.txt not found")
        return

    installed = get_installed()
    missing = []

    with open(req_file, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            pkg_name = line.split('>=')[0].split('<=')[0].split('==')[0].split('<')[0].split('>')[0].split('[')[0].strip()
            normalized = pkg_name.lower().replace('-', '_').replace('.', '_')
            if normalized not in installed:
                missing.append(line)

    if not missing:
        print("[install_deps] All dependencies already installed")
        return

    print(f"[install_deps] Installing {len(missing)} missing packages...")
    for pkg in missing:
        print(f"  -> {pkg}")
    
    try:
        subprocess.check_call(
            [sys.executable, '-m', 'pip', 'install', '--quiet'] + missing,
            stdout=subprocess.DEVNULL if len(missing) < 5 else None
        )
        print("[install_deps] All packages installed successfully")
    except subprocess.CalledProcessError as e:
        print(f"[install_deps] Batch install failed, trying one by one...")
        for pkg in missing:
            try:
                subprocess.check_call(
                    [sys.executable, '-m', 'pip', 'install', '--quiet', pkg],
                    stdout=subprocess.DEVNULL
                )
                print(f"  [OK] {pkg}")
            except subprocess.CalledProcessError:
                print(f"  [SKIP] {pkg} (optional, skipped)")

if __name__ == '__main__':
    install_requirements()
