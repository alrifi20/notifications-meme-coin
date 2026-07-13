import requests

BASE_URL = "https://api.dexscreener.com"

HEADERS = {
    "User-Agent": "MemeCoinBot/1.0"
}


# Nama token yang bukan meme coin, di-skip
SKIP_NAMES = [
    "wrapped", "usd", "usdc", "usdt", "sol", "bitcoin", "ethereum",
    "wbtc", "weth", "wsol", "bonk" , "jito", "msol", "jitosol"
]

# DEX yang relevan untuk meme coin Solana
MEME_DEX = ["raydium", "orca", "meteora", "pump"]


def _is_meme_coin(pair: dict) -> bool:
    """Return True jika pair kemungkinan besar meme coin Solana."""
    mc   = pair.get("marketCap", 0)
    liq  = pair.get("liquidity", {}).get("usd", 0)
    name = pair.get("baseToken", {}).get("name", "").lower()
    dex  = pair.get("dexId", "").lower()

    # Harus dari DEX meme coin
    if not any(d in dex for d in MEME_DEX):
        return False

    # Bukan token besar
    if mc > 50_000_000:
        return False

    # Ada sedikit liquidity
    if liq < 500:
        return False

    # Bukan nama token besar/stablecoin
    if any(s in name for s in SKIP_NAMES):
        return False

    return True


def get_pairs(query: str, chain: str = "solana", meme_only: bool = True) -> list:
    """Cari pair berdasarkan keyword, filter Solana meme coin & hapus duplikat CA."""
    try:
        url = f"{BASE_URL}/latest/dex/search?q={query}"
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
        pairs = r.json().get("pairs", [])

        # Filter chain
        pairs = [p for p in pairs if p.get("chainId", "").lower() == chain]

        # Filter meme coin only
        if meme_only:
            pairs = [p for p in pairs if _is_meme_coin(p)]

        # Hapus duplikat berdasarkan CA
        seen = set()
        unique = []
        for p in pairs:
            ca = p.get("baseToken", {}).get("address", "")
            if ca and ca not in seen:
                seen.add(ca)
                unique.append(p)

        return unique

    except Exception as e:
        print(f"[scanner] get_pairs error: {e}")
        return []


def get_new_meme_coins() -> list:
    """
    Ambil meme coin baru yang baru listed di Solana.
    Pakai endpoint token-profiles/latest.
    """
    try:
        url = f"{BASE_URL}/token-profiles/latest/v1"
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
        data = r.json()

        if isinstance(data, list):
            solana = [t for t in data if t.get("chainId", "").lower() == "solana"]
            return solana[:20]
        return []

    except Exception as e:
        print(f"[scanner] get_new_meme_coins error: {e}")
        return []


def get_trending_boosts() -> list:
    """Ambil token yang sedang di-boost di DexScreener, Solana only."""
    try:
        url = f"{BASE_URL}/token-boosts/latest/v1"
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
        data = r.json()

        if isinstance(data, list):
            return [t for t in data if t.get("chainId", "").lower() == "solana"][:20]
        return []

    except Exception as e:
        print(f"[scanner] get_trending_boosts error: {e}")
        return []


def get_pair_by_ca(ca: str) -> dict | None:
    """Ambil data pair spesifik berdasarkan contract address."""
    try:
        url = f"{BASE_URL}/latest/dex/tokens/{ca}"
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
        pairs = r.json().get("pairs", [])
        if not pairs:
            return None
        return max(pairs, key=lambda p: p.get("liquidity", {}).get("usd", 0))
    except Exception as e:
        print(f"[scanner] get_pair_by_ca error: {e}")
        return None


def get_new_solana_memes() -> list:
    """
    Ambil meme coin Solana terbaru dari raydium/orca/meteora/pump.
    Filter pakai _is_meme_coin, sort by pairCreatedAt terbaru.
    """
    results = []
    queries = ["raydium", "orca", "meteora", "pump"]
    seen = set()

    for q in queries:
        try:
            url = f"{BASE_URL}/latest/dex/search?q={q}"
            r = requests.get(url, headers=HEADERS, timeout=10)
            r.raise_for_status()
            pairs = r.json().get("pairs", [])

            for p in pairs:
                if p.get("chainId", "").lower() != "solana":
                    continue
                if not _is_meme_coin(p):
                    continue
                ca = p.get("baseToken", {}).get("address", "")
                if not ca or ca in seen:
                    continue
                seen.add(ca)
                results.append(p)

        except Exception as e:
            print(f"[scanner] get_new_solana_memes error ({q}): {e}")

    results = sorted(results, key=lambda x: x.get("pairCreatedAt", 0), reverse=True)
    return results[:20]
def get_verified_tokens() -> list:
    """
    Ambil token yang sudah diverifikasi Jupiter (digunakan Phantom).
    """
    try:
        # Jupiter verified token list
        url = "https://token.jup.ag/strict"   # strict = paling ketat & trusted
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        tokens = r.json()

        # Filter hanya Solana meme-ish (bisa di-adjust)
        verified = []
        for t in tokens:
            if t.get("chainId") == "solana" or "solana" in str(t.get("chainId", "")).lower():
                # Skip stablecoin & wrapped token besar
                symbol = t.get("symbol", "").lower()
                name = t.get("name", "").lower()
                if any(x in symbol for x in ["usdc", "usdt", "sol", "wso"]):
                    continue
                verified.append({
                    "ca": t.get("address"),
                    "name": t.get("name"),
                    "symbol": t.get("symbol"),
                    "logo": t.get("logoURI"),
                    "decimals": t.get("decimals")
                })
        return verified[:100]  # batasi 100 dulu

    except Exception as e:
        print(f"[scanner] get_verified_tokens error: {e}")
        return []