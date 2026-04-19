"""
Helper script to generate a Pyrogram String Session.
Run this locally, log in, and copy the printed string to your Koyeb environment variables as STRING_SESSION.
"""
import asyncio
from pyrogram import Client
import sys
import os
from dotenv import load_dotenv

load_dotenv()

# Get credentials from .env
API_ID = os.getenv("TELEGRAM_API_ID")
API_HASH = os.getenv("TELEGRAM_API_HASH")

async def main():
    if not API_ID or not API_HASH:
        print("❌ Error: TELEGRAM_API_ID or TELEGRAM_API_HASH not found in .env file.")
        return

    print("===================================================")
    print("Pyrogram String Session Generator")
    print("===================================================")
    print("This script will help you log in and get a session string for cloud deployment.")
    print("Logging in as the UserBot...")
    
    async with Client("temp_session", api_id=int(API_ID), api_hash=API_HASH, phone_number=os.getenv("PHONE_NUMBER")) as app:
        session_string = await app.export_session_string()


        print("\n✅ Session String Generated Successfully!")
        print("---------------------------------------------------")
        print(session_string)
        print("---------------------------------------------------")
        print("\nIMPORTANT: Copy the string above (it starts with B...) and save it.")
        print("Add it to your Koyeb environment variables as STRING_SESSION.")
        print("===================================================")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nOperation cancelled.")
    except Exception as e:
        print(f"\n❌ An error occurred: {e}")
