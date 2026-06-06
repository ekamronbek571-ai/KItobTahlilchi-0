import sqlite3
import os


class Database:
    def __init__(self, db_path: str = "data/books.db"):
        self.db_path = db_path

    def _conn(self):
        return sqlite3.connect(self.db_path)

    def init(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS books (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    info TEXT NOT NULL,
                    image_file_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def add_book(self, name: str, info: str, image_file_id: str = None):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO books (name, info, image_file_id) VALUES (?, ?, ?)",
                (name, info, image_file_id),
            )
            conn.commit()

    def search_book(self, query: str) -> dict | None:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            # Avval aniq nom
            row = conn.execute(
                "SELECT * FROM books WHERE LOWER(name) = LOWER(?)", (query,)
            ).fetchone()
            if not row:
                # Keyin qisman moslik
                row = conn.execute(
                    "SELECT * FROM books WHERE LOWER(name) LIKE LOWER(?)",
                    (f"%{query}%",),
                ).fetchone()
            return dict(row) if row else None

    def get_all_books(self) -> list[dict]:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM books ORDER BY name").fetchall()
            return [dict(r) for r in rows]

    def get_book_by_id(self, book_id: int) -> dict | None:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
            return dict(row) if row else None

    def update_book_info(self, book_id: int, info: str):
        with self._conn() as conn:
            conn.execute("UPDATE books SET info = ? WHERE id = ?", (info, book_id))
            conn.commit()

    def delete_book(self, book_id: int):
        with self._conn() as conn:
            conn.execute("DELETE FROM books WHERE id = ?", (book_id,))
            conn.commit()
