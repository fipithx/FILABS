from flask import Blueprint, jsonify, current_app, redirect, url_for, flash, render_template, request, session, make_response
from flask_login import current_user, login_required
from utils import requires_role, is_admin, get_mongo_db, limiter
import utils
from translations import trans
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)

personal_bp = Blueprint('personal', __name__, url_prefix='/personal', template_folder='templates/personal')

# Register all personal finance sub-blueprints
from personal.bill import bill_bp
from personal.budget import budget_bp
from personal.emergency_fund import emergency_fund_bp
from personal.financial_health import financial_health_bp
from personal.net_worth import net_worth_bp
from personal.quiz import quiz_bp
from personal.summaries import summaries_bp

personal_bp.register_blueprint(bill_bp)
personal_bp.register_blueprint(budget_bp)
personal_bp.register_blueprint(emergency_fund_bp)
personal_bp.register_blueprint(financial_health_bp)
personal_bp.register_blueprint(net_worth_bp)
personal_bp.register_blueprint(quiz_bp)
personal_bp.register_blueprint(summaries_bp)

def init_app(app):
    """Initialize all personal finance sub-blueprints."""
    try:
        for blueprint in [bill_bp, budget_bp, emergency_fund_bp, financial_health_bp, net_worth_bp, quiz_bp, summaries_bp]:
            if hasattr(blueprint, 'init_app'):
                blueprint.init_app(app)
                current_app.logger.info(f"Initialized {blueprint.name} blueprint", extra={'session_id': 'no-request-context'})
        current_app.logger.info("Personal finance blueprints initialized successfully", extra={'session_id': 'no-request-context'})
    except Exception as e:
        current_app.logger.error(f"Error initializing personal finance blueprints: {str(e)}", extra={'session_id': 'no-request-context'})
        raise

@personal_bp.route('/')
@login_required
@requires_role(['personal', 'admin'])
def index():
    """Render the personal finance dashboard."""
    try:
        current_app.logger.info(f"Accessing personal.index - User: {current_user.id}, Authenticated: {current_user.is_authenticated}, Session: {dict(session)}")
        response = make_response(render_template(
            'personal/GENERAL/index.html',
            title=trans('general_welcome', lang=session.get('lang', 'en'), default='Welcome'),
            tools_for_template=utils.PERSONAL_TOOLS,
            explore_features_for_template=utils.PERSONAL_EXPLORE_FEATURES,
            is_admin=is_admin(),
            is_anonymous=False,
            is_public=False
        ))
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    except Exception as e:
        current_app.logger.error(f"Error rendering personal index: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
        flash(trans('general_error', default='An error occurred'), 'danger')
        response = make_response(render_template(
            'personal/GENERAL/error.html',
            error_message="Unable to load the personal finance dashboard due to an internal error.",
            title=trans('general_welcome', lang=session.get('lang', 'en'), default='Welcome'),
            is_admin=is_admin()
        ), 500)
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        return response
