# -*- coding: utf-8 -*-
"""精确分区词数统计 + 关键位置定位。"""
import sys
from docx import Document

path = sys.argv[1]
doc = Document(path)

sec = []
mode = "body"
for p in doc.paragraphs:
    t = p.text.strip()
    if t.startswith("References"):
        mode = "refs"
        sec.append((mode, len(t.split()), t[:40]))
        continue
    if t.startswith("Appendix"):
        mode = "app"
        sec.append((mode, len(t.split()), t[:40]))
        continue
    sec.append((mode, len(t.split()), t[:40]))

from collections import Counter
c = Counter()
for m, w, _ in sec:
    c[m] += w
print("words by mode:", dict(c))
print("total:", sum(c.values()))
# References/Appendix 位置
for i, (m, w, t) in enumerate(sec):
    if t in ("References", "Appendix"):
        print(f"  pos {i}: mode={m} '{t}'")
