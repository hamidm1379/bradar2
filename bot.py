"""
Async Telegram Client - Channel Post Processor

Listens to posts from SOURCE_CHANNEL_ID, extracts the first number,
divides it by 3.63, and forwards the modified message to TARGET_CHANNEL_ID.
Also saves posts to a file for backup.

Uses Pyrogram (MTProto API) with API ID and API Hash.
"""

import asyncio
import json
import logging
import os
import re
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

# Fix asyncio event loop for Python 3.14+ compatibility with Pyrogram
# Python 3.14+ requires explicit event loop policy setup
# Pyrogram tries to get an event loop during import, so we need to ensure one exists
if sys.platform == 'win32':
    # Set Windows event loop policy (suppress deprecation warnings for Python 3.16+)
    import warnings
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning, module="asyncio")
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        except AttributeError:
            # Fallback for older Python versions that don't have this
            pass

# Create or get event loop for Pyrogram's sync wrapper (required for Python 3.14+)
try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    # No event loop exists, create one
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

# Fix encoding for Windows console
if sys.platform == 'win32':
    try:
        import codecs
        # Check if stdout has encoding attribute and buffer
        if hasattr(sys.stdout, 'buffer') and hasattr(sys.stdout, 'encoding'):
            if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
                sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        if hasattr(sys.stderr, 'buffer') and hasattr(sys.stderr, 'encoding'):
            if sys.stderr.encoding and sys.stderr.encoding.lower() != 'utf-8':
                sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
    except (AttributeError, LookupError, ValueError):
        # If codecs not available or already UTF-8, continue
        pass

from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.errors import (
    FloodWait, 
    RPCError,
    ChatWriteForbidden,
    ChannelPrivate,
    UsernameNotOccupied,
    PeerIdInvalid,
    UserBannedInChannel
)
from pyrogram.types import Message

# Load environment variables
load_dotenv()

# Configuration
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
SESSION_NAME = os.getenv("SESSION_NAME", "bot_session")
SOURCE_CHANNEL = os.getenv("SOURCE_CHANNEL")
TARGET_CHANNEL = os.getenv("TARGET_CHANNEL")
SAVE_POSTS = os.getenv("SAVE_POSTS", "true").lower() == "true"
POSTS_FILE = os.getenv("POSTS_FILE", "saved_posts.json")
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
RETRY_DELAY = int(os.getenv("RETRY_DELAY", "5"))

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

# Reduce Pyrogram connection logging noise
logging.getLogger("pyrogram.connection.connection").setLevel(logging.WARNING)
logging.getLogger("pyrogram.connection.transport").setLevel(logging.WARNING)
logging.getLogger("pyrogram.session.session").setLevel(logging.WARNING)


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


def check_session_lock(session_name: str) -> tuple[bool, str]:
    """
    Check if the session file is locked and provide helpful information.
    
    Args:
        session_name: Name of the session file (without .session extension)
        
    Returns:
        tuple: (is_locked, error_message)
    """
    session_file = Path(f"{session_name}.session")
    session_journal = Path(f"{session_name}.session-journal")
    
    if not session_file.exists():
        return False, ""
    
    # Try to open the database in exclusive mode to check if it's locked
    try:
        conn = sqlite3.connect(str(session_file), timeout=1.0)
        conn.execute("BEGIN EXCLUSIVE")
        conn.rollback()
        conn.close()
        return False, ""
    except sqlite3.OperationalError as e:
        if "database is locked" in str(e).lower():
            error_msg = (
                f"Session file '{session_file}' is locked. This usually means:\n"
                f"  1. Another instance of the bot is already running\n"
                f"  2. A previous instance didn't close properly\n"
                f"  3. The session file is corrupted\n\n"
                f"Solutions:\n"
                f"  - Check if another bot instance is running and stop it\n"
                f"  - Wait a few seconds and try again\n"
                f"  - If the problem persists, delete '{session_file}' and '{session_journal}' "
                f"(you'll need to re-authenticate)\n"
            )
            return True, error_msg
        else:
            return False, str(e)
    except Exception as e:
        return False, str(e)


def force_unlock_session(session_name: str) -> bool:
    """
    Attempt to force unlock a stale session file by removing the journal file.
    This should only be used when you're certain no other instance is running.
    
    Args:
        session_name: Name of the session file (without .session extension)
        
    Returns:
        bool: True if unlock was successful, False otherwise
    """
    session_file = Path(f"{session_name}.session")
    session_journal = Path(f"{session_name}.session-journal")
    
    if not session_file.exists():
        return False
    
    try:
        # Remove journal file if it exists (this often resolves stale locks)
        if session_journal.exists():
            logger.warning(f"Removing stale journal file: {session_journal}")
            try:
                session_journal.unlink()
            except Exception as e:
                logger.warning(f"Could not remove journal file: {e}")
        
        # Try multiple times to ensure the database is accessible
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                conn = sqlite3.connect(str(session_file), timeout=2.0)
                # Try to execute a simple query to ensure the database is accessible
                conn.execute("SELECT 1")
                # Try to get an exclusive lock to ensure no other process is using it
                conn.execute("BEGIN EXCLUSIVE")
                conn.rollback()
                conn.close()
                if attempt > 0:
                    logger.info(f"Session file unlocked successfully after {attempt + 1} attempts")
                else:
                    logger.info("Session file unlocked successfully")
                return True
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e).lower():
                    if attempt < max_attempts - 1:
                        time.sleep(1)  # Wait a bit before retrying
                        continue
                    else:
                        logger.warning("Session file is still locked after multiple attempts. Another process may be using it.")
                        return False
                else:
                    logger.warning(f"Database error during unlock attempt: {e}")
                    return False
            except Exception as e:
                if attempt < max_attempts - 1:
                    time.sleep(1)
                    continue
                else:
                    logger.warning(f"Error during unlock attempt: {e}")
                    return False
        return False
    except Exception as e:
        logger.error(f"Error attempting to force unlock session: {e}")
        return False


async def wait_for_session_unlock(session_name: str, max_wait: int = 30, check_interval: float = 2.0) -> bool:
    """
    Wait for the session file to become unlocked.
    
    Args:
        session_name: Name of the session file
        max_wait: Maximum time to wait in seconds
        check_interval: Time between checks in seconds
        
    Returns:
        bool: True if unlocked, False if still locked after max_wait
    """
    start_time = time.time()
    while time.time() - start_time < max_wait:
        is_locked, _ = check_session_lock(session_name)
        if not is_locked:
            return True
        await asyncio.sleep(check_interval)
    return False


def save_post_to_file(message_data: dict) -> None:
    """
    Save post data to a JSON file for backup.
    
    Args:
        message_data: Dictionary containing message information
    """
    if not SAVE_POSTS:
        return
    
    try:
        posts_file = Path(POSTS_FILE)
        
        # Load existing posts if file exists
        if posts_file.exists():
            try:
                with open(posts_file, 'r', encoding='utf-8') as f:
                    posts = json.load(f)
            except (json.JSONDecodeError, IOError):
                posts = []
        else:
            posts = []
        
        # Add new post
        posts.append(message_data)
        
        # Save back to file
        with open(posts_file, 'w', encoding='utf-8') as f:
            json.dump(posts, f, ensure_ascii=False, indent=2)
        
        logger.debug(f"Post saved to {POSTS_FILE}")
    except Exception as e:
        logger.error(f"Error saving post to file: {e}", exc_info=True)


async def handle_channel_post(client: Client, message: Message) -> None:
    """
    Handle incoming channel posts from SOURCE_CHANNEL_ID.
    
    Args:
        client: The Pyrogram client instance
        message: The message object from the channel
    """
    message_data = None
    try:
        # Only process text messages
        if not message.text:
            logger.debug("Received message without text, skipping")
            return
        
        logger.info(f"New post received from channel {message.chat.id}")
        logger.debug(f"Original text: {message.text}")
        
        # Save original post to file
        message_data = {
            "timestamp": datetime.now().isoformat(),
            "message_id": message.id,
            "chat_id": message.chat.id,
            "original_text": message.text,
            "processed": False
        }
        
        # Extract and process the first number
        result = extract_and_process_number(message.text)
        
        if result is None:
            logger.info("No number found in post, ignoring")
            message_data["reason"] = "No number found"
            save_post_to_file(message_data)
            return
        
        original_number, processed_number = result
        
        # Replace only the first number in the text
        modified_text = replace_first_number(
            message.text,
            original_number,
            processed_number
        )
        
        logger.info(f"Modified text: {modified_text}")
        
        # Try to send with retry logic
        retries = 0
        while retries < MAX_RETRIES:
            try:
                # Check if client is connected
                if not client.is_connected:
                    logger.warning("Client not connected, waiting for reconnection...")
                    await asyncio.sleep(RETRY_DELAY)
                    retries += 1
                    continue
                
                # Send modified message to target channel
                await client.send_message(
                    chat_id=TARGET_CHANNEL,
                    text=modified_text
                )
                
                logger.info(f"Message sent successfully to channel {TARGET_CHANNEL}")
                
                # Update message data
                message_data["processed"] = True
                message_data["modified_text"] = modified_text
                message_data["original_number"] = original_number
                message_data["processed_number"] = processed_number
                save_post_to_file(message_data)
                return
                
            except (ChatWriteForbidden, ChannelPrivate, UsernameNotOccupied, PeerIdInvalid, UserBannedInChannel) as e:
                # These errors should not be retried - they indicate permission/access issues
                error_msg = f"Cannot send message to target channel {TARGET_CHANNEL}: {e}"
                logger.error(error_msg)
                if message_data:
                    message_data["error"] = str(e)
                    message_data["error_type"] = type(e).__name__
                    save_post_to_file(message_data)
                # Don't retry for permission errors
                return
                
            except (ConnectionError, asyncio.TimeoutError, OSError) as e:
                retries += 1
                if retries < MAX_RETRIES:
                    logger.warning(f"Connection error (attempt {retries}/{MAX_RETRIES}): {e}. Retrying in {RETRY_DELAY}s...")
                    await asyncio.sleep(RETRY_DELAY)
                else:
                    logger.error(f"Failed to send message after {MAX_RETRIES} attempts: {e}")
                    if message_data:
                        message_data["error"] = str(e)
                        message_data["error_type"] = "ConnectionError"
                        save_post_to_file(message_data)
                    raise
                    
            except RPCError as e:
                # Other RPC errors - log and don't retry
                error_msg = f"Telegram RPC error while sending to {TARGET_CHANNEL}: {e}"
                logger.error(error_msg, exc_info=True)
                if message_data:
                    message_data["error"] = str(e)
                    message_data["error_type"] = type(e).__name__
                    save_post_to_file(message_data)
                # Don't retry for RPC errors (except FloodWait which is handled separately)
                return
    
    except FloodWait as e:
        logger.warning(f"Flood wait: {e.value} seconds. Waiting...")
        await asyncio.sleep(e.value)
        # Retry after flood wait
        await handle_channel_post(client, message)
    except (ConnectionError, asyncio.TimeoutError, OSError) as e:
        logger.error(f"Connection error in handle_channel_post: {e}")
        if message_data:
            message_data["error"] = str(e)
            save_post_to_file(message_data)
    except RPCError as e:
        logger.error(f"Telegram RPC error: {e}", exc_info=True)
        if message_data:
            message_data["error"] = str(e)
            save_post_to_file(message_data)
    except Exception as e:
        logger.error(f"Unexpected error in handle_channel_post: {e}", exc_info=True)
        if message_data:
            message_data["error"] = str(e)
            save_post_to_file(message_data)


async def main() -> None:
    """
    Start the client and begin listening for channel posts.
    """
    logger.info("Starting Telegram client...")
    logger.info(f"Source Channel: {SOURCE_CHANNEL}")
    logger.info(f"Target Channel: {TARGET_CHANNEL}")
    logger.info(f"Save posts to file: {SAVE_POSTS}")
    if SAVE_POSTS:
        logger.info(f"Posts file: {POSTS_FILE}")
    
    # Create Pyrogram client with improved configuration
    # Note: Connection retries are handled at the application level in the retry loop below
    app = Client(
        name=SESSION_NAME,
        api_id=API_ID,
        api_hash=API_HASH,
        # Connection settings for better stability
        workdir=".",
        # Reduce timeout issues
        no_updates=False,
        takeout=False,
    )
    
    # Track connection state
    connection_retries = 0
    max_connection_retries = 10  # Increased retries for network issues
    base_retry_delay = 15  # Start with 15 seconds delay
    
    # Register handler for channel posts
    # Remove filters.channel to catch all messages from the channel
    @app.on_message(filters.chat(SOURCE_CHANNEL))
    async def channel_post_handler(client: Client, message: Message):
        """Handle new channel posts."""
        logger.info(f"Message received from chat: {message.chat.id} ({message.chat.title or message.chat.username or 'N/A'})")
        logger.info(f"Expected source channel: {SOURCE_CHANNEL}")
        await handle_channel_post(client, message)
    
    # Register handler for edited channel posts
    @app.on_edited_message(filters.chat(SOURCE_CHANNEL))
    async def edited_channel_post_handler(client: Client, message: Message):
        """Handle edited channel posts."""
        logger.info(f"Edited message received from chat: {message.chat.id} ({message.chat.title or message.chat.username or 'N/A'})")
        logger.info(f"Expected source channel: {SOURCE_CHANNEL}")
        await handle_channel_post(client, message)
    
    # Check for session lock before starting
    is_locked, lock_message = check_session_lock(SESSION_NAME)
    if is_locked:
        logger.warning("Session file is locked. Attempting to wait for unlock...")
        logger.warning(lock_message)
        unlocked = await wait_for_session_unlock(SESSION_NAME, max_wait=10)
        if not unlocked:
            logger.warning("Session file is still locked after waiting. Attempting to force unlock stale lock...")
            logger.warning("Note: This is safe if no other bot instance is running.")
            force_unlocked = force_unlock_session(SESSION_NAME)
            if not force_unlocked:
                logger.error("Session file is still locked. Please resolve the issue manually:")
                logger.error(lock_message)
                logger.error("\nTo manually fix:")
                logger.error(f"  1. Make sure no other bot instance is running")
                logger.error(f"  2. Delete '{SESSION_NAME}.session' and '{SESSION_NAME}.session-journal'")
                logger.error(f"  3. Restart the bot (you'll need to re-authenticate)")
                return
            else:
                logger.info("Stale lock removed successfully. Proceeding with connection...")
    
    # Start the client with retry logic
    logger.info("Attempting to connect to Telegram...")
    logger.info("If you experience connection timeouts, check:")
    logger.info("  - Your internet connection")
    logger.info("  - Firewall/proxy settings")
    logger.info("  - Telegram API availability in your region")
    logger.info("Press Ctrl+C to stop")
    
    lock_retry_count = 0
    max_lock_retries = 3  # Prevent infinite lock retry loops
    
    while connection_retries < max_connection_retries:
        try:
            # Ensure client is stopped before starting (in case of retry)
            if app.is_connected:
                try:
                    await app.stop()
                    await asyncio.sleep(1)  # Give time for cleanup
                except Exception:
                    pass
            
            await app.start()
            logger.info("Client started successfully")
            connection_retries = 0  # Reset on successful connection
            lock_retry_count = 0  # Reset lock retry count on successful connection
            
            # Get info about the logged-in user
            me = await app.get_me()
            logger.info(f"Logged in as: {me.first_name} (@{me.username or 'N/A'})")
            
            # Verify access to channels
            try:
                logger.info("Verifying access to channels...")
                
                # Check source channel
                try:
                    source_chat = await app.get_chat(SOURCE_CHANNEL)
                    logger.info(f"✓ Source channel accessible: {source_chat.title} (@{source_chat.username or 'N/A'}) - ID: {source_chat.id}")
                except Exception as e:
                    logger.error(f"✗ Cannot access source channel {SOURCE_CHANNEL}: {e}")
                    logger.error("Make sure you are a member of the source channel!")
                
                # Check target channel
                try:
                    target_chat = await app.get_chat(TARGET_CHANNEL)
                    logger.info(f"✓ Target channel accessible: {target_chat.title} (@{target_chat.username or 'N/A'}) - ID: {target_chat.id}")
                except Exception as e:
                    logger.error(f"✗ Cannot access target channel {TARGET_CHANNEL}: {e}")
                    logger.error("Make sure you have permission to send messages to the target channel!")
                
                logger.info("Channel verification complete. Listening for messages...")
            except Exception as e:
                logger.warning(f"Error verifying channels: {e}")
            
            # Keep the client running using asyncio.Event
            # This will wait indefinitely until interrupted
            stop_event = asyncio.Event()
            await stop_event.wait()
            
        except (ConnectionError, asyncio.TimeoutError, OSError) as e:
            connection_retries += 1
            logger.error(f"Connection error (attempt {connection_retries}/{max_connection_retries}): {e}")
            if connection_retries < max_connection_retries:
                # Exponential backoff: increase delay with each retry
                retry_delay = base_retry_delay * (1.5 ** (connection_retries - 1))
                logger.info(f"Retrying connection in {retry_delay:.1f} seconds...")
                await asyncio.sleep(retry_delay)
            else:
                logger.error("Max connection retries reached. Exiting...")
                logger.error("Please check your internet connection and firewall settings.")
                break
        except Exception as e:
            # Check if it's a database lock error
            error_str = str(e).lower()
            is_db_lock = False
            
            # Check the main exception message
            if "database is locked" in error_str:
                is_db_lock = True
            # Check exception cause
            elif isinstance(e.__cause__, sqlite3.OperationalError):
                if "database is locked" in str(e.__cause__).lower():
                    is_db_lock = True
            # Check if it's a direct sqlite3.OperationalError
            elif isinstance(e, sqlite3.OperationalError):
                if "database is locked" in error_str:
                    is_db_lock = True
            
            if is_db_lock:
                lock_retry_count += 1
                logger.error("Database lock error detected!")
                
                # Prevent infinite lock retry loops
                if lock_retry_count > max_lock_retries:
                    logger.error(f"Max lock retry attempts ({max_lock_retries}) reached. Exiting to prevent infinite loop.")
                    logger.error("Please manually resolve the session lock issue:")
                    logger.error(f"  1. Stop any other running instances of the bot")
                    logger.error(f"  2. Delete '{SESSION_NAME}.session' and '{SESSION_NAME}.session-journal' if corrupted")
                    logger.error(f"  3. Restart the bot (you'll need to re-authenticate)")
                    break
                
                # Ensure client is stopped before attempting unlock
                try:
                    if app.is_connected:
                        await app.stop()
                    await asyncio.sleep(2)  # Give time for cleanup and lock release
                except Exception as stop_error:
                    logger.debug(f"Error stopping client during lock handling: {stop_error}")
                
                is_locked, lock_message = check_session_lock(SESSION_NAME)
                if is_locked:
                    logger.error(lock_message)
                    logger.info("Waiting for session to unlock...")
                    unlocked = await wait_for_session_unlock(SESSION_NAME, max_wait=10)
                    if unlocked:
                        logger.info("Session unlocked! Retrying connection...")
                        await asyncio.sleep(3)  # Longer pause to ensure lock is fully released
                        continue
                    else:
                        logger.warning("Session is still locked. Attempting to force unlock stale lock...")
                        force_unlocked = force_unlock_session(SESSION_NAME)
                        if force_unlocked:
                            logger.info("Stale lock removed! Retrying connection...")
                            await asyncio.sleep(3)  # Longer pause to ensure lock is fully released
                            continue
                        else:
                            logger.error("Session is still locked after force unlock attempt.")
                            logger.error(f"Lock retry count: {lock_retry_count}/{max_lock_retries}")
                            # Continue to retry loop instead of breaking immediately
                            connection_retries += 1
                else:
                    logger.warning(f"Database lock error detected but session check shows unlocked. Retrying...")
                    await asyncio.sleep(3)  # Brief pause before retry
                    continue
            else:
                logger.error(f"Unexpected error: {e}", exc_info=True)
                connection_retries += 1
            
            if connection_retries < max_connection_retries:
                # Exponential backoff: increase delay with each retry
                retry_delay = base_retry_delay * (1.5 ** (connection_retries - 1))
                logger.info(f"Retrying in {retry_delay:.1f} seconds...")
                await asyncio.sleep(retry_delay)
            else:
                logger.error("Max connection retries reached. Exiting...")
                break
        except KeyboardInterrupt:
            logger.info("Stopping client...")
            break
        finally:
            try:
                if app.is_connected:
                    await app.stop()
                logger.info("Client stopped")
            except Exception as e:
                logger.error(f"Error stopping client: {e}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Client stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
