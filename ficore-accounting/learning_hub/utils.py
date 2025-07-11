from flask import session, g
from flask_login import current_user

def trans(key, default, lang=None):
    """Placeholder translation function."""
    # Implement translation logic or import from main app
    return default

def get_mongo_db():
    """Placeholder MongoDB connection function."""
    # Implement MongoDB connection or import from main app
    from pymongo import MongoClient
    if not hasattr(g, 'db'):
        g.db = MongoClient('mongodb://localhost:27017/')['database_name']
    return g.db

def log_tool_usage(db, tool_name, user_id, session_id, action):
    """Placeholder for logging tool usage."""
    pass

def create_anonymous_session():
    """Create an anonymous session."""
    import uuid
    session['sid'] = str(uuid.uuid4())
    session['is_anonymous'] = True

def requires_role(roles):
    """Decorator to check user roles."""
    from functools import wraps
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or current_user.role not in roles:
                return redirect(url_for('personal.index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def is_admin():
    """Check if user is admin."""
    return current_user.is_authenticated and current_user.role == 'admin'

def format_currency(amount, currency='NGN'):
    """Format currency."""
    return f"{currency} {amount:,.2f}"

def clean_currency(amount):
    """Clean currency string to float."""
    if isinstance(amount, str):
        return float(amount.replace(',', '').split()[-1])
    return float(amount)

PERSONAL_TOOLS = [
    {'endpoint': 'personal.index', 'title_key': 'personal_home', 'title': 'Home'},
    {'endpoint': 'learning_hub.main', 'title_key': 'learning_hub_title', 'title': 'Learning Hub'}
]

ALL_TOOLS = PERSONAL_TOOLS + [
    {'endpoint': 'admin.dashboard', 'title_key': 'admin_dashboard', 'title': 'Admin Dashboard'}
]

PERSONAL_NAV = [
    {'endpoint': 'personal.index', 'title_key': 'personal_home', 'title': 'Home'},
    {'endpoint': 'learning_hub.main', 'title_key': 'learning_hub_title', 'title': 'Learning Hub'}
]

ADMIN_NAV = PERSONAL_NAV + [
    {'endpoint': 'admin.dashboard', 'title_key': 'admin_dashboard', 'title': 'Admin Dashboard'}
]