"""绘本生产管线——创建绘本→添加页面→生成全部→预览"""
import uuid, logging
from datetime import datetime
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

class BookPage:
    def __init__(self, page_number: int, text: str, image_prompt: str = ""):
        self.page_id = f"bp_{uuid.uuid4().hex[:8]}"
        self.page_number = page_number
        self.text = text
        self.image_prompt = image_prompt or text[:100]
        self.image_path = ""
        self.status = "pending"

class BookProject:
    def __init__(self, title: str, author: str = ""):
        self.book_id = f"bk_{uuid.uuid4().hex[:12]}"
        self.title = title
        self.author = author
        self.pages: List[BookPage] = []
        self.cover_prompt = ""
        self.style = "children_illustration"
        self.status = "draft"
        self.created_at = datetime.now().isoformat()

class BookPipeline:
    _books: Dict[str, BookProject] = {}

    @classmethod
    def create(cls, title, author=""):
        b = BookProject(title, author)
        cls._books[b.book_id] = b
        return b

    @classmethod
    def get(cls, book_id):
        return cls._books.get(book_id)

    @classmethod
    def list_all(cls):
        return [{"book_id": b.book_id, "title": b.title, "author": b.author,
                 "pages": len(b.pages), "status": b.status} for b in cls._books.values()]

    @classmethod
    def add_page(cls, book_id, text, image_prompt=""):
        b = cls._books.get(book_id)
        if not b:
            return None
        p = BookPage(len(b.pages) + 1, text, image_prompt)
        b.pages.append(p)
        return p

    @classmethod
    def generate_all_pages(cls, book_id):
        b = cls._books.get(book_id)
        if not b:
            return False
        for p in b.pages:
            p.status = "generating"
            p.image_path = f"/output/books/{book_id}/page_{p.page_number}.png"
            p.status = "completed"
        b.status = "generating"
        return True

book = BookPipeline()
