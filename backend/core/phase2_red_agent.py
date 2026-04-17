"""
[R1] Phase 2 — Red Agent 변형 공격

세부기획서 섹션 1(R1 역할), 기능별 파이프라인 섹션 2 참조.
Phase 1에서 "safe" 결과를 가져와 AI가 우회 변형 생성. 최대 5라운드 Self-Play.
"""
import json
import sys
from pyprojroot import here
root = str(here())
sys.path.append(root)
from backend.agents.llm_client import AgentShieldLLM
from backend.agents.red_agent import RedAgent
from backend.agents.blue_agent import BlueAgent
from backend.agents.judge_agent import JudgeAgent
from utils.data_loader import load_attack_patterns, save_defense_pattern, save_generated_attack
    
class Phase2RedNode:
    def __init__(self, llm_client: AgentShieldLLM):
        self.llm_client = llm_client
        self.red = RedAgent(llm_client)
        self.blue = BlueAgent(llm_client)
        self.judge = JudgeAgent(llm_client)
        
        self.max_mutation_rounds = 5

    def run(self, category: str):
        attack_patterns = load_attack_patterns(category, "colla_v3.json")
        if not attack_patterns:
            print(f"[{category}] 공격 패턴이 없습니다. 데이터를 확인하세요.")
            return

        print(f"\n{'='*65}")
        print(f"[Phase 2]: Red vs Blue 에이전트 직접 대결 (대상: {len(attack_patterns)}개 시나리오)")
        print(f"{'='*65}")

        for idx, item in enumerate(attack_patterns):
            initial_attack = item.get("prompt_text")
            if not initial_attack:
                continue

            print(f"\n[Scenario {idx+1}/{len(attack_patterns)}] 시작")
            print(f"   > 초기 공격: {initial_attack}\n")

            pre_attack = initial_attack

            for round_num in range(1, self.max_mutation_rounds + 1):
                print(f"\n[Round {round_num}]")
                
                # 1. Blue Agent 방어 시뮬레이션
                print("> Blue Agent: 방어 응답 생성 중...")
                blue_response = self.blue.simulate_response(category, pre_attack)
                print(f"> Blue Agent 응답: {blue_response}\n")

                # 2. Judge Agent 판정 (Gemma 4 기반 JSON 판정)
                print("> Judge Agent: 보안 판정 중...")
                judgment_dict = self.judge.evaluate_response(category, pre_attack, blue_response)
                
                # [요청사항] 판정 결과를 JSON 형식으로 출력
                print(f"> 판정 결과: {json.dumps(judgment_dict, indent=2, ensure_ascii=False)}")

                judgment = judgment_dict.get("judgment")
                reason = judgment_dict.get("reason")
                
                # 3. 방어 패턴 저장 (데이터셋 축적)
                save_defense_pattern(category, pre_attack, blue_response, judgment, reason)

                if judgment == "FAIL":
                    # 방어선 붕괴 시 루프 종료
                    print(f"\n[!] RED WINS: 방어선이 돌파되었습니다.")
                    save_generated_attack(category, pre_attack, blue_response, round_num, judgment, reason)
                    break
                else:
                    print(f"\n[*] BLUE WINS: 방어 성공. Red Agent가 변형을 시도합니다.")

                # 4. Red Agent 변형 공격 생성 (Thinking Mode 활용)
                print("> Red Agent: 변형 공격 생성 중...")
                mutated_attack = self.red.generate_attack(
                    category=category, 
                    pre_attack=pre_attack, 
                    target_res=blue_response, 
                    similar_successes=[], 
                    round_num=round_num
                )
                print(f"\n> Red Agent (변형 공격): {mutated_attack}")

                pre_attack = mutated_attack
    
if __name__ == "__main__":
    llm = AgentShieldLLM(use_local_peft=False)
    pipeline = Phase2RedNode(llm)
    pipeline.run("LLM01")