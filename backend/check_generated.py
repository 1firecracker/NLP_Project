#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查生成题库的前 11 道题"""

from app.agents.database.question_bank_storage import load_question_bank

def main():
    conv_id = "286d8d8d-45c6-4358-898c-48c6925bb076"
    qb = load_question_bank(f"{conv_id}_generated")
    
    if not qb or not qb.questions:
        print("生成题库为空！")
        return
    
    print(f"总共 {len(qb.questions)} 道题")
    print("=" * 80)
    
    for i, q in enumerate(qb.questions[:11], 1):
        print(f"\n[{i}] ID: {q.id}")
        print(f"    Type: {q.question_type}")
        print(f"    Stem (first 150 chars): {q.stem[:150]}...")
        
        # 检查是否重复
        if i > 1 and q.stem == qb.questions[0].stem:
            print(f"    ⚠️  与第一题相同！")

if __name__ == "__main__":
    main()
