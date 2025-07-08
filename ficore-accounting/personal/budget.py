from flask import Blueprint, request, session, redirect, url_for, render_template, flash, current_app, jsonify
from flask_wtf import FlaskForm
from flask_wtf.csrf import CSRFProtect, CSRFError
from wtforms import StringField, FloatField, BooleanField, SubmitField
from wtforms.validators import DataRequired, NumberRange, Email, ValidationError
from flask_login import current_user, login_required
from mailersend_email import send_email, EMAIL_CONFIG
from datetime import datetime
import re
from translations import trans
from bson import ObjectId
from models import log_tool_usage
from session_utils import create_anonymous_session
from utils import requires_role, is_admin, get_mongo_db, limiter

budget_bp = Blueprint(
    'budget',
    __name__,
    template_folder='templates/budget',
    url_prefix='/budget'
)

csrf = CSRFProtect()

def strip_commas(value):
    """Strip commas from string values."""
    if isinstance(value, str):
        return value.replace(',', '')
    return value

def custom_login_required(f):
    """Custom login decorator that allows both authenticated users and anonymous sessions."""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.is_authenticated or session.get('is_anonymous', False):
            return f(*args, **kwargs)
        return redirect(url_for('users.login', next=request.url))
    return decorated_function

class BudgetForm(FlaskForm):
    first_name = StringField(trans('general_first_name', default='First Name'))
    email = StringField(trans('general_email', default='Email'))
    send_email = BooleanField(trans('general_send_email', default='Send Email'))
    income = FloatField(trans('budget_monthly_income', default='Monthly Income'), filters=[strip_commas])
    housing = FloatField(trans('budget_housing_rent', default='Housing/Rent'), filters=[strip_commas])
    food = FloatField(trans('budget_food', default='Food'), filters=[strip_commas])
    transport = FloatField(trans('budget_transport', default='Transport'), filters=[strip_commas])
    dependents = FloatField(trans('budget_dependents_support', default='Dependents Support'), filters=[strip_commas])
    miscellaneous = FloatField(trans('budget_miscellaneous', default='Miscellaneous'), filters=[strip_commas])
    others = FloatField(trans('budget_others', default='Others'), filters=[strip_commas])
    savings_goal = FloatField(trans('budget_savings_goal', default='Savings Goal'), filters=[strip_commas])
    submit = SubmitField(trans('budget_submit', default='Submit'))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        lang = session.get('lang', 'en')
        self.first_name.validators = [DataRequired(message=trans('general_first_name_required', lang))]
        self.email.validators = []
        self.income.validators = [
            DataRequired(message=trans('budget_income_required', lang)),
            NumberRange(min=0, max=10000000000, message=trans('budget_income_max', lang))
        ]
        for field in [self.housing, self.food, self.transport, self.dependents, self.miscellaneous, self.others]:
            field.validators = [
                DataRequired(message=trans(f'budget_{field.name}_required', lang)),
                NumberRange(min=0, message=trans('budget_amount_positive', lang))
            ]
        self.savings_goal.validators = [
            DataRequired(message=trans('budget_savings_goal_required', lang)),
            NumberRange(min=0, message=trans('budget_amount_positive', lang))
        ]

    def validate_email(self, field):
        if self.send_email.data and not field.data:
            current_app.logger.warning(f"Email required for notifications for session {session.get('sid', 'no-session-id')}")
            raise ValidationError(trans('budget_email_required', session.get('lang', 'en')))
        if field.data:
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(email_pattern, field.data):
                current_app.logger.warning(f"Invalid email format for session {session.get('sid', 'no-session-id')}: {field.data}")
                raise ValidationError(trans('general_email_invalid', session.get('lang', 'en')))

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators):
            return False
        for field in [self.income, self.housing, self.food, self.transport, self.dependents, self.miscellaneous, self.others, self.savings_goal]:
            try:
                if field.data is not None:
                    field.data = float(field.data)
                current_app.logger.debug(f"Validated {field.name} for session {session.get('sid', 'no-session-id')}: {field.data}")
            except (ValueError, TypeError):
                current_app.logger.warning(f"Invalid {field.name} value for session {session.get('sid', 'no-session-id')}: {field.data}")
                field.errors.append(trans('budget_amount_invalid', session.get('lang', 'en')))
                return False
        return True

@budget_bp.route('/main', methods=['GET', 'POST'])
@custom_login_required
@requires_role(['personal', 'admin'])
def main():
    """Main budget management interface with tabbed layout."""
    if 'sid' not in session:
        create_anonymous_session()
        current_app.logger.debug(f"New anonymous session created with sid: {session['sid']}", extra={'session_id': session['sid']})
    session.permanent = True
    session.modified = True
    form_data = {}
    if current_user.is_authenticated:
        form_data['email'] = current_user.email
        form_data['first_name'] = current_user.get_first_name()
    form = BudgetForm(data=form_data)
    try:
        log_tool_usage(
            get_mongo_db(),
            tool_name='budget',
            user_id=current_user.id if current_user.is_authenticated else None,
            session_id=session['sid'],
            action='main_view'
        )
    except Exception as e:
        current_app.logger.error(f"Failed to log tool usage: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
        flash(trans('budget_log_error', default='Error logging budget activity. Please try again.'), 'warning')
    
    try:
        filter_criteria = {} if is_admin() else {'user_id': current_user.id} if current_user.is_authenticated else {'session_id': session['sid']}
        if request.method == 'POST':
            action = request.form.get('action')
            if action == 'create_budget' and form.validate_on_submit():
                try:
                    log_tool_usage(
                        get_mongo_db(),
                        tool_name='budget',
                        user_id=current_user.id if current_user.is_authenticated else None,
                        session_id=session['sid'],
                        action='create_budget'
                    )
                except Exception as e:
                    current_app.logger.error(f"Failed to log budget creation: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
                    flash(trans('budget_log_error', default='Error logging budget creation. Continuing with submission.'), 'warning')
                
                income = form.income.data
                expenses = sum([
                    form.housing.data,
                    form.food.data,
                    form.transport.data,
                    form.dependents.data,
                    form.miscellaneous.data,
                    form.others.data
                ])
                savings_goal = form.savings_goal.data
                surplus_deficit = income - expenses
                budget_data = {
                    '_id': ObjectId(),
                    'user_id': current_user.id if current_user.is_authenticated else None,
                    'session_id': session['sid'],
                    'user_email': form.email.data,
                    'income': income,
                    'fixed_expenses': expenses,
                    'variable_expenses': 0,
                    'savings_goal': savings_goal,
                    'surplus_deficit': surplus_deficit,
                    'housing': form.housing.data,
                    'food': form.food.data,
                    'transport': form.transport.data,
                    'dependents': form.dependents.data,
                    'miscellaneous': form.miscellaneous.data,
                    'others': form.others.data,
                    'created_at': datetime.utcnow()
                }
                try:
                    get_mongo_db().budgets.insert_one(budget_data)
                    current_app.logger.info(f"Budget saved successfully to MongoDB for session {session['sid']}", extra={'session_id': session['sid']})
                    flash(trans("budget_completed_success", default='Budget created successfully!'), "success")
                except Exception as e:
                    current_app.logger.error(f"Failed to save budget to MongoDB for session {session['sid']}: {str(e)}", extra={'session_id': session['sid']})
                    flash(trans("budget_storage_error", default='Error saving budget.'), "danger")
                    return render_template(
                        'personal/BUDGET/budget_main.html',
                        form=form,
                        budgets={},
                        latest_budget={},
                        categories={},
                        tips=[],
                        insights=[],
                        tool_title=trans('budget_title', default='Budget Planner')
                    )
                if form.send_email.data and form.email.data:
                    try:
                        config = EMAIL_CONFIG["budget"]
                        subject = trans(config["subject_key"], default='Your Budget Summary')
                        template = config["template"]
                        send_email(
                            app=current_app,
                            logger=current_app.logger,
                            to_email=form.email.data,
                            subject=subject,
                            template_name=template,
                            data={
                                "first_name": form.first_name.data,
                                "income": income,
                                "expenses": expenses,
                                "housing": form.housing.data,
                                "food": form.food.data,
                                "transport": form.transport.data,
                                "dependents": form.dependents.data,
                                "miscellaneous": form.miscellaneous.data,
                                "others": form.others.data,
                                "savings_goal": savings_goal,
                                "surplus_deficit": surplus_deficit,
                                "created_at": budget_data['created_at'].strftime('%Y-%m-%d'),
                                "cta_url": url_for('budget.main', _external=True)
                            },
                            lang=session.get('lang', 'en')
                        )
                        current_app.logger.info(f"Email sent to {form.email.data}", extra={'session_id': session['sid']})
                    except Exception as e:
                        current_app.logger.error(f"Failed to send email: {str(e)}", extra={'session_id': session['sid']})
                        flash(trans("general_email_send_failed", default='Failed to send email.'), "warning")
            elif action == 'delete':
                budget_id = request.form.get('budget_id')
                try:
                    result = get_mongo_db().budgets.delete_one({'_id': ObjectId(budget_id), **filter_criteria})
                    if result.deleted_count > 0:
                        current_app.logger.info(f"Deleted budget ID {budget_id} for session {session['sid']}", extra={'session_id': session['sid']})
                        flash(trans("budget_deleted_success", default='Budget deleted successfully!'), "success")
                    else:
                        current_app.logger.warning(f"Budget ID {budget_id} not found for session {session['sid']}", extra={'session_id': session['sid']})
                        flash(trans("budget_not_found", default='Budget not found.'), "danger")
                except Exception as e:
                    current_app.logger.error(f"Failed to delete budget ID {budget_id} for session {session['sid']}: {str(e)}", extra={'session_id': session['sid']})
                    flash(trans("budget_delete_failed", default='Error deleting budget.'), "danger")
        budgets = list(get_mongo_db().budgets.find(filter_criteria).sort('created_at', -1))
        current_app.logger.info(f"Read {len(budgets)} records from MongoDB budgets collection [session: {session['sid']}]", extra={'session_id': session['sid']})
        budgets_dict = {}
        latest_budget = None
        for budget in budgets:
            budget_data = {
                'id': str(budget['_id']),
                'user_id': budget.get('user_id'),
                'session_id': budget.get('session_id'),
                'user_email': budget.get('user_email'),
                'income': budget.get('income', 0.0),
                'fixed_expenses': budget.get('fixed_expenses', 0.0),
                'variable_expenses': budget.get('variable_expenses', 0.0),
                'savings_goal': budget.get('savings_goal', 0.0),
                'surplus_deficit': budget.get('surplus_deficit', 0.0),
                'housing': budget.get('housing', 0.0),
                'food': budget.get('food', 0.0),
                'transport': budget.get('transport', 0.0),
                'dependents': budget.get('dependents', 0.0),
                'miscellaneous': budget.get('miscellaneous', 0.0),
                'others': budget.get('others', 0.0),
                'created_at': budget.get('created_at').strftime('%Y-%m-%d') if budget.get('created_at') else 'N/A'
            }
            budgets_dict[budget_data['id']] = budget_data
            if not latest_budget or budget.get('created_at') > datetime.strptime(latest_budget['created_at'], '%Y-%m-%d') if latest_budget['created_at'] != 'N/A' else budget.get('created_at'):
                latest_budget = budget_data
        if not latest_budget:
            latest_budget = {
                'income': 0.0,
                'fixed_expenses': 0.0,
                'surplus_deficit': 0.0,
                'savings_goal': 0.0,
                'housing': 0.0,
                'food': 0.0,
                'transport': 0.0,
                'dependents': 0.0,
                'miscellaneous': 0.0,
                'others': 0.0,
                'created_at': 'N/A'
            }
        categories = {
            'Housing/Rent': latest_budget.get('housing', 0),
            'Food': latest_budget.get('food', 0),
            'Transport': latest_budget.get('transport', 0),
            'Dependents': latest_budget.get('dependents', 0),
            'Miscellaneous': latest_budget.get('miscellaneous', 0),
            'Others': latest_budget.get('others', 0)
        }
        tips = [
            trans("budget_tip_track_expenses", default='Track your expenses daily to stay within budget.'),
            trans("budget_tip_ajo_savings", default='Contribute to ajo savings for financial discipline.'),
            trans("budget_tip_data_subscriptions", default='Optimize data subscriptions to reduce costs.'),
            trans("budget_tip_plan_dependents", default='Plan for dependents’ expenses in advance.')
        ]
        insights = []
        if latest_budget.get('income', 0) > 0:
            if latest_budget.get('surplus_deficit', 0) < 0:
                insights.append(trans("budget_insight_budget_deficit", default='Your expenses exceed your income. Consider reducing costs.'))
            elif latest_budget.get('surplus_deficit', 0) > 0:
                insights.append(trans("budget_insight_budget_surplus", default='You have a surplus. Consider increasing savings.'))
            if latest_budget.get('savings_goal', 0) == 0:
                insights.append(trans("budget_insight_set_savings_goal", default='Set a savings goal to build financial security.'))
        return render_template(
            'personal/BUDGET/budget_main.html',
            form=form,
            budgets=budgets_dict,
            latest_budget=latest_budget,
            categories=categories,
            tips=tips,
            insights=insights,
            tool_title=trans('budget_title', default='Budget Planner')
        )
    except Exception as e:
        current_app.logger.error(f"Unexpected error in budget.main for session {session.get('sid', 'unknown')}: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
        flash(trans("budget_dashboard_load_error", default='Error loading budget dashboard.'), "danger")
        return render_template(
            'personal/BUDGET/budget_main.html',
            form=form,
            budgets={},
            latest_budget={
                'income': 0.0,
                'fixed_expenses': 0.0,
                'surplus_deficit': 0.0,
                'savings_goal': 0.0,
                'housing': 0.0,
                'food': 0.0,
                'transport': 0.0,
                'dependents': 0.0,
                'miscellaneous': 0.0,
                'others': 0.0,
                'created_at': 'N/A'
            },
            categories={},
            tips=[],
            insights=[],
            tool_title=trans('budget_title', default='Budget Planner')
        ), 500

@budget_bp.route('/summary')
@login_required
@requires_role(['personal', 'admin'])
def summary():
    """Return summary of the latest budget for the current user."""
    try:
        filter_criteria = {} if is_admin() else {'user_id': current_user.id}
        budgets_collection = get_mongo_db().budgets
        latest_budget = budgets_collection.find(filter_criteria).sort('created_at', -1).limit(1)
        latest_budget = list(latest_budget)
        if not latest_budget:
            current_app.logger.info(f"No budget found for user {current_user.id}", extra={'session_id': session.get('sid', 'unknown')})
            return jsonify({'totalBudget': 0.0})
        total_budget = latest_budget[0].get('income', 0.0)
        current_app.logger.info(f"Fetched budget summary for user {current_user.id}: {total_budget}", extra={'session_id': session.get('sid', 'unknown')})
        return jsonify({'totalBudget': total_budget})
    except Exception as e:
        current_app.logger.error(f"Error in budget.summary: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
        return jsonify({'totalBudget': 0.0}), 500

@budget_bp.errorhandler(CSRFError)
def handle_csrf_error(e):
    """Handle CSRF errors with user-friendly message."""
    current_app.logger.error(f"CSRF error on {request.path}: {e.description}", extra={'session_id': session.get('sid', 'unknown')})
    flash(trans('budget_csrf_error', default='Form submission failed due to a missing security token. Please refresh and try again.'), 'danger')
    return redirect(url_for('personal.index')), 400
