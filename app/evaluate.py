from __future__ import annotations

import argparse
import json
import math
import os
import re
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from app.config import DATA_DIR, GEMINI_API_KEY, GEMINI_MODEL
from app.multimodal import multimodal_artifacts
from app.rag import answer_question
from app.retriever import hybrid_retrieve


EVAL_CASES_PATH = DATA_DIR / "evaluation" / "eval_cases.json"
EVAL_REPORT_DIR = DATA_DIR / "evaluation" / "reports"
SUGGESTED_QUESTIONS_PATH = DATA_DIR / "processed" / "q&a.json"
TICKER_PATTERN = re.compile(r"\b[A-Z]{2,5}\b")
NUMBER_PATTERN = re.compile(r"[-+]?\d+(?:[.,]\d+)*(?:%|x)?")
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "cho",
    "co",
    "cua",
    "da",
    "duoc",
    "gi",
    "hay",
    "khi",
    "khong",
    "la",
    "mot",
    "neu",
    "nhung",
    "noi",
    "nua",
    "or",
    "tai",
    "the",
    "thi",
    "this",
    "to",
    "tren",
    "tu",
    "va",
    "ve",
    "voi",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate retrieval, generation and performance.")
    parser.add_argument("--cases", default=str(EVAL_CASES_PATH), help="Path to evaluation cases JSON.")
    parser.add_argument("--top-k", type=int, default=5, help="Top-k retrieval cutoff.")
    parser.add_argument(
        "--repeats",
        type=int,
        default=3,
        help="Number of repeated runs for latency measurements.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(EVAL_REPORT_DIR),
        help="Directory to write JSON and Markdown reports.",
    )
    parser.add_argument(
        "--eval-model",
        default=None,
        help="Optional DeepEval model name. Defaults to GEMINI_MODEL when GEMINI_API_KEY is set.",
    )
    parser.add_argument(
        "--deepeval-threshold",
        type=float,
        default=0.5,
        help="Passing threshold for DeepEval metrics.",
    )
    parser.add_argument(
        "--include-reason",
        action="store_true",
        help="Include DeepEval metric reasons in the JSON/Markdown reports.",
    )
    return parser.parse_args()


def normalize_text(text: str) -> str:
    return " ".join(str(text).lower().replace("\n", " ").split())


def tokenize(text: str) -> list[str]:
    cleaned = []
    current = []
    for char in normalize_text(text):
        if char.isalnum():
            current.append(char)
        else:
            if current:
                cleaned.append("".join(current))
                current = []
    if current:
        cleaned.append("".join(current))
    return cleaned


def informative_tokens(text: str) -> list[str]:
    return [token for token in tokenize(text) if len(token) > 2 and token not in STOPWORDS]


def token_set(text: str) -> set[str]:
    return set(informative_tokens(text))


def overlap_score(candidate: str, reference: str) -> float:
    reference_tokens = token_set(reference)
    if not reference_tokens:
        return 0.0
    candidate_tokens = token_set(candidate)
    return len(candidate_tokens & reference_tokens) / len(reference_tokens)


def mean_or_zero(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(statistics.mean(values), 3)


def numeric_values(results: list[dict], key: str) -> list[float]:
    values = []
    for result in results:
        value = result.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            values.append(float(value))
    return values


def preview(text: str, limit: int = 180) -> str:
    compact = " ".join(str(text).split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = pct * (len(ordered) - 1)
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[lower]
    fraction = rank - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def latency_summary(latencies_ms: list[float]) -> dict:
    if not latencies_ms:
        return {"count": 0, "avg_ms": 0.0, "p95_ms": 0.0, "min_ms": 0.0, "max_ms": 0.0}
    return {
        "count": len(latencies_ms),
        "avg_ms": round(statistics.mean(latencies_ms), 2),
        "p95_ms": round(percentile(latencies_ms, 0.95), 2),
        "min_ms": round(min(latencies_ms), 2),
        "max_ms": round(max(latencies_ms), 2),
    }


def infer_case_ticker(question: str) -> str | None:
    for match in TICKER_PATTERN.findall(question.upper()):
        if match in {"HPG", "FPT", "VCB"}:
            return match
    return None


def build_default_eval_cases(limit: int = 9) -> list[dict]:
    payload = {}
    if SUGGESTED_QUESTIONS_PATH.exists():
        payload = json.loads(SUGGESTED_QUESTIONS_PATH.read_text(encoding="utf-8"))

    questions = []
    for group in payload.get("suggested_questions", []):
        if not isinstance(group, dict):
            continue
        for question in group.get("questions", []):
            if isinstance(question, str) and question.strip():
                questions.append(question.strip())

    if not questions:
        questions = [
            "Tom tat nhanh co phieu HPG hien tai",
            "FPT co nhung dong luc tang truong nao?",
            "VCB co diem manh va rui ro gi?",
        ]

    cases = []
    for index, question in enumerate(questions[:limit], start=1):
        cases.append(
            {
                "id": f"auto_{index:03d}",
                "question": question,
                "ticker": infer_case_ticker(question),
                "expected_chunks": [],
                "expected_answer_keywords": [],
                "expected_source_keywords": [],
            }
        )
    return cases


def write_default_eval_cases(path: Path, cases: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "note": (
            "Auto-generated starter cases. Add expected_chunks, expected_answer_keywords "
            "and expected_source_keywords for stricter evaluation."
        ),
        "cases": cases,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_eval_cases(path: Path) -> list[dict]:
    if not path.exists():
        cases = build_default_eval_cases()
        write_default_eval_cases(path, cases)
        print(f"Created starter eval cases: {path.as_posix()}")
        return cases

    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        cases = payload.get("cases", [])
    elif isinstance(payload, list):
        cases = payload
    else:
        cases = []
    return [case for case in cases if isinstance(case, dict)]


def chunk_matches_expectation(chunk, expectation: dict) -> bool:
    source_path = normalize_text(getattr(chunk, "source_path", ""))
    heading_path = normalize_text(" ".join(getattr(chunk, "heading_path", [])))
    text = normalize_text(getattr(chunk, "text", ""))
    modality = normalize_text(getattr(chunk, "modality", ""))
    ticker = normalize_text(getattr(chunk, "ticker", ""))
    scope = normalize_text(getattr(chunk, "scope", "") or getattr(chunk, "ticker", ""))

    if expectation.get("ticker") and ticker != normalize_text(expectation["ticker"]):
        return False
    if expectation.get("scope") and scope != normalize_text(expectation["scope"]):
        return False
    if expectation.get("modality") and modality != normalize_text(expectation["modality"]):
        return False
    if expectation.get("source_path_contains"):
        if normalize_text(expectation["source_path_contains"]) not in source_path:
            return False
    if expectation.get("heading_contains_any"):
        if not any(normalize_text(value) in heading_path for value in expectation["heading_contains_any"]):
            return False
    if expectation.get("text_contains_any"):
        if not any(normalize_text(value) in text for value in expectation["text_contains_any"]):
            return False
    return True


def expected_context_text(case: dict) -> str:
    values = []
    for key in ["expected_output", "expected_answer", "reference_answer"]:
        if case.get(key):
            values.append(str(case[key]))
    values.extend(str(value) for value in case.get("expected_answer_keywords", []))
    values.extend(str(value) for value in case.get("expected_source_keywords", []))
    for expectation in case.get("expected_chunks", []):
        values.extend(str(value) for value in expectation.get("text_contains_any", []))
        values.extend(str(value) for value in expectation.get("heading_contains_any", []))
        if expectation.get("source_path_contains"):
            values.append(str(expectation["source_path_contains"]))
    return " ".join(values)


def chunk_relevance_flags(case: dict, chunks) -> list[bool]:
    expectations = case.get("expected_chunks", [])
    if expectations:
        return [
            any(chunk_matches_expectation(chunk, expectation) for expectation in expectations)
            for chunk in chunks
        ]

    reference = expected_context_text(case) or case["question"]
    return [overlap_score(chunk.text, reference) > 0 for chunk in chunks]


def evaluate_retrieval_case(case: dict, top_k: int) -> dict:
    started_at = time.perf_counter()
    try:
        hits = hybrid_retrieve(case["question"], top_k=top_k, ticker=case.get("ticker"))
        latency_ms = (time.perf_counter() - started_at) * 1000
    except Exception as exc:  # noqa: BLE001
        return {
            "case_id": case["id"],
            "question": case["question"],
            "ticker": case.get("ticker"),
            "latency_ms": round((time.perf_counter() - started_at) * 1000, 2),
            "top_k": top_k,
            "expected_evidence_count": len(case.get("expected_chunks", [])),
            "matched_evidence_count": 0,
            "strict_evaluation": bool(case.get("expected_chunks")),
            "recall_at_k": None,
            "first_relevant_rank": None,
            "mrr": None,
            "qualitative_top_chunks": [],
            "error": str(exc),
        }

    expectations = case.get("expected_chunks", [])
    matched_ranks: list[int] = []
    for expectation in expectations:
        matched_rank = None
        for rank, chunk in enumerate(hits, start=1):
            if chunk_matches_expectation(chunk, expectation):
                matched_rank = rank
                break
        if matched_rank is not None:
            matched_ranks.append(matched_rank)

    expected_count = len(expectations)
    strict_evaluation = expected_count > 0
    first_relevant_rank = min(matched_ranks) if matched_ranks else None
    coverage = (len(matched_ranks) / expected_count) if strict_evaluation else None
    relevance_flags = chunk_relevance_flags(case, hits)
    if strict_evaluation and relevance_flags and first_relevant_rank is None:
        first_relevant_rank = next((rank for rank, flag in enumerate(relevance_flags, start=1) if flag), None)

    return {
        "case_id": case["id"],
        "question": case["question"],
        "ticker": case.get("ticker"),
        "latency_ms": round(latency_ms, 2),
        "top_k": top_k,
        "strict_evaluation": strict_evaluation,
        "expected_evidence_count": expected_count,
        "matched_evidence_count": len(matched_ranks),
        "recall_at_k": round(coverage, 3) if coverage is not None else None,
        "first_relevant_rank": first_relevant_rank,
        "mrr": round(1 / first_relevant_rank, 4) if first_relevant_rank else None,
        "qualitative_top_chunks": [
            {
                "rank": rank,
                "score": round(chunk.score, 4),
                "ticker": chunk.ticker,
                "scope": chunk.scope,
                "modality": chunk.modality,
                "source_path": chunk.source_path,
                "heading_path": chunk.heading_path,
                "preview": preview(chunk.text),
            }
            for rank, chunk in enumerate(hits[: min(3, len(hits))], start=1)
        ],
    }


def source_keyword_match_score(sources: list[dict], expected_keywords: list[str]) -> float:
    if not expected_keywords:
        return 1.0
    haystack = normalize_text(
        " ".join(
            f"{source.get('source_path', '')} {source.get('artifact_path', '')} {source.get('url', '')}"
            for source in sources
        )
    )
    hits = sum(1 for keyword in expected_keywords if normalize_text(keyword) in haystack)
    return hits / len(expected_keywords)


def context_grounding_score(answer: str, retrieved_chunks) -> float:
    answer_tokens = informative_tokens(answer)
    if not answer_tokens:
        return 0.0
    context_tokens: set[str] = set()
    for chunk in retrieved_chunks:
        context_tokens.update(informative_tokens(chunk.text))
    if not context_tokens:
        return 0.0
    shared = sum(1 for token in answer_tokens if token in context_tokens)
    return shared / len(answer_tokens)


def lexical_answer_relevancy_score(question: str, answer: str) -> float:
    question_tokens = token_set(question)
    answer_tokens = token_set(answer)
    if not question_tokens:
        return 0.0
    return len(question_tokens & answer_tokens) / len(question_tokens)


def extract_numbers(text: str) -> list[float]:
    values = []
    for raw_value in NUMBER_PATTERN.findall(text):
        parsed = parse_number_token(raw_value)
        if parsed is None:
            continue
        values.append(parsed)
    return values


def parse_number_token(raw_value: str) -> float | None:
    value = raw_value.strip().rstrip("%xX")
    if not value:
        return None

    sign = ""
    if value[0] in {"+", "-"}:
        sign, value = value[0], value[1:]

    if "," in value and "." in value:
        last_comma = value.rfind(",")
        last_dot = value.rfind(".")
        if last_comma > last_dot:
            normalized = value.replace(".", "").replace(",", ".")
        else:
            normalized = value.replace(",", "")
    elif "," in value:
        parts = value.split(",")
        if len(parts) > 2 or len(parts[-1]) == 3:
            normalized = "".join(parts)
        else:
            normalized = value.replace(",", ".")
    elif "." in value:
        parts = value.split(".")
        if len(parts) > 2:
            normalized = "".join(parts)
        elif len(parts[-1]) == 3 and len(parts[0]) > 2:
            normalized = "".join(parts)
        else:
            normalized = value
    else:
        normalized = value

    try:
        return float(f"{sign}{normalized}")
    except ValueError:
        return None


def numerical_accuracy_score(answer: str, case: dict) -> float | None:
    expected_numbers = case.get("expected_numbers")
    if expected_numbers is None:
        return None
    else:
        expected_numbers = [float(value) for value in expected_numbers]
    if not expected_numbers:
        return None

    answer_numbers = extract_numbers(answer)
    if not answer_numbers:
        return 0.0

    matched = 0
    remaining = answer_numbers[:]
    for expected in expected_numbers:
        tolerance = max(abs(expected) * 0.01, 0.01)
        match_index = next(
            (index for index, actual in enumerate(remaining) if math.isclose(actual, expected, abs_tol=tolerance)),
            None,
        )
        if match_index is not None:
            matched += 1
            remaining.pop(match_index)
    return matched / len(expected_numbers)


def citation_accuracy_score(sources: list[dict], case: dict) -> float | None:
    expected_keywords = case.get("expected_source_keywords", [])
    if expected_keywords:
        return source_keyword_match_score(sources, expected_keywords)

    expectations = case.get("expected_chunks", [])
    if not expectations:
        return None

    matched = 0
    for expectation in expectations:
        expected_path = normalize_text(expectation.get("source_path_contains", ""))
        expected_text = normalize_text(expectation.get("text_contains", ""))
        for source in sources:
            source_text = normalize_text(
                " ".join(
                    str(source.get(key, ""))
                    for key in ["source_path", "artifact_path", "url", "title", "structure_type"]
                )
            )
            if expected_path and expected_path in source_text:
                matched += 1
                break
            if expected_text and expected_text in source_text:
                matched += 1
                break
    return matched / len(expectations)


def evaluate_generation_case(case: dict, top_k: int) -> dict:
    started_at = time.perf_counter()
    try:
        result = answer_question(case["question"], ticker=case.get("ticker"), top_k=top_k)
        latency_ms = (time.perf_counter() - started_at) * 1000
    except Exception as exc:  # noqa: BLE001
        return {
            "case_id": case["id"],
            "question": case["question"],
            "ticker": case.get("ticker"),
            "latency_ms": round((time.perf_counter() - started_at) * 1000, 2),
            "source_count": 0,
            "numerical_accuracy": None,
            "citation_accuracy": None,
            "has_sources": False,
            "answer_preview": "",
            "source_preview": [],
            "error": str(exc),
        }

    answer = str(result.get("answer", ""))
    sources = list(result.get("sources", []))
    numerical_accuracy = numerical_accuracy_score(answer, case)
    citation_accuracy = citation_accuracy_score(sources, case)
    fallback_metrics = {}
    if not case.get("expected_numbers") and not extract_numbers(expected_output_for_deepeval(case)):
        fallback_metrics["numerical_accuracy"] = "no_expected_numbers"
    if not case.get("expected_source_keywords") and not case.get("expected_chunks"):
        fallback_metrics["citation_accuracy"] = "sources_present_without_expected_citations"

    return {
        "case_id": case["id"],
        "question": case["question"],
        "ticker": case.get("ticker"),
        "latency_ms": round(latency_ms, 2),
        "source_count": len(sources),
        "numerical_accuracy": round(numerical_accuracy, 3) if numerical_accuracy is not None else None,
        "citation_accuracy": round(citation_accuracy, 3) if citation_accuracy is not None else None,
        "fallback_metrics": fallback_metrics,
        "has_sources": bool(sources),
        "answer": answer,
        "answer_preview": preview(answer, limit=260),
        "source_preview": [
            {
                "ticker": source.get("ticker"),
                "modality": source.get("modality"),
                "structure_type": source.get("structure_type"),
                "source_path": source.get("source_path"),
                "url": source.get("url"),
            }
            for source in sources[:3]
        ],
    }


def expected_output_for_deepeval(case: dict) -> str:
    return str(
        case.get("expected_output")
        or case.get("expected_answer")
        or case.get("reference_answer")
        or expected_context_text(case)
        or ""
    )


def deepeval_metric_kwargs(eval_model: str | None, threshold: float, include_reason: bool) -> dict:
    kwargs = {
        "threshold": threshold,
        "include_reason": include_reason,
    }
    if eval_model and not eval_model.lower().startswith("gemini"):
        kwargs["model"] = eval_model
    elif GEMINI_API_KEY:
        from deepeval.models.llms.gemini_model import GeminiModel

        kwargs["model"] = GeminiModel(
            model=eval_model or GEMINI_MODEL,
            api_key=GEMINI_API_KEY or None,
            temperature=0,
        )
    return kwargs


def effective_eval_model(eval_model: str | None) -> str | None:
    if eval_model:
        return eval_model
    if GEMINI_API_KEY:
        return GEMINI_MODEL
    return None


def measure_deepeval_metric(metric, test_case) -> dict:
    metric.measure(test_case)
    return {
        "score": round(float(getattr(metric, "score", 0.0) or 0.0), 3),
        "reason": getattr(metric, "reason", None),
        "success": bool(getattr(metric, "success", False)),
    }


def apply_deepeval_generation_scores(
    case: dict,
    result: dict,
    chunks,
    answer: str,
    eval_model: str | None,
    threshold: float,
    include_reason: bool,
) -> dict:
    try:
        from deepeval.metrics import AnswerRelevancyMetric, FaithfulnessMetric
        from deepeval.test_case import LLMTestCase
    except ImportError as exc:
        result["deepeval_error"] = (
            "DeepEval is not installed. Install the optional dependency with "
            "`pip install deepeval` before running evaluation."
        )
        result["deepeval_import_error"] = str(exc)
        return result

    retrieval_context = [chunk.text for chunk in chunks]
    test_case_kwargs = {
        "input": case["question"],
        "actual_output": answer,
        "retrieval_context": retrieval_context,
    }
    expected_output = expected_output_for_deepeval(case)
    if expected_output:
        test_case_kwargs["expected_output"] = expected_output
    test_case = LLMTestCase(**test_case_kwargs)
    metric_kwargs = deepeval_metric_kwargs(eval_model, threshold, include_reason)
    scores = {}

    for key, metric_cls in [
        ("answer_relevancy", AnswerRelevancyMetric),
        ("faithfulness", FaithfulnessMetric),
    ]:
        try:
            scores[key] = measure_deepeval_metric(metric_cls(**metric_kwargs), test_case)
            result[key] = scores[key]["score"]
            result.get("fallback_metrics", {}).pop(key, None)
        except Exception as exc:  # noqa: BLE001
            scores[key] = {"error": str(exc)}

    result["deepeval"] = scores
    return result


def evaluate_generation_case_with_deepeval(
    case: dict,
    top_k: int,
    eval_model: str | None,
    threshold: float,
    include_reason: bool,
) -> dict:
    result = evaluate_generation_case(case, top_k)
    if result.get("error"):
        return result

    try:
        retrieval_chunks = hybrid_retrieve(case["question"], top_k=top_k, ticker=case.get("ticker"))
    except Exception as exc:  # noqa: BLE001
        result["deepeval_error"] = str(exc)
        return result

    fallback_scores = {
        "faithfulness": round(context_grounding_score(str(result.get("answer", "")), retrieval_chunks), 3),
        "answer_relevancy": round(
            lexical_answer_relevancy_score(case["question"], str(result.get("answer", ""))),
            3,
        ),
    }
    result.setdefault("fallback_metrics", {}).update(
        {
            "faithfulness": "lexical_context_grounding",
            "answer_relevancy": "question_answer_token_overlap",
        }
    )

    result = apply_deepeval_generation_scores(
        case,
        result,
        retrieval_chunks,
        str(result.get("answer", "")),
        eval_model,
        threshold,
        include_reason,
    )
    for metric_name, fallback_score in fallback_scores.items():
        if result.get(metric_name) is None:
            result[metric_name] = fallback_score
    return result


def evaluate_multimodal_readiness(cases: list[dict]) -> dict:
    tickers = sorted({str(case.get("ticker", "")).upper() for case in cases if case.get("ticker")})
    inventory = []
    lookup_latencies = []
    for ticker in tickers:
        started_at = time.perf_counter()
        artifacts = multimodal_artifacts(ticker)
        lookup_latencies.append((time.perf_counter() - started_at) * 1000)
        inventory.append(
            {
                "ticker": ticker,
                "has_chart": bool(artifacts["chart"]),
                "table_count": len(artifacts["tables"]),
                "pdf_count": len(artifacts["pdfs"]),
            }
        )

    ready_all_three = sum(
        1
        for item in inventory
        if item["has_chart"] and item["table_count"] > 0 and item["pdf_count"] > 0
    )
    return {
        "tickers_evaluated": tickers,
        "inventory": inventory,
        "tickers_with_chart_table_pdf": ready_all_three,
        "artifact_lookup_latency_ms": latency_summary(lookup_latencies),
        "note": (
            "Current system surfaces image/csv/pdf artifacts in UI and sources, "
            "but retrieval is still primarily text+dense/BM25 rather than true multimodal embedding."
        ),
    }


def evaluate_performance(cases: list[dict], top_k: int, repeats: int) -> dict:
    retrieval_latencies = []
    generation_latencies = []
    retrieval_errors: dict[str, int] = {}
    generation_errors: dict[str, int] = {}
    per_case = []

    for case in cases:
        case_retrieval_latencies = []
        case_generation_latencies = []
        for _ in range(repeats):
            try:
                retrieval_started_at = time.perf_counter()
                hybrid_retrieve(case["question"], top_k=top_k, ticker=case.get("ticker"))
                case_retrieval_latencies.append((time.perf_counter() - retrieval_started_at) * 1000)
            except Exception as exc:  # noqa: BLE001
                message = str(exc)
                retrieval_errors[message] = retrieval_errors.get(message, 0) + 1

            try:
                generation_started_at = time.perf_counter()
                answer_question(case["question"], ticker=case.get("ticker"), top_k=top_k)
                case_generation_latencies.append((time.perf_counter() - generation_started_at) * 1000)
            except Exception as exc:  # noqa: BLE001
                message = str(exc)
                generation_errors[message] = generation_errors.get(message, 0) + 1

        retrieval_latencies.extend(case_retrieval_latencies)
        generation_latencies.extend(case_generation_latencies)
        per_case.append(
            {
                "case_id": case["id"],
                "question": case["question"],
                "ticker": case.get("ticker"),
                "retrieval_latency_ms": latency_summary(case_retrieval_latencies),
                "generation_latency_ms": latency_summary(case_generation_latencies),
            }
        )

    return {
        "retrieval_latency_ms": latency_summary(retrieval_latencies),
        "generation_latency_ms": latency_summary(generation_latencies),
        "retrieval_failure_count": sum(retrieval_errors.values()),
        "generation_failure_count": sum(generation_errors.values()),
        "retrieval_errors": retrieval_errors,
        "generation_errors": generation_errors,
        "multimodal_readiness": evaluate_multimodal_readiness(cases),
        "per_case": per_case,
    }


def summarize_retrieval(results: list[dict]) -> dict:
    total = len(results)
    error_count = sum(1 for result in results if result.get("error"))
    strict_results = [result for result in results if result.get("strict_evaluation")]
    mrr_values = numeric_values(strict_results, "mrr")
    recall_at_k_values = numeric_values(strict_results, "recall_at_k")
    latencies = [result["latency_ms"] for result in results]
    return {
        "case_count": total,
        "error_count": error_count,
        "strict_case_count": len(strict_results),
        "smoke_case_count": total - len(strict_results),
        "mean_mrr": round(statistics.mean(mrr_values), 3) if mrr_values else None,
        "recall_at_k": mean_or_zero(recall_at_k_values) if recall_at_k_values else None,
        "latency_ms": latency_summary(latencies),
    }


def summarize_generation(results: list[dict]) -> dict:
    total = len(results)
    error_count = sum(1 for result in results if result.get("error"))
    answer_relevancy_values = numeric_values(results, "answer_relevancy")
    faithfulness_values = numeric_values(results, "faithfulness")
    numerical_accuracy_values = numeric_values(results, "numerical_accuracy")
    citation_accuracy_values = numeric_values(results, "citation_accuracy")
    latencies = [result["latency_ms"] for result in results]
    return {
        "case_count": total,
        "error_count": error_count,
        "latency_ms": latency_summary(latencies),
        "faithfulness": mean_or_zero(faithfulness_values) if faithfulness_values else None,
        "answer_relevancy": mean_or_zero(answer_relevancy_values) if answer_relevancy_values else None,
        "numerical_case_count": len(numerical_accuracy_values),
        "numerical_accuracy": mean_or_zero(numerical_accuracy_values) if numerical_accuracy_values else None,
        "citation_case_count": len(citation_accuracy_values),
        "citation_accuracy": mean_or_zero(citation_accuracy_values) if citation_accuracy_values else None,
    }


def build_markdown_report(report: dict) -> str:
    retrieval_summary = report["retrieval"]["summary"]
    generation_summary = report["generation"]["summary"]
    performance_summary = report["performance"]

    lines = [
        "# Danh gia he thong",
        "",
        f"Thoi gian tao bao cao: {report['generated_at_utc']}",
        f"DeepEval model: {report.get('eval_model') or 'N/A'}",
        f"Top-k: {report['top_k']}",
        f"So case: {report['case_count']}",
        "",
        "## 4.x.1 Danh gia Retrieval",
        f"- Strict cases: {retrieval_summary.get('strict_case_count', 0)}",
        f"- Smoke-only cases: {retrieval_summary.get('smoke_case_count', 0)}",
        f"- Mean MRR: {retrieval_summary['mean_mrr']}",
        f"- Recall@{report['top_k']}: {retrieval_summary['recall_at_k']}",
        "",
        "### Qualitative examples",
    ]

    for case in report["retrieval"]["cases"][:3]:
        lines.extend(
            [
                f"- Case `{case['case_id']}`: {case['question']}",
                (
                    f"  strict={case.get('strict_evaluation', False)} "
                    f"mrr={case['mrr']} recall_at_k={case.get('recall_at_k', 'N/A')}"
                ),
            ]
        )
        if case.get("deepeval_error"):
            lines.append(f"  deepeval_error: {preview(case['deepeval_error'], 220)}")
        for chunk in case["qualitative_top_chunks"]:
            lines.append(
                f"  top{chunk['rank']}: {chunk['source_path']} | score={chunk['score']} | {chunk['preview']}"
            )

    lines.extend(
        [
            "",
            "## 4.x.2 Danh gia Generation",
            f"- Faithfulness: {generation_summary.get('faithfulness', 'N/A')}",
            f"- Answer relevancy: {generation_summary.get('answer_relevancy', 'N/A')}",
            f"- Numerical cases: {generation_summary.get('numerical_case_count', 0)}",
            f"- Numerical accuracy: {generation_summary.get('numerical_accuracy', 'N/A')}",
            f"- Citation cases: {generation_summary.get('citation_case_count', 0)}",
            f"- Citation accuracy: {generation_summary.get('citation_accuracy', 'N/A')}",
            "",
            "### Qualitative examples",
        ]
    )

    for case in report["generation"]["cases"][:3]:
        lines.extend(
            [
                (
                    f"- Case `{case['case_id']}`: source_count={case['source_count']} "
                    f"numerical_accuracy={case.get('numerical_accuracy', 'N/A')} "
                    f"citation_accuracy={case.get('citation_accuracy', 'N/A')}"
                ),
                f"  answer: {case['answer_preview']}",
            ]
        )
        lines.append(
            f"  answer_relevancy={case.get('answer_relevancy', 'N/A')} "
            f"faithfulness={case.get('faithfulness', 'N/A')}"
        )
        if case.get("deepeval_error"):
            lines.append(f"  deepeval_error: {preview(case['deepeval_error'], 220)}")
        for metric_name in ["answer_relevancy", "faithfulness"]:
            reason = case.get("deepeval", {}).get(metric_name, {}).get("reason")
            if reason:
                lines.append(f"  {metric_name}_reason: {preview(reason, 220)}")
        for source in case["source_preview"]:
            lines.append(
                f"  source: {source['source_path']} | modality={source['modality']} | ticker={source['ticker']}"
            )

    multimodal = performance_summary["multimodal_readiness"]
    lines.extend(
        [
            "",
            "## 4.x.3 Danh gia hieu nang he thong",
            f"- Retrieval P95 latency (ms): {performance_summary['retrieval_latency_ms']['p95_ms']}",
            f"- Answer P95 latency (ms): {performance_summary['generation_latency_ms']['p95_ms']}",
            f"- Retrieval failures: {performance_summary.get('retrieval_failure_count', 0)}",
            f"- Answer failures: {performance_summary.get('generation_failure_count', 0)}",
            f"- Tickers co du chart + table + pdf: {multimodal['tickers_with_chart_table_pdf']}",
            f"- Artifact lookup latency avg/p95 (ms): {multimodal['artifact_lookup_latency_ms']['avg_ms']} / {multimodal['artifact_lookup_latency_ms']['p95_ms']}",
            f"- Ghi chu multimodal: {multimodal['note']}",
            "",
            "### Multimodal inventory",
        ]
    )

    for item in multimodal["inventory"]:
        lines.append(
            f"- {item['ticker']}: chart={item['has_chart']} tables={item['table_count']} pdfs={item['pdf_count']}"
        )

    return "\n".join(lines) + "\n"


def ensure_output_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def main() -> int:
    args = parse_args()
    cases_path = Path(args.cases)
    output_dir = Path(args.output_dir)
    ensure_output_dir(output_dir)

    cases = load_eval_cases(cases_path)
    retrieval_cases = [evaluate_retrieval_case(case, args.top_k) for case in cases]
    generation_cases = [
        evaluate_generation_case_with_deepeval(
            case,
            args.top_k,
            args.eval_model,
            args.deepeval_threshold,
            args.include_reason,
        )
        for case in cases
    ]
    performance = evaluate_performance(cases, args.top_k, args.repeats)

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "eval_model": effective_eval_model(args.eval_model),
        "deepeval_threshold": args.deepeval_threshold,
        "top_k": args.top_k,
        "repeats": args.repeats,
        "case_count": len(cases),
        "cases_path": cases_path.as_posix(),
        "retrieval": {
            "summary": summarize_retrieval(retrieval_cases),
            "cases": retrieval_cases,
        },
        "generation": {
            "summary": summarize_generation(generation_cases),
            "cases": generation_cases,
        },
        "performance": performance,
    }

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = output_dir / f"evaluation_report_{timestamp}.json"
    md_path = output_dir / f"evaluation_report_{timestamp}.md"

    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(build_markdown_report(report), encoding="utf-8")

    print(f"Saved JSON report: {json_path.as_posix()}")
    print(f"Saved Markdown report: {md_path.as_posix()}")
    print(json.dumps(report["retrieval"]["summary"], ensure_ascii=False, indent=2))
    print(json.dumps(report["generation"]["summary"], ensure_ascii=False, indent=2))
    print(json.dumps(report["performance"]["retrieval_latency_ms"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
