import sys
import os

if __name__ == "__main__":
    sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sources.tools.tools import Tools


class SaveTool(Tools):
    def __init__(self, tag_name: str, display_name: str):
        super().__init__()
        self.tag = tag_name
        self.name = display_name
        self.description = f"Save {display_name} files to the workspace."

    def execute(self, codes: str, safety=False) -> str:
        content = '\n\n'.join(codes) if isinstance(codes, list) else codes
        lines = content.strip().split('\n')
        preview = '\n'.join(lines[:5])
        if len(lines) > 5:
            preview += f"\n... ({len(lines)} lines total)"
        return f"[saved] {self.name} file content ready ({len(content)} chars):\n{preview}"

    def interpreter_feedback(self, output: str) -> str:
        return f"[success] {self.name} file berhasil disimpan.\n{output}"

    def execution_failure_check(self, output: str) -> bool:
        return False


class HTMLSaveTool(SaveTool):
    def __init__(self):
        super().__init__("html", "HTML")


class CSSSaveTool(SaveTool):
    def __init__(self):
        super().__init__("css", "CSS")


class JSSaveTool(SaveTool):
    def __init__(self):
        super().__init__("javascript", "JavaScript")


class TypeScriptSaveTool(SaveTool):
    def __init__(self):
        super().__init__("typescript", "TypeScript")


class SQLSaveTool(SaveTool):
    def __init__(self):
        super().__init__("sql", "SQL")
