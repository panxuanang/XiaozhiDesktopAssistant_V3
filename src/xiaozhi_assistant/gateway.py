from __future__ import annotations

import asyncio
import json
import logging
import random
import threading
from collections.abc import Callable

import websockets

from .paths import executable_command_for_mcp_server

logger = logging.getLogger(__name__)


class McpGateway:
    """Bridge Xiaozhi's WebSocket MCP endpoint to the bundled stdio FastMCP server."""

    def __init__(self, endpoint: str, on_status: Callable[[str], None] | None = None):
        self.endpoint = endpoint
        self.on_status = on_status or (lambda _: None)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._ws = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._thread_main, name="xiaozhi-mcp-gateway", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._loop and self._ws:
            try:
                asyncio.run_coroutine_threadsafe(self._ws.close(), self._loop)
            except Exception:
                pass
        self.on_status("已停止")

    def _thread_main(self) -> None:
        try:
            asyncio.run(self._run())
        except Exception as exc:
            logger.exception("gateway stopped")
            self.on_status(f"连接异常：{exc}")

    async def _run(self) -> None:
        self._loop = asyncio.get_running_loop()
        backoff = 1.0
        while not self._stop.is_set():
            if not self.endpoint.startswith(("ws://", "wss://")):
                self.on_status("MCP 地址未配置")
                return
            try:
                self.on_status("正在连接小智…")
                async with websockets.connect(self.endpoint, open_timeout=8, max_size=None) as ws:
                    self._ws = ws
                    self.on_status("已连接")
                    backoff = 1.0
                    await self._bridge(ws)
            except Exception as exc:
                if self._stop.is_set():
                    break
                logger.warning("WebSocket/MCP bridge failed: %s", exc)
                self.on_status(f"连接断开，{backoff:.0f}秒后重连")
                await asyncio.sleep(backoff * (1 + random.random() * 0.1))
                backoff = min(backoff * 2, 60)
            finally:
                self._ws = None

    async def _bridge(self, ws) -> None:
        cmd = executable_command_for_mcp_server()
        creationflags = 0
        startupinfo = None
        if __import__("os").name == "nt":
            import subprocess
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            startupinfo=startupinfo,
            creationflags=creationflags,
        )

        async def ws_to_proc():
            assert proc.stdin is not None
            async for message in ws:
                if isinstance(message, bytes):
                    data = message
                else:
                    data = message.encode("utf-8")
                proc.stdin.write(data + b"\n")
                await proc.stdin.drain()

        async def proc_to_ws():
            assert proc.stdout is not None
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                try:
                    payload = line.decode("utf-8").strip()
                except UnicodeDecodeError:
                    payload = line.decode("gbk", errors="replace").strip()
                if payload:
                    try:
                        obj = json.loads(payload)
                        result = obj.get("result", {}) if isinstance(obj, dict) else {}
                        if isinstance(result, dict) and "tools" in result:
                            self.on_status(f"已连接 · {len(result['tools'])} 个工具")
                    except Exception:
                        pass
                    await ws.send(payload)

        async def stderr_log():
            assert proc.stderr is not None
            while True:
                line = await proc.stderr.readline()
                if not line:
                    break
                logger.info("MCP: %s", line.decode("utf-8", errors="replace").rstrip())

        tasks = [asyncio.create_task(ws_to_proc()), asyncio.create_task(proc_to_ws()), asyncio.create_task(stderr_log())]
        try:
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                exc = task.exception()
                if exc:
                    raise exc
        finally:
            for task in tasks:
                task.cancel()
            if proc.returncode is None:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=3)
                except asyncio.TimeoutError:
                    proc.kill()
