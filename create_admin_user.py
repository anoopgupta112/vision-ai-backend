import os
import sys
from datetime import datetime

# Ensure we can import from app
sys.path.append(os.getcwd())

from app import create_app
from app.core.database import get_collection
from werkzeug.security import generate_password_hash

def create_admin(email, password):
    app = create_app()
    with app.app_context():
        users = get_collection('users')
        existing_user = users.find_one({'email': email})
        
        hashed_pw = generate_password_hash(password, method='pbkdf2:sha256')
        
        if existing_user:
            users.update_one(
                {'_id': existing_user['_id']},
                {'$set': {
                    'password_hash': hashed_pw,
                    'is_admin': True,
                    'is_active': True,
                    'updated_at': datetime.utcnow()
                }}
            )
            print(f"Updated existing user {email}. Reset password and set as Admin.")
        else:
            new_user = {
                'email': email,
                'password_hash': hashed_pw,
                'is_admin': True,
                'is_active': True,
                'created_at': datetime.utcnow(),
                'updated_at': datetime.utcnow()
            }
            users.insert_one(new_user)
            print(f"Created new Admin user {email}.")

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python create_admin_user.py <email> <password>")
        sys.exit(1)
    
    create_admin(sys.argv[1], sys.argv[2])
