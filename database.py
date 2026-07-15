"""
数据库操作 - SQLite
"""
import aiosqlite
import json
import uuid
from datetime import datetime, timezone

DB_PATH = "/workspace/aeo-analyzer/backend/aeo.db"


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                target_title TEXT,
                scores TEXT,
                full_report TEXT,
                status TEXT DEFAULT 'completed',
                created_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY,
                report_id TEXT,
                amount INTEGER DEFAULT 199,
                status TEXT DEFAULT 'pending',
                created_at TEXT,
                paid_at TEXT,
                FOREIGN KEY (report_id) REFERENCES reports(id)
            )
        """)
        await db.commit()


async def save_report(url: str, page_data, aeo_score, full_report: dict) -> str:
    report_id = uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO reports (id, url, target_title, scores, full_report, status, created_at) VALUES (?,?,?,?,?,?,?)",
            (
                report_id,
                url,
                full_report["meta"]["site_name"],
                json.dumps({
                    "total": aeo_score.total_score,
                    "grade": aeo_score.grade,
                    "dimensions": [{"name": d.name, "score": d.score, "weight": d.weight} for d in aeo_score.dimensions],
                }, ensure_ascii=False),
                json.dumps(full_report, ensure_ascii=False),
                "completed",
                now,
            ),
        )
        await db.commit()
    return report_id


async def get_report(report_id: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT * FROM reports WHERE id = ?", (report_id,))
        row = await cursor.fetchone()
        if row:
            return {
                "id": row[0],
                "url": row[1],
                "target_title": row[2],
                "scores": json.loads(row[3]),
                "full_report": json.loads(row[4]),
                "status": row[5],
                "created_at": row[6],
            }
    return None


async def create_order(report_id: str, amount: int = 199) -> dict:
    order_id = uuid.uuid4().hex[:16]
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO orders (id, report_id, amount, status, created_at) VALUES (?,?,?,?,?)",
            (order_id, report_id, amount, "pending", now),
        )
        await db.commit()
    return {"order_id": order_id, "amount": amount, "status": "pending"}


async def verify_order(order_id: str) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
        row = await cursor.fetchone()
        if row:
            return {"order_id": row[0], "report_id": row[1], "amount": row[2], "status": row[3]}
    return {"status": "not_found"}


async def confirm_payment(order_id: str) -> bool:
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT status FROM orders WHERE id = ?", (order_id,))
        row = await cursor.fetchone()
        if row and row[0] == "pending":
            await db.execute("UPDATE orders SET status = 'paid', paid_at = ? WHERE id = ?", (now, order_id))
            await db.commit()
            return True
    return False
