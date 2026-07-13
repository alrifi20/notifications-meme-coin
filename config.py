import os
from dotenv import load_dotenv

load_dotenv()

# Token diambil dari .env, BUKAN hardcoded
TOKEN = os.getenv("TELEGRAM_TOKEN")

if not TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN tidak ditemukan! Cek file .env kamu.")

# ========================
# FILTER THRESHOLD (satu tempat, konsisten)
# ========================

MIN_LIQUIDITY = 5_000       # minimal $5k liquidity
MIN_VOLUME    = 50_000      # minimal $50k volume 24h
MAX_MARKETCAP = 500_000     # maksimal $500k marketcap

# ========================
# SCORING THRESHOLD
# ========================

SCORE_LIQUIDITY_GOOD  = 50_000   # liquidity bagus untuk scoring
SCORE_VOLUME_GOOD     = 100_000  # volume bagus untuk scoring