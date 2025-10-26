from mcp.server.fastmcp import FastMCP, Context
import json
import faiss
from sentence_transformers import SentenceTransformer
from typing import List, Dict, Any
import os
from pathlib import Path
import tensorflow as tf
tf.get_logger().setLevel('ERROR')

# ---------- تنظیمات ----------
# مسیر پوشه‌ای که فایل سرور در آن قرار دارد
_CURRENT_DIR = Path(__file__).resolve().parent

INDEX_PATH = os.getenv("RAG_INDEX_PATH", str(_CURRENT_DIR / "rag.index"))
META_PATH  = os.getenv("RAG_META_PATH", str(_CURRENT_DIR / "rag_meta.json"))

# ---------- بارگذاری مدل ----------
_model: SentenceTransformer = None

def load_model():
    global _model
    if _model is None:
        _model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')  # مدل مناسب خود را اینجا بارگذاری کنید.

# ---------- بارگذاری ایندکس ----------
_index: faiss.IndexFlatIP = None
_meta: Dict[str, Any] = {}

def load_index():
    global _index, _meta
    if os.path.exists(INDEX_PATH) and os.path.exists(META_PATH):
        _index = faiss.read_index(INDEX_PATH)
        with open(META_PATH, "r", encoding="utf-8") as f:
            _meta = json.load(f)
        return True
    return False

def search_internal(query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    if _index is None or _meta == {}:
        load_index()

    if _index is None or _meta == {}:
        return []

    # تبدیل query به embedding
    load_model()  # بارگذاری مدل
    q = _model.encode([query], normalize_embeddings=True, convert_to_numpy=True)
    scores, idxs = _index.search(q, top_k)
    res = []
    for rank, (i, s) in enumerate(zip(idxs[0], scores[0])):
        if i == -1:
            continue
        row = _meta["rows"][i]
        text_cols = _meta["text_cols"]
        preview = " | ".join([str(row.get(c, "")) for c in text_cols])
        res.append({
            "rank": rank + 1,
            "score": float(s),
            "row_index": int(i),
            "row": row,
            "preview": preview,
        })
    return res

# ---------- تعریف MCP سرور ----------
server = FastMCP(
    name="csv-rag",
    instructions=(
        "Search CSV-based data using RAG (Retrieval Augmented Generation). "
        "Use the `rag_search` tool to find relevant rows based on semantic similarity."
    ),
)

@server.tool()
def rag_search(ctx: Context, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """
    جستجو بر اساس query و ایندکس RAG.

    Args:
        query: متن جستجو برای یافتن ردیف‌های مشابه
        top_k: تعداد نتایج برتر (پیش‌فرض ۵)

    Returns:
        لیستی از دیکشنری‌ها حاوی ردیف‌های مشابه و امتیاز آن‌ها
    """
    return search_internal(query, top_k)

if __name__ == "__main__":
    import logging

    # تنظیم سطح log
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

    # بارگذاری ایندکس و اجرای سرور MCP
    if not load_index():
        logging.warning(
            "Index files not found. Run generate_embeddings.py first to create the RAG index."
        )

    # اجرای سرور MCP با stdio transport
    server.run()
