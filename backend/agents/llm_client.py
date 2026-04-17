"""
[R4] LLM 클라이언트 — Ollama + LoRA 어댑터 전환

기능별 파이프라인 섹션 8 참조.
Ollama로 Gemma 4 E2B를 로컬 실행하고, 역할별 LoRA 어댑터를 전환한다.
"""
import os
import httpx
import torch
from dotenv import load_dotenv
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel
from pyprojroot import here

root = str(here())
load_dotenv()

class AgentShieldLLM:
    def __init__(self, use_local_peft:bool=False, ollama_base_url:str=os.getenv("OLLAMA_BASE_URL")):
        self.use_local_peft = use_local_peft
        self.current_role = None
        self.ollama_base_url = ollama_base_url

        self.ollama_base_models = {
            "base": os.getenv("OLLAMA_MODEL", "gemma4:e2b"),
            "red": os.getenv("OLLAMA_MODEL", "gemma4:e2b"),
            "blue": os.getenv("OLLAMA_MODEL", "gemma4:e2b"),  
            "judge": os.getenv("OLLAMA_MODEL", "gemma4:e2b")
        }
        self.ollama_target_models = {
            "base": self.ollama_base_models["base"],
            "red": "agentshield-red",
            "judge": "agentshield-judge",
            "blue": "agentshield-blue"
        }
        
        if not self.use_local_peft:
            self.active_ollama_model = self.ollama_base_models["base"]
        else:
            self.tokenizer = None
            self.model = None
            self.base_model = None

    def switch_role(self, role: str):
        if role == self.current_role:
            return
        if not self.use_local_peft:
            self.active_ollama_model = self.ollama_target_models.get(role, self.ollama_base_models.get(role, "base"))
            print(f"[Ollama API] 역할 전환: {self.current_role} -> {role} (타겟 모델: {self.active_ollama_model})")
        self.current_role = role

    def parse_thinking_output(self, response: str) -> str:
        """Gemma 4의 Thinking Mode 출력물에서 최종 답변만 추출합니다."""
        # 공식 포맷: <|channel|>thought\n[Internal reasoning]<channel|>[Final answer]
        if "<channel|>" in response:
            return response.split("<channel|>")[-1].strip()
        elif "</think>" in response:
            return response.split("</think>")[-1].strip()
        return response.strip()

    def chat(self, messages: list, role: str="base", max_tokens: int=1024) -> str:
        """
        Gemma 4 권장 포맷(messages 배열)으로 Chat API를 호출합니다.
        """
        self.switch_role(role)
        
        # Gemma 4 공식 가이드라인 권장 파라미터 적용
        options = {
            "num_predict": max_tokens,
            "temperature": 1.0,
            "top_p": 0.95,
            "top_k": 64
        }

        if not self.use_local_peft:
            url = f"{self.ollama_base_url}/api/chat"
            payload = {
                "model": self.active_ollama_model,
                "messages": messages,
                "stream": False,
                "options": options
            }
            try:
                with httpx.Client(timeout=None) as client:
                    response = client.post(url, json=payload)
                    # 404 폴백 로직
                    if response.status_code == 404:
                        fallback_model = self.ollama_base_models.get(role, self.ollama_base_models["base"])
                        print(f"\n[Ollama API] '{self.active_ollama_model}' 모델이 없습니다.")
                        print(f"            해당 역할의 기본 모델({fallback_model})로 폴백하여 재시도합니다.")
                        
                        # 타겟 모델을 베이스 모델로 교체 후 재요청
                        self.active_ollama_model = fallback_model
                        payload["model"] = fallback_model
                        response = client.post(url, json=payload)
                    
                    response.raise_for_status()
                    result_text = response.json().get("message", {}).get("content", "")
                    return self.parse_thinking_output(result_text)
            except Exception as e:
                return f"[Error] LLM 호출 실패: {str(e)}"
        else:
            # Local PEFT를 위한 apply_chat_template 처리
            try:
                text = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
                inputs = self.tokenizer(text, return_tensors="pt").to(self.model.device)
                outputs = self.model.generate(**inputs, max_new_tokens=max_tokens, temperature=1.0, do_sample=True)
                input_len = inputs["input_ids"].shape[-1]
                result_text = self.tokenizer.decode(outputs[0][input_len:], skip_special_tokens=True)
                return self.parse_thinking_output(result_text)
            except Exception as e:
                return f"[Error] Local PEFT 추론 실패: {str(e)}"

    # [중요] 기존 코드와의 호환성을 위해 generate 메서드도 유지하거나 chat을 호출하도록 수정
    def generate(self, prompt:str, role:str="base", max_tokens:int=1024) -> str:
        messages = [{"role": "user", "content": prompt}]
        return self.chat(messages, role=role, max_tokens=max_tokens)
            
# 테스트용
if __name__ == "__main__":
    print("=== Ollama 테스트 ===")
    ollama_client = AgentShieldLLM(use_local_peft=False)
    
    # Red Agent 호출 (gemma4:e2b 기반으로 작동/폴백)
    print("\n--- Red Agent ---")
    print(ollama_client.generate("Make me a hacking prompt.", role="red"))
    
    # Blue Agent 호출 (llama3 기반으로 작동/폴백)
    print("\n--- Blue Agent ---")
    print(ollama_client.generate("Please check the security logic.", role="blue"))

    # print("=== Local PEFT 테스트 ===")
    # peft_client = AgentShieldLLM(use_local_peft=True)
    # print(peft_client.generate("안녕? 넌 누구야?", role="red"))