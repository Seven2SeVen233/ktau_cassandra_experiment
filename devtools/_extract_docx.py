"""提取 docx 结构：标题层级 + 段落文本 + 表格摘要。"""
import sys
import docx

path = r"C:\Users\34333\OneDrive\Desktop\Kendall-tau\Kendall_Tau_Log_Reconciliation_ICSDC_prepare.docx"
d = docx.Document(path)

print("=== 段落结构（标题+首句）===")
for i, p in enumerate(d.paragraphs):
    t = p.text.strip()
    if not t:
        continue
    st = p.style.name if p.style else ""
    is_head = st.lower().startswith("heading") or st.lower().startswith("title")
    if is_head:
        print(f"[{i}] <{st}> {t}")
    elif len(t) < 120 and (t[0].isdigit() or t.startswith(("Table", "Figure", "Fig.", "Algorithm"))):
        print(f"[{i}] <{st}> {t}")

print("\n=== 表格 ===")
for ti, tb in enumerate(d.tables):
    rows = len(tb.rows)
    cols = len(tb.columns)
    hdr = [c.text.strip()[:20] for c in tb.rows[0].cells]
    print(f"Table {ti}: {rows}x{cols} header={hdr}")
