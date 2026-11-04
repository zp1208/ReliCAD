# -*- coding: utf-8 -*-
"""
MCPBase — mcp_bridge 的连接层。

职责：
  1. 服务发现：通过 AuraFriday 原生消息协议找到 MCP-Link 服务器的 URL 和 Token
  2. 连接管理：懒加载 SSE 长连接，维护 session_id 和响应队列
  3. 命令执行：execute(command) 将任意命令封装成 JSON-RPC，发往 "fusion360" 工具
  4. 引用生成：_next_ref(prefix) 产生唯一的 Fusion context 存储键

仅使用 Python 标准库，无第三方依赖。
"""

import http.client
import json
import os
import platform
import queue
import re
import ssl
import struct
import subprocess
import threading
import uuid
from pathlib import Path
from urllib.parse import urlparse

_MM = 0.1  # mm -> cm, Fusion 360 internal length unit
_DEFAULT_DIRECT_URL = "http://127.0.0.1:8765/execute"


class MCPBase:
    """所有功能 Mixin 的公共基类，提供 MCP 协议的连接与执行能力。"""

    # ── 全局计数器（类变量，跨实例共享，确保 store key 唯一）─────────────
    _cnt_lock: threading.Lock = threading.Lock()
    _cnt: int = 0

    # ──────────────────────────────────────────────────────────────────────
    # 初始化
    # ──────────────────────────────────────────────────────────────────────

    def __init__(
        self,
        server_url: str | None = None,
        auth_token: str | None = None,
        *,
        transport: str = "direct",
        direct_url: str | None = None,
    ):
        """初始化 MCPBase。

        Args:
            server_url:  直接指定 MCP-Link 的 SSE 端点 URL（测试时绕过服务发现）。
            auth_token:  直接指定 Authorization Bearer token。
        """
        transport_norm = str(transport).strip().lower()
        if transport_norm not in ("mcp", "direct"):
            raise ValueError("transport must be 'mcp' or 'direct'.")

        self._transport: str = transport_norm
        self._direct_url: str = direct_url or _DEFAULT_DIRECT_URL
        self._url: str | None = server_url
        self._token: str | None = auth_token
        self._sse: dict | None = None       # SSE 状态包，None 表示未连接
        self._lock = threading.Lock()       # 防止并发重复建连
        self._fusion_token: str | None = None  # fusion360 工具的 unlock token（首次调用时自动发现）
        self._sketch_transforms: dict = {}  # 存储每个草图的坐标转换信息

        # 继续协作式初始化链：MCPBase 已消费自己的具名参数，
        # 无参调用让 MRO 中排在其后的 mixin（如 MCPEvidence）得以初始化。
        super().__init__()

    # ──────────────────────────────────────────────────────────────────────
    # 服务发现
    # ──────────────────────────────────────────────────────────────────────

    def _discover_server(self) -> tuple[str, str]:
        """通过 AuraFriday 原生消息协议发现 MCP-Link 服务器。

        Returns:
            (url, auth_token) 元组。

        Raises:
            ConnectionError: 找不到 manifest 文件或运行 binary 失败。
        """
        manifest_path = self._find_manifest()
        if manifest_path is None:
            raise ConnectionError(
                "找不到 AuraFriday 原生消息 manifest 文件。"
                "请确认 MCP-Link 已安装并运行。\n"
                f"Windows 预期路径: %LOCALAPPDATA%\\AuraFriday\\com.aurafriday.shim.json"
            )

        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ConnectionError(f"读取 manifest 文件失败: {exc}") from exc

        binary_path = manifest.get("path")
        if not binary_path or not Path(binary_path).exists():
            raise ConnectionError(
                f"manifest 中的 binary 路径不存在: {binary_path}"
            )

        config = self._run_binary(binary_path)
        if config is None:
            raise ConnectionError(
                "运行 AuraFriday binary 失败，无法获取服务器配置。"
            )

        # 提取第一个服务器的 url 和 Authorization
        mcp_servers = config.get("mcpServers", {})
        if not mcp_servers:
            raise ConnectionError("服务器配置中缺少 mcpServers 字段。")

        server_cfg = next(iter(mcp_servers.values()))
        url = server_cfg.get("url")
        token = server_cfg.get("headers", {}).get("Authorization")

        if not url or not token:
            raise ConnectionError(
                f"服务器配置缺少 url 或 Authorization: {server_cfg}"
            )

        return url, token

    def _find_manifest(self) -> Path | None:
        """在操作系统预期位置查找 AuraFriday manifest 文件。"""
        system = platform.system().lower()
        candidates: list[Path] = []

        if system == "windows":
            local_appdata = os.environ.get("LOCALAPPDATA")
            if local_appdata:
                candidates.append(
                    Path(local_appdata) / "AuraFriday" / "com.aurafriday.shim.json"
                )
            # 兜底路径
            candidates.append(
                Path.home() / "AppData" / "Local" / "AuraFriday" / "com.aurafriday.shim.json"
            )
        elif system == "darwin":
            for browser in ("Google/Chrome", "Chromium"):
                candidates.append(
                    Path.home() / "Library" / "Application Support"
                    / browser / "NativeMessagingHosts" / "com.aurafriday.shim.json"
                )
        else:
            for browser in ("google-chrome", "chromium"):
                candidates.append(
                    Path.home() / ".config" / browser
                    / "NativeMessagingHosts" / "com.aurafriday.shim.json"
                )

        for path in candidates:
            if path.exists():
                return path
        return None

    def _run_binary(self, binary_path: str) -> dict | None:
        """运行 AuraFriday native binary，读取 Chrome 原生消息格式的 JSON 配置。

        协议：4 字节小端无符号整数（消息长度）+ UTF-8 JSON 正文。

        Returns:
            解析后的配置字典，失败返回 None。
        """
        creation_flags = 0
        if platform.system() == "Windows":
            try:
                creation_flags = subprocess.CREATE_NO_WINDOW
            except AttributeError:
                pass

        try:
            proc = subprocess.Popen(
                [binary_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE,
                bufsize=0,
                creationflags=creation_flags,
            )
        except OSError:
            return None

        try:
            # communicate(timeout=5) 整体读取，避免 read() 无限阻塞
            stdout, _ = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            return None
        except Exception:
            return None
        finally:
            try:
                proc.terminate()
            except Exception:
                pass

        # 解析 4 字节小端长度前缀
        if len(stdout) < 4:
            return None
        msg_len = struct.unpack("<I", stdout[:4])[0]
        if msg_len <= 0 or msg_len > 10_000_000:
            return None
        raw_bytes = stdout[4: 4 + msg_len]
        if len(raw_bytes) != msg_len:
            return None

        # 解码并解析 JSON
        text = raw_bytes.decode("utf-8", errors="replace")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # JSON 被截断时，用正则兜底提取关键字段
            return self._extract_truncated(text)

    def _extract_truncated(self, text: str) -> dict | None:
        """从截断的 JSON 文本中提取 url 和 Authorization（兜底策略）。"""
        url_match = re.search(r'"url"\s*:\s*"(https?://[^"]+)"', text)
        auth_match = re.search(r'"Authorization"\s*:\s*"(Bearer\s+[^"]+)"', text)
        name_match = re.search(r'"mcpServers"\s*:\s*\{\s*"([^"]+)"', text)

        if not url_match or not auth_match:
            return None

        server_name = name_match.group(1) if name_match else "server"
        return {
            "mcpServers": {
                server_name: {
                    "url": url_match.group(1),
                    "headers": {"Authorization": auth_match.group(1)},
                }
            }
        }

    # ──────────────────────────────────────────────────────────────────────
    # 连接管理
    # ──────────────────────────────────────────────────────────────────────

    def _ensure_connected(self):
        """确保 SSE 连接可用（双重检查锁，懒加载）。

        Raises:
            ConnectionError: 服务发现或 SSE 连接失败。
        """
        # 快速路径：已连接且 reader 线程存活
        if self._sse is not None and self._sse["thread"].is_alive():
            return

        with self._lock:
            # 再次检查，防止多线程重复建连
            if self._sse is not None and self._sse["thread"].is_alive():
                return

            if not self._url or not self._token:
                self._url, self._token = self._discover_server()

            self._sse = self._connect_sse(self._url, self._token)

    def _connect_sse(self, url: str, token: str) -> dict:
        """建立 SSE 长连接，读取 session_id，启动响应分发线程。

        Args:
            url:   MCP-Link SSE 端点 URL（https 或 http）。
            token: Authorization Bearer token。

        Returns:
            SSE 状态包字典。

        Raises:
            ConnectionError: 连接失败或未收到 endpoint 事件。
        """
        parsed = urlparse(url)
        host = parsed.netloc
        path = parsed.path or "/"

        # 建立 HTTP 连接（HTTPS 忽略自签名证书，适配 .local 域名）
        if parsed.scheme == "https":
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            conn = http.client.HTTPSConnection(host, context=ctx, timeout=15)
        else:
            conn = http.client.HTTPConnection(host, timeout=15)

        try:
            conn.request(
                "GET", path,
                headers={
                    "Accept": "text/event-stream",
                    "Cache-Control": "no-cache",
                    "Authorization": token,
                },
            )
            resp = conn.getresponse()
        except Exception as exc:
            conn.close()
            raise ConnectionError(f"SSE 连接失败 ({url}): {exc}") from exc

        if resp.status != 200:
            conn.close()
            raise ConnectionError(
                f"SSE 服务器返回非 200 状态码: {resp.status}"
            )

        # 读取初始事件，找到 endpoint（包含 session_id）
        message_endpoint: str | None = None
        session_id: str | None = None
        event_type: str | None = None

        for _ in range(30):
            line = resp.readline().decode("utf-8", errors="replace").strip()
            if line.startswith("event:"):
                event_type = line[6:].strip()
            elif line.startswith("data:") and event_type == "endpoint":
                data = line[5:].strip()
                # data 形如 /messages/?session_id=xxxx
                message_endpoint = data
                m = re.search(r"session_id=([^&\s]+)", data)
                if m:
                    session_id = m.group(1)
                break

        if not message_endpoint or not session_id:
            conn.close()
            raise ConnectionError(
                "未从 SSE 流收到 endpoint 事件，MCP-Link 可能未就绪。"
            )

        # 准备并发基础设施
        pending: dict[str, queue.Queue] = {}
        pending_lock = threading.Lock()
        stop_event = threading.Event()

        def _reader():
            """后台线程：持续读 SSE 行，按 id 把响应分发到对应 Queue。"""
            try:
                while not stop_event.is_set():
                    try:
                        line = resp.readline()
                    except Exception:
                        break
                    if not line:
                        break

                    line_str = line.decode("utf-8", errors="replace").strip()
                    if not line_str.startswith("data:"):
                        continue

                    data_str = line_str[5:].strip()
                    try:
                        payload = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    req_id = payload.get("id")
                    if req_id:
                        with pending_lock:
                            q = pending.get(req_id)
                        if q is not None:
                            q.put(payload)
            except Exception:
                pass    # 线程退出，_ensure_connected 下次调用时会重连

        reader_thread = threading.Thread(target=_reader, daemon=True)
        reader_thread.start()

        return {
            "conn": conn,
            "response": resp,
            "endpoint": message_endpoint,   # 相对路径，如 /messages/?session_id=xxx
            "session_id": session_id,
            "pending": pending,
            "pending_lock": pending_lock,
            "thread": reader_thread,
            "stop_event": stop_event,
            "host": host,
            "scheme": parsed.scheme,
            "token": token,
        }

    def close(self):
        """停止 reader 线程，关闭连接，重置状态。"""
        if self._sse is None:
            return
        sse = self._sse
        self._sse = None

        sse["stop_event"].set()
        try:
            sse["response"].close()
        except Exception:
            pass
        try:
            sse["conn"].close()
        except Exception:
            pass
        sse["thread"].join(timeout=3)

    # ──────────────────────────────────────────────────────────────────────
    # 命令执行
    # ──────────────────────────────────────────────────────────────────────

    def _discover_fusion_token(self):
        """发送 readme 操作获取 fusion360 工具的 unlock token。

        readme 操作无需 token 即可调用（官方文档明确说明 readme 豁免）。
        成功后将 token 存入 self._fusion_token，后续所有 execute() 调用自动注入。
        """
        sse = self._sse
        req_id = str(uuid.uuid4())
        response_q: queue.Queue = queue.Queue()

        with sse["pending_lock"]:
            sse["pending"][req_id] = response_q

        body = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "method": "tools/call",
                "params": {"name": "fusion360", "arguments": {"operation": "readme"}},
            },
            ensure_ascii=False,
        ).encode("utf-8")

        try:
            self._post(body, sse)
            try:
                raw = response_q.get(timeout=10)
            except queue.Empty:
                return   # token 发现失败，后续调用会返回有意义的错误
        finally:
            with sse["pending_lock"]:
                sse["pending"].pop(req_id, None)

        # 从返回文本中提取 token（格式："tool_unlock_token for this installation is: <token>"）
        result = raw.get("result", {})
        content = result.get("content") or []
        text = content[0].get("text", "") if content else ""

        m = re.search(r"tool_unlock_token[^:]*:\s*([a-f0-9]{6,})", text)
        if m:
            self._fusion_token = m.group(1)

    def execute(self, command: dict, timeout: float = 30.0) -> dict:
        """发送命令到 Fusion 360，返回解析后的结果。

        command 是直接传给 Fusion 端的参数字典，支持两种格式：

        格式一 — 通用 API 调用（最常用）::

            {
                "api_path": "design.rootComponent.sketches.add",
                "args": ["design.rootComponent.xYConstructionPlane"],
                "store_as": "my_sketch",        # 可选
                "return_properties": ["name"],  # 可选
            }

        格式二 — Python 代码执行（需要 ValueInput 等复杂对象时）::

            {
                "operation": "execute_python",
                "code": "sketch = design.rootComponent.sketches.add(...)",
                "session_id": "my_session",     # 可选
            }

        execute() 不解析 command，只负责封包发送。
        所有解析和执行逻辑在 Fusion 端 mcp_integration.py 中。

        Args:
            command: 发往 Fusion 360 的命令字典。
            timeout: 等待 Fusion 响应的超时秒数（默认 30 秒）。

        Returns:
            {"success": True, "data": ...}

        Raises:
            ConnectionError: 无法连接到 MCP-Link 服务器。
            TimeoutError:    Fusion 360 在 timeout 秒内未响应。
            RuntimeError:    Fusion 360 返回错误（isError=True）。
        """
        if self._transport == "direct":
            return self._execute_direct(command, timeout)

        self._ensure_connected()

        # 首次调用时自动发现 fusion360 工具的 unlock token
        if self._fusion_token is None:
            self._discover_fusion_token()

        # 将 token 注入 command（readme 操作本身不需要 token，跳过）
        if self._fusion_token and command.get("operation") != "readme":
            command = {**command, "tool_unlock_token": self._fusion_token}

        sse = self._sse
        req_id = str(uuid.uuid4())
        response_q: queue.Queue = queue.Queue()

        with sse["pending_lock"]:
            sse["pending"][req_id] = response_q

        body = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "method": "tools/call",
                "params": {"name": "fusion360", "arguments": command},
            },
            ensure_ascii=False,
        ).encode("utf-8")

        try:
            self._post(body, sse)
            try:
                raw = response_q.get(timeout=timeout)
            except queue.Empty:
                raise TimeoutError(
                    f"Fusion 360 在 {timeout} 秒内未响应，命令: {command}"
                )
        finally:
            with sse["pending_lock"]:
                sse["pending"].pop(req_id, None)

        return self._parse(raw)

    def _execute_direct(self, command: dict, timeout: float = 30.0) -> dict:
        """Send a command directly to the local Fusion HTTP endpoint."""
        parsed = urlparse(self._direct_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError(f"Invalid direct_url: {self._direct_url!r}")

        path = parsed.path or "/execute"
        if parsed.query:
            path = f"{path}?{parsed.query}"

        body = json.dumps({"command": command}, ensure_ascii=False).encode("utf-8")

        if parsed.scheme == "https":
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            conn = http.client.HTTPSConnection(parsed.netloc, context=ctx, timeout=timeout)
        else:
            conn = http.client.HTTPConnection(parsed.netloc, timeout=timeout)

        try:
            conn.request(
                "POST",
                path,
                body=body,
                headers={
                    "Content-Type": "application/json",
                    "Content-Length": str(len(body)),
                },
            )
            resp = conn.getresponse()
            raw_body = resp.read()
        except Exception as exc:
            raise ConnectionError(
                f"Direct HTTP request failed ({self._direct_url}): {exc}"
            ) from exc
        finally:
            try:
                conn.close()
            except Exception:
                pass

        text = raw_body.decode("utf-8", errors="replace")
        if resp.status != 200:
            message = text
            try:
                error_payload = json.loads(text)
                message = error_payload.get("error") or error_payload.get("message") or text
            except Exception:
                pass
            raise ConnectionError(
                f"Direct HTTP request failed ({self._direct_url}): "
                f"HTTP {resp.status}: {message}"
            )

        try:
            direct_result = json.loads(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Direct HTTP response was not valid JSON ({self._direct_url}): {text}"
            ) from exc

        if "result" in direct_result or "error" in direct_result:
            raw = direct_result
        else:
            raw = {"result": direct_result}
        return self._parse(raw)

    def _post(self, body: bytes, sse: dict):
        """向 message_endpoint 发送 JSON-RPC 请求（每次新建短连接）。

        Args:
            body: 已编码的 JSON-RPC 请求体。
            sse:  当前 SSE 状态包（提供 host/scheme/endpoint/token）。

        Raises:
            ConnectionError: POST 请求失败或服务器返回非 202 状态码。
        """
        host = sse["host"]
        scheme = sse["scheme"]
        endpoint = sse["endpoint"]
        token = sse["token"]

        if scheme == "https":
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            post_conn = http.client.HTTPSConnection(host, context=ctx, timeout=10)
        else:
            post_conn = http.client.HTTPConnection(host, timeout=10)

        try:
            post_conn.request(
                "POST",
                endpoint,
                body=body,
                headers={
                    "Content-Type": "application/json",
                    "Content-Length": str(len(body)),
                    "Authorization": token,
                },
            )
            resp = post_conn.getresponse()
            resp.read()  # 消耗响应体，避免连接泄漏
            if resp.status != 202:
                raise ConnectionError(
                    f"POST 到 {endpoint} 返回非 202 状态码: {resp.status}"
                )
        except ConnectionError:
            raise
        except Exception as exc:
            raise ConnectionError(f"POST 请求失败: {exc}") from exc
        finally:
            try:
                post_conn.close()
            except Exception:
                pass

    def _parse(self, raw: dict) -> dict:
        """解析 Fusion 360 工具的响应，错误时直接抛出异常。

        Args:
            raw: SSE 流返回的原始 JSON-RPC 响应字典。

        Returns:
            {"success": True, "data": ...}

        Raises:
            RuntimeError: Fusion 360 返回错误，或 MCP 协议层返回 error 字段。
        """
        # JSON-RPC 协议层错误（服务器返回 "error" key 而非 "result"）
        if "error" in raw and "result" not in raw:
            err = raw["error"]
            msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
            raise RuntimeError(f"MCP 协议错误: {msg}")

        result = raw.get("result", {})
        is_err = result.get("isError", False)
        content = result.get("content") or []
        text = content[0].get("text", "") if content else ""

        if is_err:
            try:
                error_msg = json.loads(text).get("error", text)
            except Exception:
                error_msg = text
            raise RuntimeError(f"Fusion 360 错误: {error_msg}")

        # 成功：尝试把 text 当 JSON 解析（execute_python 返回 JSON）；
        # 否则将原始文本作为 data 返回
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            data = {"text": text}

        return {"success": True, "data": data}

    # ──────────────────────────────────────────────────────────────────────
    # 工具方法
    # ──────────────────────────────────────────────────────────────────────

    def _next_ref(self, prefix: str) -> str:
        """生成唯一的 Fusion context 存储键，如 'sketch_0'、'line_1'。

        使用类级全局计数器，确保多实例也不产生重名 key。
        """
        with MCPBase._cnt_lock:
            n = MCPBase._cnt
            MCPBase._cnt += 1
        return f"{prefix}_{n}"

    def _transform_point(self, point, sketch_ref):
        """Transform a sketch-local 2D/3D point in mm into Fusion 3D coordinates in cm."""
        H = self._sketch_transforms[sketch_ref]["homogeneous_matrix"]
        if len(point) not in (2, 3):
            raise ValueError("point must contain 2 or 3 numeric coordinates.")

        x = float(point[0]) * _MM
        y = float(point[1]) * _MM
        z = float(point[2]) * _MM if len(point) == 3 else 0.0

        x_new = H[0][0] * x + H[0][1] * y + H[0][2] * z + H[0][3]
        y_new = H[1][0] * x + H[1][1] * y + H[1][2] * z + H[1][3]
        z_new = H[2][0] * x + H[2][1] * y + H[2][2] * z + H[2][3]

        return (x_new, y_new, z_new)
