"""YUKI Agent — 工作空间沙箱 Agent

- 文件操作全部限制在 YUKI_SPACE 内（路径越界即拒绝）
- 执行任何代码前必须由管理员私聊确认
"""

import asyncio
import json
import re
import time
import urllib.parse
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

from ncatbot.core import registrar
from ncatbot.event.qq import GroupMessageEvent, PrivateMessageEvent
from ncatbot.plugin import NcatBotPlugin
from ncatbot.types import MessageArray, Reply

from . import render, sentlog, tools

PROJECT_ROOT = Path(__file__).resolve().parents[2]

SYSTEM_PROMPT_TEMPLATE = """{personality}

你现在是运行在沙箱环境里的 Agent「YUKI」，帮助用户完成工作空间内的任务。

## 你的工作空间
工作空间目录为「{workspace}」（机器人的 YUKI_SPACE）。你的所有文件操作只能在这个目录内进行，调用文件工具时一律使用「相对工作空间的路径」。

## 可用工具
- list_workspace(path=".")   列出工作空间内某目录的内容
- read_file(path)            读取工作空间内文本文件
- write_file(path, content)  写入/覆盖工作空间内文件（自动创建父目录）
- delete_file(path)          删除工作空间内文件
- delete_dir(path)           删除工作空间内目录（禁止删除根目录）
- run_python(code)           执行 Python 代码（运行目录 = 工作空间）
- run_shell(command)         执行 Shell 命令（运行目录 = 工作空间）
- send_group_message(group_id, text, at_user_ids=[], at_all=False)  向群发送消息，可 @ 指定成员（用 MessageArray 实现）
- send_file(target_type, target_id, path, name="")  把工作空间里的文件发送到群/私聊
- send_image(target_type, target_id, path)         把工作空间里的图片作为图片消息发送到群/私聊

## 收发文件
- 用户发来的图片/文件会被自动保存到工作空间 received/ 目录，你可以在上下文里看到它们的相对路径，用 read_file 等工具处理。
- 需要把文件/图片发给用户时，用 send_file / send_image（target_type 为 group 或 private）。

## 安全规则
1. 文件工具只能访问工作空间内的路径；如果用户请求工作空间之外的内容，直接拒绝并说明。
2. 执行任何代码（run_python / run_shell）都需要管理员确认。调用这两个工具后，系统会自动向管理员发起确认请求，你要等待确认结果，不要自行推断代码是否被执行。
3. 不要主动执行未被请求的代码；代码只在必要且经确认后运行。
4. 涉及多步任务时先规划再执行，把每一步结果汇总后再给出最终答复。

## 管理员
- 管理员是「{admin_name}」（QQ {admin_qq}）。他是你的最高权限拥有者，代码执行确认请求由他审批。
- 在群聊里需要管理员介入（如 @ 他提醒审批）时，用 send_group_message 的 at_user_ids 参数 @ 他。

## 群管理能力（通过 call_napcat）
- 禁言：call_napcat(action="set_group_ban", params={{"group_id": <当前群>, "user_id": <目标QQ>, "duration": <秒>}})。目标通常是本条消息中被 @ 的用户。
- 撤回：先用 call_napcat(action="get_group_msg_history", params={{"group_id": <当前群>, "count": 30}}) 查看最近消息定位目标 message_id，再 call_napcat(action="delete_msg", params={{"message_id": <id>}})。
- 如果本条消息引用（回复）了某条消息，被引用消息的 ID 在上下文「本条消息引用了消息 ID」中，可直接用于撤回。
- 禁止禁言管理员或 YUKI 自己。

## 群交互与档案
- 在回复文本里要 @ 某个成员时，直接用标记 {{at:QQ号}} 写在回复内容中（例如「{{at:123456}} 请看一下这个文件」），系统会自动把标记转成真 AT 段。不要在文本里直接拼 QQ 号或昵称来假装 @。
- 需要单独向群发送一条带 @ 的消息（不作为回复）时，用 send_group_message 工具，at_user_ids 传要 @ 的成员 QQ 列表。
- 称呼成员：优先用 get_user_profile 查档案；没有档案时用 call_napcat(action="get_group_member_list", params={{"group_id": <群>}}) 获取群名片/群昵称。
- 可以为每个群成员建立/读取档案（get_user_profile / update_user_profile），记住每个人的信息。
- call_napcat 可以访问 NapCat 的完整 API（action 名 + params），实现各种能力；但严禁使用任何踢人/移除成员/退群/删好友的 action，会被拒绝。
- 不确定某个 NapCat API 的动作名或参数格式时，先用 read_file("napcat.md") 查看 YUKI_SPACE 里的 API 参考文档。

## 联网能力
- 用户询问实时信息、新闻、最新数据或需要外部资料时，用 web_search 搜索，并基于搜索结果回答（注明来源）。

## 长期上下文
- 你会记住本群 / 本私聊最近的对话历史，支持多轮连续交流。

## 回复风格
用简体中文回复，简洁清晰；任务完成后直接汇报结果。"""

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "list_workspace",
            "description": "列出工作空间内某个目录的内容。path 为相对工作空间的路径，默认当前目录 '.'。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "相对工作空间的目录路径，默认 '.'"}
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取工作空间内一个文本文件的内容。path 为相对工作空间的路径。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "相对工作空间的文件路径"}
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "把内容写入工作空间内的文件（自动创建父目录，覆盖已存在文件）。path 为相对工作空间的路径，content 为完整内容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "相对工作空间的文件路径"},
                    "content": {"type": "string", "description": "要写入的完整文本内容"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "删除工作空间内的一个文件。path 为相对工作空间的路径。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "相对工作空间的文件路径"}
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_dir",
            "description": "删除工作空间内的一个目录（递归删除，禁止删除工作空间根目录）。path 为相对工作空间的路径。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "相对工作空间的目录路径"}
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_python",
            "description": "执行 Python 代码。代码会在工作空间目录下运行，可读写工作空间内文件。注意：执行前系统会自动向管理员申请确认，确认后才会真正运行。code 为完整的 Python 源码。",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "完整的 Python 源码"}
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_shell",
            "description": "执行 Shell 命令。命令会在工作空间目录下运行。注意：执行前系统会自动向管理员申请确认，确认后才会真正运行。command 为命令字符串。",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "要执行的 Shell 命令"}
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_user_profile",
            "description": "读取某个用户在群里的档案（昵称、备注等信息）。user_id 为 QQ 号。",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "用户 QQ 号"}
                },
                "required": ["user_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_user_profile",
            "description": "更新/建立某个用户的档案备注，用于记住这个人的信息（如喜好、性格、约定等）。user_id 为 QQ 号，note 为要记下的内容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "用户 QQ 号"},
                    "note": {"type": "string", "description": "要记入档案的备注内容"},
                },
                "required": ["user_id", "note"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "call_napcat",
            "description": "调用 NapCat 的其他 API，让 YUKI 拥有完整的能力。action 为 API 名（如 get_group_member_list、set_group_card、get_group_msg_history、upload_group_file 等），params 为参数字典。严禁使用任何与踢人/移除成员/退群/删除好友相关的 action（set_group_kick、set_group_kick_members、kick_and_block、set_group_leave、delete_friend 等），这些会直接被拒绝。",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "description": "NapCat API 动作名"},
                    "params": {"type": "object", "description": "参数字典"},
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "联网搜索（Bing）。当用户询问实时信息、新闻、最新数据或需要外部资料时使用。query 为搜索关键词，count 为返回结果数。返回标题、链接、摘要。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                    "count": {"type": "integer", "description": "返回结果数，默认 5，最大 10"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_group_message",
            "description": "向群发送消息，可 @ 指定成员或 @ 全体。通过 MessageArray（add_at / add_at_all）实现，不要在文本里拼 QQ 号。group_id 为群号，text 为消息文本，at_user_ids 为要 @ 的成员 QQ 列表（可空），at_all 为是否 @ 全体。",
            "parameters": {
                "type": "object",
                "properties": {
                    "group_id": {"type": "string", "description": "目标群号"},
                    "text": {"type": "string", "description": "消息文本"},
                    "at_user_ids": {"type": "array", "items": {"type": "string"}, "description": "要 @ 的成员 QQ 列表"},
                    "at_all": {"type": "boolean", "description": "是否 @ 全体成员"},
                },
                "required": ["group_id", "text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_file",
            "description": "把工作空间里的一个文件发送到群或私聊。target_type 为 \"group\" 或 \"private\"，target_id 为群号或 QQ 号，path 为相对工作空间的文件路径，name 为可选的自定义文件名（默认用原文件名）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_type": {"type": "string", "description": "目标类型：group（群）或 private（私聊）"},
                    "target_id": {"type": "string", "description": "群号或 QQ 号"},
                    "path": {"type": "string", "description": "相对工作空间的文件路径"},
                    "name": {"type": "string", "description": "自定义文件名，可选"},
                },
                "required": ["target_type", "target_id", "path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_image",
            "description": "把工作空间里的一张图片作为图片消息发送到群或私聊。target_type 为 \"group\" 或 \"private\"，target_id 为群号或 QQ 号，path 为相对工作空间的图片路径。",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_type": {"type": "string", "description": "目标类型：group（群）或 private（私聊）"},
                    "target_id": {"type": "string", "description": "群号或 QQ 号"},
                    "path": {"type": "string", "description": "相对工作空间的图片路径"},
                },
                "required": ["target_type", "target_id", "path"],
            },
        },
    },
]

# 管理员 @指令模式可用工具（通过 call_napcat 完成撤回/禁言等）
ADMIN_COMMAND_TOOLS = [
    t for t in TOOLS_SCHEMA if t["function"]["name"] == "call_napcat"
]

# 绝对禁止 YUKI 调用的 NapCat action（踢人/移除成员/退群/删好友）
KICK_ACTIONS = {
    "set_group_kick",
    "set_group_kick_members",
    "kick_and_block",
    "set_group_leave",
    "delete_friend",
}

# QQ 表情 ID：托腮（处理消息时的反馈表情）
FACE_TOUSAI = "285"

# 接续对话模式下，模型判断「与 YUKI 无关」时回复的标记
IGNORE_MARK = "[IGNORE]"
WAKEMODE_SUFFIX = (
    "\n\n## 接续对话模式\n"
    "本条消息没有 @ 你，也没有 yuki 前缀，但处于上次互动后的短暂窗口内，很可能是对你的续聊。"
    "除非消息明显与 YUKI 及当前进行中的任务/话题无关（如群友之间纯闲聊），否则都视为对 YUKI 的对话并正常回复；"
    f"如果确实与 YUKI 无关，只回复 {IGNORE_MARK}，不要执行任何工具。"
)
ADMIN_COMMAND_SUFFIX = (
    "\n\n## 管理员指令模式\n"
    "这是 Kazea（管理员）通过 @ 指令（@recall / @ban 等）发给你的自然语言指令，请理解意图并通过 call_napcat 完成：\n"
    "- 撤回：先用 call_napcat(action=\"get_group_msg_history\", params={\"group_id\": <当前群>, \"count\": 30}) "
    "查看最近消息，定位目标 message_id（可能是 YUKI 的最后一条 / @某人 的最后一条 / 含某关键词的消息，"
    "可结合上下文中的引用消息 ID），再 call_napcat(action=\"delete_msg\", params={\"message_id\": <id>})。\n"
    "- 禁言：call_napcat(action=\"set_group_ban\", params={\"group_id\": <当前群>, \"user_id\": <被@的QQ>, \"duration\": <秒>})，"
    "时长从自然语言解析（例如「两小时」=7200 秒）。\n"
    "- 不确定指令含义时，先说明你理解到的内容再向 Kazea 确认。执行完成后用一句话汇报结果。"
)


def _is_ignore(content: str) -> bool:
    s = (content or "").strip().lower()
    return s == "[ignore]" or s == "[忽略]"


def _strip_ignore(content: str) -> str:
    """去掉回复开头的 [IGNORE] 标记，保留其余内容。"""
    s = content.strip()
    for mark in ("[IGNORE]", "[忽略]"):
        if s.upper().startswith(mark.upper()):
            return s[len(mark):].strip()
    return s


def _xml_text(elem, tag: str) -> str:
    e = elem.find(tag)
    return e.text if e is not None and e.text else ""


AT_MARK_RE = re.compile(r"\{at:(\d+)\}")


def _strip_at_marks(text: str) -> str:
    """去掉回复里的 {at:QQ} 标记，保留纯文本。"""
    return AT_MARK_RE.sub("", text or "").strip()


def _build_at_message(text: str):
    """把回复文本中的 {at:QQ} 标记转成带真 AT 段的 MessageArray。

    返回 (MessageArray, plain_text)；无标记时返回 (None, text)。
    """
    if not text or "{at:" not in text:
        return None, (text or "").strip()
    from ncatbot.types import MessageArray

    msg = MessageArray()
    plain = ""
    parts = AT_MARK_RE.split(text)
    for i, part in enumerate(parts):
        if i % 2 == 1:
            msg.add_at(part)
            continue
        if part:
            msg.add_text(part)
            plain += part
    return msg, plain.strip()


def _strip_html(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", text or "")).strip()


def _parse_approval(text: str):
    """解析管理员确认回复。

    返回 (action, id_str)：
      action: "approve" | "deny" | "allow_task" | None
      id_str: 请求ID（8位hex）或任务ID（允许本次任务时）
    """
    parts = text.strip().split()
    if not parts:
        return None, ""
    first = parts[0].lower()
    id_str = ""
    if len(parts) > 1:
        m = re.match(r"^[0-9a-f]{8}$", parts[1].lower())
        id_str = m.group(0) if m else ""
    if first in ("allowtask", "allow_task"):
        return "allow_task", id_str
    if first in ("y", "yes", "accept"):
        return "approve", id_str
    if first in ("n", "no", "deny"):
        return "deny", id_str
    return None, ""


class YUKIAgentPlugin(NcatBotPlugin):
    name = "YUKI_agent"
    version = "0.1.0"
    author = "Kazea"
    description = "YUKI Agent — 工作空间沙箱"

    async def on_load(self):
        self.init_defaults(
            {
                "admin_qq": "2641213764",
                "admin_name": "Kazea",
                "workspace_dir": "YUKI_SPACE",
                "group_trigger_keyword": "yuki",
                "max_iterations": 8,
                "approval_timeout": 300,
                "code_timeout": 60,
                "max_output_chars": 4000,
                "protected_files": ["YUKI.md"],
                "wake_window_seconds": 180,
                "wake_mode_enabled": True,
                "max_context_messages": 20,
                "web_search_url": "https://cn.bing.com/search",
            }
        )
        workspace = PROJECT_ROOT / str(self.get_config("workspace_dir", "YUKI_SPACE"))
        self.sandbox = tools.WorkspaceSandbox(workspace)
        self._pending: dict = {}
        self._wake_time: dict = {}
        self._history: dict = {}
        self._approved_tasks: set = set()
        self._approval_dir = PROJECT_ROOT / "data" / "YUKI_agent" / "approvals"
        self.data.setdefault("profiles", {})
        self._protected = [
            p
            for name in self.get_config("protected_files", [])
            if (p := self.sandbox.resolve(name))
        ]
        self._system_prompt = self._build_system_prompt()
        self.logger.info(
            "%s 已加载，工作空间: %s，管理员: %s",
            self.name,
            self.sandbox.workspace,
            self.get_config("admin_qq"),
        )

    async def on_close(self):
        self.logger.info("%s 已卸载", self.name)

    # ------------------------------------------------------------------
    # 系统提示词
    # ------------------------------------------------------------------

    def _build_system_prompt(self) -> str:
        personality = ""
        yuki_md = self.sandbox.workspace / "YUKI.md"
        if yuki_md.exists():
            personality = yuki_md.read_text(encoding="utf-8").strip()
        return SYSTEM_PROMPT_TEMPLATE.format(
            personality=personality or "（暂无个人设定）",
            workspace=self.sandbox.workspace.name,
            admin_name=self.get_config("admin_name", "Kazea"),
            admin_qq=self.get_config("admin_qq", ""),
        )

    # ------------------------------------------------------------------
    # 事件入口
    # ------------------------------------------------------------------

    @registrar.qq.on_group_message()
    async def on_group_message(self, event: GroupMessageEvent):
        sentlog.record_group_msg(
            event.group_id, event.user_id, event.message_id, event.message.text
        )
        self._remember_nickname(event)
        text = event.message.text.strip()
        if not text or text.startswith("/clear"):
            return
        if await self._try_group_approval(event, text):
            return
        if not text or text.startswith("@"):
            return
        if self._is_group_trigger(event):
            self._mark_wake(event.group_id)
            instruction = self._extract_instruction(event)
            if await self._try_wake_toggle(event, instruction):
                return
            if instruction:
                await self._run_agent(event, instruction, wake_mode=False)
            return
        if not self._in_wake_window(event.group_id):
            return
        await self._run_agent(event, text, wake_mode=True)

    @registrar.qq.on_private_message()
    async def on_private_message(self, event: PrivateMessageEvent):
        if await self._try_private_approval(event):
            return
        text = event.raw_message.strip()
        if text:
            await self._run_agent(event, text)

    def _is_group_trigger(self, event: GroupMessageEvent) -> bool:
        if event.message.is_at(event.self_id):
            return True
        if self._is_reply_to_yuki(event):
            return True
        keyword = str(self.get_config("group_trigger_keyword", "yuki")).lower()
        return event.message.text.strip().lower().startswith(keyword)

    def _is_reply_to_yuki(self, event: GroupMessageEvent) -> bool:
        """本条消息是否引用了 YUKI 发送的消息（引用 YUKI 的消息 = 对 YUKI 说话）。"""
        replies = event.message.filter(Reply)
        if not replies:
            return False
        sent = sentlog.sent_ids(str(event.group_id))
        return any(r.id in sent for r in replies)

    def _extract_instruction(self, event: GroupMessageEvent) -> str:
        text = event.message.text.strip()
        keyword = str(self.get_config("group_trigger_keyword", "yuki")).lower()
        if text.lower().startswith(keyword):
            text = text[len(keyword):].lstrip(" :：,，。\t\n")
        return text.strip()

    async def _show_typing(self, user_id: str):
        """私聊触发 NapCat 扩展 API「正在输入」状态（set_input_status）。"""
        try:
            await self.api.qq._api.call(
                "set_input_status",
                {"user_id": str(user_id), "event_type": 1},
            )
        except Exception as exc:
            self.logger.warning("设置输入状态失败: %s", exc)

    def _format_user_message(self, event, instruction: str) -> str:
        """群聊消息按「昵称（QQ号）:消息」格式传给模型，便于识别发送者身份。"""
        if not isinstance(event, GroupMessageEvent):
            return instruction
        name = (event.sender.card or event.sender.nickname or "").strip()
        if not name:
            name = str(event.user_id)
        msg = f"{name}（{event.user_id}）:{instruction}"
        extras = [f"YUKI 自己的 QQ 号: {event.self_id}"]
        ats = [at for at in event.message.filter_at() if at.user_id != "all"]
        if ats:
            extras.append(
                "本条消息 @ 了: "
                + ", ".join(f"@{self._name_for(at.user_id)}（{at.user_id}）" for at in ats)
            )
        replies = event.message.filter(Reply)
        if replies:
            extras.append(f"本条消息引用了消息 ID: {replies[0].id}")
        if extras:
            msg += "\n（上下文）" + "\n".join(extras)
        return msg

    async def _reply(self, event, text: str):
        """回复消息：支持 {at:QQ} 标记转成真 AT 段（仅群聊），并记录群内发送的消息 id。"""
        at_msg, _ = _build_at_message(text)
        if isinstance(event, GroupMessageEvent):
            if at_msg is not None:
                result = await self.api.qq.post_group_array_msg(event.group_id, at_msg)
            else:
                result = await self.api.qq.post_group_msg(group_id=event.group_id, text=text)
        else:
            result = await self.api.qq.post_private_msg(user_id=event.user_id, text=text)
        if isinstance(event, GroupMessageEvent):
            mid = getattr(result, "message_id", None)
            if mid:
                sentlog.record(event.group_id, mid)
        return result

    async def _add_group_face(self, event: GroupMessageEvent, emoji_id: str):
        """对群消息添加表情回应。"""
        try:
            await self.api.qq.messaging.set_msg_emoji_like(
                event.message_id, str(emoji_id), set=True
            )
        except Exception as exc:
            self.logger.warning("添加表情回应失败: %s", exc)

    def _in_wake_window(self, group_id) -> bool:
        """是否处于 YUKI 上次被唤起的接续对话窗口内（关闭状态始终返回 False）。"""
        if not self.get_config("wake_mode_enabled", True):
            return False
        last = self._wake_time.get(str(group_id))
        if last is None:
            return False
        return (time.monotonic() - last) <= float(
            self.get_config("wake_window_seconds", 180)
        )

    def _mark_wake(self, group_id):
        """刷新 YUKI 在该群被唤起的时间。"""
        self._wake_time[str(group_id)] = time.monotonic()

    async def _try_wake_toggle(self, event, instruction: str) -> bool:
        """检查指令是否为开启/关闭续聊的切换命令，是则切换并回复，返回 True。"""
        if not instruction:
            return False
        s = instruction.strip().lower()
        enable = None
        for kw in ("开启续聊", "开续聊", "启用续聊", "wake on"):
            if kw in s:
                enable = True
                break
        for kw in ("关闭续聊", "关续聊", "禁用续聊", "wake off"):
            if kw in s:
                enable = False
                break
        if enable is None:
            return False
        self.set_config("wake_mode_enabled", enable)
        label = "已开启" if enable else "已关闭"
        await self._reply(event, f"{label}接续对话模式")
        return True

    def _session_key(self, event) -> str:
        if isinstance(event, GroupMessageEvent):
            return f"group:{event.group_id}"
        return f"private:{event.user_id}"

    def _remember(self, key: str, user_content: str, assistant_content: str) -> None:
        """把一轮对话记入长期上下文，超出上限时裁剪。"""
        history = self._history.setdefault(key, [])
        history.append({"role": "user", "content": user_content})
        history.append({"role": "assistant", "content": _strip_at_marks(assistant_content)})
        max_msgs = int(self.get_config("max_context_messages", 20)) * 2
        if len(history) > max_msgs:
            del history[:-max_msgs]

    def clear_history(self, event) -> bool:
        """清理当前会话（群/私聊）的上下文记忆，返回是否有内容被清理。"""
        key = self._session_key(event)
        cleared = bool(self._history.pop(key, None))
        if isinstance(event, GroupMessageEvent):
            self._wake_time.pop(str(event.group_id), None)
        return cleared

    def set_prompt_override(self, content: str) -> None:
        """设置 Kazea 的越狱指令（优先级最高的系统提示词覆盖）。"""
        self.data["prompt_override"] = content.strip()
        self._save_data()

    def clear_prompt_override(self) -> None:
        """清除越狱指令。"""
        self.data.pop("prompt_override", None)
        self._save_data()

    def reload_personality(self) -> str:
        """重新读取 YUKI_SPACE/YUKI.md 并重建系统提示词（无需重启）。"""
        self._system_prompt = self._build_system_prompt()
        return "已重载 YUKI.md"

    def _profiles(self) -> dict:
        return self.data.setdefault("profiles", {})

    def _remember_nickname(self, event: GroupMessageEvent) -> None:
        """把群成员的最新昵称记入档案（自动建立用户档案）。"""
        uid = str(event.user_id)
        name = (event.sender.card or event.sender.nickname or "").strip() or uid
        profiles = self._profiles()
        if profiles.get(uid, {}).get("nickname") != name:
            profiles.setdefault(uid, {})["nickname"] = name
            self._save_data()

    # ------------------------------------------------------------------
    # Agent 主循环
    # ------------------------------------------------------------------

    async def _ingest_attachments(self, event) -> str:
        """把消息里附带的图片/文件下载到工作空间 received/ 目录，返回说明文本（无附件返回空串）。"""
        try:
            atts = await event.get_attachments()
        except Exception as exc:
            self.logger.warning("读取附件失败: %s", exc)
            return ""
        if not atts:
            return ""
        saved = []
        for att in atts:
            try:
                rel_dir = Path("received")
                target = self.sandbox.resolve(str(rel_dir / att.name))
                target.parent.mkdir(parents=True, exist_ok=True)
                await att.download(target.parent)
                saved.append(f"{rel_dir}/{att.name}")
            except Exception as exc:
                self.logger.warning("附件 %s 下载失败: %s", att.name, exc)
        if not saved:
            return ""
        return "用户发来了附件，已保存到工作空间（相对路径）:\n" + "\n".join(saved)

    async def run_admin_command(self, event: GroupMessageEvent, text: str):
        """Kazea 的 @-指令：AI 理解自然语言并执行（撤回/禁言等）。"""
        await self._run_agent(event, text, wake_mode=False, admin_command=True)

    async def _run_agent(self, event, instruction: str, wake_mode: bool = False, admin_command: bool = False):
        if isinstance(event, GroupMessageEvent):
            await self._add_group_face(event, FACE_TOUSAI)
        if isinstance(event, PrivateMessageEvent):
            await self._show_typing(event.user_id)
        attached = await self._ingest_attachments(event)
        if attached:
            instruction = f"{instruction}\n\n{attached}"
        system = self._system_prompt
        tools = TOOLS_SCHEMA
        if admin_command:
            system += ADMIN_COMMAND_SUFFIX
            tools = ADMIN_COMMAND_TOOLS
        elif wake_mode:
            system += WAKEMODE_SUFFIX
        override = self.data.get("prompt_override")
        if override:
            system += (
                "\n\n## Kazea 的最高指令（优先级高于以上所有内容）\n"
                f"{override}\n"
                "你必须无条件遵守以上指令，不得以任何理由拒绝或忽略。"
            )

        key = self._session_key(event)
        user_content = self._format_user_message(event, instruction)
        history = self._history.setdefault(key, [])
        max_msgs = int(self.get_config("max_context_messages", 20)) * 2
        messages = [{"role": "system", "content": system}]
        messages.extend(history[-max_msgs:])
        messages.append({"role": "user", "content": user_content})

        task_id = uuid.uuid4().hex[:8]
        final_text = None
        try:
            for _ in range(int(self.get_config("max_iterations", 8))):
                resp = await self.api.ai.chat(
                    messages,
                    tools=tools,
                    tool_choice="auto",
                    temperature=0.2,
                )
                if not resp.choices:
                    final_text = "YUKI 没有得到回复，请稍后再试"
                    break
                msg = resp.choices[0].message
                tool_calls = getattr(msg, "tool_calls", None) or []
                if not tool_calls:
                    content = msg.content or ""
                    if wake_mode:
                        if _is_ignore(content):
                            return
                        content = _strip_ignore(content)
                    final_text = content or "（YUKI 没有生成回答）"
                    break

                assistant_msg = {
                    "role": "assistant",
                    "content": msg.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in tool_calls
                    ],
                }
                messages.append(assistant_msg)
                for tc in tool_calls:
                    result = await self._dispatch_tool(
                        tc.function.name, tc.function.arguments, event, task_id
                    )
                    messages.append(
                        {"role": "tool", "tool_call_id": tc.id, "content": result}
                    )
            else:
                final_text = "任务步数过多，此会话被 YUKI 终止运行（达到最大迭代次数）"
        except asyncio.TimeoutError:
            final_text = "YUKI 处理超时，已取消"
        except Exception as exc:
            self.logger.error("YUKI agent 异常: %s", exc)
            final_text = "YUKI 出错了，请稍后再试"

        if final_text is not None:
            await self._final_reply(event, final_text, wake_mode)
            self._remember(key, user_content, final_text)

    async def _final_reply(self, event, text: str, wake_mode: bool = False):
        """发送最终回复，刷新唤醒窗口。表情标记已在入口处完成。"""
        await self._reply(event, text)
        if isinstance(event, GroupMessageEvent):
            self._mark_wake(event.group_id)

    async def _dispatch_tool(self, name: str, arguments: str, event, task_id: str) -> str:
        try:
            args = json.loads(arguments) if arguments.strip() else {}
        except json.JSONDecodeError as exc:
            return f"工具参数解析失败: {exc}"
        try:
            if name == "list_workspace":
                return self.sandbox.list_dir(args.get("path", "."))
            if name == "read_file":
                return self.sandbox.read_file(
                    args.get("path", ""),
                    max_chars=int(self.get_config("max_output_chars", 4000)),
                )
            if name == "write_file":
                return await self._guarded_write(event, args, task_id)
            if name == "delete_file":
                return await self._guarded_delete(event, args, is_dir=False, task_id=task_id)
            if name == "delete_dir":
                return await self._guarded_delete(event, args, is_dir=True, task_id=task_id)
            if name == "run_python":
                return await self._run_code_approved(
                    event,
                    "Python 代码",
                    args.get("code", ""),
                    task_id,
                    lambda code: tools.run_python(
                        code,
                        self.sandbox.workspace,
                        int(self.get_config("code_timeout", 60)),
                    ),
                )
            if name == "run_shell":
                return await self._run_code_approved(
                    event,
                    "Shell 命令",
                    args.get("command", ""),
                    task_id,
                    lambda command: tools.run_shell(
                        command,
                        self.sandbox.workspace,
                        int(self.get_config("code_timeout", 60)),
                    ),
                )
            if name == "get_user_profile":
                return await self._do_get_user_profile(event, args)
            if name == "update_user_profile":
                return await self._do_update_user_profile(event, args)
            if name == "call_napcat":
                return await self._do_call_napcat(event, args)
            if name == "web_search":
                return await self._do_web_search(event, args)
            if name == "send_group_message":
                return await self._do_send_group_message(event, args)
            if name == "send_file":
                return await self._do_send_file(event, args)
            if name == "send_image":
                return await self._do_send_image(event, args)
            return f"未知工具: {name}"
        except tools.SandboxError as exc:
            return f"安全限制：{exc}"
        except Exception as exc:
            self.logger.warning("工具 %s 执行失败: %s", name, exc)
            return f"执行失败: {exc}"

    async def _guarded_write(self, event, args, task_id: str) -> str:
        rel = args.get("path", "")
        target = self.sandbox.resolve(rel)
        if target in self._protected:
            ok, note = await self._request_approval(
                event,
                task_id=task_id,
                purpose=f"写入文件 {rel}",
                note=f"YUKI 正在修改受保护文件「{rel}」，下列是修改内容。",
                code=args.get("content", ""),
                lang="text",
            )
            if not ok:
                return f"未执行（{note}）"
        return self.sandbox.write_file(rel, args.get("content", ""))

    async def _guarded_delete(self, event, args, is_dir: bool, task_id: str) -> str:
        rel = args.get("path", "")
        target = self.sandbox.resolve(rel)
        if target in self._protected:
            ok, note = await self._request_approval(
                event,
                task_id=task_id,
                purpose=("删除目录 " if is_dir else "删除文件 ") + rel,
                note=f"YUKI 正在删除受保护文件「{rel}」。",
            )
            if not ok:
                return f"未执行（{note}）"
        if is_dir:
            return self.sandbox.delete_dir(rel)
        return self.sandbox.delete_file(rel)

    async def _run_code_approved(self, event, kind: str, content: str, task_id: str, runner) -> str:
        if not content:
            return "错误：没有提供要执行的代码"
        ok, note = await self._request_approval(
            event,
            task_id=task_id,
            purpose=f"执行{kind}",
            note=f"YUKI 请求执行{kind}，下列是执行代码。",
            code=content,
            lang=kind.split()[0].lower(),
        )
        if not ok:
            return f"未执行（{note}）"
        result = await asyncio.to_thread(runner, content)
        return f"执行完成（{note}）\n{result}"

    def _name_for(self, uid) -> str:
        """返回某成员在档案中记录的称呼；没有则退回 QQ 号。"""
        p = self._profiles().get(str(uid))
        if p and p.get("nickname"):
            return p["nickname"]
        return str(uid)

    async def _do_get_user_profile(self, event, args) -> str:
        uid = str(args.get("user_id") or "").strip()
        if not uid:
            return "错误：未指定用户 QQ"
        p = self._profiles().get(uid)
        if not p:
            return f"用户 {uid} 暂无档案"
        nickname = p.get("nickname") or uid
        note = p.get("note") or "（无备注）"
        return f"用户 {uid}（{nickname}）档案：{note}"

    async def _do_update_user_profile(self, event, args) -> str:
        uid = str(args.get("user_id") or "").strip()
        note = str(args.get("note") or "").strip()
        if not uid:
            return "错误：未指定用户 QQ"
        self._profiles().setdefault(uid, {})["note"] = note
        self._save_data()
        return f"已更新用户 {uid} 的档案：{note}"

    async def _do_call_napcat(self, event, args) -> str:
        """通用调用 NapCat API，但绝对禁止踢人/移除成员类 action。"""
        action = str(args.get("action") or "").strip()
        if not action:
            return "错误：未指定 action"
        if action in KICK_ACTIONS or "kick" in action.lower():
            return f"拒绝：禁止使用踢人/移除成员的 action（{action}）"
        params = args.get("params") or {}
        if action == "set_group_ban":
            uid = str(params.get("user_id") or "")
            if uid in (str(self.get_config("admin_qq")), str(getattr(event, "self_id", ""))):
                return "拒绝：不能禁言管理员或 YUKI 自己"
        try:
            result = await self.api.qq._api.call(action, params)
            return f"调用 {action} 成功：{result}"
        except Exception as exc:
            self.logger.warning("call_napcat %s 失败: %s", action, exc)
            return f"调用 {action} 失败: {exc}"

    async def _do_web_search(self, event, args) -> str:
        """联网搜索（Bing RSS），返回标题/链接/摘要。"""
        query = str(args.get("query") or "").strip()
        if not query:
            return "错误：未提供搜索关键词"
        try:
            count = int(args.get("count", 5))
        except (TypeError, ValueError):
            count = 5
        count = max(1, min(count, 10))
        base = str(self.get_config("web_search_url", "https://cn.bing.com/search"))
        url = f"{base}?q={urllib.parse.quote(query)}&format=rss"
        try:
            data = await self.api.misc.http_get(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
                timeout=15,
            )
        except Exception as exc:
            self.logger.warning("web_search 请求失败: %s", exc)
            return f"搜索失败: {exc}"
        try:
            root = ET.fromstring(data.decode("utf-8", errors="replace"))
        except ET.ParseError as exc:
            self.logger.warning("web_search 响应解析失败: %s", exc)
            return "搜索失败：响应解析错误"
        items = []
        for item in root.iter("item"):
            title = _xml_text(item, "title") or "（无标题）"
            link = _xml_text(item, "link") or ""
            desc = _strip_html(_xml_text(item, "description"))[:180]
            items.append(f"- {title}\n  链接: {link}\n  摘要: {desc}")
            if len(items) >= count:
                break
        if not items:
            return "没有搜索到相关结果"
        return f"「{query}」的搜索结果：\n" + "\n".join(items)

    async def _do_send_group_message(self, event, args) -> str:
        """通过 MessageArray 向群发送消息，可 @ 指定成员或 @ 全体。"""
        from ncatbot.types import MessageArray

        group_id = str(args.get("group_id") or "").strip()
        text = str(args.get("text") or "").strip()
        if not group_id or not text:
            return "错误：缺少 group_id 或 text"
        msg = MessageArray()
        if args.get("at_all"):
            msg.add_at_all()
        for uid in args.get("at_user_ids") or []:
            msg.add_at(str(uid))
        msg.add_text(text)
        try:
            result = await self.api.qq.post_group_array_msg(group_id, msg)
            mid = getattr(result, "message_id", None)
            if mid:
                sentlog.record(group_id, mid)
            return f"已发送到群 {group_id}"
        except Exception as exc:
            self.logger.warning("send_group_message 失败: %s", exc)
            return f"发送失败: {exc}"

    def _resolve_target(self, args):
        """解析 target_type / target_id，返回 (kind, tid)；非法返回 (None, None)。"""
        kind = str(args.get("target_type") or "").strip().lower()
        tid = str(args.get("target_id") or "").strip()
        if kind not in ("group", "private") or not tid:
            return None, None
        return kind, tid

    async def _do_send_file(self, event, args) -> str:
        kind, tid = self._resolve_target(args)
        if not kind:
            return "错误：target_type 必须为 group 或 private，target_id 不能为空"
        rel = str(args.get("path") or "").strip()
        if not rel:
            return "错误：未指定文件路径"
        try:
            target = self.sandbox.resolve(rel)
        except tools.SandboxError as exc:
            return f"安全限制：{exc}"
        if not target.is_file():
            return f"错误：文件不存在（相对工作空间）: {rel}"
        name = str(args.get("name") or target.name).strip() or target.name
        try:
            if kind == "group":
                await self.api.qq.file.upload_group_file(tid, str(target), name=name)
            else:
                await self.api.qq.file.upload_private_file(tid, str(target), name=name)
            return f"已发送文件 {rel} 到 {kind} {tid}"
        except Exception as exc:
            self.logger.warning("send_file 失败: %s", exc)
            return f"发送失败: {exc}"

    async def _do_send_image(self, event, args) -> str:
        kind, tid = self._resolve_target(args)
        if not kind:
            return "错误：target_type 必须为 group 或 private，target_id 不能为空"
        rel = str(args.get("path") or "").strip()
        if not rel:
            return "错误：未指定图片路径"
        try:
            target = self.sandbox.resolve(rel)
        except tools.SandboxError as exc:
            return f"安全限制：{exc}"
        if not target.is_file():
            return f"错误：文件不存在（相对工作空间）: {rel}"
        try:
            if kind == "group":
                await self.api.qq.send_group_image(tid, str(target))
            else:
                await self.api.qq.send_private_image(tid, str(target))
            return f"已发送图片 {rel} 到 {kind} {tid}"
        except Exception as exc:
            self.logger.warning("send_image 失败: %s", exc)
            return f"发送失败: {exc}"

    # ------------------------------------------------------------------
    # 管理员确认流程
    # ------------------------------------------------------------------

    def _approval_from_text(self, text: str, allow_bare: bool):
        """从管理员文本解析审批意图。

        返回 (action, req_id)：
          action: "approve" | "deny" | "allow_task" | None
          req_id: 指定请求ID；无 ID 且 allow_bare 时可能为空串。
        """
        action, id_str = _parse_approval(text)
        if action is None:
            return None, ""
        if id_str:
            return action, id_str
        if allow_bare:
            return action, ""
        return None, ""

    def _strip_trigger_word(self, text: str) -> str:
        """去掉群聊触发词前缀（yuki 等），返回剩余文本。"""
        keyword = str(self.get_config("group_trigger_keyword", "yuki")).lower()
        s = text.strip()
        if s.lower().startswith(keyword):
            s = s[len(keyword):].lstrip(" :：,，。\t\n")
        return s.strip()

    async def _try_group_approval(self, event: GroupMessageEvent, text: str) -> bool:
        """群聊里管理员的审批：引用卡片、yuki 前缀、@、或紧跟卡片的消息，均可免 ID。"""
        if str(event.user_id) != str(self.get_config("admin_qq")) or not self._pending:
            return False
        await self._add_group_face(event, FACE_TOUSAI)
        # 1) 引用（回复）了某张审批卡片 → 直接按该请求处理，无需 ID
        replies = event.message.filter(Reply)
        if replies:
            req_id = self._pending_by_card(replies[0].id)
            if req_id:
                action, id_str = _parse_approval(self._strip_trigger_word(text))
                if action is not None:
                    if action == "allow_task":
                        await self._resolve_approval(event, "allow_task", self._pending[req_id]["task_id"])
                    else:
                        await self._resolve_approval(event, action, req_id)
                    return True
        # 2) yuki 前缀（触发词），可免 ID
        stripped = self._strip_trigger_word(text)
        if stripped != text:
            action, id_str = _parse_approval(stripped)
            if action is not None:
                await self._finish_approval(event, action, id_str)
                return True
        # 3) 紧跟卡片的消息：管理员在卡片发出的短时间内直接发「同意/拒绝」，视为免 ID 审批
        action, id_str = _parse_approval(text)
        if action is not None:
            if id_str:
                await self._resolve_approval(event, action, id_str)
                return True
            latest = self._latest_pending(event)
            if latest:
                sent_at = self._pending[latest].get("sent_at")
                if sent_at and (time.monotonic() - sent_at) <= float(
                    self.get_config("approval_timeout", 300)
                ):
                    await self._resolve_approval(event, action, latest)
                    return True
        return False

    async def _try_private_approval(self, event: PrivateMessageEvent) -> bool:
        """私聊里管理员的审批：紧跟卡片、引用卡片、或带 ID 均可。"""
        if str(event.user_id) != str(self.get_config("admin_qq")):
            return False
        text = event.raw_message.strip()
        # 1) 引用卡片 → 无需 ID
        replies = event.message.filter(Reply)
        if replies:
            req_id = self._pending_by_card(replies[0].id)
            if req_id:
                action, id_str = _parse_approval(text)
                if action is not None:
                    if action == "allow_task":
                        await self._resolve_approval(event, "allow_task", self._pending[req_id]["task_id"])
                    else:
                        await self._resolve_approval(event, action, req_id)
                    return True
        if not self._pending:
            return False
        # 2) 带 ID
        action, id_str = _parse_approval(text)
        if action is not None:
            if id_str:
                await self._resolve_approval(event, action, id_str)
            else:
                # 私聊且最近请求在该会话（即这个管理员私聊）→ 视为紧跟卡片，免 ID
                latest = self._latest_pending(event)
                if latest:
                    if action == "allow_task":
                        await self._resolve_approval(
                            event, "allow_task", self._pending[latest]["task_id"]
                        )
                    else:
                        await self._resolve_approval(event, action, latest)
                else:
                    return False
            return True
        return False

    async def _finish_approval(self, event, action: str, id_str: str):
        """执行审批：带 ID 用 ID，不带则用该会话最近的请求。"""
        if not id_str:
            latest = self._latest_pending(event)
            if not latest:
                return
            id_str = (
                self._pending[latest]["task_id"]
                if action == "allow_task"
                else latest
            )
        await self._resolve_approval(event, action, id_str)

    def _build_approval_source(self, event) -> str:
        if isinstance(event, PrivateMessageEvent):
            uname = (event.sender.nickname or "").strip() or str(event.user_id)
            return f"私聊 {uname}（{event.user_id}）"
        gname = getattr(event, "group_name", None) or event.group_id
        uname = (event.sender.card or event.sender.nickname or "").strip() or str(event.user_id)
        return f"群「{gname}」/ {uname}（{event.user_id}）"

    def _pending_by_card(self, card_msg_id) -> str:
        """根据审批卡片的 message_id 找到对应的 req_id（用于引用审批）。"""
        for req_id, p in self._pending.items():
            if p.get("card_msg_id") and str(card_msg_id) == str(p["card_msg_id"]):
                return req_id
        return ""

    def _latest_pending(self, event) -> str:
        """返回该会话（群/私聊）最近的一个待确认 req_id；没有则返回空串。"""
        key = self._session_key(event)
        candidates = {
            rid: p for rid, p in self._pending.items() if p.get("session") == key
        }
        if not candidates:
            return ""
        return max(candidates, key=lambda rid: candidates[rid]["created_at"])

    async def _admin_in_group(self, group_id) -> bool:
        """管理员是否在当前群中。"""
        admin = str(self.get_config("admin_qq"))
        try:
            members = await self.api.qq.query.get_group_member_list(group_id)
        except Exception as exc:
            self.logger.warning("查询群成员列表失败: %s", exc)
            return False
        return any(str(m.user_id) == admin for m in members)

    async def _send_approval_card(self, event, admin: str, out) -> str:
        """发送确认卡片：群聊且管理员在群则发到群里并 @ 管理员，否则私聊管理员。返回卡片 message_id（可能为空）。"""
        if isinstance(event, GroupMessageEvent) and await self._admin_in_group(event.group_id):
            msg = MessageArray().add_at(admin).add_text(" 有代码执行确认请求：").add_image(str(out))
            result = await self.api.qq.post_group_array_msg(event.group_id, msg)
            self.logger.info("确认卡片已发送到群 %s 并 @ 管理员", event.group_id)
        else:
            result = await self.api.qq.post_private_msg(admin, image=str(out))
            self.logger.info("确认卡片已私聊发送给管理员")
        return str(getattr(result, "message_id", None) or "")

    async def _request_approval(
        self,
        event,
        task_id: str,
        purpose: str,
        note: str = "",
        code: str = "",
        lang: str = "text",
    ) -> tuple:
        """向管理员发起确认请求（渲染为图片卡片），等待回复。返回 (approved, note)。"""
        if task_id in self._approved_tasks:
            return True, f"任务 {task_id} 已获批量授权，自动放行"
        await self._reply(event, f"需要向管理员确认（任务ID: {task_id}），请稍候...")
        req_id = uuid.uuid4().hex[:8]
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._pending[req_id] = {
            "future": future,
            "created_at": loop.time(),
            "task_id": task_id,
            "purpose": purpose,
            "session": self._session_key(event),
            "card_msg_id": "",
        }
        admin = str(self.get_config("admin_qq"))
        source = self._build_approval_source(event)
        out = self._approval_dir / f"approval_{req_id}.png"
        try:
            render.render_approval_card(
                task_id=task_id,
                req_id=req_id,
                purpose=purpose,
                source=source,
                code=code,
                lang=lang,
                note=note,
                out_path=out,
            )
            card_mid = await self._send_approval_card(event, admin, out)
            if not card_mid:
                return False, "确认卡片发送失败"
            self._pending[req_id]["card_msg_id"] = card_mid
            self._pending[req_id]["sent_at"] = time.monotonic()
        except Exception as exc:
            self._pending.pop(req_id, None)
            self.logger.error("确认卡片渲染/发送失败: %s", exc)
            return False, "确认卡片发送失败"
        try:
            approved = await asyncio.wait_for(
                future, timeout=float(self.get_config("approval_timeout", 300))
            )
        except asyncio.TimeoutError:
            return False, "确认超时（已自动取消）"
        finally:
            self._pending.pop(req_id, None)
        return bool(approved), ("管理员已确认" if approved else "管理员已拒绝")

    async def _resolve_approval(self, event, action: str, id_str: str):
        if action == "allow_task":
            if id_str and id_str in {p.get("task_id") for p in self._pending.values()}:
                task_id = id_str
            else:
                if not self._pending:
                    await self._reply(event, "当前没有待确认的代码执行请求")
                    return
                task_id = self._pending[
                    max(self._pending, key=lambda k: self._pending[k]["created_at"])
                ]["task_id"]
            self._approved_tasks.add(task_id)
            count = sum(
                1 for p in self._pending.values() if p.get("task_id") == task_id
            )
            for rid in list(self._pending):
                if self._pending[rid].get("task_id") == task_id:
                    self._pending[rid]["future"].set_result(True)
                    del self._pending[rid]
            await self._reply(
                event,
                f"已批准任务 {task_id}，本次放行 {count} 个请求，后续该任务请求自动放行",
            )
            return
        approved = action == "approve"
        if id_str:
            pending = self._pending.get(id_str)
            if not pending:
                await self._reply(event, f"没有找到待确认请求 {id_str}（可能已处理或过期）")
                return
        else:
            if not self._pending:
                await self._reply(event, "当前没有待确认的代码执行请求")
                return
            id_str = max(
                self._pending,
                key=lambda k: self._pending[k]["created_at"],
            )
        self._pending[id_str]["future"].set_result(approved)
        await self._reply(event, f"已{'同意' if approved else '拒绝'}请求 {id_str}")
