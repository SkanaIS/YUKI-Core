"""YUKI Core Command — Kazea 的 @指令入口

@recall / @ban 等指令交由 YUKI_agent 的 AI 理解自然语言并执行。
"""

from ncatbot.core import registrar
from ncatbot.event.qq import MessageEvent
from ncatbot.plugin import NcatBotPlugin

ADMIN_COMMANDS = ("recall", "ban")


class KazeaPlugin(NcatBotPlugin):

    async def on_load(self):
        self.init_defaults(
            {
                "owner_qq": "2641213764",
            }
        )
        self.logger.info(f"{self.name} 已加载")

    async def on_close(self):
        self.logger.info(f"{self.name} 已卸载")

    async def _reply_plain(self, event: MessageEvent, text: str):
        """纯文本回复（不引用、不 @）。"""
        if event.is_group_msg():
            await self.api.qq.post_group_msg(group_id=event.group_id, text=text)
        else:
            await self.api.qq.post_private_msg(user_id=event.user_id, text=text)

    async def _cmd_clear(self, event: MessageEvent):
        """清理 YUKI 当前会话的上下文记忆。"""
        yuki = self.get_plugin("YUKI_agent")
        if yuki is None:
            await self._reply_plain(event, "YUKI_agent 未加载，无法清理上下文")
            return
        cleared = yuki.clear_history(event)
        await self._reply_plain(event, "已清理上下文" if cleared else "上下文本来就是空的")

    async def _cmd_prompt(self, event: MessageEvent, content: str):
        """越狱指令：设置/清除优先级最高的系统提示词覆盖。"""
        yuki = self.get_plugin("YUKI_agent")
        if yuki is None:
            await self._reply_plain(event, "YUKI_agent 未加载，无法设置越狱指令")
            return
        if not content.strip() or content.strip().lower() in ("clear", "清除", "清空"):
            yuki.clear_prompt_override()
            await self._reply_plain(event, "已清除越狱指令")
        else:
            yuki.set_prompt_override(content)
            await self._reply_plain(event, "已设置越狱指令，YUKI 将无条件遵守")

    @registrar.qq.on_message()
    async def on_message(self, event: MessageEvent):
        text = event.raw_message.strip()
        if not text:
            return
        if str(event.user_id) != str(self.get_config("owner_qq", "2641213764")):
            return
        # 清理上下文：@clear / /clear（群聊、私聊均可）
        if text.startswith(("@clear", "/clear")):
            await self._cmd_clear(event)
            return
        # 越狱指令：@prompt / /prompt
        if text.startswith(("@prompt", "/prompt")):
            content = text[len("/prompt"):] if text.startswith("/prompt") else text[len("@prompt"):]
            await self._cmd_prompt(event, content.strip())
            return
        # 重载人设：@reloadmd / /reloadmd
        if text.startswith(("@reloadmd", "/reloadmd")):
            yuki = self.get_plugin("YUKI_agent")
            if yuki is None:
                await self._reply_plain(event, "YUKI_agent 未加载，无法重载")
            else:
                await self._reply_plain(event, yuki.reload_personality())
            return
        if not event.is_group_msg() or not text.startswith("@"):
            return
        parts = text[1:].strip().split()
        if not parts or parts[0] not in ADMIN_COMMANDS:
            return
        yuki = self.get_plugin("YUKI_agent")
        if yuki is None:
            await self._reply_plain(event, "YUKI_agent 未加载，无法执行 @指令")
            return
        await yuki.run_admin_command(event, text)
