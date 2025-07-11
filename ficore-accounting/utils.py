import re
import logging
import uuid
import os
import certifi
from datetime import datetime
from flask import session, has_request_context, current_app, url_for, request
from flask_mail import Mail
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from translations import trans
import requests
from werkzeug.routing import BuildError

# Flask extensions
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
root_logger = logging.getLogger('ficore_app.utils')
root_logger.setLevel(logging.DEBUG)

class SessionFormatter(logging.Formatter):
    def format(self, record):
        record.session_id = getattr(record, 'session_id', 'no_session_id')
        record.ip_address = getattr(record, 'ip_address', 'unknown')
        return super().format(record)

class SessionAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        kwargs['extra'] = kwargs.get('extra', {})
        session_id = 'no-session-id'
        ip_address = 'unknown'
        try:
            if has_request_context():
                session_id = session.get('sid', 'no-session-id')
                ip_address = request.remote_addr
            else:
                session_id = 'no-request-context'
        except Exception as e:
            session_id = 'session-error'
            kwargs['extra']['session_error'] = str(e)
        kwargs['extra']['session_id'] = session_id
        kwargs['extra']['ip_address'] = ip_address
        return msg, kwargs

logger = SessionAdapter(root_logger, {})

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
        "endpoint": "personal.bill.main",
        "label": "Bills",
        "label_key": "bill_bill_planner",
        "description_key": "bill_bill_desc",
        "tooltip_key": "bill_tooltip",
        "icon": "bi-receipt"
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
        "endpoint": "coins.history",
        "label": "Coins",
        "label_key": "coins_dashboard",
        "description_key": "coins_dashboard_desc",
        "tooltip_key": "coins_tooltip",
        "icon": "bi-coin"
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
        "endpoint": "personal.quiz.main",
        "label": "Quiz",
        "label_key": "quiz_personality_quiz",
        "description_key": "quiz_personality_desc",
        "tooltip_key": "quiz_tooltip",
        "icon": "bi-question-circle"
    },
    {
        "endpoint": "learning_hub.main",
        "label": "Learning Hub",
        "label_key": "learning_hub_main",
        "description_key": "learning_hub_desc",
        "tooltip_key": "learning_hub_tooltip",
        "icon": "bi-book"
    },
    {
        "endpoint": "personal.net_worth.main",
        "label": "Net Worth",
        "label_key": "net_worth_calculator",
        "description_key": "net_worth_desc",
        "tooltip_key": "net_worth_tooltip",
        "icon": "bi-cash-stack"
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
    {
        "endpoint": "learning_hub.main",
        "label": "Learning Hub",
        "label_key": "learning_hub_main",
        "description_key": "learning_hub_desc",
        "tooltip_key": "learning_hub_tooltip",
        "icon": "bi-book"
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
        "icon": "bi-journal-minus"
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
        "endpoint": "coins.history",
        "label": "Coins",
        "label_key": "coins_dashboard",
        "description_key": "coins_dashboard_desc",
        "tooltip_key": "coins_tooltip",
        "icon": "bi-coin"
    },
    {
        "endpoint": "learning_hub.main",
        "label": "Learning Hub",
        "label_key": "learning_hub_main",
        "description_key": "learning_hub_desc",
        "tooltip_key": "learning_hub_tooltip",
        "icon": "bi-book"
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
        "endpoint": "creditors.index",
        "label": "I Owe",
        "label_key": "creditors_dashboard",
        "description_key": "creditors_dashboard_desc",
        "tooltip_key": "creditors_tooltip",
        "icon": "bi-person-lines"
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
    {
        "endpoint": "payments.index",
        "label": "MoneyOut",
        "label_key": "payments_dashboard",
        "description_key": "payments_dashboard",
        "tooltip_key": "payments_tooltip",
        "icon": "bi-calculator"
    },
    {
        "endpoint": "learning_hub.main",
        "label": "Learning Hub",
        "label_key": "learning_hub_main",
        "description_key": "learning_hub_desc",
        "tooltip_key": "learning_hub_tooltip",
        "icon": "bi-book"
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
        "endpoint": "learning_hub.main",
        "label": "Learning Hub",
        "label_key": "learning_hub_main",
        "description_key": "learning_hub_desc",
        "tooltip_key": "learning_hub_tooltip",
        "icon": "bi-book"
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
    {
        "endpoint": "learning_hub.main",
        "label": "Learning Hub",
        "label_key": "learning_hub_main",
        "description_key": "learning_hub_desc",
        "tooltip_key": "learning_hub_tooltip",
        "icon": "bi-book"
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
    {
        "endpoint": "learning_hub.main",
        "label": "Learning Hub",
        "label_key": "learning_hub_main",
        "description_key": "learning_hub_desc",
        "tooltip_key": "learning_hub_tooltip",
        "icon": "bi-book"
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
    {
        "endpoint": "learning_hub.main",
        "label": "Learning Hub",
        "label_key": "learning_hub_main",
        "description_key": "learning_hub_desc",
        "tooltip_key": "learning_hub_tooltip",
        "icon": "bi-book"
    },
]

def get_explore_features():
    """Return explore features for unauthenticated users on the landing page."""
    try:
        with current_app.app_context():
            return generate_tools_with_urls([
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
                    "label_key": "proof_coins_dashboard",
                    "description_key": "proof_coins_desc",
                    "tooltip_key": "coins_tooltip",
                    "icon": "bi-coin",
                    "category": "Proof of Concept"
                },
                {
                    "endpoint": "news_bp.news_list",
                    "label": "News",
                    "label_key": "news_list",
                    "description_key": "news_list_desc",
                    "tooltip_key": "news_tooltip",
                    "icon": "bi-newspaper",
                    "category": "News"
                },
                {
                    "endpoint": "learning_hub.main",
                    "label": "Learning Hub",
                    "label_key": "learning_hub_main",
                    "description_key": "learning_hub_desc",
                    "tooltip_key": "learning_hub_tooltip",
                    "icon": "bi-book",
                    "category": "Learning"
                }
            ])
    except Exception as e:
        logger.error(f"Error generating explore features: {str(e)}", exc_info=True)
        return []

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
    
    try:
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
    except Exception as e:
        logger.error(f'Error initializing tools with URLs: {str(e)}', exc_info=True)
        raise

def generate_tools_with_urls(tools):
    '''
    Generate a list of tools with resolved URLs and validated icons.
    
    Args:
        tools: List of dictionaries containing 'endpoint' and 'icon' keys
    
    Returns:
        List of dictionaries with 'url' keys added and validated 'icon' fields
    '''
    result = []
    for tool in tools:
        try:
            url = url_for(tool['endpoint'], _external=True)
            # Validate icon field; use fallback if missing or invalid
            icon = tool.get('icon', 'bi-question-circle')
            if not icon or not icon.startswith('bi-'):
                logger.warning(f"Invalid or missing icon for tool {tool.get('label', 'unknown')}: {icon}. Using fallback 'bi-question-circle'.")
                icon = 'bi-question-circle'
            result.append({**tool, 'url': url, 'icon': icon})
        except BuildError as e:
            logger.warning(f"Failed to generate URL for endpoint {tool.get('endpoint', 'unknown')}: {str(e)}. Ensure endpoint is defined in blueprint.")
            result.append({**tool, 'url': '#', 'icon': tool.get('icon', 'bi-question-circle')})
        except RuntimeError as e:
            logger.warning(f"Runtime error generating URL for endpoint {tool.get('endpoint', 'unknown')}: {str(e)}")
            result.append({**tool, 'url': '#', 'icon': tool.get('icon', 'bi-question-circle')})
    return result

def get_limiter():
    '''
    Return the initialized Flask-Limiter instance.
    
    Returns:
        Limiter: The configured Flask-Limiter instance
    '''
    return limiter

def log_tool_usage(action, details=None, user_id=None, db=None, session_id=None):
    '''
    Log tool usage to MongoDB with improved error handling and session support.
    
    Args:
        action (str): The action performed (e.g., 'main_view', 'add_bill').
        details (dict, optional): Additional details about the action.
        user_id (str, optional): ID of the user performing the action.
        db (MongoDB database, optional): MongoDB database instance. If None, fetched via get_mongo_db().
        session_id (str, optional): Session ID for the action.
    
    Raises:
        RuntimeError: If database connection fails or insertion fails.
    '''
    try:
        # Fetch database instance if not provided
        if db is None:
            db = get_mongo_db()
        
        # Validate inputs
        if not action or not isinstance(action, str):
            raise ValueError("Action must be a non-empty string")
        
        # Use provided session_id or fetch from session
        effective_session_id = session_id or session.get('sid', 'no-session-id') if has_request_context() else 'no-session-id'
        
        # Prepare log entry
        log_entry = {
            'action': action,
            'details': details or {},
            'user_id': str(user_id) if user_id else None,
            'session_id': effective_session_id,
            'timestamp': datetime.utcnow(),
            'ip_address': request.remote_addr if has_request_context() else 'unknown',
            'user_agent': request.headers.get('User-Agent') if has_request_context() else 'unknown'
        }
        
        # Insert log entry into MongoDB
        db.tool_usage_logs.insert_one(log_entry)
        logger.info(
            f"Logged tool usage: {action}",
            extra={
                'user_id': user_id or 'unknown',
                'session_id': effective_session_id,
                'ip_address': request.remote_addr if has_request_context() else 'unknown'
            }
        )
    except ValueError as e:
        logger.error(
            f"Invalid input for log_tool_usage: {str(e)}",
            exc_info=True,
            extra={
                'user_id': user_id or 'unknown',
                'session_id': session_id or session.get('sid', 'no-session-id') if has_request_context() else 'no-session-id',
                'ip_address': request.remote_addr if has_request_context() else 'unknown'
            }
        )
        raise
    except Exception as e:
        logger.error(
            f"Failed to log tool usage for action {action}: {str(e)}",
            exc_info=True,
            extra={
                'user_id': user_id or 'unknown',
                'session_id': session_id or session.get('sid', 'no-session-id') if has_request_context() else 'no-session-id',
                'ip_address': request.remote_addr if has_request_context() else 'unknown'
            }
        )
        raise RuntimeError(f"Failed to log tool usage: {str(e)}")

def create_anonymous_session():
    '''
    Create a guest session for anonymous access.
    '''
    try:
        with current_app.app_context():
            session['sid'] = str(uuid.uuid4())
            session['is_anonymous'] = True
            session['created_at'] = datetime.utcnow().isoformat()
            if 'lang' not in session:
                session['lang'] = 'en'
            logger.info(f"{trans('general_anonymous_session_created', default='Created anonymous session')}: {session['sid']}")
    except Exception as e:
        logger.error(f"{trans('general_anonymous_session_error', default='Error creating anonymous session')}: {str(e)}", exc_info=True)
        raise

def clean_currency(value):
    if not value or not isinstance(value, str):
        return float(value) if isinstance(value, (int, float)) else 0.0
    # Remove currency symbols and non-numeric characters
    cleaned = re.sub(r'[^\d.]', '', value)
    try:
        return float(cleaned) if cleaned else 0.0
    except ValueError:
        logger.warning(f"Invalid currency value: {value}")
        return 0.0
        
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
        with current_app.app_context():
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
    Get MongoDB database instance from the application extensions.
    
    Returns:
        Database object
    '''
    try:
        with current_app.app_context():
            if 'mongo' not in current_app.extensions:
                mongo_uri = os.getenv('MONGO_URI')
                if not mongo_uri:
                    logger.error("MONGO_URI environment variable not set",
                                extra={'session_id': session.get('sid', 'no-session-id'), 'ip_address': request.remote_addr if has_request_context() else 'unknown'})
                    raise RuntimeError("MONGO_URI environment variable not set")
                
                client = MongoClient(
                    mongo_uri,
                    serverSelectionTimeoutMS=5000,
                    tls=True,
                    tlsCAFile=certifi.where() if os.getenv('MONGO_CA_FILE') is None else os.getenv('MONGO_CA_FILE'),
                    maxPoolSize=50,
                    minPoolSize=5
                )
                client.admin.command('ping')
                current_app.extensions['mongo'] = client
                logger.info("MongoDB client initialized successfully in utils.get_mongo_db",
                           extra={'session_id': session.get('sid', 'no-session-id'), 'ip_address': request.remote_addr if has_request_context() else 'unknown'})
            
            db = current_app.extensions['mongo']['ficodb']
            # Verify connection
            db.command('ping')
            return db
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB database: {str(e)}",
                    exc_info=True, extra={'session_id': session.get('sid', 'no-session-id'), 'ip_address': request.remote_addr if has_request_context() else 'unknown'})
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
        with app.app_context():
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
            with current_app.app_context():
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
        with current_app.app_context():
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
        with current_app.app_context():
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
        with current_app.app_context():
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
        with current_app.app_context():
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
        with current_app.app_context():
            return session.get('lang', 'en') if has_request_context() else 'en'
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
        with current_app.app_context():
            from flask_login import current_user
            from flask import request
            if user_id is None and current_user.is_authenticated:
                user_id = current_user.id
            session_id = session.get('sid', 'no-session-id') if has_request_context() else 'no-session-id'
            log_entry = {
                'user_id': user_id,
                'session_id': session_id,
                'action': action,
                'details': details or {},
                'timestamp': datetime.utcnow(),
                'ip_address': request.remote_addr if has_request_context() else None,
                'user_agent': request.headers.get('User-Agent') if has_request_context() else None
            }
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
        with current_app.app_context():
            recipient = re.sub(r'\D', '', recipient)
            if recipient.startswith('0'):
                recipient = '234' + recipient[1:]
            elif not recipient.startswith('+'):
                recipient = '234' + recipient
            sms_api_url = current_app.config.get('SMS_API_URL', 'https://api.smsprovider.com/send')
            sms_api_key = current_app.config.get('SMS_API_KEY', '')
            if not sms_api_key:
                logger.warning('SMS_API_KEY not set, cannot send SMS')
                return False, {'error': 'SMS_API_KEY not configured'}
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
        with current_app.app_context():
            recipient = re.sub(r'\D', '', recipient)
            if recipient.startswith('0'):
                recipient = '234' + recipient[1:]
            elif not recipient.startswith('+'):
                recipient = '234' + recipient
            whatsapp_api_url = current_app.config.get('WHATSAPP_API_URL', 'https://api.whatsapp.com/send')
            whatsapp_api_key = current_app.config.get('WHATSAPP_API_KEY', '')
            if not whatsapp_api_key:
                logger.warning('WHATSAPP_API_KEY not set, cannot send WhatsApp message')
                return False, {'error': 'WHATSAPP_API_KEY not configured'}
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

# Activity fetching functions
def get_recent_activities(user_id=None, is_admin_user=False, db=None, session_id=None, limit=10):
    '''
    Fetch recent activities across all tools for a user or session.
    
    Args:
        user_id: ID of the user (optional for admin)
        is_admin_user: Whether the user is an admin (default: False)
        db: MongoDB database instance (optional)
        session_id: Session ID for anonymous users (optional)
        limit: Maximum number of activities to return (default: 10)
    
    Returns:
        list: List of recent activity records
    '''
    if db is None:
        db = get_mongo_db()
    
    # Build query based on user_id or session_id
    query = {} if is_admin_user else {'user_id': str(user_id)} if user_id else {'session_id': session_id} if session_id else {}
    
    try:
        activities = []
        
        # Fetch recent bills
        bills = db.bills.find(query).sort('created_at', -1).limit(5)
        for bill in bills:
            if not bill.get('created_at') or not bill.get('bill_name'):
                logger.warning(f"Skipping invalid bill record: {bill.get('_id')}", extra={'session_id': session_id or 'unknown', 'ip': request.remote_addr or 'unknown'})
                continue
            activities.append({
                'type': 'bill',
                'description': trans('recent_activity_bill_added', default='Added bill: {name}', name=bill.get('bill_name', 'Unknown')),
                'timestamp': bill.get('created_at', datetime.utcnow()).isoformat(),
                'details': {
                    'amount': bill.get('amount', 0),
                    'due_date': bill.get('due_date', 'N/A'),
                    'status': bill.get('status', 'Unknown')
                },
                'icon': 'bi-receipt'
            })

        # Fetch recent budgets
        budgets = db.budgets.find(query).sort('created_at', -1).limit(5)
        for budget in budgets:
            activities.append({
                'type': 'budget',
                'description': trans('recent_activity_budget_created', default='Created budget with income: {amount}', amount=budget.get('income', 0)),
                'timestamp': budget.get('created_at', datetime.utcnow()).isoformat(),
                'details': {
                    'income': budget.get('income', 0),
                    'surplus_deficit': budget.get('surplus_deficit', 0)
                },
                'icon': 'bi-cash-coin'
            })

        # Fetch recent net worth records
        net_worths = db.net_worth_data.find(query).sort('created_at', -1).limit(5)
        for nw in net_worths:
            activities.append({
                'type': 'net_worth',
                'description': trans('recent_activity_net_worth_calculated', default='Calculated net worth: {amount}', amount=nw.get('net_worth', 0)),
                'timestamp': nw.get('created_at', datetime.utcnow()).isoformat(),
                'details': {
                    'net_worth': nw.get('net_worth', 0),
                    'total_assets': nw.get('total_assets', 0),
                    'total_liabilities': nw.get('total_liabilities', 0)
                },
                'icon': 'bi-graph-up'
            })

        # Fetch recent financial health scores
        health_scores = db.financial_health_scores.find(query).sort('created_at', -1).limit(5)
        for hs in health_scores:
            activities.append({
                'type': 'financial_health',
                'description': trans('recent_activity_health_score', default='Calculated financial health score: {score}', score=hs.get('score', 0)),
                'timestamp': hs.get('created_at', datetime.utcnow()).isoformat(),
                'details': {
                    'score': hs.get('score', 0),
                    'status': hs.get('status', 'Unknown')
                },
                'icon': 'bi-heart-pulse'
            })

        # Fetch recent emergency fund plans
        emergency_funds = db.emergency_funds.find(query).sort('created_at', -1).limit(5)
        for ef in emergency_funds:
            activities.append({
                'type': 'emergency_fund',
                'description': trans('recent_activity_emergency_fund_created', default='Created emergency fund plan with target: {amount}', amount=ef.get('target_amount', 0)),
                'timestamp': ef.get('created_at', datetime.utcnow()).isoformat(),
                'details': {
                    'target_amount': ef.get('target_amount', 0),
                    'savings_gap': ef.get('savings_gap', 0),
                    'monthly_savings': ef.get('monthly_savings', 0)
                },
                'icon': 'bi-piggy-bank'
            })

        # Fetch recent quiz results
        quizzes = db.quiz_responses.find(query).sort('created_at', -1).limit(5)
        for quiz in quizzes:
            activities.append({
                'type': 'quiz',
                'description': trans('recent_activity_quiz_completed', default='Completed financial quiz with score: {score}', score=quiz.get('score', 0)),
                'timestamp': quiz.get('created_at', datetime.utcnow()).isoformat(),
                'details': {
                    'score': quiz.get('score', 0),
                    'personality': quiz.get('personality', 'N/A')
                },
                'icon': 'bi-question-circle'
            })

        # Fetch recent learning hub progress
        learning_hub_progress = db.learning_materials.find({
            **query,
            'type': {'$ne': 'course'}  # Exclude course definitions, include progress records
        }).sort('updated_at', -1).limit(5)
        for progress in learning_hub_progress:
            if not progress.get('course_id') or not progress.get('updated_at'):
                logger.warning(f"Skipping invalid learning hub progress record: {progress.get('_id')}", extra={'session_id': session_id or 'unknown', 'ip': request.remote_addr or 'unknown'})
                continue
            course = db.learning_materials.find_one({'type': 'course', 'id': progress.get('course_id')})
            course_title = course.get('title_en', progress.get('course_id', 'Unknown')) if course else progress.get('course_id', 'Unknown')
            activities.append({
                'type': 'learning_hub',
                'description': trans('recent_activity_learning_hub_progress', default='Made progress in course: {course_title}', course_title=course_title),
                'timestamp': progress.get('updated_at', datetime.utcnow()).isoformat(),
                'details': {
                    'course_id': progress.get('course_id', 'N/A'),
                    'course_title': course_title,
                    'lessons_completed': len(progress.get('lessons_completed', [])),
                    'current_lesson': progress.get('current_lesson', 'N/A'),
                    'coins_earned': progress.get('coins_earned', 0),
                    'badges_earned': progress.get('badges_earned', [])
                },
                'icon': 'bi-book',
                'url': url_for('learning_hub.main', _external=True) if has_request_context() else '#'
            })

        activities.sort(key=lambda x: x['timestamp'], reverse=True)
        
        # Log successful fetch
        logger.debug(
            f"Fetched {len(activities)} recent activities for {'user ' + str(user_id) if user_id else 'session ' + str(session_id) if session_id else 'all'}",
            extra={'session_id': session_id or 'unknown', 'ip': request.remote_addr or 'unknown'}
        )
        
        return activities[:limit]
    except Exception as e:
        logger.error(
            f"Failed to fetch recent activities: {str(e)}",
            exc_info=True,
            extra={'session_id': session_id or 'unknown', 'ip': request.remote_addr or 'unknown'}
        )
        raise

def get_all_recent_activities(user_id=None, is_admin_user=False, db=None, session_id=None, limit=10):
    '''
    Fetch recent activities across all tools for a user or session.
    
    Args:
        user_id: ID of the user (optional for admin)
        is_admin_user: Whether the user is an admin (default: False)
        db: MongoDB database instance (optional)
        session_id: Session ID for anonymous users (optional)
        limit: Maximum number of activities to return (default: 10)
    
    Returns:
        list: List of recent activity records
    '''
    return get_recent_activities(user_id, is_admin_user, db, session_id, limit)

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
        'current_lesson': record.get('current_lesson'),
        'coins_earned': record.get('coins_earned', 0),
        'badges_earned': record.get('badges_earned', [])
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
    'login_manager', 'clean_currency', 'log_tool_usage', 'flask_session', 'csrf', 'babel', 'compress', 'limiter',
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
    'ADMIN_TOOLS', 'ADMIN_NAV', 'ADMIN_EXPLORE_FEATURES', 'ALL_TOOLS', 'get_explore_features',
    'get_recent_activities', 'get_all_recent_activities'
]
