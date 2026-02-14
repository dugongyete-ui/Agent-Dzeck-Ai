import subprocess
import time
import re
import os
import tempfile
import signal
import resource
from dataclasses import dataclass, field
from typing import Optional, List, Dict
from sources.logger import Logger


DANGEROUS_PATTERNS = [
    r'\bos\.system\b',
    r'\bos\.popen\b',
    r'\bos\.exec\w*\b',
    r'\bos\.spawn\w*\b',
    r'\bos\.kill\b',
    r'\bos\.remove\b',
    r'\bos\.unlink\b',
    r'\bos\.rmdir\b',
    r'\bsubprocess\.\w+',
    r'\bshutil\.rmtree\b',
    r'\bshutil\.move\b',
    r'\b__import__\b',
    r'\bimportlib\b',
    r'\beval\s*\(',
    r'\bexec\s*\(',
    r'\bcompile\s*\(',
    r'\bopen\s*\(.*/etc/',
    r'\bsocket\.\w+',
    r'\bctypes\b',
    r'\bsignal\.SIG',
    r'\bsys\.exit\b',
    r'\bos\._exit\b',
    r'\bPickle\b',
    r'\bpickle\.loads\b',
    r'\bmarshall\b',
]

SERVER_START_PATTERNS = [
    r'\.run\s*\(',
    r'app\.run\s*\(',
    r'uvicorn\.run\s*\(',
    r'serve\s*\(\s*app',
    r'httpd\.serve_forever\s*\(',
    r'socketserver\.',
    r'http\.server',
    r'waitress\.serve\s*\(',
    r'gunicorn',
    r'flask\s+run',
]

ALLOWED_PYTHON_MODULES = [
    'math', 'random', 'datetime', 'json', 'csv', 'collections',
    'itertools', 'functools', 'string', 're', 'os.path',
    'pathlib', 'typing', 'dataclasses', 'enum', 'abc',
    'flask', 'fastapi', 'jinja2', 'markdownify',
    'numpy', 'beautifulsoup4', 'bs4', 'requests',
    'html', 'xml', 'sqlite3', 'hashlib', 'base64',
    'uuid', 'time', 'calendar', 'decimal', 'fractions',
    'statistics', 'textwrap', 'unicodedata', 'io',
    'copy', 'pprint', 'operator', 'contextlib',
]

DANGEROUS_BASH_PATTERNS = [
    r'\brm\s+-rf\b',
    r'\brm\s+-fr\b',
    r'\brm\s+--no-preserve-root\b',
    r'\bdd\s+',
    r'\bmkfs\b',
    r'\bfdisk\b',
    r'\bparted\b',
    r'\bchmod\s+777\b',
    r'\bchmod\s+-R\b',
    r'\bchown\s+-R\b',
    r'\b:\(\)\s*\{\s*:\|:\s*&\s*\}\s*;',
    r'\bshutdown\b',
    r'\breboot\b',
    r'\bhalt\b',
    r'\binit\s+0\b',
    r'\bsystemctl\s+(stop|disable|mask)\b',
    r'\bmv\s+/\b',
    r'\b>\s*/dev/sd',
    r'\bcurl\b.*\|\s*bash',
    r'\bwget\b.*\|\s*bash',
    r'\bnc\s+-l',
    r'\bnetcat\b',
    r'\bnmap\b',
    r'\biptables\b',
    r'\bpasswd\b',
    r'\buseradd\b',
    r'\buserdel\b',
    r'\bvisudo\b',
    r'\bsudo\b',
    r'\bsu\s+',
    r'\bchroot\b',
]

ALLOWED_BASH_COMMANDS = [
    'ls', 'cat', 'echo', 'pwd', 'mkdir', 'touch', 'cp', 'mv',
    'find', 'grep', 'head', 'tail', 'wc', 'sort', 'uniq',
    'sed', 'awk', 'tr', 'cut', 'paste', 'tee',
    'tar', 'gzip', 'gunzip', 'zip', 'unzip',
    'curl', 'wget', 'python3', 'python', 'node', 'npm', 'npx',
    'git', 'which', 'whoami', 'date', 'env', 'export',
    'chmod', 'cd', 'tree', 'diff', 'patch',
    'pip', 'pip3', 'yarn',
]

DANGEROUS_JS_PATTERNS = [
    r'\bchild_process\b',
    r'\bexec\s*\(',
    r'\bexecSync\b',
    r'\bspawn\b',
    r'\bspawnSync\b',
    r'\beval\s*\(',
    r'\bFunction\s*\(',
    r'\bfs\.rmSync\b',
    r'\bfs\.unlinkSync\b',
    r'\bprocess\.exit\b',
    r'\brequire\s*\(\s*["\']child_process["\']\s*\)',
]

LANGUAGE_CONFIG = {
    'python': {
        'extension': '.py',
        'command': ['python3'],
        'patterns': DANGEROUS_PATTERNS,
    },
    'javascript': {
        'extension': '.js',
        'command': ['node'],
        'patterns': DANGEROUS_JS_PATTERNS,
    },
    'nodejs': {
        'extension': '.js',
        'command': ['node'],
        'patterns': DANGEROUS_JS_PATTERNS,
    },
    'bash': {
        'extension': '.sh',
        'command': ['bash'],
        'patterns': DANGEROUS_BASH_PATTERNS,
    },
    'go': {
        'extension': '.go',
        'command': ['go', 'run'],
        'patterns': [],
    },
}

MAX_OUTPUT_LENGTH = 50000

RESTRICTED_PATHS = [
    '/etc/passwd', '/etc/shadow', '/etc/sudoers',
    '/root', '/proc', '/sys',
    '/home/runner/.config',
]


@dataclass
class SandboxResult:
    success: bool
    output: str
    errors: str
    execution_time: float
    language: str = ""
    timed_out: bool = False
    blocked: bool = False
    blocked_reason: str = ""
    truncated: bool = False


class SafeExecutor:
    def __init__(self, work_dir: Optional[str] = None,
                 timeout: int = 60,
                 max_memory_mb: int = 1024,
                 block_network: bool = False,
                 isolation_mode: str = "workspace"):
        self.work_dir = work_dir or os.getcwd()
        if self.work_dir and not os.path.exists(self.work_dir):
            os.makedirs(self.work_dir, exist_ok=True)
        self.timeout = timeout
        self.max_memory_mb = max_memory_mb
        self.block_network = block_network
        self.isolation_mode = isolation_mode
        self.logger = Logger("sandbox.log")

    def _set_resource_limits(self):
        try:
            mem_bytes = self.max_memory_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
        except (ValueError, OSError):
            pass

    def _truncate_output(self, text: str) -> tuple:
        if len(text) > MAX_OUTPUT_LENGTH:
            truncated = text[:MAX_OUTPUT_LENGTH] + f"\n\n... [output truncated, {len(text) - MAX_OUTPUT_LENGTH} chars omitted]"
            return truncated, True
        return text, False

    def _check_path_safety(self, code: str) -> tuple:
        for restricted in RESTRICTED_PATHS:
            if restricted in code:
                return False, f"Access to restricted path blocked: {restricted}"
        if self.isolation_mode == "workspace":
            parent_traversal = re.findall(r'\.\./\.\./\.\./', code)
            if parent_traversal:
                return False, "Path traversal beyond workspace detected"
        return True, ""

    def _is_server_code(self, code: str) -> bool:
        if not code:
            return False
        server_indicators = [
            r'from\s+flask\s+import',
            r'from\s+fastapi\s+import',
            r'import\s+flask',
            r'import\s+fastapi',
            r'app\s*=\s*Flask\s*\(',
            r'app\s*=\s*FastAPI\s*\(',
            r'app\.run\s*\(',
            r'uvicorn\.run\s*\(',
            r'@app\.route\s*\(',
            r'@app\.(get|post|put|delete|patch)\s*\(',
        ]
        matches = sum(1 for p in server_indicators if re.search(p, code))
        return matches >= 2

    def _strip_server_start(self, code: str, language: str) -> str:
        if language != 'python':
            return code
        lines = code.split('\n')
        cleaned = []
        skip_block = False
        for line in lines:
            stripped = line.strip()
            is_server_line = False
            for pattern in SERVER_START_PATTERNS:
                if re.search(pattern, stripped):
                    is_server_line = True
                    break
            if is_server_line:
                cleaned.append(f"# [sandbox] server start removed: {stripped}")
                continue
            if stripped.startswith('if __name__') and '__main__' in stripped:
                skip_block = True
                cleaned.append(f"# [sandbox] main block removed: {stripped}")
                continue
            if skip_block:
                if stripped == '' or line[0:1] in (' ', '\t'):
                    cleaned.append(f"# [sandbox] {stripped}")
                    continue
                else:
                    skip_block = False
            cleaned.append(line)
        return '\n'.join(cleaned)

    def _try_auto_install(self, error_text: str) -> bool:
        module_match = re.search(r"No module named ['\"]([^'\"]+)['\"]", error_text)
        if not module_match:
            return False
        module_name = module_match.group(1).split('.')[0]
        pkg_map = {
            'bs4': 'beautifulsoup4',
            'cv2': 'opencv-python',
            'PIL': 'Pillow',
            'sklearn': 'scikit-learn',
            'yaml': 'pyyaml',
            'dotenv': 'python-dotenv',
            'gi': 'PyGObject',
        }
        pkg_name = pkg_map.get(module_name, module_name)
        self.logger.info(f"Auto-installing missing module: {pkg_name}")
        try:
            result = subprocess.run(
                ['pip', 'install', '--quiet', pkg_name],
                capture_output=True, text=True, timeout=60
            )
            if result.returncode == 0:
                self.logger.info(f"Successfully installed {pkg_name}")
                return True
            self.logger.warning(f"Failed to install {pkg_name}: {result.stderr}")
        except Exception as e:
            self.logger.warning(f"Auto-install error: {e}")
        return False

    def validate_code(self, code: str, language: str) -> tuple:
        path_safe, path_reason = self._check_path_safety(code)
        if not path_safe:
            return False, path_reason

        config = LANGUAGE_CONFIG.get(language)
        if not config:
            return True, ""
        
        for pattern in config['patterns']:
            match = re.search(pattern, code)
            if match:
                return False, f"Blocked dangerous pattern: {match.group()}"
        
        if self.block_network and language == 'python':
            network_patterns = [r'\bsocket\b', r'\burllib\b', r'\brequests\b', r'\bhttplib\b', r'\bhttp\b']
            for pattern in network_patterns:
                match = re.search(pattern, code)
                if match:
                    return False, f"Network access blocked: {match.group()}"
        return True, ""

    def validate_python(self, code: str) -> tuple:
        return self.validate_code(code, 'python')

    def validate_bash(self, command: str) -> tuple:
        return self.validate_code(command, 'bash')

    def _execute_code(self, code: str, language: str) -> SandboxResult:
        if language == 'python' and self._is_server_code(code):
            self.logger.info("Server code detected - saving file only, skipping execution")
            return SandboxResult(
                success=True,
                output="[server code] File backend berhasil disimpan. Server tidak dijalankan di sandbox karena port sudah digunakan. File siap digunakan.",
                errors="",
                execution_time=0.0,
                language=language
            )

        code = self._strip_server_start(code, language)

        is_safe, reason = self.validate_code(code, language)
        if not is_safe:
            self.logger.warning(f"Blocked {language} code: {reason}")
            return SandboxResult(
                success=False, output="", errors=reason,
                execution_time=0.0, language=language,
                blocked=True, blocked_reason=reason
            )

        config = LANGUAGE_CONFIG.get(language)
        if not config:
            return SandboxResult(
                success=False, output="",
                errors=f"Unsupported language: {language}",
                execution_time=0.0, language=language
            )

        if language == 'bash':
            return self._execute_shell(code)

        max_retries = 2
        for attempt in range(max_retries):
            result = self._run_code_subprocess(code, language, config)
            if result.success:
                return result
            if language == 'python' and 'No module named' in result.errors and attempt < max_retries - 1:
                if self._try_auto_install(result.errors):
                    self.logger.info("Module installed, retrying execution...")
                    continue
            return result
        return result

    def _run_code_subprocess(self, code: str, language: str, config: dict) -> SandboxResult:
        with tempfile.NamedTemporaryFile(mode='w', suffix=config['extension'],
                                          dir=self.work_dir, delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            start_time = time.time()
            env = os.environ.copy()
            if language == 'python':
                env['PYTHONDONTWRITEBYTECODE'] = '1'
                pythonlibs = os.path.join(os.path.expanduser('~'), 'workspace', '.pythonlibs', 'lib')
                if os.path.isdir(pythonlibs):
                    for d in os.listdir(pythonlibs):
                        sp = os.path.join(pythonlibs, d, 'site-packages')
                        if os.path.isdir(sp):
                            existing = env.get('PYTHONPATH', '')
                            env['PYTHONPATH'] = sp + (':' + existing if existing else '')
                            break

            cmd = config['command'] + [temp_path]
            self.logger.info(f"Executing {language}: {cmd[0]} ...")

            def preexec():
                if os.name != 'nt':
                    os.setsid()
                    self._set_resource_limits()

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self.work_dir,
                env=env,
                preexec_fn=preexec if os.name != 'nt' else None
            )

            try:
                stdout, stderr = process.communicate(timeout=self.timeout)
                execution_time = time.time() - start_time
                output_text = stdout.decode('utf-8', errors='replace')
                error_text = stderr.decode('utf-8', errors='replace')
                output_text, truncated = self._truncate_output(output_text)
                
                self.logger.info(f"{language} execution completed in {execution_time:.2f}s (rc={process.returncode})")
                return SandboxResult(
                    success=(process.returncode == 0),
                    output=output_text,
                    errors=error_text,
                    execution_time=execution_time,
                    language=language,
                    truncated=truncated
                )
            except subprocess.TimeoutExpired:
                if os.name != 'nt':
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                else:
                    process.kill()
                stdout, stderr = process.communicate()
                execution_time = time.time() - start_time
                self.logger.warning(f"{language} execution timed out after {self.timeout}s")
                return SandboxResult(
                    success=False,
                    output=stdout.decode('utf-8', errors='replace'),
                    errors=f"Execution timed out after {self.timeout} seconds",
                    execution_time=execution_time,
                    language=language,
                    timed_out=True
                )
        finally:
            try:
                os.unlink(temp_path)
            except OSError:
                pass

    def _is_system_install(self, command: str) -> bool:
        cmd_lower = command.lower().strip()
        system_patterns = [
            "apt install", "apt-get install", "apt update", "apt-get update",
            "brew install", "conda install",
        ]
        return any(pattern in cmd_lower for pattern in system_patterns)

    def _is_allowed_install(self, command: str) -> bool:
        cmd_lower = command.lower().strip()
        allowed_patterns = [
            "pip install", "pip3 install",
            "npm install", "npm i ", "yarn add", "yarn install",
            "npx ", "npm init", "npm create",
        ]
        return any(pattern in cmd_lower for pattern in allowed_patterns)

    def _add_pip_safety(self, command: str) -> str:
        return command

    def _execute_shell(self, command: str) -> SandboxResult:
        if self._is_system_install(command):
            self.logger.info(f"Blocked system install: {command[:100]}")
            return SandboxResult(
                success=True,
                output=f"[blocked] System package install not allowed: {command.strip()}\nGunakan pip/npm/yarn untuk install packages.",
                errors="", execution_time=0.0, language='bash'
            )

        if self._is_allowed_install(command):
            command = command.replace(' --break-system-packages', '')
            self.logger.info(f"Autonomous: executing install: {command[:100]}")
            return self._execute_shell_raw(command)

        is_safe, reason = self.validate_bash(command)
        if not is_safe:
            self.logger.warning(f"Blocked bash command: {reason}")
            return SandboxResult(
                success=False, output="", errors=reason,
                execution_time=0.0, language='bash',
                blocked=True, blocked_reason=reason
            )

        return self._execute_shell_raw(command)

    def _execute_shell_raw(self, command: str) -> SandboxResult:
        start_time = time.time()
        self.logger.info(f"Executing bash: {command[:100]}...")
        try:
            def preexec():
                if os.name != 'nt':
                    os.setsid()
                    self._set_resource_limits()

            env = os.environ.copy()
            env['PYTHONDONTWRITEBYTECODE'] = '1'

            process = subprocess.Popen(
                ['bash', '-c', command],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self.work_dir,
                env=env,
                preexec_fn=preexec if os.name != 'nt' else None
            )

            try:
                stdout, stderr = process.communicate(timeout=self.timeout)
                execution_time = time.time() - start_time
                output_text = stdout.decode('utf-8', errors='replace')
                error_text = stderr.decode('utf-8', errors='replace')
                output_text, truncated = self._truncate_output(output_text)

                self.logger.info(f"Bash execution completed in {execution_time:.2f}s (rc={process.returncode})")
                return SandboxResult(
                    success=(process.returncode == 0),
                    output=output_text,
                    errors=error_text,
                    execution_time=execution_time,
                    language='bash',
                    truncated=truncated
                )
            except subprocess.TimeoutExpired:
                if os.name != 'nt':
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                else:
                    process.kill()
                stdout, stderr = process.communicate()
                execution_time = time.time() - start_time
                self.logger.warning(f"Bash execution timed out after {self.timeout}s")
                return SandboxResult(
                    success=False,
                    output=stdout.decode('utf-8', errors='replace'),
                    errors=f"Execution timed out after {self.timeout} seconds",
                    execution_time=execution_time,
                    language='bash',
                    timed_out=True
                )
        except Exception as e:
            execution_time = time.time() - start_time
            self.logger.error(f"Bash execution error: {str(e)}")
            return SandboxResult(
                success=False, output="", errors=str(e),
                execution_time=execution_time,
                language='bash'
            )

    def execute_python(self, code: str) -> SandboxResult:
        return self._execute_code(code, 'python')

    def execute_bash(self, command: str) -> SandboxResult:
        return self._execute_shell(command)

    def execute_javascript(self, code: str) -> SandboxResult:
        return self._execute_code(code, 'javascript')

    def execute_go(self, code: str) -> SandboxResult:
        return self._execute_code(code, 'go')


class Sandbox:
    def __init__(self, work_dir: Optional[str] = None,
                 timeout: int = 60,
                 max_memory_mb: int = 1024,
                 block_network: bool = False,
                 isolation_mode: str = "workspace"):
        self.work_dir = work_dir or os.getcwd()
        self.timeout = timeout
        self.max_memory_mb = max_memory_mb
        self.block_network = block_network
        self.isolation_mode = isolation_mode
        self.executor = SafeExecutor(
            work_dir=self.work_dir,
            timeout=self.timeout,
            max_memory_mb=self.max_memory_mb,
            block_network=self.block_network,
            isolation_mode=self.isolation_mode,
        )
        self.execution_history: List[tuple] = []
        self.logger = Logger("sandbox.log")

    @property
    def supported_languages(self) -> List[str]:
        return list(LANGUAGE_CONFIG.keys())

    def run_python(self, code: str) -> SandboxResult:
        result = self.executor.execute_python(code)
        self.execution_history.append(('python', result))
        return result

    def run_bash(self, command: str) -> SandboxResult:
        result = self.executor.execute_bash(command)
        self.execution_history.append(('bash', result))
        return result

    def run_javascript(self, code: str) -> SandboxResult:
        result = self.executor.execute_javascript(code)
        self.execution_history.append(('javascript', result))
        return result

    def run_go(self, code: str) -> SandboxResult:
        result = self.executor.execute_go(code)
        self.execution_history.append(('go', result))
        return result

    def run(self, code: str, language: str) -> SandboxResult:
        language = language.lower().strip()
        lang_map = {
            'python': self.run_python,
            'bash': self.run_bash,
            'javascript': self.run_javascript,
            'js': self.run_javascript,
            'nodejs': self.run_javascript,
            'node': self.run_javascript,
            'go': self.run_go,
            'golang': self.run_go,
        }
        runner = lang_map.get(language)
        if runner:
            return runner(code)
        return SandboxResult(
            success=False, output="",
            errors=f"Unsupported language: {language}. Supported: {', '.join(self.supported_languages)}",
            execution_time=0.0, language=language
        )

    def get_history(self) -> list:
        return self.execution_history

    def get_stats(self) -> Dict:
        total = len(self.execution_history)
        success = sum(1 for _, r in self.execution_history if r.success)
        blocked = sum(1 for _, r in self.execution_history if r.blocked)
        timed_out = sum(1 for _, r in self.execution_history if r.timed_out)
        total_time = sum(r.execution_time for _, r in self.execution_history)
        return {
            "total_executions": total,
            "successful": success,
            "failed": total - success,
            "blocked": blocked,
            "timed_out": timed_out,
            "total_execution_time": round(total_time, 2),
        }

    def clear_history(self):
        self.execution_history.clear()

    def format_result(self, result: SandboxResult) -> str:
        lang_info = f" ({result.language})" if result.language else ""
        if result.blocked:
            return f"[blocked{lang_info}] {result.blocked_reason}"
        if result.timed_out:
            return f"[timeout{lang_info}] Execution timed out after {result.execution_time:.2f}s\nPartial output: {result.output}"
        truncation_note = " [output truncated]" if result.truncated else ""
        if result.success:
            return f"[success{lang_info}] Execution completed in {result.execution_time:.2f}s{truncation_note}\n{result.output}"
        else:
            return f"[failure{lang_info}] Execution failed in {result.execution_time:.2f}s{truncation_note}\nOutput: {result.output}\nErrors: {result.errors}"
