"""
Razorpay payment service - handles payment gateway operations
"""
import razorpay
import hmac
import hashlib
from flask import current_app
from app.core.config import Config

# Credit packages configuration
CREDIT_PACKAGES = {
    'starter': {'credits': 100, 'amount': 9900, 'name': 'Starter Pack'},      # ₹99
    'basic': {'credits': 500, 'amount': 39900, 'name': 'Basic Pack'},          # ₹399
    'pro': {'credits': 1000, 'amount': 69900, 'name': 'Pro Pack'},             # ₹699
    'enterprise': {'credits': 5000, 'amount': 299900, 'name': 'Enterprise Pack'}  # ₹2999
}

def get_razorpay_client():
    """Get Razorpay client instance"""
    return razorpay.Client(auth=(Config.RAZORPAY_KEY_ID, Config.RAZORPAY_KEY_SECRET))

def get_packages():
    """Get available credit packages"""
    return [
        {
            'id': pkg_id,
            'name': pkg['name'],
            'credits': pkg['credits'],
            'amount': pkg['amount'],
            'display_amount': f"₹{pkg['amount'] // 100}"
        }
        for pkg_id, pkg in CREDIT_PACKAGES.items()
    ]

def create_order(package_id: str, user_id: str):
    """
    Create a Razorpay order for a credit package
    
    Args:
        package_id: ID of the credit package
        user_id: ID of the user making the purchase
        
    Returns:
        Order details including order_id
    """
    if package_id not in CREDIT_PACKAGES:
        raise ValueError(f"Invalid package ID: {package_id}")
    
    package = CREDIT_PACKAGES[package_id]
    client = get_razorpay_client()
    
    order_data = {
        'amount': package['amount'],  # Amount in paise
        'currency': 'INR',
        'receipt': f"order_{user_id}_{package_id}",
        'notes': {
            'user_id': user_id,
            'package_id': package_id,
            'credits': str(package['credits'])
        }
    }
    
    order = client.order.create(data=order_data)
    
    return {
        'order_id': order['id'],
        'amount': order['amount'],
        'currency': order['currency'],
        'key_id': Config.RAZORPAY_KEY_ID,
        'package': {
            'id': package_id,
            'name': package['name'],
            'credits': package['credits']
        }
    }

def verify_payment_signature(razorpay_order_id: str, razorpay_payment_id: str, razorpay_signature: str) -> bool:
    """
    Verify the payment signature from Razorpay callback
    
    Args:
        razorpay_order_id: Order ID from Razorpay
        razorpay_payment_id: Payment ID from Razorpay
        razorpay_signature: Signature from Razorpay
        
    Returns:
        True if signature is valid, False otherwise
    """
    client = get_razorpay_client()
    
    try:
        client.utility.verify_payment_signature({
            'razorpay_order_id': razorpay_order_id,
            'razorpay_payment_id': razorpay_payment_id,
            'razorpay_signature': razorpay_signature
        })
        return True
    except razorpay.errors.SignatureVerificationError:
        return False

def get_order_details(order_id: str):
    """Fetch order details from Razorpay"""
    client = get_razorpay_client()
    return client.order.fetch(order_id)

def get_payment_details(payment_id: str):
    """Fetch payment details from Razorpay"""
    client = get_razorpay_client()
    return client.payment.fetch(payment_id)

def verify_webhook_signature(body: bytes, signature: str) -> bool:
    """
    Verify webhook signature from Razorpay
    
    Args:
        body: Raw request body
        signature: X-Razorpay-Signature header
        
    Returns:
        True if signature is valid
    """
    expected_signature = hmac.new(
        Config.RAZORPAY_WEBHOOK_SECRET.encode(),
        body,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected_signature, signature)
