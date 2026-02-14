import subprocess
import threading
import time
import os
import signal
import re
from typing import Optional, Dict, List
from sources.logger import Logger


class PersistentTerminal:
    def __init__(self, work_dir: str = None):
        self.work_dir = work_dir or os.getcwd()
        self.logger = Logger("terminal.log")
        self.processes: Dict[str, dict] = {}
        self.max_processes = 5
        self.output_buffer_size = 5000

    def run_command(self, command: str, timeout: int = 30) -> dict:
        self.logger.info(f"Running command: {command}")

        install_patterns = [
            r'^pip\s+install',
            r'^pip3\s+install',
            r'^npm\s+install',
            r'^yarn\s+add',
            r'^apt-get\s+install',
            r'^apt\s+install',
        ]
        is_install = any(re.match(p, command.strip()) for p in install_patterns)

        if is_install:
            if command.strip().startswith(('pip install', 'pip3 install')):
                command = command.strip().replace(' --break-system-packages', '')

        env = os.environ.copy()
        env['PYTHONDONTWRITEBYTECODE'] = '1'

        try:
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self.work_dir,
                env=env,
                preexec_fn=os.setsid if os.name != 'nt' else None
            )

            try:
                stdout, stderr = process.communicate(timeout=timeout)
                stdout_text = stdout.decode('utf-8', errors='replace')[-self.output_buffer_size:]
                stderr_text = stderr.decode('utf-8', errors='replace')[-self.output_buffer_size:]

                result = {
                    'success': process.returncode == 0,
                    'stdout': stdout_text,
                    'stderr': stderr_text,
                    'returncode': process.returncode,
                    'command': command,
                    'timed_out': False
                }
                self.logger.info(f"Command completed: rc={process.returncode}")
                return result

            except subprocess.TimeoutExpired:
                if os.name != 'nt':
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                else:
                    process.kill()
                stdout, stderr = process.communicate()
                return {
                    'success': False,
                    'stdout': stdout.decode('utf-8', errors='replace')[-self.output_buffer_size:],
                    'stderr': f"Command timed out after {timeout}s",
                    'returncode': -1,
                    'command': command,
                    'timed_out': True
                }

        except Exception as e:
            self.logger.error(f"Command error: {str(e)}")
            return {
                'success': False,
                'stdout': '',
                'stderr': str(e),
                'returncode': -1,
                'command': command,
                'timed_out': False
            }

    def start_background_process(self, name: str, command: str) -> dict:
        if name in self.processes and self.processes[name].get('process'):
            proc = self.processes[name]['process']
            if proc.poll() is None:
                return {
                    'success': True,
                    'message': f'Process {name} already running (PID: {proc.pid})',
                    'pid': proc.pid
                }

        if len(self.processes) >= self.max_processes:
            self._cleanup_dead_processes()

        self.logger.info(f"Starting background process '{name}': {command}")
        env = os.environ.copy()

        try:
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self.work_dir,
                env=env,
                preexec_fn=os.setsid if os.name != 'nt' else None
            )

            self.processes[name] = {
                'process': process,
                'command': command,
                'started': time.time(),
                'output_lines': []
            }

            output_thread = threading.Thread(
                target=self._capture_output,
                args=(name, process),
                daemon=True
            )
            output_thread.start()

            time.sleep(1)
            if process.poll() is not None:
                stdout, stderr = process.communicate()
                return {
                    'success': False,
                    'message': f'Process exited immediately',
                    'stdout': stdout.decode('utf-8', errors='replace'),
                    'stderr': stderr.decode('utf-8', errors='replace'),
                    'pid': process.pid
                }

            return {
                'success': True,
                'message': f'Process {name} started (PID: {process.pid})',
                'pid': process.pid
            }

        except Exception as e:
            return {
                'success': False,
                'message': f'Failed to start: {str(e)}',
                'pid': None
            }

    def _capture_output(self, name: str, process: subprocess.Popen):
        try:
            while process.poll() is None:
                line = process.stdout.readline()
                if line:
                    decoded = line.decode('utf-8', errors='replace').strip()
                    if name in self.processes:
                        lines = self.processes[name]['output_lines']
                        lines.append(decoded)
                        if len(lines) > 100:
                            self.processes[name]['output_lines'] = lines[-50:]
        except Exception:
            pass

    def get_process_output(self, name: str, last_n: int = 20) -> dict:
        if name not in self.processes:
            return {'success': False, 'message': f'No process named {name}', 'output': ''}

        proc_info = self.processes[name]
        process = proc_info['process']
        is_running = process.poll() is None
        lines = proc_info.get('output_lines', [])

        return {
            'success': True,
            'running': is_running,
            'output': '\n'.join(lines[-last_n:]),
            'pid': process.pid,
            'uptime': time.time() - proc_info['started'] if is_running else 0
        }

    def stop_process(self, name: str) -> dict:
        if name not in self.processes:
            return {'success': False, 'message': f'No process named {name}'}

        process = self.processes[name]['process']
        if process.poll() is not None:
            del self.processes[name]
            return {'success': True, 'message': f'Process {name} already stopped'}

        try:
            if os.name != 'nt':
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            else:
                process.terminate()
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            if os.name != 'nt':
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            else:
                process.kill()
        except Exception as e:
            self.logger.warning(f"Error stopping {name}: {e}")

        del self.processes[name]
        return {'success': True, 'message': f'Process {name} stopped'}

    def stop_all(self):
        names = list(self.processes.keys())
        for name in names:
            self.stop_process(name)

    def _cleanup_dead_processes(self):
        dead = [name for name, info in self.processes.items()
                if info['process'].poll() is not None]
        for name in dead:
            del self.processes[name]

    def list_processes(self) -> List[dict]:
        self._cleanup_dead_processes()
        result = []
        for name, info in self.processes.items():
            proc = info['process']
            result.append({
                'name': name,
                'command': info['command'],
                'pid': proc.pid,
                'running': proc.poll() is None,
                'uptime': time.time() - info['started']
            })
        return result

    def install_package(self, package_name: str, package_manager: str = "pip") -> dict:
        if package_manager == "pip":
            cmd = f"pip install {package_name}"
        elif package_manager == "npm":
            cmd = f"npm install {package_name}"
        else:
            return {'success': False, 'stderr': f'Unknown package manager: {package_manager}'}

        self.logger.info(f"Installing package: {cmd}")
        return self.run_command(cmd, timeout=60)

    def check_port(self, port: int) -> bool:
        result = self.run_command(f"lsof -i :{port}", timeout=5)
        return bool(result['stdout'].strip())

    def format_result(self, result: dict) -> str:
        if result['success']:
            output = result.get('stdout', '') or result.get('message', 'Success')
            return f"[SUCCESS] {output}"
        else:
            error = result.get('stderr', '') or result.get('message', 'Failed')
            return f"[ERROR] {error}"
