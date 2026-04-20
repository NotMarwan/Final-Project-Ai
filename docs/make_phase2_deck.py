from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE
from pptx.enum.shapes import MSO_AUTO_SHAPE_TYPE, MSO_SHAPE_TYPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor


OUT = Path(r"C:\Users\PCD\Downloads\Final Project AI Sentinel\docs\AI_Sentinel_Phase2_Midterm_Deck.pptx")


BG = RGBColor(11, 18, 32)
PANEL = RGBColor(18, 28, 48)
PANEL_2 = RGBColor(24, 36, 60)
TEXT = RGBColor(243, 247, 255)
MUTED = RGBColor(170, 184, 206)
ACCENT = RGBColor(45, 212, 191)
GOLD = RGBColor(245, 158, 11)
RED = RGBColor(248, 113, 113)
WHITE = RGBColor(255, 255, 255)


def set_bg(slide, color=BG):
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = color


def add_top_bar(slide, title: str, subtitle: str | None = None):
    bar = slide.shapes.add_shape(MSO_AUTO_SHAPE_TYPE.RECTANGLE, 0, 0, Inches(13.333), Inches(0.8))
    bar.fill.solid()
    bar.fill.fore_color.rgb = PANEL_2
    bar.line.color.rgb = PANEL_2

    accent = slide.shapes.add_shape(MSO_AUTO_SHAPE_TYPE.RECTANGLE, 0, 0.76 * Inches(1), Inches(13.333), Inches(0.06))
    accent.fill.solid()
    accent.fill.fore_color.rgb = ACCENT
    accent.line.color.rgb = ACCENT

    tbox = slide.shapes.add_textbox(Inches(0.45), Inches(0.14), Inches(8.8), Inches(0.42))
    tf = tbox.text_frame
    tf.clear()
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.RIGHT
    run = p.add_run()
    run.text = title
    run.font.name = "Arial"
    run.font.size = Pt(21)
    run.font.bold = True
    run.font.color.rgb = TEXT

    if subtitle:
        sbox = slide.shapes.add_textbox(Inches(0.5), Inches(0.48), Inches(9.6), Inches(0.25))
        tf2 = sbox.text_frame
        tf2.clear()
        p2 = tf2.paragraphs[0]
        p2.alignment = PP_ALIGN.RIGHT
        r2 = p2.add_run()
        r2.text = subtitle
        r2.font.name = "Arial"
        r2.font.size = Pt(10.5)
        r2.font.color.rgb = MUTED


def add_footer(slide, text="AI Sentinel | Phase 2 Mid-Term"):
    fbox = slide.shapes.add_textbox(Inches(0.35), Inches(7.03), Inches(6), Inches(0.22))
    tf = fbox.text_frame
    tf.clear()
    p = tf.paragraphs[0]
    r = p.add_run()
    r.text = text
    r.font.name = "Arial"
    r.font.size = Pt(8.5)
    r.font.color.rgb = MUTED


def add_text(slide, x, y, w, h, text, size=20, color=TEXT, bold=False, align=PP_ALIGN.RIGHT, fill=None, border=None, font="Arial"):
    shape = slide.shapes.add_textbox(x, y, w, h)
    tf = shape.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.TOP
    tf.clear()
    lines = text.split("\n")
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        r = p.add_run()
        r.text = line
        r.font.name = font
        r.font.size = Pt(size)
        r.font.color.rgb = color
        r.font.bold = bold
    if fill is not None:
        shape.fill.solid()
        shape.fill.fore_color.rgb = fill
    if border is not None:
        shape.line.color.rgb = border
    else:
        shape.line.color.rgb = BG
    return shape


def add_panel(slide, x, y, w, h, title, body, accent=ACCENT):
    panel = slide.shapes.add_shape(MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE, x, y, w, h)
    panel.fill.solid()
    panel.fill.fore_color.rgb = PANEL
    panel.line.color.rgb = accent
    panel.line.width = Pt(1.5)
    add_text(slide, x + Inches(0.18), y + Inches(0.1), w - Inches(0.36), Inches(0.3), title, size=15, bold=True, color=WHITE)
    add_text(slide, x + Inches(0.18), y + Inches(0.42), w - Inches(0.36), h - Inches(0.5), body, size=11, color=MUTED)


def add_placeholder(slide, x, y, w, h, label, kind="صورة"):
    box = slide.shapes.add_shape(MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE, x, y, w, h)
    box.fill.solid()
    box.fill.fore_color.rgb = RGBColor(14, 22, 38)
    box.line.color.rgb = GOLD
    box.line.dash_style = 1
    tf = box.text_frame
    tf.word_wrap = True
    tf.clear()
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = f"[ضع هنا {kind}]\n{label}"
    r.font.name = "Arial"
    r.font.size = Pt(13)
    r.font.bold = True
    r.font.color.rgb = GOLD
    return box


def add_bullets(slide, x, y, w, h, title, bullets, title_size=17, bullet_size=12):
    add_text(slide, x, y, w, Inches(0.3), title, size=title_size, bold=True, color=WHITE)
    box = slide.shapes.add_textbox(x, y + Inches(0.35), w, h - Inches(0.35))
    tf = box.text_frame
    tf.word_wrap = True
    tf.clear()
    for i, bullet in enumerate(bullets):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.RIGHT
        p.level = 0
        r = p.add_run()
        r.text = f"• {bullet}"
        r.font.name = "Arial"
        r.font.size = Pt(bullet_size)
        r.font.color.rgb = MUTED
    return box


prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)

# Slide 1: Title
slide = prs.slides.add_slide(prs.slide_layouts[6])
set_bg(slide)
add_top_bar(slide, "AI Sentinel", "Phase 2 Mid-Term Presentation | The project that turns camera noise into evidence")

add_text(slide, Inches(0.55), Inches(1.25), Inches(6.1), Inches(0.85),
         "Deep Learning-Based Real-Time Physical Violence Detection for Intelligent Surveillance",
         size=23, bold=True, color=TEXT)
add_text(slide, Inches(0.58), Inches(2.18), Inches(5.7), Inches(1.0),
         "من مراقبة سلبية إلى إنذار حي ودليل قابل للاسترجاع خلال ثوانٍ",
         size=20, color=ACCENT, bold=True)
add_text(slide, Inches(0.58), Inches(3.1), Inches(5.6), Inches(1.5),
         "Group G-9\nMarwan Masri | Abdulaziz AlHazmi | Saleh Hardi | Mohannad Moafa | Wael Alfaifi\nSupervisor: Dr. Abdoh Jabbari",
         size=14, color=MUTED)
add_placeholder(slide, Inches(8.0), Inches(1.15), Inches(4.55), Inches(4.35),
                 "صورة الغلاف المقترحة: واجهة المراقبة أو لقطة من الفيديو الحي")
add_text(slide, Inches(0.6), Inches(5.25), Inches(11.8), Inches(0.55),
         "الرسالة الأساسية: إذا حدث شيء، النظام لا يكتفي بالرؤية، بل يفهم ويُنبّه ويؤرشف ويُوثّق.",
         size=16, color=GOLD, bold=True)
add_footer(slide)

# Slide 2: Problem
slide = prs.slides.add_slide(prs.slide_layouts[6])
set_bg(slide)
add_top_bar(slide, "Why It Matters", "The problem behind the project")
add_panel(slide, Inches(0.55), Inches(1.15), Inches(4.0), Inches(1.35), "المشكلة", "المراقبة البشرية تتعب، وتتأخر في ملاحظة الحوادث، خصوصًا عندما يكون عدد الشاشات كبيرًا أو الحدث سريعًا.")
add_panel(slide, Inches(0.55), Inches(2.7), Inches(4.0), Inches(1.35), "الخسارة", "تأخر التنبيه يعني وقتًا ضائعًا، ودليلًا أقل، واستجابة أضعف.")
add_panel(slide, Inches(0.55), Inches(4.25), Inches(4.0), Inches(1.35), "الفرصة", "الذكاء الاصطناعي يحول الكاميرا من جهاز تسجيل إلى جهاز فهم واستجابة.")
add_placeholder(slide, Inches(5.0), Inches(1.25), Inches(7.6), Inches(4.65),
                 "صورة مطلوبة: غرفة مراقبة أو كاميرا أمنية أو مشهد surveillance")
add_text(slide, Inches(5.2), Inches(5.95), Inches(7.1), Inches(0.45),
         "فكرة المشروع: ربط المشاهدة بالتنبيه بالأدلة بدل الاكتفاء بالتسجيل.", size=15, color=ACCENT, bold=True)
add_footer(slide)

# Slide 3: What the system does
slide = prs.slides.add_slide(prs.slide_layouts[6])
set_bg(slide)
add_top_bar(slide, "What AI Sentinel Does", "A compact pipeline with real-time behavior")
steps = [
    ("1", "Video Input", "كاميرا أو ملف فيديو"),
    ("2", "Frame Window", "نافذة 32 إطار"),
    ("3", "AI Analysis", "كشف العنف + الحركة + السلاح"),
    ("4", "Threat Fusion", "دمج الإشارات في درجة واحدة"),
    ("5", "Output", "Alert + Evidence + PDF report"),
]
x0 = 0.55
for i, (num, t, b) in enumerate(steps):
    x = Inches(x0 + i*2.45)
    panel = slide.shapes.add_shape(MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE, x, Inches(1.55), Inches(2.18), Inches(2.05))
    panel.fill.solid()
    panel.fill.fore_color.rgb = PANEL
    panel.line.color.rgb = ACCENT if i != 4 else GOLD
    panel.line.width = Pt(1.3)
    circ = slide.shapes.add_shape(MSO_AUTO_SHAPE_TYPE.OVAL, x + Inches(0.75), Inches(1.72), Inches(0.7), Inches(0.7))
    circ.fill.solid()
    circ.fill.fore_color.rgb = ACCENT if i != 4 else GOLD
    circ.line.color.rgb = circ.fill.fore_color.rgb
    add_text(slide, x + Inches(0.75), Inches(1.86), Inches(0.7), Inches(0.18), num, size=16, bold=True, color=BG, align=PP_ALIGN.CENTER)
    add_text(slide, x + Inches(0.16), Inches(2.58), Inches(1.86), Inches(0.28), t, size=13, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    add_text(slide, x + Inches(0.12), Inches(2.95), Inches(1.95), Inches(0.5), b, size=10.5, color=MUTED, align=PP_ALIGN.CENTER)
add_text(slide, Inches(0.75), Inches(4.45), Inches(12.0), Inches(0.9),
         "التميّز هنا ليس في الاكتشاف فقط، بل في تحويل الحدث إلى قرار: التنبيه، التوثيق، ثم التقرير.",
         size=20, color=GOLD, bold=True)
add_footer(slide)

# Slide 4: Architecture
slide = prs.slides.add_slide(prs.slide_layouts[6])
set_bg(slide)
add_top_bar(slide, "Project Design", "Architecture that can be explained in one minute")
add_bullets(slide, Inches(0.6), Inches(1.15), Inches(4.0), Inches(2.0), "فكرة المعمارية", [
    "مصدر الفيديو يدخل أولًا.",
    "الخادم الخلفي يعالج البث.",
    "محرك التحليل يستخرج الإشارة.",
    "الواجهة تعرض النتيجة فورًا."
])
add_placeholder(slide, Inches(5.0), Inches(1.15), Inches(7.7), Inches(4.45),
                 "صورة مطلوبة: مخطط Architecture أو screenshot من الواجهة مع أسهم تدفق البيانات")
add_text(slide, Inches(0.62), Inches(4.25), Inches(3.85), Inches(1.1),
         "نقطة العرض: اشرحوا أن النظام مقسّم لوحدات مستقلة، وهذا ما يجعله سهل التطوير والتوسع.",
         size=14, color=ACCENT, bold=True)
add_footer(slide)

# Slide 5: Development roadmap chart
slide = prs.slides.add_slide(prs.slide_layouts[6])
set_bg(slide)
add_top_bar(slide, "Development Map", "Project growth rate through the real build stages")
chart_data = CategoryChartData()
chart_data.categories = ["Phase 1", "Design", "Backend", "AI Analysis", "Evidence", "Demo Ready"]
chart_data.add_series("Completion %", (20, 38, 58, 74, 88, 100))
chart = slide.shapes.add_chart(XL_CHART_TYPE.LINE_MARKERS, Inches(0.7), Inches(1.2), Inches(8.0), Inches(4.6), chart_data).chart
chart.has_legend = False
chart.value_axis.maximum_scale = 100
chart.value_axis.minimum_scale = 0
chart.value_axis.major_unit = 20
chart.value_axis.has_major_gridlines = True
chart.category_axis.tick_labels.font.size = Pt(10)
chart.value_axis.tick_labels.font.size = Pt(10)
chart.chart_title.has_text_frame = False
plot = chart.plots[0]
series = plot.series[0]
series.format.line.color.rgb = ACCENT
series.format.line.width = Pt(2.5)
try:
    from pptx.enum.chart import XL_DATA_LABEL_POSITION
    series.has_data_labels = True
    labels = series.data_labels
    labels.position = XL_DATA_LABEL_POSITION.ABOVE
    labels.number_format = '0"%"'
except Exception:
    pass
add_panel(slide, Inches(9.0), Inches(1.3), Inches(3.6), Inches(1.2), "قراءة سريعة", "التطور ليس مجرد زيادة في الملفات، بل انتقال من الفكرة إلى المعمارية ثم التحليل ثم التوثيق.")
add_panel(slide, Inches(9.0), Inches(2.85), Inches(3.6), Inches(1.2), "معلومة قوية", "أكبر قفزة حدثت عندما تحوّل النظام من كشف فقط إلى كشف + دمج تهديد + دليل + تقرير.")
add_panel(slide, Inches(9.0), Inches(4.4), Inches(3.6), Inches(1.2), "تفسير الرسم", "كل مرحلة رفعت قدرة النظام التحليلية وليس فقط شكله الخارجي.")
add_footer(slide)

# Slide 6: Analytical patterns
slide = prs.slides.add_slide(prs.slide_layouts[6])
set_bg(slide)
add_top_bar(slide, "Analytical Growth", "How the software became smarter over time")
add_panel(slide, Inches(0.55), Inches(1.15), Inches(3.9), Inches(4.95), "النمط 1: الرؤية الخام", "في البداية كان النظام يتعامل مع الفيديو كمشهد واحد. بعدها صار يقرأ تسلسل إطارات بدل لقطة منفصلة.")
add_panel(slide, Inches(4.62), Inches(1.15), Inches(3.9), Inches(4.95), "النمط 2: الفهم الزمني", "نافذة 32 إطارًا جعلت التحليل يلتقط الحركة المتسلسلة، وليس فقط صورة ثابتة.")
add_panel(slide, Inches(8.69), Inches(1.15), Inches(3.9), Inches(4.95), "النمط 3: الدمج الذكي", "تمت إضافة Threat Fusion وWeapon Signal وEvidence Ledger، فصار القرار أقرب للتوثيق الأمني لا للتصنيف فقط.")
add_text(slide, Inches(0.75), Inches(5.95), Inches(12.0), Inches(0.45),
         "الجملة المثيرة: النظام لم يتعلم كيف يرى فقط، بل كيف يفرز الضجيج من الخطر.", size=18, color=GOLD, bold=True)
add_footer(slide)

# Slide 7: Demo placeholders
slide = prs.slides.add_slide(prs.slide_layouts[6])
set_bg(slide)
add_top_bar(slide, "Demo Flow", "Replace these placeholders with your real captures")
add_placeholder(slide, Inches(0.55), Inches(1.1), Inches(3.95), Inches(2.35), "لقطة شاشة للفيديو الحي", "صورة")
add_placeholder(slide, Inches(4.7), Inches(1.1), Inches(3.95), Inches(2.35), "لقطة التنبيه داخل Alert Feed", "صورة")
add_placeholder(slide, Inches(8.85), Inches(1.1), Inches(3.95), Inches(2.35), "لقطة التقرير PDF أو Evidence Clip", "صورة")
add_panel(slide, Inches(0.55), Inches(3.75), Inches(12.25), Inches(1.55), "سيناريو سريع", "1) نفتح الواجهة  2) نشغّل المصدر  3) يظهر التنبيه  4) نفتح الحادث  5) ننزّل التقرير والدليل")
add_text(slide, Inches(0.75), Inches(5.6), Inches(12.0), Inches(0.55),
         "إذا لم تدعم الكاميرا البث المباشر، نستخدم فيديو ثابت احتياطي مع شرح أن التكامل الحقيقي جاهز للكاميرات القياسية.", size=14, color=MUTED, bold=False)
add_footer(slide)

# Slide 8: Judges mapping
slide = prs.slides.add_slide(prs.slide_layouts[6])
set_bg(slide)
add_top_bar(slide, "What Judges Care About", "How we win the rubric, not just the demo")
headers = ["Design", "Development", "Demo", "Originality", "Relevance", "Q&A"]
values = [
    "Architecture + flow",
    "Real code + APIs",
    "Live video + alerts",
    "Fusion + evidence",
    "Problem solved clearly",
    "Firm answers",
]
for i, (h, v) in enumerate(zip(headers, values)):
    x = Inches(0.6 + (i % 3) * 4.1)
    y = Inches(1.3 + (i // 3) * 2.0)
    panel = slide.shapes.add_shape(MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE, x, y, Inches(3.55), Inches(1.5))
    panel.fill.solid()
    panel.fill.fore_color.rgb = PANEL
    panel.line.color.rgb = ACCENT if i not in (3, 5) else GOLD
    add_text(slide, x + Inches(0.15), y + Inches(0.1), Inches(3.2), Inches(0.25), h, size=15, bold=True, color=WHITE)
    add_text(slide, x + Inches(0.15), y + Inches(0.45), Inches(3.2), Inches(0.6), v, size=12, color=MUTED)
add_text(slide, Inches(0.75), Inches(5.95), Inches(11.8), Inches(0.4),
         "الهدف: نخلي اللجنة تشوف مشروعًا مفهومًا، عاملًا، ومقنعًا خلال دقائق قليلة.", size=16, color=ACCENT, bold=True)
add_footer(slide)

# Slide 9: Closing
slide = prs.slides.add_slide(prs.slide_layouts[6])
set_bg(slide)
add_top_bar(slide, "Closing Line", "A memorable ending")
add_text(slide, Inches(0.75), Inches(1.55), Inches(11.7), Inches(1.2),
         "نحن لا نراقب الحادث فقط، نحن نحوله إلى ذاكرة رقمية مفهومة، موثقة، وقابلة للاسترجاع.",
         size=26, color=WHITE, bold=True)
add_text(slide, Inches(0.78), Inches(2.95), Inches(11.2), Inches(0.8),
         "هذا هو الفرق بين نظام يرى، ونظام يفهم، ونظام يثبت ما حدث.", size=20, color=ACCENT, bold=True)
add_placeholder(slide, Inches(0.95), Inches(4.05), Inches(11.45), Inches(1.65),
                 "صورة ختامية مقترحة: لوحة التحكم أو مشهد Evidence/Report", "صورة")
add_text(slide, Inches(0.95), Inches(6.0), Inches(11.45), Inches(0.35),
         "Final message: AI Sentinel turns surveillance into accountable intelligence.", size=13, color=GOLD, bold=True, align=PP_ALIGN.CENTER)
add_footer(slide)

prs.save(str(OUT))
print(f"Saved to {OUT}")

