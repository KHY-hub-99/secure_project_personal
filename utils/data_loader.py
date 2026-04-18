import json
import os
from datetime import datetime
from pyprojroot import here
root = str(here())

def load_attack_patterns(category:str=None, filename:str=None):
    file_path = os.path.join(root, "data", "attack_patterns", filename)

    if not os.path.exists(file_path):
        print(f"[Warning] 패턴 파일을 찾을 수 없습니다: {file_path}")
        return []
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data =  json.load(f)
            # print(data)
            if category == None:
                fitered_data = data
            else:
                fitered_data = [p for p in data if p.get("category") == category]
            return fitered_data
        
    except Exception as e:
        print(f"[Error] 파일 로드 실패: {str(e)}")
        return []
    
def save_defense_pattern(category:str, sub_category:str, attack_prompt:str, defense_output:str, judgment:str, reason:str, thought_process, out_path:str):
    dir_path = os.path.join(root, "data", "defense_patterns")
    os.makedirs(dir_path, exist_ok=True)

    file_path = os.path.join(dir_path, out_path)

    existing_data = []
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            existing_data = json.load(f)

    new_entry = {
        "category": category,
        "sub_category": sub_category,
        "judgment": judgment,
        "reason": reason,
        "thought_process": thought_process,
        "attack_prompt": attack_prompt,
        "blue_response": defense_output,
        "judgment": judgment,
        "timestamp": datetime.now().isoformat()
    }
    existing_data.append(new_entry)

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(existing_data, f, ensure_ascii=False, indent=2)

def save_generated_attack(category:str, sub_category:str, attack_prompt:str, blue_response:str, round_num:int, judgment:str, reason:str, thought_process, out_path:str):
    """
    Red Agent가 타겟을 뚫어내는 데 성공한 '치명적인 변형 공격(Zero-day Payload)'을 영구 저장합니다.
    """
    dir_path = os.path.join(root, "data", "attack_patterns")
    os.makedirs(dir_path, exist_ok=True)

    file_path = os.path.join(dir_path, out_path)

    existing_data = []
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            existing_data = json.load(f)

    new_entry = {
        "category": category,
        "sub_category": sub_category,
        "round_found": round_num,
        "judgment": judgment,
        "reason": reason,
        "thought_process": thought_process,
        "attack_prompt": attack_prompt,
        "blue_response": blue_response,
        "timestamp": datetime.now().isoformat()
    }
    existing_data.append(new_entry)

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(existing_data, f, ensure_ascii=False, indent=2)