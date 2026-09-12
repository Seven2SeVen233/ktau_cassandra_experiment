"""检查 caption 段落 run 格式（用于新表格 caption 保持一致）。"""
import sys
from docx import Document

path = sys.argv[1]
doc = Document(path)
for p in doc.paragraphs:
    t = p.text.strip()
    if t.startswith("Table") or t.startswith("Fig."):
        rinfo = [(r.text[:40], r.font.name, r.font.size, r.font.bold, r.font.italic) for r in p.runs]
        align = p.alignment
        print(f"style={p.style.name} align={align}\n  {t[:70]!r}\n  runs={rinfo}")
