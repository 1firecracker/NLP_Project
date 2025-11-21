#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查 shared_state 和生成题库的状态"""

from app.agents.shared_state import shared_state
from app.agents.database.question_bank_storage import load_question_bank

def main():
    # 检查内存中的 generated_exam
    qb = getattr(shared_state, 'generated_exam', None)
    print("=" * 50)
    print("shared_state.generated_exam")
    print("=" * 50)
    print(f"Type: {type(qb)}")
    print(f"Questions: {len(getattr(qb, 'questions', [])) if qb else 0}")
    
    if qb and getattr(qb, 'questions', None) and len(qb.questions) > 0:
        print(f"\nFirst Question:")
        print(f"  ID: {qb.questions[0].id}")
        print(f"  Type: {qb.questions[0].question_type}")
        print(f"  Stem: {qb.questions[0].stem[:200]}")
    
    # 检查磁盘上的 _generated 题库
    conv_id = "286d8d8d-45c6-4358-898c-48c6925bb076"
    qb2 = load_question_bank(f"{conv_id}_generated")
    
    print("\n" + "=" * 50)
    print(f"{conv_id}_generated (disk)")
    print("=" * 50)
    print(f"Type: {type(qb2)}")
    print(f"Questions: {len(getattr(qb2, 'questions', [])) if qb2 else 0}")
    
    if qb2 and getattr(qb2, 'questions', None) and len(qb2.questions) > 0:
        print(f"\nFirst Question:")
        print(f"  ID: {qb2.questions[0].id}")
        print(f"  Type: {qb2.questions[0].question_type}")
        print(f"  Stem: {qb2.questions[0].stem[:200]}")
    
    # 检查原始题库（Agent A）
    qb3 = load_question_bank(conv_id)
    print("\n" + "=" * 50)
    print(f"{conv_id} (original, Agent A)")
    print("=" * 50)
    print(f"Type: {type(qb3)}")
    print(f"Questions: {len(getattr(qb3, 'questions', [])) if qb3 else 0}")
    
    if qb3 and getattr(qb3, 'questions', None) and len(qb3.questions) > 0:
        print(f"\nFirst 3 Questions:")
        for i, q in enumerate(qb3.questions[:3], 1):
            print(f"  [{i}] ID: {q.id}, Type: {q.question_type}")
            print(f"      Stem: {q.stem[:100]}...")

if __name__ == "__main__":
    main()
