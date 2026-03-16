import os
import sys

# Ensure we can import from app
sys.path.append(os.getcwd())

from app import create_app
from app.core.database import get_collection

def list_admins():
    app = create_app()
    with app.app_context():
        users = get_collection('users')
        admins = users.find({'is_admin': True})
        print("-" * 30)
        print("Admin Users Found:")
        print("-" * 30)
        found = False
        for admin in admins:
            found = True
            print(f"Email : {admin.get('email')}")
            # Passwords are hashed, so we cannot show them.
        
        if not found:
            print("No admin users found.")
        print("-" * 30)

if __name__ == '__main__':
    list_admins()
