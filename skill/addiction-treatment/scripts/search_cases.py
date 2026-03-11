#!/usr/bin/env python3
"""
成瘾治疗用药病例搜索脚本
用法: python search_cases.py "查询词"
"""

import csv
import sys
import os
import io
from pathlib import Path

# 设置输出编码
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def search_cases(query: str, top_k: int = 5):
    """搜索匹配的病例"""
    script_dir = Path(__file__).parent
    data_file = script_dir.parent / "data" / "addiction_cases.csv"

    if not data_file.exists():
        print(f"错误: 数据文件不存在 {data_file}")
        return []

    query_lower = query.lower()
    query_terms = query_lower.split()
    results = []

    with open(data_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            score = 0
            text = f"{row.get('question', '')} {row.get('answer', '')} {row.get('诊断', '')} {row.get('药物', '')}".lower()

            for term in query_terms:
                if term in text:
                    score += 1

            if score > 0:
                results.append((score, row))

    results.sort(key=lambda x: x[0], reverse=True)
    return results[:top_k]

def format_result(row: dict) -> str:
    """格式化输出结果"""
    output = []
    output.append(f"【患者信息】年龄: {row.get('年龄', 'N/A')}岁, 诊断: {row.get('诊断', 'N/A')}")
    output.append(f"【问题】{row.get('question', 'N/A')}")
    output.append(f"【推荐方案】\n{row.get('answer', 'N/A')}")
    output.append("-" * 50)
    return "\n".join(output)

def main():
    if len(sys.argv) < 2:
        print("用法: python search_cases.py \"查询词\"")
        print("示例: python search_cases.py \"27岁 opioid成瘾\"")
        sys.exit(1)

    query = sys.argv[1]
    print(f"搜索: {query}\n")

    results = search_cases(query)

    if not results:
        print("未找到匹配的病例")
        return

    print(f"找到 {len(results)} 个相关病例:\n")
    for score, row in results:
        print(format_result(row))

if __name__ == "__main__":
    main()
