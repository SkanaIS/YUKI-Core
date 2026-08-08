"""确认卡片渲染 — 把代码执行确认渲染成一张浅色简约卡片。"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH = 660
PAD = 28
BG = (255, 255, 255)
PANEL_BG = (249, 250, 251)
BORDER = (229, 231, 235)
CODE_BG = (247, 248, 250)
TITLE_TEXT = (17, 24, 39)
BODY_TEXT = (55, 65, 81)
SUB_TEXT = (107, 114, 128)
ACCENT = (37, 99, 235)
TASK_COLOR = (79, 70, 229)
REQ_COLOR = (217, 119, 6)
OK_TEXT = (5, 150, 105)
BAD_TEXT = (220, 38, 38)
LABEL_TEXT_BG = (238, 242, 255)

FONT_CJK = "C:/Windows/Fonts/msyh.ttc"
FONT_CJK_BOLD = "C:/Windows/Fonts/msyhbd.ttc"
FONT_MONO = "C:/Windows/Fonts/consola.ttf"

_FONTS = {}


def _font(size, bold=False, mono=False):
    key = (size, bold, mono)
    if key not in _FONTS:
        path = FONT_MONO if mono else (FONT_CJK_BOLD if bold else FONT_CJK)
        _FONTS[key] = ImageFont.truetype(path, size)
    return _FONTS[key]


def _char_font(ch, mono_font, cjk_font):
    return mono_font if ord(ch) < 128 else cjk_font


def _text_width(draw, text, mono_font, cjk_font):
    w = 0
    for ch in text:
        w += draw.textlength(ch, font=_char_font(ch, mono_font, cjk_font))
    return w


def _wrap_mixed(draw, text, mono_font, cjk_font, max_width):
    lines = []
    for para in text.split("\n"):
        if not para:
            lines.append("")
            continue
        cur = ""
        for ch in para:
            if _text_width(draw, cur + ch, mono_font, cjk_font) <= max_width:
                cur += ch
            else:
                lines.append(cur)
                cur = ch
        lines.append(cur)
    return lines


def _draw_mixed(draw, xy, text, mono_font, cjk_font, fill):
    x, y = xy
    max_asc = max(mono_font.getmetrics()[0], cjk_font.getmetrics()[0])
    for ch in text:
        f = _char_font(ch, mono_font, cjk_font)
        asc = f.getmetrics()[0]
        draw.text((x, y + (max_asc - asc)), ch, font=f, fill=fill)
        x += draw.textlength(ch, font=f)


def _wrap_cjk(draw, text, font, max_width):
    lines = []
    for para in text.split("\n"):
        if not para:
            lines.append("")
            continue
        cur = ""
        for ch in para:
            if draw.textlength(cur + ch, font=font) <= max_width:
                cur += ch
            else:
                lines.append(cur)
                cur = ch
        lines.append(cur)
    return lines


def _draw_pill(draw, xy, text, mono_font, cjk_font, fill, bg):
    x, y = xy
    tw = _text_width(draw, text, mono_font, cjk_font)
    asc = max(mono_font.getmetrics()[0], cjk_font.getmetrics()[0])
    desc = max(mono_font.getmetrics()[1], cjk_font.getmetrics()[1])
    h = asc + desc + 8
    pad_y = 4
    draw.rounded_rectangle(
        [x, y, x + tw + 16, y + h], radius=h // 2, fill=bg
    )
    _draw_mixed(draw, (x + 8, y + pad_y), text, mono_font, cjk_font, fill)
    return tw + 16


def render_approval_card(
    *,
    task_id: str,
    req_id: str,
    purpose: str,
    source: str,
    code: str = "",
    lang: str = "",
    note: str = "",
    out_path: Path,
) -> Path:
    title_font = _font(21, bold=True)
    body_font = _font(15)
    small_font = _font(12)
    mono_small = _font(12, mono=True)
    code_mono = _font(14, mono=True)
    code_cjk = _font(14)
    label_font = _font(12, bold=True)

    prep = Image.new("RGB", (10, 10), BG)
    pre = ImageDraw.Draw(prep)
    inner = WIDTH - PAD * 2

    title_lines = _wrap_cjk(pre, f"要允许 YUKI {purpose} 吗？", title_font, inner)
    source_lines = _wrap_cjk(pre, f"来源：{source}", body_font, inner)
    note_lines = _wrap_cjk(pre, note, body_font, inner) if note else []
    raw_code = code
    if raw_code.count("\n") > 60:
        raw_code = "\n".join(raw_code.split("\n")[:60]) + "\n……（代码过长已截断）"
    code_lines = _wrap_mixed(pre, raw_code, code_mono, code_cjk, inner - 24) if raw_code else []

    lh_title, lh_body, lh_code = 32, 26, 24
    header_h = 40
    title_h = lh_title * len(title_lines)
    source_h = lh_body * len(source_lines)
    note_h = lh_body * len(note_lines) if note_lines else 0
    code_h = 0
    if code_lines:
        code_h = lh_body + lh_code * len(code_lines) + 20
    footer_h = lh_body * 3 + 16
    hint_h = lh_body * 1 + 28

    total_h = (
        header_h
        + 6
        + title_h
        + 4
        + source_h
        + (note_h + 4 if note_h else 0)
        + (code_h + 10 if code_h else 0)
        + footer_h
        + hint_h
        + PAD * 2
    )

    img = Image.new("RGB", (WIDTH, total_h), BG)
    draw = ImageDraw.Draw(img)
    y = PAD

    task_label = f"任务ID {task_id}"
    req_label = f"请求ID {req_id}"
    _draw_pill(draw, (PAD, y), task_label, mono_small, small_font, TASK_COLOR, LABEL_TEXT_BG)
    req_w = _text_width(draw, req_label, mono_small, small_font)
    _draw_pill(draw, (WIDTH - PAD - req_w - 16, y), req_label, mono_small, small_font, REQ_COLOR, (255, 243, 224))
    y += header_h

    for line in title_lines:
        draw.text((PAD, y), line, font=title_font, fill=TITLE_TEXT)
        y += lh_title
    y += 4

    for line in source_lines:
        draw.text((PAD, y), line, font=body_font, fill=BODY_TEXT)
        y += lh_body
    if note_h:
        y += 4
        for line in note_lines:
            draw.text((PAD, y), line, font=body_font, fill=SUB_TEXT)
            y += lh_body

    if code_h:
        y += 10
        code_top = y
        draw.rounded_rectangle(
            [PAD, code_top, WIDTH - PAD, code_top + code_h],
            radius=12,
            fill=CODE_BG,
            outline=BORDER,
        )
        bx = PAD + 14
        by = code_top + 8
        draw.text((bx, by), (lang or "代码").upper(), font=small_font, fill=SUB_TEXT)
        by += lh_body
        for line in code_lines:
            _draw_mixed(draw, (bx, by), line, code_mono, code_cjk, (31, 41, 55))
            by += lh_code
        y = code_top + code_h

    y += 12
    draw.text((PAD, y), "回复「accept」→ 批准本次请求", font=body_font, fill=OK_TEXT)
    y += lh_body
    draw.text((PAD, y), "回复「deny」→ 拒绝本次请求", font=body_font, fill=BAD_TEXT)
    y += lh_body
    draw.text((PAD, y), "回复「allow_task」→ 本任务期间自动放行", font=body_font, fill=ACCENT)
    y += lh_body + 6

    draw.rounded_rectangle(
        [PAD, y, WIDTH - PAD, y + hint_h],
        radius=12,
        fill=PANEL_BG,
        outline=BORDER,
    )
    hy = y + 12
    draw.text((PAD + 14, hy), "YUKI 也可能会犯错。请核查重要信息。", font=small_font, fill=SUB_TEXT)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG")
    return out_path
