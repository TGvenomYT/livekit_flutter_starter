import asyncio
import os

from livekit.agents import llm

WORKSPACE = "/Users/niranjan/Documents/livekitJarvis_2.0"


class OpenCodeTools:
    """Local computer-control tools for Jarvis.

    Everything here is async so a tool call never blocks the voice pipeline
    (blocking subprocess/file IO on the event loop stutters STT/TTS/VAD).
    The descriptions deliberately tell the model to use these ONLY when the
    user explicitly asks to act on the computer — not for questions it can
    answer itself.
    """

    def __init__(self):
        self._workspace = WORKSPACE

    def _resolve(self, filepath: str) -> str:
        # Allow absolute paths; otherwise resolve inside the workspace.
        return filepath if os.path.isabs(filepath) else os.path.join(self._workspace, filepath)

    @llm.function_tool(
        description=(
            "Run a quick shell command on the user's Mac and return its output. "
            "Use ONLY when the user explicitly asks to run a command, check the "
            "system, or inspect files. Do not use it to answer general questions. "
            "For commands that take a long time, use run_command_background instead."
        )
    )
    async def run_command(self, command: str) -> str:
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=self._workspace,
            )
            try:
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=20)
            except asyncio.TimeoutError:
                proc.kill()
                return (
                    "That command is taking too long. Run it with "
                    "run_command_background if it is expected to be slow."
                )
            out = (stdout or b"").decode(errors="replace").strip()
            if not out:
                return f"Command finished (exit {proc.returncode}) with no output."
            # Keep spoken output digestible.
            return out if len(out) <= 1500 else out[:1500] + "\n…(truncated)"
        except Exception as e:
            return f"Failed to run command: {e}"

    @llm.function_tool(
        description=(
            "Read the contents of a local file. Use ONLY when the user asks you "
            "to look at or read a specific file."
        )
    )
    async def read_file(self, filepath: str) -> str:
        def _read() -> str:
            with open(self._resolve(filepath), "r", errors="replace") as f:
                return f.read()

        try:
            return await asyncio.to_thread(_read)
        except Exception as e:
            return f"Failed to read file: {e}"

    @llm.function_tool(
        description=(
            "Write text to a local file, overwriting it. Use ONLY when the user "
            "explicitly asks you to create or overwrite a file."
        )
    )
    async def write_file(self, filepath: str, content: str) -> str:
        def _write() -> None:
            path = self._resolve(filepath)
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(path, "w") as f:
                f.write(content)

        try:
            await asyncio.to_thread(_write)
            return "File written successfully."
        except Exception as e:
            return f"Failed to write file: {e}"
