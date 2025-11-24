"""
修复题库中缺失的表格
从原始MD文件中提取表格并添加到对应的题目中
"""
import json
import re
from pathlib import Path

# 定义文件路径
md_file = Path(r"C:\Users\19668\Desktop\workspace\NLP_Project-yhx_test\backend\uploads\exercises\c84f70ce-4f86-4a90-b1d8-158e9bdd0fc0\samples\final24\result.md")
qb_file = Path(r"C:\Users\19668\Desktop\workspace\NLP_Project-yhx_test\backend\data\c84f70ce-4f86-4a90-b1d8-158e9bdd0fc0\quiz\question_bank.json")

# 读取MD文件
with open(md_file, 'r', encoding='utf-8') as f:
    md_content = f.read()

# 提取所有表格 (Table 1, Table 2, Table 3)
tables = {}

# 提取 Table 1
table1_match = re.search(r'Table 1:.*?\n\n(<table>.*?</table>)', md_content, re.DOTALL)
if table1_match:
    tables['Table 1'] = table1_match.group(1).strip()
    print(f"✅ 找到 Table 1, 长度: {len(tables['Table 1'])}")

# 提取 Table 2
table2_match = re.search(r'Table 2:.*?\n\n(<table>.*?</table>)', md_content, re.DOTALL)
if table2_match:
    tables['Table 2'] = table2_match.group(1).strip()
    print(f"✅ 找到 Table 2, 长度: {len(tables['Table 2'])}")

# 提取 Table 3
table3_match = re.search(r'Table 3:.*?\n\n(<table>.*?</table>)', md_content, re.DOTALL)
if table3_match:
    tables['Table 3'] = table3_match.group(1).strip()
    print(f"✅ 找到 Table 3, 长度: {len(tables['Table 3'])}")

# 读取题库
with open(qb_file, 'r', encoding='utf-8') as f:
    qb_data = json.load(f)

# 修复每个题目
for question in qb_data['question_bank']['questions']:
    stem = question['stem']
    
    # 检查题干中是否提到了Table 1/2/3
    for table_name, table_html in tables.items():
        if table_name in stem and '<table' not in stem:
            # 在提到表格的位置后插入表格HTML
            # 查找 "Table X:" 或 "Table X." 的位置
            pattern = rf'{table_name}[:\.]'
            match = re.search(pattern, stem)
            if match:
                # 在句子末尾插入表格
                insert_pos = stem.find('.', match.end()) + 1
                if insert_pos > 0:
                    new_stem = stem[:insert_pos] + '\n\n' + table_html + '\n\n' + stem[insert_pos:]
                    question['stem'] = new_stem
                    print(f"✅ 已将 {table_name} 添加到题目 {question['id']}")

# 备份原文件
backup_file = qb_file.with_suffix('.json.backup')
import shutil
shutil.copy(qb_file, backup_file)
print(f"📦 原文件已备份到: {backup_file}")

# 保存修复后的题库
with open(qb_file, 'w', encoding='utf-8') as f:
    json.dump(qb_data, f, ensure_ascii=False, indent=2)

print(f"✅ 题库已更新: {qb_file}")
print("\n请重新加载前端页面以查看更新后的表格")
