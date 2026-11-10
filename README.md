# Kazakh–Russian LLM Issue Routing

A small reproducible evaluation of how a language model routes Kazakh and Russian software issues to `bug`, `docs`, or `feature`. Both prompt strategies use the same Qwen2.5-0.5B-Instruct Q4_K_M checkpoint and the same 30 held-out issues.

| Strategy | Correct | Schema-valid JSON | Macro-F1 |
| --- | ---: | ---: | ---: |
| Zero-shot | 10/30 | 19/30 | 0.230 |
| Few-shot | 18/30 | 30/30 | 0.558 |

The six examples helped the model follow the JSON format. Kazakh remained harder in this run, with 7/15 correct compared with 11/15 for Russian under the few-shot prompt. The change also introduced regressions. For example, the model correctly called a duplicate-order report a bug with zero-shot prompting and called it a feature with few-shot prompting. [Per-language results and mistakes](results/report.md) · [Raw model responses](results/capture.json)

## Replay the results

From the repository root, run this with Python 3.10 or later. Replay requires only the standard library.

```sh
python evaluate.py replay
python -m unittest discover -s tests -v
```

## Dataset and scoring

[The dataset](data/issues.csv) contains 60 synthetic issues with explicit reference labels. Both the development and held-out splits contain five issues per language and label. The few-shot prompt draws one example per language and label from the development split. Both strategies use the same system instruction, temperature, seed, and generation budget. The server generates free-form text so the JSON format score reflects the output the model produced.

The required output is a single JSON object such as `{"label":"docs"}`. Invalid JSON, duplicate or extra keys, and unsupported labels count as incorrect. Macro-F1 gives all three classes equal weight. Replay checks the dataset, prompt and generation fingerprints and requires both recorded responses for every held-out issue.

The measurements cover one quantized checkpoint and 30 synthetic test cases. The corpus has one set of reference labels and is too small to estimate performance on real support traffic.

## Run live inference

Download `qwen2.5-0.5b-instruct-q4_k_m.gguf` from the pinned [model revision](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/tree/9217f5db79a29953eb74d5343926648285ec7e67) and use the [llama.cpp b12244 release](https://github.com/ggml-org/llama.cpp/releases/tag/b12244). The recorded run used the CPU and the commands below. Use `llama-server.exe` on Windows.

```sh
llama-server -m qwen2.5-0.5b-instruct-q4_k_m.gguf --host 127.0.0.1 --port 8080 --alias Qwen2.5-0.5B-Instruct-Q4_K_M -c 4096 -t 6 -ngl 0 -np 1
```

In a second terminal, generate a new capture and report.

```sh
python evaluate.py run --revision 9217f5db79a29953eb74d5343926648285ec7e67 --engine "llama.cpp b12244 (d5bbcd1f3), CPU" --capture results/new-capture.json --report results/new-report.md
```
