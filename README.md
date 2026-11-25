# Smart Bookstore (CSc 322)

Local desktop app: AI-enabled multimodal bookstore. Python + PySide6, text-file storage (no database), free local LLM via Ollama.

## Setup
```
pip install -r requirements.txt
ollama pull llama3.2
ollama serve
python -m smartbookstore
```
- `ultralytics` is optional (only for the experimental YOLO face backend).
- Without Ollama running, RAG answers still work; LLM fallback replies that the model is offline.
- First launch seeds 35 books and shows "Create super user": enroll the owner's face and/or voice.

## User types
| Type | Can do |
|---|---|
| VS visitor | browse, search, top-3 popular, chat (general/store) |
| RC customer | + cart, checkout, balance, comments/ratings, personal top-3, chat (account) |
| VC VIP | + 10% discount, chat (savings) |
| SU super user | add books, taboo words, reopen accounts, book lists, finance chat/report |

## Rules implemented
- Start balance $10; checkout over balance cancels the order, fines $1; negative balance suspends until SU deposits a positive amount.
- VIP after more than 3 purchases or more than $200 spent.
- Ratings 1-5, buyers weighted x2; no-order list (3+ ratings, avg < 2), to-order list (3+ ratings, avg > 4).
- Taboo words masked with `*`; more than 3 blocks the comment and gives the author 1 warning; RC with more than 2 warnings suspended; VC demoted to RC.
- Chat: RAG first (reply says "answered via RAG"), else Ollama (reply says "LLM"); permissions by role. Mood advisor: tell the chat how you feel ("I feel sad").
- Search by keyword and by picture (upload a cover image).

## Data
All under `data/` (pipe-delimited `.txt`). Edit `data/kb/team.txt` with your real team info. RAG reads every `data/kb/*.txt`.

## Tuning (`smartbookstore/config.py`)
- Face: `FACE_MAX_DISTANCE`, `FACE_BACKEND` (env `BOOKSTORE_FACE_BACKEND=yolo` for YOLO, experimental).
- Voice: `VOICE_MIN_SIMILARITY`, `VOICE_MIN_MARGIN`.
- LLM: `OLLAMA_MODEL`, `OLLAMA_URL`.

## Tests
```
python -m unittest discover -s tests -t .
```
