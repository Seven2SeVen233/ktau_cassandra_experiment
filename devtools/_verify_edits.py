# -*- coding: utf-8 -*-
"""验证修改结果：dump 关键段落 + 正文/附录词数统计。"""
import sys
from docx import Document

path = sys.argv[1]
doc = Document(path)

KEY = [
    "The paper is organized",
    "Real-trace validation (Section 7)",
    "On real-trace scenarios (Section 7), where disagreements are milder",
    "The \u00a76.4 numbers characterize",
    "On the trace platform the conservative leader-log",
    "The implementation here additionally uses a bitset",
    "Section 7 and Appendix A partially close this gap",
    "Three directions stand out",
    "7. Validation on Real Traces",
    "7.1 Scenarios and Platform",
    "7.2 Results and Analysis",
    "7.3 Comparison with the Theoretical Model",
    "Table 4. Live monitoring",
    "Table 3. End-to-end reconciliation quality",
    "Appendix",
    "A.1 Platform and Implementation",
    "A.3 Raw Results",
    "A.4 Reproducibility",
    "[44]",
    "[45]",
]

for p in doc.paragraphs:
    t = p.text.strip()
    for k in KEY:
        if t.startswith(k):
            print(f"[{p.style.name}] {t[:160]}")
            break

# 词数统计：正文（References 标题前）vs 附录（Appendix 标题后）
body_words = 0
app_words = 0
mode = "body"
for p in doc.paragraphs:
    t = p.text.strip()
    if t.startswith("References"):
        mode = "refs"
        continue
    if t.startswith("Appendix"):
        mode = "app"
        continue
    if mode in ("body", "refs"):
        body_words += len(t.split())
    elif mode == "app":
        app_words += len(t.split())
# 表格文字
for tbl in doc.tables:
    pass
print(f"\nparagraph words -> body+refs: {body_words}, appendix: {app_words}")
