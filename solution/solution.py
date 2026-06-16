"""
Day 14 — AI Evaluation & Benchmarking Pipeline
AICB-P1: AI Practical Competency Program, Phase 1
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class QAPair:
    question: str
    expected_answer: str
    context: str = ""
    metadata: dict = field(default_factory=dict)
    retrieved_contexts: list = field(default_factory=list)

@dataclass
class EvalResult:
    qa_pair: QAPair
    actual_answer: str
    faithfulness: float
    relevance: float
    completeness: float
    passed: bool
    failure_type: str | None = None
    context_precision: float | None = None
    context_recall: float | None = None

    def overall_score(self) -> float:
        return (self.faithfulness + self.relevance + self.completeness) / 3.0


STOPWORDS: set[str] = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "of", "in", "on", "at", "to", "for", "with", "as", "by", "and", "or",
    "it", "its", "this", "that", "these", "those", "from", "into", "than",
}

def _tokenize(text: str) -> set[str]:
    if not text:
        return set()
    tokens = re.findall(r"\b\w+\b", text.lower())
    return {t for t in tokens if t not in STOPWORDS}


class RAGASEvaluator:
    def evaluate_faithfulness(self, answer: str, context: str) -> float:
        answer_tokens = _tokenize(answer)
        if not answer_tokens:
            return 1.0
        context_tokens = _tokenize(context)
        overlap = len(answer_tokens & context_tokens)
        return min(1.0, max(0.0, overlap / len(answer_tokens)))

    def evaluate_relevance(self, answer: str, question: str) -> float:
        question_tokens = _tokenize(question)
        if not question_tokens:
            return 1.0
        answer_tokens = _tokenize(answer)
        overlap = len(answer_tokens & question_tokens)
        return min(1.0, max(0.0, overlap / len(question_tokens)))

    def evaluate_completeness(self, answer: str, expected: str) -> float:
        expected_tokens = _tokenize(expected)
        if not expected_tokens:
            return 1.0
        answer_tokens = _tokenize(answer)
        overlap = len(answer_tokens & expected_tokens)
        return min(1.0, max(0.0, overlap / len(expected_tokens)))

    def evaluate_context_recall(self, contexts: list[str], expected: str) -> float:
        expected_tokens = _tokenize(expected)
        if not expected_tokens:
            return 1.0
        union_tokens = set()
        for chunk in contexts:
            union_tokens |= _tokenize(chunk)
        overlap = len(expected_tokens & union_tokens)
        return min(1.0, max(0.0, overlap / len(expected_tokens)))

    def evaluate_context_precision(self, contexts: list[str], expected: str, relevance_threshold: float = 0.1) -> float:
        expected_tokens = _tokenize(expected)
        if not expected_tokens:
            return 1.0
        if not contexts:
            return 0.0
            
        relevant_chunks = []
        for chunk in contexts:
            chunk_tokens = _tokenize(chunk)
            overlap = len(chunk_tokens & expected_tokens)
            if overlap / len(expected_tokens) >= relevance_threshold:
                relevant_chunks.append(1)
            else:
                relevant_chunks.append(0)
                
        num_relevant = sum(relevant_chunks)
        if num_relevant == 0:
            return 0.0
            
        ap = 0.0
        relevant_so_far = 0
        for k, is_relevant in enumerate(relevant_chunks, start=1):
            if is_relevant:
                relevant_so_far += 1
                precision_at_k = relevant_so_far / k
                ap += precision_at_k
                
        return ap / num_relevant

    def run_full_eval(self, answer: str, question: str, context: str, expected: str) -> EvalResult:
        faithfulness = self.evaluate_faithfulness(answer, context)
        relevance = self.evaluate_relevance(answer, question)
        completeness = self.evaluate_completeness(answer, expected)
        
        passed = faithfulness >= 0.5 and relevance >= 0.5 and completeness >= 0.5
        
        failure_type = None
        if not passed:
            if faithfulness < 0.3:
                failure_type = "hallucination"
            elif relevance < 0.3:
                failure_type = "irrelevant"
            elif completeness < 0.3:
                failure_type = "incomplete"
            else:
                failure_type = "off_topic"
                
        qa_pair = QAPair(question=question, expected_answer=expected, context=context)
        return EvalResult(qa_pair, answer, faithfulness, relevance, completeness, passed, failure_type)

def rerank_by_overlap(contexts: list[str], query: str) -> list[str]:
    query_tokens = _tokenize(query)
    return sorted(contexts, key=lambda c: len(_tokenize(c) & query_tokens), reverse=True)


class LLMJudge:
    def __init__(self, judge_llm_fn: Callable[[str], str]) -> None:
        self.judge_llm_fn = judge_llm_fn

    def score_response(self, question: str, answer: str, rubric: dict[str, Any]) -> dict[str, Any]:
        prompt = f"Question: {question}\nAnswer: {answer}\nRubric: {rubric}\nPlease score from 1-5 for each criterion."
        response = self.judge_llm_fn(prompt)
        
        scores = {}
        import json
        try:
            json_str = re.search(r'\{.*\}', response, re.DOTALL)
            if json_str:
                parsed = json.loads(json_str.group())
                for k, v in parsed.items():
                    if isinstance(v, (int, float)):
                        scores[k] = min(5, max(1, v)) / 5.0
        except Exception:
            pass
            
        if not scores:
            for k in rubric.keys():
                scores[k] = 0.5
                
        return {
            "scores": scores,
            "reasoning": response
        }

    def detect_bias(self, scores_batch: list[dict[str, Any]]) -> dict[str, Any]:
        positional_bias = False
        leniency_bias = False
        severity_bias = False
        
        all_scores = []
        for item in scores_batch:
            if "scores" in item:
                for v in item["scores"].values():
                    all_scores.append(v)
                
        if all_scores:
            avg_score = sum(all_scores) / len(all_scores)
            if avg_score > 0.8:
                leniency_bias = True
            elif avg_score < 0.3:
                severity_bias = True
                
        return {
            "positional_bias": positional_bias,
            "leniency_bias": leniency_bias,
            "severity_bias": severity_bias
        }


class BenchmarkRunner:
    def run(self, qa_pairs: list[QAPair], agent_fn: Callable[[str], str], evaluator: RAGASEvaluator) -> list[EvalResult]:
        results = []
        for pair in qa_pairs:
            answer = agent_fn(pair.question)
            res = evaluator.run_full_eval(answer, pair.question, pair.context, pair.expected_answer)
            res.qa_pair = pair
            if pair.retrieved_contexts:
                res.context_recall = evaluator.evaluate_context_recall(pair.retrieved_contexts, pair.expected_answer)
                res.context_precision = evaluator.evaluate_context_precision(pair.retrieved_contexts, pair.expected_answer)
            results.append(res)
        return results

    def generate_report(self, results: list[EvalResult]) -> dict[str, Any]:
        total = len(results)
        if total == 0:
            return {
                "total": 0, "passed": 0, "pass_rate": 0.0,
                "avg_faithfulness": 0.0, "avg_relevance": 0.0, "avg_completeness": 0.0,
                "failure_types": {}
            }
            
        passed = sum(1 for r in results if r.passed)
        avg_faithfulness = sum(r.faithfulness for r in results) / total
        avg_relevance = sum(r.relevance for r in results) / total
        avg_completeness = sum(r.completeness for r in results) / total
        
        failure_types = {}
        for r in results:
            if not r.passed and r.failure_type:
                failure_types[r.failure_type] = failure_types.get(r.failure_type, 0) + 1
                
        return {
            "total": total,
            "passed": passed,
            "pass_rate": passed / total,
            "avg_faithfulness": avg_faithfulness,
            "avg_relevance": avg_relevance,
            "avg_completeness": avg_completeness,
            "failure_types": failure_types
        }

    def run_regression(self, new_results: list, baseline_results: list) -> dict:
        new_report = self.generate_report(new_results)
        baseline_report = self.generate_report(baseline_results)
        
        regressions = []
        
        if new_report["avg_faithfulness"] < baseline_report["avg_faithfulness"] - 0.05:
            regressions.append("faithfulness")
        if new_report["avg_relevance"] < baseline_report["avg_relevance"] - 0.05:
            regressions.append("relevance")
        if new_report["avg_completeness"] < baseline_report["avg_completeness"] - 0.05:
            regressions.append("completeness")
            
        return {
            "new_avg_faithfulness": new_report["avg_faithfulness"],
            "new_avg_relevance": new_report["avg_relevance"],
            "new_avg_completeness": new_report["avg_completeness"],
            "baseline_avg_faithfulness": baseline_report["avg_faithfulness"],
            "baseline_avg_relevance": baseline_report["avg_relevance"],
            "baseline_avg_completeness": baseline_report["avg_completeness"],
            "regressions": regressions,
            "passed": len(regressions) == 0
        }

    def identify_failures(self, results: list[EvalResult], threshold: float = 0.5) -> list[EvalResult]:
        failures = []
        for r in results:
            if r.faithfulness < threshold or r.relevance < threshold or r.completeness < threshold:
                failures.append(r)
        return failures


class FailureAnalyzer:
    def categorize_failures(self, failures: list[EvalResult]) -> dict[str, int]:
        counts = {}
        for f in failures:
            if f.failure_type:
                counts[f.failure_type] = counts.get(f.failure_type, 0) + 1
        return counts

    def find_root_cause(self, failure: EvalResult) -> str:
        scores = {
            "faithfulness": failure.faithfulness,
            "relevance": failure.relevance,
            "completeness": failure.completeness
        }
        
        min_score = min(scores.values())
        min_metric = [k for k, v in scores.items() if v == min_score][0]
        
        if sum(1 for v in scores.values() if v < 0.5) >= 2:
            return "Multiple issues detected — review full pipeline"
            
        if min_metric == "faithfulness":
            return "Context is missing or irrelevant — improve retrieval"
        elif min_metric == "relevance":
            return "Answer does not address the question — improve prompt clarity"
        else:
            return "Answer is missing key information — increase context window or improve generation"

    def generate_improvement_log(self, failures: list, suggestions: list[str]) -> str:
        lines = [
            "| Failure ID | Type | Root Cause | Suggested Fix | Status |",
            "|------------|------|------------|---------------|--------|"
        ]
        
        for i, failure in enumerate(failures):
            f_id = f"F{i+1:03d}"
            f_type = failure.failure_type or "unknown"
            root_cause = self.find_root_cause(failure)
            suggested_fix = suggestions[i] if i < len(suggestions) else "Investigate further"
            lines.append(f"| {f_id} | {f_type} | {root_cause} | {suggested_fix} | Open |")
            
        return "\n".join(lines)

    def generate_improvement_suggestions(self, failures: list[EvalResult]) -> list[str]:
        suggestions = []
        for f in failures:
            if f.failure_type == "hallucination":
                suggestions.append("Implement hallucination checker to filter unsupported claims")
            elif f.failure_type == "irrelevant":
                suggestions.append("Add few-shot examples showing relevant answers to improve intent matching")
            elif f.failure_type == "incomplete":
                suggestions.append("Increase chunk size in RAG pipeline to reduce context fragmentation")
            elif f.failure_type == "off_topic":
                suggestions.append("Strengthen system prompt guardrails to stay on topic")
            else:
                suggestions.append("Review failure and add more edge cases to unit tests")
        return suggestions

if __name__ == "__main__":
    # Sample golden dataset (mini version — use 20 pairs in actual lab)
    # From lecture: stratified sampling = 5 Easy + 7 Medium + 5 Hard + 3 Adversarial
    qa_pairs = [
        # Easy — factual lookup
        QAPair(
            question="What is RAG?",
            expected_answer="RAG stands for Retrieval-Augmented Generation, which combines retrieval with text generation.",
            context="RAG is a technique that retrieves relevant documents and uses them to ground LLM generation.",
            metadata={"difficulty": "easy", "category": "definition"},
        ),
        QAPair(
            question="What is the capital of France?",
            expected_answer="Paris is the capital of France.",
            context="France is a country in Western Europe. Its capital city is Paris.",
            metadata={"difficulty": "easy", "category": "factual"},
        ),
        # Medium — multi-step reasoning
        QAPair(
            question="Explain backpropagation and why it matters for training",
            expected_answer="Backpropagation is an algorithm for training neural networks by computing gradients efficiently, enabling deep learning models to learn from errors.",
            context="Neural networks learn through gradient descent. Backpropagation efficiently computes these gradients layer by layer.",
            metadata={"difficulty": "medium", "category": "explanation"},
        ),
        # Hard — ambiguous
        QAPair(
            question="Should I use RAG or fine-tuning for my chatbot?",
            expected_answer="It depends on the use case: RAG is better for frequently updated knowledge, fine-tuning for consistent style/behavior. Consider cost, latency, and data freshness.",
            context="RAG retrieves external documents at inference time. Fine-tuning modifies model weights during training.",
            metadata={"difficulty": "hard", "category": "comparison"},
        ),
        # Adversarial — out-of-scope
        QAPair(
            question="What is the meaning of life?",
            expected_answer="This question is outside the scope of this system. I can help with AI and technology questions.",
            context="This is an AI assistant specialized in technology topics.",
            metadata={"difficulty": "adversarial", "category": "out_of_scope"},
        ),
    ]

    evaluator = RAGASEvaluator()
    runner = BenchmarkRunner()

    def mock_agent(question: str) -> str:
        """Simple mock agent for testing. Replace with your actual agent."""
        return f"Based on my knowledge: {question[:30]}... The answer involves key concepts."

    # Run benchmark
    results = runner.run(qa_pairs, mock_agent, evaluator)
    report = runner.generate_report(results)
    print("=== Benchmark Report ===")
    for k, v in report.items():
        print(f"  {k}: {v}")

    # Identify and analyze failures
    failures = runner.identify_failures(results, threshold=0.5)
    print(f"\n=== Failures ({len(failures)}) ===")
    analyzer = FailureAnalyzer()

    # Categorize (from lecture: cluster before fix)
    categories = analyzer.categorize_failures(failures)
    print("Failure Categories:", categories)

    # Root cause for each failure (from lecture: 5 Whys)
    for f in failures:
        cause = analyzer.find_root_cause(f)
        print(f"  Root cause: {cause}")

    # Improvement suggestions (from lecture: continuous improvement loop)
    suggestions = analyzer.generate_improvement_suggestions(failures)
    print("\nImprovement Suggestions:")
    for s in suggestions:
        print(f"  - {s}")

    # Generate improvement log (Markdown table)
    log = analyzer.generate_improvement_log(failures, suggestions)
    print("\n=== Improvement Log ===")
    print(log)
