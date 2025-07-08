import os
import sys
import logging
import uuid
from datetime import datetime, date, timedelta
from flask import (
    Flask, jsonify, request, render_template, redirect, url_for, flash,
    make_response, has_request_context, g, send_from_directory, session, Response, current_app, abort
)
from flask_session import Session
from flask_cors import CORS
from werkzeug.security import generate_password_hash
from itsdangerous import URLSafeTimedSerializer
from dotenv import load_dotenv
import atexit
from functools import wraps
from mailersend_email import init_email_config
from scheduler_setup import init_scheduler
from models import (
    create_user, get_user_by_email, get_user, get_financial_health, get_budgets, get_bills,
    get_net_worth, get_emergency_funds, get_learning_progress, get_quiz_results,
    to_dict_financial_health, to_dict_budget, to_dict_bill, to_dict_net_worth,
    to_dict_emergency_fund, to_dict_learning_progress, to_dict_quiz_result, initialize_database
)
import utils
from session_utils import create_anonymous_session
from translations import trans, get_translations, get_all_translations, get_module_translations
from flask_login import LoginManager, login_required, current_user, UserMixin
from flask_wtf.csrf import CSRFError
from jinja2.exceptions import TemplateNotFound
import time
from pymongo import MongoClient
import certifi
from news.routes import seed_news
from taxation.routes import seed_tax_data
from coins.routes import coins_bp
import re
from flask_mail import Mail
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from flask_babel import Babel
from flask_compress import Compress
import requests

# Load environment variables
load_dotenv()

# Set up logging
root_logger = logging.getLogger('ficore_app')
root_logger.setLevel(logging.DEBUG)

class SessionFormatter(logging.Formatter):
    def format(self, record):
        record.session_id = getattr(record, 'session_id', 'no-session-id')
        record.user_role = getattr(record, 'user_role', 'anonymous')
        record.ip_address = getattr(record, 'ip_address', 'unknown')
        return super().format(record)

class SessionAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        kwargs['extra'] = kwargs.get('extra', {})
        session_id = 'no-session-id'
        user_role = 'anonymous'
        ip_address = 'unknown'
        try:
            if has_request_context():
                session_id = session.get('sid', 'no-session-id')
                user_role = current_user.role if current_user.is_authenticated else 'anonymous'
                ip_address = request.remote_addr
            else:
                session_id = 'no-request-context'
        except Exception as e:
            session_id = 'session-error'
            kwargs['extra']['session_error'] = str(e)
        kwargs['extra']['session_id'] = session_id
        kwargs['extra']['user_role'] = user_role
        kwargs['extra']['ip_address'] = ip_address
        return msg, kwargs

logger = SessionAdapter(root_logger, {})

# Initialize extensions
login_manager = utils.LoginManager()
flask_session = utils.Session()
csrf = utils.CSRFProtect()
babel = utils.Babel()
compress = utils.Compress()
limiter = utils.Limiter(key_func=get_remote_address, default_limits=['200 per day', '50 per hour'], storage_uri='memory://')

# Decorators
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            logger.warning("Unauthorized access attempt to admin route", extra={'ip_address': request.remote_addr})
            return redirect(url_for('users.login'))
        if not utils.is_admin():
            flash(utils.trans('general_no_permission', default='You do not have permission to access this page.'), 'danger')
            logger.warning(f"Non-admin user {current_user.id} attempted access", extra={'ip_address': request.remote_addr})
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def custom_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.is_authenticated or session.get('is_anonymous', False):
            return f(*args, **kwargs)
        logger.info("Redirecting unauthenticated user to login", extra={'ip_address': request.remote_addr})
        return redirect(url_for('users.login', next=request.url))
    return decorated_function

def ensure_session_id(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            if 'sid' not in session:
                if not current_user.is_authenticated:
                    utils.create_anonymous_session()
                    logger.info(f'New anonymous session created: {session["sid"]}', extra={'ip_address': request.remote_addr})
                else:
                    session['sid'] = str(uuid.uuid4())
                    session['is_anonymous'] = False
                    logger.info(f'New session ID generated for authenticated user {current_user.id}: {session["sid"]}', extra={'ip_address': request.remote_addr})
        except Exception as e:
            logger.error(f'Session operation failed: {str(e)}', exc_info=True)
        return f(*args, **kwargs)
    return decorated_function

def setup_logging(app):
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(SessionFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s [session: %(session_id)s, role: %(user_role)s, ip: %(ip_address)s]'))
    root_logger.handlers = []
    root_logger.addHandler(handler)
    
    flask_logger = logging.getLogger('flask')
    werkzeug_logger = logging.getLogger('werkzeug')
    pymongo_logger = logging.getLogger('pymongo')
    flask_logger.handlers = []
    werkzeug_logger.handlers = []
    pymongo_logger.handlers = []
    flask_logger.addHandler(handler)
    werkzeug_logger.addHandler(handler)
    pymongo_logger.addHandler(handler)
    flask_logger.setLevel(logging.DEBUG)
    werkzeug_logger.setLevel(logging.DEBUG)
    pymongo_logger.setLevel(logging.DEBUG)
    
    logger.info('Logging setup complete with StreamHandler for ficore_app, flask, werkzeug, and pymongo')

def check_mongodb_connection(app):
    try:
        client = app.extensions['mongo']
        client.admin.command('ping')
        logger.info('MongoDB connection verified with ping')
        return True
    except Exception as e:
        logger.error(f'MongoDB connection failed: {str(e)}', exc_info=True)
        return False

def setup_session(app):
    try:
        with app.app_context():
            if not check_mongodb_connection(app):
                logger.error('MongoDB client is not available, falling back to filesystem session')
                app.config['SESSION_TYPE'] = 'filesystem'
                utils.flask_session.init_app(app)
                logger.info('Session configured with filesystem fallback')
                return
            app.config['SESSION_TYPE'] = 'mongodb'
            app.config['SESSION_MONGODB'] = app.extensions['mongo']
            app.config['SESSION_MONGODB_DB'] = 'ficodb'
            app.config['SESSION_MONGODB_COLLECT'] = 'sessions'
            app.config['SESSION_PERMANENT'] = True
            app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
            app.config['SESSION_USE_SIGNER'] = True
            app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
            app.config['SESSION_COOKIE_SECURE'] = os.getenv('FLASK_ENV', 'development') == 'production'
            app.config['SESSION_COOKIE_HTTPONLY'] = True
            app.config['SESSION_COOKIE_NAME'] = 'ficore_session'
            utils.flask_session.init_app(app)
            logger.info(f'Session configured: type={app.config["SESSION_TYPE"]}, db={app.config["SESSION_MONGODB_DB"]}, collection={app.config["SESSION_MONGODB_COLLECT"]}')
    except Exception as e:
        logger.error(f'Failed to configure session with MongoDB: {str(e)}', exc_info=True)
        app.config['SESSION_TYPE'] = 'filesystem'
        utils.flask_session.init_app(app)
        logger.info('Session configured with filesystem fallback due to MongoDB error')

class User(UserMixin):
    def __init__(self, id, email, display_name=None, role='personal'):
        self.id = id
        self.email = email
        self.display_name = display_name or id
        self.role = role

    def get(self, key, default=None):
        try:
            with current_app.app_context():
                user = current_app.extensions['mongo']['ficodb'].users.find_one({'_id': self.id})
                return user.get(key, default) if user else default
        except Exception as e:
            logger.error(f'Error fetching user data for {self.id}: {str(e)}', exc_info=True)
            return default

    @property
    def is_active(self):
        try:
            with current_app.app_context():
                user = current_app.extensions['mongo']['ficodb'].users.find_one({'_id': self.id})
                return user.get('is_active', True) if user else False
        except Exception as e:
            logger.error(f'Error checking active status for user {self.id}: {str(e)}', exc_info=True)
            return False

    def get_id(self):
        return str(self.id)

    def get_first_name(self):
        try:
            with current_app.app_context():
                user = current_app.extensions['mongo']['ficodb'].users.find_one({'_id': self.id})
                if user and 'personal_details' in user:
                    return user['personal_details'].get('first_name', self.display_name)
                return self.display_name
        except Exception as e:
            logger.error(f'Error fetching first name for user {self.id}: {str(e)}', exc_info=True)
            return self.display_name

def create_app():
    app = Flask(__name__, template_folder='templates', static_folder='static')
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    
    # Load configuration
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
    if not app.config['SECRET_KEY']:
        logger.error('SECRET_KEY environment variable is not set')
        raise ValueError('SECRET_KEY must be set in environment variables')

    app.config['SERVER_NAME'] = os.getenv('SERVER_NAME', 'financial-health-score-8jvu.onrender.com')
    app.config['APPLICATION_ROOT'] = os.getenv('APPLICATION_ROOT', '/')
    app.config['PREFERRED_URL_SCHEME'] = os.getenv('PREFERRED_URL_SCHEME', 'https')
    
    app.config['MONGO_URI'] = os.getenv('MONGO_URI')
    if not app.config['MONGO_URI']:
        logger.error('MONGO_URI environment variable is not set')
        raise ValueError('MONGO_URI must be set in environment variables')
    
    app.config['GOOGLE_CLIENT_ID'] = os.getenv('GOOGLE_CLIENT_ID')
    app.config['GOOGLE_CLIENT_SECRET'] = os.getenv('GOOGLE_CLIENT_SECRET')
    app.config['SMTP_SERVER'] = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
    app.config['SMTP_PORT'] = int(os.getenv('SMTP_PORT', 587))
    app.config['SMTP_USERNAME'] = os.getenv('SMTP_USERNAME')
    app.config['SMTP_PASSWORD'] = os.getenv('SMTP_PASSWORD')
    app.config['SMS_API_URL'] = os.getenv('SMS_API_URL')
    app.config['SMS_API_KEY'] = os.getenv('SMS_API_KEY')
    app.config['WHATSAPP_API_URL'] = os.getenv('WHATSAPP_API_URL')
    app.config['WHATSAPP_API_KEY'] = os.getenv('WHATSAPP_API_KEY')
    app.config['BASE_URL'] = os.getenv('BASE_URL', 'http://localhost:5000')
    app.config['SETUP_KEY'] = os.getenv('SETUP_KEY')
    
    # Validate critical environment variables
    for key in ['SETUP_KEY', 'GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET', 'SMTP_USERNAME', 'SMTP_PASSWORD']:
        if not app.config.get(key):
            logger.warning(f'{key} environment variable not set; some features may be disabled')

    # Initialize MongoDB client with explicit TLS/SSL
    try:
        client = MongoClient(
            app.config['MONGO_URI'],
            serverSelectionTimeoutMS=5000,
            tls=True,
            tlsCAFile=certifi.where() if os.getenv('MONGO_CA_FILE') is None else os.getenv('MONGO_CA_FILE'),
            maxPoolSize=50,
            minPoolSize=5
        )
        # Store MongoDB client in app.extensions
        app.extensions = getattr(app, 'extensions', {})
        app.extensions['mongo'] = client
        # Verify connection
        client.admin.command('ping')
        logger.info('MongoDB client initialized successfully')
        
        def shutdown_mongo_client():
            try:
                with app.app_context():
                    if hasattr(app, 'extensions') and 'mongo' in app.extensions:
                        app.extensions['mongo'].close()
                        logger.info('MongoDB client closed successfully')
            except Exception as e:
                logger.error(f'Error closing MongoDB client: {str(e)}', exc_info=True)
        
        atexit.register(shutdown_mongo_client)
    except Exception as e:
        logger.error(f'MongoDB connection test failed: {str(e)}', exc_info=True)
        raise RuntimeError(f'Failed to connect to MongoDB: {str(e)}')
    
    # Initialize extensions
    setup_logging(app)
    utils.compress.init_app(app)
    utils.csrf.init_app(app)
    mail = utils.get_mail(app)
    utils.limiter.init_app(app)
    serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])
    utils.babel.init_app(app)
    utils.login_manager.init_app(app)
    utils.login_manager.login_view = 'users.login'

    # User loader callback for Flask-Login
    @utils.login_manager.user_loader
    def load_user(user_id):
        try:
            with app.app_context():
                user = app.extensions['mongo']['ficodb'].users.find_one({'_id': user_id})
                if not user:
                    return None
                return User(
                    id=user['_id'],
                    email=user['email'],
                    display_name=user.get('display_name', user['_id']),
                    role=user.get('role', 'personal')
                )
        except Exception as e:
            logger.error(f"Error loading user {user_id}: {str(e)}", exc_info=True)
            return None

    # Initialize MongoDB, session, scheduler, and other components within app context
    try:
        with app.app_context():
            # Initialize database
            initialize_database(app)
            logger.info('Database initialized successfully')

            # Setup session
            setup_session(app)

            # Initialize scheduler
            scheduler = init_scheduler(app, app.extensions['mongo']['ficodb'])
            app.config['SCHEDULER'] = scheduler
            logger.info('Scheduler initialized successfully')
            
            def shutdown_scheduler():
                try:
                    with app.app_context():
                        if 'SCHEDULER' in app.config and app.config['SCHEDULER'].running:
                            app.config['SCHEDULER'].shutdown(wait=True)
                            logger.info('Scheduler shutdown successfully')
                except Exception as e:
                    logger.error(f'Error shutting down scheduler: {str(e)}', exc_info=True)
            atexit.register(shutdown_scheduler)

            # Initialize personal finance collections
            personal_finance_collections = [
                'budgets', 'bills', 'emergency_funds', 'financial_health_scores', 
                'net_worth_data', 'quiz_responses', 'learning_materials'
            ]
            db = app.extensions['mongo']['ficodb']
            for collection_name in personal_finance_collections:
                if collection_name not in db.list_collection_names():
                    db.create_collection(collection_name)
                    logger.info(f'Created personal finance collection: {collection_name}')
            
            # Create indexes
            try:
                db.bills.create_index([('user_id', 1), ('due_date', 1)])
                db.bills.create_index([('session_id', 1), ('due_date', 1)])
                db.bills.create_index([('status', 1)])
                db.budgets.create_index([('user_id', 1), ('created_at', -1)])
                db.budgets.create_index([('session_id', 1), ('created_at', -1)])
                db.emergency_funds.create_index([('user_id', 1), ('created_at', -1)])
                db.emergency_funds.create_index([('session_id', 1), ('created_at', -1)])
                db.financial_health_scores.create_index([('user_id', 1), ('created_at', -1)])
                db.financial_health_scores.create_index([('session_id', 1), ('created_at', -1)])
                db.net_worth_data.create_index([('user_id', 1), ('due_date', 1), ('status', 1)]) 
                db.net_worth_data.create_index([('session_id', 1), ('created_at', -1)])
                db.quiz_responses.create_index([('user_id', 1), ('created_at', -1)])
                db.quiz_responses.create_index([('session_id', 1), ('created_at', -1)])
                db.learning_materials.create_index([('user_id', 1), ('course_id', 1)])
                db.learning_materials.create_index([('session_id', 1), ('course_id', 1)])
                logger.info('Created indexes for personal finance collections')
            except Exception as e:
                logger.warning(f'Some indexes may already exist: {str(e)}')
            
            # Seed tax and news data
            try:
                with app.app_context():
                    tax_version = db.tax_rates.find_one({'_id': 'version'})
                    current_tax_version = '2025-07-02'
                    if not tax_version or tax_version.get('version') != current_tax_version:
                        seed_tax_data()
                        db.tax_rates.update_one(
                            {'_id': 'version'},
                            {'$set': {'version': current_tax_version, 'updated_at': datetime.utcnow(), 'role': 'system'}},
                            upsert=True
                        )
                        logger.info(f'Tax data seeded or updated to version {current_tax_version}')
                    else:
                        logger.info('Tax data already up-to-date')
                
                if db.news.count_documents({}) == 0:
                    seed_news()
                    logger.info('News data seeded')
                else:
                    logger.info('News data already seeded')
            except Exception as e:
                logger.error(f'Failed to seed tax or news data: {str(e)}', exc_info=True)
            
            # Initialize admin user
            admin_email = os.getenv('ADMIN_EMAIL', 'ficore@gmail.com')
            admin_password = os.getenv('ADMIN_PASSWORD')
            if not admin_password:
                logger.error('ADMIN_PASSWORD environment variable is not set')
                raise ValueError('ADMIN_PASSWORD must be set in environment variables')
            admin_username = os.getenv('ADMIN_USERNAME', 'admin')
            admin_user = get_user_by_email(db, admin_email)
            if not admin_user:
                user_data = {
                    'username': admin_username.lower(),
                    'email': admin_email.lower(),
                    'password_hash': generate_password_hash(admin_password),
                    'is_admin': True,
                    'role': 'admin',
                    'created_at': datetime.utcnow(),
                    'lang': 'en',
                    'setup_complete': True,
                    'display_name': admin_username
                }
                create_user(db, user_data)
                logger.info(f'Admin user created with email: {admin_email}')
            else:
                logger.info(f'Admin user already exists with email: {admin_email}')

            # Register blueprints
            from users.routes import users_bp
            from agents.routes import agents_bp
            from creditors.routes import creditors_bp
            from dashboard.routes import dashboard_bp
            from debtors.routes import debtors_bp
            from inventory.routes import inventory_bp
            from payments.routes import payments_bp
            from receipts.routes import receipts_bp
            from reports.routes import reports_bp
            from settings.routes import settings_bp
            from personal import personal_bp
            from general.routes import general_bp
            from admin.routes import admin_bp
            from news.routes import news_bp
            from taxation.routes import taxation_bp
            
            app.register_blueprint(users_bp, url_prefix='/users')
            logger.info('Registered users blueprint')
            app.register_blueprint(agents_bp, url_prefix='/agents')
            logger.info('Registered agents blueprint')
            app.register_blueprint(news_bp, url_prefix='/news')
            logger.info('Registered news blueprint')
            app.register_blueprint(taxation_bp, url_prefix='/taxation')
            logger.info('Registered taxation blueprint')
            try:
                app.register_blueprint(coins_bp, url_prefix='/coins')
                logger.info('Registered coins blueprint and initialized limiter')
            except Exception as e:
                logger.warning(f'Could not import coins blueprint: {str(e)}')
            app.register_blueprint(creditors_bp, url_prefix='/creditors')
            logger.info('Registered creditors blueprint')
            app.register_blueprint(dashboard_bp, url_prefix='/dashboard')
            logger.info('Registered dashboard blueprint')
            app.register_blueprint(debtors_bp, url_prefix='/debtors')
            logger.info('Registered debtors blueprint')
            app.register_blueprint(inventory_bp, url_prefix='/inventory')
            logger.info('Registered inventory blueprint')
            app.register_blueprint(payments_bp, url_prefix='/payments')
            logger.info('Registered payments blueprint')
            app.register_blueprint(receipts_bp, url_prefix='/receipts')
            logger.info('Registered receipts blueprint')
            app.register_blueprint(reports_bp, url_prefix='/reports')
            logger.info('Registered reports blueprint')
            app.register_blueprint(settings_bp, url_prefix='/settings')
            logger.info('Registered settings blueprint')
            try:
                app.register_blueprint(admin_bp, url_prefix='/admin')
                logger.info('Registered admin blueprint')
            except Exception as e:
                logger.warning(f'Could not import admin blueprint: {str(e)}')
            app.register_blueprint(personal_bp)
            logger.info('Registered personal blueprint with url_prefix="/personal"')
            app.register_blueprint(general_bp, url_prefix='/general')
            logger.info('Registered general blueprint')

            # Initialize tools with URLs after blueprint registration
            utils.initialize_tools_with_urls(app)
            logger.info('Initialized tools and navigation with resolved URLs')

    except Exception as e:
        logger.error(f'Error in create_app: {str(e)}', exc_info=True)
        raise

    # Jinja2 globals and filters
    app.jinja_env.globals.update(
        FACEBOOK_URL=app.config.get('FACEBOOK_URL', 'https://facebook.com/ficoreafrica'),
        TWITTER_URL=app.config.get('TWITTER_URL', 'https://x.com/ficoreafrica'),
        LINKEDIN_URL=app.config.get('LINKEDIN_URL', 'https://linkedin.com/company/ficoreafrica'),
        FEEDBACK_FORM_URL=app.config.get('FEEDBACK_FORM_URL', url_for('general_bp.feedback')),
        WAITLIST_FORM_URL=app.config.get('WAITLIST_FORM_URL', '#'),
        CONSULTANCY_FORM_URL=app.config.get('CONSULTANCY_FORM_URL', '#'),
        trans=trans,
        trans_function=utils.trans_function,
        get_translations=get_translations,
        is_admin=utils.is_admin
    )
    
    @app.template_filter('safe_nav')
    def safe_nav(value):
        try:
            if not isinstance(value, dict) or 'icon' not in value:
                logger.warning(f'Invalid navigation item: {value}')
                return {'icon': 'bi-question-circle', 'label': value.get('label', ''), 'url': value.get('url', '#')}
            if not value.get('icon', '').startswith('bi-'):
                logger.warning(f'Invalid icon in navigation item: {value.get("icon")}')
                value['icon'] = 'bi-question-circle'
            return value
        except Exception as e:
            logger.error(f'Navigation rendering error: {str(e)}', exc_info=True)
            return {'icon': 'bi-question-circle', 'label': str(value), 'url': '#'}

    @app.template_filter('format_number')
    def format_number(value):
        try:
            if isinstance(value, (int, float)):
                return f'{float(value):,.2f}'
            return str(value)
        except (ValueError, TypeError) as e:
            logger.warning(f'Error formatting number {value}: {str(e)}')
            return str(value)
    
    @app.template_filter('format_currency')
    def format_currency(value):
        try:
            value = float(value)
            locale = session.get('lang', 'en')
            symbol = '₦'
            if value.is_integer():
                return f'{symbol}{int(value):,}'
            return f'{symbol}{value:,.2f}'
        except (TypeError, ValueError) as e:
            logger.warning(f'Error formatting currency {value}: {str(e)}')
            return str(value)
    
    @app.template_filter('format_datetime')
    def format_datetime(value):
        try:
            locale = session.get('lang', 'en')
            format_str = '%B %d, %Y, %I:%M %p' if locale == 'en' else '%d %B %Y, %I:%M %p'
            if isinstance(value, datetime):
                return value.strftime(format_str)
            elif isinstance(value, date):
                return value.strftime('%B %d, %Y' if locale == 'en' else '%d %B %Y')
            elif isinstance(value, str):
                parsed = datetime.strptime(value, '%Y-%m-%d')
                return parsed.strftime(format_str)
            return str(value)
        except Exception as e:
            logger.warning(f'Error formatting datetime {value}: {str(e)}')
            return str(value)
    
    @app.template_filter('format_date')
    def format_date(value):
        try:
            locale = session.get('lang', 'en')
            format_str = '%Y-%m-%d' if locale == 'en' else '%d-%m-%Y'
            if isinstance(value, datetime):
                return value.strftime(format_str)
            elif isinstance(value, date):
                return value.strftime(format_str)
            elif isinstance(value, str):
                parsed = datetime.strptime(value, '%Y-%m-%d').date()
                return parsed.strftime(format_str)
            return str(value)
        except Exception as e:
            logger.warning(f'Error formatting date {value}: {str(e)}')
            return str(value)
    
    @app.template_filter('trans')
    def trans_filter(key, **kwargs):
        lang = session.get('lang', 'en')
        translation = utils.trans(key, lang=lang, **kwargs)
        if translation == key:
            logger.warning(f'Missing translation for key="{key}" in lang="{lang}"')
            return key
        return translation
        
    @app.context_processor
    def inject_role_nav():
        """Inject role-based navigation data into all templates."""
        tools_for_template = []
        explore_features_for_template = []
        bottom_nav_items = []

        try:
            with app.app_context():
                if current_user.is_authenticated:
                    if current_user.role == 'personal':
                        tools_for_template = utils.PERSONAL_TOOLS
                        explore_features_for_template = utils.PERSONAL_EXPLORE_FEATURES
                        bottom_nav_items = utils.PERSONAL_NAV
                    elif current_user.role == 'trader':
                        tools_for_template = utils.BUSINESS_TOOLS
                        explore_features_for_template = utils.BUSINESS_EXPLORE_FEATURES
                        bottom_nav_items = utils.BUSINESS_NAV
                    elif current_user.role == 'agent':
                        tools_for_template = utils.AGENT_TOOLS
                        explore_features_for_template = utils.AGENT_EXPLORE_FEATURES
                        bottom_nav_items = utils.AGENT_NAV
                    elif current_user.role == 'admin':
                        tools_for_template = utils.ALL_TOOLS
                        explore_features_for_template = utils.ADMIN_EXPLORE_FEATURES
                        bottom_nav_items = utils.ADMIN_NAV
                else:
                    explore_features_for_template = utils.generate_tools_with_urls([
                        {
                            "endpoint": "personal.budget.main",
                            "label": "Budget Planner",
                            "label_key": "budget_budget_planner",
                            "description_key": "budget_budget_desc",
                            "tooltip_key": "budget_tooltip",
                            "icon": "bi-wallet",
                            "category": "Personal"
                        },
                        {
                            "endpoint": "personal.financial_health.main",
                            "label": "Financial Health",
                            "label_key": "financial_health_calculator",
                            "description_key": "financial_health_desc",
                            "tooltip_key": "financial_health_tooltip",
                            "icon": "bi-heart",
                            "category": "Personal"
                        },
                        {
                            "endpoint": "personal.quiz.main",
                            "label": "Financial Personality Quiz",
                            "label_key": "quiz_personality_quiz",
                            "description_key": "quiz_personality_desc",
                            "tooltip_key": "quiz_tooltip",
                            "icon": "bi-question-circle",
                            "category": "Personal"
                        },
                        {
                            "endpoint": "inventory.index",
                            "label": "Inventory",
                            "label_key": "inventory_dashboard",
                            "description_key": "inventory_dashboard_desc",
                            "tooltip_key": "inventory_tooltip",
                            "icon": "bi-box",
                            "category": "Business"
                        },
                        {
                            "endpoint": "creditors.index",
                            "label": "I Owe",
                            "label_key": "creditors_dashboard",
                            "description_key": "creditors_dashboard_desc",
                            "tooltip_key": "creditors_tooltip",
                            "icon": "bi-person-lines",
                            "category": "Business"
                        },
                        {
                            "endpoint": "debtors.index",
                            "label": "They Owe",
                            "label_key": "debtors_dashboard",
                            "description_key": "debtors_dashboard_desc",
                            "tooltip_key": "debtors_tooltip",
                            "icon": "bi-person-plus",
                            "category": "Business"
                        },
                        {
                            "endpoint": "agents_bp.agent_portal",
                            "label": "Agent Portal",
                            "label_key": "agents_dashboard",
                            "description_key": "agents_dashboard_desc",
                            "tooltip_key": "agents_tooltip",
                            "icon": "bi-person-workspace",
                            "category": "Agent"
                        },
                        {
                            "endpoint": "coins.history",
                            "label": "Coins",
                            "label_key": "coins_dashboard",
                            "description_key": "coins_dashboard_desc",
                            "tooltip_key": "coins_tooltip",
                            "icon": "bi-coin",
                            "category": "Agent"
                        },
                        {
                            "endpoint": "news_bp.news_list",
                            "label": "News",
                            "label_key": "news_list",
                            "description_key": "news_list_desc",
                            "tooltip_key": "news_tooltip",
                            "icon": "bi-newspaper",
                            "category": "Agent"
                        }
                    ])

                for nav_list in [tools_for_template, explore_features_for_template, bottom_nav_items]:
                    for item in nav_list:
                        if not isinstance(item, dict) or 'icon' not in item or not item['icon'].startswith('bi-'):
                            logger.warning(f'Invalid or missing icon in navigation item: {item}')
                            item['icon'] = 'bi-question-circle'

                current_app.logger.debug(f"DEBUGGING ICONS (context_processor): tools_for_template (first 2 items): {tools_for_template[:2]}")
                current_app.logger.debug(f"DEBUGGING ICONS (context_processor): explore_features_for_template (first 2 items): {explore_features_for_template[:2]}")
                current_app.logger.debug(f"DEBUGGING ICONS (context_processor): bottom_nav_items (first 2 items): {bottom_nav_items[:2]}")
        except Exception as e:
            logger.error(f'Error in inject_role_nav: {str(e)}', exc_info=True)

        return dict(
            tools_for_template=tools_for_template,
            explore_features_for_template=explore_features_for_template,
            bottom_nav_items=bottom_nav_items,
            t=trans,
            lang=session.get('lang', 'en'),
            format_currency=utils.format_currency,
            format_date=utils.format_date
        )
    
    @app.context_processor
    def inject_globals():
        lang = session.get('lang', 'en')
        def context_trans(key, **kwargs):
            used_lang = kwargs.pop('lang', lang)
            return utils.trans(
                key,
                lang=used_lang,
                logger=g.get('logger', logger) if has_request_context() else logger,
                **kwargs
            )
        supported_languages = app.config.get('SUPPORTED_LANGUAGES', ['en', 'ha'])
        return {
            'google_client_id': app.config.get('GOOGLE_CLIENT_ID', ''),
            'trans': context_trans,
            'get_translations': get_translations,
            'current_year': datetime.now().year,
            'LINKEDIN_URL': app.config.get('LINKEDIN_URL', 'https://linkedin.com/company/ficoreafrica'),
            'TWITTER_URL': app.config.get('TWITTER_URL', 'https://x.com/ficoreafrica'),
            'FACEBOOK_URL': app.config.get('FACEBOOK_URL', 'https://facebook.com/ficoreafrica'),
            'FEEDBACK_FORM_URL': app.config.get('FEEDBACK_FORM_URL', url_for('general_bp.feedback')),
            'WAITLIST_FORM_URL': app.config.get('WAITLIST_FORM_URL', '#'),
            'CONSULTANCY_FORM_URL': app.config.get('CONSULTANCY_FORM_URL', '#'),
            'current_lang': lang,
            'current_user': current_user if has_request_context() else None,
            'available_languages': [
                {'code': code, 'name': utils.trans(f'general_{code}', lang=lang, default=code.capitalize())}
                for code in supported_languages
            ]
        }
    
    # Security headers
    @app.after_request
    def add_security_headers(response):
        if not request.path.startswith('/static'):
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://code.jquery.com https://cdnjs.cloudflare.com; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com https://cdnjs.cloudflare.com; "
            "img-src 'self' data:; "
            "connect-src 'self' https://api.ficore.app; "
            "font-src 'self' https://cdn.jsdelivr.net https://fonts.gstatic.com https://cdnjs.cloudflare.com;"
        )
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        return response
    
    # Language switching route
    @app.route('/change-language', methods=['POST'])
    @utils.limiter.limit('10 per minute')
    def change_language():
        try:
            data = request.get_json()
            new_lang = data.get('language', 'en')
            supported_languages = app.config.get('SUPPORTED_LANGUAGES', ['en', 'ha'])
            if new_lang in supported_languages:
                session['lang'] = new_lang
                with app.app_context():
                    if current_user.is_authenticated:
                        try:
                            app.extensions['mongo']['ficodb'].users.update_one(
                                {'_id': current_user.id}, 
                                {'$set': {'language': new_lang}}
                            )
                        except Exception as e:
                            logger.warning(f'Could not update user language preference: {str(e)}')
                
                logger.info(f'Language changed to {new_lang}', 
                           extra={'session_id': session.get('sid', 'no-session-id'), 'ip_address': request.remote_addr})
                
                return jsonify({
                    'success': True, 
                    'message': utils.trans('general_language_changed', lang=new_lang)
                })
            else:
                logger.warning(f'Invalid language requested: {new_lang}')
                return jsonify({
                    'success': False, 
                    'message': utils.trans('general_invalid_language')
                }), 400
        except Exception as e:
            logger.error(f'Error changing language: {str(e)}', 
                        extra={'session_id': session.get('sid', 'no-session-id'), 'ip_address': request.remote_addr})
            return jsonify({
                'success': False, 
                'message': utils.trans('general_error')
            }), 500
    
    # Routes
    @app.route('/', methods=['GET', 'HEAD'])
    @ensure_session_id
    def index():
        lang = session.get('lang', 'en')
        logger.info(f'Serving index page, authenticated: {current_user.is_authenticated}, user: {current_user.username if current_user.is_authenticated and hasattr(current_user, "username") else "None"}', 
                    extra={'ip_address': request.remote_addr})
        if request.method == 'HEAD':
            return '', 200
        if current_user.is_authenticated:
            if current_user.role == 'agent':
                return redirect(url_for('agents_bp.agent_portal'))
            elif current_user.role == 'trader':
                return redirect(url_for('general_bp.home'))
            elif current_user.role == 'admin':
                try:
                    return redirect(url_for('admin.dashboard'))
                except:
                    return redirect(url_for('general_bp.home'))
            elif current_user.role == 'personal':
                return redirect(url_for('personal.index'))
        try:
            with app.app_context():
                courses = app.config.get('COURSES', [])
            logger.info(f'Retrieved {len(courses)} courses')
            return render_template(
                'personal/GENERAL/index.html',
                courses=courses,
                sample_courses=courses,
                title=utils.trans('general_welcome', lang=lang),
                is_anonymous=session.get('is_anonymous', False),
                is_public=True
            )
        except TemplateNotFound as e:
            logger.error(f'Template not found: {str(e)}', exc_info=True)
            flash(utils.trans('general_error', default='Template not found'), 'danger')
            return render_template(
                'personal/GENERAL/error.html',
                error=str(e),
                title=utils.trans('general_welcome', lang=lang)
            ), 404
        except Exception as e:
            logger.error(f'Error in index route: {str(e)}', exc_info=True)
            flash(utils.trans('general_error', default='An error occurred'), 'danger')
            try:
                return render_template(
                    'errors/500.html',
                    error=str(e),
                    title=utils.trans('general_error', lang=lang)
                ), 500
            except TemplateNotFound as e:
                logger.error(f'Template not found: {str(e)}', exc_info=True)
                return render_template(
                    'personal/GENERAL/error.html',
                    error=str(e),
                    title=utils.trans('general_error', lang=lang)
                ), 500
    
    @app.route('/general_dashboard')
    @ensure_session_id
    def general_dashboard():
        logger.info(f'Redirecting to unified dashboard for {"authenticated" if current_user.is_authenticated else "anonymous"} user', 
                    extra={'ip_address': request.remote_addr})
        return redirect(url_for('dashboard_bp.index'))
    
    @app.route('/business-agent-home')
    @ensure_session_id
    def business_agent_home():
        lang = session.get('lang', 'en')
        logger.info(f'Serving business/agent home page, authenticated: {current_user.is_authenticated}', 
                    extra={'ip_address': request.remote_addr})
        if current_user.is_authenticated:
            if current_user.role == 'agent':
                return redirect(url_for('agents_bp.agent_portal'))
            elif current_user.role == 'trader':
                try:
                    return render_template(
                        'general/home.html',
                        title=utils.trans('general_business_home', lang=lang)
                    )
                except TemplateNotFound as e:
                    logger.error(f'Template not found: {str(e)}', exc_info=True)
                    return render_template(
                        'personal/GENERAL/error.html',
                        error=str(e),
                        title=utils.trans('general_business_home', lang=lang)
                    ), 404
            else:
                flash(utils.trans('general_no_permission', default='You do not have permission to access this page.'), 'danger')
                return redirect(url_for('index'))
        try:
            logger.debug('Rendering public business-agent-home page with empty navigation', 
                         extra={'ip_address': request.remote_addr})
            return render_template(
                'general/home.html',
                is_public=True,
                title=utils.trans('general_business_home', lang=lang)
            )
        except TemplateNotFound as e:
            logger.error(f'Template not found: {str(e)}', exc_info=True)
            return render_template(
                'personal/GENERAL/error.html',
                error=str(e),
                title=utils.trans('general_business_home', lang=lang)
            ), 404
    
    @app.route('/health')
    @utils.limiter.limit('10 per minute')
    def health():
        logger.debug('Health check', extra={'ip_address': request.remote_addr})
        status = {'status': 'healthy'}
        try:
            with app.app_context():
                app.extensions['mongo'].admin.command('ping')
            return jsonify(status), 200
        except Exception as e:
            logger.error(f'Health check failed: {str(e)}', exc_info=True)
            status['status'] = 'unhealthy'
            status['details'] = str(e)
            return jsonify(status), 500
    
    @app.route('/api/translations/<lang>')
    @utils.limiter.limit('10 per minute')
    def get_translations_api(lang):
        try:
            supported_languages = app.config.get('SUPPORTED_LANGUAGES', ['en', 'ha'])
            if lang not in supported_languages:
                return jsonify({'error': utils.trans('general_invalid_language')}), 400
            
            all_translations = get_all_translations()
            result = {}
            for module_name, module_translations in all_translations.items():
                if lang in module_translations:
                    result.update(module_translations[lang])
            
            return jsonify({'translations': result})
        except Exception as e:
            logger.error(f'API translations error: {str(e)}', 
                        extra={'session_id': session.get('sid', 'no-session-id'), 'ip_address': request.remote_addr})
            return jsonify({'error': utils.trans('general_error')}), 500
    
    @app.route('/api/translate')
    @utils.limiter.limit('10 per minute')
    def api_translate():
        try:
            key = request.args.get('key')
            lang = request.args.get('lang', session.get('lang', 'en'))
            supported_languages = app.config.get('SUPPORTED_LANGUAGES', ['en', 'ha'])
            if not key:
                return jsonify({'error': utils.trans('general_missing_key')}), 400
            if lang not in supported_languages:
                return jsonify({'error': utils.trans('general_invalid_language')}), 400
            
            translation = utils.trans(key, lang=lang)
            return jsonify({'key': key, 'translation': translation, 'lang': lang})
        except Exception as e:
            logger.error(f'API translate error: {str(e)}', 
                        extra={'session_id': session.get('sid', 'no-session-id'), 'ip_address': request.remote_addr})
            return jsonify({'error': utils.trans('general_error')}), 500
    
    @app.route('/set_language/<lang>')
    @utils.limiter.limit('10 per minute')
    def set_language(lang):
        supported_languages = app.config.get('SUPPORTED_LANGUAGES', ['en', 'ha'])
        new_lang = lang if lang in supported_languages else 'en'
        try:
            session['lang'] = new_lang
            with app.app_context():
                if current_user.is_authenticated:
                    app.extensions['mongo']['ficodb'].users.update_one({'_id': current_user.id}, {'$set': {'language': new_lang}})
            logger.info(f'Language set to {new_lang}', extra={'ip_address': request.remote_addr})
            flash(utils.trans('general_language_changed', default='Language updated successfully'), 'success')
        except Exception as e:
            logger.error(f'Session operation failed: {str(e)}', extra={'ip_address': request.remote_addr})
            flash(utils.trans('general_invalid_language', default='Invalid language'), 'danger')
        return redirect(request.referrer or url_for('index'))
        
    # Accounting API routes (for non-personal users)
    @app.route('/api/debt-summary')
    @login_required
    @utils.limiter.limit('10 per minute')
    def debt_summary():
        try:
            with app.app_context():
                db = app.extensions['mongo']['ficodb']
                user_id = current_user.id
                creditors_pipeline = [
                    {'$match': {'user_id': user_id, 'type': 'creditor'}},
                    {'$group': {'_id': None, 'total': {'$sum': '$amount_owed'}}}
                ]
                creditors_result = list(db.records.aggregate(creditors_pipeline))
                total_i_owe = creditors_result[0]['total'] if creditors_result else 0
                debtors_pipeline = [
                    {'$match': {'user_id': user_id, 'type': 'debtor'}},
                    {'$group': {'_id': None, 'total': {'$sum': '$amount_owed'}}}
                ]
                debtors_result = list(db.records.aggregate(debtors_pipeline))
                total_i_am_owed = debtors_result[0]['total'] if debtors_result else 0
                return jsonify({
                    'totalIOwe': total_i_owe,
                    'totalIAmOwed': total_i_am_owed
                })
        except Exception as e:
            logger.error(f'Error fetching debt summary: {str(e)}', exc_info=True, extra={'ip_address': request.remote_addr})
            return jsonify({'error': utils.trans('general_error', default='Failed to fetch debt summary')}), 500
    
    @app.route('/api/cashflow-summary')
    @login_required
    @utils.limiter.limit('10 per minute')
    def cashflow_summary():
        try:
            with app.app_context():
                db = app.extensions['mongo']['ficodb']
                user_id = current_user.id
                now = datetime.utcnow()
                month_start = datetime(now.year, now.month, 1)
                next_month = month_start.replace(month=month_start.month + 1) if month_start.month < 12 else month_start.replace(year=month_start.year + 1, month=1)
                receipts_pipeline = [
                    {'$match': {'user_id': user_id, 'type': 'receipt', 'created_at': {'$gte': month_start, '$lt': next_month}}},
                    {'$group': {'_id': None, 'total': {'$sum': '$amount'}}}
                ]
                receipts_result = list(db.cashflows.aggregate(receipts_pipeline))
                total_receipts = receipts_result[0]['total'] if receipts_result else 0
                payments_pipeline = [
                    {'$match': {'user_id': user_id, 'type': 'payment', 'created_at': {'$gte': month_start, '$lt': next_month}}},
                    {'$group': {'_id': None, 'total': {'$sum': '$amount'}}}
                ]
                payments_result = list(db.cashflows.aggregate(payments_pipeline))
                total_payments = payments_result[0]['total'] if payments_result else 0
                net_cashflow = total_receipts - total_payments
                return jsonify({
                    'netCashflow': net_cashflow,
                    'totalReceipts': total_receipts,
                    'totalPayments': total_payments
                })
        except Exception as e:
            logger.error(f'Error fetching cashflow summary: {str(e)}', exc_info=True, extra={'ip_address': request.remote_addr})
            return jsonify({'error': utils.trans('general_error', default='Failed to fetch cashflow summary')}), 500
    
    @app.route('/api/inventory-summary')
    @login_required
    @utils.limiter.limit('10 per minute')
    def inventory_summary():
        try:
            with app.app_context():
                db = app.extensions['mongo']['ficodb']
                user_id = current_user.id
                pipeline = [
                    {'$match': {'user_id': user_id}},
                    {'$addFields': {
                        'item_group': {
                            '$multiply': [
                                '$qty',
                                {'$ifNull': ['$buying_price', 0]}
                            ]
                        }
                    }},
                    {'$group': {'_id': None, 'totalValue': {'$sum': '$item_group'}}}
                ]
                result = list(db.inventory.aggregate(pipeline))
                total_value = result[0]['totalValue'] if result else 0
                return jsonify({
                    'totalValue': total_value
                })
        except Exception as e:
            logger.error(f'Error fetching inventory summary: {str(e)}', exc_info=True, extra={'ip_address': request.remote_addr})
            return jsonify({'error': utils.trans('general_error', default='Failed to fetch inventory summary')}), 500
    
    @app.route('/api/recent-activity')
    @login_required
    @utils.limiter.limit('10 per minute')
    def recent_activity():
        try:
            with app.app_context():
                db = app.extensions['mongo']['ficodb']
                user_id = current_user.id
                activities = []
                recent_records = list(db.records.find(
                    {'user_id': user_id}
                ).sort('created_at', -1).limit(3))
                for record in recent_records:
                    activity_type = 'debt_added'
                    description = f'Added {record["type"]}: {record["name"]}'
                    activities.append({
                        'type': activity_type,
                        'description': description,
                        'amount': record['amount_owed'],
                        'timestamp': record['created_at']
                    })
                recent_cashflows = list(db.cashflows.find(
                    {'user_id': user_id}
                ).sort('created_at', -1).limit(3))
                for cashflow in recent_cashflows:
                    activity_type = 'money_in' if cashflow['type'] == 'receipt' else 'money_out'
                    description = f'{"Received" if cashflow["type"] == "receipt" else "Paid"} {cashflow["party_name"]}'
                    activities.append({
                        'type': activity_type,
                        'description': description,
                        'amount': cashflow['amount'],
                        'timestamp': cashflow['created_at']
                    })
                activities.sort(key=lambda x: x['timestamp'], reverse=True)
                activities = activities[:5]
                for activity in activities:
                    activity['timestamp'] = activity['timestamp'].isoformat()
                return jsonify(activities)
        except Exception as e:
            logger.error(f'Error fetching recent activity: {str(e)}', exc_info=True, extra={'ip_address': request.remote_addr})
            return jsonify({'error': utils.trans('general_error', default='Failed to fetch recent activity')}), 500
    
    @app.route('/api/notifications/count')
    @login_required
    @utils.limiter.limit('10 per minute')
    def notification_count():
        try:
            with app.app_context():
                db = app.extensions['mongo']['ficodb']
                user_id = current_user.id
                count = db.reminder_logs.count_documents({
                    'user_id': user_id,
                    'read_status': False
                })
                return jsonify({'count': count})
        except Exception as e:
            logger.error(f'Error fetching notification count: {str(e)}', exc_info=True, extra={'ip_address': request.remote_addr})
            return jsonify({'error': utils.trans('general_error', default='Failed to fetch notification count')}), 500
    
    @app.route('/api/notifications')
    @login_required
    @utils.limiter.limit('10 per minute')
    def notifications():
        try:
            with app.app_context():
                db = app.extensions['mongo']['ficodb']
                user_id = current_user.id
                lang = session.get('lang', 'en')
                notifications = list(db.reminder_logs.find({
                    'user_id': user_id
                }).sort('sent_at', -1).limit(10))
                logger.debug(f"Fetched {len(notifications)} notifications for user {user_id}")
                result = [{
                    'id': str(n['notification_id']),
                    'message': utils.trans(n['message'], lang=lang, default=n['message']),
                    'type': n['type'],
                    'timestamp': n['sent_at'].isoformat(),
                    'read': n.get('read_status', False)
                } for n in notifications]
                notification_ids = [n['notification_id'] for n in notifications if not n.get('read_status', False)]
                if notification_ids:
                    db.reminder_logs.update_many(
                        {'notification_id': {'$in': notification_ids}, 'user_id': user_id},
                        {'$set': {'read_status': True}}
                    )
                    logger.debug(f"Marked {len(notification_ids)} notifications as read for user {user_id}")
                    return jsonify({'notifications': result}), 200
        except Exception as e:
            logger.error(f'Error fetching notifications: {str(e)}', exc_info=True, extra={'ip_address': request.remote_addr})
            return jsonify({'error': utils.trans('general_error', default='Failed to fetch notifications')}), 500
    
    @app.route('/setup', methods=['GET'])
    @utils.limiter.limit('10 per minute')
    def setup_database_route():
        setup_key = request.args.get('key')
        if not app.config['SETUP_KEY'] or setup_key != app.config['SETUP_KEY']:
            logger.warning(f'Invalid setup key: {setup_key}', extra={'ip_address': request.remote_addr})
            try:
                return render_template(
                    'errors/403.html',
                    content=utils.trans('general_access_denied', default='Access denied'),
                    title=utils.trans('general_access_denied', lang=session.get('lang', 'en'))
                ), 403
            except TemplateNotFound as e:
                logger.error(f'Template not found: {str(e)}', exc_info=True)
                return render_template(
                    'personal/GENERAL/error.html',
                    content=utils.trans('general_access_denied', default='Access denied'),
                    error=str(e),
                    title=utils.trans('general_access_denied', lang=session.get('lang', 'en'))
                ), 403
        try:
            with app.app_context():
                initialize_database(app)
            flash(utils.trans('general_success', default='Database setup successful'), 'success')
            logger.info('Database setup completed', extra={'ip_address': request.remote_addr})
            return redirect(url_for('index'))
        except Exception as e:
            flash(utils.trans('general_error', default='An error occurred during database setup'), 'danger')
            logger.error(f'Database setup error: {str(e)}', exc_info=True, extra={'ip_address': request.remote_addr})
            try:
                return render_template(
                    'errors/500.html',
                    content=utils.trans('general_error', default='Internal server error'),
                    error=str(e),
                    title=utils.trans('general_error', lang=session.get('lang', 'en'))
                ), 500
            except TemplateNotFound as e:
                logger.error(f'Template not found: {str(e)}', exc_info=True)
                return render_template(
                    'personal/GENERAL/error.html',
                    content=utils.trans('general_error', default='Internal server error'),
                    error=str(e),
                    title=utils.trans('general_error', lang=session.get('lang', 'en'))
                ), 500
    
    @app.route('/static/<path:filename>')
    def static_files(filename):
        if '..' in filename or filename.startswith('/'):
            logger.warning(f'Invalid static file path: {filename}', extra={'ip_address': request.remote_addr})
            abort(403)
        response = send_from_directory('static', filename)
        response.headers['Cache-Control'] = 'public, max-age=31536000'
        return response

    @app.route('/static_personal/<path:filename>')
    def static_personal(filename):
        allowed_extensions = {'.css', '.js', '.png', '.jpg', '.jpeg', '.gif', '.ico', '.svg'}
        file_ext = os.path.splitext(filename)[1].lower()
        if '..' in filename or filename.startswith('/') or file_ext not in allowed_extensions:
            logger.warning(f'Invalid static_personal file path or extension: {filename}', extra={'ip_address': request.remote_addr})
            abort(403)

        try:
            response = send_from_directory('static_personal', filename)
            if file_ext in {'.css', '.js'}:
                response.headers['Cache-Control'] = 'public, max-age=31536000'
            elif file_ext in {'.png', '.jpg', '.jpeg', '.gif', '.ico', '.svg'}:
                response.headers['Cache-Control'] = 'public, max-age=604800'
            return response
        except FileNotFoundError:
            logger.error(f'Static file not found: {filename}', extra={'ip_address': request.remote_addr})
            abort(404)
                
    @app.route('/favicon.ico')
    def favicon():
        try:
            return send_from_directory(app.static_folder, 'img/favicon.ico')
        except FileNotFoundError:
            logger.error('Favicon not found', extra={'ip_address': request.remote_addr})
            abort(404)
    
    @app.route('/service-worker.js')
    def service_worker():
        try:
            return app.send_static_file('js/service-worker.js')
        except FileNotFoundError:
            logger.error('Service worker file not found', extra={'ip_address': request.remote_addr})
            abort(404)
    
    @app.route('/manifest.json')
    def manifest():
        manifest_data = {
            "name": "FiCore",
            "short_name": "FiCore",
            "description": "Financial management application for personal and business use",
            "start_url": "/",
            "display": "standalone",
            "background_color": "#ffffff",
            "theme_color": "#007bff",
            "icons": [
                {
                    "src": "/static/img/icon-192x192.png",
                    "sizes": "192x192",
                    "type": "image/png"
                },
                {
                    "src": "/static/img/icon-512x512.png",
                    "sizes": "512x512",
                    "type": "image/png"
                }
            ],
            "lang": session.get('lang', 'en'),
            "dir": "ltr",
            "orientation": "portrait",
            "scope": "/",
            "related_applications": [],
            "prefer_related_applications": False
        }
        return jsonify(manifest_data)

    # Error handlers
    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        logger.error(f'CSRF error: {str(e)}', extra={'session_id': session.get('sid', 'no-session-id'), 'ip_address': request.remote_addr})
        try:
            return render_template(
                'errors/403.html', 
                error=utils.trans('general_csrf_error', default='Invalid CSRF token'), 
                title=utils.trans('general_csrf_error', lang=session.get('lang', 'en'))
            ), 403
        except TemplateNotFound:
            return render_template(
                'personal/GENERAL/error.html', 
                error=utils.trans('general_csrf_error', default='Invalid CSRF token'), 
                title=utils.trans('general_csrf_error', lang=session.get('lang', 'en'))
            ), 403

    @app.errorhandler(404)
    def page_not_found(e):
        logger.error(f'Page not found: {request.url}', extra={'session_id': session.get('sid', 'no-session-id'), 'ip_address': request.remote_addr})
        try:
            return render_template(
                'errors/404.html', 
                error=str(e), 
                title=utils.trans('general_not_found', lang=session.get('lang', 'en'))
            ), 404
        except TemplateNotFound:
            return render_template(
                'personal/GENERAL/error.html', 
                error=str(e), 
                title=utils.trans('general_not_found', lang=session.get('lang', 'en'))
            ), 404

    @app.errorhandler(500)
    def internal_server_error(e):
        logger.error(f'Internal server error: {str(e)}', exc_info=True, extra={'session_id': session.get('sid', 'no-session-id'), 'ip_address': request.remote_addr})
        try:
            return render_template(
                'errors/500.html', 
                error=str(e), 
                title=utils.trans('general_error', lang=session.get('lang', 'en'))
            ), 500
        except TemplateNotFound:
            return render_template(
                'personal/GENERAL/error.html', 
                error=str(e), 
                title=utils.trans('general_error', lang=session.get('lang', 'en'))
            ), 500

    return app

app = create_app()

if __name__ == '__main__':
    logger.info('Starting Flask app with gunicorn')
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=os.getenv('FLASK_ENV', 'development') == 'development')
