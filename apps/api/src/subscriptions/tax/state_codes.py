"""Phase 21E.4A — Indian State and Union Territory GST 2-Digit Code Registry.

Authoritative mapping of Indian state codes defined under the Indian GST system:
- 01 to 38: States and Union Territories.
- 97: Other Territory.
Provides bidirectional lookup between state names, common abbreviations, and 2-digit codes.
"""

from typing import Final

# Authoritative mapping: 2-digit code -> Canonical State Name
GST_STATE_CODES: Final[dict[str, str]] = {
    "01": "Jammu and Kashmir",
    "02": "Himachal Pradesh",
    "03": "Punjab",
    "04": "Chandigarh",
    "05": "Uttarakhand",
    "06": "Haryana",
    "07": "Delhi",
    "08": "Rajasthan",
    "09": "Uttar Pradesh",
    "10": "Bihar",
    "11": "Sikkim",
    "12": "Arunachal Pradesh",
    "13": "Nagaland",
    "14": "Manipur",
    "15": "Mizoram",
    "16": "Tripura",
    "17": "Meghalaya",
    "18": "Assam",
    "19": "West Bengal",
    "20": "Jharkhand",
    "21": "Odisha",
    "22": "Chhattisgarh",
    "23": "Madhya Pradesh",
    "24": "Gujarat",
    "25": "Daman and Diu",
    "26": "Dadra and Nagar Haveli and Daman and Diu",
    "27": "Maharashtra",
    "28": "Andhra Pradesh",  # Legacy / undivided
    "29": "Karnataka",
    "30": "Goa",
    "31": "Lakshadweep",
    "32": "Kerala",
    "33": "Tamil Nadu",
    "34": "Puducherry",
    "35": "Andaman and Nicobar Islands",
    "36": "Telangana",
    "37": "Andhra Pradesh",  # Newly assigned post-bifurcation
    "38": "Ladakh",
    "97": "Other Territory",
}

# Inverted mapping: normalized lowercase name / abbreviation -> (canonical_name, code)
STATE_NAME_TO_CODE: Final[dict[str, tuple[str, str]]] = {}

# Populate canonical names
for code, name in GST_STATE_CODES.items():
    STATE_NAME_TO_CODE[name.lower()] = (name, code)
    STATE_NAME_TO_CODE[code] = (name, code)

# Common aliases and ISO 3166-2:IN abbreviations
ALIASES: Final[dict[str, str]] = {
    "ka": "29",
    "karnataka": "29",
    "mh": "27",
    "maharashtra": "27",
    "dl": "07",
    "delhi": "07",
    "nct of delhi": "07",
    "national capital territory of delhi": "07",
    "tn": "33",
    "tamil nadu": "33",
    "tamilnadu": "33",
    "ts": "36",
    "tg": "36",
    "telangana": "36",
    "ap": "37",
    "andhra pradesh": "37",
    "kl": "32",
    "kerala": "32",
    "gj": "24",
    "gujarat": "24",
    "wb": "19",
    "west bengal": "19",
    "up": "09",
    "uttar pradesh": "09",
    "rj": "08",
    "rajasthan": "08",
    "mp": "23",
    "madhya pradesh": "23",
    "hr": "06",
    "haryana": "06",
    "pb": "03",
    "punjab": "03",
    "or": "21",
    "od": "21",
    "odisha": "21",
    "orissa": "21",
    "cg": "22",
    "ct": "22",
    "chhattisgarh": "22",
    "chattisgarh": "22",
    "jh": "20",
    "jharkhand": "20",
    "br": "10",
    "bihar": "10",
    "as": "18",
    "assam": "18",
    "ga": "30",
    "goa": "30",
    "ut": "05",
    "uk": "05",
    "uttarakhand": "05",
    "uttaranchal": "05",
    "hp": "02",
    "himachal pradesh": "02",
    "jk": "01",
    "jammu and kashmir": "01",
    "jammu & kashmir": "01",
    "ch": "04",
    "chandigarh": "04",
    "py": "34",
    "puducherry": "34",
    "pondicherry": "34",
    "la": "38",
    "ladakh": "38",
    "dn": "26",
    "dd": "26",
    "dadra and nagar haveli": "26",
    "daman and diu": "26",
    "dadra and nagar haveli and daman and diu": "26",
    "sk": "11",
    "sikkim": "11",
    "ar": "12",
    "arunachal pradesh": "12",
    "nl": "13",
    "nagaland": "13",
    "mn": "14",
    "manipur": "14",
    "mz": "15",
    "mizoram": "15",
    "tr": "16",
    "tripura": "16",
    "ml": "17",
    "meghalaya": "17",
    "an": "35",
    "andaman and nicobar": "35",
    "andaman and nicobar islands": "35",
    "ld": "31",
    "lakshadweep": "31",
    "ot": "97",
    "other territory": "97",
}

for alias, code in ALIASES.items():
    canonical = GST_STATE_CODES[code]
    STATE_NAME_TO_CODE[alias] = (canonical, code)


def normalize_state(state_input: str | None) -> tuple[str, str] | None:
    """Normalize arbitrary state input (name, code, or alias) to (canonical_name, 2_digit_code).

    Returns None if the state cannot be determined unambiguously.
    """
    if not state_input:
        return None
    cleaned = state_input.strip().lower()
    # Direct alias or exact match
    if cleaned in STATE_NAME_TO_CODE:
        return STATE_NAME_TO_CODE[cleaned]

    # Handle numeric string with or without leading zero (e.g., '9' -> '09')
    if cleaned.isdigit() and len(cleaned) <= 2:
        padded = cleaned.zfill(2)
        if padded in GST_STATE_CODES:
            return GST_STATE_CODES[padded], padded

    return None


def get_state_code(state_input: str | None) -> str | None:
    """Resolve state input to 2-digit GST state code."""
    res = normalize_state(state_input)
    return res[1] if res else None


def get_canonical_state_name(state_input: str | None) -> str | None:
    """Resolve state input to canonical state name."""
    res = normalize_state(state_input)
    return res[0] if res else None
