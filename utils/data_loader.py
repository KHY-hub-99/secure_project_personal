import json
import os
from pyprojroot import here
root = str(here())

def load_attack_patterns(category:str=None):
    file_path = os.path.join(root, "data", "attack_patterns", "colla_v2.json")

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
    
def save_defense_pattern(category:str, attack_payload:str, defense_output:str, judgment:str):
    dir_path = os.path.join(root, "data", "defense_patterns")
    os.makedirs(dir_path, exist_ok=True)

    file_path = os.path.join(dir_path, f"{category}_defense_success_data.json")

    existing_data = []
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            existing_data = json.load(f)

    new_entry = {
        "vulnerability": category,
        "attack_input": attack_payload,
        "blue_response": defense_output,
        "judgment": judgment,
        "timestamp": str(os.path.getmtime(file_path)) if os.path.exists(file_path) else "new"
    }
    existing_data.append(new_entry)

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(existing_data, f, ensure_ascii=False, indent=2)

    print(f"[Dataset] 고품질 방어 데이터가 {file_path}에 축적되었습니다.")

def save_generated_attack(category:str, attack_payload:str, blue_response:str, round_num:int):
    """
    Red Agent가 타겟을 뚫어내는 데 성공한 '치명적인 변형 공격(Zero-day Payload)'을 영구 저장합니다.
    """
    dir_path = os.path.join(root, "data", "attack_patterns")
    os.makedirs(dir_path, exist_ok=True)

    file_path = os.path.join(dir_path, f"{category}_attack_success_data.json")

    existing_data = []
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            existing_data = json.load(f)

    new_entry = {
        "category": category,
        "round_found": round_num,
        "successful_payload": attack_payload,
        "blue_response": blue_response
    }
    existing_data.append(new_entry)

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(existing_data, f, ensure_ascii=False, indent=2)

    print(f"[Red Dataset] 타겟을 뚫어낸 치명적 공격 패턴이 {file_path}에 기록되었습니다.")