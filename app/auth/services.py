from app.auth import models, otp_model, email_service
from app.core.middleware import generate_token
from app.core.exceptions import ValidationError, AuthenticationError

def register_user(email, password, phone=None):
    """
    Register a new user and send OTP for email verification
    """
    if models.find_user_by_email(email):
        raise ValidationError('Email already registered')
    
    # Create user (unverified)
    user_doc = models.create_user(email, password, phone)
    
    # Generate and send OTP
    otp = otp_model.create_otp(
        user_id=str(user_doc['_id']),
        otp_type=otp_model.OTP_TYPE_EMAIL,
        email=email
    )
    
    # Send OTP email
    email_service.send_otp_email(email, otp['code'])
    
    return {
        'message': 'Registration successful. Please verify your email.',
        'user_id': str(user_doc['_id']),
        'email': email,
        'requires_verification': True
    }

def verify_email_otp(email, code):
    """
    Verify email OTP and mark user as verified
    """
    if not otp_model.verify_otp(email, code, otp_model.OTP_TYPE_EMAIL):
        raise ValidationError('Invalid or expired OTP')
    
    user_doc = models.find_user_by_email(email)
    if not user_doc:
        raise ValidationError('User not found')
    
    # Mark email as verified
    models.update_user(str(user_doc['_id']), {'email_verified': True})
    
    # Generate token
    token = generate_token(user_doc['_id'])
    user_doc['email_verified'] = True
    
    return {
        'token': token,
        'user': models.to_response(user_doc),
        'message': 'Email verified successfully'
    }

def resend_otp(email):
    """
    Resend OTP to email
    """
    user_doc = models.find_user_by_email(email)
    if not user_doc:
        raise ValidationError('Email not found')
    
    if user_doc.get('email_verified'):
        raise ValidationError('Email already verified')
    
    # Generate new OTP
    otp = otp_model.create_otp(
        user_id=str(user_doc['_id']),
        otp_type=otp_model.OTP_TYPE_EMAIL,
        email=email
    )
    
    # Send OTP email
    email_service.send_otp_email(email, otp['code'])
    
    return {'message': 'OTP sent to your email'}

def login_user(email, password):
    user_doc = models.find_user_by_email(email)
    if not user_doc:
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

