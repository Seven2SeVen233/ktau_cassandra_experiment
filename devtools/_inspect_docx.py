"""分析论文 docx 结构：段落统计、字数估算、表格与图片数量。"""
import sys
from docx import Document

path = sys.argv[1]
doc = Document(path)

paras = doc.paragraphs
n_words = 0
heading1 = []
n_tables = len(doc.tables)
n_inline_shapes = len(doc.inline_shapes)

for p in paras:
    style = p.style.name if p.style else "?"
    txt = p.text.strip()
    if not txt:
        continue
    n_words += len(txt.split())
    if style == "Heading 1":
        heading1.append(txt)

# 每个表格行数
print(f"== {path}")
print(f"paragraphs: {len(paras)}, words(total, incl. tables): {n_words}")
print(f"tables: {n_tables}, inline_shapes: {n_inline_shapes}")
print(f"Heading 1: {heading1}")
for i, t in enumerate(doc.tables):
    rows = len(t.rows)
    cols = len(t.columns)
    # 首个单元格文字
    first = " | ".join(c.text.strip().replace("\n", " ")[:40] for c in t.rows[0].cells)
    print(f"  table{i}: {rows}x{cols} header='{first}'")
