# YUKI 可用的 NapCat API 参考

YUKI 通过工具 `call_napcat(action, params)` 调用 NapCat 的全部能力。
- `action`：API 动作名（字符串）
- `params`：参数字典（JSON）

调用示例：
```
call_napcat(action="get_group_member_list", params={"group_id": "123456789"})
```

> 注意：`group_id` / `user_id` 可传数字或字符串，NapCat 会自动转换。

---

## 0. 禁用清单（调用会被直接拒绝，绝不要尝试）

| action | 说明 |
|--------|------|
| `set_group_kick` | 踢人 |
| `set_group_kick_members` | 批量踢人 |
| `kick_and_block` | 拉黑并踢人 |
| `set_group_leave` | 退群 |
| `delete_friend` | 删除好友 |

---

## 1. 消息 API

### 发送群消息 `send_group_msg`
```json
{
  "group_id": "群号",
  "message": [
    {"type": "text", "data": {"text": "大家好"}},
    {"type": "at", "data": {"qq": "目标QQ"}},
    {"type": "image", "data": {"file": "图片url或base64://..."}}
  ]
}
```
常用消息段：
- `text`：`{"type":"text","data":{"text":"内容"}}`
- `at`：`{"type":"at","data":{"qq":"QQ号"}}`（`"all"` 为 @全体）
- `reply`：`{"type":"reply","data":{"id":"被引用消息ID"}}`
- `image`：`{"type":"image","data":{"file":"url"}}`
- `face`：`{"type":"face","data":{"id":"表情ID"}}`

### 发送私聊消息 `send_private_msg`
```json
{"user_id": "QQ号", "message": [{"type": "text", "data": {"text": "内容"}}]}
```

### 撤回消息 `delete_msg`
```json
{"message_id": "消息ID"}
```
> 撤回他人消息需要 YUKI 有管理员权限。

### 获取消息 `get_msg`
```json
{"message_id": "消息ID"}
```

### 获取群最近聊天记录 `get_group_msg_history`
```json
{"group_id": "群号", "count": 30}
```
返回最近的群消息列表（含 `message_id`、`user_id` 发送者、`message` 内容、`time`）。
**用于定位要撤回的消息 ID**：先查历史，找到目标消息的 `message_id`，再 `delete_msg`。

### 获取私聊最近聊天记录 `get_friend_msg_history`
```json
{"user_id": "QQ号", "count": 20}
```

### 消息表情回应 `set_msg_emoji_like`
```json
{"message_id": "消息ID", "emoji_id": "317", "set": true}
```
`emoji_id` 为 QQ 表情 ID（如 285=托腮，317=托腮），`set=false` 取消。

### 标记已读
```json
{"group_id": "群号"}         // mark_group_msg_as_read
{"user_id": "QQ号"}          // mark_private_msg_as_read
```

### 发送点赞 `send_like`
```json
{"user_id": "QQ号", "times": 10}
```

### 戳一戳 `send_poke`
```json
{"group_id": "群号", "user_id": "目标QQ"}
```

### 设置输入状态 `set_input_status`
```json
{"user_id": "QQ号", "event_type": 1}
```
`event_type`：`0`=停止输入，`1`=正在输入，`2`=正在录音。仅私聊 C2C 有效。

---

## 2. 群管理 API

### 禁言 `set_group_ban`
```json
{"group_id": "群号", "user_id": "目标QQ", "duration": 3600}
```
`duration` 为**秒**（如 3600=1 小时，7200=2 小时）。`0` 表示解除禁言。
> 禁止禁言管理员或 YUKI 自己（会被拒绝）。

### 全员禁言 `set_group_whole_ban`
```json
{"group_id": "群号", "enable": true}
```

### 设置群名片 `set_group_card`
```json
{"group_id": "群号", "user_id": "目标QQ", "card": "新名片"}
```

### 设置群名 `set_group_name`
```json
{"group_id": "群号", "group_name": "新群名"}
```

### 设置/取消管理员 `set_group_admin`
```json
{"group_id": "群号", "user_id": "目标QQ", "enable": true}
```

### 设置群头衔 `set_group_special_title`
```json
{"group_id": "群号", "user_id": "目标QQ", "special_title": "头衔"}
```

### 设置群备注 `set_group_remark`
```json
{"group_id": "群号", "remark": "备注"}
```

### 发布群公告 `send_group_notice`
```json
{"group_id": "群号", "content": "公告内容"}
```

### 设置/取消精华消息
```json
{"message_id": "消息ID"}   // set_essence_msg
{"message_id": "消息ID"}   // delete_essence_msg
```

### 群签到 `set_group_sign`
```json
{"group_id": "群号"}
```

---

## 3. 查询 API

| action | params | 返回 |
|--------|--------|------|
| `get_login_info` | `{}` | 机器人自身信息 |
| `get_stranger_info` | `{"user_id":"QQ"}` | 用户信息 |
| `get_friend_list` | `{}` | 好友列表 |
| `get_group_list` | `{}` | 群列表 |
| `get_group_info` | `{"group_id":"群号"}` | 群信息 |
| `get_group_member_info` | `{"group_id":"群号","user_id":"QQ"}` | 单个成员信息（含 `card` 名片、`nickname` 昵称） |
| `get_group_member_list` | `{"group_id":"群号"}` | 成员列表（**获取称呼用这个**） |
| `get_group_essence_msg_list` | `{"group_id":"群号"}` | 精华消息列表 |
| `get_group_system_msg` | `{}` | 加群/退群请求 |
| `get_group_shut_list` | `{"group_id":"群号"}` | 被禁言成员列表 |
| `get_group_at_all_remain` | `{"group_id":"群号"}` | @全体剩余次数 |
| `get_forward_msg` | `{"message_id":"消息ID"}` | 合并转发内容 |
| `get_group_notice` | `{"group_id":"群号"}` | 群公告列表 |

---

## 4. 文件 API

### 上传群文件 `upload_group_file`
```json
{"group_id": "群号", "file": "/本地/文件路径", "name": "文件名.txt"}
```

### 上传私聊文件 `upload_private_file`
```json
{"user_id": "QQ号", "file": "/本地/文件路径", "name": "文件名.txt"}
```

### 群文件操作
```json
{"group_id": "群号"}                              // get_group_root_files 根目录文件
{"group_id": "群号", "file_id": "文件ID"}          // get_group_file_url 获取下载链接
{"group_id": "群号", "file_id": "文件ID"}          // delete_group_file 删除文件
```

### 下载文件到本地 `download_file`
```json
{"url": "https://...", "thread_count": 3}
```

---

## 5. 实用技巧

1. **想知道某成员的称呼**：`get_group_member_list`，优先用 `card`（群名片），其次 `nickname`。
2. **要撤回某条消息**：先 `get_group_msg_history` 找 `message_id`，再 `delete_msg`。
3. **@ 某人**：`send_group_msg` 的 `message` 里加 `{"type":"at","data":{"qq":"QQ号"}}` 段。
4. **不确定某个 API 怎么用**：可先 `read_file("napcat.md")` 查本文件，或调用后根据报错调整参数。
