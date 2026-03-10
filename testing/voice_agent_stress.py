from __future__ import annotations

import json
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from intent_classifier import IntentClassifier
from testing.voice_agent_simulation import ScenarioSpec, scenario_specs, simulate_voice_agent_scenario


_NAME_ROTATION = (
    "Asha Rao",
    "Rahul Sharma",
    "Neha Verma",
    "Gurpreet Singh",
    "Suman Das",
    "Ravi Kumar",
    "Anita Sen",
    "Harpreet Kaur",
    "Imran Ali",
    "Pooja Mehta",
)

_INTENT_SAMPLES: dict[str, list[tuple[str, str]]] = {
    "payment_done": [
        ("payment kar diya", "ask_payment_made"),
        ("I already paid", "ask_payment_made"),
        ("भुगतान हो गया", "ask_payment_made"),
        ("paid yesterday", "ask_payment_made"),
    ],
    "ptp_commit": [
        ("11 मार्च तक कर दूंगा", "ask_ptp_or_callback"),
        ("kal कर दूंगा", "ask_ptp_or_callback"),
        ("parso payment ho jayega", "ask_ptp_or_callback"),
        ("2 din mein pay kar dunga", "ask_ptp_or_callback"),
        ("agle hafte kar dunga", "ask_ptp_or_callback"),
        ("March 11 ko pay karunga", "ask_ptp_or_callback"),
        ("ग्यारह तारीख को कर दूंगा", "ask_ptp_or_callback"),
        ("I will pay tomorrow", "ask_ptp_or_callback"),
        ("मैं 16 मार्च तक कर दूंगा", "ask_ptp_or_callback"),
        ("13/03/2026 को दे दूंगा", "ask_ptp_or_callback"),
        ("ho jayega", "ask_ptp_or_callback"),
    ],
    "ptp_refusal": [
        ("nahi karunga", "ask_ptp_or_callback"),
        ("नहीं करूंगा", "ask_ptp_or_callback"),
        ("will not pay", "ask_ptp_or_callback"),
        ("paise nahi hain, nahi kar paunga", "ask_ptp_or_callback"),
        ("not possible", "ask_ptp_or_callback"),
        ("nahi hoga", "ask_ptp_or_callback"),
    ],
    "callback_request": [
        ("baad mein call karo", "ask_ptp_or_callback"),
        ("kal 3 baje call karna", "ask_ptp_or_callback"),
        ("call me later", "ask_ptp_or_callback"),
        ("callback kar dijiye", "ask_ptp_or_callback"),
        ("3 बजे call kariye", "ask_ptp_or_callback"),
        ("phone later", "ask_ptp_or_callback"),
    ],
    "dispute": [
        ("yeh amount galat hai", "ask_payment_made"),
        ("not my loan", "ask_payment_made"),
        ("I already disputed this", "ask_payment_made"),
        ("mera loan nahi hai", "ask_payment_made"),
        ("wrong amount", "ask_payment_made"),
    ],
    "greeting": [
        ("hello", "consent"),
        ("hi", "consent"),
        ("namaste", "consent"),
        ("good evening", "consent"),
        ("sat sri akaal", "consent"),
    ],
    "acknowledgement": [
        ("haan", "ask_payment_made"),
        ("hmm", "ask_payment_made"),
        ("ok", "ask_payment_made"),
        ("theek", "ask_payment_made"),
        ("जी", "ask_payment_made"),
        ("ਹਾਂ", "ask_payment_made"),
        ("হুম", "ask_payment_made"),
    ],
    "abuse": [
        ("fuck you", "ask_payment_made"),
        ("माँ की चूत", "ask_payment_made"),
        ("रांड के पिल्ले", "ask_payment_made"),
        ("भाड़ में जाओ", "ask_payment_made"),
        ("madarchod", "ask_payment_made"),
    ],
}


def stress_scenario_specs(call_count: int = 50) -> list[ScenarioSpec]:
    base_specs = scenario_specs()
    if call_count <= 0:
        return []
    generated: list[ScenarioSpec] = []
    for index in range(call_count):
        source = base_specs[index % len(base_specs)]
        generated.append(
            replace(
                source,
                key=f"{source.key}_stress_{index + 1:02d}",
                known_customer_name=_NAME_ROTATION[index % len(_NAME_ROTATION)] if source.known_customer_name else None,
            )
        )
    return generated


def run_voice_agent_stress_test(call_count: int = 50) -> dict[str, Any]:
    scenarios = stress_scenario_specs(call_count)
    results: list[dict[str, Any]] = []
    runtimes_ms: list[float] = []
    ptp_expected = 0
    ptp_captured = 0
    loop_occurrences = 0

    for spec in scenarios:
        started = time.perf_counter()
        result = simulate_voice_agent_scenario(spec)
        runtimes_ms.append((time.perf_counter() - started) * 1000.0)
        results.append(result)
        if spec.expect_ptp:
            ptp_expected += 1
            if result.get("ptp_date"):
                ptp_captured += 1
        if (not result.get("no_repeated_prompts", True)) or result.get("payment_question_repeated_after_unpaid", False):
            loop_occurrences += 1

    classifier = IntentClassifier()
    intent_total = 0
    intent_correct = 0
    for expected_intent, samples in _INTENT_SAMPLES.items():
        for text, current_step in samples:
            intent_total += 1
            result = classifier.classify(text, current_step=current_step)
            if result.canonical_intent == expected_intent:
                intent_correct += 1

    return {
        "calls_simulated": len(results),
        "passed_calls": sum(1 for row in results if row.get("passed")),
        "ptp_expected": ptp_expected,
        "ptp_captured": ptp_captured,
        "ptp_extraction_accuracy": round((ptp_captured / ptp_expected) if ptp_expected else 1.0, 4),
        "intent_probe_count": intent_total,
        "intent_correct": intent_correct,
        "intent_classification_accuracy": round((intent_correct / intent_total) if intent_total else 1.0, 4),
        "average_latency_ms": round(sum(runtimes_ms) / max(1, len(runtimes_ms)), 2),
        "loop_occurrences": loop_occurrences,
        "results": results,
    }


def write_voice_agent_stress_artifacts(output_dir: str | Path, *, call_count: int = 50) -> dict[str, str]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = run_voice_agent_stress_test(call_count=call_count)
    summary_path = out_dir / "voice_agent_stress_summary.json"
    report_path = out_dir / "voice_agent_stress_report.md"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    report_lines = [
        "# Voice Agent Stress Report",
        "",
        f"- Calls simulated: {summary['calls_simulated']}",
        f"- Passed calls: {summary['passed_calls']}",
        f"- PTP extraction accuracy: {summary['ptp_extraction_accuracy']}",
        f"- Intent classification accuracy: {summary['intent_classification_accuracy']}",
        f"- Average scenario latency (ms): {summary['average_latency_ms']}",
        f"- Loop occurrences: {summary['loop_occurrences']}",
        "",
    ]
    report_path.write_text("\n".join(report_lines), encoding="utf-8")
    return {"summary": str(summary_path), "report": str(report_path)}


if __name__ == "__main__":
    artifacts = write_voice_agent_stress_artifacts(Path(__file__).resolve().parent, call_count=50)
    print(json.dumps(artifacts, ensure_ascii=False))
