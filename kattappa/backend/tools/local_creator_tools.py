from __future__ import annotations

import re
from collections import Counter
from typing import Any


DEFAULT_DECK_SECTIONS = [
    "Problem",
    "Audience",
    "Current Workflow",
    "Proposed Solution",
    "Product Capabilities",
    "Free Local Stack",
    "Safety Boundary",
    "Next Build Steps",
]


def create_local_deck_outline(
    topic: str,
    audience: str = "users",
    project: str = "",
    slide_count: int = 8,
) -> dict[str, Any]:
    clean_topic = _clean_text(topic) or "Project update"
    clean_audience = _clean_text(audience) or "users"
    clean_project = _clean_text(project) or "local project"
    sections = DEFAULT_DECK_SECTIONS[: max(3, min(slide_count, len(DEFAULT_DECK_SECTIONS)))]
    slides = []
    for index, section in enumerate(sections, start=1):
        slides.append(
            {
                "number": index,
                "title": f"{section}: {clean_project}",
                "bullets": _deck_bullets(section, clean_topic, clean_audience),
            }
        )
    markdown = "\n\n".join(
        [
            f"## {slide['number']}. {slide['title']}\n"
            + "\n".join(f"- {bullet}" for bullet in slide["bullets"])
            for slide in slides
        ]
    )
    return {
        "engine": "kattappa_local_deck_generator",
        "replaces": ["pitch_ai", "gamma_ai"],
        "cost": "free",
        "network_required": False,
        "format": "markdown_deck_outline",
        "topic": clean_topic,
        "audience": clean_audience,
        "project": clean_project,
        "slides": slides,
        "markdown": markdown,
        "export_note": "Paste into Markdown, Marp, Reveal.js, PowerPoint, or the project README as a starter deck.",
    }


def create_mermaid_diagram(text: str, diagram_type: str = "flowchart") -> dict[str, Any]:
    clean_text = _clean_text(text)
    statements = _split_ideas(clean_text)
    if not statements:
        statements = ["Input", "Process", "Output"]
    if diagram_type == "mindmap":
        diagram = _mindmap(statements)
    else:
        diagram = _flowchart(statements)
    return {
        "engine": "kattappa_mermaid_diagram_generator",
        "replaces": ["napkin_ai"],
        "cost": "free",
        "network_required": False,
        "diagram_type": "mindmap" if diagram_type == "mindmap" else "flowchart",
        "items": statements,
        "mermaid": diagram,
        "export_note": "Render with Mermaid CLI, GitHub Markdown, or any local Mermaid-compatible viewer.",
    }


def compress_context(text: str, max_points: int = 12) -> dict[str, Any]:
    original = text or ""
    lines = [_clean_text(line) for line in original.splitlines()]
    lines = [line for line in lines if line]
    unique_lines = list(dict.fromkeys(lines))
    scored = sorted(
        ((line, _importance_score(line)) for line in unique_lines),
        key=lambda item: (-item[1], unique_lines.index(item[0])),
    )
    selected = [line for line, _score in scored[: max(3, min(max_points, 40))]]
    omitted = max(0, len(unique_lines) - len(selected))
    compressed = "\n".join(f"- {line}" for line in selected)
    original_chars = len(original)
    compressed_chars = len(compressed)
    ratio = 0.0 if original_chars == 0 else round(1 - (compressed_chars / original_chars), 3)
    return {
        "engine": "kattappa_local_context_compressor",
        "replaces": ["headroom_context_compression"],
        "cost": "free",
        "network_required": False,
        "original_lines": len(lines),
        "unique_lines": len(unique_lines),
        "selected_points": len(selected),
        "omitted_lines": omitted,
        "original_chars": original_chars,
        "compressed_chars": compressed_chars,
        "compression_ratio": max(0.0, ratio),
        "key_points": selected,
        "compressed_text": compressed,
        "privacy_boundary": "Local deterministic compression only. No tool output, logs, files, or chat text leave the machine.",
    }


def local_code_review(diff_text: str, project: str = "") -> dict[str, Any]:
    text = diff_text or ""
    findings = []
    checks = [
        ("hardcoded_secret", r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"][^'\"]{8,}", "high"),
        ("unsafe_shell", r"shell\s*=\s*True|subprocess\.(call|run|Popen)\([^)]*(rm\s+-rf|del\s+/)", "high"),
        ("debug_leftover", r"console\.log\(|print\(|debugger;|pdb\.set_trace", "medium"),
        ("broad_exception", r"except\s+Exception\s*:|catch\s*\([^)]*\)\s*\{\s*//", "medium"),
        ("missing_todo_resolution", r"(?i)\b(todo|fixme|hack)\b", "low"),
        ("possible_sql_injection", r"(?i)(select|insert|update|delete).*(\+|f['\"]|format\()", "high"),
    ]
    for rule_id, pattern, severity in checks:
        for match in re.finditer(pattern, text):
            line_no = text[: match.start()].count("\n") + 1
            findings.append(
                {
                    "rule": rule_id,
                    "severity": severity,
                    "line": line_no,
                    "message": _review_message(rule_id),
                }
            )
    summary = "No obvious local heuristic issues found." if not findings else f"{len(findings)} review signal(s) found."
    return {
        "engine": "kattappa_local_code_review",
        "replaces": ["coderabbit_core_dependency"],
        "cost": "free",
        "network_required": False,
        "project": _clean_text(project),
        "summary": summary,
        "findings": findings[:40],
        "checklist": [
            "Run the project-specific tests or smoke checks.",
            "Check secrets, tokens, and credentials are not committed.",
            "Verify risky shell, file, network, and desktop actions are approval-gated.",
            "Confirm user-facing changes still work on desktop and mobile where relevant.",
            "Review docs or README updates when behavior changes.",
        ],
    }


def create_gsd_workflow(goal: str, project: str = "") -> dict[str, Any]:
    clean_goal = _clean_text(goal) or "Improve the project"
    clean_project = _clean_text(project) or "local project"
    phases = [
        {
            "phase": "plan",
            "tasks": [
                f"Define the smallest useful outcome for {clean_goal}.",
                "List files likely to change and safety boundaries.",
                "Choose verification commands before editing.",
            ],
        },
        {
            "phase": "execute",
            "tasks": [
                "Make narrow source changes that match existing patterns.",
                "Keep unrelated project folders untouched.",
                "Record assumptions and fallback behavior.",
            ],
        },
        {
            "phase": "verify",
            "tasks": [
                "Run compile, lint, unit, or smoke checks that exist locally.",
                "Inspect git diff for accidental secrets, generated files, or unrelated churn.",
                "Confirm each project still works individually.",
            ],
        },
        {
            "phase": "fix",
            "tasks": [
                "Patch failures directly.",
                "Repeat focused verification.",
                "Summarize what changed, what passed, and what could not run.",
            ],
        },
    ]
    return {
        "engine": "kattappa_local_gsd_workflow",
        "replaces": ["antigravity_core_dependency", "gsd_external_framework", "ralph_coding_loop_dependency"],
        "cost": "free",
        "network_required": False,
        "project": clean_project,
        "goal": clean_goal,
        "phases": phases,
        "safety_boundary": "Human approval remains required for destructive commands, installs, credentials, payments, and risky desktop actions.",
    }


def convert_document_text_to_markdown(filename: str, text: str) -> dict[str, Any]:
    name = _clean_text(filename) or "document.txt"
    raw = text or ""
    if name.lower().endswith((".html", ".htm")):
        markdown = _html_to_markdown(raw)
    elif name.lower().endswith(".csv"):
        markdown = _csv_to_markdown(raw)
    else:
        markdown = _plain_text_to_markdown(raw)
    return {
        "engine": "kattappa_local_document_markdown",
        "replaces": ["markitdown_required_dependency"],
        "optional_adapter": "microsoft_markitdown_when_installed",
        "cost": "free",
        "network_required": False,
        "filename": name,
        "markdown": markdown,
        "note": "Built-in text/HTML/CSV fallback. Install the open-source MarkItDown adapter later for PDFs, DOCX, PPTX, XLSX, and richer formats.",
    }


def create_marketing_kit(
    brand: str,
    product: str,
    audience: str = "customers",
    channel: str = "social",
) -> dict[str, Any]:
    clean_brand = _clean_text(brand) or "Local Brand"
    clean_product = _clean_text(product) or "product"
    clean_audience = _clean_text(audience) or "customers"
    clean_channel = _clean_text(channel) or "social"
    hooks = [
        f"Meet {clean_product}: built for {clean_audience}.",
        f"{clean_brand} helps {clean_audience} move from confusion to action.",
        f"Stop guessing. Start using {clean_product} with a clear local workflow.",
    ]
    posts = [
        {
            "channel": clean_channel,
            "headline": hooks[0],
            "body": (
                f"{clean_brand} is shaping {clean_product} around practical outcomes, clear safety boundaries, "
                f"and workflows {clean_audience} can trust."
            ),
            "cta": "Try the local demo",
        },
        {
            "channel": clean_channel,
            "headline": "Built local-first, improved step by step",
            "body": (
                f"Every improvement to {clean_product} is checked against free-tool rules, privacy, and verification before release."
            ),
            "cta": "See what is ready",
        },
    ]
    return {
        "engine": "kattappa_local_marketing_kit",
        "replaces": ["pomelli_core_dependency", "ralph_ecommerce_marketing_dependency"],
        "cost": "free",
        "network_required": False,
        "brand": clean_brand,
        "product": clean_product,
        "audience": clean_audience,
        "channel": clean_channel,
        "brand_voice": ["clear", "useful", "local-first", "safety-aware"],
        "hooks": hooks,
        "posts": posts,
        "email_subjects": [
            f"What {clean_product} can do today",
            f"A safer workflow for {clean_audience}",
            f"{clean_brand}: local-first progress update",
        ],
    }


def toolbox_replacement_report() -> dict[str, Any]:
    return {
        "mode": "fully_free_replacements_for_toolbox_topics",
        "rule": "Add free/open/local equivalents only; keep paid, freemium, invasive, or cloud-account tools out of the core.",
        "added_capabilities": [
            "local_deck_generator",
            "mermaid_diagram_generator",
            "local_context_compressor",
            "local_code_review",
            "local_gsd_workflow",
            "local_document_markdown",
            "local_marketing_kit",
            "local_blackbox_coding_assistant",
            "local_friday_voice_assistant_patterns",
            "local_personal_assistant_patterns",
        ],
        "safe_research_only": [
            "openbci_research_adapter",
            "mne_python_eeg_research_adapter",
        ],
        "blocked_from_core": [
            "pitch_ai_core_dependency",
            "gamma_ai_core_dependency",
            "napkin_ai_core_dependency",
            "vela_hosted_scheduling_dependency",
            "neuralink_or_neuracle_implant_dependency",
            "coderabbit_core_dependency",
            "antigravity_core_dependency",
            "gsd_external_framework",
            "ralph_coding_loop_dependency",
            "ralph_ecommerce_marketing_dependency",
            "pomelli_core_dependency",
            "markitdown_required_dependency",
            "friday_cloud_voice_stack_dependency",
            "blackbox_ai_core_dependency",
            "personal_assistant_repo_code_copying",
        ],
    }


def _deck_bullets(section: str, topic: str, audience: str) -> list[str]:
    templates = {
        "Problem": [
            f"{audience.title()} need a clearer path for {topic}.",
            "Current workflows are fragmented, slow, or hard to verify.",
            "The product should make the next safe action obvious.",
        ],
        "Audience": [
            f"Primary users: {audience}.",
            "Design for repeated daily use, not one-time demos.",
            "Prefer local-first defaults and visible safety boundaries.",
        ],
        "Current Workflow": [
            "Capture the user goal.",
            "Map the project state and available free tools.",
            "Verify with local tests, smoke checks, or exports.",
        ],
        "Proposed Solution": [
            f"Use the local project stack to turn {topic} into a guided workflow.",
            "Keep private data on the machine.",
            "Use adapters only when they are fully free and replaceable.",
        ],
        "Product Capabilities": [
            "Planning, memory, diagrams, exports, and local automation.",
            "Clear status for what is ready, missing, or blocked.",
            "Approval gates before risky actions.",
        ],
        "Free Local Stack": [
            "Markdown/Marp or Reveal.js for decks.",
            "Mermaid for diagrams.",
            "SQLite and local files for state.",
        ],
        "Safety Boundary": [
            "No paid API dependency in the core.",
            "No hidden cloud upload.",
            "No medical or invasive-device claims without research review.",
        ],
        "Next Build Steps": [
            "Pick the smallest useful workflow.",
            "Add a local smoke test.",
            "Document the run command and export path.",
        ],
    }
    return templates.get(section, [topic, audience, "Verify locally."])


def _flowchart(statements: list[str]) -> str:
    lines = ["flowchart TD"]
    for index, statement in enumerate(statements, start=1):
        lines.append(f"  N{index}[\"{_mermaid_label(statement)}\"]")
        if index > 1:
            lines.append(f"  N{index - 1} --> N{index}")
    return "\n".join(lines)


def _mindmap(statements: list[str]) -> str:
    lines = ["mindmap", "  root((Local Plan))"]
    for statement in statements:
        lines.append(f"    {_mermaid_label(statement)}")
    return "\n".join(lines)


def _split_ideas(text: str) -> list[str]:
    parts = re.split(r"[.;\n]+", text)
    ideas = [_clean_text(part) for part in parts]
    return [idea[:90] for idea in ideas if idea][:10]


def _importance_score(line: str) -> int:
    lowered = line.lower()
    keywords = {
        "error": 9,
        "failed": 9,
        "traceback": 9,
        "todo": 8,
        "fix": 7,
        "risk": 7,
        "approval": 7,
        "test": 6,
        "build": 6,
        "warning": 6,
        "memory": 5,
        "voice": 5,
        "desktop": 5,
        "free": 5,
    }
    score = sum(value for key, value in keywords.items() if key in lowered)
    if re.search(r"\b[\w./-]+\.(py|ts|tsx|js|json|md|html|css)\b", line):
        score += 5
    if line.startswith(("-", "*", "1.", "2.", "3.")):
        score += 2
    return score or max(1, min(5, len(line) // 40))


def _review_message(rule_id: str) -> str:
    messages = {
        "hardcoded_secret": "Possible hardcoded secret or credential. Move it to local env/config and keep it out of git.",
        "unsafe_shell": "Risky shell execution found. Ensure it is allowlisted or approval-gated.",
        "debug_leftover": "Debug output or breakpoint may have been left in source.",
        "broad_exception": "Broad exception handling can hide failures. Prefer scoped errors and useful logs.",
        "missing_todo_resolution": "TODO/FIXME/HACK marker needs a decision before release.",
        "possible_sql_injection": "Possible string-built SQL. Prefer parameterized queries.",
    }
    return messages.get(rule_id, "Review this line before merging.")


def _html_to_markdown(text: str) -> str:
    cleaned = re.sub(r"(?is)<(script|style).*?</\1>", "", text)
    cleaned = re.sub(r"(?i)<h1[^>]*>(.*?)</h1>", r"# \1\n\n", cleaned)
    cleaned = re.sub(r"(?i)<h2[^>]*>(.*?)</h2>", r"## \1\n\n", cleaned)
    cleaned = re.sub(r"(?i)<h3[^>]*>(.*?)</h3>", r"### \1\n\n", cleaned)
    cleaned = re.sub(r"(?i)<li[^>]*>(.*?)</li>", r"- \1\n", cleaned)
    cleaned = re.sub(r"(?i)<br\s*/?>", "\n", cleaned)
    cleaned = re.sub(r"(?i)</p>", "\n\n", cleaned)
    cleaned = re.sub(r"<[^>]+>", "", cleaned)
    return _normalize_markdown(cleaned)


def _csv_to_markdown(text: str) -> str:
    rows = [line.split(",") for line in text.splitlines() if line.strip()]
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    padded = [row + [""] * (width - len(row)) for row in rows[:50]]
    header = padded[0]
    body = padded[1:]
    lines = [
        "| " + " | ".join(_clean_text(cell) for cell in header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    for row in body:
        lines.append("| " + " | ".join(_clean_text(cell) for cell in row) + " |")
    return "\n".join(lines)


def _plain_text_to_markdown(text: str) -> str:
    paragraphs = [_clean_text(part) for part in re.split(r"\n{2,}", text) if _clean_text(part)]
    return "\n\n".join(paragraphs)


def _normalize_markdown(text: str) -> str:
    text = re.sub(r"\n{3,}", "\n\n", text)
    lines = [_clean_text(line) if not line.startswith("#") else line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def _clean_text(value: str) -> str:
    return " ".join(str(value).strip().split())


def _mermaid_label(value: str) -> str:
    return _clean_text(value).replace('"', "'").replace("[", "(").replace("]", ")")[:90]
