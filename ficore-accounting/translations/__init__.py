import logging
from flask import session, has_request_context, g, request  
from typing import Dict, Optional, Union

# Set up logger to match app.py
root_logger = logging.getLogger('ficore_app')
root_logger.setLevel(logging.DEBUG)

class SessionFormatter(logging.Formatter):
    def format(self, record):
        record.session_id = getattr(record, 'session_id', 'no_session_id')
        return super().format(record)

formatter = SessionFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s [session: %(session_id)s]')

class SessionAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        kwargs['extra'] = kwargs.get('extra', {})
        session_id = kwargs['extra'].get('session_id', 'no-session-id')
        if has_request_context():
            session_id = session.get('sid', 'no-session-id')
        kwargs['extra']['session_id'] = session_id
        return msg, kwargs

logger = SessionAdapter(root_logger, {})

# Import translation modules
try:
    # Personal Finance Tools
    from .personal_finance.bill_translations import BILL_TRANSLATIONS
    from .personal_finance.budget_translations import BUDGET_TRANSLATIONS
    from .personal_finance.emergency_fund_translations import EMERGENCY_FUND_TRANSLATIONS
    from .personal_finance.financial_health_translations import FINANCIAL_HEALTH_TRANSLATIONS
    from .personal_finance.net_worth_translations import NET_WORTH_TRANSLATIONS
    from .personal_finance.learning_hub_translations import LEARNING_HUB_TRANSLATIONS
    from .personal_finance.quiz_translations import QUIZ_TRANSLATIONS
    
    # Accounting Tools
    from .accounting_tools.admin_translations import ADMIN_TRANSLATIONS
    from .accounting_tools.agents_translations import AGENTS_TRANSLATIONS
    from .accounting_tools.coins_translations import COINS_TRANSLATIONS
    from .accounting_tools.creditors_translations import CREDITORS_TRANSLATIONS
    from .accounting_tools.debtors_translations import DEBTORS_TRANSLATIONS
    from .accounting_tools.inventory_translations import INVENTORY_TRANSLATIONS
    from .accounting_tools.payments_translations import PAYMENTS_TRANSLATIONS
    from .accounting_tools.receipts_translations import RECEIPTS_TRANSLATIONS
    from .accounting_tools.reports_translations import REPORTS_TRANSLATIONS
    
    # General Tools
    from .general_tools.general_translations import GENERAL_TRANSLATIONS
    from .general_tools.common_features_translations import COMMON_FEATURES_TRANSLATIONS
    
except ImportError as e:
    logger.error(f"Failed to import translation module: {str(e)}", exc_info=True)
    raise

# Map module names to translation dictionaries
translation_modules = {
    # Personal Finance
    'bill': BILL_TRANSLATIONS,
    'budget': BUDGET_TRANSLATIONS,
    'emergency_fund': EMERGENCY_FUND_TRANSLATIONS,
    'financial_health': FINANCIAL_HEALTH_TRANSLATIONS,
    'net_worth': NET_WORTH_TRANSLATIONS,
    'learning_hub': LEARNING_HUB_TRANSLATIONS,
    'quiz': QUIZ_TRANSLATIONS,
    
    # Accounting Tools
    'admin': ADMIN_TRANSLATIONS,
    'agents': AGENTS_TRANSLATIONS,
    'coins': COINS_TRANSLATIONS,
    'creditors': CREDITORS_TRANSLATIONS,
    'debtors': DEBTORS_TRANSLATIONS,
    'inventory': INVENTORY_TRANSLATIONS,
    'payments': PAYMENTS_TRANSLATIONS,
    'receipts': RECEIPTS_TRANSLATIONS,
    'reports': REPORTS_TRANSLATIONS,
    
    # General Tools
    'general': GENERAL_TRANSLATIONS,
    'common_features': COMMON_FEATURES_TRANSLATIONS,
}

# Map key prefixes to module names
KEY_PREFIX_TO_MODULE = {
    # Personal Finance prefixes
    'bill_': 'bill',
    'budget_': 'budget',
    'emergency_fund_': 'emergency_fund',
    'financial_health_': 'financial_health',
    'net_worth_': 'net_worth',
    'learning_hub_': 'learning_hub',
    'quiz_': 'quiz',
    'badge_': 'quiz',  # Route badge_ keys to quiz translations
    
    # Accounting Tools prefixes
    'admin_': 'admin',
    'agents_': 'agents',
    'coins_': 'coins',
    'creditors_': 'creditors',
    'debtors_': 'debtors',
    'inventory_': 'inventory',
    'payments_': 'payments',
    'receipts_': 'receipts',
    'reports_': 'reports',
    
    # General Tools prefixes
    'general_': 'general',
    'news_': 'common_features',
    'tax_': 'common_features',
    'notifications_': 'common_features',
    'search_': 'common_features',
    'filter_': 'common_features',
    'export_': 'common_features',
    'import_': 'common_features',
    'backup_': 'common_features',
    'maintenance_': 'common_features',
    'api_': 'common_features',
    'webhook_': 'common_features',
}

# Quiz-specific keys without prefixes
QUIZ_SPECIFIC_KEYS = {'Yes', 'No', 'See Results'}

# General-specific keys without prefixes (common navigation and UI elements)
GENERAL_SPECIFIC_KEYS = {
    'Home', 'About', 'Contact', 'Login', 'Logout', 'Register', 'Profile',
    'Settings', 'Help', 'Support', 'Terms', 'Privacy', 'FAQ', 'Documentation',
    'Get Started', 'Learn More', 'Try Now', 'Sign Up', 'Sign In', 'Welcome',
    'Dashboard', 'Tools', 'Features', 'Pricing', 'Blog', 'News', 'Updates',
    'Save', 'Cancel', 'Submit', 'Edit', 'Delete', 'Add', 'Create', 'Update',
    'View', 'Search', 'Filter', 'Sort', 'Export', 'Import', 'Print', 'Download',
    'Upload', 'Back', 'Next', 'Previous', 'Continue', 'Finish', 'Close', 'Open'
}

# Log loaded translations
for module_name, translations in translation_modules.items():
    for lang in ['en', 'ha']:
        lang_dict = translations.get(lang, {})
        logger.info(f"Loaded {len(lang_dict)} translations for module '{module_name}', lang='{lang}'")

def trans(key: str, lang: Optional[str] = None, **kwargs: str) -> str:
    """
    Translate a key using the appropriate module's translation dictionary.
    
    Args:
        key: The translation key (e.g., 'bill_submit', 'general_welcome', 'quiz_yes', 'Yes').
        lang: Language code ('en', 'ha'). Defaults to session['lang'] or 'en'.
        **kwargs: String formatting parameters for the translated string.
    
    Returns:
        The translated string, falling back to English or the key itself if missing.
        Applies string formatting with kwargs if provided.
    
    Notes:
        - Uses session['lang'] if lang is None and request context exists.
        - Logs warnings for missing translations.
        - Uses g.logger if available, else the default logger.
        - Checks general translations for common UI elements without prefixes.
    """
    current_logger = g.get('logger', logger) if has_request_context() else logger
    session_id = session.get('sid', 'no-session-id') if has_request_context() else 'no-session-id'

    # Default to session language or 'en'
    if lang is None:
        lang = session.get('lang', 'en') if has_request_context() else 'en'
    if lang not in ['en', 'ha']:
        current_logger.warning(f"Invalid language '{lang}', falling back to 'en'", extra={'session_id': session_id})
        lang = 'en'

    # Determine module based on key prefix or specific keys
    module_name = 'general'  # Default to general instead of core
    
    # Check for specific prefix mappings first
    for prefix, mod in KEY_PREFIX_TO_MODULE.items():
        if key.startswith(prefix):
            module_name = mod
            break
    
    # Check for quiz-specific keys
    if key in QUIZ_SPECIFIC_KEYS and has_request_context() and '/quiz/' in request.path:
        module_name = 'quiz'
    
    # Check for general-specific keys (common UI elements)
    elif key in GENERAL_SPECIFIC_KEYS:
        module_name = 'general'
    
    # If no specific module found and key doesn't have a prefix, check general
    elif '_' not in key:
        # Try general module for unprefixed general keys
        general_module = translation_modules.get('general', {})
        general_lang_dict = general_module.get(lang, {})
        if key in general_lang_dict:
            module_name = 'general'

    module = translation_modules.get(module_name, translation_modules['general'])
    lang_dict = module.get(lang, {})

    # Get translation
    translation = lang_dict.get(key)

    # Fallback to English, then key
    if translation is None:
        en_dict = module.get('en', {})
        translation = en_dict.get(key, key)
        if translation == key:
            current_logger.warning(
                f"Missing translation for key='{key}' in module '{module_name}', lang='{lang}'",
                extra={'session_id': session_id}
            )

    # Apply string formatting
    try:
        return translation.format(**kwargs) if kwargs else translation
    except (KeyError, ValueError) as e:
        current_logger.error(
            f"Formatting failed for key '{key}', lang='{lang}', kwargs={kwargs}, error={str(e)}",
            extra={'session_id': session_id}
        )
        return translation

def get_translations(lang: Optional[str] = None) -> Dict[str, callable]:
    """
    Return a dictionary with a trans callable for the specified language.

    Args:
        lang: Language code ('en', 'ha'). Defaults to session['lang'] or 'en'.

    Returns:
        A dictionary with a 'trans' function that translates keys for the specified language.
    """
    if lang is None:
        lang = session.get('lang', 'en') if has_request_context() else 'en'
    if lang not in ['en', 'ha']:
        logger.warning(f"Invalid language '{lang}', falling back to 'en'")
        lang = 'en'
    return {
        'trans': lambda key, **kwargs: trans(key, lang=lang, **kwargs)
    }

def get_all_translations() -> Dict[str, Dict[str, Dict[str, str]]]:
    """
    Get all translations from all modules.
    
    Returns:
        A dictionary with module names as keys and their translation dictionaries as values.
    """
    return translation_modules.copy()

def get_module_translations(module_name: str, lang: Optional[str] = None) -> Dict[str, str]:
    """
    Get translations for a specific module and language.
    
    Args:
        module_name: Name of the translation module (e.g., 'general', 'bill', 'quiz').
        lang: Language code ('en', 'ha'). Defaults to session['lang'] or 'en'.
    
    Returns:
        Dictionary of translations for the specified module and language.
    """
    if lang is None:
        lang = session.get('lang', 'en') if has_request_context() else 'en'
    
    module = translation_modules.get(module_name, {})
    return module.get(lang, {})

__all__ = ['trans', 'get_translations', 'get_all_translations', 'get_module_translations']
