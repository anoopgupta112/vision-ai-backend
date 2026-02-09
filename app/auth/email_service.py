"""
Email service for sending OTP and notifications via Gmail SMTP
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from flask import current_app

def get_smtp_config():
    """Get SMTP configuration from environment"""
    return {
        'host': os.environ.get('SMTP_HOST', 'smtp.gmail.com'),
        'port': int(os.environ.get('SMTP_PORT', 587)),
        'user': os.environ.get('SMTP_USER', ''),
        'password': os.environ.get('SMTP_PASSWORD', ''),
        'from_name': os.environ.get('SMTP_FROM_NAME', 'Lead Gen Platform')
    }

def send_email(to_email: str, subject: str, body_html: str) -> bool:
    """
    Send an email via SMTP
    
    Args:
        to_email: Recipient email address
        subject: Email subject
        body_html: HTML body content
        
    Returns:
        True if sent successfully, False otherwise
    """
    config = get_smtp_config()
    
    print(f"[EMAIL] Attempting to send email to: {to_email}")
    print(f"[EMAIL] SMTP User: {config['user']}")
    print(f"[EMAIL] SMTP Host: {config['host']}:{config['port']}")
    
    if not config['user'] or not config['password']:
        print("[EMAIL] ERROR: SMTP not configured, missing user or password")
        try:
            current_app.logger.warning('SMTP not configured, skipping email send')
        except:
            pass
        return False
    
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = f"{config['from_name']} <{config['user']}>"
        msg['To'] = to_email
        
        # Attach HTML body
        msg.attach(MIMEText(body_html, 'html'))
        
        # Connect and send
        print(f"[EMAIL] Connecting to SMTP server...")
        with smtplib.SMTP(config['host'], config['port']) as server:
            server.starttls()
            print(f"[EMAIL] Logging in...")
            server.login(config['user'], config['password'])
            print(f"[EMAIL] Sending email...")
            server.sendmail(config['user'], to_email, msg.as_string())
        
        print(f"[EMAIL] SUCCESS: Email sent to {to_email}")
        return True
        
    except Exception as e:
        print(f"[EMAIL] FAILED: {str(e)}")
        try:
            current_app.logger.error(f'Failed to send email: {str(e)}')
        except:
            pass
        return False

def send_otp_email(to_email: str, otp_code: str) -> bool:
    """Send OTP verification email"""
    subject = "Your Verification Code"
    
    body_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .otp-box {{ 
                background: #f5f5f5; 
                border-radius: 8px; 
                padding: 20px; 
                text-align: center; 
                margin: 20px 0;
            }}
            .otp-code {{ 
                font-size: 32px; 
                font-weight: bold; 
                color: #6366f1; 
                letter-spacing: 4px;
            }}
            .footer {{ color: #666; font-size: 12px; margin-top: 20px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>Email Verification</h2>
            <p>Use the following code to verify your email address:</p>
            <div class="otp-box">
                <span class="otp-code">{otp_code}</span>
            </div>
            <p>This code will expire in <strong>10 minutes</strong>.</p>
            <p>If you didn't request this code, please ignore this email.</p>
            <div class="footer">
                <p>Lead Gen Platform</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    return send_email(to_email, subject, body_html)

def send_credit_request_notification(admin_email: str, user_email: str, amount: int) -> bool:
    """Send notification to admin about credit request"""
    subject = f"Credit Request: {user_email}"
    
    body_html = f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family: Arial, sans-serif;">
        <h2>New Credit Request</h2>
        <p><strong>User:</strong> {user_email}</p>
        <p><strong>Requested Credits:</strong> {amount}</p>
        <p>Please login to the admin dashboard to approve or reject this request.</p>
    </body>
    </html>
    """
    
    return send_email(admin_email, subject, body_html)
