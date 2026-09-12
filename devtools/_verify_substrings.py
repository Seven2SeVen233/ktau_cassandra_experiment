# -*- coding: utf-8 -*-
"""验证段尾追加的微调文本。"""
import sys
from docx import Document

path = sys.argv[1]
doc = Document(path)

SUBS = [
    "On real-trace scenarios (Section 7), where disagreements are milder",
    "The \u00a76.4 numbers characterize",
    "On the trace platform the conservative leader-log",
    "The implementation here additionally uses a bitset",
    "Section 7 and Appendix A partially close this gap",
    "Table 4 reports all dimensions",
    "Table 3 reports all dimensions",
]
for p in doc.paragraphs:
    t = p.text
    for s in SUBS:
        if s in t:
            print(f"[{p.style.name}] ...{t[max(0, t.index(s) - 60): t.index(s) + 120]}...")
            break
