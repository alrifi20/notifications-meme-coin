import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)

from config import TOKEN
from scanner import get_pairs, get_new_solana_memes, get_trending_boosts, get_pair_by_ca
from filter import is_gem, get_filter_status
from score import calculate_score, score_label

# =========================
# LOGGING
# =========================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# =========================
# SUBSCRIBER STORAGE
# =========================

subscribers: set[int] = set()

# =========================
# PRICE ALERT STORAGE
# Format: { chat_id: [ {ca, name, symbol, target_price, direction, current_price}, ... ] }
# direction: "up" = notif kalau naik ke target, "down" = notif kalau turun ke target
# =========================

price_alerts: dict[int, list] = {}

# =========================
# CONVERSATION STATES
# =========================
ALERT_WAIT_CA     = 1
ALERT_WAIT_TARGET = 2

# =========================
# MENU KEYBOARD
# =========================

keyboard = [
    [
        InlineKeyboardButton("🆕 New Meme",      callback_data="new"),
        InlineKeyboardButton("🚀 Pump 5m",       callback_data="pump5"),
    ],
    [
        InlineKeyboardButton("📈 Top Gainer",    callback_data="up24"),
        InlineKeyboardButton("📉 Top Loser",     callback_data="down24"),
    ],
    [
        InlineKeyboardButton("💎 Potential Gem", callback_data="gem"),
        InlineKeyboardButton("🔥 Trending",      callback_data="trending"),
    ],
    [
        InlineKeyboardButton("🔔 Auto Notif ON",  callback_data="sub"),
        InlineKeyboardButton("🔕 Auto Notif OFF", callback_data="unsub"),
    ],
    [
        InlineKeyboardButton("🔎 Search CA",     callback_data="search"),
        InlineKeyboardButton("ℹ️ About",          callback_data="about"),
    ],
    [
        InlineKeyboardButton("🔔 Set Alert",     callback_data="set_alert"),
        InlineKeyboardButton("📋 My Alerts",     callback_data="my_alerts"),
    ],
]

reply_markup = InlineKeyboardMarkup(keyboard)

# =========================
# REPLY KEYBOARD (nempel di bawah layar)
# =========================

reply_keyboard = [
    [KeyboardButton("🆕 New Meme"),      KeyboardButton("🚀 Pump 5m")],
    [KeyboardButton("📈 Top Gainer"),    KeyboardButton("📉 Top Loser")],
    [KeyboardButton("💎 Potential Gem"), KeyboardButton("🔥 Trending")],
    [KeyboardButton("🔔 Auto Notif ON"), KeyboardButton("🔕 Auto Notif OFF")],
    [KeyboardButton("🔎 Search CA"),     KeyboardButton("ℹ️ About")],
    [KeyboardButton("🔔 Set Alert"),      KeyboardButton("📋 My Alerts")],
]

persistent_keyboard = ReplyKeyboardMarkup(
    reply_keyboard,
    resize_keyboard=True,       # ukuran tombol menyesuaikan layar
    is_persistent=True,            # tetap muncul terus
    input_field_placeholder="Atau kirim CA langsung...",
)

# =========================
# HELPER: FORMAT PAIR
# =========================

def format_token(pair: dict) -> str:
    name      = pair.get("baseToken", {}).get("name", "Unknown")
    symbol    = pair.get("baseToken", {}).get("symbol", "???")
    ca        = pair.get("baseToken", {}).get("address", "Unknown")
    price     = pair.get("priceUsd", "0")
    change24  = pair.get("priceChange", {}).get("h24", 0)
    liquidity = pair.get("liquidity", {}).get("usd", 0)
    volume    = pair.get("volume", {}).get("h24", 0)
    mc        = pair.get("marketCap", 0)
    chain     = pair.get("chainId", "solana")
    pair_addr = pair.get("pairAddress", "")

    sc = calculate_score(pair)
    sl = score_label(sc)
    fs = get_filter_status(pair)
    gem = is_gem(pair)
    gem_status = "💎 POTENTIAL GEM" if gem else "❌ BUKAN GEM"

    return f"""
🔥 *{name}* (`{symbol}`)

📉 24H : `{change24}%`
💰 Price : `${price}`
💧 Liquidity : `${liquidity:,.0f}`
📊 Volume 24H : `${volume:,.0f}`
🏦 Marketcap : `${mc:,.0f}`

━━━━━━━━━━

🎯 Score : `{sc}/100` — {sl}

{gem_status}

Filter:
{"✅" if fs["liquidity_ok"] else "❌"} Liquidity ≥ $5k
{"✅" if fs["volume_ok"]    else "❌"} Volume ≥ $50k
{"✅" if fs["mc_ok"]        else "❌"} Marketcap ≤ $500k
{"✅" if fs["community_ok"] else "❌"} Ada Telegram & Twitter

━━━━━━━━━━

📎 CA:
`{ca}`

🔗 [Lihat di DexScreener](https://dexscreener.com/{chain}/{pair_addr})
"""


def format_mini(pair: dict, emoji: str = "🔥") -> str:
    name   = pair.get("baseToken", {}).get("name", "Unknown")
    symbol = pair.get("baseToken", {}).get("symbol", "???")
    ca     = pair.get("baseToken", {}).get("address", "Unknown")
    price  = pair.get("priceUsd", "0")
    sc     = calculate_score(pair)
    sl     = score_label(sc)
    return (
        f"\n{emoji} *{name}* (`{symbol}`)\n"
        f"Score: `{sc}/100` {sl}\n"
        f"Price: `${price}`\n"
        f"CA:\n`{ca}`\n"
    )


def format_new_meme(pair: dict) -> str:
    """Format detail ala DexScreener untuk New Meme list."""
    name      = pair.get("baseToken", {}).get("name", "Unknown")
    symbol    = pair.get("baseToken", {}).get("symbol", "???")
    price_usd = pair.get("priceUsd", "0")
    price_sol = pair.get("priceNative", "0")
    liquidity = pair.get("liquidity", {}).get("usd", 0)
    fdv       = pair.get("fdv", 0)
    mc        = pair.get("marketCap", 0)
    volume    = pair.get("volume", {}).get("h24", 0)
    chain     = pair.get("chainId", "solana")
    pair_addr = pair.get("pairAddress", "")

    # Price change
    c5m  = pair.get("priceChange", {}).get("m5", 0)
    c1h  = pair.get("priceChange", {}).get("h1", 0)
    c6h  = pair.get("priceChange", {}).get("h6", 0)
    c24h = pair.get("priceChange", {}).get("h24", 0)

    # Txns
    txns  = pair.get("txns", {}).get("h24", {})
    buys  = txns.get("buys", 0)
    sells = txns.get("sells", 0)
    total = buys + sells

    # Volume buy/sell (estimasi dari ratio)
    buy_vol  = volume * (buys / total) if total > 0 else 0
    sell_vol = volume * (sells / total) if total > 0 else 0

    # Traders (tidak tersedia langsung, skip)
    dex_url = f"https://dexscreener.com/{chain}/{pair_addr}"

    def fmt_price_change(val):
        arrow = "📈" if val >= 0 else "📉"
        return f"{arrow}`{val:+.2f}%`"

    def shorten(val):
        if val >= 1_000_000:
            return f"${val/1_000_000:.2f}M"
        elif val >= 1_000:
            return f"${val/1_000:.1f}K"
        return f"${val:,.0f}"

    return (
        f"\n━━━━━━━━━━\n"
        f"🔥 *{name}* (`{symbol}`)\n\n"
        f"💰 Price USD : `${price_usd}`\n"
        f"💎 Price SOL : `{price_sol} SOL`\n"
        f"💧 Liquidity : `{shorten(liquidity)}`\n"
        f"🏦 Mkt Cap   : `{shorten(mc)}`\n"
        f"📊 FDV       : `{shorten(fdv)}`\n\n"
        f"📉 5M  : {fmt_price_change(c5m)}\n"
        f"📉 1H  : {fmt_price_change(c1h)}\n"
        f"📉 6H  : {fmt_price_change(c6h)}\n"
        f"📉 24H : {fmt_price_change(c24h)}\n\n"
        f"📊 Volume 24H : `{shorten(volume)}`\n"
        f"🔢 Txns : `{total:,}` (B:`{buys:,}` / S:`{sells:,}`)\n"
        f"📈 Buy Vol  : `{shorten(buy_vol)}`\n"
        f"📉 Sell Vol : `{shorten(sell_vol)}`\n\n"
        f"🔗 [Lihat di DexScreener]({dex_url})\n"
    )

# =========================
# COMMAND: /start
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🔥 *MEME COIN BOT* 🔥\n"
        "━━━━━━━━━━━━━━━━\n"
        "Realtime Solana Meme Coin Tracker\n\n"
        "Pilih menu di bawah\n"
        "atau kirim *Contract Address* langsung."
    )
    await update.message.reply_text(
        text,
        reply_markup=persistent_keyboard,
        parse_mode="Markdown",
    )

# =========================
# COMMAND: /menu
# =========================

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 *Main Menu*",
        reply_markup=persistent_keyboard,
        parse_mode="Markdown",
    )

# =========================
# HANDLE CA
# =========================

async def handle_reply_keyboard(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
    """Handle tombol reply keyboard."""
    chat_id = update.message.chat_id

    async def reply(text, **kwargs):
        await update.message.reply_text(text, **kwargs)

    try:
        if data == "sub":
            subscribers.add(chat_id)
            await reply("\U0001f514 *Auto Notif aktif!*\nKamu akan dapat notif gem setiap 5 menit.", parse_mode="Markdown")

        elif data == "unsub":
            subscribers.discard(chat_id)
            await reply("\U0001f515 Auto Notif dimatikan.")

        elif data == "search":
            await reply("\U0001f50e *SEARCH CA*\n\nKirim Contract Address token yang mau kamu cek.", parse_mode="Markdown")

        elif data == "set_alert":
            context.user_data["alert_state"] = ALERT_WAIT_CA
            await reply(
                "\U0001f514 *SET PRICE ALERT*\n"
                "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
                "Kirim *Contract Address (CA)* token yang mau kamu pantau.\n\n"
                "Contoh:\n`DezXAZ8z7PnrnRJjz3wXBoRgixCa1bB8a9`\n\n"
                "Ketik /cancel untuk batal.",
                parse_mode="Markdown"
            )

        elif data == "my_alerts":
            alerts = price_alerts.get(chat_id, [])
            if not alerts:
                await reply(
                    "\U0001f4cb Kamu belum punya alert aktif.\n\nSet alert dulu pakai tombol \U0001f514 Set Alert.",
                    parse_mode="Markdown"
                )
            else:
                text = "\U0001f4cb *ALERT AKTIF KAMU*\n\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
                for i, a in enumerate(alerts, 1):
                    icon  = "\U0001f4c8" if a["direction"] == "up" else "\U0001f4c9"
                    aname = a["name"]
                    asym  = a["symbol"]
                    aent  = a["entry_price"]
                    atgt  = a["target_price"]
                    text += f"{i}. {icon} *{aname}* (`{asym}`)\n"
                    text += f"   Entry  : `${aent:.8f}`\n"
                    text += f"   Target : `${atgt:.8f}`\n"
                    text += f"   Hapus  : `/delalert {i}`\n\n"
                await reply(text, parse_mode="Markdown")

        elif data == "about":
            msg = (
                "\u2139\ufe0f *ABOUT BOT*\n"
                "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
                "\U0001f916 Solana Meme Coin Tracker\n"
                "\U0001f4e1 Data dari DexScreener API\n\n"
                "*Fitur:*\n"
                "\U0001f195 New Meme \u2014 Coin baru Solana\n"
                "\U0001f680 Pump 5m \u2014 Naik paling cepat\n"
                "\U0001f4c8 Top Gainer \u2014 Naik 24 jam\n"
                "\U0001f4c9 Top Loser \u2014 Turun 24 jam\n"
                "\U0001f48e Potential Gem \u2014 Filter ketat\n"
                "\U0001f525 Trending \u2014 Boost DexScreener\n"
                "\U0001f514 Auto Notif \u2014 Scan otomatis 5 menit\n"
                "\U0001f50e Search CA \u2014 Cek token by address"
            )
            await reply(msg, parse_mode="Markdown")

        elif data == "new":
            await reply("\U0001f50d Memproses...")
            pairs = get_new_solana_memes()
            if not pairs:
                pairs = sorted(get_pairs("raydium"), key=lambda x: x.get("pairCreatedAt", 0), reverse=True)
            await reply("\U0001f195 *NEW MEME COINS \u2014 SOLANA*", parse_mode="Markdown")
            for pair in pairs[:5]:
                await reply(format_new_meme(pair), parse_mode="Markdown", disable_web_page_preview=True)

        elif data == "pump5":
            await reply("\U0001f50d Memproses...")
            pairs = sorted(get_pairs("raydium"), key=lambda x: x.get("priceChange", {}).get("m5", 0), reverse=True)
            await reply("\U0001f680 *TOP PUMP 5 MENIT \u2014 SOLANA*", parse_mode="Markdown")
            for pair in pairs[:5]:
                await reply(format_new_meme(pair), parse_mode="Markdown", disable_web_page_preview=True)

        elif data == "up24":
            await reply("\U0001f50d Memproses...")
            pairs = sorted(get_pairs("raydium"), key=lambda x: x.get("priceChange", {}).get("h24", 0), reverse=True)
            await reply("\U0001f4c8 *TOP GAINER 24 JAM \u2014 SOLANA*", parse_mode="Markdown")
            for pair in pairs[:5]:
                await reply(format_new_meme(pair), parse_mode="Markdown", disable_web_page_preview=True)

        elif data == "down24":
            await reply("\U0001f50d Memproses...")
            pairs = sorted(get_pairs("raydium"), key=lambda x: x.get("priceChange", {}).get("h24", 0))
            await reply("\U0001f4c9 *TOP LOSER 24 JAM \u2014 SOLANA*", parse_mode="Markdown")
            for pair in pairs[:5]:
                await reply(format_new_meme(pair), parse_mode="Markdown", disable_web_page_preview=True)

        elif data == "gem":
            await reply("\U0001f50d Memproses...")
            pairs = get_pairs("raydium")
            gems = sorted([p for p in pairs if is_gem(p)], key=calculate_score, reverse=True)
            if not gems:
                await reply("\U0001f614 Tidak ada gem yang memenuhi syarat saat ini.")
                return
            await reply("\U0001f48e *POTENTIAL GEM LIST \u2014 SOLANA*", parse_mode="Markdown")
            for pair in gems[:5]:
                await reply(format_new_meme(pair), parse_mode="Markdown", disable_web_page_preview=True)

        elif data == "trending":
            await reply("\U0001f50d Memproses...")
            boosts = get_trending_boosts()
            if not boosts:
                await reply("\u274c Tidak ada data trending.")
                return
            text = "\U0001f525 *TRENDING BOOSTS \u2014 SOLANA*\n"
            for item in boosts[:10]:
                name = item.get("description", item.get("tokenAddress", "Unknown"))[:30]
                ca_  = item.get("tokenAddress", "Unknown")
                url  = item.get("url", "")
                text += f"\n\U0001f525 *{name}*\nCA: `{ca_}`\n"
                if url:
                    text += f"[Lihat]({url})\n"
            await reply(text, parse_mode="Markdown", disable_web_page_preview=True)

    except Exception as e:
        logger.error(f"handle_reply_keyboard error: {e}")
        await reply(f"\u274c Error:\n`{e}`", parse_mode="Markdown")



# =========================
# PRICE ALERT FUNCTIONS
# =========================

async def check_price_alerts(context: ContextTypes.DEFAULT_TYPE):
    if not price_alerts:
        return
    triggered = []
    for chat_id, alerts in list(price_alerts.items()):
        for i, alert in enumerate(alerts):
            try:
                from scanner import get_pair_by_ca as _gp
                pair = _gp(alert["ca"])
                if not pair:
                    continue
                current   = float(pair.get("priceUsd", 0) or 0)
                target    = alert["target_price"]
                direction = alert["direction"]
                hit = (direction == "up" and current >= target) or (direction == "down" and current <= target)
                if hit:
                    name   = alert["name"]
                    symbol = alert["symbol"]
                    pct    = ((current - alert["entry_price"]) / alert["entry_price"]) * 100
                    ca_addr = alert["ca"]
                    d_icon  = "\U0001f4c8" if direction == "up" else "\U0001f4c9"
                    d_text  = "Target NAIK tercapai!" if direction == "up" else "Target TURUN tercapai!"
                    msg = (
                        "\U0001f6a8 *PRICE ALERT TRIGGERED!*\n"
                        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
                        + f"\U0001fab9 *{name}* (`{symbol}`)\n\n"
                        + f"\U0001f3af Target      : `${target:.8f}`\n"
                        + f"\U0001f4b0 Harga skrng : `${current:.8f}`\n"
                        + f"\U0001f4ca Perubahan   : `{pct:+.2f}%`\n\n"
                        + f"{d_icon} {d_text}\n\n"
                        + f"\U0001f4ce CA:\n`{ca_addr}`"
                    )
                    await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
                    triggered.append((chat_id, i))
            except Exception as e:
                logger.warning(f"check_price_alerts error: {e}")
    for chat_id, i in reversed(triggered):
        if chat_id in price_alerts:
            price_alerts[chat_id].pop(i)
            if not price_alerts[chat_id]:
                del price_alerts[chat_id]


async def alert_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Step 1: Minta CA dari user."""
    await update.message.reply_text(
        "\U0001f514 *SET PRICE ALERT*\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
        "Kirim *Contract Address (CA)* token yang mau kamu pantau.\n\n"
        "Contoh:\n`DezXAZ8z7PnrnRJjz3wXBoRgixCa1bB8a9`\n\n"
        "Ketik /cancel untuk batal.",
        parse_mode="Markdown"
    )
    return ALERT_WAIT_CA


async def alert_got_ca(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Step 2: Terima CA, fetch harga, minta target."""
    ca = update.message.text.strip()

    if ca.lower() == "/cancel":
        await update.message.reply_text("\u274c Alert dibatalkan.")
        return ConversationHandler.END

    await update.message.reply_text("\U0001f50d Mengecek token...")

    from scanner import get_pair_by_ca as _gp
    pair = _gp(ca)
    if not pair:
        await update.message.reply_text(
            "\u274c Token tidak ditemukan. Coba kirim CA yang benar, atau /cancel untuk batal."
        )
        return ALERT_WAIT_CA  # minta CA lagi

    current = float(pair.get("priceUsd", 0) or 0)
    name    = pair.get("baseToken", {}).get("name", "Unknown")
    symbol  = pair.get("baseToken", {}).get("symbol", "???")

    # Simpan sementara di context
    context.user_data["alert_ca"]      = ca
    context.user_data["alert_name"]    = name
    context.user_data["alert_symbol"]  = symbol
    context.user_data["alert_current"] = current

    await update.message.reply_text(
        f"\u2705 Token ditemukan!\n\n"
        f"\U0001fab9 *{name}* (`{symbol}`)\n"
        f"\U0001f4b0 Harga skrng : `${current:.8f}`\n\n"
        f"Sekarang kirim *target harga* yang kamu mau.\n"
        f"Contoh: `0.000025`\n\n"
        f"Bot otomatis detect:\n"
        f"\U0001f4c8 Target lebih tinggi = notif kalau NAIK\n"
        f"\U0001f4c9 Target lebih rendah = notif kalau TURUN\n\n"
        f"Ketik /cancel untuk batal.",
        parse_mode="Markdown"
    )
    return ALERT_WAIT_TARGET


async def alert_got_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Step 3: Terima target harga, simpan alert."""
    text = update.message.text.strip()

    if text.lower() == "/cancel":
        await update.message.reply_text("\u274c Alert dibatalkan.")
        context.user_data.clear()
        return ConversationHandler.END

    try:
        target = float(text)
    except ValueError:
        await update.message.reply_text(
            "\u274c Format salah. Kirim angka harga, contoh: `0.000025`\n"
            "Atau /cancel untuk batal.",
            parse_mode="Markdown"
        )
        return ALERT_WAIT_TARGET

    ca      = context.user_data.get("alert_ca")
    name    = context.user_data.get("alert_name")
    symbol  = context.user_data.get("alert_symbol")
    current = context.user_data.get("alert_current")

    chat_id   = update.message.chat_id
    direction = "up" if target > current else "down"

    if chat_id not in price_alerts:
        price_alerts[chat_id] = []

    if len(price_alerts[chat_id]) >= 5:
        await update.message.reply_text(
            "\u26a0\ufe0f Maksimal 5 alert aktif.\n"
            "Hapus dulu yang lama pakai /myalerts lalu /delalert <nomor>",
            parse_mode="Markdown"
        )
        context.user_data.clear()
        return ConversationHandler.END

    price_alerts[chat_id].append({
        "ca": ca, "name": name, "symbol": symbol,
        "target_price": target, "entry_price": current, "direction": direction,
    })

    pct_diff = ((target - current) / current) * 100
    d_icon   = "\U0001f4c8" if direction == "up" else "\U0001f4c9"
    d_text   = "Notif kalau NAIK ke target" if direction == "up" else "Notif kalau TURUN ke target"

    await update.message.reply_text(
        "\u2705 *Alert berhasil di-set!*\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
        + f"\U0001fab9 *{name}* (`{symbol}`)\n"
        + f"\U0001f4b0 Harga skrng : `${current:.8f}`\n"
        + f"\U0001f3af Target      : `${target:.8f}`\n"
        + f"\U0001f4ca Selisih     : `{pct_diff:+.2f}%`\n"
        + f"{d_icon} {d_text}\n\n"
        + "Gue akan notif kamu begitu harga nyentuh target!",
        parse_mode="Markdown"
    )
    context.user_data.clear()
    return ConversationHandler.END


async def alert_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("\u274c Alert dibatalkan.")
    return ConversationHandler.END


async def cmd_set_alert(update, context):
    """Alias untuk /alert command — langsung mulai conversation."""
    return await alert_start(update, context)


async def cmd_my_alerts(update, context):
    chat_id = update.message.chat_id
    alerts  = price_alerts.get(chat_id, [])
    if not alerts:
        await update.message.reply_text(
            "\U0001f4cb Kamu belum punya alert aktif.\n\nSet alert: `/alert <CA> <target>`",
            parse_mode="Markdown"
        )
        return
    text = "\U0001f4cb *ALERT AKTIF KAMU*\n\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
    for i, a in enumerate(alerts, 1):
        icon   = "\U0001f4c8" if a["direction"] == "up" else "\U0001f4c9"
        aname  = a["name"]
        asym   = a["symbol"]
        aentry = a["entry_price"]
        atgt   = a["target_price"]
        text  += f"{i}. {icon} *{aname}* (`{asym}`)\n"
        text  += f"   Entry  : `${aentry:.8f}`\n"
        text  += f"   Target : `${atgt:.8f}`\n"
        text  += f"   Hapus  : `/delalert {i}`\n\n"
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_del_alert(update, context):
    chat_id = update.message.chat_id
    alerts  = price_alerts.get(chat_id, [])
    if not context.args:
        await update.message.reply_text("Contoh: `/delalert 1`", parse_mode="Markdown")
        return
    try:
        idx = int(context.args[0]) - 1
        if idx < 0 or idx >= len(alerts):
            raise ValueError
    except ValueError:
        await update.message.reply_text("\u274c Nomor tidak valid.", parse_mode="Markdown")
        return
    removed = alerts.pop(idx)
    if not alerts:
        del price_alerts[chat_id]
    await update.message.reply_text(
        f"\U0001f5d1\ufe0f Alert *{removed['name']}* (target `${removed['target_price']:.8f}`) dihapus.",
        parse_mode="Markdown"
    )


# Map teks tombol reply keyboard ke callback data
REPLY_KEYBOARD_MAP = {
    "🆕 New Meme":       "new",
    "🚀 Pump 5m":        "pump5",
    "📈 Top Gainer":     "up24",
    "📉 Top Loser":      "down24",
    "💎 Potential Gem":  "gem",
    "🔥 Trending":       "trending",
    "🔔 Auto Notif ON":  "sub",
    "🔕 Auto Notif OFF": "unsub",
    "🔎 Search CA":      "search",
    "ℹ️ About":          "about",
    "🔔 Set Alert":      "set_alert",
    "📋 My Alerts":      "my_alerts",
}


async def handle_ca(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text_in = update.message.text.strip()

    # Cek apakah pesan dari tombol reply keyboard
    if text_in in REPLY_KEYBOARD_MAP:
        await handle_reply_keyboard(update, context, REPLY_KEYBOARD_MAP[text_in])
        return

    # Cek apakah sedang dalam flow alert (dari tombol Set Alert)
    alert_state = context.user_data.get("alert_state")

    if alert_state == ALERT_WAIT_CA:
        # User kirim CA untuk alert
        context.user_data["alert_state"] = ALERT_WAIT_TARGET
        await alert_got_ca(update, context)
        return

    elif alert_state == ALERT_WAIT_TARGET:
        # User kirim target harga untuk alert
        context.user_data.pop("alert_state", None)
        await alert_got_target(update, context)
        return

    # Normal: search token by CA
    await update.message.reply_text("\U0001f50d Mencari token...")

    try:
        pair = get_pair_by_ca(text_in)

        if not pair:
            pairs = get_pairs(text_in)
            pair = pairs[0] if pairs else None

        if not pair:
            await update.message.reply_text("\u274c Token tidak ditemukan.")
            return

        text = format_token(pair)
        await update.message.reply_text(
            text,
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )

    except Exception as e:
        logger.error(f"handle_ca error: {e}")
        await update.message.reply_text(f"\u274c Error:\n`{e}`", parse_mode="Markdown")

# =========================
# AUTO NOTIF JOB
# =========================

async def auto_gem_scan(context: ContextTypes.DEFAULT_TYPE):
    if not subscribers:
        return

    logger.info(f"[auto_scan] Scanning untuk {len(subscribers)} subscriber...")

    pairs = get_pairs("raydium")
    gems  = [p for p in pairs if is_gem(p)]

    if not gems:
        return

    top_gems = sorted(gems, key=calculate_score, reverse=True)[:3]

    text = "🤖 *AUTO SCAN — POTENTIAL GEMS*\n"
    for pair in top_gems:
        text += format_mini(pair, "💎")

    for chat_id in list(subscribers):
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.warning(f"Gagal kirim ke {chat_id}: {e}")
            subscribers.discard(chat_id)

# =========================
# BUTTON CALLBACK
# =========================

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    await query.answer()
    data    = query.data
    chat_id = query.message.chat_id

    try:

        # ---- SUBSCRIBE ----
        if data == "sub":
            subscribers.add(chat_id)
            await query.message.reply_text(
                "🔔 *Auto Notif aktif!*\nKamu akan dapat notif gem setiap 5 menit.",
                parse_mode="Markdown",
            )

        # ---- UNSUBSCRIBE ----
        elif data == "unsub":
            subscribers.discard(chat_id)
            await query.message.reply_text("🔕 Auto Notif dimatikan.")

        # ---- NEW MEME ----
        elif data == "new":
            await query.message.reply_text("🔍 Mengambil meme coin terbaru di Solana...")

            pairs = get_new_solana_memes()
            if not pairs:
                await query.message.reply_text("❌ Tidak ada meme coin baru ditemukan.")
                return

            await query.message.reply_text(
                "🆕 *NEW MEME COINS — SOLANA*",
                parse_mode="Markdown",
            )

            for pair in pairs[:5]:
                text = format_new_meme(pair)
                await query.message.reply_text(
                    text,
                    parse_mode="Markdown",
                    disable_web_page_preview=True,
                )

        # ---- PUMP 5M ----
        elif data == "pump5":
            await query.message.reply_text("🔍 Mengambil pump 5 menit di Solana...")
            pairs = get_pairs("raydium")
            if not pairs:
                await query.message.reply_text("❌ Tidak ada data.")
                return
            sorted_pairs = sorted(
                pairs,
                key=lambda x: x.get("priceChange", {}).get("m5", 0),
                reverse=True,
            )
            await query.message.reply_text(
                "🚀 *TOP PUMP 5 MENIT — SOLANA*",
                parse_mode="Markdown",
            )
            for pair in sorted_pairs[:5]:
                await query.message.reply_text(
                    format_new_meme(pair),
                    parse_mode="Markdown",
                    disable_web_page_preview=True,
                )

        # ---- TOP GAINER ----
        elif data == "up24":
            await query.message.reply_text("🔍 Mengambil top gainer Solana...")
            pairs = get_pairs("raydium")
            if not pairs:
                await query.message.reply_text("❌ Tidak ada data.")
                return
            sorted_pairs = sorted(
                pairs,
                key=lambda x: x.get("priceChange", {}).get("h24", 0),
                reverse=True,
            )
            await query.message.reply_text(
                "📈 *TOP GAINER 24 JAM — SOLANA*",
                parse_mode="Markdown",
            )
            for pair in sorted_pairs[:5]:
                await query.message.reply_text(
                    format_new_meme(pair),
                    parse_mode="Markdown",
                    disable_web_page_preview=True,
                )

        # ---- TOP LOSER ----
        elif data == "down24":
            await query.message.reply_text("🔍 Mengambil top loser Solana...")
            pairs = get_pairs("raydium")
            if not pairs:
                await query.message.reply_text("❌ Tidak ada data.")
                return
            sorted_pairs = sorted(
                pairs,
                key=lambda x: x.get("priceChange", {}).get("h24", 0),
            )
            await query.message.reply_text(
                "📉 *TOP LOSER 24 JAM — SOLANA*",
                parse_mode="Markdown",
            )
            for pair in sorted_pairs[:5]:
                await query.message.reply_text(
                    format_new_meme(pair),
                    parse_mode="Markdown",
                    disable_web_page_preview=True,
                )

        # ---- POTENTIAL GEM ----
        elif data == "gem":
            await query.message.reply_text("🔍 Scanning potential gems di Solana...")
            pairs = get_pairs("raydium")
            gems  = [p for p in pairs if is_gem(p)]

            if not gems:
                await query.message.reply_text(
                    "😔 Tidak ada gem yang memenuhi syarat saat ini."
                )
                return

            gems = sorted(gems, key=calculate_score, reverse=True)[:10]
            text = "💎 *POTENTIAL GEM LIST — SOLANA*\n"
            for pair in gems:
                sc     = calculate_score(pair)
                sl     = score_label(sc)
                name   = pair.get("baseToken", {}).get("name", "Unknown")
                symbol = pair.get("baseToken", {}).get("symbol", "???")
                ca     = pair.get("baseToken", {}).get("address", "Unknown")
                text += (
                    f"\n💎 *{name}* (`{symbol}`)\n"
                    f"Score: `{sc}/100` {sl}\n"
                    f"✅ Liquidity ✅ Volume ✅ MC ✅ Sosmed\n"
                    f"CA:\n`{ca}`\n"
                )
            await query.message.reply_text(text, parse_mode="Markdown")

        # ---- TRENDING ----
        elif data == "trending":
            await query.message.reply_text("🔍 Mengambil trending di Solana...")
            boosts = get_trending_boosts()
            if not boosts:
                await query.message.reply_text("❌ Tidak ada data trending.")
                return
            text = "🔥 *TRENDING BOOSTS — SOLANA*\n"
            for item in boosts[:10]:
                name = item.get("description", item.get("tokenAddress", "Unknown"))[:30]
                ca   = item.get("tokenAddress", "Unknown")
                url  = item.get("url", "")
                text += f"\n🔥 *{name}*\nCA: `{ca}`\n"
                if url:
                    text += f"[Lihat]({url})\n"
            await query.message.reply_text(
                text,
                parse_mode="Markdown",
                disable_web_page_preview=True,
            )

        # ---- SEARCH CA ----
        elif data == "search":
            await query.message.reply_text(
                "🔎 *SEARCH CA*\n\nKirim Contract Address token yang mau kamu cek.",
                parse_mode="Markdown",
            )

        # ---- ABOUT ----
        elif data == "about":
            await query.message.reply_text(
                "ℹ️ *ABOUT BOT*\n"
                "━━━━━━━━━━\n\n"
                "🤖 Solana Meme Coin Tracker\n"
                "📡 Data dari DexScreener API\n\n"
                "*Fitur:*\n"
                "🆕 New Meme — Coin baru Solana\n"
                "🚀 Pump 5m — Naik paling cepat\n"
                "📈 Top Gainer — Naik 24 jam\n"
                "📉 Top Loser — Turun 24 jam\n"
                "💎 Potential Gem — Filter ketat\n"
                "🔥 Trending — Boost DexScreener\n"
                "🔔 Auto Notif — Scan otomatis 5 menit\n"
                "🔎 Search CA — Cek token by address\n"
                "🔔 Set Alert — Alert harga otomatis",
                parse_mode="Markdown",
            )

        elif data == "set_alert":
            await query.message.reply_text(
                "\U0001f514 *SET PRICE ALERT*\n"
                "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
                "Kirim *Contract Address (CA)* token yang mau kamu pantau.\n\n"
                "Contoh:\n`DezXAZ8z7PnrnRJjz3wXBoRgixCa1bB8a9`\n\n"
                "Ketik /cancel untuk batal.",
                parse_mode="Markdown",
            )
            # Set state manual supaya next message masuk ke alert flow
            context.user_data["alert_state"] = ALERT_WAIT_CA

        elif data == "my_alerts":
            alerts = price_alerts.get(chat_id, [])
            if not alerts:
                await query.message.reply_text(
                    "📋 Kamu belum punya alert aktif.\n\n"
                    "Set alert dengan:\n`/alert <CA> <target_harga>`",
                    parse_mode="Markdown"
                )
            else:
                text = "📋 *ALERT AKTIF KAMU*\n━━━━━━━━━━\n\n"
                for i, a in enumerate(alerts, 1):
                    icon  = "\U0001f4c8" if a["direction"] == "up" else "\U0001f4c9"
                    aname = a["name"]
                    asym  = a["symbol"]
                    aent  = a["entry_price"]
                    atgt  = a["target_price"]
                    text += f"{i}. {icon} *{aname}* (`{asym}`)\n"
                    text += f"   Entry  : `${aent:.8f}`\n"
                    text += f"   Target : `${atgt:.8f}`\n"
                    text += f"   Hapus  : `/delalert {i}`\n\n"
                await query.message.reply_text(text, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"button error: {e}")
        await query.message.reply_text(f"❌ Error:\n`{e}`", parse_mode="Markdown")

# =========================
# MAIN
# =========================

def main():
    app = Application.builder().token(TOKEN).build()

    # Conversation handler untuk Set Alert
    alert_conv = ConversationHandler(
        entry_points=[CommandHandler("alert", alert_start)],
        states={
            ALERT_WAIT_CA: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, alert_got_ca)
            ],
            ALERT_WAIT_TARGET: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, alert_got_target)
            ],
        },
        fallbacks=[CommandHandler("cancel", alert_cancel)],
    )

    app.add_handler(alert_conv)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CommandHandler("myalerts", cmd_my_alerts))
    app.add_handler(CommandHandler("delalert", cmd_del_alert))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_ca)
    )

    # Auto scan gem setiap 5 menit
    app.job_queue.run_repeating(
        auto_gem_scan,
        interval=300,
        first=60,
    )

    # Cek price alert setiap 1 menit
    app.job_queue.run_repeating(
        check_price_alerts,
        interval=60,
        first=30,
    )

    logger.info("🚀 BOT RUNNING...")
    print("🚀 BOT RUNNING... Tekan Ctrl+C untuk berhenti.")
    app.run_polling()


if __name__ == "__main__":
    main()