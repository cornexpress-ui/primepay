import datetime
from pymongo import MongoClient
from config import MONGODB_URI

client = MongoClient(MONGODB_URI)
db = client.premium_channel_bot

# Collections
users = db.users
subscriptions = db.subscriptions
payments = db.payments


def get_user(user_id):
    """Get user from database or create if not exists"""
    user = users.find_one({"user_id": user_id})
    if not user:
        user = {
            "user_id": user_id,
            "username": None,
            "first_name": None,
            "last_name": None,
            "created_at": datetime.datetime.utcnow(),
            "is_active": True
        }
        users.insert_one(user)
    return user


def update_user(user_id, data):
    """Update user information"""
    users.update_one(
        {"user_id": user_id},
        {"$set": data}
    )


def create_payment(user_id, channel_id, amount, payment_method, reference=None):
    """Create a new payment record"""
    payment = {
        "user_id": user_id,
        "channel_id": channel_id,
        "amount": amount,
        "payment_method": payment_method,
        "reference": reference,
        "status": "pending",
        "screenshot_file_id": None,
        "created_at": datetime.datetime.utcnow(),
        "updated_at": datetime.datetime.utcnow()
    }
    return payments.insert_one(payment).inserted_id


def update_payment(payment_id, data):
    """Update payment information"""
    payments.update_one(
        {"_id": payment_id},
        {"$set": {**data, "updated_at": datetime.datetime.utcnow()}}
    )


def get_pending_payments():
    """Get all pending payments"""
    return list(payments.find({"status": "pending"}))


def create_subscription(user_id, channel_id, expires_at):
    """Create a new subscription"""
    subscription = {
        "user_id": user_id,
        "channel_id": channel_id,
        "status": "active",
        "created_at": datetime.datetime.utcnow(),
        "expires_at": expires_at
    }
    return subscriptions.insert_one(subscription).inserted_id


def update_subscription(subscription_id, data):
    """Update subscription information"""
    subscriptions.update_one(
        {"_id": subscription_id},
        {"$set": data}
    )


def get_user_subscriptions(user_id):
    """Get all subscriptions for a user"""
    return list(subscriptions.find({"user_id": user_id}))


def get_expiring_subscriptions(days):
    """Get subscriptions that expire in the specified number of days"""
    expiry_date = datetime.datetime.utcnow() + datetime.timedelta(days=days)
    start_date = expiry_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_date = expiry_date.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    return list(subscriptions.find({
        "status": "active",
        "expires_at": {"$gte": start_date, "$lte": end_date}
    }))


def get_expired_subscriptions():
    """Get all expired subscriptions that are still active"""
    now = datetime.datetime.utcnow()
    return list(subscriptions.find({
        "status": "active",
        "expires_at": {"$lt": now}
    }))
