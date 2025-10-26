import os
import pandas as pd
from sentence_transformers import SentenceTransformer
import faiss
import json
from typing import Optional, List, Tuple, Dict, Any
from pathlib import Path
import tensorflow as tf
tf.get_logger().setLevel('ERROR')

# ---------- تنظیمات ----------
# مسیر پوشه‌ای که فایل در آن قرار دارد
_CURRENT_DIR = Path(__file__).resolve().parent

EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
INDEX_PATH = os.getenv("RAG_INDEX_PATH", str(_CURRENT_DIR / "rag.index"))
META_PATH  = os.getenv("RAG_META_PATH", str(_CURRENT_DIR / "rag_meta.json"))
CSV_PATH   = os.getenv("RAG_CSV_PATH", str(_CURRENT_DIR / "data.csv"))
TEXT_COLS  = os.getenv("RAG_TEXT_COLS", "")  # مانند "مدل خودرو,شرکت سازنده,روغن موتور"

# ---------- لود مدل ----------
_model: SentenceTransformer = None

def load_model():
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBEDDING_MODEL_NAME)

# ---------- تولید ایندکس از CSV ----------
def build_index_from_csv(csv_path: str, text_cols: Optional[List[str]] = None) -> Tuple[faiss.IndexFlatIP, Dict[str, Any]]:
    df = pd.read_csv(csv_path)
    if text_cols is None or len(text_cols) == 0:
        # اگر تعیین نشده، همه ستون‌ها را به صورت متن ترکیب می‌کنیم
        text_cols = [c for c in df.columns]

    # ترکیب ستون‌ها برای هر ردیف
    rows_text = df[text_cols].astype(str).apply(lambda r: " | ".join(r.values), axis=1).tolist()

    load_model()
    embs = _model.encode(rows_text, normalize_embeddings=True, convert_to_numpy=True)
    dim = embs.shape[1]
    index = faiss.IndexFlatIP(dim)  # cosine similarity
    index.add(embs)

    meta = {
        "csv_path": csv_path,
        "text_cols": text_cols,
        "rows": df.to_dict(orient="records"),
        "size": len(rows_text),
    }
    return index, meta

# ---------- ذخیره ایندکس و متا دیتا ----------
def persist_index(index: faiss.IndexFlatIP, meta: Dict[str, Any]):
    faiss.write_index(index, INDEX_PATH)
    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)

# ---------- اجرای تولید ایندکس ----------
if __name__ == "__main__":
    text_cols = [c.strip() for c in TEXT_COLS.split(",")] if TEXT_COLS else None
    index, meta = build_index_from_csv(CSV_PATH, text_cols)
    persist_index(index, meta)
    print(f"Index created with {meta['size']} rows from {CSV_PATH}")
