import json

f = open(r'data\c84f70ce-4f86-4a90-b1d8-158e9bdd0fc0\quiz\question_bank.json','r',encoding='utf-8')
d = json.load(f)
f.close()

for i, q in enumerate(d['question_bank']['questions']):
    has_table = '<table' in q.get('stem', '')
    answer = q.get('answer', '')
    print(f"题目{i+1} (ID:{q.get('id')}): 包含表格={has_table}, 答案={answer[:30]}...")
