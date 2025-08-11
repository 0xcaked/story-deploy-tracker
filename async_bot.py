import os
import time
import sqlite3
import logging
import asyncio
import aiohttp
from datetime import datetime, timezone
from web3 import Web3, HTTPProvider
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
import queue
import threading

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --------------------
# Config
# --------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set")

STORY_RPC = os.getenv("STORY_RPC_URL")
if not STORY_RPC:
    raise ValueError("STORY_RPC_URL environment variable is not set")

CHAT_ID = int(os.getenv("ALERT_CHAT_ID", "-1002714144239"))
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL_SECONDS", "6"))
DB_PATH = os.getenv("DB_PATH", "seen_contracts.db")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
DB_CLEANUP_DAYS = int(os.getenv("DB_CLEANUP_DAYS", "30"))
TELEGRAM_RATE_LIMIT = int(os.getenv("TELEGRAM_RATE_LIMIT", "20"))
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "5"))

# Configure API endpoints and links
STORYSCAN_API_BASE = "https://www.storyscan.io/api"
STORYSCAN_UI = "https://www.storyscan.io"
STORY_EXPLORER = "https://explorer.story.foundation"
BLAZING_LINK = "https://t.me/blazing_trading_bot?start=ref_thin-existence-3844"

# Initialize Web3
w3 = Web3(HTTPProvider(STORY_RPC))

# Initialize bot
bot = Bot(token=TELEGRAM_BOT_TOKEN)

# --------------------
# DB
# --------------------
class DBConnectionPool:
    def __init__(self, db_path, pool_size):
        self.db_path = db_path
        self.pool_size = pool_size
        self.connections = queue.Queue(maxsize=pool_size)
        self._init_pool()

    def _init_pool(self):
        for _ in range(self.pool_size):
            conn = sqlite3.connect(self.db_path)
            self.connections.put(conn)

    def get_connection(self):
        return self.connections.get()

    def return_connection(self, conn):
        if not conn:
            return
        try:
            self.connections.put(conn)
        except queue.Full:
            conn.close()

    def close_all(self):
        while not self.connections.empty():
            conn = self.connections.get()
            conn.close()

db_pool = None

def init_db():
    global db_pool
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS seen_contracts (
            address TEXT PRIMARY KEY,
            detected_at INTEGER
        )
    """)
    conn.commit()
    
    cleanup_time = int(time.time()) - (DB_CLEANUP_DAYS * 24 * 60 * 60)
    conn.execute("DELETE FROM seen_contracts WHERE detected_at < ?", (cleanup_time,))
    conn.commit()
    conn.close()

    db_pool = DBConnectionPool(DB_PATH, DB_POOL_SIZE)

def mark_seen(addr: str):
    conn = None
    try:
        conn = db_pool.get_connection()
        conn.execute(
            "INSERT OR IGNORE INTO seen_contracts(address, detected_at) VALUES (?, ?)",
            (addr.lower(), int(time.time()))
        )
        conn.commit()
    finally:
        if conn:
            db_pool.return_connection(conn)

def is_seen(addr: str) -> bool:
    conn = None
    try:
        conn = db_pool.get_connection()
        res = conn.execute("SELECT 1 FROM seen_contracts WHERE address = ?", (addr.lower(),)).fetchone()
        return res is not None
    finally:
        if conn:
            db_pool.return_connection(conn)

# --------------------
# API helpers
# --------------------
async def query_sourcecode(session: aiohttp.ClientSession, contract_address: str):
    params = {
        "module": "contract",
        "action": "getsourcecode",
        "address": contract_address
    }
    try:
        async with session.get(STORYSCAN_API_BASE, params=params, timeout=REQUEST_TIMEOUT) as response:
            response.raise_for_status()
            return await response.json()
    except Exception as e:
        logger.exception("StoryScan sourcecode query failed: %s", e)
        return None

async def query_metadata(session: aiohttp.ClientSession, contract_address: str):
    try:
        url = f"{STORYSCAN_UI}/api/v2/smart-contracts/{contract_address}"
        async with session.get(url, timeout=REQUEST_TIMEOUT) as response:
            if response.status == 200:
                return await response.json()
    except Exception as e:
        logger.warning("Metadata query failed: %s", e)
    return {}

def is_verified(api_resp):
    if not api_resp or "result" not in api_resp:
        return False
    try:
        r = api_resp["result"][0]
        if r.get("SourceCode") and r.get("SourceCode").strip() not in ("", "null"):
            return True
        if r.get("ContractName"):
            return True
    except Exception:
        pass
    return False

# --------------------
# Message Sending
# --------------------
async def send_telegram_message(msg: str, kb: InlineKeyboardMarkup = None):
    for _ in range(MAX_RETRIES):
        try:
            await bot.send_message(
                chat_id=CHAT_ID,
                text=msg,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=kb
            )
            return
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            await asyncio.sleep(1)
    raise Exception("Failed to send message after all retries")

# --------------------
# Formatting
# --------------------
def format_alert(addr, deployer, block_num, ts_unix, src_meta, extra_meta):
    dt = datetime.fromtimestamp(ts_unix, tz=timezone.utc).astimezone()
    ts = dt.strftime("%Y-%m-%d %H:%M:%S %Z")

    name = src_meta.get("ContractName") or "Unknown"
    compiler = src_meta.get("CompilerVersion", "")
    storyscan_link = f"{STORYSCAN_UI}/address/{addr}/contracts"
    storyexplorer_link = f"{STORY_EXPLORER}/address/{addr}"

    text = [
        "🚀 *New Story Contract Deployed!*",
        f"*Name:* `{name}`",
        f"*Address:* [{addr}]({storyscan_link})",
        f"*Deployer:* `{deployer}`",
        f"*Block:* `{block_num}`",
        f"*Time:* `{ts}`"
    ]
    if compiler:
        text.append(f"*Compiler:* `{compiler}`")

    socials = []
    if extra_meta:
        try:
            links = extra_meta.get("links", {})
            for key in ["website", "twitter", "discord", "telegram"]:
                if key in links and links[key]:
                    socials.append(f"[{key.capitalize()}]({links[key]})")
        except Exception:
            pass
    if socials:
        text.append("*Socials:* " + " | ".join(socials))

    kb = [
        [InlineKeyboardButton("Trade (Blazing)", url=BLAZING_LINK)],
        [InlineKeyboardButton("StoryScan", url=storyscan_link),
         InlineKeyboardButton("Story Explorer", url=storyexplorer_link)]
    ]
    return "\n".join(text), InlineKeyboardMarkup(kb)

# --------------------
# Block Processing
# --------------------
async def process_block(session: aiohttp.ClientSession, block_num):
    logger.info("Checking block %d", block_num)
    try:
        block = w3.eth.get_block(block_num, full_transactions=True)
        for tx in block.transactions:
            if tx.to is None:
                try:
                    receipt = w3.eth.get_transaction_receipt(tx.hash)
                    contract_addr = receipt.contractAddress
                    if not contract_addr or is_seen(contract_addr):
                        continue

                    src_resp = await query_sourcecode(session, contract_addr)
                    if not is_verified(src_resp):
                        mark_seen(contract_addr)
                        continue

                    src_meta = src_resp["result"][0]
                    extra_meta = await query_metadata(session, contract_addr)

                    deployer = tx["from"]
                    msg, kb = format_alert(contract_addr, deployer, block_num, block.timestamp, src_meta, extra_meta)
                    await send_telegram_message(msg, kb)
                    mark_seen(contract_addr)
                except Exception as e:
                    logger.error(f"Failed to process transaction {tx.hash}: {e}")
                    continue
    except Exception as e:
        logger.error(f"Failed to process block {block_num}: {e}")
        return

# --------------------
# Main Loop
# --------------------
async def main():
    logger.info("Starting Story contract monitor...")
    logger.info(f"Using RPC: {STORY_RPC}")
    logger.info(f"Alert chat ID: {CHAT_ID}")
    
    # Check Web3 connection
    if not w3.isConnected():
        logger.error("Failed to connect to Story RPC")
        raise SystemExit("RPC connection failed")
    logger.info("Connected to Story blockchain")

    # Initialize database
    try:
        init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise SystemExit("Database initialization failed")

    # Send startup message
    try:
        await send_telegram_message("🚀 Contract monitor bot started!")
    except Exception as e:
        logger.error(f"Failed to send startup message: {e}")
        # Continue anyway

    # Main monitoring loop
    last_block = w3.eth.block_number
    logger.info(f"Starting from block {last_block}")
    
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                latest = w3.eth.block_number
                if latest > last_block:
                    for b in range(last_block + 1, latest + 1):
                        await process_block(session, b)
                    last_block = latest
                await asyncio.sleep(POLL_INTERVAL)
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                await asyncio.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot stopped due to error: {e}")
