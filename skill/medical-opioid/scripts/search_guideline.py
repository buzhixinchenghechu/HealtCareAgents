"""
搜索阿片类药物急危重症专家共识原文
用法：python search_guideline.py <查询词>
"""
import sys, io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 数据文件路径（相对于本脚本，不依赖本机绝对路径）
SKILL_DIR = Path(__file__).resolve().parent.parent
GUIDELINE_FILE = SKILL_DIR / "data" / "consensus_ocr.txt"

def search(query, context=4):
    with open(GUIDELINE_FILE, encoding="utf-8") as f:
        lines = f.readlines()
    words = query.lower().split()
    hits = []
    for i, line in enumerate(lines):
        if any(w in line.lower() for w in words):
            start = max(0, i - context)
            end = min(len(lines), i + context + 1)
            snippet = "".join(lines[start:end]).strip()
            hits.append((i, snippet))
    # 合并相邻片段
    merged, last_i = [], -999
    for i, s in hits:
        if i - last_i > context * 2:
            merged.append(s)
        last_i = i
    return merged[:6]

if __name__ == "__main__":
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else ""
    if not query:
        print("用法: python search_guideline.py <查询词>")
        sys.exit(1)
    snippets = search(query)
    if not snippets:
        print("专家共识中未找到相关内容。")
        sys.exit(0)
    print(f"专家共识检索结果（查询：{query}）：\n")
    for i, s in enumerate(snippets, 1):
        print(f"--- 片段 {i} ---")
        print(s)
        print()
