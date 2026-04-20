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
    """LLM 클라이언트 — 역할별 어댑터 전환"""

    def __init__(
        self,
        use_local_peft: bool = False,
        ollama_base_url: str = os.getenv("OLLAMA_BASE_URL")
    ):
        self.use_local_peft = use_local_peft
        self.current_role = None
        self.ollama_base_url = ollama_base_url

        self.ollama_base_models = {
            "base": os.getenv("OLLAMA_MODEL"),
            "red": os.getenv("OLLAMA_RED_MODEL"),
            "blue": os.getenv("OLLAMA_BLUE_MODEL"),
            "judge": os.getenv("OLLAMA_JUDGE_MODEL"),
        }

        self.local_base_models = {
            "base": os.getenv("LOCAL_BASE_MODEL"),
            "red": os.getenv("LOCAL_RED_MODEL"),
            "blue": os.getenv("LOCAL_BLUE_MODEL"),
            "judge": os.getenv("LOCAL_JUDGE_MODEL"),
        }

        self.role_configs: Dict[str, Dict[str, Any]] = {
            "base": {
                "local_model": self.local_base_models["base"],
                "ollama_model": self.ollama_base_models["base"],
                "temperature": 0.1,
                "top_p": 0.95,
                "top_k": 64,
                "num_ctx": 8192,
                "adapter_path": None,
            },
            "red": {
                "local_model": self.local_base_models["red"],
                "ollama_model": self.ollama_base_models["red"],
                "temperature": 1.0,
                "top_p": 0.95,
                "top_k": 64,
                "num_ctx": 8192,
                "adapter_path": os.path.join(root, "adapters", "lora-red"),
            },
            "blue": {
                "local_model": self.local_base_models["blue"],
                "ollama_model": self.ollama_base_models["blue"],
                "temperature": 0.1,
                "top_p": 0.95,
                "top_k": 64,
                "num_ctx": 8192,
                "adapter_path": os.path.join(root, "adapters", "lora-blue"),
            },
            "judge": {
                "local_model": self.local_base_models["judge"],
                "ollama_model": self.ollama_base_models["judge"],
                "temperature": 0.0,
                "top_p": 1,
                "top_k": 1,
                "num_ctx": 16384,
                "adapter_path": os.path.join(root, "adapters", "lora-judge"),
            },
        }

        self.ollama_target_models = {
            "red": os.getenv("OLLAMA_RED_TARGET_MODEL", "agentshield-red"),
            "judge": os.getenv("OLLAMA_JUDGE_TARGET_MODEL", "agentshield-judge"),
            "blue": os.getenv("OLLAMA_BLUE_TARGET_MODEL", "agentshield-blue"),
            "base": os.getenv("OLLAMA_BASE_TARGET_MODEL", self.role_configs["base"]["ollama_model"]),
        }

        if not self.use_local_peft:
            print("[LLM Client] Ollama API 모드(시뮬레이션 전용) 초기화")
            self.active_ollama_model = self.ollama_target_models["base"]
        else:
            print("[LLM Client] Local PEFT 모드(학습 전용) 초기화")
            self.base_model = None
            self.model = None
            self.tokenizer = None
            self.current_local_base_path = None

    def switch_role(self, role: str):
        if role == self.current_role:
            return

        role_config = self.role_configs.get(role, self.role_configs["base"])

        if not self.use_local_peft:
            self.active_ollama_model = self.ollama_target_models.get(role, role_config["ollama_model"])
            print(f"[Ollama API] 역할 전환: {self.current_role} -> {role} (타겟 모델: {self.active_ollama_model})")
        else:
            target_base_path = role_config["local_model"]

            if self.current_local_base_path != target_base_path:
                print(f"[Local PEFT] 베이스 모델 변경 감지. 기존 메모리 정리 및 [{target_base_path}] 로드 중...")

                if self.base_model is not None:
                    del self.model
                    del self.base_model
                    del self.tokenizer
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()

                self.tokenizer = AutoTokenizer.from_pretrained(target_base_path)
                self.base_model = AutoModelForCausalLM.from_pretrained(
                    target_base_path,
                    device_map="auto",
                    torch_dtype=torch.float16,
                )
                self.current_local_base_path = target_base_path

            adapter_path = role_config.get("adapter_path")
            if adapter_path and os.path.exists(adapter_path):
                print(f"[{role}] 어댑터 로드 중... ({adapter_path})")
                self.model = PeftModel.from_pretrained(self.base_model, adapter_path)
            else:
                print(f"[{role}] 어댑터를 찾을 수 없어 Base 모델로 동작합니다.")
                self.model = self.base_model

        self.current_role = role

    @staticmethod
    def parse_thinking_output(response: str) -> str:
        if "<channel|>" in response:
            return response.split("<channel|>")[-1].strip()
        if "</think>" in response:
            return response.split("</think>")[-1].strip()
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