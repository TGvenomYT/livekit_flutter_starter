import asyncio
import logging
import uuid
from typing import Optional

from livekit.agents import llm
from livekit.agents.voice import AgentSession
from opencode_tools import OpenCodeTools

logger = logging.getLogger("jarvis.tools")


class AsyncOpenCodeTools(OpenCodeTools):
    """OpenCode tools plus a fire-and-forget background command runner.

    `session` is injected by the entrypoint after AgentSession is created, so a
    finished background task can proactively make Jarvis speak.
    """

    def __init__(self):
        super().__init__()
        self.session: Optional[AgentSession] = None

    @llm.function_tool(
        description=(
            "Start a long-running shell command in the background and return "
            "immediately. Jarvis will announce the result out loud when it "
            "finishes. Use ONLY for commands the user asks for that are expected "
            "to take a while (builds, installs, downloads, long scripts)."
        )
    )
    async def run_command_background(self, command: str) -> str:
        task_id = str(uuid.uuid4())[:8]
        logger.info("bg command %s: %s", task_id, command)
        asyncio.create_task(self._run_background_command(task_id, command))
        return (
            f"Started '{command}' in the background (task {task_id}). "
            "Tell the user it's running and you'll report back when it's done."
        )

    async def _run_background_command(self, task_id: str, command: str) -> None:
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=self._workspace,
            )
            stdout, _ = await proc.communicate()
            out = (stdout or b"").decode(errors="replace").strip()
            tail = out[-600:] if len(out) > 600 else out
            result = (
                f"Task {task_id} ('{command}') finished with exit code "
                f"{proc.returncode}."
            )
            if tail:
                result += f" Output: {tail}"
        except Exception as e:
            result = f"Task {task_id} ('{command}') failed to run: {e}"

        logger.info(result)

        if self.session is not None:
            # 1.x-correct way to inject context AND trigger speech. tool_choice
            # "none" so it just reports the result instead of chaining more tools.
            try:
                await self.session.generate_reply(
                    instructions=(
                        "A background task just finished. Briefly tell the user "
                        f"the outcome in one spoken sentence. Result: {result}"
                    ),
                    tool_choice="none",
                    allow_interruptions=True,
                )
            except Exception as e:
                logger.warning("failed to announce bg task %s: %s", task_id, e)
