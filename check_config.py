"""
Quick script to check if .env configuration is correct
"""
import os
from dotenv import load_dotenv

load_dotenv()

print("=" * 50)
print("Checking Configuration...")
print("=" * 50)

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
SOURCE_CHANNEL = os.getenv("SOURCE_CHANNEL")
TARGET_CHANNEL = os.getenv("TARGET_CHANNEL")

print(f"\nAPI_ID: {'✓ Set' if API_ID else '✗ Missing'}")
print(f"API_HASH: {'✓ Set' if API_HASH else '✗ Missing'}")
print(f"\nSOURCE_CHANNEL: {SOURCE_CHANNEL or '✗ Missing'}")
print(f"TARGET_CHANNEL: {TARGET_CHANNEL or '✗ Missing'}")

if SOURCE_CHANNEL:
    if not SOURCE_CHANNEL.startswith('@'):
        print(f"\n⚠ WARNING: SOURCE_CHANNEL should start with @ (e.g., @Hareta_Dollar_Bloe)")
        print(f"   Current value: {SOURCE_CHANNEL}")
    else:
        print(f"✓ SOURCE_CHANNEL format looks correct")

if TARGET_CHANNEL:
    if not TARGET_CHANNEL.startswith('@'):
        print(f"\n⚠ WARNING: TARGET_CHANNEL should start with @ (e.g., @MAMMAD_NEW)")
        print(f"   Current value: {TARGET_CHANNEL}")
    else:
        print(f"✓ TARGET_CHANNEL format looks correct")

print("\n" + "=" * 50)
print("Expected values:")
print(f"  SOURCE_CHANNEL=@Hareta_Dollar_Bloe")
print(f"  TARGET_CHANNEL=@MAMMAD_NEW")
print("=" * 50)
