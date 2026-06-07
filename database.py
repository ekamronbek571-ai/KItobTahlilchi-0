import sqlite3
import logging

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_path="books.db"):
        self.db_path = db_path

    def get_conn(self):
        return sqlite3.connect(self.db_path)

    def init_db(self):
        with self.get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS books (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    info TEXT NOT NULL,
                    photo TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
        logger.info("Baza tayyor.")

    def add_book(self, name: str, info: str, photo: str = None):
        with self.get_conn() as conn:
            conn.execute(
                "INSERT INTO books (name, info, photo) VALUES (?, ?, ?)",
                (name, info, photo)
            )
            conn.commit()

    def get_book_by_name(self, name: str):
        with self.get_conn() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM books WHERE LOWER(name) = LOWER(?)",
                (name,)
            ).fetchone()
            return dict(row) if row else None

    def get_book_by_id(self, book_id: int):
        with self.get_conn() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM books WHERE id = ?",
                (book_id,)
            ).fetchone()
            return dict(row) if row else None

    def search_books(self, query: str):
        with self.get_conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM books WHERE LOWER(name) LIKE LOWER(?)",
                (f"%{query}%",)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_all_books(self):
        with self.get_conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM books ORDER BY name").fetchall()
            return [dict(r) for r in rows]

    def delete_book(self, book_id: int):
        with self.get_conn() as conn:
            conn.execute("DELETE FROM books WHERE id = ?", (book_id,))
            conn.commit()

    def update_book(self, book_id: int, field: str, value: str):
        allowed = {"name", "info", "photo"}
        if field not in allowed:
            return
        with self.get_conn() as conn:
            conn.execute(
                f"UPDATE books SET {field} = ? WHERE id = ?",
                (value, book_id)
            )
            conn.commit()
