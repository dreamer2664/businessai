# Scores (one line per milestone; nothing ships that lowers a score)

| set | what | score | notes |
|---|---|---|---|
| tests/business.txt | 55 knowledge questions, 4 blocks | **52/55** | business.kdw 5.7 MB, KDR_WIKI_READK=3 |
| tests/banks/mcq_principles-marketing.jsonl (coverage) | is the right answer inside the retrieved passages? (100-q sample) | **77 %** | ceiling for the exam |
| tests/banks/mcq_principles-marketing.jsonl (exam, offline) | agent/mcq.py picks a choice, no external model | **57–60 %** (chance 25 %) | 87 % on its most-confident half → escalate the rest |
| tests/browse.txt | 19 read-only browsing tasks | **18/19** | Brave→Yahoo→Bing fallback; walls detected 2/2 |
| tests/chat.txt, tests/general.txt | inherited from kdr-brain (small talk, arithmetic, world knowledge) | not wired yet | needs the composer model (milestone 3+) |
