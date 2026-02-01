import os
import sys

# Ensure we can import from app
sys.path.append(os.getcwd())

from app import create_app
from app.core.database import get_collection

def make_admin(email):
    app = create_app()
    with app.app_context():
        users = get_collection('users')
        user = users.find_one({'email': email})
        
        if not user:
            print(f"User {email} not found")
            return
        
        users.update_one(
            {'_id': user['_id']},
            {'$set': {'is_admin': True}}
        )
        print(f"User {email} is now an admin")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python make_admin.py <email>")
        sys.exit(1)
    
    make_admin(sys.argv[1])
