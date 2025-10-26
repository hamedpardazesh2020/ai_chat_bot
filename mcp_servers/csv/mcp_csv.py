from mcp.server.fastmcp import FastMCP, Context
import uvicorn
import json
import faiss
from sentence_transformers import SentenceTransformer
from typing import List, Dict, Any
import os
import tensorflow as tf
tf.get_logger().setLevel('ERROR')
# ---------- تنظیمات ----------
INDEX_PATH = os.getenv("RAG_INDEX_PATH", "rag.index")
META_PATH  = os.getenv("RAG_META_PATH", "rag_meta.json")

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
app = FastMCP(name="csv-rag-mcp")  # حذف پارامتر 'description'

@app.tool()
def rag_search(ctx: Context, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """
    جستجو بر اساس query و ایندکس
    """
    return search_internal(query, top_k)

if __name__ == "__main__":
    # بارگذاری ایندکس و اجرای سرور MCP
    load_index()

    # استفاده از uvicorn برای اجرا
    uvicorn.run(app, host="0.0.0.0", port=8000)
