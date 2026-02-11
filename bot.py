"""
Async Telegram Client - Channel Post Processor

Listens to posts from SOURCE_CHANNEL_ID, extracts the first number,
divides it by 3.63, and forwards the modified message to TARGET_CHANNEL_ID.

Uses Pyrogram (MTProto API) with API ID and API Hash.
"""

import asyncio
import logging
import os
import re
import sys
from typing import Optional

from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.errors import FloodWait, RPCError
from pyrogram.types import Message

# Load environment variables
load_dotenv()

# Configuration
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
SESSION_NAME = os.getenv("SESSION_NAME", "bot_session")
SOURCE_CHANNEL = os.getenv("SOURCE_CHANNEL")
TARGET_CHANNEL = os.getenv("TARGET_CHANNEL")

# Validate configuration
if not API_ID:
    raise ValueError("API_ID environment variable is required")
if not API_HASH:
    raise ValueError("API_HASH environment variable is required")
if not SOURCE_CHANNEL:
    raise ValueError("SOURCE_CHANNEL environment variable is required")
if not TARGET_CHANNEL:
    raise ValueError("TARGET_CHANNEL environment variable is required")

# Convert API_ID to integer
try:
    API_ID = int(API_ID)
except ValueError:
    raise ValueError("API_ID must be a valid integer")

# Normalize channel identifiers
# Support both usernames (with or without @) and channel IDs
def normalize_channel(channel: str):
    """Normalize channel identifier to support username or ID."""
    channel = channel.strip()
    # If it starts with @, keep it as is
    if channel.startswith('@'):
        return channel
    # If it's a numeric string, try to convert to int (channel ID)
    try:
        return int(channel)
    except ValueError:
        # If not numeric, assume it's a username and add @ if missing
        return f"@{channel}" if not channel.startswith('@') else channel

SOURCE_CHANNEL = normalize_channel(SOURCE_CHANNEL)
TARGET_CHANNEL = normalize_channel(TARGET_CHANNEL)

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


def extract_and_process_number(text: str) -> Optional[tuple[str, str]]:
    """
    Extract the first number from text, divide by 3.63, round to 2 decimals.
    
    Args:
        text: The message text to process
        
    Returns:
        tuple: (original_number_str, processed_number_str) or None if no number found
    """
    # Regex pattern: matches integers and floats (supports optional minus sign)
    # Matches: 123, 123.45, -123, -123.45, 0.5, etc.
    pattern = r'-?\d+\.?\d*'
    match = re.search(pattern, text)
    
    if not match:
        logger.debug("No number found in text")
        return None
    
    original_number_str = match.group()
    try:
        number = float(original_number_str)
        processed_number = round(number / 3.63, 2)
        processed_number_str = f"{processed_number:.2f}"
        
        logger.info(
            f"Number extracted: {original_number_str} → "
            f"Processed: {processed_number_str} (÷ 3.63)"
        )
        return (original_number_str, processed_number_str)
    
    except ValueError as e:
        logger.error(f"Error processing number '{original_number_str}': {e}")
        return None


def replace_first_number(text: str, original: str, replacement: str) -> str:
    """
    Replace ONLY the first occurrence of the original number with the replacement.
    
    Args:
        text: Original message text
        original: Original number string to find
        replacement: Replacement number string
    
    Returns:
        Modified text with only the first number replaced
    """
    # Escape special regex characters in the original number
    escaped_original = re.escape(original)
    # Use count=1 to replace only the first occurrence
    modified_text = re.sub(escaped_original, replacement, text, count=1)
    return modified_text


async def handle_channel_post(client: Client, message: Message) -> None:
    """
    Handle incoming channel posts from SOURCE_CHANNEL_ID.
    
    Args:
        client: The Pyrogram client instance
        message: The message object from the channel
    """
    try:
        # Only process text messages
        if not message.text:
            logger.debug("Received message without text, skipping")
            return
        
        logger.info(f"New post received from channel {message.chat.id}")
        logger.debug(f"Original text: {message.text}")
        
        # Extract and process the first number
        result = extract_and_process_number(message.text)
        
        if result is None:
            logger.info("No number found in post, ignoring")
            return
        
        original_number, processed_number = result
        
        # Replace only the first number in the text
        modified_text = replace_first_number(
            message.text,
            original_number,
            processed_number
        )
        
        logger.info(f"Modified text: {modified_text}")
        
        # Send modified message to target channel
        await client.send_message(
            chat_id=TARGET_CHANNEL,
            text=modified_text
        )
        
        logger.info(f"Message sent successfully to channel {TARGET_CHANNEL}")
    
    except FloodWait as e:
        logger.warning(f"Flood wait: {e.value} seconds. Waiting...")
        await asyncio.sleep(e.value)
    except RPCError as e:
        logger.error(f"Telegram RPC error: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"Unexpected error in handle_channel_post: {e}", exc_info=True)


async def main() -> None:
    """
    Start the client and begin listening for channel posts.
    """
    logger.info("Starting Telegram client...")
    logger.info(f"Source Channel: {SOURCE_CHANNEL}")
    logger.info(f"Target Channel: {TARGET_CHANNEL}")
    
    # Create Pyrogram client
    app = Client(
        name=SESSION_NAME,
        api_id=API_ID,
        api_hash=API_HASH
    )
    
    # Register handler for channel posts
    @app.on_message(filters.chat(SOURCE_CHANNEL) & filters.channel)
    async def channel_post_handler(client: Client, message: Message):
        """Handle new channel posts."""
        await handle_channel_post(client, message)
    
    # Register handler for edited channel posts
    @app.on_edited_message(filters.chat(SOURCE_CHANNEL) & filters.channel)
    async def edited_channel_post_handler(client: Client, message: Message):
        """Handle edited channel posts."""
        await handle_channel_post(client, message)
    
    # Start the client
    logger.info("Client is running and listening for channel posts...")
    logger.info("Press Ctrl+C to stop")
    
    try:
        await app.start()
        logger.info("Client started successfully")
        
        # Get info about the logged-in user
        me = await app.get_me()
        logger.info(f"Logged in as: {me.first_name} (@{me.username or 'N/A'})")
        
        # Keep the client running using asyncio.Event
        # This will wait indefinitely until interrupted
        stop_event = asyncio.Event()
        await stop_event.wait()
    except KeyboardInterrupt:
        logger.info("Stopping client...")
    finally:
        if app.is_connected:
            await app.stop()
        logger.info("Client stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Client stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
