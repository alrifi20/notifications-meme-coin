from config import SCORE_LIQUIDITY_GOOD, SCORE_VOLUME_GOOD


def calculate_score(pair: dict) -> int:
    """
    Hitung score 0-100 untuk sebuah token pair.
    Semakin tinggi score, semakin menarik tokennya.

    Breakdown:
    - Liquidity   : 25 poin
    - Volume      : 25 poin
    - Buy pressure: 20 poin
    - Sosial media: 20 poin
    - Marketcap   : 10 poin
    """
    score = 0

    liquidity = pair.get("liquidity", {}).get("usd", 0)
    volume    = pair.get("volume", {}).get("h24", 0)
    mc        = pair.get("marketCap", 0)
    txns      = pair.get("txns", {}).get("h24", {})
    buys      = txns.get("buys", 0)
    sells     = txns.get("sells", 0)

    # --- Liquidity (25 poin) ---
    if liquidity >= SCORE_LIQUIDITY_GOOD:
        score += 25
    elif liquidity >= 10_000:
        score += 15
    elif liquidity >= 5_000:
        score += 5

    # --- Volume (25 poin) ---
    if volume >= SCORE_VOLUME_GOOD:
        score += 25
    elif volume >= 50_000:
        score += 15
    elif volume >= 10_000:
        score += 5

    # --- Buy pressure (20 poin) ---
    total_txns = buys + sells
    if total_txns > 0:
        buy_ratio = buys / total_txns
        if buy_ratio >= 0.6:
            score += 20
        elif buy_ratio >= 0.5:
            score += 10

    # --- Sosial media (20 poin) ---
    telegram_ok = False
    twitter_ok  = False
    for s in pair.get("info", {}).get("socials", []):
        if s.get("type") == "telegram":
            telegram_ok = True
        if s.get("type") == "twitter":
            twitter_ok = True

    if telegram_ok:
        score += 10
    if twitter_ok:
        score += 10

    # --- Marketcap kecil (10 poin) ---
    if 0 < mc <= 100_000:
        score += 10
    elif mc <= 500_000:
        score += 5

    return min(score, 100)


def score_label(score: int) -> str:
    """Label dari nilai score."""
    if score >= 80:
        return "🔥 VERY HOT"
    elif score >= 60:
        return "💎 STRONG"
    elif score >= 40:
        return "👀 WATCH"
    else:
        return "❄️ WEAK"