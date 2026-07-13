from config import MIN_LIQUIDITY, MIN_VOLUME, MAX_MARKETCAP


def is_gem(pair: dict) -> bool:
    """
    Cek apakah pair memenuhi syarat Potential Gem.
    Threshold konsisten dengan config.py.
    """
    liquidity = pair.get("liquidity", {}).get("usd", 0)
    volume    = pair.get("volume", {}).get("h24", 0)
    mc        = pair.get("marketCap", 0)

    telegram_ok = False
    twitter_ok  = False

    for s in pair.get("info", {}).get("socials", []):
        if s.get("type") == "telegram":
            telegram_ok = True
        if s.get("type") == "twitter":
            twitter_ok = True

    return (
        liquidity >= MIN_LIQUIDITY
        and volume    >= MIN_VOLUME
        and mc        <= MAX_MARKETCAP
        and telegram_ok
        and twitter_ok
    )


def get_filter_status(pair: dict) -> dict:
    """
    Return status tiap filter secara individual,
    berguna untuk format pesan detail.
    """
    liquidity = pair.get("liquidity", {}).get("usd", 0)
    volume    = pair.get("volume", {}).get("h24", 0)
    mc        = pair.get("marketCap", 0)

    telegram_ok = False
    twitter_ok  = False

    for s in pair.get("info", {}).get("socials", []):
        if s.get("type") == "telegram":
            telegram_ok = True
        if s.get("type") == "twitter":
            twitter_ok = True

    return {
        "liquidity_ok": liquidity >= MIN_LIQUIDITY,
        "volume_ok":    volume    >= MIN_VOLUME,
        "mc_ok":        mc        <= MAX_MARKETCAP,
        "community_ok": telegram_ok and twitter_ok,
    }