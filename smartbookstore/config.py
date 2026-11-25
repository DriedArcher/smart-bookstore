import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
DATA = Path(os.environ.get("BOOKSTORE_DATA", str(ROOT / "data")))

FACE_BACKEND = os.environ.get("BOOKSTORE_FACE_BACKEND", "lbph")
FACE_MAX_DISTANCE = 100.0
FACE_DIST_SCALE = 200.0
MIN_FACE_CROPS = 10
FACE_SIZE = 96
YOLO_MIN_CONFIDENCE = 0.98

VOICE_MIN_SIMILARITY = 0.55
VOICE_MIN_MARGIN = 0.05
VOICE_MIN_VECTORS = 4
VOICE_RATE = 16000

STARTING_BALANCE = 10.0
FINE = 1.0
VIP_DISCOUNT = 0.10
PURCHASE_COUNT_LIMIT = 3
SPEND_LIMIT = 200.0
MAX_TABOO = 3
MAX_WARNINGS = 2
MIN_RATINGS = 3
LOW_AVG = 2.0
HIGH_AVG = 4.0
PURCHASER_WEIGHT = 2
IMAGE_SIM_CUTOFF = 0.6

RAG_CUTOFF = 0.5
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")
LLM_TIMEOUT = 90


def set_data_dir(path):
    global DATA
    DATA = Path(path)
    DATA.mkdir(parents=True, exist_ok=True)
