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
STICKER_CHANCE = 0.3  # 30% chance to send a sticker

EMOJI_LIST = [
    "👍", "👎", "❤️", "🔥", "🥳", "👏", "😁", "😂", "😲", "😱", 
    "😢", "😭", "🎉", "😇", "😍", "😅", "💩", "🙏", "🤝", "🍓", 
    "🎃", "👀", "💯", "😎", "🤖", "🐵", "👻", "🎄", "🥂", "🎅", 
    "❄️", "✍️", "🎁", "🤔", "💔", "🥰", "😢", "🥺", "🙈", "🤡", 
    "😋", "🎊", "🍾", "🌟", "👶", "🦄", "💤", "😷", "👨‍💻", "🍌", 
    "🍓", "💀", "👨‍🏫", "🤝", "☠️", "🎯", "🍕", "🦾", "🔥", "💃"
]

STICKER_FILE_IDS = [
    "CAACAgIAAxkBAAEJL5FkZM7RRVadGorxiD9w47-4HUvzXgACbgADr8ZRGmTn_PAl6RC7LwQ",
    "CAACAgIAAxkBAAEJL5NkZM7TTzTGpK_Ecs3zyCwI8ZRu8gACFwADwDZPE_lqX5qCa011LwQ",
    # Add more sticker file_ids here
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
        'a': '𝓪', 'b': '𝓫', 'c': '𝓬', 'd': '𝓭', 'e': '𝓮', 'f': '𝓯', 'g': '𝓰', 'h': '𝓱',
        'i': '𝓲', 'j': '𝓳', 'k': '𝓴', 'l': '𝓵', 'm': '𝓶', 'n': '𝓷', 'o': '𝓸', 'p': '𝓹',
        'q': '𝓺', 'r': '𝓻', 's': '𝓼', 't': '𝓽', 'u': '𝓾', 'v': '𝓿', 'w': '𝔀', 'x': '𝔁',
        'y': '𝔂', 'z': '𝔃', 'A': '𝓐', 'B': '𝓑', 'C': '𝓒', 'D': '𝓓', 'E': '𝓔', 'F': '𝓕',
        'G': '𝓖', 'H': '𝓗', 'I': '𝓘', 'J': '𝓙', 'K': '𝓚', 'L': '𝓛', 'M': '𝓜', 'N': '𝓝',
        'O': '𝓞', 'P': '𝓟', 'Q': '𝓠', 'R': '𝓡', 'S': '𝓢', 'T': '𝓣', 'U': '𝓤', 'V': '𝓥',
        'W': '𝓦', 'X': '𝓧', 'Y': '𝓨', 'Z': '𝓩'
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

async def react_with_emoji_or_sticker(message: Message) -> None:
    try:
        if random.random() < STICKER_CHANCE:
            sticker_file_id = random.choice(STICKER_FILE_IDS)
            await message.reply_sticker(sticker_file_id)
        else:
            emoji = random.choice(EMOJI_LIST)
            await app.send_reaction(message.chat.id, message.id, emoji)
    except Exception as e:
        logger.warning(f"Failed to send reaction or sticker: {str(e)}")

async def process_message(message: Message) -> None:
    await react_with_emoji_or_sticker(message)
    await app.send_chat_action(message.chat.id, ChatAction.TYPING)
    
    user_input = message.text.strip()
    try:
        await rate_limiter.wait()
        response = api.gemini(user_input)
        x = response.get("results")
        image_url = response.get("image_url")

        if x:
            formatted_response = await format_response(truncate_text(x))
            
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
                if random.random() < STICKER_CHANCE:
                    sticker_file_id = random.choice(STICKER_FILE_IDS)
                    await message.reply_sticker(sticker_file_id)
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
            await react_with_emoji_or_sticker(message)
            await process_message(message)
        elif f"@{bot_username}" in message.text:
            await react_with_emoji_or_sticker(message)
            message.text = message.text.replace(f"@{bot_username}", "").strip()
            await process_message(message)

@app.on_callback_query()
async def callback_query_handler(client, callback_query):
    if callback_query.data == "regenerate":
        await process_message(callback_query.message.reply_to_message)
    elif callback_query.data == "like":
        await callback_query.answer("Thanks for your feedback! 😊")
    elif callback_query.data == "dislike":
        await callback_query.answer("We're sorry to hear that. We'll try to improve! 😔")

    await callback_query.message.edit_reply_markup(reply_markup=None)

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
