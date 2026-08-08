"""YUKI 消息记录 — 供 @recall 撤回消息

模块级状态，被 YUKI_agent（记录）与 Kazea_plugin（读取撤回）共用。
- record/pop_last: YUKI 自己发送的消息（@recall 撤 YUKI 的最后一条）
- record_group_msg/last_msg_by: 群内收到的消息（@recall @xxx 撤对方最后一条）
"""

from collections import deque
from typing import Deque, Optional, Tuple

# group_id -> YUKI 发送的消息 id（按时间倒序）
_sent: dict[str, Deque[str]] = {}
# group_id -> (user_id, message_id, text) 收到的群消息
_msgs: dict[str, Deque[Tuple[str, str, str]]] = {}


def record(group_id, message_id) -> None:
    """记录 YUKI 在群内发送的一条消息 id。"""
    q = _sent.setdefault(str(group_id), deque(maxlen=30))
    q.append(str(message_id))


def last_sent(group_id) -> Optional[str]:
    """返回 YUKI 在该群发送的最后一条消息 id。"""
    q = _sent.get(str(group_id))
    return q[-1] if q else None


def pop_last(group_id) -> Optional[str]:
    """取出并移除 YUKI 在该群发送的最后一条消息 id。"""
    q = _sent.get(str(group_id))
    return q.pop() if q else None


def sent_ids(group_id) -> set:
    """返回 YUKI 在该群发送过的全部消息 id。"""
    q = _sent.get(str(group_id))
    return set(q) if q else set()


def record_group_msg(group_id, user_id, message_id, text="") -> None:
    """记录一条收到的群消息。"""
    q = _msgs.setdefault(str(group_id), deque(maxlen=50))
    q.append((str(user_id), str(message_id), text or ""))


def last_msg_by(group_id, user_id) -> Optional[str]:
    """返回某用户在该群发送的最后一条消息 id。"""
    q = _msgs.get(str(group_id))
    if not q:
        return None
    for uid, mid, _ in reversed(q):
        if uid == str(user_id):
            return mid
    return None


def search_group_msgs(group_id, user_id=None, keyword=None, limit: int = 10):
    """在记录的群消息中按发送者/关键词搜索，返回 [(user_id, message_id, text)]（时间倒序）。"""
    q = _msgs.get(str(group_id))
    if not q:
        return []
    out = []
    for uid, mid, text in reversed(q):
        if user_id and uid != str(user_id):
            continue
        if keyword and keyword not in text:
            continue
        out.append((uid, mid, text))
        if len(out) >= limit:
            break
    return out
