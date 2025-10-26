# راهنمای اضافه کردن MCP Server به سیستم چت

## 📚 مقدمه

**MCP (Model Context Protocol)** یک پروتکل استاندارد برای ارتباط بین LLM‌ها و سرویس‌های خارجی است. با استفاده از MCP می‌توانید به Agent چت خود ابزارهای جدیدی اضافه کنید که به آن امکان دسترسی به پایگاه‌داده، جستجو در فایل‌ها، و اجرای عملیات‌های مختلف را می‌دهد.

این سیستم چت از کتابخانه [`mcp-agent`](https://github.com/lastmile-ai/mcp-agent) استفاده می‌کند که به Agent اجازه می‌دهد با چندین MCP server همزمان کار کند.

---

## 🎯 MCP Serverهای موجود

در حال حاضر دو MCP server در این پروژه پیاده‌سازی شده است:

### 1. **ham3d-mysql** (`mcp_servers/ham3d_mysql.py`)
- **توضیح**: جستجو در کاتالوگ محصولات ham3d در MySQL
- **ابزار**: `search_products` - جستجو بر اساس نام، دسته‌بندی، برند، قیمت و رنگ
- **نیازمندی**: اتصال به پایگاه داده MySQL

### 2. **csv-rag** (`mcp_servers/csv/mcp_csv.py`)
- **توضیح**: جستجوی معنایی (semantic search) در فایل‌های CSV با استفاده از RAG
- **ابزار**: `rag_search` - جستجوی مشابهت معنایی در داده‌های CSV
- **نیازمندی**: فایل CSV و ایندکس embeddings تولید شده

---

## 🔧 مراحل اضافه کردن MCP Server

### قدم ۱: ایجاد فایل کانفیگ YAML

برای هر MCP server باید یک فایل کانفیگ YAML ایجاد کنید که مشخصات اجرا را تعیین می‌کند.

**مسیر پیشنهادی**: `mcp_servers/<server_name>/config/mcp_agent.config.yaml`

**ساختار فایل کانفیگ**:
```yaml
mcp:
  servers:
    <server-name>:
      transport: stdio          # نوع ارتباط (stdio برای ارتباط استاندارد)
      command: python           # دستور اجرا
      args:                     # آرگومان‌های دستور
        - -m
        - mcp_servers.<module_path>
      env:                      # متغیرهای محیطی (اختیاری)
        KEY: value
```

---

### قدم ۲: تنظیم متغیرهای محیطی

در فایل `.env` یا `app.config.yaml` متغیرهای زیر را تنظیم کنید:

```bash
# مسیر فایل کانفیگ MCP agent
MCP_AGENT_CONFIG=/path/to/mcp_agent.config.yaml

# لیست سرورهای MCP که می‌خواهید فعال شوند (جدا شده با کاما)
MCP_AGENT_SERVERS=server1,server2,server3

# سایر تنظیمات (اختیاری)
MCP_AGENT_LLM=openrouter              # LLM provider (openrouter یا openai)
MCP_AGENT_MODEL=anthropic/claude-3.5  # مدل پیش‌فرض
```

**نکته مهم**: اگر چندین سرور دارید، می‌توانید همه آن‌ها را در یک فایل کانفیگ قرار دهید یا فایل‌های جداگانه ایجاد کنید.

---

### قدم ۳: راه‌اندازی سرور

قبل از اضافه کردن به Agent، مطمئن شوید سرور به تنهایی کار می‌کند:

```bash
# اجرای مستقیم برای تست
python -m mcp_servers.<module_name>
```

اگر سرور به درستی اجرا شد، باید منتظر دریافت ورودی از stdin بماند.

---

## 📋 مثال ۱: فعال‌سازی سرور CSV-RAG

### ۱. آماده‌سازی داده‌ها

ابتدا باید ایندکس RAG را از فایل CSV تولید کنید:

```bash
cd /home/user/ai_chat_bot
python -m mcp_servers.csv.generate_embeddings
```

خروجی:
```
Index created with 925 rows from /home/user/ai_chat_bot/mcp_servers/csv/data.csv
```

این دستور دو فایل ایجاد می‌کند:
- `mcp_servers/csv/rag.index` - ایندکس FAISS
- `mcp_servers/csv/rag_meta.json` - متادیتای ردیف‌ها

### ۲. ایجاد فایل کانفیگ

فایل `mcp_servers/csv/config/mcp_agent.config.yaml` از قبل ایجاد شده است:

```yaml
mcp:
  servers:
    csv-rag:
      transport: stdio
      command: python
      args:
        - -m
        - mcp_servers.csv.mcp_csv
      env:
        LOG_LEVEL: INFO
```

### ۳. تنظیم متغیرهای محیطی

در `.env` یا `app.config.yaml`:

```bash
MCP_AGENT_CONFIG=/home/user/ai_chat_bot/mcp_servers/csv/config/mcp_agent.config.yaml
MCP_AGENT_SERVERS=csv-rag
```

### ۴. راه‌اندازی سیستم چت

```bash
uvicorn app.main:app --reload
```

حالا Agent می‌تواند از ابزار `rag_search` برای جستجو در CSV استفاده کند!

**مثال استفاده**:
```
کاربر: روغن موتور مناسب برای پژو ۲۰۶ چیست؟
Agent: [از ابزار rag_search استفاده می‌کند]
```

---

## 📋 مثال ۲: فعال‌سازی سرور ham3d-mysql

### ۱. تنظیم متغیرهای پایگاه داده

در `.env`:

```bash
HAM3D_DB_HOST=127.0.0.1
HAM3D_DB_PORT=3306
HAM3D_DB_USER=your-username
HAM3D_DB_PASSWORD=your-password
HAM3D_DB_NAME=ham3dbot_ham3d_shop
HAM3D_DB_POOL_MIN_SIZE=1
HAM3D_DB_POOL_MAX_SIZE=5
```

### ۲. استفاده از فایل کانفیگ موجود

فایل `mcp_servers/ham3d_mysql/config/mcp_agent.config.yaml` از قبل ایجاد شده است.

### ۳. تنظیم متغیرهای محیطی

```bash
MCP_AGENT_CONFIG=/home/user/ai_chat_bot/mcp_servers/ham3d_mysql/config/mcp_agent.config.yaml
MCP_AGENT_SERVERS=ham3d
```

### ۴. راه‌اندازی سیستم چت

```bash
uvicorn app.main:app --reload
```

---

## 🔗 استفاده از چند MCP Server همزمان

می‌توانید چندین سرور را همزمان فعال کنید:

### روش ۱: یک فایل کانفیگ با چندین سرور

فایل `mcp_agent.config.yaml`:
```yaml
mcp:
  servers:
    csv-rag:
      transport: stdio
      command: python
      args:
        - -m
        - mcp_servers.csv.mcp_csv
      env:
        LOG_LEVEL: INFO

    ham3d:
      transport: stdio
      command: python
      args:
        - -m
        - mcp_servers.ham3d_mysql
      env:
        HAM3D_DB_HOST: 127.0.0.1
        HAM3D_DB_USER: your-username
        HAM3D_DB_PASSWORD: your-password
        HAM3D_DB_NAME: ham3dbot_ham3d_shop
```

در `.env`:
```bash
MCP_AGENT_CONFIG=/home/user/ai_chat_bot/mcp_agent.config.yaml
MCP_AGENT_SERVERS=csv-rag,ham3d
```

### روش ۲: فایل‌های کانفیگ جداگانه

**توجه**: در حال حاضر `mcp-agent` فقط از یک فایل کانفیگ پشتیبانی می‌کند، پس باید همه سرورها را در یک فایل تعریف کنید.

---

## 🛠️ ساخت MCP Server جدید

### قالب پایه

```python
from mcp.server.fastmcp import FastMCP, Context
from typing import Any
import logging
import os

# ایجاد سرور MCP
server = FastMCP(
    name="my-server",
    instructions="توضیحات سرور و نحوه استفاده از آن",
)

# تعریف ابزار
@server.tool()
def my_tool(ctx: Context, param1: str, param2: int = 10) -> dict[str, Any]:
    """
    توضیحات ابزار که به Agent نمایش داده می‌شود.

    Args:
        param1: توضیحات پارامتر اول
        param2: توضیحات پارامتر دوم (اختیاری)

    Returns:
        دیکشنری حاوی نتایج
    """
    # منطق ابزار
    return {"result": "success"}

# نقطه ورود برای اجرا
if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    server.run()
```

### نکات مهم:

1. **حتماً از `server.run()` استفاده کنید نه `uvicorn.run()`**
   - MCP از stdio transport استفاده می‌کند نه HTTP

2. **از Type hints استفاده کنید**
   - Agent از type hints برای درک پارامترهای ابزار استفاده می‌کند

3. **Docstring واضح بنویسید**
   - Agent از docstring برای تصمیم‌گیری استفاده می‌کند

4. **مسیرهای فایل را مطلق کنید**
   ```python
   from pathlib import Path
   _CURRENT_DIR = Path(__file__).resolve().parent
   FILE_PATH = str(_CURRENT_DIR / "data.csv")
   ```

---

## 🐛 عیب‌یابی (Troubleshooting)

### مشکل: سرور اجرا نمی‌شود

**علت**: احتمالاً از `uvicorn.run()` استفاده کرده‌اید
**راه‌حل**: از `server.run()` استفاده کنید

```python
# ❌ اشتباه
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

# ✅ درست
if __name__ == "__main__":
    server.run()
```

### مشکل: Agent ابزار را نمی‌بیند

**علت**: سرور در `MCP_AGENT_SERVERS` اضافه نشده
**راه‌حل**: اسم سرور را به `MCP_AGENT_SERVERS` اضافه کنید

```bash
MCP_AGENT_SERVERS=csv-rag,ham3d,my-new-server
```

### مشکل: فایل‌ها پیدا نمی‌شوند

**علت**: استفاده از مسیرهای نسبی
**راه‌حل**: از `Path(__file__).resolve().parent` استفاده کنید

```python
from pathlib import Path
_CURRENT_DIR = Path(__file__).resolve().parent
CSV_PATH = str(_CURRENT_DIR / "data.csv")
```

### مشکل: خطای اتصال به پایگاه داده

**علت**: متغیرهای محیطی تنظیم نشده‌اند
**راه‌حل**:
1. متغیرها را در فایل کانفیگ YAML تعریف کنید
2. یا آن‌ها را در `.env` قرار دهید

### مشکل: Agent از ابزار استفاده نمی‌کند

**علت**: docstring یا instructions واضح نیست
**راه‌حل**: توضیحات دقیق‌تر بنویسید و نمونه استفاده ارائه دهید

---

## 📖 منابع بیشتر

- [مستندات mcp-agent](https://github.com/lastmile-ai/mcp-agent)
- [پروتکل MCP](https://modelcontextprotocol.io/)
- [FastMCP Documentation](https://github.com/jlowin/fastmcp)

---

## ✅ چک‌لیست راه‌اندازی

قبل از اینکه بگویید "کار نمی‌کند"، این موارد را بررسی کنید:

- [ ] آیا ایندکس/داده‌های مورد نیاز ایجاد شده‌اند؟ (برای csv-rag)
- [ ] آیا فایل کانفیگ YAML ساخته شده است؟
- [ ] آیا `MCP_AGENT_CONFIG` به درستی تنظیم شده است؟
- [ ] آیا نام سرور در `MCP_AGENT_SERVERS` قرار دارد؟
- [ ] آیا متغیرهای محیطی مورد نیاز تنظیم شده‌اند؟
- [ ] آیا سرور به تنهایی اجرا می‌شود؟ (`python -m mcp_servers...`)
- [ ] آیا از `server.run()` به جای `uvicorn.run()` استفاده کرده‌اید؟

---

**موفق باشید!** 🚀
