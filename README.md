# Telegram Channel Post Processor

An async Telegram client that listens to posts from a source channel, extracts the first number from each post, divides it by 3.63, and forwards the modified message to a target channel.

Uses **Pyrogram** (MTProto API) with API ID and API Hash instead of Bot Token.

## Features

- ✅ Listens to posts from a specific source channel
- ✅ **No admin rights needed** for source channel - just be a member!
- ✅ Extracts the first number (integer or float) from message text
- ✅ Divides the number by 3.63 and rounds to 2 decimal places
- ✅ Preserves all original formatting, emojis, and line breaks
- ✅ Only modifies the first number found (ignores subsequent numbers)
- ✅ Ignores posts without numbers
- ✅ Full async/await support using Pyrogram
- ✅ Comprehensive error handling and logging
- ✅ Production-ready code
- ✅ Uses Telegram Client API (MTProto) with API ID/API Hash

## Prerequisites

- Python 3.8 or higher
- Telegram API credentials:
  - **API ID** and **API Hash** (get from [https://my.telegram.org/apps](https://my.telegram.org/apps))
- **Source channel**: Your account must be a **member** of the channel (no admin rights needed)
- **Target channel**: Your account must be able to send messages (member for public channels, admin for private channels)

## Installation

1. **Clone or download this repository**

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
   
   **Note:** If you encounter issues installing `tgcrypto` (optional dependency for faster encryption), you can skip it. Pyrogram works fine without it, just slightly slower. If you want to install it later:
   ```bash
   pip install tgcrypto
   ```

3. **Configure environment variables:**
   ```bash
   # Copy the example file
   cp .env.example .env
   
   # Edit .env with your actual values
   # On Windows, you can use notepad or any text editor
   notepad .env
   ```

4. **Fill in your `.env` file:**
   ```
   API_ID=12345678
   API_HASH=your_api_hash_here
   SESSION_NAME=bot_session
   SOURCE_CHANNEL=@source_channel_name
   TARGET_CHANNEL=@target_channel_name
   ```
   
   **Note:** You can use channel usernames (with @) or channel IDs. Usernames are easier to use!

## Getting API Credentials

1. **Get API ID and API Hash:**
   - Go to [https://my.telegram.org/apps](https://my.telegram.org/apps)
   - Log in with your phone number
   - Create a new application (if you haven't already)
   - Copy your **API ID** and **API Hash**
   - Add them to your `.env` file

## Getting Channel Information

**Recommended: Use Channel Usernames**

Simply use the channel username with @ symbol:
- For public channels: `@channel_name`
- Example: `@my_source_channel`

**Alternative: Using Channel IDs**

If you prefer to use channel IDs:

1. Forward a message from your channel to [@userinfobot](https://t.me/userinfobot)
2. The bot will show you the channel ID (usually a negative number like `-1001234567890`)

Alternatively:
- Add [@RawDataBot](https://t.me/RawDataBot) to your channel
- It will show the channel ID in the chat information

**Note:** The bot supports both usernames (with @) and channel IDs. Usernames are recommended as they're easier to use!

## Setup

1. **Ensure access to channels:**
   - **Source channel**: Your account must be a **member** of the channel (just join it, no admin rights needed)
     - For public channels: Simply join using the channel username
     - For private channels: You need to be added as a member
   - **Target channel**: Your account must be able to send messages
     - For public channels: Join the channel (you can send messages as a member)
     - For private channels: You typically need to be an admin with permission to send messages

## Running the Client

**First run:**
```bash
python bot.py
```

On first run, you'll be asked to:
1. Enter your phone number (with country code, e.g., +989123456789)
2. Enter the verification code sent to your Telegram
3. If 2FA is enabled, enter your password

A session file (e.g., `bot_session.session`) will be created. You won't need to log in again on subsequent runs.

**Start the client:**
```bash
python bot.py
```

The client will:
- Log startup information
- Show your logged-in account info
- Begin listening for posts from the source channel
- Process and forward messages automatically

**Stop the client:**
Press `Ctrl+C` to stop the client gracefully.

## How It Works

1. The client connects to Telegram using your API credentials
2. It listens for new posts in the source channel
3. When a post is detected:
   - Extracts the first number found in the text (using regex)
   - Divides that number by 3.63
   - Rounds the result to 2 decimal places
   - Replaces only that number in the original text
   - Sends the modified message to the target channel
4. If no number is found, the post is ignored

## Example

**Input message:**
```
قیمت امروز 7260 تومان است 🔥
```

**Output message:**
```
قیمت امروز 2000.00 تومان است 🔥
```

Calculation: `7260 ÷ 3.63 = 2000.00`

## Logging

The client logs to:
- **Console** (stdout) - for real-time monitoring
- **bot.log** file - for persistent logging

Log levels:
- `INFO`: Normal operations (posts received, messages sent)
- `DEBUG`: Detailed information
- `ERROR`: Errors and exceptions

## Error Handling

The client handles:
- Telegram API errors (network issues, rate limits, FloodWait, etc.)
- Invalid messages (no text, no numbers)
- Configuration errors
- Unexpected exceptions
- Automatic retry on FloodWait errors

All errors are logged with full stack traces for debugging.

## Notes

- The client only processes the **first number** found in each message
- Numbers can be integers or floats (e.g., `123`, `123.45`, `-123`)
- All formatting, emojis, and special characters are preserved
- The client ignores posts that don't contain any numbers
- Both new posts and edited posts are processed
- Session file (`.session`) stores your login - keep it secure and don't share it
- You can use channel usernames (e.g., `@channel`) or IDs in the `.env` file

## Troubleshooting

**Client not receiving messages:**
- Verify your account is a **member** of the source channel (you don't need to be admin)
- Check that `SOURCE_CHANNEL` is correct (use username like `@channel` or channel ID)
- For public channels: Make sure you've joined the channel
- For private channels: Ensure you've been added as a member
- Make sure the username starts with `@` (e.g., `@channel_name`)

**Client not sending messages:**
- For public channels: Verify your account is a member (you can send messages as a member)
- For private channels: You may need to be an admin with permission to send messages
- Check that `TARGET_CHANNEL` is correct (use username like `@channel` or channel ID)
- Ensure you have permission to send messages in the target channel
- Make sure the username starts with `@` (e.g., `@target_channel`)

**Login/Authentication issues:**
- Make sure your API_ID and API_HASH are correct
- Delete the `.session` file and try logging in again
- Check that your phone number format is correct (with country code)

**No numbers being processed:**
- Check the log file for details
- Verify messages contain numbers in a recognizable format
- The regex pattern matches: integers, floats, and negative numbers

## License

This project is provided as-is for educational and personal use.
