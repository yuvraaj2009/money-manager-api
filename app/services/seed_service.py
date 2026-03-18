"""
Seed service: creates default categories and accounts for a new user.
12 categories + 2 accounts. Called inside registration transaction.
If this fails, the entire registration ROLLS BACK.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.category import Category

DEFAULT_CATEGORIES = [
    # Expense categories
    {"name": "Food & Dining", "icon": "restaurant", "color": "#FF5733", "type": "expense"},
    {"name": "Transport", "icon": "directions_car", "color": "#33A1FF", "type": "expense"},
    {"name": "Shopping", "icon": "shopping_bag", "color": "#FF33A1", "type": "expense"},
    {"name": "Bills & Recharge", "icon": "receipt_long", "color": "#FFB833", "type": "expense"},
    {"name": "Housing", "icon": "home", "color": "#8B33FF", "type": "expense"},
    {"name": "Entertainment", "icon": "movie", "color": "#FF3366", "type": "expense"},
    {"name": "Health", "icon": "local_hospital", "color": "#33FFB8", "type": "expense"},
    {"name": "Education", "icon": "school", "color": "#3366FF", "type": "expense"},
    {"name": "Other Expense", "icon": "more_horiz", "color": "#999999", "type": "expense"},
    # Income categories
    {"name": "Salary", "icon": "account_balance", "color": "#00C853", "type": "income"},
    {"name": "Freelance", "icon": "work", "color": "#00BFA5", "type": "income"},
    {"name": "Other Income", "icon": "attach_money", "color": "#66BB6A", "type": "income"},
]

DEFAULT_ACCOUNTS = [
    {"name": "Cash", "type": "cash"},
    {"name": "Bank Account", "type": "bank"},
]


async def seed_user_defaults(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Seed default categories and accounts for a user.
    Must be called inside an existing transaction.
    """
    # Insert categories
    for cat_data in DEFAULT_CATEGORIES:
        category = Category(
            user_id=user_id,
            name=cat_data["name"],
            icon=cat_data["icon"],
            color=cat_data["color"],
            type=cat_data["type"],
            is_default=True,
        )
        db.add(category)

    # Insert accounts
    for acc_data in DEFAULT_ACCOUNTS:
        account = Account(
            user_id=user_id,
            name=acc_data["name"],
            type=acc_data["type"],
            is_default=True,
        )
        db.add(account)
