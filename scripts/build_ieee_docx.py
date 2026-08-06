import os
from pathlib import Path
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.section import WD_SECTION
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from lxml import etree
import latex2mathml.converter

REPO_ROOT = Path(__file__).resolve().parents[1]
BUILD_DIR = REPO_ROOT / "paper" / "docx_assets"
OUTPUT_DOCX = REPO_ROOT / "output" / "doc" / "se_pim_data_cleansing_paper.docx"

w_ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
m_ns = "http://schemas.openxmlformats.org/officeDocument/2006/math"
r_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
nsmap = {'w': w_ns, 'm': m_ns, 'r': r_ns}

SINGLE_COL_WIDTH_DXA = 4866  # 3.38 in = 243.3 pt
WIDE_TABLE_WIDTH_DXA = 10092  # 7.01 in = 504.6 pt

def set_section_columns(section, num_cols, space_dxa=360):
    sectPr = section._sectPr
    for c in sectPr.findall(qn('w:cols')):
        sectPr.remove(c)
    if num_cols == 1:
        cols = parse_xml(f'<w:cols {nsdecls("w")} w:num="1"/>')
    else:
        cols = parse_xml(f'<w:cols {nsdecls("w")} w:num="{num_cols}" w:space="{space_dxa}"/>')
    sectPr.append(cols)

def set_cell_margins(cell, top=40, bottom=40, left=60, right=60):
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = parse_xml(f'<w:tcMar {nsdecls("w")}><w:top w:w="{top}" w:type="dxa"/><w:bottom w:w="{bottom}" w:type="dxa"/><w:left w:w="{left}" w:type="dxa"/><w:right w:w="{right}" w:type="dxa"/></w:tcMar>')
    tcPr.append(tcMar)

def set_cell_borders(cell, top=None, bottom=None, left=None, right=None):
    tcPr = cell._tc.get_or_add_tcPr()
    tcBorders = parse_xml(f'<w:tcBorders {nsdecls("w")}/>')
    for b_name, b_val in [('top', top), ('bottom', bottom), ('left', left), ('right', right)]:
        if b_val:
            border = parse_xml(f'<w:{b_name} {nsdecls("w")} w:val="{b_val.get("val", "single")}" w:sz="{b_val.get("sz", "4")}" w:space="0" w:color="{b_val.get("color", "auto")}"/>')
            tcBorders.append(border)
        else:
            border = parse_xml(f'<w:{b_name} {nsdecls("w")} w:val="none"/>')
            tcBorders.append(border)
    tcPr.append(tcBorders)

def add_bookmark(run, bookmark_name, bookmark_id):
    p = run._r.getparent()
    bm_start = parse_xml(f'<w:bookmarkStart {nsdecls("w")} w:id="{bookmark_id}" w:name="{bookmark_name}"/>')
    bm_end = parse_xml(f'<w:bookmarkEnd {nsdecls("w")} w:id="{bookmark_id}"/>')
    p.insert(p.index(run._r), bm_start)
    p.insert(p.index(run._r) + 1, bm_end)

def add_hyperlink(paragraph, target_bookmark, text, is_external=False, url=None):
    if is_external:
        r_id = paragraph.part.relate_to(url, docx.opc.constants.RELATIONSHIP_TYPE.HYPERLINK, is_external=True)
        hyperlink = parse_xml(f'<w:hyperlink {nsdecls("w", "r")} r:id="{r_id}"/>')
    else:
        hyperlink = parse_xml(f'<w:hyperlink {nsdecls("w")} w:anchor="{target_bookmark}"/>')

    r = parse_xml(f'<w:r {nsdecls("w")}><w:rPr><w:rStyle w:val="Hyperlink"/><w:color w:val="0000FF"/><w:u w:val="single"/></w:rPr><w:t>{text}</w:t></w:r>')
    hyperlink.append(r)
    paragraph._p.append(hyperlink)

def convert_mathml_node_to_omml(node):
    tag = etree.QName(node).localname
    if tag in ['math', 'mrow']:
        container = etree.Element(f'{{{m_ns}}}oMath' if tag == 'math' else f'{{{m_ns}}}r', nsmap=nsmap) if tag == 'math' else []
        children = []
        for child in node:
            res = convert_mathml_node_to_omml(child)
            if isinstance(res, list):
                children.extend(res)
            elif res is not None:
                children.append(res)
        if tag == 'math':
            for c in children:
                container.append(c)
            return container
        else:
            return children
    elif tag in ['mi', 'mn', 'mo']:
        r = etree.Element(f'{{{m_ns}}}r', nsmap=nsmap)
        t = etree.SubElement(r, f'{{{m_ns}}}t', nsmap=nsmap)
        t.text = node.text or ''
        return r
    elif tag == 'msub':
        ssub = etree.Element(f'{{{m_ns}}}sSub', nsmap=nsmap)
        e = etree.SubElement(ssub, f'{{{m_ns}}}e', nsmap=nsmap)
        sub = etree.SubElement(ssub, f'{{{m_ns}}}sub', nsmap=nsmap)

        base_res = convert_mathml_node_to_omml(node[0])
        if isinstance(base_res, list):
            for item in base_res: e.append(item)
        elif base_res is not None:
            e.append(base_res)

        sub_res = convert_mathml_node_to_omml(node[1])
        if isinstance(sub_res, list):
            for item in sub_res: sub.append(item)
        elif sub_res is not None:
            sub.append(sub_res)
        return ssub
    elif tag == 'mfrac':
        frac = etree.Element(f'{{{m_ns}}}f', nsmap=nsmap)
        num = etree.SubElement(frac, f'{{{m_ns}}}num', nsmap=nsmap)
        den = etree.SubElement(frac, f'{{{m_ns}}}den', nsmap=nsmap)

        n_res = convert_mathml_node_to_omml(node[0])
        if isinstance(n_res, list):
            for item in n_res: num.append(item)
        elif n_res is not None:
            num.append(n_res)

        d_res = convert_mathml_node_to_omml(node[1])
        if isinstance(d_res, list):
            for item in d_res: den.append(item)
        elif d_res is not None:
            den.append(d_res)
        return frac
    return None

def latex_math_to_omml(latex_str):
    try:
        mml_str = latex2mathml.converter.convert(latex_str)
        mml_xml = etree.fromstring(mml_str.encode('utf-8'))
        return convert_mathml_node_to_omml(mml_xml)
    except Exception:
        omath = parse_xml(f'<m:oMath {nsdecls("m")}><m:r><m:t>{latex_str}</m:t></m:r></m:oMath>')
        return omath

def add_display_equation(doc, latex_str, eq_num_str):
    tbl = doc.add_table(rows=1, cols=3)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl.autofit = False

    tblPr = tbl._tbl.tblPr
    tblBorders = parse_xml(f'<w:tblBorders {nsdecls("w")}><w:top w:val="none"/><w:left w:val="none"/><w:bottom w:val="none"/><w:right w:val="none"/><w:insideH w:val="none"/><w:insideV w:val="none"/></w:tblBorders>')
    tblPr.append(tblBorders)
    tblPr.append(parse_xml(f'<w:tblW {nsdecls("w")} w:w="{SINGLE_COL_WIDTH_DXA}" w:type="dxa"/>'))

    col_widths_dxa = [600, 3666, 600]
    tblGrid = parse_xml(f'<w:tblGrid {nsdecls("w")}>' + "".join([f'<w:gridCol w:w="{w}"/>' for w in col_widths_dxa]) + '</w:tblGrid>')
    tbl._tbl.append(tblGrid)

    row = tbl.rows[0]
    for i, w in enumerate(col_widths_dxa):
        cell = row.cells[i]
        tcPr = cell._tc.get_or_add_tcPr()
        tcPr.append(parse_xml(f'<w:tcW {nsdecls("w")} w:w="{w}" w:type="dxa"/>'))

    cell_l, cell_c, cell_r = row.cells

    p_c = cell_c.paragraphs[0]
    p_c.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_c.paragraph_format.space_before = Pt(0)
    p_c.paragraph_format.space_after = Pt(0)
    omath_para = parse_xml(f'<m:oMathPara {nsdecls("m")}/>')
    omml_elem = latex_math_to_omml(latex_str)
    omath_para.append(omml_elem)
    p_c._p.append(omath_para)

    p_r = cell_r.paragraphs[0]
    p_r.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p_r.paragraph_format.space_before = Pt(0)
    p_r.paragraph_format.space_after = Pt(0)
    run = p_r.add_run(eq_num_str)
    run.font.name = 'Times New Roman'
    run.font.size = Pt(10)

    p_after = doc.add_paragraph()
    p_after.paragraph_format.space_before = Pt(0)
    p_after.paragraph_format.space_after = Pt(4)

def add_column_break(doc):
    p = doc.add_paragraph()
    run = p.add_run()
    run.add_break(WD_BREAK.COLUMN)

def add_h1(doc, text):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(12)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.keep_with_next = True
    run = p.add_run(text)
    run.font.name = 'Times New Roman'
    run.font.size = Pt(10)
    run.font.bold = True
    return p

def add_h2(doc, text):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.keep_with_next = True
    run = p.add_run(text)
    run.font.name = 'Times New Roman'
    run.font.size = Pt(10)
    run.font.italic = True
    return p

def add_body_p(doc, text="", space_after=0):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(space_after)
    p.paragraph_format.line_spacing = 1.15
    p.paragraph_format.first_line_indent = Pt(14.4)
    if text:
        run = p.add_run(text)
        run.font.name = 'Times New Roman'
        run.font.size = Pt(10)
    return p

def add_formatted_body_p(doc, runs_data, space_after=0):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(space_after)
    p.paragraph_format.line_spacing = 1.15
    p.paragraph_format.first_line_indent = Pt(14.4)

    for r_type, content in runs_data:
        if r_type == 'text':
            r = p.add_run(content)
            r.font.name = 'Times New Roman'
            r.font.size = Pt(10)
        elif r_type == 'bold':
            r = p.add_run(content)
            r.font.name = 'Times New Roman'
            r.font.size = Pt(10)
            r.font.bold = True
        elif r_type == 'italic':
            r = p.add_run(content)
            r.font.name = 'Times New Roman'
            r.font.size = Pt(10)
            r.font.italic = True
        elif r_type == 'bold_italic':
            r = p.add_run(content)
            r.font.name = 'Times New Roman'
            r.font.size = Pt(10)
            r.font.bold = True
            r.font.italic = True
        elif r_type == 'code':
            r = p.add_run(content)
            r.font.name = 'Courier New'
            r.font.size = Pt(9)
        elif r_type == 'cite':
            for i, (c_num, bm) in enumerate(content):
                if i > 0:
                    r_comma = p.add_run(", ")
                    r_comma.font.name = 'Times New Roman'
                    r_comma.font.size = Pt(10)
                r_bracket1 = p.add_run("[")
                r_bracket1.font.name = 'Times New Roman'
                r_bracket1.font.size = Pt(10)
                add_hyperlink(p, bm, str(c_num))
                r_bracket2 = p.add_run("]")
                r_bracket2.font.name = 'Times New Roman'
                r_bracket2.font.size = Pt(10)
        elif r_type == 'url':
            add_hyperlink(p, "", content[0], is_external=True, url=content[1])
        elif r_type == 'math':
            omml = latex_math_to_omml(content)
            p._p.append(omml)
    return p

def add_table_with_header(doc, number_str, title_str, headers, rows_data, col_widths_dxa, col_alignments=None, is_wide=False):
    total_table_width = WIDE_TABLE_WIDTH_DXA if is_wide else SINGLE_COL_WIDTH_DXA

    # Caption above table
    p_num = doc.add_paragraph()
    p_num.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_num.paragraph_format.space_before = Pt(6)
    p_num.paragraph_format.space_after = Pt(1)
    p_num.paragraph_format.keep_with_next = True
    r_num = p_num.add_run(number_str)
    r_num.font.name = 'Times New Roman'
    r_num.font.size = Pt(8)
    r_num.font.bold = True

    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_title.paragraph_format.space_before = Pt(0)
    p_title.paragraph_format.space_after = Pt(4)
    p_title.paragraph_format.keep_with_next = True
    r_title = p_title.add_run(title_str.upper())
    r_title.font.name = 'Times New Roman'
    r_title.font.size = Pt(8)

    tbl = doc.add_table(rows=len(rows_data)+1, cols=len(headers))
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl.autofit = False

    tblPr = tbl._tbl.tblPr
    tblBorders = parse_xml(f'<w:tblBorders {nsdecls("w")}><w:top w:val="single" w:sz="8" w:space="0" w:color="000000"/><w:bottom w:val="single" w:sz="8" w:space="0" w:color="000000"/><w:left w:val="none"/><w:right w:val="none"/><w:insideH w:val="none"/><w:insideV w:val="none"/></w:tblBorders>')
    tblPr.append(tblBorders)
    tblPr.append(parse_xml(f'<w:tblW {nsdecls("w")} w:w="{total_table_width}" w:type="dxa"/>'))

    # Add explicit column grid
    tblGrid = parse_xml(f'<w:tblGrid {nsdecls("w")}>' + "".join([f'<w:gridCol w:w="{w}"/>' for w in col_widths_dxa]) + '</w:tblGrid>')
    tbl._tbl.append(tblGrid)

    # Header row
    hdr_row = tbl.rows[0]
    hdr_trPr = hdr_row._tr.get_or_add_trPr()
    hdr_trPr.append(parse_xml(f'<w:tblHeader {nsdecls("w")}/>'))
    hdr_trPr.append(parse_xml(f'<w:cantSplit {nsdecls("w")}/>'))

    for c_idx, h_text in enumerate(headers):
        cell = hdr_row.cells[c_idx]
        w = col_widths_dxa[c_idx]
        tcPr = cell._tc.get_or_add_tcPr()
        tcPr.append(parse_xml(f'<w:tcW {nsdecls("w")} w:w="{w}" w:type="dxa"/>'))
        set_cell_margins(cell, top=40, bottom=40, left=50, right=50)
        set_cell_borders(cell, bottom={"val": "single", "sz": "4", "color": "000000"})
        p = cell.paragraphs[0]
        align = col_alignments[c_idx] if col_alignments else WD_ALIGN_PARAGRAPH.CENTER
        p.alignment = align
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        r = p.add_run(h_text)
        r.font.name = 'Times New Roman'
        r.font.size = Pt(8)
        r.font.bold = True

    for r_idx, r_data in enumerate(rows_data):
        row = tbl.rows[r_idx+1]
        trPr = row._tr.get_or_add_trPr()
        trPr.append(parse_xml(f'<w:cantSplit {nsdecls("w")}/>'))

        for c_idx, val in enumerate(r_data):
            cell = row.cells[c_idx]
            w = col_widths_dxa[c_idx]
            tcPr = cell._tc.get_or_add_tcPr()
            tcPr.append(parse_xml(f'<w:tcW {nsdecls("w")} w:w="{w}" w:type="dxa"/>'))
            set_cell_margins(cell, top=30, bottom=30, left=50, right=50)
            p = cell.paragraphs[0]
            align = col_alignments[c_idx] if col_alignments else WD_ALIGN_PARAGRAPH.LEFT
            p.alignment = align
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(0)
            r = p.add_run(str(val))
            r.font.name = 'Times New Roman'
            r.font.size = Pt(8)

    p_space = doc.add_paragraph()
    p_space.paragraph_format.space_before = Pt(0)
    p_space.paragraph_format.space_after = Pt(4)

def add_figure(doc, img_path, fig_num_str, caption_str, width_inches=3.38):
    p_img = doc.add_paragraph()
    p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_img.paragraph_format.space_before = Pt(6)
    p_img.paragraph_format.space_after = Pt(3)
    p_img.paragraph_format.keep_with_next = True

    run_img = p_img.add_run()
    run_img.add_picture(img_path, width=Inches(width_inches))

    p_cap = doc.add_paragraph()
    p_cap.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p_cap.paragraph_format.space_before = Pt(0)
    p_cap.paragraph_format.space_after = Pt(8)
    p_cap.paragraph_format.line_spacing = 1.15

    r_fig = p_cap.add_run(fig_num_str + " ")
    r_fig.font.name = 'Times New Roman'
    r_fig.font.size = Pt(8)
    r_fig.font.bold = True

    r_cap = p_cap.add_run(caption_str)
    r_cap.font.name = 'Times New Roman'
    r_cap.font.size = Pt(8)
