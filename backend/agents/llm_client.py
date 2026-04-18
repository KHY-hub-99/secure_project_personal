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
from pydantic import BaseModel
from typing import Optional, Type, Any, Dict

root = str(here())
load_dotenv()

class AgentShieldLLM:
    def __init__(self, use_local_peft:bool=False, ollama_base_url:str=os.getenv("OLLAMA_BASE_URL")):
        self.use_local_peft = use_local_peft
        self.current_role = None
        self.ollama_base_url = ollama_base_url
        
        self.role_configs: Dict[str, Dict[str, Any]] = {
            "red": {
                "local_model": "google/gemma-4-E2B",
                "ollama_model": os.getenv("OLLAMA_MODEL"),
                "temperature": 1.0,
                "top_p": 0.95,
                "top_k": 64,
                "num_ctx": 8192,
                "adapter_path": os.path.join(root, "adapters", "lora-red")
            },
            "blue": {
                "local_model": "google/gemma-4-E2B",
                "ollama_model": os.getenv("OLLAMA_MODEL"),
                "temperature": 1.0,
                "top_p": 0.95,
                "top_k": 64,
                "num_ctx": 8192,
                "adapter_path": os.path.join(root, "adapters", "lora-blue")
            },
            "judge": {
                "local_model": "google/gemma-4-E2B",
                "ollama_model": os.getenv("OLLAMA_MODEL"),
                "temperature": 0.0,
                "top_p": 0.95,
                "top_k": 1,
                "num_ctx": 16384,
                "adapter_path": os.path.join(root, "adapters", "lora-judge")
            },
            "base": {
                "local_model": "google/gemma-4-E2B",
                "ollama_model": os.getenv("OLLAMA_MODEL"),
                "temperature": 1.0,
                "top_p": 0.95,
                "top_k": 64,
                "num_ctx": 8192,
                "adapter_path": None
            }
        }

        # Ollama 전용 타겟 모델 매핑 (Ollama에 미리 생성해둔 어댑터 모델이 있을 경우)
        self.ollama_target_models = {
            "red": "agentshield-red",
            "judge": "agentshield-judge",
            "blue": "agentshield-blue",
            "base": self.role_configs["base"]["ollama_model"]
        }
        
        if not self.use_local_peft:
            self.active_ollama_model = self.role_configs["base"]["ollama_model"]
        else:
            # [Local PEFT 모드] 초기 모델 로드 (기본적으로 base 모델로 시작)
            self.current_base_model_id = self.role_configs["base"]["local_model"]
            print(f"[Local PEFT] 초기 베이스 모델 로드 중: {self.current_base_model_id}")
            
            self.tokenizer = AutoTokenizer.from_pretrained(self.current_base_model_id)
            self.base_model = AutoModelForCausalLM.from_pretrained(
                self.current_base_model_id, 
                torch_dtype=torch.float16, 
                device_map="auto"
            )
            # 최초 실행 시 모델을 PeftModel 구조로 감싸둠 (어댑터 없이 시작)
            self.model = PeftModel.from_pretrained(
                self.base_model, 
                self.role_configs["red"]["adapter_path"], 
                adapter_name="red"
            )
            self.current_role = "red"

    def switch_role(self, role: str):
        """역할에 따라 모델(Ollama) 또는 베이스 모델/어댑터(Local)를 전환합니다."""
        if role == self.current_role:
            return
        
        config = self.role_configs.get(role, self.role_configs["base"])
        
        if not self.use_local_peft:
            self.active_ollama_model = self.ollama_target_models.get(role, config["ollama_model"])
            print(f"[Ollama API] 역할 전환: {self.current_role} -> {role} (모델: {self.active_ollama_model})\n")
        else:
            target_base_model = config["local_model"]
            
            if hasattr(self, 'current_base_model_id') and self.current_base_model_id != target_base_model:
                print(f"[Local PEFT] 베이스 모델 전면 교체: {target_base_model}\n")
                del self.model
                del self.base_model
                torch.cuda.empty_cache() # VRAM 비우기
                
                self.base_model = AutoModelForCausalLM.from_pretrained(
                    target_base_model, torch_dtype=torch.float16, device_map="auto"
                )
                self.tokenizer = AutoTokenizer.from_pretrained(target_base_model)
                self.model = PeftModel.from_pretrained(
                    self.base_model, config["adapter_path"], adapter_name=role
                )
                self.current_base_model_id = target_base_model
            else:
                print(f"[Local PEFT] 어댑터 전환: {role}\n")
                if config["adapter_path"]:
                    if role not in self.model.peft_config:
                        self.model.load_adapter(config["adapter_path"], adapter_name=role)
                    self.model.set_adapter(role)
                    
            print(f"[Local PEFT] '{role}' 역할 활성화 완료.\n")

        self.current_role = role

    def parse_thinking_output(self, response: str) -> str:
        """Gemma 4의 Thinking Mode 출력물에서 최종 답변만 추출합니다."""
        if "<channel|>" in response:
            return response.split("<channel|>")[-1].strip()
        elif "</think>" in response:
            return response.split("</think>")[-1].strip()
        # 태그가 아예 없는 경우 원본을 반환
        return response.strip()

    def chat(self, messages: list, role: str="base", max_tokens: int=2048, response_model: Optional[Type[BaseModel]] = None) -> Any:
        self.switch_role(role)
        
        role_config = self.role_configs.get(role, self.role_configs["base"])
        
        # 역할별 최적 파라미터 로드
        options = {
            "num_predict": max_tokens,
            "temperature": role_config["temperature"],
            "top_p": role_config.get("top_p", 0.95),
            "top_k": role_config.get("top_k", 64),
            "num_ctx": role_config["num_ctx"]
        }

        if not self.use_local_peft:
            url = f"{self.ollama_base_url}/api/chat"
            payload = {
                "model": self.active_ollama_model,
                "messages": messages,
                "stream": False,
                "options": options
            }
            if response_model:
                payload["format"] = response_model.model_json_schema()
                
            try:
                with httpx.Client(timeout=None) as client:
                    response = client.post(url, json=payload)
                    if response.status_code == 404:
                        fallback_model = role_config["ollama_model"]
                        print(f"[Fallback] {self.active_ollama_model} 없음 -> {fallback_model} 사용")
                        payload["model"] = fallback_model
                        response = client.post(url, json=payload)
                    
                    response.raise_for_status()
                    data = response.json()
                    
                    # 토큰 모니터링 출력
                    p_tokens = data.get("prompt_eval_count", 0)
                    print(f"[{role.upper()}] Tokens: {p_tokens} / {options['num_ctx']}")
                    
                    result_text = data.get("message", {}).get("content", "")
                    cleaned_text = self.parse_thinking_output(result_text)
                    
                    if response_model:
                        try:
                            return response_model.model_validate_json(cleaned_text)
                        except Exception as e:
                            print(f"[{role}] Pydantic 에러: {e}\n원본: {cleaned_text}")
                            return None
                    return cleaned_text
            except Exception as e:
                print(f"[Ollama Error] {e}")
                return None
        # [Local PEFT 실행 로직]
        else:
            try:
                text = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
                inputs = self.tokenizer(text, return_tensors="pt").to(self.model.device)
                
                outputs = self.model.generate(
                    **inputs, 
                    max_new_tokens=max_tokens, 
                    temperature=options["temperature"],
                    do_sample=True if options["temperature"] > 0 else False,
                    top_p=options["top_p"]
                )
                
                input_len = inputs["input_ids"].shape[-1]
                result_text = self.tokenizer.decode(outputs[0][input_len:], skip_special_tokens=True)
                cleaned_text = self.parse_thinking_output(result_text)
                
                if response_model:
                    try:
                        return response_model.model_validate_json(cleaned_text)
                    except Exception as e:
                        print(f"[Local PEFT] Pydantic 에러: {e}")
                        return None
                return cleaned_text
            except Exception as e:
                print(f"[Local PEFT Error] {e}")
                return None

    # 기존 코드와의 호환성을 위해 generate 메서드도 유지하거나 chat을 호출하도록 수정
    def generate(self, prompt: str, role: str = "base", max_tokens: int = 2048) -> str:
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