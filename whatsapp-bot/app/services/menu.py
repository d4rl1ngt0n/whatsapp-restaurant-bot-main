from typing import List, Optional, Tuple

from sqlalchemy import select

from app.models import MenuItem
from app.services.db import get_session


def list_categories_with_counts() -> List[Tuple[str, int]]:
	with get_session() as s:
		rows = s.execute(select(MenuItem.category, MenuItem.id).where(MenuItem.available == True)).all()  # noqa: E712
		counts: dict[str, int] = {}
		for category, _ in rows:
			key = category or "Other"
			counts[key] = counts.get(key, 0) + 1
		return sorted(counts.items(), key=lambda kv: kv[0])


def list_items(limit: int = 10) -> List[MenuItem]:
	with get_session() as s:
		return list(s.execute(select(MenuItem).where(MenuItem.available == True).order_by(MenuItem.number).limit(limit)).scalars())  # noqa: E712


def list_all_items() -> List[MenuItem]:
	with get_session() as s:
		return list(s.execute(select(MenuItem).where(MenuItem.available == True).order_by(MenuItem.number)).scalars())  # noqa: E712


def search_items(query: str, limit: int = 10) -> List[MenuItem]:
	q = f"%{query.lower()}%"
	with get_session() as s:
		return list(
			s.execute(
				select(MenuItem).where(
					(MenuItem.available == True)
					& ((MenuItem.name.ilike(q)) | (MenuItem.description.ilike(q)) | (MenuItem.tags.ilike(q)))
				).order_by(MenuItem.number).limit(limit)
			).scalars()
		)


def get_item_by_number(number: int) -> Optional[MenuItem]:
	with get_session() as s:
		return s.execute(select(MenuItem).where(MenuItem.number == number)).scalars().first()
