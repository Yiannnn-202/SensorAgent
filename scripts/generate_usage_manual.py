#!/usr/bin/env python3
"""Generate the single-file Chinese SensorAgent deployment manual."""

from __future__ import annotations

import html
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    Image,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents
from pypdf import PdfReader, PdfWriter


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "安装部署与使用说明书.pdf"
CAPTURE = ROOT / "logs/vision/manual_probe_repeat_4/rgb.png"
DETECTION = Path("/tmp/opencode/sensoragent-manual-detection/rgb.jpg")

NAVY = colors.HexColor("#10273D")
BLUE = colors.HexColor("#176B87")
CYAN = colors.HexColor("#20A4B8")
PALE = colors.HexColor("#EAF4F6")
INK = colors.HexColor("#17232D")
MUTED = colors.HexColor("#5B6973")
LINE = colors.HexColor("#CBD7DC")
WARN = colors.HexColor("#FFF3D6")
WARN_LINE = colors.HexColor("#D99A24")
SAFE = colors.HexColor("#E9F5ED")
SAFE_LINE = colors.HexColor("#3F8B5B")
CODE_BG = colors.HexColor("#F3F6F7")


def register_fonts() -> None:
    font_dir = Path("/mnt/c/Windows/Fonts")
    pdfmetrics.registerFont(TTFont("CN", str(font_dir / "msyh.ttc")))
    pdfmetrics.registerFont(TTFont("CN-Bold", str(font_dir / "msyhbd.ttc")))
    pdfmetrics.registerFont(TTFont("Mono", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"))


register_fonts()

styles = getSampleStyleSheet()
BODY = ParagraphStyle(
    "BodyCN",
    parent=styles["BodyText"],
    fontName="CN",
    fontSize=9.5,
    leading=15,
    textColor=INK,
    spaceAfter=4,
    wordWrap="CJK",
)
LEAD = ParagraphStyle(
    "LeadCN",
    parent=BODY,
    fontSize=11,
    leading=18,
    textColor=NAVY,
)
H1 = ParagraphStyle(
    "Heading1",
    parent=styles["Heading1"],
    fontName="CN-Bold",
    fontSize=18,
    leading=24,
    textColor=NAVY,
    spaceBefore=8,
    spaceAfter=12,
    keepWithNext=True,
)
H2 = ParagraphStyle(
    "Heading2",
    parent=styles["Heading2"],
    fontName="CN-Bold",
    fontSize=13,
    leading=19,
    textColor=BLUE,
    spaceBefore=9,
    spaceAfter=7,
    keepWithNext=True,
)
H3 = ParagraphStyle(
    "Heading3",
    parent=styles["Heading3"],
    fontName="CN-Bold",
    fontSize=10.5,
    leading=16,
    textColor=NAVY,
    spaceBefore=6,
    spaceAfter=4,
    keepWithNext=True,
)
FRONT_H1 = ParagraphStyle("FrontHeading1", parent=H1)
FRONT_H2 = ParagraphStyle("FrontHeading2", parent=H2)
CAPTION = ParagraphStyle(
    "CaptionCN",
    parent=BODY,
    fontSize=8,
    leading=12,
    alignment=TA_CENTER,
    textColor=MUTED,
    spaceBefore=3,
    spaceAfter=8,
)
SMALL = ParagraphStyle(
    "SmallCN",
    parent=BODY,
    fontSize=8,
    leading=12,
    textColor=MUTED,
)
TABLE_HEAD = ParagraphStyle(
    "TableHeadCN",
    parent=BODY,
    fontName="CN-Bold",
    fontSize=8.5,
    leading=12,
    textColor=colors.white,
    alignment=TA_LEFT,
)
TABLE_CELL = ParagraphStyle(
    "TableCellCN",
    parent=BODY,
    fontSize=8.3,
    leading=12,
    spaceAfter=0,
)
CODE = ParagraphStyle(
    "CodeCN",
    parent=BODY,
    fontName="Mono",
    fontSize=7.3,
    leading=11,
    textColor=colors.HexColor("#20313B"),
    leftIndent=0,
    spaceAfter=0,
)
CODE_CN = ParagraphStyle(
    "CodeChinese",
    parent=CODE,
    fontName="CN",
    fontSize=7.8,
    leading=11.5,
)


def p(text: str, style: ParagraphStyle = BODY) -> Paragraph:
    return Paragraph(text, style)


def h1(text: str) -> Paragraph:
    return Paragraph(text, H1)


def h2(text: str) -> Paragraph:
    return Paragraph(text, H2)


def h3(text: str) -> Paragraph:
    return Paragraph(text, H3)


def bullet(text: str) -> Paragraph:
    style = ParagraphStyle(
        "BulletCN",
        parent=BODY,
        leftIndent=13,
        firstLineIndent=-10,
        bulletIndent=0,
        spaceAfter=2,
    )
    return Paragraph(f"<font color='#176B87'>•</font> {text}", style)


def numbered(number: int, text: str) -> Paragraph:
    style = ParagraphStyle(
        "NumberCN",
        parent=BODY,
        leftIndent=18,
        firstLineIndent=-18,
        spaceAfter=3,
    )
    return Paragraph(f"<b>{number}.</b> {text}", style)


def code_block(text: str) -> Table:
    escaped = html.escape(text).replace("\n", "<br/>")
    style = CODE if text.isascii() else CODE_CN
    box = Table([[Paragraph(escaped, style)]], colWidths=[166 * mm])
    box.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), CODE_BG),
                ("BOX", (0, 0), (-1, -1), 0.6, LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return box


def data_table(rows: list[list[str]], widths: list[float]) -> Table:
    rendered = []
    for row_index, row in enumerate(rows):
        style = TABLE_HEAD if row_index == 0 else TABLE_CELL
        rendered.append([Paragraph(str(cell), style) for cell in row])
    table = Table(rendered, colWidths=[value * mm for value in widths], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7FAFB")]),
                ("GRID", (0, 0), (-1, -1), 0.45, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def callout(title: str, text: str, warning: bool = False) -> Table:
    background = WARN if warning else SAFE
    line_color = WARN_LINE if warning else SAFE_LINE
    title_color = colors.HexColor("#7A4A00") if warning else colors.HexColor("#225D37")
    body = Paragraph(
        f"<font name='CN-Bold' color='{title_color.hexval()}'>{title}</font><br/>{text}",
        ParagraphStyle("CalloutCN", parent=BODY, fontSize=8.8, leading=14, spaceAfter=0),
    )
    table = Table([[body]], colWidths=[166 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), background),
                ("BOX", (0, 0), (-1, -1), 1.0, line_color),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return table


class ArchitectureDiagram(Flowable):
    def __init__(self) -> None:
        super().__init__()
        self.width = 166 * mm
        self.height = 64 * mm

    def draw_box(self, canvas, x, y, width, height, title, lines, fill):
        canvas.setFillColor(fill)
        canvas.setStrokeColor(colors.white)
        canvas.roundRect(x, y, width, height, 4, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont("CN-Bold", 9)
        canvas.drawCentredString(x + width / 2, y + height - 13, title)
        canvas.setFont("CN", 7.3)
        for index, line in enumerate(lines):
            canvas.drawCentredString(x + width / 2, y + height - 27 - index * 10, line)

    def draw(self):
        canvas = self.canv
        gap = 7 * mm
        box_width = (self.width - 2 * gap) / 3
        y = 16 * mm
        height = 36 * mm
        self.draw_box(canvas, 0, y, box_width, height, "交互与 Agent", ["中文/英文指令", "持续任务 loop", "规划·验证·恢复"], NAVY)
        self.draw_box(canvas, box_width + gap, y, box_width, height, "双分支视觉", ["YOLO11 固定类别", "Grounding DINO", "SAM 2 + RGB-D"], BLUE)
        self.draw_box(canvas, 2 * (box_width + gap), y, box_width, height, "ROS 2 执行层", ["仿真 / 实机桥", "RM65-B", "相机 + 夹爪"], CYAN)
        canvas.setStrokeColor(MUTED)
        canvas.setLineWidth(1.2)
        for x in (box_width + 1 * mm, 2 * box_width + gap + 1 * mm):
            canvas.line(x, y + height / 2, x + gap - 2 * mm, y + height / 2)
            canvas.line(x + gap - 4 * mm, y + height / 2 + 2 * mm, x + gap - 2 * mm, y + height / 2)
            canvas.line(x + gap - 4 * mm, y + height / 2 - 2 * mm, x + gap - 2 * mm, y + height / 2)
        canvas.setFillColor(MUTED)
        canvas.setFont("CN", 7.5)
        canvas.drawCentredString(self.width / 2, 5 * mm, "运动控制：HTTP/JSON；视觉输入：ROS 2 Topic / TF")


class RouteDiagram(Flowable):
    def __init__(self) -> None:
        super().__init__()
        self.width = 166 * mm
        self.height = 61 * mm

    def draw(self):
        c = self.canv
        c.setFont("CN-Bold", 9)
        c.setFillColor(NAVY)
        c.roundRect(58 * mm, 49 * mm, 50 * mm, 10 * mm, 4, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.drawCentredString(83 * mm, 52.5 * mm, "自然语言目标")
        c.setStrokeColor(MUTED)
        c.line(83 * mm, 49 * mm, 83 * mm, 43 * mm)
        c.setFillColor(PALE)
        c.setStrokeColor(BLUE)
        c.roundRect(50 * mm, 32 * mm, 66 * mm, 11 * mm, 4, fill=1, stroke=1)
        c.setFillColor(NAVY)
        c.drawCentredString(83 * mm, 35.5 * mm, "工业类别路由与置信度判断")
        c.setStrokeColor(MUTED)
        c.line(58 * mm, 32 * mm, 34 * mm, 25 * mm)
        c.line(108 * mm, 32 * mm, 132 * mm, 25 * mm)
        c.setFillColor(BLUE)
        c.roundRect(4 * mm, 7 * mm, 61 * mm, 18 * mm, 4, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.drawCentredString(34.5 * mm, 17 * mm, "YOLO11 固定类别检测")
        c.setFont("CN", 7.2)
        c.drawCentredString(34.5 * mm, 11 * mm, "bearing / bolt / gear / nut")
        c.setFillColor(CYAN)
        c.roundRect(101 * mm, 7 * mm, 61 * mm, 18 * mm, 4, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("CN-Bold", 9)
        c.drawCentredString(131.5 * mm, 17 * mm, "Grounding DINO + SAM 2")
        c.setFont("CN", 7.2)
        c.drawCentredString(131.5 * mm, 11 * mm, "开放词汇检测与实例掩码")
        c.setFillColor(MUTED)
        c.setFont("CN", 7)
        c.drawCentredString(28 * mm, 27.5 * mm, "已知类别优先")
        c.drawCentredString(138 * mm, 27.5 * mm, "未知/长尾/低置信度回退")


class ManualDocTemplate(BaseDocTemplate):
    def __init__(self, filename: str) -> None:
        super().__init__(
            filename,
            pagesize=A4,
            leftMargin=22 * mm,
            rightMargin=22 * mm,
            topMargin=20 * mm,
            bottomMargin=18 * mm,
            title="SensorAgent 安装部署与使用说明书",
            author="SensorAgent 项目组",
            subject="挑战杯项目安装部署与使用说明",
        )
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="normal")
        self.addPageTemplates(PageTemplate(id="manual", frames=[frame], onPage=self.draw_page))

    def draw_page(self, canvas, doc) -> None:
        if doc.page == 1:
            return
        canvas.saveState()
        canvas.setStrokeColor(LINE)
        canvas.setLineWidth(0.5)
        canvas.line(22 * mm, A4[1] - 13 * mm, A4[0] - 22 * mm, A4[1] - 13 * mm)
        canvas.setFont("CN", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(22 * mm, A4[1] - 10 * mm, "SensorAgent 安装部署与使用说明书")
        canvas.drawRightString(A4[0] - 22 * mm, 10 * mm, f"第 {doc.page} 页")
        canvas.restoreState()

    def afterFlowable(self, flowable) -> None:
        if isinstance(flowable, Paragraph) and flowable.style.name in {"Heading1", "Heading2", "Heading3"}:
            level = {"Heading1": 0, "Heading2": 1, "Heading3": 2}[flowable.style.name]
            text = flowable.getPlainText()
            key = f"section-{self.seq.nextf('section')}"
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(text, key, level=level, closed=False)
            self.notify("TOCEntry", (level, text, self.page, key))


def cover(story: list) -> None:
    story.extend(
        [
            Spacer(1, 25 * mm),
            Table(
                [[Paragraph("SENSORAGENT", ParagraphStyle("Brand", fontName="CN-Bold", fontSize=13, textColor=colors.white, alignment=TA_CENTER))]],
                colWidths=[48 * mm],
                style=TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), CYAN),
                        ("BOX", (0, 0), (-1, -1), 0, CYAN),
                        ("TOPPADDING", (0, 0), (-1, -1), 6),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ]
                ),
            ),
            Spacer(1, 15 * mm),
            Paragraph(
                "安装部署与使用说明书",
                ParagraphStyle("CoverTitle", fontName="CN-Bold", fontSize=30, leading=40, textColor=NAVY, alignment=TA_CENTER),
            ),
            Spacer(1, 5 * mm),
            Paragraph(
                "面向工业零部件感知、抓取与分拣的具身智能系统",
                ParagraphStyle("CoverSub", fontName="CN", fontSize=13, leading=20, textColor=BLUE, alignment=TA_CENTER),
            ),
            Spacer(1, 18 * mm),
            ArchitectureDiagram(),
            Spacer(1, 14 * mm),
            data_table(
                [
                    ["文档版本", "适用平台", "发布日期"],
                    ["V1.2 精简版", "Ubuntu 22.04 / ROS 2 Humble", "2026-09-04"],
                ],
                [34, 88, 44],
            ),
            Spacer(1, 16 * mm),
            Paragraph(
                "SensorAgent 项目组",
                ParagraphStyle("CoverTeam", fontName="CN-Bold", fontSize=11, textColor=NAVY, alignment=TA_CENTER),
            ),
            Spacer(1, 3 * mm),
            Paragraph(
                "挑战杯项目提交文档",
                ParagraphStyle("CoverFoot", fontName="CN", fontSize=9, textColor=MUTED, alignment=TA_CENTER),
            ),
            PageBreak(),
        ]
    )


def build_story() -> list:
    story: list = []
    cover(story)

    story.extend(
        [
            h1("文档说明"),
            p("本文档用于指导 SensorAgent 工业零部件分拣系统的安装、部署、接线、启动、操作与维护。内容以项目 <b>submission</b> 分支 <font name='Mono'>bb3b2b9</font>、实机驱动工作区和现场设备参数为依据，适用于挑战杯演示环境。"),
            data_table(
                [
                    ["项目", "内容"],
                    ["系统目标", "通过自然语言指令完成工业零部件识别、三维定位、抓取、放置、验证与受控恢复"],
                    ["实机设备", "RealMan RM65-B、Intel RealSense D435、智元灵犀 X1 OmniPicker"],
                    ["运行方式", "WSL2 Ubuntu 22.04；Agent 与 ROS 2 分进程，通过本机 HTTP/JSON 通信"],
                    ["演示入口", "bash scripts/linux/run_hardware_agent.sh --enable-motion"],
                    ["适用人员", "项目部署人员、现场操作员、评审与复现人员"],
                ],
                [35, 131],
            ),
            Spacer(1, 5 * mm),
            callout("安全声明", "sensoragent_hardware_bridge 是系统集成适配器，不是安全认证控制器。实机运动前必须确认急停有效、人员退出机械臂工作空间、工件与料箱布置正确，并由操作员全程监督。", warning=True),
            Spacer(1, 8 * mm),
            h1("目录"),
        ]
    )
    toc = TableOfContents()
    toc.levelStyles = [
        ParagraphStyle("TOC1", fontName="CN-Bold", fontSize=10, leading=17, leftIndent=0, textColor=NAVY),
        ParagraphStyle("TOC2", fontName="CN", fontSize=9, leading=15, leftIndent=14, textColor=INK),
        ParagraphStyle("TOC3", fontName="CN", fontSize=8, leading=13, leftIndent=28, textColor=MUTED),
    ]
    story.extend([toc, PageBreak()])

    story.extend(
        [
            h1("1. 系统概述"),
            p("SensorAgent 是面向工业现场的持续运行 Agent。操作者输入中文或英文分拣指令后，系统依次执行意图理解、世界状态检查、RGB-D 观测、双分支感知、目标选择、抓放规划、机械臂与夹爪控制、抓取验证和失败恢复，并返回结构化运行记录。"),
            ArchitectureDiagram(),
            h2("1.1 进程与通信架构"),
            data_table(
                [
                    ["层级", "主要组件", "接口"],
                    ["Agent 层", "任务 loop、规则化指令理解、ActionList、DecisionTree", "Python >=3.10（现场 3.12）"],
                    ["感知层", "YOLO11 固定类别检测、Grounding DINO、SAM 2、RGB-D 定位", "Tool 调用"],
                    ["集成层", "sensoragent_hardware_bridge", "HTTP/JSON 127.0.0.1:8766"],
                    ["ROS 2 层", "rm_driver、arm_control、op_control、vision_dep", "ROS 2 Service/Topic/TF"],
                    ["设备层", "RM65-B、D435、OmniPicker", "Ethernet、USB 3.x、USB-RS485"],
                ],
                [26, 84, 56],
            ),
            h2("1.2 Agent 持续任务 loop"),
            code_block("IDLE -> UNDERSTAND -> CHECK_WORLD -> OBSERVE -> PERCEIVE\n     -> SELECT -> PLAN -> ACT -> VERIFY -> RECOVER -> COMPLETE -> IDLE"),
            p("默认文本模式持续等待输入，输入 <b>exit、quit、q、退出</b> 或 <b>结束</b> 后退出。每轮任务生成 JSON 事件，并在 <font name='Mono'>logs/tasks/</font> 下保存 JSONL 记录。"),
            h2("1.3 实机系统拓扑"),
            data_table(
                [
                    ["连接", "现场值", "用途"],
                    ["工控机/笔记本以太网", "192.168.1.100/24", "接收机械臂 UDP 状态"],
                    ["RM65-B 控制器", "192.168.1.19:8080", "TCP 运动控制"],
                    ["RM65-B 状态回传", "192.168.1.100:8089，5 ms", "UDP 主动上报"],
                    ["D435", "USB 3.x，经 usbipd 接入 WSL2", "彩色图像、对齐深度与点云"],
                    ["OmniPicker", "/dev/ttyUSB0，115200 8N1", "USB 转 RS485 夹爪控制"],
                    ["硬件桥", "127.0.0.1:8766", "Agent 与 ROS 2 解耦"],
                ],
                [40, 62, 64],
            ),
            PageBreak(),
            h1("2. 硬件配置"),
            h2("2.1 计算平台"),
            data_table(
                [
                    ["项目", "实测配置"],
                    ["操作系统", "Windows WSL2 中的 Ubuntu 22.04.5 LTS"],
                    ["CPU", "Intel Core i7-14700HX"],
                    ["GPU", "NVIDIA GeForce RTX 4070 Laptop GPU，8188 MiB"],
                    ["WSL2 分配内存", "约 7.6 GiB"],
                    ["NVIDIA 驱动", "566.36；驱动支持 CUDA 12.7"],
                    ["CUDA Toolkit", "未单独安装 nvcc；推理使用 PyTorch 自带 CUDA 运行时"],
                ],
                [48, 118],
            ),
            h2("2.2 RealMan RM65-B 机械臂"),
            data_table(
                [
                    ["项目", "参数"],
                    ["型号", "RM65-B，6 自由度，标准版"],
                    ["额定负载 / 工作半径", "5 kg / 610 mm"],
                    ["重复定位精度", "±0.05 mm"],
                    ["本体防护等级", "IP54"],
                    ["工作环境", "0～45 ℃；25%～85% RH，无结露；海拔不高于 1000 m"],
                    ["供电", "DC 24 V，允许 20～27 V；建议 600 W 以上电源"],
                    ["安装", "底座四个 M6 螺栓；安装面应满足厂商承载要求"],
                    ["坐标系", "base_link；末端法兰 Link6"],
                ],
                [55, 111],
            ),
            p("机械臂通过 RealMan ROS 2 驱动接入。控制参数为 <font name='Mono'>arm_ip=192.168.1.19</font>、<font name='Mono'>tcp_port=8080</font>、<font name='Mono'>udp_ip=192.168.1.100</font>、<font name='Mono'>udp_port=8089</font>、<font name='Mono'>udp_cycle=5</font>。"),
            h2("2.3 Intel RealSense D435"),
            data_table(
                [
                    ["项目", "部署值"],
                    ["安装方式", "眼在手，固定于 RM65-B 末端；Link6 -> camera_link"],
                    ["驱动节点", "vision_dep/dep_cam，直接调用 librealsense2 2.58.3"],
                    ["彩色流", "1920×1080，30 FPS，BGR8"],
                    ["深度流", "1280×720，30 FPS，Z16，并对齐至彩色图像"],
                    ["集成发布频率", "5 Hz"],
                    ["ROS 话题", "/vision/raw、/vision/cloud"],
                    ["点云格式", "float32 x/y/z/u/v，frame_id=camera_link"],
                ],
                [46, 120],
            ),
            h3("眼在手标定"),
            p("项目采用 PARK 方法，标定文件为 <font name='Mono'>eye_in_hand.json</font>。部署时静态 TF 使用下列 <font name='Mono'>T_link6_camera</font> 平移和旋转矩阵："),
            code_block("[ 0.036323,  0.999140, -0.019993, -0.086848 ]\n[-0.999327,  0.036213, -0.005850,  0.034513 ]\n[-0.005121,  0.020192,  0.999783, -0.027494 ]\n[ 0.000000,  0.000000,  0.000000,  1.000000 ]"),
            callout("标定要求", "相机、夹爪转接件、末端法兰或工作台位置发生变化后，必须重新完成手眼标定、桌面平面和工作区校验，不得继续沿用原矩阵。", warning=True),
            h2("2.4 智元灵犀 X1 OmniPicker"),
            data_table(
                [
                    ["项目", "参数"],
                    ["产品重量 / 最大行程", "0.43 kg / 120 mm"],
                    ["最大夹持力 / 推荐负载", "30 N / 1.5 kg"],
                    ["重复定位精度", "±0.05 mm"],
                    ["额定电压", "24 V DC"],
                    ["现场通信", "USB 转 RS485 直接接入工控机"],
                    ["Linux 设备", "/dev/ttyUSB0"],
                    ["串口参数", "115200，8N1，无流控；12 字节协议帧"],
                    ["位置定义", "0.0 为闭合，1.0 为完全张开"],
                    ["ROS 接口", "/task/op/open、/close、/set_position；/omnipicker_state"],
                ],
                [56, 110],
            ),
            p("上电前须确认夹爪行程内无障碍物。夹爪上电后会自动闭合寻找零位；不能正常归零时应立即停止使用并检查机械结构、RS485 接线和固件。串口协议要求固件版本不低于 3.3.2。"),
            PageBreak(),
            h1("3. 软件环境"),
            h2("3.1 版本清单"),
            data_table(
                [
                    ["组件", "版本 / 用途"],
                    ["ROS 2", "Humble，运行于 Ubuntu 22.04"],
                    ["Agent Python", "项目要求 >=3.10；现场环境 3.12.13；CI 使用 3.12"],
                    ["ROS Python", "系统 Python 3.10.12，rclpy 与采集子进程"],
                    ["PyTorch", "2.13.0+cu126"],
                    ["torchvision", "0.28.0+cu126"],
                    ["transformers", "4.57.6"],
                    ["ultralytics", "8.4.117"],
                    ["librealsense", "2.58.3"],
                    ["RMW", "rmw_cyclonedds_cpp；ROS_DOMAIN_ID=0"],
                ],
                [52, 114],
            ),
            callout("推荐双 Python 环境", "项目声明支持 Python 3.10 及以上，现场 Agent 使用 Python 3.12.13；ROS 2 Humble 使用 Ubuntu 22.04 的系统 Python 3.10。为避免 rclpy 与视觉依赖冲突，ROS 图像采集由 /usr/bin/python3 执行，Agent 与视觉推理在 .venv312 中执行。"),
            h2("3.2 项目目录"),
            code_block("/home/hcn/workspace/SensorAgent    # Agent、配置、硬件桥\n/home/hcn/Island-Arm              # RM65、D435、OmniPicker 驱动\n/opt/ros/humble                   # ROS 2 Humble"),
            h2("3.3 主要依赖"),
            p("基础依赖包括 NumPy、PyYAML、Requests、sounddevice 和 sherpa-onnx；视觉依赖包括 Pillow、safetensors、SciPy、Transformers 和 Ultralytics。模型权重、密钥、数据集和实机日志不纳入 Git。"),
            h1("4. 安装与部署"),
            h2("4.1 WSL2 网络与 USB 设备"),
            p("Windows 侧建议启用 WSL2 镜像网络，使 RM65-B 能将 UDP 状态直接回传至 <font name='Mono'>192.168.1.100:8089</font>。在 <font name='Mono'>%UserProfile%\\.wslconfig</font> 中配置："),
            code_block("[wsl2]\nnetworkingMode=mirrored"),
            p("管理员 PowerShell 执行以下命令，将 D435 和 OmniPicker 的 USB 设备挂载到 WSL2："),
            code_block("winget install --exact dorssel.usbipd-win\nusbipd list\nusbipd bind --busid <BUSID>\nusbipd attach --wsl --busid <BUSID>\nwsl --shutdown"),
            p("重新进入 Ubuntu 后检查设备，并授予当前用户串口和视频设备权限："),
            code_block("lsusb\nls -l /dev/ttyUSB0 /dev/video*\nsudo usermod -aG dialout,video \"$USER\""),
            callout("USB 注意事项", "D435 高分辨率彩色与深度流应接入直连 USB 3.x 端口，不建议通过无源集线器。WSL 重启、USB 拔插或 wsl --shutdown 后通常需要重新执行 usbipd attach。", warning=True),
            h2("4.2 安装 ROS 2 Humble 与系统依赖"),
            code_block("sudo apt update\nsudo apt install -y ros-humble-desktop ros-humble-rmw-cyclonedds-cpp \\\n  ros-humble-xacro ros-humble-robot-state-publisher \\\n  python3-rosdep python3-colcon-common-extensions \\\n  libturbojpeg0-dev librealsense2-dev librealsense2-utils \\\n  netcat-openbsd usbutils v4l-utils\nrosdep update"),
            h2("4.3 构建 Island-Arm 驱动工作区"),
            code_block("source /opt/ros/humble/setup.bash\ncd /home/hcn/Island-Arm\nrosdep install --from-paths src --ignore-src --rosdistro humble -r -y\ncolcon build --symlink-install --packages-up-to \\\n  rm_driver arm_control op_control vision_dep"),
            p("构建后验证 <font name='Mono'>/home/hcn/Island-Arm/install/setup.bash</font> 存在，并检查四个驱动包："),
            code_block("source /home/hcn/Island-Arm/install/setup.bash\nros2 pkg prefix rm_driver\nros2 pkg prefix arm_control\nros2 pkg prefix op_control\nros2 pkg prefix vision_dep"),
            h2("4.4 构建 SensorAgent ROS 2 硬件桥"),
            code_block("source /opt/ros/humble/setup.bash\nsource /home/hcn/Island-Arm/install/setup.bash\ncd /home/hcn/workspace/SensorAgent/ros2_ws\nrosdep install --from-paths src/sensoragent_hardware_bridge \\\n  --ignore-src --rosdistro humble -r -y\ncolcon build --symlink-install \\\n  --packages-select sensoragent_hardware_bridge"),
            h2("4.5 创建 Agent Python 环境"),
            p("最新版本已将核心、音频和视觉依赖合并到单一 <font name='Mono'>requirements.txt</font>，不再使用 <font name='Mono'>requirements-vision.txt</font>。现场继续采用 Python 3.12 虚拟环境："),
            code_block("cd /home/hcn/workspace/SensorAgent\npython3.12 -m venv .venv312\nsource .venv312/bin/activate\npython -m pip install --upgrade pip setuptools wheel\npython -m pip install -r requirements.txt\npython -m pip install onnxruntime pytest"),
            h2("4.6 安装模型文件"),
            data_table(
                [
                    ["分支", "本地路径", "SHA-256"],
                    ["YOLO11 固定类别", "models/vision/yolo11n_4class.pt", "f6be64b7…446be24"],
                    ["Grounding DINO 微调版", "models/vision/grounding-dino/grounding_dino", "model.safetensors: c23e9c47…7bda4b8d"],
                    ["SAM 2", "models/vision/sam2_t.pt", "94375f98…5ca501"],
                ],
                [37, 78, 51],
            ),
            p("完整 SHA-256 可通过以下命令复核："),
            code_block("sha256sum models/vision/yolo11n_4class.pt\nsha256sum models/vision/grounding-dino/grounding_dino/model.safetensors\nsha256sum models/vision/sam2_t.pt"),
            callout("模型类型核验", "yolo11n_4class.pt 经 Ultralytics 加载后报告为 DetectionModel / detect，类别为 bearing、bolt、gear、nut。该文件不包含原生实例掩码，因此固定分支应按 YOLO11 检测模型接入；需要掩码时由 Grounding DINO + SAM 2 分支提供。", warning=True),
            h2("4.7 配置视觉模型路径"),
            code_block("integrations:\n  vision:\n    backend: dual_branch\n    model_path: models/vision/yolo11n_4class.pt\n    grounding_dino_model: models/vision/grounding-dino/grounding_dino\n    sam2_model_path: models/vision/sam2_t.pt\n    dual_branch:\n      route_policy: industrial_first\n      fallback_on_error: true\n      min_fixed_confidence: 0.35"),
            p("仓库示例路径为 <font name='Mono'>models/vision/yolo11-seg/industrial-best.pt</font> 和 <font name='Mono'>models/vision/grounding-dino/industrial-open-vocab</font>；现场实际模型名称不同，因此正式运行配置必须使用上方本地路径，或将经过核验的权重部署到示例路径。"),
            h2("4.8 运行环境变量"),
            p("启动脚本已支持可迁移路径。现场建议显式设置 Agent 解释器、ROS、Island-Arm 和 SensorAgent overlay："),
            code_block("export SENSORAGENT_PYTHON=/home/hcn/workspace/SensorAgent/.venv312/bin/python\nexport SENSORAGENT_ROS_PYTHON=/usr/bin/python3\nexport SENSORAGENT_ROS_SETUP=/opt/ros/humble/setup.bash\nexport SENSORAGENT_ISLAND_ARM_SETUP=/home/hcn/Island-Arm/install/setup.bash\nexport SENSORAGENT_ROS_WS_SETUP=/home/hcn/workspace/SensorAgent/ros2_ws/install/local_setup.bash\nexport PYTHONPATH=/home/hcn/workspace/SensorAgent/src"),
            p("未设置时，硬件栈会依次使用 <font name='Mono'>/opt/ros/${ROS_DISTRO:-humble}/setup.bash</font>、<font name='Mono'>~/Island-Arm/install/setup.bash</font> 和项目内 <font name='Mono'>ros2_ws/install/local_setup.bash</font>。启动后脚本固定使用 CycloneDDS 和 <font name='Mono'>ROS_DOMAIN_ID=0</font>。"),
            h3("文本 LLM 配置"),
            p("竞赛 session 默认启用受约束的文本 LLM <font name='Mono'>assist</font> 模式。LLM 只在允许的对象、动作、目标格和空间关系内辅助意图解析，不直接生成机械臂轨迹。启动前配置："),
            code_block("export SENSORAGENT_LLM_PROVIDER=deepseek\nexport SENSORAGENT_LLM_BASE_URL=https://api.deepseek.com\nexport SENSORAGENT_LLM_API_KEY=<YOUR_API_KEY>\nexport SENSORAGENT_LLM_MODEL=deepseek-v4-flash"),
            p("如不使用联网 LLM，可在启动命令后添加 <font name='Mono'>--no-llm-grounding</font>，系统仅使用确定性规则。当前版本不需要配置 VLM 密钥。真实密钥不得写入说明书、Git 或运行日志。"),
            PageBreak(),
            h1("5. 双分支视觉系统"),
            p("实机采用完整双分支视觉方案。统一入口为 <font name='Mono'>vision.dual_branch_detect</font>，路由策略为 <font name='Mono'>industrial_first</font>：已知工业类别优先使用速度快、结果稳定的固定类别模型；未知类别、长尾描述、低置信度或固定分支异常时，回退到工业场景微调 Grounding DINO，并由 SAM 2 生成实例掩码。"),
            RouteDiagram(),
            h2("5.1 固定类别分支"),
            data_table(
                [
                    ["项目", "内容"],
                    ["权重", "models/vision/yolo11n_4class.pt"],
                    ["模型任务", "YOLO11 目标检测（detect）"],
                    ["类别", "bearing、bolt、gear、nut"],
                    ["路由条件", "规范化目标属于固定工业类别，且置信度达到 0.35"],
                    ["输出", "类别、置信度、二维框；结合 D435 点云估计三维坐标"],
                ],
                [46, 120],
            ),
            h2("5.2 开放词汇分支"),
            data_table(
                [
                    ["项目", "内容"],
                    ["检测器", "工业场景微调 Grounding DINO，本地 from_pretrained 目录"],
                    ["分割器", "SAM 2，权重 models/vision/sam2_t.pt"],
                    ["触发条件", "未知类别、长尾描述、固定分支低置信度或执行异常"],
                    ["输出", "类别、置信度、二维框、实例掩码和 RGB-D 三维位置"],
                ],
                [46, 120],
            ),
            h2("5.3 RGB-D 三维定位"),
            numbered(1, "D435 同步输出 <font name='Mono'>/vision/raw</font> 与 <font name='Mono'>/vision/cloud</font>。"),
            numbered(2, "视觉模型输出目标框或掩码，系统计算有效深度点和图像中心。"),
            numbered(3, "根据采集时刻的 TF，将 <font name='Mono'>camera_link</font> 中目标坐标变换到 <font name='Mono'>base_link</font>。"),
            numbered(4, "工作区、桌面高度、姿态和 TCP 偏置校验通过后，生成受约束抓取计划。"),
            h2("5.4 实机识别示例"),
        ]
    )
    image_path = DETECTION if DETECTION.exists() else CAPTURE
    if image_path.exists():
        story.extend(
            [
                Image(str(image_path), width=166 * mm, height=93.4 * mm),
                p("图 1  D435 实机视角下的工业螺栓识别示例。固定类别模型在现场采集画面中识别出 3 个 bolt，置信度约为 0.934、0.932 和 0.690。", CAPTION),
            ]
        )
    story.extend(
        [
            callout("类别与动作配置", "当前权重还支持 bearing、gear、nut。新增实物类别可先通过开放分支完成感知；若需要机械臂自动抓放，还必须补充对应的抓取开度、姿态、偏置、工作区和放置目标，不能只增加模型类别。"),
            PageBreak(),
            h1("6. 实机安装与校验"),
            h2("6.1 机械安装"),
            bullet("将 RM65-B 固定在刚性底座上，确认四颗 M6 底座螺栓完全紧固；壁挂或倒挂时增加防坠落措施。"),
            bullet("通过适配板将 OmniPicker 固定到 Link6 法兰，宽手指朝操作者身体外侧；确认夹爪、相机和线束不进入关节夹点。"),
            bullet("D435 采用眼在手安装，支架不得松动；USB 线缆应留足各关节极限位运动余量并可靠应力释放。"),
            bullet("工作台内放置零件源区和目标料箱，确保全部位于项目定义的受控工作区内。"),
            h2("6.2 电气和通信连接"),
            numbered(1, "关闭机械臂和夹爪电源，完成 RM65-B 24 V 电源、急停和 Ethernet 接线。禁止带电插拔机械臂航插。"),
            numbered(2, "将工控机有线网卡配置为 <font name='Mono'>192.168.1.100/24</font>，机械臂控制器地址设为 <font name='Mono'>192.168.1.19</font>。"),
            numbered(3, "OmniPicker 使用 USB 转 RS485 直接连接工控机，接线前核对夹爪 PCBA 版本对应的 A/B 定义。"),
            numbered(4, "将 D435 接入 USB 3.x，并在 Windows 中通过 usbipd 挂载至 WSL2。"),
            h2("6.3 上电检查"),
            code_block("ip route get 192.168.1.19\nping -c 3 192.168.1.19\nnc -vz 192.168.1.19 8080\nlsusb\nls -l /dev/ttyUSB0\nrs-enumerate-devices"),
            p("机械臂正常启动约需 50 秒。OmniPicker 上电后应完成零位搜索；LED 红色常亮表示故障。D435 应能被 <font name='Mono'>rs-enumerate-devices</font> 正确枚举。"),
            h2("6.4 现场参数校验"),
            data_table(
                [
                    ["校验项", "要求"],
                    ["急停", "按下后机械臂停止；复位流程明确"],
                    ["TF", "base_link <- Link6 <- camera_link 连续、方向正确"],
                    ["相机同步", "RGB 与点云时间差不高于 50 ms"],
                    ["工作区", "X [-0.55,-0.20] m；Y [-0.26,0.18] m；Z [0,0.35] m"],
                    ["夹爪", "开合方向、零位、120 mm 行程映射和反馈状态正确"],
                    ["观测位", "机械臂到达后相机完整覆盖源区和目标区"],
                    ["抓放参数", "螺母、螺栓、滚柱等对象分别完成低速空载验证"],
                ],
                [48, 118],
            ),
            PageBreak(),
            h1("7. 启动与使用"),
            h2("7.1 运动前安全检查"),
            data_table(
                [
                    ["检查", "确认内容"],
                    ["□", "急停按钮有效且操作员可立即触及"],
                    ["□", "机械臂工作空间内无人、无遗留工具和无关线缆"],
                    ["□", "RM65-B、D435、OmniPicker 固定可靠，线缆无拉扯"],
                    ["□", "零件源区、目标料箱、桌面高度与配置一致"],
                    ["□", "手眼标定、TCP、夹爪和放置点已经完成现场验证"],
                    ["□", "192.168.1.19 可达，/dev/ttyUSB0 与 D435 已接入 WSL2"],
                    ["□", "操作员全程监督，不离开控制位置"],
                ],
                [16, 150],
            ),
            h2("7.2 启动完整硬件 Agent"),
            p("进入项目根目录。确认当前 <font name='Mono'>python3</font> 已安装全部依赖，或已设置 <font name='Mono'>SENSORAGENT_PYTHON</font>。实机演示采用单一启动命令，由脚本启动 ROS 2 硬件栈，然后进入持续工业 Agent loop："),
            code_block("cd /home/hcn/workspace/SensorAgent\nbash scripts/linux/run_hardware_agent.sh --enable-motion"),
            p("脚本按顺序完成以下操作："),
            numbered(1, "执行 <font name='Mono'>start_hardware_stack.sh</font>，检查并依次加载 ROS 2、Island-Arm 和 SensorAgent overlay；路径可由环境变量覆盖。"),
            numbered(2, "启动 RM65-B 驱动、机械臂控制服务、OmniPicker、D435、静态手眼 TF 和 8766 硬件桥。"),
            numbered(3, "以 <font name='Mono'>backend=hardware</font>、<font name='Mono'>configs/competition_hardware.yaml</font> 进入文本交互模式，硬件 ActionList 直接调用 <font name='Mono'>vision.dual_branch_detect</font>。"),
            numbered(4, "<font name='Mono'>--enable-motion</font> 向 session 添加 <font name='Mono'>--execute</font>，允许经安全边界检查后的实机动作。"),
            callout("启动前提", "仅在完成第 7.1 节全部检查后使用 --enable-motion。首次部署应先不加该参数进行无运动检查，并通过 /health、/ready、ROS 服务和相机话题确认所有设备正常。最终集成版还必须确认 allow_motion 启动参数已传入硬件桥，不能只依据控制台提示判断运动门控。", warning=True),
            h2("7.3 交互命令"),
            p("出现输入提示后，可连续输入分拣任务。系统完成一轮后回到 IDLE，等待下一条指令。示例："),
            code_block("把左边的螺母放到一号格\n把短螺栓放到二号格\n把离机械臂最近的滚柱放到三号格\n状态\n退出"),
            p("固定模型类别使用中文别名映射：<font name='Mono'>螺母 -> nut</font>、<font name='Mono'>螺栓 -> bolt</font>、<font name='Mono'>齿轮 -> gear</font>、<font name='Mono'>轴承 -> bearing</font>。滚柱等非固定类别目标由 Grounding DINO + SAM 2 分支处理。"),
            h2("7.4 语音模式"),
            code_block("bash scripts/linux/run_hardware_agent.sh --enable-motion --mode voice"),
            p("语音模式使用 VAD/ASR 获取指令，任务执行链与文本模式一致。现场噪声较大时应优先使用文本模式，或在部署前重新验证麦克风、VAD 阈值和识别模型。"),
            h2("7.5 状态和健康检查"),
            code_block("curl -fsS http://127.0.0.1:8766/health | python3 -m json.tool\ncurl -fsS http://127.0.0.1:8766/ready  | python3 -m json.tool\ncurl -fsS http://127.0.0.1:8766/state  | python3 -m json.tool\ncurl -fsS http://127.0.0.1:8766/gripper/state | python3 -m json.tool"),
            p("<font name='Mono'>/ready</font> 应显示 movej、move_to_pose、movel、get_current_pose、gripper_open、gripper_close 和 gripper_position 均可用。最终集成版的 session readiness 等待项必须与这些硬件键一致。"),
            h2("7.6 正常停止与紧急停止"),
            bullet("正常结束：在 Agent 中输入 <b>退出</b>，或按 Ctrl-C。启动脚本会尽力调用硬件桥 <font name='Mono'>/stop</font>，随后结束 ROS launch 子进程。"),
            bullet("软件停止：<font name='Mono'>curl -X POST http://127.0.0.1:8766/stop</font>。该接口向机械臂驱动发布停止命令。"),
            bullet("发生人员侵入、碰撞风险、失控动作或通信异常时：立即按下物理急停。HTTP stop 不能代替硬件急停。"),
            PageBreak(),
            h1("8. 通信接口"),
            h2("8.1 HTTP/JSON 硬件桥"),
            data_table(
                [
                    ["方法", "路径", "功能"],
                    ["GET", "/health", "桥接进程与运动门控状态"],
                    ["GET", "/ready", "机械臂和夹爪 ROS 服务可用性"],
                    ["GET", "/state", "机械臂当前状态"],
                    ["GET", "/gripper/state", "OmniPicker 当前状态"],
                    ["POST", "/move-joints", "关节运动"],
                    ["POST", "/move-pose", "末端位姿运动"],
                    ["POST", "/move-linear", "末端直线运动"],
                    ["POST", "/gripper/open", "夹爪打开"],
                    ["POST", "/gripper/close", "夹爪闭合"],
                    ["POST", "/stop", "停止机械臂运动"],
                ],
                [24, 54, 88],
            ),
            h2("8.2 ROS 2 接口"),
            data_table(
                [
                    ["类型", "名称", "说明"],
                    ["Service", "/task/arm/movej_deg", "关节角运动"],
                    ["Service", "/task/arm/move_to_pose", "笛卡尔位姿运动"],
                    ["Service", "/task/arm/movel", "直线运动"],
                    ["Service", "/task/arm/get_current_pose", "读取末端位姿"],
                    ["Service", "/task/op/open、/close、/set_position", "夹爪开、关和指定位置"],
                    ["Topic", "/omnipicker_state", "夹爪开度、运动和故障反馈"],
                    ["Topic", "/vision/raw", "D435 BGR8 彩色图像"],
                    ["Topic", "/vision/cloud", "与彩色图对齐的 x/y/z/u/v 点云"],
                    ["TF", "base_link -> Link6 -> camera_link", "机械臂、工具和眼在手相机坐标变换"],
                ],
                [26, 75, 65],
            ),
            h2("8.3 安全边界"),
            p("硬件桥对坐标系、四元数、工作区、速度和运动开关进行输入校验。当前项目工作盒为 X <font name='Mono'>[-0.55,-0.20]</font> m、Y <font name='Mono'>[-0.26,0.18]</font> m、Z <font name='Mono'>[0,0.35]</font> m，机械臂驱动速度上限为 50。该边界是现场软件限制，不等同于碰撞规划或安全认证。"),
            h1("9. 故障排查"),
            data_table(
                [
                    ["现象", "可能原因", "处理方法"],
                    ["无法连接 192.168.1.19", "网卡地址/WSL 网络模式错误", "确认 Windows 网卡为 192.168.1.100/24；启用 mirrored；检查网线和 8080 端口"],
                    ["TCP 可通但状态不更新", "UDP 8089 被 Windows/Hyper-V 防火墙阻断", "检查机械臂 udp_ip；放行入站 UDP 8089；抓包确认状态帧"],
                    ["找不到 /dev/ttyUSB0", "USB-RS485 未附加到 WSL 或权限不足", "重新 usbipd attach；检查 lsusb；加入 dialout 组并重启 WSL"],
                    ["夹爪红灯/故障码 04", "开度端点超限", "停止命令，重新上电归零；最大打开命令保持低于满量程端点"],
                    ["D435 无图像或频繁掉线", "USB 2.0、集线器带宽不足或 USB/IP 丢失", "改用直连 USB 3.x；重新挂载；执行 rs-enumerate-devices"],
                    ["图像存在但无三维坐标", "点云字段、时间同步或 TF 不满足要求", "检查 /vision/cloud 的 x/y/z/u/v、point_step=20、时间差及 base_link<-camera_link"],
                    ["固定分支无结果", "类别不在四类中、置信度低或中英文别名未映射", "确认类别表和阈值；由 Grounding DINO + SAM 2 回退处理"],
                    ["固定分支要求 mask 时报错", "yolo11n_4class.pt 是 detect 模型", "取消固定分支原生 mask 强制要求，或更换真正的 YOLO11-seg 权重"],
                    ["模型加载失败", "路径错误、权重不完整或 Python 环境错误", "核对路径和 SHA-256；确认在 .venv312 中运行"],
                    ["启动等待约 60 秒后退出", "session 等待项与硬件 /ready 键不一致", "确认最终集成版等待 movej、move_to_pose、movel、get_current_pose 和夹爪服务键"],
                    ["Agent 与 ROS 导入冲突", "Agent 环境直接导入 Humble rclpy", "Agent 使用 .venv312；ROS 和采集使用 /usr/bin/python3"],
                ],
                [39, 51, 76],
            ),
            h2("9.1 快速诊断命令"),
            code_block("ros2 node list\nros2 service list | sort\nros2 topic hz /vision/raw\nros2 topic hz /vision/cloud\nros2 topic echo --once /omnipicker_state\nros2 run tf2_ros tf2_echo base_link camera_link"),
            h2("9.2 相机与点云采集验证"),
            code_block("/usr/bin/python3 scripts/linux/capture_hardware_rgb_cloud.py \\\n  --out-dir /tmp/sensoragent-hardware-capture \\\n  --image-topic /vision/raw \\\n  --cloud-topic /vision/cloud \\\n  --base-frame base_link \\\n  --timeout 30"),
            p("成功后目录中应生成 <font name='Mono'>rgb.npy</font>、<font name='Mono'>rgb.png</font>、<font name='Mono'>cloud_xyzuv.npy</font> 和 <font name='Mono'>manifest.json</font>。"),
            PageBreak(),
            h1("10. 安全、维护与复现要求"),
            h2("10.1 安全操作"),
            bullet("首次投产、重新安装或修改安全参数后，重新完成整机风险评估和全部安全功能检查。"),
            bullet("安全设备不得接入普通 I/O；人员不得停留在机械臂工作范围内。"),
            bullet("发生夹困时立即急停并切断主电源，等待控制器完全断电后再按厂商流程解除，禁止强拉机械臂。"),
            bullet("运行中或停机后不得立即触摸发热部位；进入工作空间维修前必须完全断电。"),
            bullet("任何未经验证的模型、抓取偏置、放置点、手眼矩阵或工作区参数不得直接用于实机。"),
            h2("10.2 日常维护"),
            data_table(
                [
                    ["周期", "检查项目"],
                    ["每次启动前", "急停、底座、末端转接件、相机支架、线束、USB 接入、网络、源区和料箱"],
                    ["每周", "机械臂异常噪声和松动、夹爪手指磨损、RS485 接头、相机镜面清洁"],
                    ["配置变更后", "模型 SHA-256、类别映射、TF、工作区、观测位、抓取/放置姿态和速度"],
                    ["系统升级后", "Python/ROS 依赖、驱动通信、/health、/ready、无运动 dry-run 和低速单物体实机测试"],
                ],
                [38, 128],
            ),
            h2("10.3 复现记录"),
            p("为保证演示可追溯，建议每次正式运行记录 Git commit、配置文件、模型校验值、设备 IP/串口、标定文件、运行日志和现场照片。不得在仓库中提交真实 API 密钥。"),
            h1("附录 A：部署参数速查"),
            data_table(
                [
                    ["项目", "值"],
                    ["项目目录", "/home/hcn/workspace/SensorAgent"],
                    ["驱动目录", "/home/hcn/Island-Arm"],
                    ["实机启动", "bash scripts/linux/run_hardware_agent.sh --enable-motion"],
                    ["机械臂", "RM65-B；192.168.1.19:8080"],
                    ["主机网卡", "192.168.1.100/24；UDP 8089，周期 5 ms"],
                    ["夹爪", "OmniPicker；/dev/ttyUSB0；115200 8N1"],
                    ["相机", "D435；/vision/raw；/vision/cloud；5 Hz 集成发布"],
                    ["硬件桥", "http://127.0.0.1:8766"],
                    ["固定模型", "models/vision/yolo11n_4class.pt"],
                    ["开放模型", "models/vision/grounding-dino/grounding_dino"],
                    ["掩码模型", "models/vision/sam2_t.pt"],
                ],
                [44, 122],
            ),
            h1("附录 B：完整模型校验值"),
            code_block("yolo11n_4class.pt\n  f6be64b7b6ae208e0734743cbe36ea147e7c75b8591a0edc3582f22ae446be24\n\ngrounding_dino/model.safetensors\n  c23e9c47c64ff3db8f4864d6d00d6225b01986ac2bea2c44e7c856177bda4b8d\n\nsam2_t.pt\n  94375f988270836169320bd901960c67b5770e8bef3867d70102f01a8b5ca501"),
            h1("附录 C：资料依据"),
            bullet("SensorAgent submission 分支 README、环境配置指南、竞赛 Agent 复现指南、硬件配置和 ROS 2 硬件桥源码。"),
            bullet("Island-Arm 实机驱动工作区及 RM65、OmniPicker、D435 部署配置。"),
            bullet("《睿尔曼超轻量仿人机械臂（RM65&RM75 系列）V1.2.0 用户使用说明》。"),
            bullet("《OmniPicker 产品手册》，硬件 Ver1.2、软件 Ver3.2.8。"),
            bullet("D435 实机采集记录 <font name='Mono'>logs/vision/manual_probe_repeat_4</font>。"),
            Spacer(1, 14 * mm),
            callout("文档结束", "完成安装和参数校验后，应先执行无运动验证，再以单个零件、低风险姿态完成实机验收，最后进入正式演示。"),
        ]
    )
    return story


def build_concise_story() -> list:
    """Build the evaluator-facing installation and one-command run guide."""

    story: list = []
    cover(story)
    story.extend(
        [
            p("导览", FRONT_H1),
            p("本文档用于帮助评委在 Ubuntu 22.04 环境中完成 SensorAgent 的依赖安装、硬件连接和一键运行，并快速了解相机、机械臂、夹爪、ROS 2 与 Agent 之间的通信及系统集成方式。", LEAD),
            data_table(
                [
                    ["导览内容", "配置说明"],
                    ["应用", "根据中文或英文指令识别工业零件，并控制机械臂完成抓取和分拣"],
                    ["仿真", "RM65-B + Robotiq 2F-85 + 固定俯视 RGB-D 相机"],
                    ["实机", "RM65-B + RealSense D435 + OmniPicker"],
                    ["软件", "Ubuntu 22.04、ROS 2 Humble、Python >=3.10"],
                ],
                [38, 128],
            ),
            p("快速运行入口", FRONT_H2),
            data_table(
                [
                    ["模式", "启动命令"],
                    ["仿真·文本", "bash scripts/linux/run_sim_agent.sh"],
                    ["仿真·语音", "bash scripts/linux/run_sim_agent.sh --mode voice"],
                    ["实机·文本", "bash scripts/linux/run_hardware_agent.sh --enable-motion"],
                    ["实机·语音", "bash scripts/linux/run_hardware_agent.sh --enable-motion --mode voice"],
                ],
                [38, 128],
            ),
            Spacer(1, 8 * mm),
            p("目录", FRONT_H1),
        ]
    )
    toc = TableOfContents()
    toc.levelStyles = [
        ParagraphStyle("ConciseTOC1", fontName="CN-Bold", fontSize=10, leading=18, leftIndent=0, textColor=NAVY),
        ParagraphStyle("ConciseTOC2", fontName="CN", fontSize=9, leading=15, leftIndent=14, textColor=INK),
    ]
    story.extend([toc, PageBreak()])

    story.extend(
        [
            h1("1. 环境配置"),
            h2("1.1 运行环境"),
            data_table(
                [
                    ["环境组件", "版本 / 配置要求"],
                    ["操作系统", "Ubuntu 22.04.5 LTS"],
                    ["ROS", "ROS 2 Humble，系统 Python 3.10"],
                    ["Agent Python", "项目支持 >=3.10；现场使用 3.12.13"],
                    ["CPU / GPU", "Intel Core i7-14700HX / RTX 4070 Laptop 8 GB"],
                    ["GPU 软件", "NVIDIA Driver 566.36；PyTorch 2.13.0+cu126"],
                    ["主要组件", "Transformers 4.57.6、Ultralytics 8.4.117、librealsense 2.58.3"],
                ],
                [46, 120],
            ),
            p("仿真与实机使用同一套 Agent 和任务配置；仿真由 Gazebo Sim、MoveIt 2 和 ros2_control 提供执行环境，实机由 RM65-B、D435 与 OmniPicker 驱动提供执行环境。"),
            PageBreak(),
            h1("2. 硬件配置"),
            h2("2.1 仿真硬件配置"),
            data_table(
                [
                    ["组件", "仿真配置"],
                    ["场景", "Gazebo Sim；industrial_sorting_metal_pgs.sdf 工业分拣场景"],
                    ["机械臂", "RealMan RM65-B，6 自由度；实体名 rm65_b_robotiq_2f85"],
                    ["运动规划", "MoveIt 2；规划组 rm_group；base_link -> robotiq_85_tcp"],
                    ["机械臂控制器", "rm_group_controller；FollowJointTrajectory；joint1～joint6"],
                    ["夹爪", "Robotiq 2F-85；最大开度 84.8 mm；最大控制 effort 20.0"],
                    ["夹爪控制", "robotiq_gripper_controller/gripper_cmd；左右 knuckle joint"],
                    ["仿真桥", "sensoragent_robot_bridge；http://127.0.0.1:8765"],
                ],
                [48, 118],
            ),
            h2("2.2 仿真相机配置"),
            data_table(
                [
                    ["相机参数", "仿真配置"],
                    ["相机模型", "sensoragent_rgbd_rig；固定俯视 Gazebo RGB-D 相机"],
                    ["世界坐标", "xyz=(0.34, 0, 1.06) m，朝向工作台"],
                    ["RGB / 深度", "424×240，10 Hz；水平视场 1.047 rad（约 60°）"],
                    ["裁剪范围", "0.10～3.0 m"],
                    ["ROS 话题", "/industrial_camera/image、/industrial_camera/depth_image、/industrial_camera/camera_info"],
                    ["TF", "world -> sensoragent_rgbd_rig/rig/depth_camera"],
                ],
                [48, 118],
            ),
            h2("2.3 实机硬件清单"),
            data_table(
                [
                    ["设备", "现场配置", "连接方式"],
                    ["机械臂", "RealMan RM65-B；6 自由度；5 kg；610 mm；重复定位 ±0.05 mm", "Ethernet"],
                    ["相机", "Intel RealSense D435；眼在手安装于 Link6", "USB 3.x"],
                    ["夹爪", "智元灵犀 X1 OmniPicker；120 mm 行程；30 N；115200 8N1", "USB 转 RS485"],
                    ["计算平台", "i7-14700HX；RTX 4070 Laptop 8 GB；Ubuntu 22.04", "本机"],
                ],
                [30, 92, 44],
            ),
            h2("2.4 实机相机数据"),
            data_table(
                [
                    ["相机参数", "实机配置"],
                    ["彩色流", "1920×1080@30 FPS，BGR8"],
                    ["深度流", "1280×720@30 FPS，深度对齐到彩色图"],
                    ["Agent 发布频率", "5 Hz"],
                    ["话题", "/vision/raw、/vision/cloud"],
                    ["坐标系", "camera_link；通过眼在手 TF 转换到 base_link"],
                ],
                [48, 118],
            ),
            h2("2.5 实机机械臂与夹爪参数"),
            data_table(
                [
                    ["控制参数", "实机配置"],
                    ["机械臂地址", "192.168.1.19:8080"],
                    ["状态回传", "主机 192.168.1.100:8089，UDP 周期 5 ms"],
                    ["夹爪设备", "/dev/ttyUSB0，115200，8N1"],
                    ["夹爪位置", "0.0 为闭合，1.0 为完全张开"],
                    ["软件工作区", "X [-0.55,-0.20] m；Y [-0.26,0.18] m；Z [0,0.35] m"],
                ],
                [48, 118],
            ),
            PageBreak(),
            h1("3. 依赖安装"),
            h2("3.1 ROS 2 与系统依赖"),
            p("按照 ROS 2 官方 Ubuntu 安装流程配置软件源后，安装 Humble、构建工具、RealSense 和运行依赖："),
            code_block("sudo apt update\nsudo apt install -y ros-humble-desktop ros-humble-rmw-cyclonedds-cpp \\\n  ros-humble-xacro ros-humble-robot-state-publisher \\\n  python3-rosdep python3-colcon-common-extensions \\\n  libturbojpeg0-dev librealsense2-dev librealsense2-utils \\\n  netcat-openbsd usbutils\nrosdep update"),
            h2("3.2 准备仿真工作区"),
            p("首次运行仿真时执行以下准备脚本，自动安装 rosdep 依赖，并构建 RM65-B、Robotiq、Gazebo bringup 与仿真桥："),
            code_block("cd ~/SensorAgent\nbash scripts/linux/prepare_rm65_b_sim.sh"),
            h2("3.3 准备实机工作区"),
            p("SensorAgent 已包含 RM65-B、OmniPicker、D435 驱动、ROS 2 接口和硬件桥。首次运行实机时执行以下准备脚本，统一安装依赖并完成构建："),
            code_block("cd ~/SensorAgent\nbash scripts/linux/prepare_hardware_stack.sh"),
            h2("3.4 安装 Python 依赖"),
            p("项目已将核心、语音和视觉依赖统一到一个 <font name='Mono'>requirements.txt</font>："),
            code_block("cd ~/SensorAgent\npython3.12 -m venv .venv312\nsource .venv312/bin/activate\npython -m pip install --upgrade pip setuptools wheel\npython -m pip install -r requirements.txt\npython -m pip install onnxruntime"),
            PageBreak(),
            h1("4. 模型与运行配置"),
            h2("4.1 模型文件"),
            p("将项目组提供的模型包放到以下位置。模型权重不通过 Git 下载："),
            data_table(
                [
                    ["功能", "提交后的模型路径"],
                    ["YOLO11 固定类别分支", "models/vision/yolo11-seg/industrial-best.pt"],
                    ["Grounding DINO 开放词汇分支", "models/vision/grounding-dino/industrial-open-vocab"],
                    ["SAM 2 实例掩码", "models/vision/sam2_t.pt"],
                    ["ASR（仅语音模式）", "models/asr/sense-voice/model.int8.onnx、tokens.txt"],
                    ["VAD（仅语音模式）", "models/asr/vad/silero_vad.onnx"],
                ],
                [58, 108],
            ),
            h2("4.2 双分支配置"),
            p("在 <font name='Mono'>configs/competition_hardware.yaml</font> 中使用现场模型路径："),
            code_block("integrations:\n  vision:\n    backend: dual_branch\n    model_path: models/vision/yolo11-seg/industrial-best.pt\n    grounding_dino_model: models/vision/grounding-dino/industrial-open-vocab\n    sam2_model_path: models/vision/sam2_t.pt\n    dual_branch:\n      route_policy: industrial_first\n      fallback_on_error: true\n      min_fixed_confidence: 0.35"),
            p("固定类别分支优先识别项目工业类别，例如 roller、hex_nut 和 short_bolt；未知类别、长尾描述、低置信度或固定分支失败时，自动转入 Grounding DINO + SAM 2。仿真 RGB-D 深度或实机 D435 点云用于将二维识别结果转换为 <font name='Mono'>base_link</font> 下的三维坐标。"),
            h2("4.3 启动环境变量"),
            code_block("export SENSORAGENT_PYTHON=$HOME/SensorAgent/.venv312/bin/python\nexport SENSORAGENT_ROS_PYTHON=/usr/bin/python3\nexport SENSORAGENT_ROS_SETUP=/opt/ros/humble/setup.bash\nexport SENSORAGENT_ROS_WS_SETUP=$HOME/SensorAgent/ros2_ws/install/local_setup.bash"),
            p("如使用默认 LLM 辅助指令理解，再设置 <font name='Mono'>SENSORAGENT_LLM_API_KEY</font>、<font name='Mono'>SENSORAGENT_LLM_MODEL</font> 和 <font name='Mono'>SENSORAGENT_LLM_BASE_URL</font>。不使用联网 LLM 时，在启动命令后增加 <font name='Mono'>--no-llm-grounding</font>。"),
            PageBreak(),
            h1("5. 一键运行完整流程"),
            h2("5.1 运行前检查"),
            data_table(
                [
                    ["检查项", "预期结果"],
                    ["机械臂网络", "ping 192.168.1.19 成功，TCP 8080 可连接"],
                    ["夹爪串口", "/dev/ttyUSB0 存在，当前用户可读写"],
                    ["D435", "rs-enumerate-devices 能找到设备，使用 USB 3.x"],
                    ["ROS workspace", "ros2_ws/install setup 存在，实机驱动与硬件桥可被 ros2 pkg 找到"],
                    ["视觉模型", "第 4.1 节三个视觉模型路径存在"],
                    ["语音模式", "ASR、VAD 模型存在，麦克风可进行 16 kHz 单声道采样"],
                    ["安全", "急停有效，机械臂工作空间内无人且无障碍物"],
                ],
                [48, 118],
            ),
            h2("5.2 仿真链路"),
            p("脚本会启动工业分拣 Gazebo 场景、RM65-B/Robotiq 模型、MoveIt 2、仿真桥和 Agent。仿真默认执行动作；只验证指令解析时增加 <font name='Mono'>--dry-run</font>。"),
            code_block("# 文本\nbash scripts/linux/run_sim_agent.sh\n\n# 语音\nbash scripts/linux/run_sim_agent.sh --mode voice"),
            h2("5.3 实机链路"),
            p("统一 launch 同时启动 RM65-B、OmniPicker、D435 驱动节点和 SensorAgent 硬件桥。硬件桥只将 HTTP 请求转换为 ROS 2 Service/Topic 调用，不负责启动驱动或给硬件上电。"),
            code_block("# 文本\nbash scripts/linux/run_hardware_agent.sh --enable-motion\n\n# 语音\nbash scripts/linux/run_hardware_agent.sh --enable-motion --mode voice"),
            h2("5.4 指令与输出"),
            p("出现 <font name='Mono'>&gt;</font> 提示后直接输入指令，例如："),
            code_block("把左边的螺母放到一号格\n把短螺栓放到二号格\n把离机械臂最近的滚柱放到三号格\n状态\n退出"),
            p("每条指令完成后系统返回 IDLE，继续等待下一条。运行结果打印为 JSON，并保存到 <font name='Mono'>logs/tasks/</font>；实机图像和点云保存在 <font name='Mono'>logs/vision/hardware_latest/</font>。"),
            p("输入 <b>退出</b> 或按 Ctrl-C 正常结束；发生碰撞风险或异常动作时立即使用机械臂物理急停。"),
        ]
    )
    story.extend(
        [
            PageBreak(),
            h1("6. 通信接口与系统集成"),
            h2("6.1 集成方式"),
            p("Agent 负责语言理解、双分支视觉、任务编排和恢复；ROS 2 负责相机、TF、运动规划、机械臂及夹爪。运动命令与状态通过本机 HTTP/JSON 桥传递，视觉模块通过下表中的 ROS 2 相机话题和 TF 获取观测。"),
            h2("6.2 关键节点"),
            data_table(
                [
                    ["环境", "节点 / 组件", "作用"],
                    ["仿真", "robot_state_publisher、move_group", "发布机器人 TF；完成 RM65-B 运动规划"],
                    ["仿真", "controller_manager、rm_group_controller", "关节状态与六轴轨迹控制"],
                    ["仿真", "robotiq_gripper_action_bridge", "将夹爪 Action 转为 Gazebo 力控制命令"],
                    ["仿真", "ros_gz_bridge", "桥接时钟、RGB、深度与 CameraInfo"],
                    ["仿真", "sensoragent_robot_bridge", "向 Agent 提供 127.0.0.1:8765 HTTP 接口"],
                    ["实机", "rm_driver、arm_control_server", "RM65-B 状态通信与运动服务"],
                    ["实机", "op_control_node、dep_cam", "OmniPicker 控制；D435 图像和点云"],
                    ["实机", "sensoragent_hardware_bridge", "向 Agent 提供 127.0.0.1:8766 HTTP 接口"],
                ],
                [22, 76, 68],
            ),
            h2("6.3 HTTP/JSON 接口"),
            p("仿真桥地址为 <font name='Mono'>http://127.0.0.1:8765</font>，实机桥地址为 <font name='Mono'>http://127.0.0.1:8766</font>；两者为 Agent 提供一致的主要控制接口。"),
            data_table(
                [
                    ["接口", "用途"],
                    ["GET /health、/ready", "检查硬件桥与 ROS 服务状态"],
                    ["GET /state、/gripper/state", "读取机械臂和夹爪状态"],
                    ["POST /move-joints、/move-pose、/move-linear", "执行机械臂关节、位姿和直线运动"],
                    ["POST /gripper/open、/gripper/close", "控制仿真 Robotiq 或实机 OmniPicker"],
                    ["POST /stop", "请求停止机械臂运动"],
                ],
                [74, 92],
            ),
            h2("6.4 ROS 2 接口"),
            data_table(
                [
                    ["环境 / 类型", "接口", "用途"],
                    ["仿真 Topic", "/industrial_camera/image、/industrial_camera/depth_image、/industrial_camera/camera_info", "RGB、深度和内参"],
                    ["仿真 Action", "/rm_group_controller/follow_joint_trajectory", "RM65-B 六轴轨迹"],
                    ["仿真 Action", "/robotiq_gripper_controller/gripper_cmd", "Robotiq 夹爪开度"],
                    ["仿真 Topic", "/joint_states", "机械臂和夹爪关节状态"],
                    ["实机 Topic", "/vision/raw、/vision/cloud", "D435 彩色图像和对齐点云"],
                    ["实机 Service", "/task/arm/movej_deg、/task/arm/move_to_pose、/task/arm/movel", "关节、位姿和直线运动"],
                    ["实机 Service", "/task/arm/get_current_pose", "读取当前末端位姿"],
                    ["实机 Service", "/task/op/open、/task/op/close、/task/op/set_position", "OmniPicker 开合及指定位置"],
                    ["实机 Topic", "/omnipicker_state", "夹爪状态反馈"],
                    ["实机 TF", "base_link -> Link6 -> camera_link", "机械臂与眼在手相机坐标变换"],
                ],
                [31, 79, 56],
            ),
            h2("6.5 完整工作流程"),
            code_block("自然语言指令 -> 目标与料箱解析\n-> ROS 2 相机话题 / TF -> 双分支视觉与三维定位\n-> 抓取 / 放置规划 -> HTTP/JSON 仿真桥或实机桥\n-> ROS 2 控制接口 -> RM65-B + 夹爪\n-> 状态验证 -> 日志记录 -> 返回 IDLE"),
        ]
    )
    return story


def main() -> None:
    document = ManualDocTemplate(str(OUTPUT))
    document.multiBuild(build_concise_story())
    # multiBuild leaves superseded page-tree objects from its TOC passes. Rewrite
    # once so simple PDF inspectors report the same final page count as readers.
    cleaned = OUTPUT.with_suffix(".clean.pdf")
    reader = PdfReader(str(OUTPUT))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    if reader.metadata:
        writer.add_metadata(dict(reader.metadata))

    def copy_outline(items, parent=None) -> None:
        previous = parent
        for item in items:
            if isinstance(item, list):
                copy_outline(item, previous)
                continue
            page_number = reader.get_destination_page_number(item)
            previous = writer.add_outline_item(item.title, page_number, parent=parent)

    copy_outline(reader.outline)
    with cleaned.open("wb") as stream:
        writer.write(stream)
    cleaned.replace(OUTPUT)
    print(OUTPUT)


if __name__ == "__main__":
    main()
