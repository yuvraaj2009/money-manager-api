"""
SMS Auto-Parsing Engine.
Regex patterns for Indian bank SMS. Extracts amount, type, bank, merchant.
Auto-categorizes by keyword matching. SHA-256 dedup.
"""

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
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
    transaction_date: Optional[datetime] = field(default=None)


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
    # PNB: "A/c XX4235 debited INR 800.00 Dt 16-03-26 19:25:18 thru UPI:..."
    {
        "name": "PNB",
        "identifiers": ["PNBSMS", "PNB"],
        "patterns": [
            re.compile(
                r"A/c\s+\w+\s+(debited|credited)\s+INR\s+([\d,]+\.?\d*)",
                re.IGNORECASE,
            ),
        ],
        "date_pattern": re.compile(
            r"Dt\s+(\d{2}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})",
            re.IGNORECASE,
        ),
        "merchant_pattern": re.compile(
            r"thru\s+(?:UPI:)?(.+?)\.?Bal",
            re.IGNORECASE,
        ),
    },
    # BOB OneCard: "spent Rs. 525.00 at Zepto" or "paid USD 23.60 at Claude.ai"
    {
        "name": "BOB_ONECARD",
        "identifiers": ["BOBONE", "BOBCARD", "BOB"],
        "patterns": [
            re.compile(
                r"(?:spent|paid)\s+(?:Rs\.?|INR|USD)\s*([\d,]+\.?\d*)\s+at\s+(.+?)\s+with\s+your\s+BOBCARD",
                re.IGNORECASE,
            ),
        ],
        "currency_pattern": re.compile(
            r"(?:spent|paid)\s+(Rs\.?|INR|USD)",
            re.IGNORECASE,
        ),
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


def _extract_date_from_sms(sms_body: str, bank_config: dict) -> Optional[datetime]:
    """Extract transaction date from SMS if bank has a date pattern."""
    date_pattern = bank_config.get("date_pattern")
    if not date_pattern:
        return None
    match = date_pattern.search(sms_body)
    if not match:
        return None
    date_str = match.group(1)
    # PNB format: DD-MM-YY HH:MM:SS
    try:
        return datetime.strptime(date_str, "%d-%m-%y %H:%M:%S")
    except ValueError:
        return None


def parse_sms(sms_body: str, timestamp: str, sender: Optional[str] = None) -> Optional[ParsedSMS]:
    """
    Parse a single SMS message. Returns ParsedSMS or None if not a transaction SMS.
    """
    sms_hash = compute_sms_hash(sms_body, timestamp)
    bank = _detect_bank(sms_body, sender)

    # Try bank-specific patterns first, then generic
    amount = None
    txn_type = None
    bob_merchant = None
    txn_date = None
    matched_config = None

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

                # BOB OneCard: groups = (amount, merchant)
                if bank_config["name"] == "BOB_ONECARD" and len(groups) == 2:
                    amount = _parse_amount(groups[0])
                    txn_type = "expense"  # spent/paid is always debit
                    bob_merchant = groups[1].strip()
                    matched_config = bank_config
                elif len(groups) == 2:
                    # Standard: determine which group is amount and which is type
                    if groups[0].replace(",", "").replace(".", "").isdigit():
                        amount_str, type_str = groups[0], groups[1]
                    else:
                        type_str, amount_str = groups[0], groups[1]
                    amount = _parse_amount(amount_str)
                    txn_type = "expense" if type_str.lower() in ("debited", "spent") else "income"
                    matched_config = bank_config
                elif len(groups) == 1:
                    # Axis "spent" pattern - only amount, always expense
                    amount = _parse_amount(groups[0])
                    txn_type = "expense"
                    matched_config = bank_config
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

    # Extract date from SMS if available (e.g., PNB)
    if matched_config:
        txn_date = _extract_date_from_sms(sms_body, matched_config)

    # Extract merchant — BOB has it in the regex, PNB has a special pattern
    if bob_merchant:
        merchant = bob_merchant
    elif matched_config and matched_config.get("merchant_pattern"):
        m = matched_config["merchant_pattern"].search(sms_body)
        merchant = m.group(1).strip().rstrip(".") if m else _extract_merchant(sms_body)
    else:
        merchant = _extract_merchant(sms_body)

    category_name, confidence = _auto_categorize(merchant, sms_body)

    # Build description — append (USD) for foreign currency BOB transactions
    description = merchant or sms_body[:100]
    if matched_config and matched_config["name"] == "BOB_ONECARD":
        curr_pat = matched_config.get("currency_pattern")
        if curr_pat:
            curr_match = curr_pat.search(sms_body)
            if curr_match and curr_match.group(1).upper() == "USD":
                description = f"{description} (USD)"

    return ParsedSMS(
        amount=amount,
        type=txn_type,
        bank_identifier=bank,
        merchant=merchant,
        description=description,
        confidence=confidence,
        category_keyword=category_name,
        sms_hash=sms_hash,
        transaction_date=txn_date,
    )
