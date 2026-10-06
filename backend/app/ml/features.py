import ipaddress
import math
import re
from collections import Counter
from urllib.parse import parse_qsl, urlsplit


FEATURE_NAMES = (
    "url_length",
    "hostname_length",
    "path_length",
    "query_length",
    "digit_count",
    "dot_count",
    "hyphen_count",
    "at_count",
    "percent_count",
    "subdomain_count",
    "path_depth",
    "query_parameter_count",
    "suspicious_keyword_count",
    "uses_https",
    "has_ip_hostname",
    "has_explicit_port",
    "has_punycode",
    "uses_known_shortener",
    "url_entropy",
)

# HTTPS prevalence differs sharply between the two supplied data sources, so
# using it as a learned signal creates a source shortcut rather than phishing
# detection. It remains extracted and visible to clients, but is excluded from
# model fitting.
MODEL_FEATURE_NAMES = tuple(name for name in FEATURE_NAMES if name != "uses_https")

# Compatibility schema for the externally supplied precomputed dataset.
PRECOMPUTED_FEATURE_NAMES = FEATURE_NAMES[:15]


SUSPICIOUS_KEYWORDS = (
    "account",
    "auth",
    "confirm",
    "credential",
    "invoice",
    "login",
    "password",
    "payment",
    "recover",
    "secure",
    "signin",
    "suspend",
    "update",
    "verify",
    "wallet",
)


KNOWN_SHORTENERS = {
    "bit.ly",
    "buff.ly",
    "cutt.ly",
    "is.gd",
    "ow.ly",
    "rebrand.ly",
    "t.co",
    "tiny.cc",
    "tinyurl.com",
}


def normalize_url(url):
    if not isinstance(url, str):
        raise ValueError("URL must be a string")
    normalized = url.strip()
    if not normalized or len(normalized) > 2048:
        raise ValueError("URL must contain between 1 and 2048 characters")
    if any(character.isspace() for character in normalized):
        raise ValueError("URL cannot contain whitespace")
    if "://" not in normalized:
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", normalized):
            raise ValueError("Only valid HTTP and HTTPS URLs are supported")
        normalized = f"http://{normalized}"
    parsed = urlsplit(normalized)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Only valid HTTP and HTTPS URLs are supported")
    return normalized, parsed


def shannon_entropy(value):
    if not value:
        return 0.0
    counts = Counter(value)
    length = len(value)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


def extract_url_features(url):
    normalized, parsed = normalize_url(url)
    hostname = (parsed.hostname or "").lower().rstrip(".")
    hostname_labels = [label for label in hostname.split(".") if label]
    try:
        ipaddress.ip_address(hostname.strip("[]"))
        has_ip_hostname = 1
    except ValueError:
        has_ip_hostname = 0

    lowered_url = normalized.lower()
    keyword_count = sum(
        len(re.findall(rf"(?<![a-z]){re.escape(keyword)}(?![a-z])", lowered_url))
        for keyword in SUSPICIOUS_KEYWORDS
    )
    try:
        explicit_port = parsed.port is not None
    except ValueError:
        explicit_port = True

    values = {
        "url_length": len(normalized),
        "hostname_length": len(hostname),
        "path_length": len(parsed.path),
        "query_length": len(parsed.query),
        "digit_count": sum(character.isdigit() for character in normalized),
        "dot_count": normalized.count("."),
        "hyphen_count": normalized.count("-"),
        "at_count": normalized.count("@"),
        "percent_count": normalized.count("%"),
        "subdomain_count": 0 if has_ip_hostname else max(len(hostname_labels) - 2, 0),
        "path_depth": len([part for part in parsed.path.split("/") if part]),
        "query_parameter_count": len(parse_qsl(parsed.query, keep_blank_values=True)),
        "suspicious_keyword_count": keyword_count,
        "uses_https": int(parsed.scheme.lower() == "https"),
        "has_ip_hostname": has_ip_hostname,
        "has_explicit_port": int(explicit_port),
        "has_punycode": int("xn--" in hostname),
        "uses_known_shortener": int(hostname in KNOWN_SHORTENERS),
        "url_entropy": round(shannon_entropy(normalized), 6),
    }
    return values


def feature_vector(url):
    features = extract_url_features(url)
    return [features[name] for name in MODEL_FEATURE_NAMES]
