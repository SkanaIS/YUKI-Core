# YUKI Core

基于 NcatBot 框架的 QQ 机器人，搭载基于 DeepSeek 的 AI Agent「YUKI」，提供工作空间沙箱、代码执行、群管理、联网搜索等能力。

## 架构

```
YUKI Core/
├── config.yaml              # 机器人配置
├── .env                     # API Key
├── plugins/
│   ├── YUKI_agent/          # 核心 AI Agent 插件
│   │   ├── plugin.py        # 主逻辑：事件处理、AI 对话循环、工具调度、审批流程
│   │   ├── tools.py         # 沙箱工具：文件操作、代码执行
│   │   ├── render.py        # 审批卡片渲染（Pillow）
│   │   └── sentlog.py       # 发送消息 ID 记录（引用回复判断）
│   └── Kazea_plugin/        # 管理员 @指令 入口
│       └── plugin.py        # @recall / @ban / @clear / @prompt / @reloadmd
├── YUKI_SPACE/              # YUKI 工作空间（沙箱目录）
│   ├── YUKI.md              # 人设 / 个性提示词
│   └── napcat.md            # NapCat API 参考
├── requirements.txt
└── config.example.yaml
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 初始化配置

```bash
ncatbot init
```

添加 AI 适配器和 Napcat /QQ 适配器。
填写 NapCat WebSocket 地址、令牌、机器人 QQ、管理员 QQ 等信息。

然后在 `.env` 中填写 API Key：

```
DEEPSEEK_API_KEY=sk-xxxxx
```

### 3. 启动 NapCat

确保 NapCat 已启动并配置好 WebSocket 连接。

### 4. 启动机器人

调试模式（热重载、详细日志）：

```bash
ncatbot dev
```

生产模式：

```bash
ncatbot run
```

## 功能

### AI 对话

- `@YUKI <消息>` — @ 机器人唤醒
- `yuki <消息>` — 关键词触发（默认 `yuki`）
- 回复 YUKI 的消息 — 引用即触发
- 接续对话 — 互动后 180 秒内自动续聊（config.yaml）

### 工作空间沙箱

YUKI 的所有文件操作限制在 `YUKI_SPACE/` 目录内：

- 列出 / 读取 / 写入 / 删除文件
- 发送文件 / 图片到群或私聊
- 接收的附件自动保存到 `received/`

### 代码执行（需管理员确认）

- `run_python` — 执行 Python 代码
- `run_shell` — 执行 Shell 命令

管理员审批命令：

| 命令 | 效果 |
|---|---|
| `accept` / `yes` / `y` | 批准当前请求 |
| `deny` / `no` / `n` | 拒绝当前请求 |
| `allow_task` / `allowtask` | 同任务后续请求自动放行 |

### 群管理

- `@recall <自然语言>` — AI 理解并撤回消息
- `@ban <自然语言>` — AI 理解并禁言成员

### 联网搜索

YUKI 可使用 Bing 搜索实时信息。

### 管理员命令

| 命令 | 效果 |
|---|---|
| `/clear` | 清除当前会话上下文 |
| `@prompt <内容>` | 设置越狱指令（最高优先级prompt） |
| `@prompt clear` | 清除越狱指令 |
| `@reloadmd` | 重载 YUKI.md |

## 安全

- 所有文件操作限制在 `YUKI_SPACE/` 沙箱内
- 代码执行需管理员逐次或批量确认
- 禁止踢人、退群、删好友等破坏性操作

## 鸣谢

- [NcatBot](https://github.com/AnomalyCat/ncatbot) — QQ 机器人框架