import argparse,json
from agent.graph import agent
from agent.mocks import mock_changed_files
def main():
    parser=argparse.ArgumentParser();parser.add_argument("--scenario",choices=["low","high","critical"],default="critical");args=parser.parse_args()
    result=agent.invoke({"base_sha":"mock-base","head_sha":"mock-head","branch_name":f"feature/{args.scenario}-demo","commit_sha":"abcdef1234567890","changed_files":mock_changed_files(args.scenario),"error":None})
    print(result["markdown_report"]);print(json.dumps({"severity":result["severity"],"gate_status":result["gate_status"]},indent=2))
if __name__=="__main__":main()
