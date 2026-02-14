import os
import time
import subprocess
from typing import Optional, Tuple
from sources.logger import Logger


class WebViewer:
    def __init__(self, screenshot_dir: str = ".screenshots"):
        self.screenshot_dir = screenshot_dir
        self.logger = Logger("web_viewer.log")
        os.makedirs(self.screenshot_dir, exist_ok=True)

    def check_url_accessible(self, url: str, timeout: int = 5) -> Tuple[bool, str]:
        try:
            result = subprocess.run(
                ['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}', '--max-time', str(timeout), url],
                capture_output=True, text=True, timeout=timeout + 2
            )
            status_code = result.stdout.strip()
            if status_code and status_code.startswith(('2', '3')):
                return True, f"URL accessible (HTTP {status_code})"
            return False, f"URL returned HTTP {status_code}"
        except Exception as e:
            return False, f"URL not accessible: {str(e)}"

    def get_page_content(self, url: str, timeout: int = 10) -> Tuple[bool, str]:
        try:
            result = subprocess.run(
                ['curl', '-s', '--max-time', str(timeout), url],
                capture_output=True, text=True, timeout=timeout + 2
            )
            if result.returncode == 0 and result.stdout:
                content = result.stdout[:3000]
                return True, content
            return False, f"Failed to fetch: {result.stderr}"
        except Exception as e:
            return False, f"Error fetching URL: {str(e)}"

    def verify_html_file(self, file_path: str) -> dict:
        if not os.path.exists(file_path):
            return {
                'success': False,
                'exists': False,
                'message': f'File not found: {file_path}'
            }

        try:
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()

            has_html = '<html' in content.lower() or '<!doctype' in content.lower()
            has_head = '<head' in content.lower()
            has_body = '<body' in content.lower()
            has_css = '<style' in content.lower() or 'stylesheet' in content.lower()
            has_js = '<script' in content.lower()
            size = len(content)

            issues = []
            if not has_html:
                issues.append("Missing <html> tag")
            if not has_head:
                issues.append("Missing <head> tag")
            if not has_body:
                issues.append("Missing <body> tag")
            if size < 100:
                issues.append("File too small, may be incomplete")

            return {
                'success': len(issues) == 0,
                'exists': True,
                'size': size,
                'has_html': has_html,
                'has_css': has_css,
                'has_js': has_js,
                'issues': issues,
                'message': 'HTML file valid' if not issues else f'Issues: {", ".join(issues)}'
            }
        except Exception as e:
            return {
                'success': False,
                'exists': True,
                'message': f'Error reading file: {str(e)}'
            }

    def verify_project_files(self, project_dir: str) -> dict:
        if not os.path.isdir(project_dir):
            return {
                'success': False,
                'message': f'Directory not found: {project_dir}',
                'files': []
            }

        files_found = []
        issues = []

        for root, dirs, files in os.walk(project_dir):
            dirs[:] = [d for d in dirs if d not in ('node_modules', '.git', '__pycache__', 'venv')]
            for fname in files:
                fpath = os.path.join(root, fname)
                rel_path = os.path.relpath(fpath, project_dir)
                size = os.path.getsize(fpath)
                files_found.append({
                    'path': rel_path,
                    'size': size,
                    'type': os.path.splitext(fname)[1]
                })
                if size == 0:
                    issues.append(f"Empty file: {rel_path}")

        has_html = any(f['type'] == '.html' for f in files_found)
        has_py = any(f['type'] == '.py' for f in files_found)
        has_index = any('index' in f['path'].lower() for f in files_found)

        return {
            'success': len(files_found) > 0,
            'files': files_found,
            'file_count': len(files_found),
            'has_html': has_html,
            'has_python': has_py,
            'has_index': has_index,
            'issues': issues,
            'message': f'Found {len(files_found)} files' + (f', {len(issues)} issues' if issues else '')
        }

    def get_verification_feedback(self, project_dir: str) -> str:
        result = self.verify_project_files(project_dir)
        lines = [f"📁 Project Verification: {result['message']}"]

        if result['files']:
            lines.append("\nFile yang dibuat:")
            for f in result['files'][:20]:
                size_str = f"{f['size']}B" if f['size'] < 1024 else f"{f['size']//1024}KB"
                lines.append(f"  {f['path']} ({size_str})")

        if result['issues']:
            lines.append("\n⚠️ Issues:")
            for issue in result['issues']:
                lines.append(f"  - {issue}")

        for f in result['files']:
            if f['type'] == '.html':
                html_check = self.verify_html_file(os.path.join(project_dir, f['path']))
                if not html_check['success']:
                    lines.append(f"\n🔍 HTML check {f['path']}: {html_check['message']}")

        return '\n'.join(lines)
