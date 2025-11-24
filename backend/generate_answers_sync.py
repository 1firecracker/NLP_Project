"""
为包含表格的题目生成答案（同步版本）
"""
import json
import os
import requests
from pathlib import Path
from dotenv import load_dotenv
import re
import time

load_dotenv()

API_URL = os.getenv("LLM_BINDING_HOST", "https://api.siliconflow.cn/v1")
API_KEY = os.getenv("LLM_BINDING_API_KEY")
MODEL_NAME = os.getenv("LLM_MODEL", "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B")

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}

def html_table_to_markdown(html_text):
    """简单的HTML表格转Markdown"""
    if not html_text or '<table' not in html_text.lower():
        return html_text
    
    result = html_text
    table_pattern = re.compile(r'<table[^>]*>(.*?)</table>', re.DOTALL | re.IGNORECASE)
    
    for table_match in table_pattern.finditer(html_text):
        table_html = table_match.group(0)
        table_content = table_match.group(1)
        
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_content, re.DOTALL | re.IGNORECASE)
        if not rows:
            continue
        
        markdown_rows = []
        for i, row in enumerate(rows):
            cells = re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', row, re.DOTALL | re.IGNORECASE)
            if cells:
                clean_cells = []
                for cell in cells:
                    cell_text = re.sub(r'<[^>]+>', '', cell)
                    cell_text = ' '.join(cell_text.split())
                    clean_cells.append(cell_text)
                
                markdown_rows.append('| ' + ' | '.join(clean_cells) + ' |')
                
                if i == 0:
                    markdown_rows.append('| ' + ' | '.join(['---'] * len(clean_cells)) + ' |')
        
        if markdown_rows:
            markdown_table = '\n' + '\n'.join(markdown_rows) + '\n'
            result = result.replace(table_html, markdown_table)
    
    return result


def generate_answer(question_id, stem):
    """使用LLM为题目生成答案"""
    
    # 将HTML表格转为Markdown
    stem_for_llm = html_table_to_markdown(stem)
    
    prompt = f"""请为以下题目提供详细的答案。题目包含表格数据，请仔细分析表格中的信息来回答问题。

题目：
{stem_for_llm}

要求：
1. 如果题目有多个子问题(a)(b)(c)等，请分别作答
2. 对于计算题，给出计算步骤和最终结果
3. 对于分析题，给出清晰的分析思路和结论
4. 答案要简洁明确，重点突出关键步骤和结论
5. 使用中文作答

请直接输出答案，不要重复题目：
"""
    
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": "你是一名数据挖掘和机器学习领域的专家，擅长解答算法、数学计算和数据分析相关的问题。"},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 2000,
        "temperature": 0.3,
    }
    
    try:
        print(f"[→] 正在为题目 {question_id} 生成答案...")
        response = requests.post(
            f"{API_URL}/chat/completions",
            headers=HEADERS,
            json=payload,
            timeout=300  # 增加到 5 分钟，因为 DeepSeek-R1 需要长时间思考
        )
        
        if response.status_code != 200:
            print(f"❌ HTTP错误 {response.status_code}: {response.text}")
            return f"（生成失败：HTTP {response.status_code}）"
        
        res = response.json()
        
        if "error" in res:
            print(f"❌ API错误: {res['error']}")
            return "（生成失败：API错误）"
        
        if "choices" not in res or len(res["choices"]) == 0:
            print(f"❌ 响应格式错误: {res}")
            return "（生成失败：响应格式错误）"
        
        answer = res["choices"][0]["message"]["content"].strip()
        print(f"✅ 题目 {question_id} 答案已生成 (长度: {len(answer)})")
        return answer
        
    except Exception as e:
        import traceback
        print(f"❌ 题目 {question_id} 生成答案失败:")
        print(traceback.format_exc())
        return "（生成失败）"


def main():
    qb_file = Path(r"C:\Users\19668\Desktop\workspace\NLP_Project-yhx_test\backend\data\c84f70ce-4f86-4a90-b1d8-158e9bdd0fc0\quiz\question_bank.json")
    
    # 读取题库
    with open(qb_file, 'r', encoding='utf-8') as f:
        qb_data = json.load(f)
    
    # 找出需要生成答案的题目（包括失败的）
    questions_to_answer = []
    for q in qb_data['question_bank']['questions']:
        answer = q.get('answer', '')
        if '<table' in q.get('stem', '') and (answer == '（待补充）' or '生成失败' in answer):
            questions_to_answer.append(q)
    
    if not questions_to_answer:
        print("没有找到需要生成答案的表格题")
        return
    
    print(f"\n找到 {len(questions_to_answer)} 道需要生成答案的表格题\n")
    
    # 逐个生成答案
    for i, q in enumerate(questions_to_answer, 1):
        print(f"\n[{i}/{len(questions_to_answer)}] 处理题目 {q['id']}...")
        answer = generate_answer(q['id'], q['stem'])
        q['answer'] = answer
        
        # 避免API限流
        if i < len(questions_to_answer):
            time.sleep(3)
    
    # 备份原文件
    import shutil
    backup_file = qb_file.with_suffix('.json.backup5')
    shutil.copy(qb_file, backup_file)
    print(f"\n📦 原文件已备份到: {backup_file}")
    
    # 保存更新后的题库
    with open(qb_file, 'w', encoding='utf-8') as f:
        json.dump(qb_data, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ 题库已更新，共为 {len(questions_to_answer)} 道题目生成了答案")
    print("请刷新前端页面查看")


if __name__ == "__main__":
    main()
