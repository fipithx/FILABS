from flask import Blueprint, render_template, redirect, url_for, flash, session, request, jsonify, make_response
from flask_login import login_required, current_user
from translations import trans
from jinja2.exceptions import TemplateNotFound
from datetime import datetime
from models import create_feedback
from flask_wtf.csrf import CSRFError
from flask import current_app
import utils

general_bp = Blueprint('general_bp', __name__, url_prefix='/general')

@general_bp.route('/home')
@login_required
def home():
    """Trader homepage."""
    if current_user.role not in ['trader', 'admin']:
        flash(trans('general_access_denied', default='You do not have permission to access this page.'), 'danger')
        return redirect(url_for('index'))
    
    return render_template(
        'general/home.html',
        title=trans('general_business_home', lang=session.get('lang', 'en'))
    )

@general_bp.route('/about')
def about():
    """Public about page."""
    return render_template(
        'general/about.html',
        title=trans('general_about', lang=session.get('lang', 'en'))
    )

@general_bp.route('/contact')
def contact():
    """Public contact page."""
    return render_template(
        'general/contact.html',
        title=trans('general_contact', lang=session.get('lang', 'en'))
    )

@general_bp.route('/privacy')
def privacy():
    """Public privacy policy page."""
    lang = session.get('lang', 'en')
    try:
        return render_template(
            'general/privacy.html',
            title=trans('general_privacy', lang=lang)
        )
    except TemplateNotFound as e:
        current_app.logger.error(f'Template not found: {str(e)}', exc_info=True)
        return render_template(
            'personal/GENERAL/error.html',
            error=str(e),
            title=trans('general_privacy', lang=lang)
        ), 404

@general_bp.route('/terms')
def terms():
    """Public terms of service page."""
    lang = session.get('lang', 'en')
    try:
        return render_template(
            'general/terms.html',
            title=trans('general_terms', lang=lang)
        )
    except TemplateNotFound as e:
        current_app.logger.error(f'Template not found: {str(e)}', exc_info=True)
        return render_template(
            'personal/GENERAL/error.html',
            error=str(e),
            title=trans('general_terms', lang=lang)
        ), 404

@general_bp.route('/feedback', methods=['GET', 'POST'])
@utils.limiter.limit('10 per minute')
def feedback():
    """Public feedback page."""
    lang = session.get('lang', 'en')
    current_app.logger.info('Handling feedback', extra={'ip_address': request.remote_addr})
    tool_options = [
        ['profile', trans('general_profile', default='Profile')],
        ['coins', trans('coins_dashboard', default='Coins')],
        ['debtors', trans('debtors_dashboard', default='Debtors')],
        ['creditors', trans('creditors_dashboard', default='Creditors')],
        ['receipts', trans('receipts_dashboard', default='Receipts')],
        ['payment', trans('payments_dashboard', default='Payments')],
        ['inventory', trans('inventory_dashboard', default='Inventory')],
        ['report', trans('reports_dashboard', default='Reports')],
        ['financial_health', trans('financial_health_calculator', default='Financial Health')],
        ['budget', trans('budget_budget_planner', default='Budget')],
        ['bill', trans('bill_bill_planner', default='Bill')],
        ['net_worth', trans('net_worth_calculator', default='Net Worth')],
        ['emergency_fund', trans('emergency_fund_calculator', default='Emergency Fund')],
        ['learning', trans('learning_hub_courses', default='Learning')],
        ['quiz', trans('quiz_personality_quiz', default='Quiz')],
        ['taxation', trans('taxation_calculator', default='Taxation')],
        ['news', trans('news_updates', default='News')]
    ]
    if request.method == 'POST':
        try:
            tool_name = request.form.get('tool_name')
            rating = request.form.get('rating')
            comment = request.form.get('comment', '').strip()
            valid_tools = [option[0] for option in tool_options]
            if not tool_name or tool_name not in valid_tools:
                current_app.logger.error(f'Invalid feedback tool: {tool_name}', extra={'ip_address': request.remote_addr})
                flash(trans('general_invalid_input', default='Please select a valid tool'), 'danger')
                return render_template('general/feedback.html', tool_options=tool_options, title=trans('general_feedback', lang=lang))
            if not rating or not rating.isdigit() or int(rating) < 1 or int(rating) > 5:
                current_app.logger.error(f'Invalid rating: {rating}', extra={'ip_address': request.remote_addr})
                flash(trans('general_invalid_input', default='Please provide a rating between 1 and 5'), 'danger')
                return render_template('general/feedback.html', tool_options=tool_options, title=trans('general_feedback', lang=lang))
            with current_app.app_context():
                from models import get_mongo_db
                if current_user.is_authenticated:
                    from utils import get_user_query
                    query = get_user_query(str(current_user.id))
                    result = get_mongo_db().users.update_one(query, {'$inc': {'coin_balance': -1}})
                    if result.matched_count == 0:
                        raise ValueError(f'No user found for ID {current_user.id}')
                    get_mongo_db().coin_transactions.insert_one({
                        'user_id': str(current_user.id),
                        'amount': -1,
                        'type': 'spend',
                        'ref': f'FEEDBACK_{datetime.utcnow().isoformat()}',
                        'date': datetime.utcnow()
                    })
                feedback_entry = {
                    'user_id': current_user.id if current_user.is_authenticated else None,
                    'session_id': session.get('sid', 'no-session-id'),
                    'tool_name': tool_name,
                    'rating': int(rating),
                    'comment': comment or None,
                    'timestamp': datetime.utcnow()
                }
                create_feedback(get_mongo_db(), feedback_entry)
                get_mongo_db().audit_logs.insert_one({
                    'admin_id': 'system',
                    'action': 'submit_feedback',
                    'details': {'user_id': str(current_user.id) if current_user.is_authenticated else None, 'tool_name': tool_name},
                    'timestamp': datetime.utcnow()
                })
            current_app.logger.info(f'Feedback submitted: tool={tool_name}, rating={rating}', 
                                   extra={'session_id': session.get('sid', 'no-session-id'), 'ip_address': request.remote_addr})
            flash(trans('general_thank_you', default='Thank you for your feedback!'), 'success')
            return redirect(url_for('index'))
        except ValueError as e:
            current_app.logger.error(f'User not found: {str(e)}', extra={'ip_address': request.remote_addr})
            flash(trans('general_error', default='User not found'), 'danger')
            return render_template('general/feedback.html', tool_options=tool_options, title=trans('general_feedback', lang=lang)), 400
        except Exception as e:
            current_app.logger.error(f'Error processing feedback: {str(e)}', exc_info=True, extra={'ip_address': request.remote_addr})
            flash(trans('general_error', default='Error occurred during feedback submission'), 'danger')
            try:
                return render_template('general/feedback.html', tool_options=tool_options, title=trans('general_feedback', lang=lang)), 500
            except TemplateNotFound as e:
                current_app.logger.error(f'Template not found: {str(e)}', exc_info=True)
                return render_template('personal/GENERAL/error.html', error=str(e), title=trans('general_feedback', lang=lang)), 500
