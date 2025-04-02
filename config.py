import os
from dotenv import load_dotenv

# Load environment variables from .env file (for local development)
load_dotenv()

# Bot Configuration
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
API_ID = os.environ.get("API_ID", "")
API_HASH = os.environ.get("API_HASH", "")

# MongoDB Configuration
MONGODB_URI = os.environ.get("MONGODB_URI", "")

# Admin Configuration
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "")

# Premium Channel Configuration
PREMIUM_CHANNELS = {
    "study_data_1": {
        "name": "Study Data 1",
        "channel_id": os.environ.get("CHANNEL_ID_1", ""),
        "price": 499,
        "validity_days": 30,
        "description": "Complete study material for beginners",
        "preview_images": [
            "https://example.com/channel1_preview1.jpg",
            "https://example.com/channel1_preview2.jpg"
        ]
    },
    "study_data_2": {
        "name": "Study Data 2",
        "channel_id": os.environ.get("CHANNEL_ID_2", ""),
        "price": 699,
        "validity_days": 45,
        "description": "Advanced study resources for intermediate level",
        "preview_images": [
            "https://example.com/channel2_preview1.jpg",
            "https://example.com/channel2_preview2.jpg"
        ]
    },
    "study_data_3": {
        "name": "Study Data 3",
        "channel_id": os.environ.get("CHANNEL_ID_3", ""),
        "price": 899,
        "validity_days": 60,
        "description": "Premium materials for advanced students",
        "preview_images": [
            "https://example.com/channel3_preview1.jpg",
            "https://example.com/channel3_preview2.jpg"
        ]
    },
    "study_data_4": {
        "name": "Study Data 4",
        "channel_id": os.environ.get("CHANNEL_ID_4", ""),
        "price": 1099,
        "validity_days": 90,
        "description": "Expert level materials with practice sets",
        "preview_images": [
            "https://example.com/channel4_preview1.jpg",
            "https://example.com/channel4_preview2.jpg"
        ]
    },
    "study_data_5": {
        "name": "Study Data 5",
        "channel_id": os.environ.get("CHANNEL_ID_5", ""),
        "price": 1499,
        "validity_days": 120,
        "description": "Complete preparation package with mock tests",
        "preview_images": [
            "https://example.com/channel5_preview1.jpg",
            "https://example.com/channel5_preview2.jpg"
        ]
    },
    "study_data_6": {
        "name": "Study Data 6",
        "channel_id": os.environ.get("CHANNEL_ID_6", ""),
        "price": 1999,
        "validity_days": 180,
        "description": "Comprehensive package with personal guidance",
        "preview_images": [
            "https://example.com/channel6_preview1.jpg",
            "https://example.com/channel6_preview2.jpg"
        ]
    }
}

# Payment Configuration
PAYMENT_METHODS = {
    "upi_id": "example@upi",
    "qr_code_url": "https://example.com/qr-code.png"
}

# Reminder Configuration (days before expiry)
REMINDER_DAYS = 3
