from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta
from app.auth import models, otp_model, email_service
from app.core.middleware import generate_token
from app.core.exceptions import ValidationError, AuthenticationError
from app.core.database import get_collection

# Pending registrations expire after 30 minutes
PENDING_REGISTRATION_EXPIRY_MINUTES = 30

def register_user(email, password, phone=None):
    """
    Initiate registration - store pending registration and send OTP.
    User is NOT created in the database until email is verified.
    """
    # Check if email is already registered (verified user)
    if models.find_user_by_email(email):
        raise ValidationError('Email already registered')
    
    # Check for existing pending registration
    pending_coll = get_collection('pending_registrations')
    
    # Delete any existing pending registration for this email
    pending_coll.delete_many({'email': email})
    
    # Hash the password
    password_hash = generate_password_hash(password, method='pbkdf2:sha256')
    
    # Store pending registration
    pending_doc = {
        'email': email,
        'password_hash': password_hash,
        'phone': phone,
        'created_at': datetime.utcnow(),
        'expires_at': datetime.utcnow() + timedelta(minutes=PENDING_REGISTRATION_EXPIRY_MINUTES)
    }
    
    result = pending_coll.insert_one(pending_doc)
    pending_id = str(result.inserted_id)
    
    # Generate and send OTP (user_id is None since user doesn't exist yet)
    otp = otp_model.create_otp(
        user_id=None,
        otp_type=otp_model.OTP_TYPE_EMAIL,
        email=email
    )
    
    # Send OTP email
    email_service.send_otp_email(email, otp['code'])
    
    return {
        'message': 'Registration initiated. Please verify your email.',
        'pending_id': pending_id,
        'email': email,
        'requires_verification': True
    }

def verify_email_otp(email, code):
    """
    Verify email OTP and complete registration.
    Creates the user in the database only after successful verification.
    """
    if not otp_model.verify_otp(email, code, otp_model.OTP_TYPE_EMAIL):
        raise ValidationError('Invalid or expired OTP')
    
    # Get pending registration
    pending_coll = get_collection('pending_registrations')
    pending_doc = pending_coll.find_one({
        'email': email,
        'expires_at': {'$gt': datetime.utcnow()}
    })
    
    if not pending_doc:
        raise ValidationError('Registration expired. Please register again.')
    
    # Check if user was created in the meantime (race condition)
    if models.find_user_by_email(email):
        pending_coll.delete_one({'_id': pending_doc['_id']})
        raise ValidationError('Email already registered')
    
    # Now create the actual user
    user_doc = models.create_user_from_pending(
        email=pending_doc['email'],
        password_hash=pending_doc['password_hash'],
        phone=pending_doc.get('phone'),
        email_verified=True
    )
    
    # Delete the pending registration
    pending_coll.delete_one({'_id': pending_doc['_id']})
    
    # Generate token
    token = generate_token(user_doc['_id'])
    
    return {
        'token': token,
        'user': models.to_response(user_doc),
        'message': 'Email verified successfully. Welcome!'
    }

def resend_otp(email):
    """
    Resend OTP to email for pending registration
    """
    # Check for pending registration
    pending_coll = get_collection('pending_registrations')
    pending_doc = pending_coll.find_one({
        'email': email,
        'expires_at': {'$gt': datetime.utcnow()}
    })
    
    if not pending_doc:
        # Also check if user exists but is unverified (for backward compatibility)
        user_doc = models.find_user_by_email(email)
        if not user_doc:
            raise ValidationError('No pending registration found. Please register again.')
        
        if user_doc.get('email_verified'):
            raise ValidationError('Email already verified')
        
        # Legacy unverified user - send OTP
        otp = otp_model.create_otp(
            user_id=str(user_doc['_id']),
            otp_type=otp_model.OTP_TYPE_EMAIL,
            email=email
        )
        email_service.send_otp_email(email, otp['code'])
        return {'message': 'OTP sent to your email'}
    
    # Generate new OTP for pending registration
    otp = otp_model.create_otp(
        user_id=None,
        otp_type=otp_model.OTP_TYPE_EMAIL,
        email=email
    )
    
    # Send OTP email
    email_service.send_otp_email(email, otp['code'])
    
    return {'message': 'OTP sent to your email'}

def login_user(email, password):
    user_doc = models.find_user_by_email(email)
    if not user_doc:
        # Check if there's a pending registration
        pending_coll = get_collection('pending_registrations')
        pending_doc = pending_coll.find_one({
            'email': email,
            'expires_at': {'$gt': datetime.utcnow()}
        })
        
        if pending_doc:
            # Resend OTP for pending registration
            otp = otp_model.create_otp(
                user_id=None,
                otp_type=otp_model.OTP_TYPE_EMAIL,
                email=email
            )
            email_service.send_otp_email(email, otp['code'])
            raise AuthenticationError('Email not verified. A new OTP has been sent to your email.')
        
        raise AuthenticationError('Invalid email or password')
    
    if not models.verify_password(user_doc, password):
        raise AuthenticationError('Invalid email or password')
    
    if not user_doc.get('is_active', True):
        raise AuthenticationError('Account is disabled')
    
    # Check email verification
    if not user_doc.get('email_verified', False):
        # Send new OTP
        otp = otp_model.create_otp(
            user_id=str(user_doc['_id']),
            otp_type=otp_model.OTP_TYPE_EMAIL,
            email=email
        )
        email_service.send_otp_email(email, otp['code'])
        
        raise AuthenticationError('Email not verified. A new OTP has been sent to your email.')
    
    token = generate_token(user_doc['_id'])
    return {
        'token': token,
        'user': models.to_response(user_doc)
    }

def cleanup_expired_pending_registrations():
    """Remove expired pending registrations (can be run as a background task)"""
    pending_coll = get_collection('pending_registrations')
    pending_coll.delete_many({'expires_at': {'$lt': datetime.utcnow()}})
