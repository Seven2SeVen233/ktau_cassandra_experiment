"""导出 docx 段落级结构（带索引、样式、文本前80字符），用于精确定位插入点。"""
import sys
from docx import Document

path = sys.argv[1]
doc = Document(path)

# 找出 Table 在段落流中的位置：用 body 元素顺序
from docx.table import Table
from docx.text.paragraph import Paragraph

body = doc.element.body
idx = 0
for child in body.iterchildren():
    tag = child.tag.split("}")[-1]
    if tag == "p":
        p = Paragraph(child, doc)
        style = p.style.name if p.style else "?"
        txt = p.text.strip().replace("\n", " ")
        if txt or style.startswith("Heading"):
            print(f"[{idx:3d}] {style:<14} {txt[:90]}")
    elif tag == "tbl":
        t = Table(child, doc)
        print(f"[{idx:3d}] === TABLE {len(t.rows)}x{len(t.columns)} ===")
    elif tag == "sectPr":
        print(f"[{idx:3d}] === SECTPR ===")
    else:
        print(f"[{idx:3d}] === {tag} ===")
    idx += 1
