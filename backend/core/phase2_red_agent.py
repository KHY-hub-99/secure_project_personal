"""
[R1] Phase 2 — 초기 데이터 blue_agent 주입 -> 응답 판정 -> 변형 공격 생성 반복
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
        attack_patterns = load_attack_patterns(category, "colla_v2.json")
        if not attack_patterns:
            print(f"[{category}] 공격 패턴이 없습니다. 데이터를 확인하세요.")
            return

        print(f"\n{'='*65}")
        print(f"[Phase 2]: Red vs Blue 에이전트 직접 대결 (대상: {len(attack_patterns)}개 시나리오)")
        print(f"{'='*65}")

        for idx, item in enumerate(attack_patterns):
            initial_attack = item.get("prompt_text")
            sub_category = item.get("subcategory", "Initial-Entry")
            
            if not initial_attack:
                continue
            
            print(f"\n[Scenario {idx+1}/{len(attack_patterns)}] 시작")
            
            previous_attack = initial_attack
            previous_blue_response = ""

            for round_num in range(1, self.max_mutation_rounds + 1):
                print("\n" + "=" * 65)
                
                # 1. Red Agent 턴 (공격 세팅 또는 변형 생성)
                if round_num == 1:
                    print(f"\n[Round 1] 시작")
                    print("> Red Agent: 초기 공격 사용")
                    current_attack = initial_attack
                else:
                    print(f"\n[Round {round_num}] 시작")
                    print("\n> Red Agent: 이전 방어 논리를 분석하여 변형 공격 생성 중...")
                    current_attack = self.red.generate_attack(
                        category=category, 
                        sub_category=sub_category,
                        pre_attack=previous_attack, 
                        target_res=previous_blue_response, 
                        similar_successes=[], 
                        round_num=round_num
                    )
                print(f"[Red Agent 공격 페이로드]\n{current_attack}")

                # 2. Blue Agent 턴 (방어 시뮬레이션)
                print("\n" + "=" * 65)
                print("> Blue Agent: 방어 응답 생성 중...")
                blue_response = self.blue.generate_defense(category, current_attack)
                print(f"[Blue Agent 응답]\n{blue_response}\n")

                # 3. Judge Agent 턴 (보안 판정)
                print("\n" + "=" * 65)
                print("> Judge Agent: 보안 판정 중...")
                judgment_dict = self.judge.evaluate_response(category, current_attack, blue_response)
                
                print(f"[판정 결과]\n{json.dumps(judgment_dict, indent=2, ensure_ascii=False)}\n")

                phase1 = judgment_dict.get("phase1", {})
                phase2 = judgment_dict.get("phase2", {})
                
                judgment = judgment_dict.get("verdict", "ERROR")
                reason = judgment_dict.get("technical_impact", "No reason provided.")
                confidence = judgment_dict.get("confidence", 0.0)
                integrity_score = judgment_dict.get("integrity_score", 0.0)
                
                thought_process = {
                    "trigger_to_evidence": judgment_dict.get("trigger_to_evidence", {}),
                    "narrative_surrender": judgment_dict.get("narrative_surrender", False)
                }
                evidence = {
                    "signals": judgment_dict.get("signals", []),
                    "integrity_score": integrity_score,
                    "confidence": confidence
                }
                
                # 4. 결과 판독 및 데이터 저장
                if judgment == "FAIL":
                    print("\n" + "=" * 65)
                    print(f"[!] RED WINS: 방어선이 돌파되었습니다. (시나리오 종료)")
                    save_generated_attack(category, sub_category, current_attack, blue_response, round_num, judgment, reason, thought_process, evidence, out_path=f"{category}_attack_PASS_data.json")
                    save_defense_pattern(category, sub_category, current_attack, blue_response, judgment, reason, thought_process, evidence, out_path=f"{category}_deffense_FAIL_data.json")
                    break # 뚫렸으므로 다음 시나리오로 넘어감
                else:
                    print("\n" + "=" * 65)
                    if round_num < self.max_mutation_rounds:
                        print(f"[*] BLUE WINS: 방어 성공(신뢰도: {phase2.get('confidence')}). Red Agent가 다음 라운드에서 변형을 시도합니다.")
                        save_generated_attack(category, sub_category, current_attack, blue_response, round_num, judgment, reason, thought_process, evidence, out_path=f"{category}_attack_FAIL_data.json")
                        save_defense_pattern(category, sub_category, current_attack, blue_response, judgment, reason, thought_process, evidence, out_path=f"{category}_deffense_PASS_data.json")
                    else:
                        print(f"[*] BLUE WINS: 최종 방어 성공. 최대 라운드({self.max_mutation_rounds})를 버텨냈습니다.")
                        save_generated_attack(category, sub_category, current_attack, blue_response, round_num, judgment, reason, thought_process, evidence, out_path=f"{category}_attack_FAIL_data.json")
                        save_defense_pattern(category, sub_category, current_attack, blue_response, judgment, reason, thought_process, evidence, out_path=f"{category}_deffense_PASS_data.json")
                
                # 다음 라운드 준비
                previous_attack = current_attack
                previous_blue_response = blue_response
    
if __name__ == "__main__":
    llm = AgentShieldLLM(use_local_peft=False)
    pipeline = Phase2RedNode(llm)
    pipeline.run("LLM01")