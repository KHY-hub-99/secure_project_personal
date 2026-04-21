import json
import time
import os
import sys
from googletrans import Translator
from pyprojroot import here
root = str(here())
sys.path.append(root)

def translate_json_values(data, translator, target_lang='ko', exclude_keys=None):
    if exclude_keys is None:
        # 번역하지 않고 영어 그대로 남겨둘 키워드 목록 (필요에 따라 수정하세요)
        exclude_keys = ['category', 'sub_category', 'round_found', 'judgment', 'evidence', 'timestamp']

    if isinstance(data, dict):
        translated_dict = {}
        for key, value in data.items():
            # 키(Key)가 제외 목록에 있으면 번역 생략
            if key in exclude_keys:
                translated_dict[key] = value
            else:
                translated_dict[key] = translate_json_values(value, translator, target_lang, exclude_keys)
        return translated_dict
    
    elif isinstance(data, list):
        return [translate_json_values(item, translator, target_lang, exclude_keys) for item in data]
    
    elif isinstance(data, str):
        # 빈 문자열이나 너무 짧은 공백은 무시
        if not data.strip():
            return data
        try:
            # 구글 API 차단(Rate Limit)을 막기 위한 딜레이
            time.sleep(0.5) 
            result = translator.translate(data, dest=target_lang)
            print(f"번역 완료: {data[:20]}... -> {result.text[:20]}...")
            return result.text
        except Exception as e:
            print(f"번역 오류 발생: {e} | 원본: {data}")
            return data
    
    else:
        return data
    
def main():
    source_file_path = os.path.join(root, "data", "attack_patterns", "LLM01_attack_PASS_data.json")
    target_file_path = os.path.join(root, "data", "attack_data_kor.json")

    if not os.path.exists(source_file_path):
        print(f"오류: {source_file_path} 파일을 찾을 수 없습니다.")
        return
    
    with open(source_file_path, 'r', encoding='utf-8') as f:
        original_data = json.load(f)

    print("번역을 시작합니다. (데이터 크기에 따라 시간이 걸릴 수 있습니다.)")
    translator = Translator()

    exclude_keys = ['category', 'sub_category', 'round_found', 'judgment', 'evidence', 'timestamp']

    translated_data = translate_json_values(original_data, translator, target_lang='ko', exclude_keys=exclude_keys)

    with open(target_file_path, 'w', encoding='utf-8') as f:
        json.dump(translated_data, f, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    main()