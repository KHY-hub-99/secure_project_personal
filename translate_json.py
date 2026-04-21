import json
import time
import re
import os
import sys
from googletrans import Translator
from pyprojroot import here
root = str(here())
sys.path.append(root)

def split_and_translate(text, translator, target_lang, max_chars=2000):
    if len(text) <= max_chars:
        return translator.translate(text, dest=target_lang).text
    
    sentences = re.split(r'(?<=[.!?])\s+|\n', text)

    translated_chunks = []
    current_chunk = ""

    for sentence in sentences:
        # 현재 청크에 문장을 더했을 때 제한 길이를 넘는지 확인
        if len(current_chunk) + len(sentence) < max_chars:
            current_chunk += (" " + sentence if current_chunk else sentence)
        else:
            # 지금까지 쌓인 청크 번역
            if current_chunk:
                translated_chunks.append(translator.translate(current_chunk, dest=target_lang).text)
                time.sleep(0.3) # API 차단 방지
            current_chunk = sentence

    # 마지막으로 남은 청크 번역
    if current_chunk:
        translated_chunks.append(translator.translate(current_chunk, dest=target_lang).text)

    return " ".join(translated_chunks)


def translate_json_values(data, translator, target_lang='ko', exclude_keys=None):
    if exclude_keys is None:
        exclude_keys = ['category', 'sub_category', 'round_found', 'judgment', 'evidence', 'timestamp']

    if isinstance(data, dict):
        translated_dict = {}
        for key, value in data.items():
            if key in exclude_keys:
                translated_dict[key] = value
            else:
                translated_dict[key] = translate_json_values(value, translator, target_lang, exclude_keys)
        return translated_dict
    
    elif isinstance(data, list):
        return [translate_json_values(item, translator, target_lang, exclude_keys) for item in data]
    
    elif isinstance(data, str):
        if not data.strip():
            return data
        try:
            time.sleep(0.5) 
            # 일반 번역 대신 '길이 확인 및 분할 번역' 함수 호출
            translated_text = split_and_translate(data, translator, target_lang)
            print(f"번역 완료: {data[:20]}... -> {translated_text[:20]}...")
            return translated_text
        except Exception as e:
            print(f"번역 오류 발생: {e} | 원본: {data[:50]}")
            return data
    
    else:
        return data
    
def main(category="LLM01", pf="PASS"):
    source_file_path = os.path.join(root, "data", "attack_patterns", f"{category}_attack_{pf}_data.json")
    target_file_path = os.path.join(root, "data", f"{category}_attack_data_kor.json")

    if not os.path.exists(source_file_path):
        print(f"오류: {source_file_path} 파일을 찾을 수 없습니다.")
        return
    
    with open(source_file_path, 'r', encoding='utf-8') as f:
        original_data = json.load(f)

    print("번역을 시작합니다. (긴 문장은 분할 번역 처리됨)")
    translator = Translator()
    
    translated_data = translate_json_values(original_data, translator, target_lang='ko')

    with open(target_file_path, 'w', encoding='utf-8') as f:
        json.dump(translated_data, f, ensure_ascii=False, indent=4)
    print(f"저장 완료: {target_file_path}")

if __name__ == "__main__":
    main("LLM01", "FAIL")