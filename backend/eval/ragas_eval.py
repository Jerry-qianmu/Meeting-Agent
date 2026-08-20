# -*- coding: utf-8 -*-
"""
DeepEval 评估脚本（逐条评估 + 即时保存 + 断点续跑）
"""
import json
import re
import argparse
import logging
import requests
from typing import List, Dict

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def load_dataset(path: str) -> List[Dict]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else data.get("data", [])


def call_rag(query: str, kb_id: str, api_base: str) -> Dict:
    try:
        resp = requests.post(
            f"{api_base}/api/v1/agent/chat",
            json={"session_id": "deepeval_eval", "query": query, "knowledge_base_ids": [kb_id], "web_search_enabled": False},
            timeout=180,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"API 错误: {e}")
        return {}


def get_answer(result: Dict) -> str:
    return result.get("answer", "")


def get_contexts(result: Dict) -> List[str]:
    context_blocks = result.get("context_blocks", [])
    if context_blocks:
        contexts = []
        for block in context_blocks:
            text = block.get("text", "")
            text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL).strip()
            if text:
                contexts.append(text)
        if contexts:
            return contexts
    sources = result.get("sources", [])
    contexts = []
    for s in sources:
        content = s.get("preview", s.get("content", ""))
        content = re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL).strip()
        if content:
            contexts.append(content)
    return contexts


def get_retrieval_scores(result: Dict) -> List[float]:
    context_blocks = result.get("context_blocks", [])
    if context_blocks:
        return [b.get("score", 0.0) for b in context_blocks]
    sources = result.get("sources", [])
    return [s.get("score", 0.0) for s in sources]


def setup_judge_env(base_url: str, api_key: str, model: str):
    import os
    os.environ["OPENAI_API_KEY"] = api_key
    os.environ["OPENAI_API_BASE"] = base_url
    os.environ["OPENAI_BASE_URL"] = base_url
    os.environ["DEEPEVAL_TELEMETRY_OPT_OUT"] = "1"
    return model


def evaluate_single(question: str, answer: str, contexts: List[str], ground_truth: str, model_name: str) -> Dict:
    from deepeval.test_case import LLMTestCase
    from deepeval.metrics import FaithfulnessMetric, AnswerRelevancyMetric, ContextualPrecisionMetric, ContextualRecallMetric

    tc = LLMTestCase(input=question, actual_output=answer, retrieval_context=contexts, expected_output=ground_truth)
    metrics = [
        FaithfulnessMetric(model=model_name, async_mode=False),
        AnswerRelevancyMetric(model=model_name, async_mode=False),
        ContextualPrecisionMetric(model=model_name, async_mode=False),
        ContextualRecallMetric(model=model_name, async_mode=False),
    ]
    scores = {}
    for metric in metrics:
        try:
            metric.measure(tc)
            scores[metric.__class__.__name__] = {"score": round(metric.score, 4), "success": metric.is_successful()}
        except Exception as e:
            scores[metric.__class__.__name__] = {"score": None, "success": False, "error": str(e)}
    return scores


def load_progress(output_path: str) -> dict:
    try:
        with open(output_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"completed": [], "results": []}


def save_progress(output_path: str, progress: dict):
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description="DeepEval RAG 评估（逐条评估，即时保存）")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--kb-id", required=True)
    parser.add_argument("--api-base", default="http://localhost:8000")
    parser.add_argument("--output", default="eval_results.json", help="支持断点续跑")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--judge-base-url", default="https://api.deepseek.com")
    parser.add_argument("--judge-api-key", default="sk-79a1a4802a184dd9b6451a8fbe8b9651")
    parser.add_argument("--judge-model", default="deepseek-v4-flash")
    args = parser.parse_args()

    if args.judge_api_key:
        model_name = setup_judge_env(args.judge_base_url, args.judge_api_key, args.judge_model)
    else:
        model_name = args.judge_model

    dataset = load_dataset(args.dataset)
    progress = load_progress(args.output)
    completed_questions = set(progress.get("completed", []))
    results = progress.get("results", [])

    logger.info(f"数据集: {len(dataset)} 条, 已完成: {len(completed_questions)} 条, 剩余: {len(dataset) - len(completed_questions)} 条")

    for i, item in enumerate(dataset):
        query = item.get("question", "")
        if query in completed_questions:
            logger.info(f"[{i+1}/{len(dataset)}] 已完成，跳过")
            continue

        gt_answer = item.get("answer", "")
        gt_passages = [p.get("content", "") for p in item.get("passages", []) if p.get("content")]
        ground_truth = gt_answer if gt_answer else "\n".join(gt_passages)
        if not query or not ground_truth:
            continue

        logger.info(f"[{i+1}/{len(dataset)}] {query[:60]}...")

        result = call_rag(query, args.kb_id, args.api_base)
        if not result:
            continue

        answer = get_answer(result)
        contexts = get_contexts(result)
        if not answer or not contexts:
            logger.info("  ⚠ 回答或上下文为空，跳过")
            continue

        logger.info(f"  检索到 {len(contexts)} 个 chunk")

        if args.verbose:
            print(f"\n{'='*60}\nQ: {query}\nA: {answer[:200]}...\nGT: {ground_truth[:200]}...\n{'='*60}")

        try:
            eval_scores = evaluate_single(query, answer, contexts, ground_truth, model_name)
            for k, v in eval_scores.items():
                logger.info(f"  {k}: {v.get('score', 'N/A')}")
        except Exception as e:
            logger.error(f"  评估失败: {e}")
            eval_scores = {"error": str(e)}

        results.append({"question": query, "answer": answer, "ground_truth": ground_truth, "context_count": len(contexts), "eval_scores": eval_scores})
        completed_questions.add(query)
        progress["completed"] = list(completed_questions)
        progress["results"] = results
        save_progress(args.output, progress)
        logger.info(f"  ✓ 已保存 ({len(completed_questions)}/{len(dataset)})")

    # 汇总
    print(f"\n{'='*60}\n  评估完成: {len(results)}/{len(dataset)} 条\n{'='*60}")
    for name in ["FaithfulnessMetric", "AnswerRelevancyMetric", "ContextualPrecisionMetric", "ContextualRecallMetric"]:
        vals = [r["eval_scores"][name]["score"] for r in results if isinstance(r.get("eval_scores"), dict) and name in r["eval_scores"] and r["eval_scores"][name].get("score") is not None]
        if vals:
            print(f"  {name}: {sum(vals)/len(vals):.4f}")
    print(f"\n  详细结果: {args.output}\n{'='*60}")


if __name__ == "__main__":
    main()
