"""
搜索阿片类药物临床病例库
用法：python search_cases.py <查询词> [top_k]
"""
import json, sys, io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 数据文件路径（相对于本脚本，不依赖本机绝对路径）
SKILL_DIR = Path(__file__).resolve().parent.parent
CASES_FILE = SKILL_DIR / "data" / "sample_cases.json"

# 字段权重：诊断/药物名命中比风险提示更重要
FIELD_WEIGHTS = {
    "diagnosis":       3,
    "pain_type":       2,
    "category":        2,
    "recommended_plan": 2,
    "evidence":        1,
    "risk_notes":      1,
    "comorbidities":   1,
}

# 医学通用词，几乎所有病例都包含，不应参与排名
STOP_WORDS = {"镇痛", "疼痛", "用药", "治疗", "方案", "患者", "阿片", "阿片类", "药物", "急性", "重症"}

def search(query, top_k=5):
    with open(CASES_FILE, encoding="utf-8") as f:
        cases = json.load(f)
    words = [w for w in query.lower().split() if w not in STOP_WORDS]
    if not words:  # 如果全是停用词，退回原始查询
        words = query.lower().split()
    results = []
    for case in cases:
        score = 0
        for field, weight in FIELD_WEIGHTS.items():
            val = case.get(field, "")
            if isinstance(val, list):
                val = " ".join(val)
            val = val.lower()
            score += sum(weight for w in words if w in val)
        if score > 0:
            results.append((score, case))
    results.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in results[:top_k]]

if __name__ == "__main__":
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else ""
    if not query:
        print("用法: python search_cases.py <查询词>")
        sys.exit(1)
    cases = search(query)
    if not cases:
        print("未找到匹配病例。")
        sys.exit(0)
    print(f"找到 {len(cases)} 个相关病例：\n")
    for c in cases:
        print(f"【{c['id']}】{c['diagnosis']}（{c.get('pain_type','')}）")
        print(f"  推荐方案：{c.get('recommended_plan','')}")
        print(f"  循证依据：{c.get('evidence','')}")
        print(f"  风险提示：{c.get('risk_notes','')}")
        print(f"  治疗结果：{c.get('outcome','')}")
        print()
