# Recorded evaluation

**Model** · Qwen2.5-0.5B-Instruct-Q4_K_M

**Model revision** · 9217f5db79a29953eb74d5343926648285ec7e67

**Runtime** · llama.cpp b12244 (d5bbcd1f3), CPU

| Strategy | Language | Correct | Schema-valid JSON | Macro-F1 |
| --- | --- | ---: | ---: | ---: |
| zero-shot | kk | 5/15 | 14/15 | 0.175 |
| zero-shot | ru | 5/15 | 5/15 | 0.333 |
| zero-shot | all | 10/30 | 19/30 | 0.230 |
| few-shot | kk | 7/15 | 15/15 | 0.376 |
| few-shot | ru | 11/15 | 15/15 | 0.719 |
| few-shot | all | 18/30 | 30/30 | 0.558 |

Macro-F1 averages the F1 scores for bug, docs, and feature. Malformed JSON, extra fields, and unknown labels count as incorrect.

## Example disagreements and errors

| ID | Issue | Expected | Zero-shot | Few-shot |
| --- | --- | --- | --- | --- |
| kk-t01 | Бір рет басқан батырма екі бірдей тапсырыс жасайды. | bug | bug | feature |
| kk-t02 | Тапсырманы жойсам тізімде қалып қояды және бетті жаңартқанда қайта ашылады. | bug | bug | feature |
| kk-t05 | Беттің екінші бетіне өтсем бірінші беттің нәтижелері қайта шығады. | bug | bug | feature |
| kk-t06 | Ескі атау кодта өзгерген. Миграция нұсқаулығындағы атауды да жаңартыңыз. | docs | bug | feature |
| kk-t07 | Порт бос болмаса іске қосу мысалын қалай өзгерту керегін жазыңыз. | docs | bug | feature |
| kk-t08 | Бір сұрауда бірнеше тег жіберуге болады екен. Осыған API мысалы керек. | docs | invalid | feature |
