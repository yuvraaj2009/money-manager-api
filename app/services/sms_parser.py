"""
SMS Auto-Parsing Engine.
Regex patterns for Indian bank SMS. Extracts amount, type, bank, merchant.
Auto-categorizes by keyword matching. SHA-256 dedup.
"""

import hashlib
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


@dataclass
class ParsedSMS:
    amount: Decimal
    type: str  # income / expense
    bank_identifier: Optional[str]
    merchant: Optional[str]
    description: str
    confidence: str  # high / medium / low
    category_keyword: Optional[str]  # matched keyword for auto-categorization
    sms_hash: str


# Bank regex patterns: each returns (amount_str, txn_type)
BANK_PATTERNS = [
    # SBI: "debited for Rs 500.00" or "credited for Rs 500.00"
    {
        "name": "SBI",
        "identifiers": ["SBIINB", "SBIIN", "SBI", "ATMSBI"],
        "patterns": [
            re.compile(
                r"(debited|credited)\s+(?:for\s+)?Rs\.?\s*([\d,]+\.?\d*)",
                re.IGNORECASE,
            ),
            re.compile(
                r"Rs\.?\s*([\d,]+\.?\d*)\s+(?:has been\s+)?(debited|credited)",
                re.IGNORECASE,
            ),
        ],
    },
    # HDFC: "Rs.1500.00 debited from a/c"
    {
        "name": "HDFC",
        "identifiers": ["HDFCBK", "HDFC", "HDFCBANK"],
        "patterns": [
            re.compile(
                r"Rs\.?\s*([\d,]+\.?\d*)\s+(debited|credited)",
                re.IGNORECASE,
            ),
            re.compile(
                r"(debited|credited)\s+(?:for\s+)?Rs\.?\s*([\d,]+\.?\d*)",
                re.IGNORECASE,
            ),
        ],
    },
    # ICICI: "debited with INR 2,500.00" or "credited with INR 25,000.00"
    {
        "name": "ICICI",
        "identifiers": ["ICICIB", "ICICI", "ICICBK"],
        "patterns": [
            re.compile(
                r"(debited|credited)\s+(?:with\s+)?(?:INR|Rs\.?)\s*([\d,]+\.?\d*)",
                re.IGNORECASE,
            ),
            re.compile(
                r"(?:INR|Rs\.?)\s*([\d,]+\.?\d*)\s+(?:has been\s+)?(debited|credited)",
                re.IGNORECASE,
            ),
        ],
    },
    # Axis: "INR 750.00 spent on" or standard debit/credit
    {
        "name": "AXIS",
        "identifiers": ["AXISBK", "AXIS", "AXISBNK"],
        "patterns": [
            re.compile(
                r"INR\s*([\d,]+\.?\d*)\s+spent",
                re.IGNORECASE,
            ),
            re.compile(
                r"(debited|credited)\s+(?:for\s+)?(?:INR|Rs\.?)\s*([\d,]+\.?\d*)",
                re.IGNORECASE,
            ),
        ],
    },
    # Generic fallback for any bank
    {
        "name": "GENERIC",
        "identifiers": [],
        "patterns": [
            re.compile(
                r"(debited|credited)\s+(?:for\s+)?(?:INR|Rs\.?)\s*([\d,]+\.?\d*)",
                re.IGNORECASE,
            ),
            re.compile(
                r"(?:INR|Rs\.?)\s*([\d,]+\.?\d*)\s+(?:has been\s+)?(debited|credited)",
                re.IGNORECASE,
            ),
            re.compile(
                r"INR\s*([\d,]+\.?\d*)\s+spent",
                re.IGNORECASE,
            ),
        ],
    },
]

# Keyword -> category name mapping
CATEGORY_KEYWORDS: dict[str, dict] = {
    # Food & Dining (high confidence)
    "swiggy": {"category": "Food & Dining", "confidence": "high"},
    "zomato": {"category": "Food & Dining", "confidence": "high"},
    "restaurant": {"category": "Food & Dining", "confidence": "high"},
    "food": {"category": "Food & Dining", "confidence": "high"},
    "dominos": {"category": "Food & Dining", "confidence": "high"},
    "mcdonalds": {"category": "Food & Dining", "confidence": "high"},
    "starbucks": {"category": "Food & Dining", "confidence": "high"},
    "blinkit": {"category": "Food & Dining", "confidence": "high"},
    "zepto": {"category": "Food & Dining", "confidence": "high"},
    "bigbasket": {"category": "Food & Dining", "confidence": "high"},
    # Transport (high confidence)
    "uber": {"category": "Transport", "confidence": "high"},
    "ola": {"category": "Transport", "confidence": "high"},
    "rapido": {"category": "Transport", "confidence": "high"},
    "metro": {"category": "Transport", "confidence": "high"},
    "petrol": {"category": "Transport", "confidence": "high"},
    "fuel": {"category": "Transport", "confidence": "high"},
    "irctc": {"category": "Transport", "confidence": "high"},
    "indigo": {"category": "Transport", "confidence": "high"},
    # Shopping (high confidence)
    "amazon": {"category": "Shopping", "confidence": "high"},
    "flipkart": {"category": "Shopping", "confidence": "high"},
    "myntra": {"category": "Shopping", "confidence": "high"},
    "ajio": {"category": "Shopping", "confidence": "high"},
    "nykaa": {"category": "Shopping", "confidence": "high"},
    "meesho": {"category": "Shopping", "confidence": "high"},
    # Bills & Recharge (high confidence)
    "airtel": {"category": "Bills & Recharge", "confidence": "high"},
    "jio": {"category": "Bills & Recharge", "confidence": "high"},
    "recharge": {"category": "Bills & Recharge", "confidence": "high"},
    "broadband": {"category": "Bills & Recharge", "confidence": "high"},
    "electricity": {"category": "Bills & Recharge", "confidence": "high"},
    "vodafone": {"category": "Bills & Recharge", "confidence": "high"},
    "bsnl": {"category": "Bills & Recharge", "confidence": "high"},
    "gas": {"category": "Bills & Recharge", "confidence": "medium"},
    # Housing (medium confidence)
    "rent": {"category": "Housing", "confidence": "medium"},
    "maintenance": {"category": "Housing", "confidence": "medium"},
    "society": {"category": "Housing", "confidence": "medium"},
    # Entertainment (high confidence)
    "netflix": {"category": "Entertainment", "confidence": "high"},
    "hotstar": {"category": "Entertainment", "confidence": "high"},
    "spotify": {"category": "Entertainment", "confidence": "high"},
    "pvr": {"category": "Entertainment", "confidence": "high"},
    "inox": {"category": "Entertainment", "confidence": "high"},
    # Health (medium confidence)
    "pharmacy": {"category": "Health", "confidence": "medium"},
    "hospital": {"category": "Health", "confidence": "medium"},
    "apollo": {"category": "Health", "confidence": "medium"},
    "medplus": {"category": "Health", "confidence": "medium"},
    # Income keywords
    "salary": {"category": "Salary", "confidence": "high"},
    "neft": {"category": "Salary", "confidence": "medium"},
    "freelance": {"category": "Freelance", "confidence": "medium"},
}


def compute_sms_hash(sms_body: str, timestamp: str) -> str:
    """SHA-256(sms_body + timestamp) for deduplication."""
    raw = f"{sms_body.strip()}{timestamp.strip()}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _parse_amount(amount_str: str) -> Decimal:
    """Remove commas and convert to Decimal."""
    cleaned = amount_str.replace(",", "")
    return Decimal(cleaned)


def _extract_merchant(sms_body: str) -> Optional[str]:
    """Try to extract merchant/payee from SMS text."""
    # Common patterns for merchant extraction
    patterns = [
        re.compile(r"(?:to|at|for)\s+([A-Z][A-Za-z0-9\s&.]+?)(?:\s+on|\s+ref|\s*\.|\s*$)", re.IGNORECASE),
        re.compile(r"VPA\s+(\S+?)(?:\s|$)", re.IGNORECASE),
        re.compile(r"(?:Info|Ref):\s*(?:NEFT/|UPI/|IMPS/)?(.+?)(?:\s*$)", re.IGNORECASE),
        re.compile(r"transfer\s+to\s+(.+?)(?:\s+on|\s+ref|\s*$)", re.IGNORECASE),
    ]
    for pattern in patterns:
        match = pattern.search(sms_body)
        if match:
            merchant = match.group(1).strip().rstrip(".")
            if len(merchant) > 2:
                return merchant
    return None


def _detect_bank(sms_body: str, sender: Optional[str] = None) -> Optional[str]:
    """Detect bank from sender ID or SMS content."""
    check_text = f"{sender or ''} {sms_body}".upper()
    for bank in BANK_PATTERNS:
        if bank["name"] == "GENERIC":
            continue
        for identifier in bank["identifiers"]:
            if identifier in check_text:
                return bank["name"]
    return None


def _auto_categorize(merchant: Optional[str], sms_body: str) -> tuple[Optional[str], str]:
    """Match keywords to find category. Returns (category_name, confidence)."""
    search_text = f"{merchant or ''} {sms_body}".lower()
    for keyword, info in CATEGORY_KEYWORDS.items():
        if keyword in search_text:
            return info["category"], info["confidence"]
    return None, "low"


def parse_sms(sms_body: str, timestamp: str, sender: Optional[str] = None) -> Optional[ParsedSMS]:
    """
    Parse a single SMS message. Returns ParsedSMS or None if not a transaction SMS.
    """
    sms_hash = compute_sms_hash(sms_body, timestamp)
    bank = _detect_bank(sms_body, sender)

    # Try bank-specific patterns first, then generic
    amount = None
    txn_type = None

    for bank_config in BANK_PATTERNS:
        # Skip non-matching bank-specific patterns
        if bank_config["name"] != "GENERIC" and bank and bank_config["name"] != bank:
            continue
        if bank_config["name"] != "GENERIC" and not bank:
            continue

        for pattern in bank_config["patterns"]:
            match = pattern.search(sms_body)
            if match:
                groups = match.groups()
                if len(groups) == 2:
                    # Determine which group is amount and which is type
                    if groups[0].replace(",", "").replace(".", "").isdigit():
                        amount_str, type_str = groups[0], groups[1]
                    else:
                        type_str, amount_str = groups[0], groups[1]
                    amount = _parse_amount(amount_str)
                    txn_type = "expense" if type_str.lower() in ("debited", "spent") else "income"
                elif len(groups) == 1:
                    # Axis "spent" pattern - only amount, always expense
                    amount = _parse_amount(groups[0])
                    txn_type = "expense"
                break
        if amount is not None:
            break

    # Try generic patterns if bank-specific didn't match
    if amount is None:
        for pattern in BANK_PATTERNS[-1]["patterns"]:  # GENERIC
            match = pattern.search(sms_body)
            if match:
                groups = match.groups()
                if len(groups) == 2:
                    if groups[0].replace(",", "").replace(".", "").isdigit():
                        amount_str, type_str = groups[0], groups[1]
                    else:
                        type_str, amount_str = groups[0], groups[1]
                    amount = _parse_amount(amount_str)
                    txn_type = "expense" if type_str.lower() in ("debited", "spent") else "income"
                elif len(groups) == 1:
                    amount = _parse_amount(groups[0])
                    txn_type = "expense"
                break

    if amount is None:
        return None

    merchant = _extract_merchant(sms_body)
    category_name, confidence = _auto_categorize(merchant, sms_body)

    # Build description
    description = merchant or sms_body[:100]

    return ParsedSMS(
        amount=amount,
        type=txn_type,
        bank_identifier=bank,
        merchant=merchant,
        description=description,
        confidence=confidence,
        category_keyword=category_name,
        sms_hash=sms_hash,
    )
