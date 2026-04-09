"""
Safety Guard Module
===================
3-tier tool safety classification and human confirmation.

Levels:
  AUTO_APPROVE   : Read-only tools, no side effects -> pass through
  ALWAYS_CONFIRM : Write/delete tools -> always ask human
  KEYWORD_CHECK  : Other tools -> check args for dangerous patterns
"""

DANGEROUS_KEYWORDS = [
    "rm ",
    "rm\t",
    "shutil.rmtree",
    "os.remove",
    "os.unlink",
    "DROP TABLE",
    "DELETE FROM",
    "format(",
    "subprocess.call",
    "> /dev/",
    "os.system(",
]

ALWAYS_CONFIRM_TOOLS: frozenset[str] = frozenset()

AUTO_APPROVE_TOOLS: frozenset[str] = frozenset({
    "list_files",
    "read_file",
    "get_file_info",
    "write_file",
    "delete_file",
})


def is_dangerous(tool_input: dict) -> bool:
    """Check if tool arguments contain dangerous keywords."""
    content = str(tool_input).lower()
    return any(kw.lower() in content for kw in DANGEROUS_KEYWORDS)


def classify_tool(tool_name: str, tool_input: dict) -> str:
    """Classify a tool call into one of three safety tiers.

    Returns:
        "auto_approve" | "always_confirm" | "keyword_check"
    """
    if tool_name in AUTO_APPROVE_TOOLS:
        return "auto_approve"
    if tool_name in ALWAYS_CONFIRM_TOOLS:
        return "always_confirm"
    if is_dangerous(tool_input):
        return "keyword_check"
    return "auto_approve"


def should_confirm(tool_name: str, tool_input: dict) -> bool:
    """Whether this tool call requires human confirmation."""
    level = classify_tool(tool_name, tool_input)
    return level in ("always_confirm", "keyword_check")


def request_human_approval(tool_name: str, tool_input: dict) -> bool:
    """Pause execution and ask the human operator for approval.

    Returns:
        True if approved, False if rejected.
    """
    level = classify_tool(tool_name, tool_input)
    if level == "always_confirm" and tool_name == "delete_file":
        flag = "DELETE OP"
    elif level == "keyword_check":
        flag = "HIGH RISK"
    else:
        flag = "WRITE OP"

    print(f"\n{'=' * 55}")
    print(f"  [HARNESS GUARD] {flag}")
    print(f"  Tool   : {tool_name}")
    for k, v in tool_input.items():
        display = str(v)
        if len(display) > 200:
            display = display[:200] + "... (truncated)"
        print(f"  {k:8}: {display}")
    print(f"{'=' * 55}")

    while True:
        answer = input("  Approve? (yes / no): ").strip().lower()
        if answer in ("yes", "y"):
            print("  Approved.\n")
            return True
        if answer in ("no", "n"):
            print("  Rejected. Operation cancelled.\n")
            return False
        print("  Please type 'yes' or 'no'.")
