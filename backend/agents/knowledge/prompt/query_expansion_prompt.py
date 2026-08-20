# 问题扩展模板
EXPANSION_PROMPT = """
You are a search query expansion engine.

Generate alternative search queries for retrieval.

Requirements:
- Preserve original meaning
- Use diverse wording
- Keep queries short
- Avoid duplicates
- Output EXACTLY {n} queries

Also assign each query a type:
- semantic: paraphrase / similar meaning
- keyword: keyword-style / bag-of-words
- intent: intent-specific (e.g., tutorial, definition, comparison)

User intent: {intent}

Original query:
{query}

Output format (STRICT):
1. [semantic] ...
2. [semantic] ...
3. [keyword] ...
4. [intent] ...
5. [intent] ...
"""

# 问题意图识别模板
INTENT_PROMPT = """
Classify the query intent into one of the following categories:
- factual (asking for definition, concept, or explanation)
- procedural (asking for steps, methods, or how-to)
- comparative (asking for comparison or differences)

Rules:
- Output ONLY one word: factual / procedural / comparative
- Do NOT explain
- Do NOT output anything else

Query:
{query}
"""