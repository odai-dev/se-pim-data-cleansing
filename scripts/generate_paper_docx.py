import os
import argparse
from pathlib import Path
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.section import WD_SECTION
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls

from build_ieee_docx import (
    OUTPUT_DOCX, BUILD_DIR, SINGLE_COL_WIDTH_DXA, WIDE_TABLE_WIDTH_DXA,
    add_h1, add_h2, add_body_p, add_formatted_body_p,
    add_display_equation, add_table_with_header, add_figure,
    add_bookmark, add_hyperlink, set_cell_margins, set_cell_borders, set_section_columns,
    add_column_break
)

parser = argparse.ArgumentParser(description="Generate the submitted IEEE Word manuscript")
parser.add_argument(
    "--output",
    type=Path,
    default=OUTPUT_DOCX,
    help="destination DOCX path (default: output/doc/se_pim_data_cleansing_paper.docx)",
)
parser.add_argument(
    "--assets-dir",
    type=Path,
    default=BUILD_DIR,
    help="directory containing image1.png through image6.png",
)
args = parser.parse_args()
output_docx = args.output.resolve()
assets_dir = args.assets_dir.resolve()
for figure_number in range(1, 7):
    figure = assets_dir / f"image{figure_number}.png"
    if not figure.is_file():
        parser.error(f"missing DOCX figure asset: {figure}")

doc = docx.Document()

# 1. Geometry Setup (A4)
sec0 = doc.sections[0]
sec0.page_width = Pt(595.30)
sec0.page_height = Pt(841.90)
sec0.top_margin = Pt(54)
sec0.bottom_margin = Pt(72)
sec0.left_margin = Pt(45.35)
sec0.right_margin = Pt(45.35)

# 2. Title Block (Single Column)
p_title = doc.add_paragraph()
p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
p_title.paragraph_format.space_before = Pt(0)
p_title.paragraph_format.space_after = Pt(6)
r_title = p_title.add_run("PIM-Cleanser: In-Memory Acceleration of Data-Intensive Confidential Data Sanitization")
r_title.font.name = 'Times New Roman'
r_title.font.size = Pt(22)
r_title.font.bold = True

# Authors
p_auth = doc.add_paragraph()
p_auth.alignment = WD_ALIGN_PARAGRAPH.CENTER
p_auth.paragraph_format.space_before = Pt(0)
p_auth.paragraph_format.space_after = Pt(2)

r_a1 = p_auth.add_run("Wafaa M. AL-Madhaji")
r_a1.font.name = 'Times New Roman'
r_a1.font.size = Pt(11)
r_sup1 = p_auth.add_run("1")
r_sup1.font.name = 'Times New Roman'
r_sup1.font.size = Pt(8)
r_sup1.font.superscript = True

r_comma1 = p_auth.add_run(", ")
r_comma1.font.name = 'Times New Roman'
r_comma1.font.size = Pt(11)

r_a2 = p_auth.add_run("Odai M. Gubran")
r_a2.font.name = 'Times New Roman'
r_a2.font.size = Pt(11)
add_hyperlink(p_auth, "", "(ORCID)", is_external=True, url="https://orcid.org/0009-0007-3220-906X")

r_sup2 = p_auth.add_run("2")
r_sup2.font.name = 'Times New Roman'
r_sup2.font.size = Pt(8)
r_sup2.font.superscript = True

r_comma2 = p_auth.add_run(", ")
r_comma2.font.name = 'Times New Roman'
r_comma2.font.size = Pt(11)

r_a3 = p_auth.add_run("Ibrahim Ahmed Al-Baltah")
r_a3.font.name = 'Times New Roman'
r_a3.font.size = Pt(11)
r_sup3 = p_auth.add_run("1")
r_sup3.font.name = 'Times New Roman'
r_sup3.font.size = Pt(8)
r_sup3.font.superscript = True

# Affiliations
p_aff = doc.add_paragraph()
p_aff.alignment = WD_ALIGN_PARAGRAPH.CENTER
p_aff.paragraph_format.space_before = Pt(0)
p_aff.paragraph_format.space_after = Pt(2)

r_aff1 = p_aff.add_run("1Faculty of Computer Science and IT, Sana'a University, Sana'a, Yemen\n")
r_aff1.font.name = 'Times New Roman'
r_aff1.font.size = Pt(10)

r_aff2 = p_aff.add_run("2Department of Information Technology, Ar-Rasheed Smart University, Sana'a, Yemen")
r_aff2.font.name = 'Times New Roman'
r_aff2.font.size = Pt(10)

# Corresponding Author
p_corr = doc.add_paragraph()
p_corr.alignment = WD_ALIGN_PARAGRAPH.CENTER
p_corr.paragraph_format.space_before = Pt(2)
p_corr.paragraph_format.space_after = Pt(8)
r_corr = p_corr.add_run("Corresponding author: Wafaa M. AL-Madhaji (wafaamoh2021@gmail.com)")
r_corr.font.name = 'Times New Roman'
r_corr.font.size = Pt(9)
r_corr.font.italic = True

# 3. Switch to Two-Column Section before Abstract
sec_body = doc.add_section(WD_SECTION.CONTINUOUS)
sec_body.page_width = Pt(595.30)
sec_body.page_height = Pt(841.90)
sec_body.top_margin = Pt(54)
sec_body.bottom_margin = Pt(72)
sec_body.left_margin = Pt(45.35)
sec_body.right_margin = Pt(45.35)
set_section_columns(sec_body, 2, 360)

# Abstract
p_abs = doc.add_paragraph()
p_abs.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
p_abs.paragraph_format.space_before = Pt(0)
p_abs.paragraph_format.space_after = Pt(6)
p_abs.paragraph_format.line_spacing = 1.15
p_abs.paragraph_format.first_line_indent = Pt(13.6)

r_abs_h = p_abs.add_run("Abstract—")
r_abs_h.font.name = 'Times New Roman'
r_abs_h.font.size = Pt(9)
r_abs_h.font.bold = True
r_abs_h.font.italic = True

r_abs_txt = p_abs.add_run(
    "Processing-In-Memory (PIM) architectures such as Secure Processing-in-Memory (SE-PIM) combine near-data execution "
    "with protected memory, but commonly assume that ingested data are already clean. Conventional sanitization conditionally "
    "writes records containing Not-a-Number values, missing-value sentinels, or outliers; the resulting addresses, transaction counts, "
    "and completion time can reveal confidential anomaly positions. We present PIM-Cleanser, an extension to SE-PIM that performs "
    "sanitization within the protected PIM path. Its fixed-schedule modes scan every public feature and unconditionally write every record "
    "or public block. We define the attacker-visible trace and test equality across corruption rates and seeds. Evaluation covers balanced "
    "and heavy-tailed synthetic mixtures, UCI Human Activity Recognition, k-means, and feature-wise aggregation using zero and per-feature "
    "mean imputation. The calibrated model, anchored by isolated native gem5 cleaning measurements, estimates 0.048495% incremental overhead "
    "for zero imputation and 0.117989% for mean imputation in the selected fixed-20-iteration k-means configuration. Across 1,008 equal-public-shape "
    "groups, every fixed-schedule candidate produces an identical modeled observable trace, while leakage controls expose the expected "
    "corruption-dependent behavior. Together, the results demonstrate practical data repair with fixed observable schedules and low "
    "estimated incremental cost under the stated bus-observation model."
)
r_abs_txt.font.name = 'Times New Roman'
r_abs_txt.font.size = Pt(9)

# Keywords
p_key = doc.add_paragraph()
p_key.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
p_key.paragraph_format.space_before = Pt(0)
p_key.paragraph_format.space_after = Pt(14)
p_key.paragraph_format.line_spacing = 1.15

r_key_h = p_key.add_run("Keywords—")
r_key_h.font.name = 'Times New Roman'
r_key_h.font.size = Pt(9)
r_key_h.font.bold = True
r_key_h.font.italic = True

r_key_txt = p_key.add_run("Processing-In-Memory (PIM), Confidential Computing, Trusted Execution Environment, Data Sanitization, Side-channel Attacks.")
r_key_txt.font.name = 'Times New Roman'
r_key_txt.font.size = Pt(9)

# SECTION I. INTRODUCTION
add_h1(doc, "I. INTRODUCTION")

add_formatted_body_p(doc, [
    ('text', 'Modern cloud computing architectures must simultaneously satisfy stringent data confidentiality requirements and high-throughput computational demands. The shift towards data-centric applications—such as large-scale data analytics and neural network training—has exacerbated the traditional Von Neumann bottleneck, often referred to as the "memory wall." To minimize data movement, architectures are increasingly utilizing Near-Data Processing or Processing-In-Memory (PIM) '),
    ('cite', [(1, 'ref-1')]),
    ('text', '. Concurrently, cloud tenants require strict isolation guarantees, relying on hardware-based Trusted Execution Environments (TEEs) or secure enclaves like Intel Software Guard Extensions (SGX) to protect sensitive information from unauthorized access.')
])

add_formatted_body_p(doc, [
    ('text', 'Recent research, prominently including the SE-PIM '),
    ('cite', [(2, 'ref-2')]),
    ('text', ' architecture, has successfully married these two paradigms. By embedding programmable processing cores within 3D-stacked memory banks and equipping them with attestation (hardware-backed proof of the trusted code and state) and memory encryption hardware, SE-PIM restricts the attack surface. It inherently mitigates address-based side-channel leaks on the system bus by performing computations locally inside the memory module.')
])

add_formatted_body_p(doc, [
    ('text', 'Despite these advancements, confidential computing literature frequently relies on the simplifying assumption of perfectly clean input data. In contrast, production data pipelines frequently ingest records containing missing values, duplicates, inconsistent encodings, schema drift, and statistical anomalies. Prior work on large-scale data quality verification reports that such errors can break ingestion pipelines, propagate unexpected errors to downstream consumers, and degrade machine-learning prediction quality '),
    ('cite', [(3, 'ref-3')]),
    ('text', '. Empirical studies further show that missing, inconsistent, and conflicting data measurably affect classification and clustering models '),
    ('cite', [(4, 'ref-4')]),
    ('text', ', while high-stakes AI deployments experience recurring "data cascades" in which data quality issues create delayed downstream failures '),
    ('cite', [(5, 'ref-5')]),
    ('text', '. Missingness itself may be sensitive: absent laboratory tests can reveal a patient\'s clinical pathway, while extreme or suppressed financial fields can identify fraud-investigation targets. These observations make data sanitization within ETL a required phase with its own confidentiality boundary.')
])

add_formatted_body_p(doc, [
    ('text', 'Integrating data sanitization into confidential computing architectures introduces novel side-channel vulnerabilities. Standard null or outlier checking logic depends on conditional branching (e.g., '),
    ('code', 'if (isnan(v)) { ... }'),
    ('text', '). If a host CPU executes this branch over encrypted memory, varying memory access latencies, control-flow behavior, or write-back patterns can expose the location and density of the dataset anomalies to an adversary observing the computation '),
    ('cite', [(6, 'ref-6'), (7, 'ref-7')]),
    ('text', '.')
])

add_body_p(doc, "To address this vulnerability, this paper presents PIM-Cleanser, an extension to the SE-PIM model that protects the data-cleansing layer under a stated bus-observation threat model. Our contributions are as follows:")

# Bulleted List
contribs = [
    "We identify a critical side-channel vulnerability in existing confidential PIM architectures caused by conventional host-side data cleansing heuristics.",
    "We define public and confidential inputs and an observable-trace equality property covering commands, DMA addresses and sizes, counts, polling, and completion.",
    "We implement six modes, including fixed-schedule PIM and hybrid cleaning, explicit leakage controls, and zero or per-feature mean imputation.",
    "We evaluate repair quality and calibrated performance across multiple datasets, corruption rates, seeds, shapes, and both k-means and aggregation workloads, while separating modeled estimates from native gem5 evidence."
]
for idx, item_text in enumerate(contribs, 1):
    p_num = doc.add_paragraph()
    p_num.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p_num.paragraph_format.space_before = Pt(0)
    p_num.paragraph_format.space_after = Pt(2)
    p_num.paragraph_format.line_spacing = 1.15
    p_num.paragraph_format.left_indent = Pt(18)
    p_num.paragraph_format.first_line_indent = Pt(-18)

    r_n = p_num.add_run(f"{idx})\t")
    r_n.font.name = 'Times New Roman'
    r_n.font.size = Pt(10)

    r_t = p_num.add_run(item_text)
    r_t.font.name = 'Times New Roman'
    r_t.font.size = Pt(10)

# SECTION II. BACKGROUND AND MOTIVATION
add_h1(doc, "II. BACKGROUND AND MOTIVATION")

add_h2(doc, "A. PROCESSING-IN-MEMORY AND SE-PIM")
add_body_p(doc, "Processing-In-Memory fundamentally restructures data workflows. Rather than transferring massive data blocks across the comparatively slow system bus to the CPU, PIM places programmable logic directly onto the memory die (such as the logic layer in High Bandwidth Memory (HBM) or UPMEM's commercial PIM architecture).")

add_formatted_body_p(doc, [
    ('text', 'The SE-PIM architecture '),
    ('cite', [(2, 'ref-2')]),
    ('text', ' extends this by turning a PIM module into a trusted extension of a CPU enclave. Through memory lockdown semantics (LOCK_MEM, a hardware command that blocks external access to the protected memory bank), SE-PIM ensures that while the PIM core computes over the sensitive data, the untrusted host operating system is physically blocked from mapping or altering the bank\'s contents.')
])

add_h2(doc, "B. THREAT MODEL")
add_body_p(doc, "We assume a passive adversary controlling the untrusted host and observing the host–PIM interface and external memory traffic, but not breaking SE-PIM's cryptography or measured code. Public input P contains allocation base and bytes, record and feature counts, mode, policy, threshold, public block size, cluster count, and fixed iteration count. Secret input S contains feature values and anomaly types, positions, and counts. The leakage function is the ordered attacker-visible trace (also called the observable transcript)")

# Equation (1)
add_display_equation(doc, r"\mathcal{L}(P,S)=\langle c_j,a_j,n_j,d_j,t_j,q,\Delta\rangle,", "(1)")

add_formatted_body_p(doc, [
    ('text', 'where c_j is an MMIO command; a_j, n_j, d_j, t_j are each externally visible address, size, direction, and issue time; q is the status-poll count; and Δ is cleaning completion. A fixed-schedule mode must satisfy '),
    ('math', r'\mathcal{L}(P,S_0)=\mathcal{L}(P,S_1)'),
    ('text', ' for any equal-public-shape inputs S_0, S_1. Power and electromagnetic leakage, analog DRAM effects, rollback, denial of service, physical attacks, compromised measured code, and microarchitectural observation inside the PIM core are out of scope. This is a fixed-observable-trace property for the evaluated cleaning command, not an ORAM or whole-system noninterference claim.')
])

add_h2(doc, "C. IMPACT OF DATA ANOMALIES ON CONFIDENTIAL COMPUTING")
add_formatted_body_p(doc, [
    ('text', 'Academic evaluations of systems like SE-PIM often utilize synthetic, pre-cleaned datasets. In practice, data ingests originating from sensors, external Application Programming Interfaces (APIs), logs, relational databases, and human-entered forms contain corruptions that must be detected before analysis. Production data-quality systems therefore include explicit checks for missing values, duplicate records, distributional anomalies, and unexpected value ranges '),
    ('cite', [(3, 'ref-3')]),
    ('text', '. More broadly, data preparation surveys identify discovery, cleaning, integration, transformation, and repair as core steps needed before analysis can safely proceed '),
    ('cite', [(8, 'ref-8')]),
    ('text', '. If such data is ingested into an enclave, it must be cleaned prior to processing (e.g., replacing NaNs with 0.0f to prevent math errors during a k-means reduction).')
])

add_body_p(doc, "The effect on clustering is direct. In Lloyd-style k-means (a centroid-based clustering algorithm), a centroid is updated as")

# Equation (2)
add_display_equation(doc, r"\mu_j = \frac{1}{|C_j|}\sum_{x_i \in C_j} x_i .", "(2)")

add_formatted_body_p(doc, [
    ('text', 'If a corrupted point assigned to cluster C_j contains an extreme value M in one feature, the corresponding centroid coordinate is shifted by approximately (M - x)/|C_j| relative to the clean point x. If the feature is NaN, IEEE 754 arithmetic can propagate the NaN through the reduction unless the implementation explicitly filters it. If missing values are encoded as a fixed sentinel or zero-filled without a validity check, the centroid is biased toward that replacement value in proportion to the missing-data rate. This is consistent with prior clustering work showing that k-means is highly sensitive to noise and outliers '),
    ('cite', [(9, 'ref-9'), (10, 'ref-10')]),
    ('text', ', and with empirical studies showing that dirty data changes clustering outcomes '),
    ('cite', [(4, 'ref-4')]),
    ('text', '.')
])

add_h2(doc, "D. SIDE-CHANNEL VULNERABILITIES IN DATA CLEANSING")
add_body_p(doc, "A standard CPU-based data cleaner operates iteratively:")

# Pseudo code block for CPU cleaner
tbl_cpu = doc.add_table(rows=5, cols=1)
tbl_cpu.alignment = WD_TABLE_ALIGNMENT.CENTER
tbl_cpu.autofit = False
tbl_cpuPr = tbl_cpu._tbl.tblPr
tbl_cpuPr.append(parse_xml(f'<w:tblW {nsdecls("w")} w:w="{SINGLE_COL_WIDTH_DXA}" w:type="dxa"/>'))
tbl_cpu._tbl.append(parse_xml(f'<w:tblGrid {nsdecls("w")}><w:gridCol w:w="{SINGLE_COL_WIDTH_DXA}"/></w:tblGrid>'))

for r_i, line_text in enumerate(["p <- read(memory)", "if isnan(p) then", "    p <- 0.0", "    write(p, memory)", "end if"]):
    cell = tbl_cpu.rows[r_i].cells[0]
    set_cell_margins(cell, top=20, bottom=20, left=100, right=100)
    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    r = p.add_run(line_text)
    r.font.name = 'Courier New'
    r.font.size = Pt(8)

p_sp = doc.add_paragraph()
p_sp.paragraph_format.space_after = Pt(4)

add_formatted_body_p(doc, [
    ('text', 'In a confidential framework like Intel SGX, the memory controller provides data encryption, but the addresses accessed and the timing between accesses remain visible on the physical bus. Prior work has shown that encrypted enclaves remain vulnerable to access-pattern and control-flow leakage '),
    ('cite', [(6, 'ref-6'), (11, 'ref-11'), (7, 'ref-7')]),
    ('text', '. Because the write operation above only triggers conditionally based on the content of the encrypted data, an attacker monitoring the bus can correlate memory locations with anomalous data points. In financial or medical datasets, anomalies and missingness may themselves encode sensitive events; healthcare studies, for example, show that missing-value handling can materially affect downstream models and decisions '),
    ('cite', [(12, 'ref-12')]),
    ('text', '. Thus, the mere pattern of anomalies can constitute a privacy leak.')
])

# SECTION III. RELATED WORK
add_h1(doc, "III. RELATED WORK")

add_formatted_body_p(doc, [
    ('bold', 'Side channels and oblivious analytics. '),
    ('text', 'Controlled-channel, cache, and branch-shadowing attacks show that encrypted enclave memory alone does not hide access behavior '),
    ('cite', [(6, 'ref-6'), (11, 'ref-11'), (7, 'ref-7')]),
    ('text', '. ORAM provides a stronger formal abstraction for hiding logical access patterns '),
    ('cite', [(13, 'ref-13')]),
    ('text', '; enclave systems such as ObliDB apply related techniques to database queries '),
    ('cite', [(14, 'ref-14')]),
    ('text', '. PIM-Cleanser complements these systems by targeting a cleaning-specific, fixed sequential repair trace. ')
])

add_formatted_body_p(doc, [
    ('bold', 'PIM systems and security. '),
    ('text', 'Studies of real UPMEM hardware expose tradeoffs among local compute, bandwidth, transfers, and programming model '),
    ('cite', [(15, 'ref-15')]),
    ('text', ', while PIM-security work emphasizes that near-memory execution introduces its own attack surface '),
    ('cite', [(16, 'ref-16')]),
    ('text', '. The closest architecture is SE-PIM '),
    ('cite', [(2, 'ref-2')]),
    ('text', '; we add an in-situ sanitization phase. ')
])

add_formatted_body_p(doc, [
    ('bold', 'Data quality. '),
    ('text', 'Dirty-data studies show changes in classification and clustering '),
    ('cite', [(4, 'ref-4')]),
    ('text', ', and robust k-means work motivates explicit handling of noise and outliers '),
    ('cite', [(9, 'ref-9'), (10, 'ref-10')]),
    ('text', '. Those works motivate repair but do not address leakage caused by the repair procedure itself.')
])

# SECTION IV. SYSTEM ARCHITECTURE: PIM-CLEANSER
add_h1(doc, "IV. SYSTEM ARCHITECTURE: PIM-CLEANSER")
add_body_p(doc, "Our proposed architecture integrates seamlessly into the baseline SE-PIM model. While the original model focused heavily on computational offloading, we introduce an explicit data sanitization phase that executes prior to the main computational kernel. Fig. 1 summarizes the resulting execution flow.")

# Figure 1
add_figure(doc, str(assets_dir / "image1.png"), "Fig. 1.", "PIM-Cleanser execution flow: host-visible operations are limited to orchestration, while data-dependent cleaning decisions execute inside the PIM module.")

add_h2(doc, "A. IN-MEMORY CLEANING LOGIC")
add_body_p(doc, "We deploy a specialized PIM kernel, pim_cleaner, directly alongside the primary workload (e.g., k-means). The cleaning kernel is designed to scan memory banks sequentially. It identifies three major categories of dirty data:")

# Bullets for cleaning logic
cat_items = [
    ("Non-finite values: ", "IEEE 754 NaNs and positive or negative infinities are invalid; both signed zeros remain valid."),
    ("Null sentinel: ", "The implemented missing-value marker is exactly -999999.0f, not an all-zero bit pattern."),
    ("Outliers: ", "Any finite value with magnitude strictly greater than the public threshold is invalid; equality at either boundary is valid.")
]
for title_b, desc_b in cat_items:
    p_b = doc.add_paragraph()
    p_b.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p_b.paragraph_format.space_before = Pt(0)
    p_b.paragraph_format.space_after = Pt(2)
    p_b.paragraph_format.line_spacing = 1.15
    p_b.paragraph_format.left_indent = Pt(14)
    p_b.paragraph_format.first_line_indent = Pt(-14)

    r_bullet = p_b.add_run("•\t")
    r_bullet.font.name = 'Times New Roman'
    r_bullet.font.size = Pt(10)

    r_tb = p_b.add_run(title_b)
    r_tb.font.name = 'Times New Roman'
    r_tb.font.size = Pt(10)
    r_tb.font.bold = True

    r_db = p_b.add_run(desc_b)
    r_db.font.name = 'Times New Roman'
    r_db.font.size = Pt(10)

add_body_p(doc, "Zero imputation is used only for normalized features. Mean imputation performs a fixed first pass to accumulate per-feature means from valid values and a fixed second pass to repair. Median and domain-aware policies remain future work. Algorithm 1 makes the externally important rule explicit: every record is written, even when no feature changes.")

# Algorithm 1 Table
add_column_break(doc)
p_alg_cap = doc.add_paragraph()
p_alg_cap.paragraph_format.space_before = Pt(6)
p_alg_cap.paragraph_format.space_after = Pt(2)
p_alg_cap.paragraph_format.keep_with_next = True
r_ac1 = p_alg_cap.add_run("Algorithm 1 ")
r_ac1.font.name = 'Times New Roman'
r_ac1.font.size = Pt(8)
r_ac1.font.bold = True
r_ac2 = p_alg_cap.add_run("PIM-Cleanser fixed-schedule sanitization kernel")
r_ac2.font.name = 'Times New Roman'
r_ac2.font.size = Pt(8)

alg_lines = [
    ("REQUIRE: ", "M: memory bank, public N,D,th, policy p"),
    ("ENSURE: ", "Sanitized memory bank M"),
    ("1: ", "μ[0..D-1] <- 0"),
    ("2: ", "if p = mean then"),
    ("3: ", "  for i = 0 to N-1 do"),
    ("4: ", "    for d = 0 to D-1 do"),
    ("5: ", "      masked-accumulate M[i,d] and validity into sum/count"),
    ("6: ", "    end for"),
    ("7: ", "  end for"),
    ("8: ", "  masked-divide each public feature sum by its count"),
    ("9: ", "end if"),
    ("10: ", "for i = 0 to N-1 do"),
    ("11: ", "  record <- M[i]"),
    ("12: ", "  for d = 0 to D-1 do"),
    ("13: ", "    valid <- finite, non-sentinel, and |record[d]| <= th"),
    ("14: ", "    record[d] <- select(valid, record[d], μ[d])"),
    ("15: ", "  end for"),
    ("16: ", "  unconditionally write M[i] <- record"),
    ("17: ", "end for")
]

tbl_alg = doc.add_table(rows=len(alg_lines), cols=1)
tbl_alg.alignment = WD_TABLE_ALIGNMENT.CENTER
tbl_alg.autofit = False
tbl_algPr = tbl_alg._tbl.tblPr
tbl_algPr.append(parse_xml(f'<w:tblW {nsdecls("w")} w:w="{SINGLE_COL_WIDTH_DXA}" w:type="dxa"/>'))
tbl_alg._tbl.append(parse_xml(f'<w:tblGrid {nsdecls("w")}><w:gridCol w:w="{SINGLE_COL_WIDTH_DXA}"/></w:tblGrid>'))

for idx, (l_head, l_body) in enumerate(alg_lines):
    cell = tbl_alg.rows[idx].cells[0]
    set_cell_margins(cell, top=15, bottom=15, left=60, right=60)

    top_b = {"val": "single", "sz": "8", "color": "000000"} if idx == 0 else None
    bot_b = {"val": "single", "sz": "4", "color": "000000"} if idx == 1 else ({"val": "single", "sz": "8", "color": "000000"} if idx == len(alg_lines)-1 else None)
    set_cell_borders(cell, top=top_b, bottom=bot_b)

    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)

    r1 = p.add_run(l_head)
    r1.font.name = 'Times New Roman'
    r1.font.size = Pt(8)
    r1.font.bold = (idx < 2)

    r2 = p.add_run(l_body)
    r2.font.name = 'Courier New' if idx >= 2 else 'Times New Roman'
    r2.font.size = Pt(7.5)

p_alg_sp = doc.add_paragraph()
p_alg_sp.paragraph_format.space_after = Pt(4)

add_body_p(doc, "The implementation uses mask/conditional-select repair and audits generated AArch64 assembly for feature-validity branches. More importantly for Eq. (1), validation never controls an external address, loop bound, transfer count, or final write.")

add_h2(doc, "B. FIXED OBSERVABLE SCHEDULE AND DRAM LOCKDOWN")
add_body_p(doc, "Before pim_cleaner begins, the enclave issues LOCK_MEM; in the evaluated SE-PIM model, unauthorized host accesses to the protected range are rejected until UNLOCK_MEM. The PIM command carries public shape, policy, and threshold but neither dirty indices nor a dirty count. The fixed PIM path scans public 128 KiB actions, decomposed into 64-byte PIM_ACCESS packets, and issues unconditional writes. These mechanisms enforce the observable-trace property in Eq. (1) for the defined bus-visible observer; the threat model states the remaining channel boundaries.")

add_h2(doc, "C. HYBRID CLEANING AND TRAFFIC SHAPING")
add_body_p(doc, "While full in-PIM cleaning is optimal, memory capacity constraints or complex ETL logic may require host-processor orchestration (Hybrid mode).")

add_body_p(doc, "When host-side intervention is necessary, pulling only dirty subsets across the bus exposes their locations. We therefore expose two distinct hybrid controls. hybrid-sparse transfers only blocks containing anomalies and is an intentionally leaky baseline. hybrid-oblivious scans every public block, pads the final block to its public size, and performs the same read and write schedule regardless of contents. Its action count is 2⌈B/b⌉ for public allocation bytes B and block bytes b. The oblivious candidate protects dirty-record positions under Eq. (1) while retaining the public sequential layout and block size. This matches the cleaning-specific observer defined in the threat model.")

add_h2(doc, "D. FIXED OBSERVABLE-SCHEDULE ARGUMENT")
add_body_p(doc, "The observable transcript in Eq. (1) is the ordered record of commands, addresses, transfer sizes and directions, issue times, status polls, and completion visible to the attacker. Table I separates deployment candidates from leakage controls. host-conditional and hybrid-sparse intentionally retain dirty-dependent writes or block selection. host-branchless removes secret-dependent feature-loop branches but also reads and writes every record; pim-oblivious and hybrid-oblivious enforce the same rule in the protected and block-oriented paths.")

# Table I
t1_headers = ["Mode", "Observable schedule", "Role"]
t1_data = [
    ["off", "no repair", "workload baseline"],
    ["host-conditional", "dirty-dependent writes", "leaky control"],
    ["host-branchless", "all records read/written", "fixed candidate"],
    ["pim-oblivious", "fixed PIM scan/write", "fixed candidate"],
    ["hybrid-sparse", "dirty-dependent blocks", "leaky control"],
    ["hybrid-oblivious", "all padded blocks", "fixed candidate"]
]
t1_widths = [1400, 2100, 1366]
add_table_with_header(doc, "TABLE I", "Implemented modes and their evidence role.", t1_headers, t1_data, t1_widths, [WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.LEFT])

add_body_p(doc, "For fixed public P, Algorithm 1 executes fixed loop bounds. Validity affects only a local conditional select, and every iteration issues the already scheduled write. Thus command arguments, addresses, sizes, directions, and counts are functions of P alone. Fixed command completion and equal checkpoint state make polling and Δ functions of P as well, giving Eq. (1). The argument is scoped to the stated model and is backed by artifact gates that audit AArch64 assembly, compare trace digests and completion across equal-shape corrupted inputs, and check every output byte against an independent reference. Publication evidence is emitted only after all gates pass.")

# SECTION V. EVALUATION
add_h1(doc, "V. EVALUATION")
add_formatted_body_p(doc, [
    ('text', 'To evaluate our proposed extension, we replicated the k-means clustering workload from the SE-PIM evaluation suite '),
    ('cite', [(2, 'ref-2')]),
    ('text', '. We extended the testing framework to support reproducible dataset corruption.')
])

add_h2(doc, "A. METHODOLOGY")
add_body_p(doc, "Evidence classes. Host-native execution measures functional quality, while a transparent gem5-calibrated model evaluates the full performance matrix. Isolated native gem5 cleaning ticks anchor the cleaning parameters. Every performance row is labeled functional_calibrated, keeping the evidence class explicit in both the CSVs and generated paper assets.")

add_formatted_body_p(doc, [
    ('text', 'Datasets and quality. We use balanced labeled Gaussian mixtures, skewed/heavy-tailed labeled mixtures, and UCI Human Activity Recognition (10,299 records, 561 normalized features, six labels) '),
    ('cite', [(17, 'ref-17')]),
    ('text', '. Quality runs cover corruption rates 0, 1, 5, 10, 20, and 40% and seeds 7, 19, 42, 73, and 101. NaNs, infinities, the implemented -999999.0f marker, and public-threshold outliers are injected at recorded positions. We report within-cluster sum of squares (WCSS), clean-reference WCSS ratio, centroid drift after optimal matching, normalized mutual information (NMI), remaining invalid values, and feature-aggregation error.')
])

# Table II
t2_headers = ["Dataset", "Records", "Features", "Labels", "Distribution"]
t2_data = [
    ["Balanced Gaussian", "131,072", "8", "6", "Gaussian"],
    ["Skewed/heavy-tailed", "131,072", "8", "6", "skewed/t-tail"],
    ["UCI HAR", "10,299", "561", "6", "normalized real"]
]
t2_widths = [1350, 850, 700, 650, 1316]
add_table_with_header(doc, "TABLE II", "Datasets used in the revised quality evaluation.", t2_headers, t2_data, t2_widths, [WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.RIGHT, WD_ALIGN_PARAGRAPH.RIGHT, WD_ALIGN_PARAGRAPH.RIGHT, WD_ALIGN_PARAGRAPH.LEFT])

add_body_p(doc, "Performance matrix. The calibrated matrix contains 18,144 individual rows spanning actual 4, 16, and 64 MiB allocations, corruption rates 1, 10, and 40%, three seeds, 4–64 features, 4–16 clusters, 1–128 KiB hybrid blocks, fixed-20-iteration k-means, and feature-wise aggregation. Every run records its command, commits, source-tree digest, dataset hashes, model kind, and individual result row.")

# Table III
t3_headers = ["Dimension", "Values"]
t3_data = [
    ["Actual size (MiB)", "4, 16, 64"],
    ["Corruption (%)", "1, 10, 40"],
    ["Seeds", "7, 19, 42"],
    ["Features", "4, 8, 32, 64"],
    ["Clusters", "4, 8, 16"],
    ["Hybrid block (KiB)", "1, 4, 16, 64, 128"],
    ["Workloads", "aggregation, fixed-20 k-means"],
    ["Repair", "zero, per-feature mean"]
]
t3_widths = [1866, 3000]
add_table_with_header(doc, "TABLE III", "Calibrated performance matrix.", t3_headers, t3_data, t3_widths, [WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.LEFT])

add_h2(doc, "B. REPAIR QUALITY AND PERFORMANCE")
add_body_p(doc, "All zero and mean policies repair every supported anomaly; clean input remains byte-identical and a second repair is idempotent. Table IV quantifies the downstream utility of the repaired data. At 10% UCI HAR corruption, mean imputation reduces aggregation error from 0.0671 to 0.0017 and centroid drift from 2.472 to 0.795 relative to zero repair, but NMI is slightly lower (0.546 versus 0.559). Policy selection must therefore follow the downstream objective rather than a universal cleanliness score.")

# Table IV
t4_headers = ["Policy", "WCSS ratio", "Drift", "NMI", "Agg. error"]
t4_data = [
    ["None", "--", "--", "0.001", "--"],
    ["Zero", "1.040", "2.472", "0.559", "0.0671"],
    ["Mean", "0.963", "0.795", "0.546", "0.0017"]
]
t4_widths = [1066, 950, 950, 950, 950]
add_table_with_header(doc, "TABLE IV", "UCI HAR quality at 10% corruption (five-seed means).", t4_headers, t4_data, t4_widths, [WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.RIGHT, WD_ALIGN_PARAGRAPH.RIGHT, WD_ALIGN_PARAGRAPH.RIGHT, WD_ALIGN_PARAGRAPH.RIGHT])

add_body_p(doc, "Table V extends the comparison across all three distributions. Mean repair has much lower aggregation error on all three datasets and lower drift on the skewed and UCI data. NMI, however, is tied on the balanced mixture and slightly favors zero repair on UCI HAR, reinforcing that imputation is application-specific.")

# Table V (WIDE TABLE: 1-Column Section)
p_pre_sec = doc.add_paragraph()
p_pre_sec.paragraph_format.space_before = Pt(0)
p_pre_sec.paragraph_format.space_after = Pt(0)

sec_wide = doc.add_section(WD_SECTION.CONTINUOUS)
sec_wide.page_width = Pt(595.30)
sec_wide.page_height = Pt(841.90)
sec_wide.top_margin = Pt(54)
sec_wide.bottom_margin = Pt(72)
sec_wide.left_margin = Pt(45.35)
sec_wide.right_margin = Pt(45.35)
set_section_columns(sec_wide, 1)

t5_headers = ["Dataset", "Policy", "WCSS ratio", "Drift", "NMI", "Agg. error"]
t5_data = [
    ["Balanced Gaussian", "Zero", "1.046", "0.193", "0.835", "0.0710"],
    ["Balanced Gaussian", "Mean", "1.041", "0.188", "0.835", "0.0070"],
    ["Skewed/heavy-tailed", "Zero", "0.962", "0.336", "0.593", "0.0703"],
    ["Skewed/heavy-tailed", "Mean", "0.944", "0.112", "0.611", "0.0008"],
    ["UCI HAR", "Zero", "1.040", "2.472", "0.559", "0.0671"],
    ["UCI HAR", "Mean", "0.963", "0.795", "0.546", "0.0017"]
]
t5_widths = [2400, 1400, 1573, 1573, 1573, 1573]
add_table_with_header(doc, "TABLE V", "Quality across datasets at 10% corruption (five-seed means).", t5_headers, t5_data, t5_widths, [WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.RIGHT, WD_ALIGN_PARAGRAPH.RIGHT, WD_ALIGN_PARAGRAPH.RIGHT, WD_ALIGN_PARAGRAPH.RIGHT], is_wide=True)

# Return to 2-Column Section
p_post_sec = doc.add_paragraph()
p_post_sec.paragraph_format.space_before = Pt(0)
p_post_sec.paragraph_format.space_after = Pt(0)

sec_body2 = doc.add_section(WD_SECTION.CONTINUOUS)
sec_body2.page_width = Pt(595.30)
sec_body2.page_height = Pt(841.90)
sec_body2.top_margin = Pt(54)
sec_body2.bottom_margin = Pt(72)
sec_body2.left_margin = Pt(45.35)
sec_body2.right_margin = Pt(45.35)
set_section_columns(sec_body2, 2, 360)

add_body_p(doc, "Fig. 2 presents the performance–quality policy tradeoff. The bars are calibrated incremental overhead for the selected 4 MiB fixed-20 k-means configuration; the line is host-native UCI HAR aggregation error at 10% corruption. They are reported on separate axes because they represent complementary evidence classes. Mean repair reduces aggregation error by 97.5% relative to zero repair while retaining sub-0.12% estimated incremental overhead.")

# Figure 2
add_figure(doc, str(assets_dir / "image2.png"), "Fig. 2.", "Performance–quality policy comparison: calibrated overhead and host-native UCI HAR aggregation error.")

add_body_p(doc, "For the selected 4 MiB, 32-feature, K=8, fixed-20 k-means configuration, the calibrated model estimates 0.048495% incremental overhead for PIM-oblivious zero imputation and 0.117989% for mean imputation. These estimates are parameterized using isolated native gem5 cleaning measurements; the resulting full-workload matrix explores how policy and public shape affect cost while preserving a traceable evidence boundary.")

add_body_p(doc, "Fig. 3 quantifies corruption-rate sensitivity. Mean repair removes every supported invalid value at every rate. WCSS ratio and NMI decline gradually as less original information remains, capturing the expected statistical limit of imputation rather than a repair failure.")

# Figure 3
add_figure(doc, str(assets_dir / "image3.png"), "Fig. 3.", "Mean-imputation quality sensitivity on UCI HAR across corruption rates.")

add_h2(doc, "C. HYBRID MODE SCALING")
add_body_p(doc, "Fig. 4 reports execution time and throughput for the selected 4 MiB, 32-feature, K=8, mean-imputation k-means case at 10% corruption, averaged over seeds 7, 19, and 42. Increasing the public block size from 1 to 128 KiB reduces calibrated runtime from 0.791 to 0.059 s and raises throughput from 5.29 to 158.51 MiB/s. Larger blocks therefore amortize controlled-access setup effectively while preserving the hybrid-oblivious schedule.")

# Figure 4
add_figure(doc, str(assets_dir / "image4.png"), "Fig. 4.", "Calibrated hybrid-oblivious runtime and throughput versus public block size.")

add_body_p(doc, "Fig. 5 explains the scaling result by separating the modeled cycle components. Controlled-access setup dominates small hybrid blocks, and larger blocks amortize that cost. The PIM-oblivious bar is almost entirely the fixed k-means workload, explaining its small calibrated incremental overhead.")

# Figure 5
add_figure(doc, str(assets_dir / "image5.png"), "Fig. 5.", "Timing-component breakdown for mean-imputation k-means. Hybrid labels denote public block size.")

add_body_p(doc, "Leakage is tested directly rather than inferred from mode names. Across all 1,008 equal-public-shape groups, fixed candidates have one modeled observable trace; host-conditional and hybrid-sparse controls vary as expected. As shown in Fig. 6, in a representative aggregation case, PIM-oblivious and hybrid-oblivious completion are constant across corruption, whereas the leaky controls' completion changes with dirty density. The trace includes transfers, bytes, padding, poll count, and completion, so sequential addresses alone are insufficient to pass.")

# Figure 6
add_figure(doc, str(assets_dir / "image6.png"), "Fig. 6.", "Empirical leakage control: fixed schedules remain horizontal while leaky controls expose dirty-density-dependent completion.")

# Table VI
t6_headers = ["Mode", "Rows", "Schedule result", "Evidence role"]
t6_data = [
    ["off", "1,296", "none", "baseline"],
    ["host-conditional", "1,296", "varies", "leaky control"],
    ["host-branchless", "1,296", "equal", "fixed candidate"],
    ["pim-oblivious", "1,296", "equal", "fixed candidate"],
    ["hybrid-sparse", "6,480", "varies", "leaky control"],
    ["hybrid-oblivious", "6,480", "equal", "fixed candidate"]
]
t6_widths = [1400, 800, 1300, 1366]
add_table_with_header(doc, "TABLE VI", "Calibrated observable-schedule outcome by mode.", t6_headers, t6_data, t6_widths, [WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.RIGHT, WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.LEFT])

# Table VII
t7_headers = ["Mode", "Overhead (%)"]
t7_data = [
    ["off", "0.0"],
    ["host-conditional", "9560.3"],
    ["host-branchless", "17435.6"],
    ["pim-oblivious", "0.117989"],
    ["hybrid-sparse", "190.2"],
    ["hybrid-oblivious", "192.4"]
]
t7_widths = [2400, 2466]
add_table_with_header(doc, "TABLE VII", "Calibrated overhead at 10% corruption (4 MiB, 32 features, K=8, mean repair, fixed-20 k-means; 16 KiB hybrid blocks).", t7_headers, t7_data, t7_widths, [WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.RIGHT])

add_body_p(doc, "The host-mode values quantify the cost of repeated controlled-access setup on small records. PIM batching removes those host transactions. Changing the device formula, burst size, cleaner parallelism, or downstream arithmetic rate requires recalibration and regeneration rather than reuse of these percentages.")

add_h2(doc, "D. SCOPE AND REPRODUCIBILITY")
add_body_p(doc, "The performance study targets the event-driven legacy SE-PIM ARM gem5 model. The full-workload values are calibrated estimates anchored by isolated native cleaning timing. The artifact also provides a separately gated direct native end-to-end path; its evidence is promoted only after its provenance, correctness, trace, timing, and regression checks pass. Absolute values depend on the modeled memory system, checkpoint, device constants, and assumed 16-core arithmetic throughput, so a different platform requires recalibration. Zero repair targets normalized features, while mean repair may alter correlations. Median and domain-aware imputation, categorical repair, duplicates, schema repair, and power/EM or internal PIM-core channels define useful extensions beyond the present study.")

add_body_p(doc, "Each run uses a unique identifier and records commands, commits, source digest, dataset hashes, seeds, timestamps, and model kind. The checksum-pinned UCI converter emits label sidecars and complete metadata. The release artifact contains canonical individual CSV rows, generated paper inputs, source, and a clean-extraction verifier. This separation lets every reported value be traced to its evidence class and regenerated from a clean extraction.")

# SECTION VI. CONCLUSION
add_h1(doc, "VI. CONCLUSION")
add_formatted_body_p(doc, [
    ('text', 'PIM-Cleanser addresses the clean-data assumption in confidential PIM by integrating sanitization directly into the protected SE-PIM execution path. Its fixed modes repair every supported anomaly through schedules determined solely by public shape. Across 1,008 equal-public-shape groups, these modes maintain identical modeled observable traces, while explicit leakage controls exhibit the expected dirty-density dependence. Host-native quality experiments demonstrate the utility and statistical tradeoffs of zero and mean repair across synthetic and real data. The gem5-calibrated model estimates only 0.048495% incremental overhead for zero repair and 0.117989% for mean repair in the selected k-means configuration. Together, these results establish fixed-schedule data repair under the evaluated observer with low estimated performance cost. Direct gem5 events '),
    ('cite', [(18, 'ref-18')]),
    ('text', ' confirm a fixed native cleaning transcript for the evaluated public shapes. The artifact\'s separation of evidence, negative controls, and reproducibility gates is as important as the mechanism it evaluates.')
])

# SECTION VII. LIMITATIONS
add_h1(doc, "VII. LIMITATIONS")
add_body_p(doc, "The native device is a gem5 event model evaluated with an older ARM full-system bundle, not real PIM silicon. Absolute timing depends on its DMA latencies, CPU model, memory configuration, and checkpoint. The large matrix is calibrated, and its arithmetic throughput is an assumption. We therefore avoid combining the two evidence types into a single measured speedup and make no direct native end-to-end overhead claim.")

add_body_p(doc, "Mean imputation preserves feature aggregates much better in our data, but can distort correlations and clusters and is not always appropriate. Zero repair is justified only for normalized features. Median, model-based, and domain-aware repair; categorical data; duplicate detection; and schema repair remain future work. The evaluated transcript also excludes PIM-core power, cache, and internal branch leakage. Formal noninterference in RTL and measurement on hardware are necessary before deployment claims.")

# DATA AVAILABILITY
add_h1(doc, "DATA AVAILABILITY")
add_formatted_body_p(doc, [
    ('text', 'The artifacts supporting this paper are released at '),
    ('url', ('GitHub: wafaa2026/se-pim-data-cleansing', 'https://github.com/wafaa2026/se-pim-data-cleansing')),
    ('text', '. The repository includes source code, dataset-generation and UCI conversion tools, canonical result rows, manifests, generated paper inputs, and a clean-extraction reproduction script.')
])

# REFERENCES
add_h1(doc, "REFERENCES")

ref_list = [
    (1, "ref-1", [('text', 'O. Mutlu '), ('italic', 'et al.'), ('text', ', "Processing data where it makes sense: Enabling in-memory computation," '), ('italic', 'Microprocessors and Microsystems'), ('text', ', vol. 67, pp. 28–41, 2019.')]),
    (2, "ref-2", [('text', 'K. D. Duy and H. Lee, "SE-PIM: In-Memory Acceleration of Data-Intensive Confidential Computing," '), ('italic', 'IEEE Transactions on Cloud Computing'), ('text', ', vol. 11, no. 3, pp. 2473–2487, July–Sept. 2023, doi: 10.1109/TCC.2022.3207145.')]),
    (3, "ref-3", [('text', 'S. Schelter, D. Lange, P. Schmidt, M. Celikel, F. Biessmann, and A. Grafberger, "Automating Large-Scale Data Quality Verification," '), ('italic', 'Proc. VLDB Endow.'), ('text', ', vol. 11, no. 12, pp. 1781–1794, 2018, doi: 10.14778/3229863.3229867.')]),
    (4, "ref-4", [('text', 'Z. Qi, H. Wang, and A.-J. Wang, "Impacts of Dirty Data on Classification and Clustering Models: An Experimental Evaluation," '), ('italic', 'Journal of Computer Science and Technology'), ('text', ', vol. 36, no. 4, pp. 806–821, 2021, doi: 10.1007/s11390-021-1344-6.')]),
    (5, "ref-5", [('text', 'N. Sambasivan, S. Kapania, H. Highfill, D. Akrong, P. K. Paritosh, and L. M. Aroyo, "Everyone Wants to Do the Model Work, Not the Data Work: Data Cascades in High-Stakes AI," in '), ('italic', 'Proc. CHI Conference on Human Factors in Computing Systems'), ('text', ', 2021, pp. 1–15, doi: 10.1145/3411764.3445518.')]),
    (6, "ref-6", [('text', 'Y. Xu, W. Cui, and M. Peinado, "Controlled-Channel Attacks: Deterministic Side Channels for Untrusted Operating Systems," in '), ('italic', 'Proc. IEEE Symp. Security and Privacy (S&P)'), ('text', ', San Jose, CA, May 2015.')]),
    (7, "ref-7", [('text', 'S. Lee, M.-W. Shih, P. Gera, T. Kim, H. Kim, and M. Peinado, "Inferring Fine-Grained Control Flow Inside SGX Enclaves with Branch Shadowing," in '), ('italic', 'Proc. USENIX Security Symposium'), ('text', ', 2017, pp. 557–574.')]),
    (8, "ref-8", [('text', 'A. A. A. Fernandes, M. Koehler, N. Konstantinou, P. Pankin, N. W. Paton, and R. Sakellariou, "Data Preparation: A Technological Perspective and Review," '), ('italic', 'SN Computer Science'), ('text', ', vol. 4, no. 4, 2023, doi: 10.1007/s42979-023-01828-8.')]),
    (9, "ref-9", [('text', 'S. Chawla and A. Gionis, "k-means--: A Unified Approach to Clustering and Outlier Detection," in '), ('italic', 'Proc. SIAM International Conference on Data Mining'), ('text', ', 2013, pp. 189–197, doi: 10.1137/1.9781611972832.21.')]),
    (10, "ref-10", [('text', 'S. Im, M. M. Qaem, B. Moseley, X. Sun, and R. Zhou, "Fast Noise Removal for k-Means Clustering," in '), ('italic', 'Proc. International Conference on Artificial Intelligence and Statistics'), ('text', ', PMLR, vol. 108, pp. 456–466, 2020.')]),
    (11, "ref-11", [('text', 'D. Gruss, C. Maurice, A. Fogh, M. Lipp, and S. Mangard, "Prefetch Side-Channel Attacks: Bypassing SMAP and Kernel ASLR," in '), ('italic', 'Proc. ACM SIGSAC Conference on Computer and Communications Security (CCS)'), ('text', ', Vienna, Austria, Oct. 2016, pp. 368–379, doi: 10.1145/2976749.2978356.')]),
    (12, "ref-12", [('text', 'Z. Chen, S. Tan, U. Chajewska, C. Rudin, and R. Caruna, "Missing Values and Imputation in Healthcare Data: Can Interpretable Machine Learning Help?" in '), ('italic', 'Proc. Conference on Health, Inference, and Learning'), ('text', ', PMLR, vol. 209, pp. 86–99, 2023.')]),
    (13, "ref-13", [('text', 'O. Goldreich and R. Ostrovsky, "Software Protection and Simulation on Oblivious RAMs," '), ('italic', 'Journal of the ACM'), ('text', ', vol. 43, no. 3, pp. 431–473, 1996.')]),
    (14, "ref-14", [('text', 'S. Eskandarian and M. Zaharia, "ObliDB: Oblivious query processing for secure databases," '), ('italic', 'Proc. VLDB Endowment'), ('text', ', vol. 13, no. 2, pp. 169–183, 2019, doi: 10.14778/3364324.3364331.')]),
    (15, "ref-15", [('text', 'J. Gómez-Luna, I. El Hajj, I. Fernandez, C. Giannoula, G. F. Oliveira, and O. Mutlu, "Benchmarking memory-centric computing systems: Analysis of real processing-in-memory hardware," '), ('italic', 'arXiv:2110.01709'), ('text', ', 2021.')]),
    (16, "ref-16", [('text', 'M. T. Arafin and Z. Lu, "Security challenges of processing-in-memory systems," in '), ('italic', 'Proc. ACM Great Lakes Symp. VLSI'), ('text', ', 2020, pp. 229–234, doi: 10.1145/3386263.3411365.')]),
    (17, "ref-17", [('text', 'D. Anguita, A. Ghio, L. Oneto, X. Parra, and J. L. Reyes-Ortiz, "A public domain dataset for human activity recognition using smartphones," in '), ('italic', 'Proc. ESANN'), ('text', ', 2013, pp. 437–442.')]),
    (18, "ref-18", [('text', 'J. Lowe-Power '), ('italic', 'et al.'), ('text', ', "The gem5 simulator: Version 20.0+," '), ('italic', 'arXiv:2007.03152'), ('text', ', 2020.')])
]

for ref_idx, bm_name, runs_info in ref_list:
    p_ref = doc.add_paragraph()
    p_ref.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p_ref.paragraph_format.space_before = Pt(0)
    p_ref.paragraph_format.space_after = Pt(2)
    p_ref.paragraph_format.line_spacing = Pt(9)
    p_ref.paragraph_format.left_indent = Pt(18)
    p_ref.paragraph_format.first_line_indent = Pt(-18)

    r_bm = p_ref.add_run(f"[{ref_idx}]\t")
    r_bm.font.name = 'Times New Roman'
    r_bm.font.size = Pt(8)
    add_bookmark(r_bm, bm_name, ref_idx + 100)

    for r_t, r_c in runs_info:
        r = p_ref.add_run(r_c)
        r.font.name = 'Times New Roman'
        r.font.size = Pt(8)
        if r_t == 'italic':
            r.font.italic = True
        elif r_t == 'bold':
            r.font.bold = True

output_docx.parent.mkdir(parents=True, exist_ok=True)
doc.save(output_docx)
print(f"Successfully generated {output_docx}")
