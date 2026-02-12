"""
Test script to check if we can send messages to TARGET_CHANNEL
"""
import asyncio
import os
import sys

# Fix encoding for Windows console
if sys.platform == 'win32':
    try:
        import codecs
        if hasattr(sys.stdout, 'buffer') and hasattr(sys.stdout, 'encoding'):
            if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
                sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        if hasattr(sys.stderr, 'buffer') and hasattr(sys.stderr, 'encoding'):
            if sys.stderr.encoding and sys.stderr.encoding.lower() != 'utf-8':
                sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
    except (AttributeError, LookupError, ValueError):
        pass

from dotenv import load_dotenv

load_dotenv()

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
SESSION_NAME = os.getenv("SESSION_NAME", "bot_session")
TARGET_CHANNEL = os.getenv("TARGET_CHANNEL")

if not API_ID or not API_HASH or not TARGET_CHANNEL:
    print("Error: Missing required environment variables!")
    print("Make sure API_ID, API_HASH, and TARGET_CHANNEL are set in .env file")
    sys.exit(1)

try:
    API_ID = int(API_ID)
except ValueError:
    print("Error: API_ID must be a valid integer")
    sys.exit(1)

# Normalize channel identifier
def normalize_channel(channel: str):
    channel = channel.strip()
    if channel.startswith('@'):
        return channel
    try:
        return int(channel)
    except ValueError:
        return f"@{channel}" if not channel.startswith('@') else channel

TARGET_CHANNEL = normalize_channel(TARGET_CHANNEL)

async def test_target_channel():
    """Test if we can access and send messages to TARGET_CHANNEL"""
    # Import here to avoid event loop issues
    from pyrogram import Client
    from pyrogram.errors import (
        ChatWriteForbidden,
        ChannelPrivate,
        UsernameNotOccupied,
        PeerIdInvalid,
        UserBannedInChannel,
        RPCError
    )
    
    app = Client(
        name=SESSION_NAME,
        api_id=API_ID,
        api_hash=API_HASH,
        workdir=".",
    )
    
    try:
        await app.start()
        print("=" * 60)
        print("Testing TARGET_CHANNEL Access")
        print("=" * 60)
        
        me = await app.get_me()
        print(f"\nLogged in as: {me.first_name} (@{me.username or 'N/A'})")
        print(f"Target Channel: {TARGET_CHANNEL}\n")
        
        # Test 1: Check if channel exists and is accessible
        print("Test 1: Checking channel access...")
        try:
            target_chat = await app.get_chat(TARGET_CHANNEL)
            print(f"[OK] Channel found: {target_chat.title}")
            print(f"     Channel ID: {target_chat.id}")
            print(f"     Username: @{target_chat.username or 'N/A'}")
            print(f"     Type: {target_chat.type}")
        except ChannelPrivate as e:
            print(f"[ERROR] Channel is private: {e}")
            print("        Solution: Join the channel or ask to be added as a member/admin")
            return
        except UsernameNotOccupied as e:
            print(f"[ERROR] Channel username not found: {e}")
            print("        Solution: Check the channel username in your .env file")
            return
        except PeerIdInvalid as e:
            print(f"[ERROR] Invalid channel ID/username: {e}")
            print("        Solution: Check the channel identifier in your .env file")
            return
        except Exception as e:
            print(f"[ERROR] Cannot access channel: {e}")
            return
        
        # Test 2: Check member status
        print("\nTest 2: Checking member status...")
        try:
            member = await app.get_chat_member(TARGET_CHANNEL, me.id)
            print(f"[OK] Member status: {member.status}")
            if member.status == "restricted":
                print("     [WARNING] Your account is restricted in this channel")
                if hasattr(member, 'permissions'):
                    perms = member.permissions
                    print(f"     Can send messages: {perms.can_send_messages if hasattr(perms, 'can_send_messages') else 'Unknown'}")
            elif member.status == "left":
                print("     [ERROR] You are not a member of this channel")
                print("     Solution: Join the channel first")
                return
            elif member.status == "kicked":
                print("     [ERROR] You are banned from this channel")
                print("     Solution: Contact channel admin to unban you")
                return
        except Exception as e:
            print(f"[WARNING] Could not check member status: {e}")
        
        # Test 3: Try to send a test message
        print("\nTest 3: Testing message send capability...")
        test_message = "🧪 Test message from bot - If you see this, the bot can send messages!"
        try:
            sent_msg = await app.send_message(
                chat_id=TARGET_CHANNEL,
                text=test_message
            )
            print(f"[OK] Test message sent successfully!")
            print(f"     Message ID: {sent_msg.id}")
            print(f"     You should see the test message in the channel now.")
            print(f"\n     [NOTE] You can delete this test message from the channel.")
        except ChatWriteForbidden as e:
            print(f"[ERROR] Cannot write to channel: ChatWriteForbidden")
            print("        This means you don't have permission to send messages.")
            print("        Solutions:")
            print("        - For public channels: Make sure you joined the channel")
            print("        - For private channels: You need to be an admin with 'Post Messages' permission")
            print("        - Check if the channel allows members to post")
            return
        except UserBannedInChannel as e:
            print(f"[ERROR] You are banned from this channel: {e}")
            print("        Solution: Contact channel admin to unban you")
            return
        except ChannelPrivate as e:
            print(f"[ERROR] Channel is private: {e}")
            print("        Solution: Join the channel or ask to be added")
            return
        except RPCError as e:
            print(f"[ERROR] Telegram RPC error: {e}")
            print(f"        Error code: {e.ID if hasattr(e, 'ID') else 'Unknown'}")
            return
        except Exception as e:
            print(f"[ERROR] Unexpected error: {type(e).__name__}: {e}")
            return
        
        print("\n" + "=" * 60)
        print("[SUCCESS] All tests passed! The bot should be able to send messages.")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n[FATAL ERROR] {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
    finally:
        try:
            if app.is_connected:
                await app.stop()
        except:
            pass

if __name__ == "__main__":
    try:
        # Fix for Python 3.14+ event loop handling
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        loop.run_until_complete(test_target_channel())
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
    except Exception as e:
        print(f"\n[FATAL ERROR] {e}")
        import traceback
        traceback.print_exc()
