import re
import logging
import uuid
from datetime import datetime
from flask import session, has_request_context, current_app, url_for
from flask_mail import Mail
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from translations import trans
import requests
from werkzeug.routing import BuildError

# Flask extensions - defined here to avoid having too many files
from flask_login import LoginManager
from flask_session import Session
from flask_wtf.csrf import CSRFProtect
from flask_babel import Babel
from flask_compress import Compress

# Initialize extensions
login_manager = LoginManager()
flask_session = Session()
csrf = CSRFProtect()
babel = Babel()
compress = Compress()
limiter = Limiter(key_func=get_remote_address, default_limits=['200 per day', '50 per hour'], storage_uri='memory://')

# Set up logging with session support
root_logger = logging.getLogger('ficore_app')
root_logger.setLevel(logging.INFO)

class SessionFormatter(logging.Formatter):
    def format(self, record):
        record.session_id = getattr(record, 'session_id', 'no_session_id')
        return super().format(record)

class SessionAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        kwargs['extra'] = kwargs.get('extra', {})
        session_id = 'no-session-id'
        try:
            if has_request_context():
                session_id = session.get('sid', 'no-session-id')
            else:
                session_id = 'no-request-context'
        except Exception as e:
            session_id = 'session-error'
            kwargs['extra']['session_error'] = str(e)
        kwargs['extra']['session_id'] = session_id
        return msg, kwargs

logger = SessionAdapter(root_logger, {})

# Helper function to generate URLs for tools/navigation
def generate_tools_with_urls(tools):
    '''
    Generate a list of tools with resolved URLs.
    
    Args:
        tools: List of dictionaries containing 'endpoint' keys
    
    Returns:
        List of dictionaries with 'url' keys added
    '''
    result = []
    for tool in tools:
        try:
            with current_app.app_context():
                url = url_for(tool['endpoint'], _external=True)
                result.append({**tool, 'url': url})
        except BuildError as e:
            logger.error(f"Failed to generate URL for endpoint {tool.get('endpoint', 'unknown')}: {str(e)}. Ensure endpoint is defined in blueprint.")
            result.append({**tool, 'url': '#'})
        except RuntimeError as e:
            logger.warning(f"Runtime error generating URL for endpoint {tool.get('endpoint', 'unknown')}: {str(e)}")
            result.append({**tool, 'url': '#'})
    return result

# Tool/navigation lists with endpoints
_PERSONAL_TOOLS = [
    {
        "endpoint": "personal.budget.main",
        "label": "Budget",
        "label_key": "budget_budget_planner",
        "description_key": "budget_budget_desc",
        "tooltip_key": "budget_tooltip",
        "icon": "bi-wallet"
    },
    {
        "endpoint": "personal.quiz.main",
        "label": "Quiz",
        "label_key": "quiz_personality_quiz",
        "description_key": "quiz_personality_desc",
        "tooltip_key": "quiz_tooltip",
        "icon": "bi-question-circle"
    },
    {
        "endpoint": "taxation_bp.calculate_tax",
        "label": "Taxation",
        "label_key": "taxation_calculator",
        "description_key": "taxation_calculator_desc",
        "tooltip_key": "taxation_tooltip",
        "icon": "bi-calculator"
    },
    {
        "endpoint": "news_bp.news_list",
        "label": "News",
        "label_key": "news_list",
        "description_key": "news_list_desc",
        "tooltip_key": "news_tooltip",
        "icon": "bi-newspaper"
    },
]

_PERSONAL_NAV = [
    {
        "endpoint": "personal.index",
        "label": "Home",
        "label_key": "general_home",
        "description_key": "general_home_desc",
        "tooltip_key": "general_home_tooltip",
        "icon": "bi-house"
    },
    {
        "endpoint": "personal.budget.main",
        "label": "Budget",
        "label_key": "budget_budget_planner",
        "description_key": "budget_budget_desc",
        "tooltip_key": "budget_tooltip",
        "icon": "bi-wallet"
    },
    {
        "endpoint": "personal.bill.main",
        "label": "Bills",
        "label_key": "bill_bill_planner",
        "description_key": "bill_bill_desc",
        "tooltip_key": "bill_tooltip",
        "icon": "bi-receipt"
    },
    {
        "endpoint": "settings.profile",
        "label": "Profile",
        "label_key": "profile_settings",
        "description_key": "profile_settings_desc",
        "tooltip_key": "profile_tooltip",
        "icon": "bi-person"
    },
]

_PERSONAL_EXPLORE_FEATURES = [
    {
        "endpoint": "personal.budget.main",
        "label": "Budget",
        "label_key": "budget_budget_planner",
        "description_key": "budget_budget_desc",
        "tooltip_key": "budget_tooltip",
        "icon": "bi-wallet"
    },
    {
        "endpoint": "personal.emergency_fund.main",
        "label": "Emergency Fund",
        "label_key": "emergency_fund_calculator",
        "description_key": "emergency_fund_desc",
        "tooltip_key": "emergency_fund_tooltip",
        "icon": "bi-shield"
    },
    
    {
        "endpoint": "coins.history",
        "label": "Coins",
        "label_key": "coins_dashboard",
        "description_key": "coins_dashboard_desc",
        "tooltip_key": "coins_tooltip",
        "icon": "bi-coin"
    },
    {
        "endpoint": "personal.financial_health.main",
        "label": "Financial Health",
        "label_key": "financial_health_calculator",
        "description_key": "financial_health_desc",
        "tooltip_key": "financial_health_tooltip",
        "icon": "bi-heart"
    },
    {
        "endpoint": "personal.net_worth.main",
        "label": "Net Worth",
        "label_key": "net_worth_calculator",
        "description_key": "net_worth_desc",
        "tooltip_key": "net_worth_tooltip",
        "icon": "bi-cash-stack"
    },
    {
        "endpoint": "personal.quiz.main",
        "label": "Quiz",
        "label_key": "quiz_personality_quiz",
        "description_key": "quiz_personality_desc",
        "tooltip_key": "quiz_tooltip",
        "icon": "bi-question-circle"
    },
    {
        "endpoint": "taxation_bp.calculate_tax",
        "label": "Taxation",
        "label_key": "taxation_calculator",
        "description_key": "taxation_calculator_desc",
        "tooltip_key": "taxation_tooltip",
        "icon": "bi-calculator"
    },
    {
        "endpoint": "news_bp.news_list",
        "label": "News",
        "label_key": "news_list",
        "description_key": "news_list_desc",
        "tooltip_key": "news_tooltip",
        "icon": "bi-newspaper"
    },
    
    {
        "endpoint": "personal.bill.main",
        "label": "Bills",
        "label_key": "bill_bill_planner",
        "description_key": "bill_bill_desc",
        "tooltip_key": "bill_tooltip",
        "icon": "bi-receipt"
    },
]

_BUSINESS_TOOLS = [
    {
        "endpoint": "inventory.index",
        "label": "Inventory",
        "label_key": "inventory_dashboard",
        "description_key": "inventory_dashboard_desc",
        "tooltip_key": "inventory_tooltip",
        "icon": "bi-box"
    },
    {
        "endpoint": "creditors.index",
        "label": "I Owe",
        "label_key": "creditors_dashboard",
        "description_key": "creditors_dashboard_desc",
        "tooltip_key": "creditors_tooltip",
        "icon": "bi-person-lines"
    },
    
    {
        "endpoint": "taxation_bp.calculate_tax",
        "label": "Taxation",
        "label_key": "taxation_calculator",
        "description_key": "taxation_calculator_desc",
        "tooltip_key": "taxation_tooltip",
        "icon": "bi-calculator"
    },
]

_BUSINESS_EXPLORE_FEATURES = [
    {
        "endpoint": "inventory.index",
        "label": "Inventory",
        "label_key": "inventory_dashboard",
        "description_key": "inventory_dashboard_desc",
        "tooltip_key": "inventory_tooltip",
        "icon": "bi-box"
    },
    
    {
        "endpoint": "coins.history",
        "label": "Coins",
        "label_key": "coins_dashboard",
        "description_key": "coins_dashboard_desc",
        "tooltip_key": "coins_tooltip",
        "icon": "bi-coin"
    },
    {
        "endpoint": "taxation_bp.calculate_tax",
        "label": "Taxation",
        "label_key": "taxation_calculator",
        "description_key": "taxation_calculator_desc",
        "tooltip_key": "taxation_tooltip",
        "icon": "bi-calculator"
    },
    
    {
        "endpoint": "debtors.index",
        "label": "They Owe",
        "label_key": "debtors_dashboard",
        "description_key": "debtors_dashboard_desc",
        "tooltip_key": "debtors_tooltip",
        "icon": "bi-person-plus"
    },
    
    {
        "endpoint": "taxation_bp.calculate_tax",
        "label": "Taxation",
        "label_key": "taxation_calculator",
        "description_key": "taxation_calculator_desc",
        "tooltip_key": "taxation_tooltip",
        "icon": "bi-calculator"
    },
    
    {
        "endpoint": "news_bp.news_list",
        "label": "News",
        "label_key": "news_list",
        "description_key": "news_list_desc",
        "tooltip_key": "news_tooltip",
        "icon": "bi-newspaper"
    },
    {
        "endpoint": "receipts.index",
        "label": "MoneyIn",
        "label_key": "receipts_dashboard",
        "description_key": "receipts_dashboard",
        "tooltip_key": "receipts_tooltip",
        "icon": "bi-cash-coin"
    },

    {"endpoint": "payments.index",
     "label": "MoneyOut",
     "label_key": "payments_dashboard",
     "description_key": "payments_dashboard",
     "tooltip_key": "payments_tooltip",
     "icon": "bi-person-minus"
    
    },
]

_BUSINESS_NAV = [
    {
        "endpoint": "general_bp.home",
        "label": "Home",
        "label_key": "general_business_home",
        "description_key": "general_business_home_desc",
        "tooltip_key": "general_business_home_tooltip",
        "icon": "bi-house"
    },
    {
        "endpoint": "debtors.index",
        "label": "They Owe",
        "label_key": "debtors_dashboard",
        "description_key": "debtors_dashboard_desc",
        "tooltip_key": "debtors_tooltip",
        "icon": "bi-person-plus"
    },
    {
        "endpoint": "inventory.index",
        "label": "Inventory",
        "label_key": "inventory_dashboard",
        "description_key": "inventory_dashboard_desc",
        "tooltip_key": "inventory_tooltip",
        "icon": "bi-box"
    },
    
    {
        "endpoint": "settings.profile",
        "label": "Profile",
        "label_key": "profile_settings",
        "description_key": "profile_settings_desc",
        "tooltip_key": "profile_tooltip",
        "icon": "bi-person"
    },
]

_AGENT_TOOLS = [
    {
        "endpoint": "agents_bp.agent_portal",
        "label": "Agent Portal",
        "label_key": "agents_dashboard",
        "description_key": "agents_dashboard_desc",
        "tooltip_key": "agents_tooltip",
        "icon": "bi-person-workspace"
    },
    {
        "endpoint": "coins.history",
        "label": "Coins",
        "label_key": "coins_dashboard",
        "description_key": "coins_dashboard_desc",
        "tooltip_key": "coins_tooltip",
        "icon": "bi-coin"
    },
    {
        "endpoint": "news_bp.news_list",
        "label": "News",
        "label_key": "news_list",
        "description_key": "news_list_desc",
        "tooltip_key": "news_tooltip",
        "icon": "bi-newspaper"
    },
]

_AGENT_NAV = [
    {
        "endpoint": "agents_bp.agent_portal",
        "label": "Agent Portal",
        "label_key": "agents_dashboard",
        "description_key": "agents_dashboard_desc",
        "tooltip_key": "agents_tooltip",
        "icon": "bi-person-workspace"
    },
    {
        "endpoint": "agents_bp.agent_portal",
        "label": "My Activity",
        "label_key": "agents_my_activity",
        "description_key": "agents_my_activity_desc",
        "tooltip_key": "agents_my_activity_tooltip",
        "icon": "bi-person-workspace"
    },
    {
        "endpoint": "settings.profile",
        "label": "Profile",
        "label_key": "profile_settings",
        "description_key": "profile_settings_desc",
        "tooltip_key": "profile_tooltip",
        "icon": "bi-person"
    },
]

_AGENT_EXPLORE_FEATURES = [
    {
        "endpoint": "agents_bp.agent_portal",
        "label": "Agent Portal",
        "label_key": "agents_dashboard",
        "description_key": "agents_dashboard_desc",
        "tooltip_key": "agents_tooltip",
        "icon": "bi-person-workspace"
    },
    {
        "endpoint": "coins.history",
        "label": "Coins",
        "label_key": "coins_dashboard",
        "description_key": "coins_dashboard_desc",
        "tooltip_key": "coins_tooltip",
        "icon": "bi-coin"
    },
    {
        "endpoint": "news_bp.news_list",
        "label": "News",
        "label_key": "news_list",
        "description_key": "news_list_desc",
        "tooltip_key": "news_tooltip",
        "icon": "bi-newspaper"
    },
]

_ADMIN_TOOLS = [
    {
        "endpoint": "admin.dashboard",
        "label": "Dashboard",
        "label_key": "admin_dashboard",
        "description_key": "admin_dashboard_desc",
        "tooltip_key": "admin_dashboard_tooltip",
        "icon": "bi-speedometer"
    },
    {
        "endpoint": "admin.manage_users",
        "label": "Manage Users",
        "label_key": "admin_manage_users",
        "description_key": "admin_manage_users_desc",
        "tooltip_key": "admin_manage_users_tooltip",
        "icon": "bi-people"
    },
    {
        "endpoint": "admin.credit_coins",
        "label": "Credit Coins",
        "label_key": "admin_credit_coins",
        "description_key": "admin_credit_coins_desc",
        "tooltip_key": "admin_credit_coins_tooltip",
        "icon": "bi-coin"
    },
]

_ADMIN_NAV = [
    {
        "endpoint": "admin.dashboard",
        "label": "Dashboard",
        "label_key": "admin_dashboard",
        "description_key": "admin_dashboard_desc",
        "tooltip_key": "admin_dashboard_tooltip",
        "icon": "bi-speedometer"
    },
    {
        "endpoint": "admin.manage_users",
        "label": "Manage Users",
        "label_key": "admin_manage_users",
        "description_key": "admin_manage_users_desc",
        "tooltip_key": "admin_manage_users_tooltip",
        "icon": "bi-people"
    },
    {
        "endpoint": "admin.credit_coins",
        "label": "Credit Coins",
        "label_key": "admin_credit_coins",
        "description_key": "admin_credit_coins_desc",
        "tooltip_key": "admin_credit_coins_tooltip",
        "icon": "bi-coin"
    },
    {
        "endpoint": "admin.audit",
        "label": "View Audit Logs",
        "label_key": "admin_view_audit_logs",
        "description_key": "admin_view_audit_logs_desc",
        "tooltip_key": "admin_view_audit_logs_tooltip",
        "icon": "bi-file-earmark-text"
    },
]

_ADMIN_EXPLORE_FEATURES = [
    {
        "endpoint": "admin.dashboard",
        "label": "Dashboard",
        "label_key": "admin_dashboard",
        "description_key": "admin_dashboard_desc",
        "tooltip_key": "admin_dashboard_tooltip",
        "icon": "bi-speedometer"
    },
    {
        "endpoint": "admin.manage_users",
        "label": "Manage Users",
        "label_key": "admin_manage_users",
        "description_key": "admin_manage_users_desc",
        "tooltip_key": "admin_manage_users_tooltip",
        "icon": "bi-people"
    },
    {
        "endpoint": "admin.manage_agents",
        "label": "Manage Agents",
        "label_key": "admin_manage_agents",
        "description_key": "admin_manage_agents_desc",
        "tooltip_key": "admin_manage_agents_tooltip",
        "icon": "bi-person-workspace"
    },
    {
        "endpoint": "admin.admin_budgets",
        "label": "Manage Budgets",
        "label_key": "admin_manage_budgets",
        "description_key": "admin_manage_budgets_desc",
        "tooltip_key": "admin_manage_budgets_tooltip",
        "icon": "bi-wallet"
    },
    {
        "endpoint": "admin.admin_bills",
        "label": "Manage Bills",
        "label_key": "admin_manage_bills",
        "description_key": "admin_manage_bills_desc",
        "tooltip_key": "admin_manage_bills_tooltip",
        "icon": "bi-receipt"
    },
    {
        "endpoint": "admin.admin_emergency_funds",
        "label": "Manage Emergency Funds",
        "label_key": "admin_manage_emergency_funds",
        "description_key": "admin_manage_emergency_funds_desc",
        "tooltip_key": "admin_manage_emergency_funds_tooltip",
        "icon": "bi-shield"
    },
    {
        "endpoint": "admin.admin_net_worth",
        "label": "Manage Net Worth",
        "label_key": "admin_manage_net_worth",
        "description_key": "admin_manage_net_worth_desc",
        "tooltip_key": "admin_manage_net_worth_tooltip",
        "icon": "bi-cash-stack"
    },
    {
        "endpoint": "admin.admin_quiz_results",
        "label": "Manage Quiz Results",
        "label_key": "admin_manage_quiz_results",
        "description_key": "admin_manage_quiz_results_desc",
        "tooltip_key": "admin_manage_quiz_results_tooltip",
        "icon": "bi-question-circle"
    },
    {
        "endpoint": "admin.admin_learning_hub",
        "label": "Manage Learning Hub",
        "label_key": "admin_manage_learning_hub",
        "description_key": "admin_manage_learning_hub_desc",
        "tooltip_key": "admin_manage_learning_hub_tooltip",
        "icon": "bi-book"
    },
]

# Initialize module-level variables (will be populated with URLs later)
PERSONAL_TOOLS = []
PERSONAL_NAV = []
PERSONAL_EXPLORE_FEATURES = []
BUSINESS_TOOLS = []
BUSINESS_NAV = []
BUSINESS_EXPLORE_FEATURES = []
AGENT_TOOLS = []
AGENT_NAV = []
AGENT_EXPLORE_FEATURES = []
ADMIN_TOOLS = []
ADMIN_NAV = []
ADMIN_EXPLORE_FEATURES = []
ALL_TOOLS = []

# Pre-generate tools/navigation with URLs at startup
def initialize_tools_with_urls(app):
    '''
    Initialize all tool/navigation lists with resolved URLs.
    
    Args:
        app: Flask application instance
    '''
    global PERSONAL_TOOLS, PERSONAL_NAV, PERSONAL_EXPLORE_FEATURES
    global BUSINESS_TOOLS, BUSINESS_NAV, BUSINESS_EXPLORE_FEATURES
    global AGENT_TOOLS, AGENT_NAV, AGENT_EXPLORE_FEATURES
    global ADMIN_TOOLS, ADMIN_NAV, ADMIN_EXPLORE_FEATURES
    global ALL_TOOLS
    
    with app.app_context():
        PERSONAL_TOOLS = generate_tools_with_urls(_PERSONAL_TOOLS)
        PERSONAL_NAV = generate_tools_with_urls(_PERSONAL_NAV)
        PERSONAL_EXPLORE_FEATURES = generate_tools_with_urls(_PERSONAL_EXPLORE_FEATURES)
        BUSINESS_TOOLS = generate_tools_with_urls(_BUSINESS_TOOLS)
        BUSINESS_NAV = generate_tools_with_urls(_BUSINESS_NAV)
        BUSINESS_EXPLORE_FEATURES = generate_tools_with_urls(_BUSINESS_EXPLORE_FEATURES)
        AGENT_TOOLS = generate_tools_with_urls(_AGENT_TOOLS)
        AGENT_NAV = generate_tools_with_urls(_AGENT_NAV)
        AGENT_EXPLORE_FEATURES = generate_tools_with_urls(_AGENT_EXPLORE_FEATURES)
        ADMIN_TOOLS = generate_tools_with_urls(_ADMIN_TOOLS)
        ADMIN_NAV = generate_tools_with_urls(_ADMIN_NAV)
        ADMIN_EXPLORE_FEATURES = generate_tools_with_urls(_ADMIN_EXPLORE_FEATURES)
        ALL_TOOLS = (
            PERSONAL_TOOLS +
            BUSINESS_TOOLS +
            AGENT_TOOLS +
            ADMIN_TOOLS +
            generate_tools_with_urls([{
                "endpoint": "admin.dashboard",
                "label": "Management",
                "label_key": "admin_dashboard",
                "description_key": "admin_dashboard_desc",
                "tooltip_key": "admin_dashboard_tooltip",
                "icon": "bi-speedometer"
            }])
        )
        logger.info('Initialized tools and navigation with resolved URLs')

def get_limiter():
    '''
    Return the initialized Flask-Limiter instance.
    
    Returns:
        Limiter: The configured Flask-Limiter instance
    '''
    return limiter

def create_anonymous_session():
    '''
    Create a guest session for anonymous access.
    '''
    try:
        session['sid'] = str(uuid.uuid4())
        session['is_anonymous'] = True
        session['created_at'] = datetime.utcnow().isoformat()
        if 'lang' not in session:
            session['lang'] = 'en'
        logger.info(f"{trans('general_anonymous_session_created', default='Created anonymous session')}: {session['sid']}")
    except Exception as e:
        logger.error(f"{trans('general_anonymous_session_error', default='Error creating anonymous session')}: {str(e)}", exc_info=True)

def trans_function(key, lang=None, **kwargs):
    '''
    Translation function wrapper for backward compatibility.
    
    Args:
        key: Translation key
        lang: Language code ('en', 'ha'). Defaults to session['lang'] or 'en'
        **kwargs: String formatting parameters
    
    Returns:
        Translated string with formatting applied
    '''
    try:
        return trans(key, lang=lang, **kwargs)
    except Exception as e:
        logger.error(f"{trans('general_translation_error', default='Translation error for key')} '{key}': {str(e)}", exc_info=True)
        return key

def is_valid_email(email):
    '''
    Validate email address format.
    
    Args:
        email: Email address to validate
    
    Returns:
        bool: True if email is valid, False otherwise
    '''
    if not email or not isinstance(email, str):
        return False
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email.strip()) is not None

def get_mongo_db():
    '''
    Get MongoDB database connection.
    
    Returns:
        Database object
    '''
    try:
        if not hasattr(current_app._get_current_object(), 'mongo_client'):
            raise RuntimeError('MongoDB client not initialized in application context')
        return current_app._get_current_object().mongo_client[current_app.config.get('SESSION_MONGODB_DB', 'ficodb')]
    except Exception as e:
        logger.error(f"{trans('general_mongo_connection_error', default='Error getting MongoDB connection')}: {str(e)}", exc_info=True)
        raise

def close_mongo_db():
    '''
    No-op function for backward compatibility.
    '''
    pass

def get_mail(app):
    '''
    Initialize and return Flask-Mail instance.
    
    Args:
        app: Flask application instance
    
    Returns:
        Mail instance
    '''
    try:
        mail = Mail(app)
        logger.info(trans('general_mail_service_initialized', default='Mail service initialized'))
        return mail
    except Exception as e:
        logger.error(f"{trans('general_mail_service_error', default='Error initializing mail service')}: {str(e)}", exc_info=True)
        return None

def requires_role(role):
    '''
    Decorator to require specific user role.
    
    Args:
        role: Required role (e.g., 'admin', 'agent', 'personal') or list of roles
    
    Returns:
        Decorator function
    '''
    def decorator(f):
        from functools import wraps
        from flask_login import current_user
        from flask import redirect, url_for, flash
        
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash(trans('general_login_required', default='Please log in to access this page.'), 'warning')
                return redirect(url_for('users.login'))
            if is_admin():
                return f(*args, **kwargs)
            allowed_roles = role if isinstance(role, list) else [role]
            if current_user.role not in allowed_roles:
                flash(trans('general_access_denied', default='You do not have permission to access this page.'), 'danger')
                return redirect(url_for('dashboard.index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def check_coin_balance(required_amount=1, user_id=None):
    '''
    Check if user has sufficient coin balance.
    
    Args:
        required_amount: Required coin amount (default: 1)
        user_id: User ID (optional, will use current_user if not provided)
    
    Returns:
        bool: True if user has sufficient balance, False otherwise
    '''
    try:
        from flask_login import current_user
        if user_id is None and current_user.is_authenticated:
            user_id = current_user.id
        if not user_id:
            return False
        db = get_mongo_db()
        if db is None:
            return False
        user_query = get_user_query(user_id)
        user = db.users.find_one(user_query)
        if not user:
            return False
        coin_balance = user.get('coin_balance', 0)
        return coin_balance >= required_amount
    except Exception as e:
        logger.error(f"{trans('general_coin_balance_check_error', default='Error checking coin balance for user')} {user_id}: {str(e)}", exc_info=True)
        return False

def get_user_query(user_id):
    '''
    Get user query for MongoDB operations.
    
    Args:
        user_id: User ID
    
    Returns:
        dict: MongoDB query for user
    '''
    return {'_id': user_id}

def is_admin():
    '''
    Check if current user is admin.
    
    Returns:
        bool: True if current user is admin, False otherwise
    '''
    try:
        from flask_login import current_user
        return current_user.is_authenticated and (current_user.role == 'admin' or getattr(current_user, 'is_admin', False))
    except Exception:
        return False

def format_currency(amount, currency='₦', lang=None):
    '''
    Format currency amount with proper locale.
    
    Args:
        amount: Amount to format
        currency: Currency symbol (default: '₦')
        lang: Language code for formatting
    
    Returns:
        Formatted currency string
    '''
    try:
        if lang is None:
            lang = session.get('lang', 'en') if has_request_context() else 'en'
        amount = float(amount) if amount is not None else 0
        if amount.is_integer():
            return f"{currency}{int(amount):,}"
        return f"{currency}{amount:,.2f}"
    except (TypeError, ValueError) as e:
        logger.warning(f"{trans('general_currency_format_error', default='Error formatting currency')} {amount}: {str(e)}")
        return f"{currency}0"

def format_date(date_obj, lang=None, format_type='short'):
    '''
    Format date according to language preference.
    
    Args:
        date_obj: Date object to format
        lang: Language code
        format_type: 'short', 'long', or 'iso'
    
    Returns:
        Formatted date string
    '''
    try:
        if lang is None:
            lang = session.get('lang', 'en') if has_request_context() else 'en'
        if not date_obj:
            return ''
        if isinstance(date_obj, str):
            try:
                date_obj = datetime.strptime(date_obj, '%Y-%m-%d')
            except ValueError:
                try:
                    date_obj = datetime.fromisoformat(date_obj.replace('Z', '+00:00'))
                except ValueError:
                    return date_obj
        if format_type == 'iso':
            return date_obj.strftime('%Y-%m-%d')
        elif format_type == 'long':
            if lang == 'ha':
                return date_obj.strftime('%d %B %Y')
            else:
                return date_obj.strftime('%B %d, %Y')
        else:
            if lang == 'ha':
                return date_obj.strftime('%d/%m/%Y')
            else:
                return date_obj.strftime('%m/%d/%Y')
    except Exception as e:
        logger.warning(f"{trans('general_date_format_error', default='Error formatting date')} {date_obj}: {str(e)}")
        return str(date_obj) if date_obj else ''

def sanitize_input(input_string, max_length=None):
    '''
    Sanitize user input to prevent XSS and other attacks.
    
    Args:
        input_string: String to sanitize
        max_length: Maximum allowed length
    
    Returns:
        Sanitized string
    '''
    if not input_string:
        return ''
    sanitized = str(input_string).strip()
    sanitized = re.sub(r'[<>"\']', '', sanitized)
    if max_length and len(sanitized) > max_length:
        sanitized = sanitized[:max_length]
    return sanitized

def generate_unique_id(prefix=''):
    '''
    Generate a unique identifier.
    
    Args:
        prefix: Optional prefix for the ID
    
    Returns:
        Unique identifier string
    '''
    unique_id = str(uuid.uuid4())
    if prefix:
        return f"{prefix}_{unique_id}"
    return unique_id

def validate_required_fields(data, required_fields):
    '''
    Validate that all required fields are present and not empty.
    
    Args:
        data: Dictionary of data to validate
        required_fields: List of required field names
    
    Returns:
        tuple: (is_valid, missing_fields)
    '''
    missing_fields = []
    for field in required_fields:
        if field not in data or not data[field] or str(data[field]).strip() == '':
            missing_fields.append(field)
    return len(missing_fields) == 0, missing_fields

def get_user_language():
    '''
    Get the current user's language preference.
    
    Returns:
        Language code ('en' or 'ha')
    '''
    try:
        if has_request_context():
            return session.get('lang', 'en')
        return 'en'
    except Exception:
        return 'en'

def log_user_action(action, details=None, user_id=None):
    '''
    Log user action for audit purposes.
    
    Args:
        action: Action performed
        details: Additional details about the action
        user_id: User ID (optional, will use current_user if not provided)
    '''
    try:
        from flask_login import current_user
        if user_id is None and current_user.is_authenticated:
            user_id = current_user.id
        session_id = session.get('sid', 'no-session-id') if has_request_context() else 'no-session-id'
        log_entry = {
            'user_id': user_id,
            'session_id': session_id,
            'action': action,
            'details': details or {},
            'timestamp': datetime.utcnow(),
            'ip_address': None,
            'user_agent': None
        }
        if has_request_context():
            from flask import request
            log_entry['ip_address'] = request.remote_addr
            log_entry['user_agent'] = request.headers.get('User-Agent')
        db = get_mongo_db()
        if db:
            db.audit_logs.insert_one(log_entry)
        logger.info(f"{trans('general_user_action_logged', default='User action logged')}: {action} by user {user_id}")
    except Exception as e:
        logger.error(f"{trans('general_user_action_log_error', default='Error logging user action')}: {str(e)}", exc_info=True)

def send_sms_reminder(recipient, message):
    '''
    Send an SMS reminder to the specified recipient.
    
    Args:
        recipient: Phone number of the recipient
        message: Message to send
    
    Returns:
        tuple: (success, api_response)
    '''
    try:
        recipient = re.sub(r'\D', '', recipient)
        if recipient.startswith('0'):
            recipient = '234' + recipient[1:]
        elif not recipient.startswith('+'):
            recipient = '234' + recipient
        sms_api_url = current_app.config.get('SMS_API_URL', 'https://api.smsprovider.com/send')
        sms_api_key = current_app.config.get('SMS_API_KEY', '')
        payload = {
            'to': f'+{recipient}',
            'message': message,
            'api_key': sms_api_key
        }
        response = requests.post(sms_api_url, json=payload, timeout=10)
        response_data = response.json()
        if response.status_code == 200 and response_data.get('success', False):
            logger.info(f"SMS sent to {recipient}")
            return True, response_data
        else:
            logger.error(f"Failed to send SMS to {recipient}: {response_data}")
            return False, response_data
    except Exception as e:
        logger.error(f"Error sending SMS to {recipient}: {str(e)}", exc_info=True)
        return False, {'error': str(e)}

def send_whatsapp_reminder(recipient, message):
    '''
    Send a WhatsApp reminder to the specified recipient.
    
    Args:
        recipient: Phone number of the recipient
        message: Message to send
    
    Returns:
        tuple: (success, api_response)
    '''
    try:
        recipient = re.sub(r'\D', '', recipient)
        if recipient.startswith('0'):
            recipient = '234' + recipient[1:]
        elif not recipient.startswith('+'):
            recipient = '234' + recipient
        whatsapp_api_url = current_app.config.get('WHATSAPP_API_URL', 'https://api.whatsapp.com/send')
        whatsapp_api_key = current_app.config.get('WHATSAPP_API_KEY', '')
        payload = {
            'phone': f'+{recipient}',
            'text': message,
            'api_key': whatsapp_api_key
        }
        response = requests.post(whatsapp_api_url, json=payload, timeout=10)
        response_data = response.json()
        if response.status_code == 200 and response_data.get('success', False):
            logger.info(f"WhatsApp message sent to {recipient}")
            return True, response_data
        else:
            logger.error(f"Failed to send WhatsApp message to {recipient}: {response_data}")
            return False, response_data
    except Exception as e:
        logger.error(f"Error sending WhatsApp message to {recipient}: {str(e)}", exc_info=True)
        return False, {'error': str(e)}

# Data conversion functions for backward compatibility
def to_dict_financial_health(record):
    '''Convert financial health record to dictionary.'''
    if not record:
        return {'score': None, 'status': None}
    return {
        'score': record.get('score'),
        'status': record.get('status'),
        'debt_to_income': record.get('debt_to_income'),
        'savings_rate': record.get('savings_rate'),
        'interest_burden': record.get('interest_burden'),
        'badges': record.get('badges', []),
        'created_at': record.get('created_at')
    }

def to_dict_budget(record):
    '''Convert budget record to dictionary.'''
    if not record:
        return {'surplus_deficit': None, 'savings_goal': None}
    return {
        'income': record.get('income', 0),
        'fixed_expenses': record.get('fixed_expenses', 0),
        'variable_expenses': record.get('variable_expenses', 0),
        'savings_goal': record.get('savings_goal', 0),
        'surplus_deficit': record.get('surplus_deficit', 0),
        'housing': record.get('housing', 0),
        'food': record.get('food', 0),
        'transport': record.get('transport', 0),
        'dependents': record.get('dependents', 0),
        'miscellaneous': record.get('miscellaneous', 0),
        'others': record.get('others', 0),
        'created_at': record.get('created_at')
    }

def to_dict_bill(record):
    '''Convert bill record to dictionary.'''
    if not record:
        return {'amount': None, 'status': None}
    return {
        'id': str(record.get('_id', '')),
        'bill_name': record.get('bill_name', ''),
        'amount': record.get('amount', 0),
        'due_date': record.get('due_date', ''),
        'frequency': record.get('frequency', ''),
        'category': record.get('category', ''),
        'status': record.get('status', ''),
        'send_email': record.get('send_email', False),
        'reminder_days': record.get('reminder_days'),
        'user_email': record.get('user_email', ''),
        'first_name': record.get('first_name', '')
    }

def to_dict_net_worth(record):
    '''Convert net worth record to dictionary.'''
    if not record:
        return {'net_worth': None, 'total_assets': None}
    return {
        'cash_savings': record.get('cash_savings', 0),
        'investments': record.get('investments', 0),
        'property': record.get('property', 0),
        'loans': record.get('loans', 0),
        'total_assets': record.get('total_assets', 0),
        'total_liabilities': record.get('total_liabilities', 0),
        'net_worth': record.get('net_worth', 0),
        'badges': record.get('badges', []),
        'created_at': record.get('created_at')
    }

def to_dict_emergency_fund(record):
    '''Convert emergency fund record to dictionary.'''
    if not record:
        return {'target_amount': None, 'savings_gap': None}
    return {
        'monthly_expenses': record.get('monthly_expenses', 0),
        'monthly_income': record.get('monthly_income', 0),
        'current_savings': record.get('current_savings', 0),
        'risk_tolerance_level': record.get('risk_tolerance_level', ''),
        'dependents': record.get('dependents', 0),
        'timeline': record.get('timeline', 0),
        'recommended_months': record.get('recommended_months', 0),
        'target_amount': record.get('target_amount', 0),
        'savings_gap': record.get('savings_gap', 0),
        'monthly_savings': record.get('monthly_savings', 0),
        'percent_of_income': record.get('percent_of_income'),
        'badges': record.get('badges', []),
        'created_at': record.get('created_at')
    }

def to_dict_learning_progress(record):
    '''Convert learning progress record to dictionary.'''
    if not record:
        return {'lessons_completed': [], 'quiz_scores': {}}
    return {
        'course_id': record.get('course_id', ''),
        'lessons_completed': record.get('lessons_completed', []),
        'quiz_scores': record.get('quiz_scores', {}),
        'current_lesson': record.get('current_lesson')
    }

def to_dict_quiz_result(record):
    '''Convert quiz result record to dictionary.'''
    if not record:
        return {'personality': None, 'score': None}
    return {
        'personality': record.get('personality', ''),
        'score': record.get('score', 0),
        'badges': record.get('badges', []),
        'insights': record.get('insights', []),
        'tips': record.get('tips', []),
        'created_at': record.get('created_at')
    }

def to_dict_news_article(record):
    '''Convert news article record to dictionary.'''
    if not record:
        return {'title': None, 'content': None}
    return {
        'id': str(record.get('_id', '')),
        'title': record.get('title', ''),
        'content': record.get('content', ''),
        'source_type': record.get('source_type', ''),
        'source_link': record.get('source_link'),
        'published_at': record.get('published_at'),
        'category': record.get('category'),
        'is_verified': record.get('is_verified', False),
        'is_active': record.get('is_active', True)
    }

def to_dict_tax_rate(record):
    '''Convert tax rate record to dictionary.'''
    if not record:
        return {'rate': None, 'description': None}
    return {
        'id': str(record.get('_id', '')),
        'role': record.get('role', ''),
        'min_income': record.get('min_income', 0),
        'max_income': record.get('max_income'),
        'rate': record.get('rate', 0),
        'description': record.get('description', '')
    }

def to_dict_payment_location(record):
    '''Convert payment location record to dictionary.'''
    if not record:
        return {'name': None, 'address': None}
    return {
        'id': str(record.get('_id', '')),
        'name': record.get('name', ''),
        'address': record.get('address', ''),
        'contact': record.get('contact', ''),
        'coordinates': record.get('coordinates')
    }

def to_dict_tax_reminder(record):
    '''Convert tax reminder record to dictionary.'''
    if not record:
        return {'tax_type': None, 'amount': None}
    return {
        'id': str(record.get('_id', '')),
        'user_id': record.get('user_id', ''),
        'tax_type': record.get('tax_type', ''),
        'due_date': record.get('due_date'),
        'amount': record.get('amount', 0),
        'status': record.get('status', ''),
        'created_at': record.get('created_at'),
        'notification_id': record.get('notification_id'),
        'sent_at': record.get('sent_at'),
        'payment_location_id': record.get('payment_location_id')
    }

# Export all functions and variables
__all__ = [
    'login_manager', 'flask_session', 'csrf', 'babel', 'compress', 'limiter',
    'get_limiter', 'create_anonymous_session', 'trans_function', 'is_valid_email',
    'get_mongo_db', 'close_mongo_db', 'get_mail', 'requires_role', 'check_coin_balance',
    'get_user_query', 'is_admin', 'format_currency', 'format_date', 'sanitize_input',
    'generate_unique_id', 'validate_required_fields', 'get_user_language',
    'log_user_action', 'send_sms_reminder', 'send_whatsapp_reminder',
    'to_dict_financial_health', 'to_dict_budget', 'to_dict_bill', 'to_dict_net_worth',
    'to_dict_emergency_fund', 'to_dict_learning_progress', 'to_dict_quiz_result',
    'to_dict_news_article', 'to_dict_tax_rate', 'to_dict_payment_location',
    'to_dict_tax_reminder', 'initialize_tools_with_urls',
    'PERSONAL_TOOLS', 'PERSONAL_NAV', 'PERSONAL_EXPLORE_FEATURES',
    'BUSINESS_TOOLS', 'BUSINESS_NAV', 'BUSINESS_EXPLORE_FEATURES',
    'AGENT_TOOLS', 'AGENT_NAV', 'AGENT_EXPLORE_FEATURES',
    'ADMIN_TOOLS', 'ADMIN_NAV', 'ADMIN_EXPLORE_FEATURES', 'ALL_TOOLS'
]
