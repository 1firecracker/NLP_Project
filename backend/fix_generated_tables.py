"""
修复生成题库中缺失的表格
"""
import json
import re
from pathlib import Path
import shutil

# 定义文件路径
md_file = Path(r"C:\Users\19668\Desktop\workspace\NLP_Project-yhx_test\backend\uploads\exercises\c84f70ce-4f86-4a90-b1d8-158e9bdd0fc0\samples\final24\result.md")
qb_file = Path(r"C:\Users\19668\Desktop\workspace\NLP_Project-yhx_test\backend\data\c84f70ce-4f86-4a90-b1d8-158e9bdd0fc0_generated\quiz\question_bank.json")

# 读取MD文件
with open(md_file, 'r', encoding='utf-8') as f:
    md_content = f.read()

# 提取所有表格
tables = {}

table1_match = re.search(r'Table 1:.*?\n\n(<table>.*?</table>)', md_content, re.DOTALL)
if table1_match:
    tables['Table 1'] = table1_match.group(1).strip()

table2_match = re.search(r'Table 2:.*?\n\n(<table>.*?</table>)', md_content, re.DOTALL)
if table2_match:
    tables['Table 2'] = table2_match.group(1).strip()

table3_match = re.search(r'Table 3:.*?\n\n(<table>.*?</table>)', md_content, re.DOTALL)
if table3_match:
    tables['Table 3'] = table3_match.group(1).strip()

# 读取题库
with open(qb_file, 'r', encoding='utf-8') as f:
    qb_data = json.load(f)

# 修复每个题目
updated_count = 0
for question in qb_data['question_bank']['questions']:
    stem = question['stem']
    
    for table_name, table_html in tables.items():
        if table_name in stem and '<table' not in stem:
            pattern = rf'{table_name}[:\.]'
            match = re.search(pattern, stem)
            if match:
                insert_pos = stem.find('.', match.end()) + 1
                if insert_pos > 0:
                    new_stem = stem[:insert_pos] + '\n\n' + table_html + '\n\n' + stem[insert_pos:]
                    question['stem'] = new_stem
                    updated_count += 1
                    print(f"✅ 题目 {question.get('id', '?')}: 添加了 {table_name}")

# 备份
backup_file = qb_file.with_suffix('.json.backup2')
shutil.copy(qb_file, backup_file)

# 保存
with open(qb_file, 'w', encoding='utf-8') as f:
    json.dump(qb_data, f, ensure_ascii=False, indent=2)

print(f"\n✅ 共更新 {updated_count} 个题目")
print(f"✅ 文件已更新: {qb_file}")
