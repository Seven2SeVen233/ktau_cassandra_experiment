"""导出 docx 全文（含表格）为 txt，供阅读。"""
import docx

path = r"C:\Users\34333\OneDrive\Desktop\Kendall-tau\Kendall_Tau_Log_Reconciliation_ICSDC_prepare.docx"
d = docx.Document(path)
out = []

# 按 body 顺序输出段落与表格（python-docx 遍历 body 元素）
from docx.table import Table
from docx.text.paragraph import Paragraph

body = d.element.body
for child in body.iterchildren():
    if child.tag.endswith("}p"):
        p = Paragraph(child, d)
        t = p.text.strip()
        if t:
            st = p.style.name if p.style else ""
            out.append(f"[{st}] {t}")
    elif child.tag.endswith("}tbl"):
        tb = Table(child, d)
        for r in tb.rows:
            cells = [c.text.strip().replace("\n", " ") for c in r.cells]
            out.append(" | ".join(cells))
        out.append("---")

with open(r"C:\Users\34333\OneDrive\Desktop\Kendall-tau\ktau_cassandra_experiment\_paper_full.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(out))
print(f"导出行数: {len(out)}")
