"""
Word 报告生成器 - 严格按照用户上传的报告模板格式
字体：Microsoft YaHei，正文12pt，标题深蓝色加粗
"""
import io
from docx import Document
from docx.shared import Inches, Pt, Cm, RGBColor, Emu
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml.ns import qn, nsdecls
from docx.oxml import parse_xml


def generate_word(report: dict) -> bytes:
    doc = Document()

    # 设置默认字体
    style = doc.styles['Normal']
    font = style.font
    font.name = 'Microsoft YaHei'
    font.size = Pt(12)
    style.element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')

    # 设置页面边距
    for section in doc.sections:
        section.top_margin = Cm(2.54)
        section.bottom_margin = Cm(2.54)
        section.left_margin = Cm(2.54)
        section.right_margin = Cm(2.54)

    # 颜色常量
    DARK_BLUE = RGBColor(0x17, 0x36, 0x5D)
    ACCENT_BLUE = RGBColor(0x36, 0x5F, 0x91)
    LIGHT_BLUE = RGBColor(0x4F, 0x81, 0xBD)
    HEADER_BG = RGBColor(0x36, 0x5F, 0x91)
    WHITE = RGBColor(0xFF, 0xFF, 0xFF)
    LIGHT_GRAY = RGBColor(0xF2, 0xF2, 0xF2)

    meta = report.get("meta", {})

    # ===== 标题 =====
    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run(f"{meta.get('site_name', '')} AEO / GEO 优化分析报告")
    run.font.size = Pt(26)
    run.font.color.rgb = DARK_BLUE
    run.bold = True
    run.font.name = 'Microsoft YaHei'
    run._element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')
    # 底部边框
    pPr = title._element.get_or_add_pPr()
    pBdr = parse_xml(f'<w:pBdr {nsdecls("w")}><w:bottom w:val="single" w:sz="8" w:space="4" w:color="4F81BD"/></w:pBdr>')
    pPr.append(pBdr)

    # 副标题
    subtitle = doc.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = subtitle.add_run('基于"AI 是否会把它当成合理答案"的优化建议方案')
    run.font.size = Pt(14)
    run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
    run.font.name = 'Microsoft YaHei'
    run._element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')

    # 分析对象
    info = doc.add_paragraph()
    info.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = info.add_run(f"分析对象：{meta.get('url', '')}")
    run.font.size = Pt(10)
    run.font.color.rgb = RGBColor(0x99, 0x99, 0x99)
    run.font.name = 'Microsoft YaHei'
    run._element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')

    # 评分
    score_p = doc.add_paragraph()
    score_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = score_p.add_run(f"初步 AEO 评分 {meta.get('total_score', 0)} / 100")
    run.font.size = Pt(16)
    run.font.color.rgb = DARK_BLUE
    run.bold = True
    run.font.name = 'Microsoft YaHei'
    run._element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')

    doc.add_paragraph()  # 空行

    # ===== 第一部分：总览 =====
    _add_h1(doc, "一、AEO 健康度评分总览")

    overview = report.get("part1_overview", {})
    p = doc.add_paragraph()
    run = p.add_run(f"网站 AEO 综合评分：{overview.get('total_score', 0)}/100（{overview.get('grade', 'N/A')} 级）")
    run.font.size = Pt(12)
    run.font.name = 'Microsoft YaHei'
    run._element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')

    p = doc.add_paragraph()
    run = p.add_run(overview.get("summary", ""))
    run.font.size = Pt(11)
    run.font.name = 'Microsoft YaHei'
    run._element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')

    # 评分表格
    dimensions = overview.get("dimensions", [])
    if dimensions:
        doc.add_paragraph()
        table = doc.add_table(rows=len(dimensions) + 1, cols=4)
        table.style = 'Table Grid'
        table.alignment = WD_TABLE_ALIGNMENT.CENTER

        # 表头
        headers = ["维度", "权重", "评分", "关键发现"]
        for i, h in enumerate(headers):
            cell = table.rows[0].cells[i]
            cell.text = ""
            p = cell.paragraphs[0]
            run = p.add_run(h)
            run.bold = True
            run.font.size = Pt(10)
            run.font.color.rgb = WHITE
            run.font.name = 'Microsoft YaHei'
            run._element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            shading = parse_xml(f'<w:shd {nsdecls("w")} w:fill="365F91" w:val="clear"/>')
            cell._element.get_or_add_tcPr().append(shading)

        for r, dim in enumerate(dimensions):
            data = [dim.get("name", ""), f"{dim.get('weight', 0)}%", f"{dim.get('score', 0)}/100", dim.get("key_finding", "")]
            for c, val in enumerate(data):
                cell = table.rows[r + 1].cells[c]
                cell.text = ""
                p = cell.paragraphs[0]
                run = p.add_run(str(val))
                run.font.size = Pt(9)
                run.font.name = 'Microsoft YaHei'
                run._element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')
                if r % 2 == 0:
                    shading = parse_xml(f'<w:shd {nsdecls("w")} w:fill="F2F2F2" w:val="clear"/>')
                    cell._element.get_or_add_tcPr().append(shading)

    # ===== 第二部分：AEO 优势 =====
    _add_h1(doc, "二、网站当前 AEO 优势")

    advantages = report.get("part2_advantages", {})
    for item in advantages.get("items", []):
        p = doc.add_paragraph()
        run = p.add_run(f"• {item}")
        run.font.size = Pt(11)
        run.font.name = 'Microsoft YaHei'
        run._element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')
        p.paragraph_format.left_indent = Cm(0.5)

    # ===== 第三部分：AEO 问题 =====
    _add_h1(doc, "三、当前最大 AEO 问题")

    problems = report.get("part3_problems", {})
    for prob in problems.get("problems", []):
        _add_h2(doc, prob.get("title", ""))
        p = doc.add_paragraph()
        run = p.add_run(prob.get("detail", ""))
        run.font.size = Pt(11)
        run.font.name = 'Microsoft YaHei'
        run._element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')

    # ===== 第四部分：Persona × Funnel × Use Case =====
    _add_h1(doc, "四、Persona × Funnel × Use Case 内容机会")

    opportunities = report.get("part4_content_opportunities", {})
    p = doc.add_paragraph()
    run = p.add_run(opportunities.get("description", ""))
    run.font.size = Pt(11)
    run.font.name = 'Microsoft YaHei'
    run._element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')

    scenarios = opportunities.get("scenarios", [])
    if scenarios:
        doc.add_paragraph()
        table = doc.add_table(rows=len(scenarios) + 1, cols=5)
        table.style = 'Table Grid'
        table.alignment = WD_TABLE_ALIGNMENT.CENTER

        headers = ["Persona", "Funnel", "Use Case", "AI 可能遇到的问题", "建议页面"]
        for i, h in enumerate(headers):
            cell = table.rows[0].cells[i]
            cell.text = ""
            p = cell.paragraphs[0]
            run = p.add_run(h)
            run.bold = True
            run.font.size = Pt(9)
            run.font.color.rgb = WHITE
            run.font.name = 'Microsoft YaHei'
            run._element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            shading = parse_xml(f'<w:shd {nsdecls("w")} w:fill="365F91" w:val="clear"/>')
            cell._element.get_or_add_tcPr().append(shading)

        for r, sc in enumerate(scenarios):
            data = [sc.get("persona", ""), sc.get("funnel", ""), sc.get("use_case", ""), sc.get("ai_question", ""), sc.get("page", "")]
            for c, val in enumerate(data):
                cell = table.rows[r + 1].cells[c]
                cell.text = ""
                p = cell.paragraphs[0]
                run = p.add_run(str(val))
                run.font.size = Pt(8)
                run.font.name = 'Microsoft YaHei'
                run._element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')

    # ===== 第五部分：优先页面 =====
    _add_h1(doc, "五、最值得优先做的 20 个 AEO 页面")

    priority = report.get("part5_priority_pages", {})
    for group in priority.get("groups", []):
        _add_h2(doc, group.get("name", ""))
        for i, page in enumerate(group.get("pages", []), 1):
            p = doc.add_paragraph()
            run = p.add_run(f"{i}. {page}")
            run.font.size = Pt(11)
            run.font.name = 'Microsoft YaHei'
            run._element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')
            p.paragraph_format.left_indent = Cm(0.5)

    top5 = priority.get("top5", [])
    if top5:
        p = doc.add_paragraph()
        run = p.add_run(f"优先级最高的 5 篇：{'、'.join(top5[:5])}。")
        run.bold = True
        run.font.size = Pt(11)
        run.font.name = 'Microsoft YaHei'
        run._element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')

    # ===== 第六部分：页面模板 =====
    _add_h1(doc, "六、页面重构模板")

    template = report.get("part6_page_template", {})
    example = template.get("example", {})

    p = doc.add_paragraph()
    run = p.add_run(f"示例页面：{example.get('page_title', '')}")
    run.bold = True
    run.font.size = Pt(12)
    run.font.name = 'Microsoft YaHei'
    run._element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')

    for item in example.get("structure", []):
        if item["level"] == "H1":
            _add_h2(doc, item["content"])
        elif item["level"] == "H2":
            p = doc.add_paragraph()
            run = p.add_run(f"• {item['content']}")
            run.font.size = Pt(11)
            run.font.name = 'Microsoft YaHei'
            run._element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')
            p.paragraph_format.left_indent = Cm(0.5)
        elif item["level"] == "对比表":
            p = doc.add_paragraph()
            run = p.add_run(f"📊 {item['content']}")
            run.font.size = Pt(11)
            run.italic = True
            run.font.name = 'Microsoft YaHei'
            run._element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')
        else:
            p = doc.add_paragraph()
            run = p.add_run(item["content"])
            run.font.size = Pt(11)
            run.font.name = 'Microsoft YaHei'
            run._element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')

    # GEO 模板
    _add_h2(doc, "GEO/AEO 内容模板")
    p = doc.add_paragraph()
    run = p.add_run(example.get("geo_template", ""))
    run.font.size = Pt(11)
    run.font.name = 'Microsoft YaHei'
    run._element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')

    # ===== 第七部分：技术建议 =====
    _add_h1(doc, "七、技术与抓取层面建议")

    tech = report.get("part7_technical_suggestions", {})
    for item in tech.get("items", []):
        p = doc.add_paragraph()
        run = p.add_run(f"• {item}")
        run.font.size = Pt(11)
        run.font.name = 'Microsoft YaHei'
        run._element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')
        p.paragraph_format.left_indent = Cm(0.5)

    # ===== 第八部分：效果衡量 =====
    _add_h1(doc, "八、AEO 效果衡量方式")

    measurement = report.get("part8_measurement", {})
    p = doc.add_paragraph()
    run = p.add_run(measurement.get("description", ""))
    run.font.size = Pt(11)
    run.font.name = 'Microsoft YaHei'
    run._element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')

    for dim in measurement.get("dimensions", []):
        _add_h2(doc, dim.get("name", ""))
        p = doc.add_paragraph()
        run = p.add_run(dim.get("description", ""))
        run.font.size = Pt(11)
        run.font.name = 'Microsoft YaHei'
        run._element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')
        for prompt in dim.get("prompts", []):
            p = doc.add_paragraph()
            run = p.add_run(f"  • {prompt}")
            run.font.size = Pt(10)
            run.font.name = 'Microsoft YaHei'
            run._element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')

    # ===== 第九部分：最终判断 =====
    _add_h1(doc, "九、最终判断")

    conclusion = report.get("part9_conclusion", {})
    p = doc.add_paragraph()
    run = p.add_run(conclusion.get("overview", ""))
    run.font.size = Pt(12)
    run.bold = True
    run.font.name = 'Microsoft YaHei'
    run._element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')

    p = doc.add_paragraph()
    run = p.add_run(conclusion.get("action", ""))
    run.font.size = Pt(11)
    run.font.name = 'Microsoft YaHei'
    run._element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')

    p = doc.add_paragraph()
    run = p.add_run(conclusion.get("summary", ""))
    run.font.size = Pt(11)
    run.font.name = 'Microsoft YaHei'
    run._element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')

    # 保存
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _add_h1(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(18)
    p.paragraph_format.space_after = Pt(6)
    run = p.add_run(text)
    run.font.size = Pt(14)
    run.font.color.rgb = RGBColor(0x36, 0x5F, 0x91)
    run.bold = True
    run.font.name = 'Microsoft YaHei'
    run._element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')


def _add_h2(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(12)
    p.paragraph_format.space_after = Pt(4)
    run = p.add_run(text)
    run.font.size = Pt(13)
    run.font.color.rgb = RGBColor(0x4F, 0x81, 0xBD)
    run.bold = True
    run.font.name = 'Microsoft YaHei'
    run._element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')
