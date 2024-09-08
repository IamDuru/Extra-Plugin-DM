import asyncio
import logging
from typing import Optional, Dict, Any
import random
import re
from aiocache import cached
from pyrogram import filters
from pyrogram.enums import ChatAction, ParseMode
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait

from MukeshAPI import api
from DuruMusic import app

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
MAX_RETRIES = 3
CACHE_TTL = 3600  # 1 hour
RATE_LIMIT = 5  # requests per second
MAX_MESSAGE_LENGTH = 4096  # Telegram's max message length

EMOJI_LIST = [
    "👍", "👎", "❤️", "🔥", "🥳", "👏", "😁", "😂", "😲", "😱", 
    "😢", "😭", "🎉", "😇", "😍", "😅", "💩", "🙏", "🤝", "🍓", 
    "🎃", "👀", "💯", "😎", "🤖", "🐵", "👻", "🎄", "🥂", "🎅", 
    "❄️", "✍️", "🎁", "🤔", "💔", "🥰", "😢", "🥺", "🙈", "🤡", 
    "😋", "🎊", "🍾", "🌟", "👶", "🦄", "💤", "😷", "👨‍💻", "🍌", 
    "🍓", "💀", "👨‍🏫", "🤝", "☠️", "🎯", "🍕", "🦾", "🔥", "💃"
]

class RateLimiter:
    def __init__(self, rate: int):
        self.rate = rate
        self.allowance = rate
        self.last_check = 0

    async def wait(self):
        current = asyncio.get_event_loop().time()
        time_passed = current - self.last_check
        self.last_check = current
        self.allowance += time_passed * self.rate
        if self.allowance > self.rate:
            self.allowance = self.rate
        if self.allowance < 1:
            await asyncio.sleep(1 - self.allowance / self.rate)
            self.allowance = 0
        else:
            self.allowance -= 1

rate_limiter = RateLimiter(RATE_LIMIT)

@cached(ttl=CACHE_TTL)
async def to_fancy_text(text: str) -> str:
    fancy_chars = {
        'a': 'ᴀ', 'b': 'ʙ', 'c': 'ᴄ', 'd': 'ᴅ', 'e': 'ᴇ', 'f': 'ғ', 'g': 'ɢ', 'h': 'ʜ',
        'i': 'ɪ', 'j': 'ᴊ', 'k': 'ᴋ', 'l': 'ʟ', 'm': 'ᴍ', 'n': 'ɴ', 'o': 'ᴏ', 'p': 'ᴘ',
        'q': 'ǫ', 'r': 'ʀ', 's': 's', 't': 'ᴛ', 'u': 'ᴜ', 'v': 'ᴠ', 'w': 'ᴡ', 'x': 'x',
        'y': 'ʏ', 'z': 'ᴢ'
    }

    return ''.join(fancy_chars.get(char, char) for char in text)

def contains_link(text: str) -> bool:
    return bool(re.search(r'http[s]?://', text))

async def format_response(text: str) -> str:
    if contains_link(text):
        return text
    else:
        return await to_fancy_text(text)

def truncate_text(text: str, max_length: int = MAX_MESSAGE_LENGTH) -> str:
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."

async def react_with_random_emoji(message: Message) -> None:
    try:
        emoji = random.choice(EMOJI_LIST)
        await app.send_reaction(message.chat.id, message.id, emoji)
    except Exception as e:
        logger.warning(f"Failed to send reaction: {str(e)}")

async def process_message(message: Message) -> None:
    await react_with_random_emoji(message)
    await app.send_chat_action(message.chat.id, ChatAction.TYPING)
    
    user_input = message.text.strip()
    try:
        await rate_limiter.wait()
        response = api.gemini(user_input)
        x = response.get("results")
        image_url = response.get("image_url")

        if x:
            formatted_response = await format_response(truncate_text(x))
            
            # Create inline keyboard
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Regenerate", callback_data="regenerate"),
                 InlineKeyboardButton("👍 Like", callback_data="like"),
                 InlineKeyboardButton("👎 Dislike", callback_data="dislike")]
            ])

            if image_url:
                await message.reply_photo(
                    image_url,
                    caption=formatted_response,
                    reply_markup=keyboard,
                    quote=True
                )
            else:
                await message.reply_text(
                    formatted_response,
                    reply_markup=keyboard,
                    quote=True
                )
        else:
            await message.reply_text(await to_fancy_text("Sorry sir! Please try again"), quote=True)
    except Exception as e:
        logger.error(f"Error processing message: {str(e)}")
        await message.reply_text(await to_fancy_text("An error occurred. Please try again later."), quote=True)

@app.on_message(filters.private & ~filters.service)
async def gemini_dm_handler(client, message: Message) -> None:
    await process_message(message)

@app.on_message(filters.group)
async def gemini_group_handler(client, message: Message) -> None:
    bot_username = (await app.get_me()).username

    if message.text:
        if message.reply_to_message and message.reply_to_message.from_user.username == bot_username:
            await process_message(message)
        elif f"@{bot_username}" in message.text:
            message.text = message.text.replace(f"@{bot_username}", "").strip()
            await process_message(message)

@app.on_callback_query()
async def callback_query_handler(client, callback_query):
    if callback_query.data == "regenerate":
        # Regenerate the response
        await process_message(callback_query.message.reply_to_message)
    elif callback_query.data == "like":
        await callback_query.answer("Thanks for your feedback! 😊")
    elif callback_query.data == "dislike":
        await callback_query.answer("We're sorry to hear that. We'll try to improve! 😔")

    # Remove the inline keyboard after user interaction
    await callback_query.message.edit_reply_markup(reply_markup=None)

# Helper function to split long messages
async def send_long_message(chat_id: int, text: str, reply_to_message_id: Optional[int] = None):
    chunks = [text[i:i+MAX_MESSAGE_LENGTH] for i in range(0, len(text), MAX_MESSAGE_LENGTH)]
    for i, chunk in enumerate(chunks):
        try:
            if i == 0:
                await app.send_message(chat_id, chunk, reply_to_message_id=reply_to_message_id)
            else:
                await app.send_message(chat_id, chunk)
        except FloodWait as e:
            await asyncio.sleep(e.x)
            if i == 0:
                await app.send_message(chat_id, chunk, reply_to_message_id=reply_to_message_id)
            else:
                await app.send_message(chat_id, chunk)
