# Pilot results — 2026-06-10 (T1+T2, 3 seeds, 2 conditions; n=6 per cell — DIRECTIONAL ONLY)

Harness: post-fix (tool-use requires kernel feedback before DONE is accepted; DONE parsed outside
code block; extractor coerces builder/list results; per-attempt code logged). Anthropic via API,
others via OpenRouter. Raw records: `pilot_*.jsonl`; summaries: `pilot_*_summary.json`.

| model | condition | success | silent-failure | mean conf | mean steps |
|---|---|---|---|---|---|
| claude-haiku-4-5 | single_shot | 0% | **33%** | 0.92 | 1.0 |
| claude-haiku-4-5 | tool_use | 67% | 0% | 0.94 | 3.3 |
| claude-sonnet-4-6 | single_shot | 83% | **17%** | 0.97 | 1.0 |
| claude-sonnet-4-6 | tool_use | 100% | 0% | 0.98 | 2.0 |
| deepseek/deepseek-v3.2 | single_shot | 17% | **17%** | 1.00 | 1.0 |
| deepseek/deepseek-v3.2 | tool_use | 67% | 0% | 0.98 | 3.7 |
| openai/gpt-5.5 | single_shot | 67% | 0% | 0.98 | 1.0 |
| openai/gpt-5.5 | tool_use | 100% | 0% | 0.99 | 2.7 |
| qwen/qwen3.7-max | single_shot | 83% | 0% | 1.00 | 1.0 |
| qwen/qwen3.7-max | tool_use | 100% | 0% | 1.00 | 2.8 |
| moonshotai/kimi-k2.6 | (dropped — endpoint hung past 180s client timeout on 2026-06-10, twice; retry for the full sweep or substitute kimi-k2.5 / another open-weight coder) | | | | |

## Early signals (to test at scale on the ~40-task suite)
1. **P1 holds in every family:** tool-use with kernel feedback ≥ single-shot, all 5 models.
2. **Silent failures appear only in single-shot** (Haiku 33%, Sonnet 17%, DeepSeek 17%) and went to
   0% with kernel feedback in this small sample.
3. **Universal overconfidence:** mean claimed confidence 0.92–1.00 across all cells regardless of
   actual success. Extreme case: DeepSeek single-shot = 17% success at 1.00 mean confidence.
4. **Failure-mode profiles differ by family:** GPT-5.5/Qwen single-shot failures were "loud"
   (invalid/absent solids), Anthropic/DeepSeek failures included silent ones (valid-looking wrong
   geometry). If this survives scale, it's a per-model finding the paper can feature.
5. Best specimen: claude-sonnet-4-6, T1 flange, CONFIDENCE: 0.97, valid solid, bolt-circle check
   failed (`pilot_sonnet.jsonl` seed 0 single_shot).

Caveats: n=6/cell, 2 tasks, 1 run date, temperature defaults, no multi-agent condition yet.
