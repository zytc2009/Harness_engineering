"""Quick probe: ask each phase provider '你是谁？' and print the reply."""

import config
from langchain_core.messages import HumanMessage

PHASES = [
    ("architect",   "Claude"),
    ("implementer", "Kimi"),
    ("tester",      "MiniMax"),
]

def probe(phase: str, label: str) -> None:
    provider = config._resolve_provider(phase)
    model    = config._resolve_model(phase)
    print(f"\n{'─'*50}")
    print(f"  {label} | provider={provider} | model={model}")
    print(f"{'─'*50}")
    try:
        llm = config.get_llm(phase=phase)
        resp = llm.invoke([HumanMessage(content="你是谁？请简短回答。")])
        print(resp.content)
    except Exception as e:
        print(f"[ERROR] {e}")

if __name__ == "__main__":
    for phase, label in PHASES:
        probe(phase, label)
    print(f"\n{'─'*50}")
    print("  Done.")
    print(f"{'─'*50}\n")
