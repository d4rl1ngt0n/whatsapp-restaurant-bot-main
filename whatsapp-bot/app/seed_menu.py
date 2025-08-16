from sqlite3 import IntegrityError as SqliteIntegrityError
from app.services.db import get_session, init_db
from app.models import MenuItem

SAMPLE_MENU = [
	{"number": 1, "name": "Margherita Pizza", "description": "Tomato, mozzarella, basil", "price": 10.0, "category": "Pizza", "tags": "vegetarian"},
	{"number": 2, "name": "Pepperoni Pizza", "description": "Tomato, mozzarella, pepperoni", "price": 12.0, "category": "Pizza", "tags": ""},
	{"number": 3, "name": "Caesar Salad", "description": "Romaine, croutons, parmesan", "price": 9.0, "category": "Salad", "tags": ""},
	{"number": 4, "name": "Grilled Chicken Bowl", "description": "Rice, veggies, chicken", "price": 13.5, "category": "Bowl", "tags": "high-protein,gluten-free"},
	{"number": 5, "name": "Tiramisu", "description": "Mascarpone, espresso, cocoa", "price": 6.5, "category": "Dessert", "tags": ""},
]


def main() -> None:
	init_db()
	with get_session() as s:
		for item in SAMPLE_MENU:
			try:
				exists = s.query(MenuItem).filter_by(number=item["number"]).first()
				if exists:
					continue
				s.add(MenuItem(**item, available=True))
				s.flush()
			except (SqliteIntegrityError, Exception):  # noqa: BLE001
				s.rollback()
				# Ignore duplicate insert races
				continue


if __name__ == "__main__":
	main()
