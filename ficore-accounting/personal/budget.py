from flask import Blueprint, request, session, redirect, url_for, render_template, flash, current_app, jsonify
from flask_wtf import FlaskForm
from flask_wtf.csrf import CSRFProtect, CSRFError
from wtforms import StringField, FloatField, BooleanField, SubmitField
from wtforms.validators import DataRequired, NumberRange, Email, ValidationError
from flask_login import current_user, login_required
from mailersend_email import send_email, EMAIL_CONFIG
from utils import get_all_recent_activities, requires_role, is_admin, get_mongo_db, limiter
from datetime import datetime
import re
from translations import trans
from bson import ObjectId
from models import log_tool_usage
from session_utils import create_anonymous_session

budget_bp = Blueprint(
    'budget',
    __name__,
    template_folder='templates/budget',
    url_prefix='/budget'
)

csrf = CSRFProtect()

def clean_currency(value):
    """Strip commas and handle edge cases for numeric inputs."""
    if not value or value == '0':
        return '0'
    if isinstance(value, str):
        # Remove commas, whitespace, and other non-numeric characters (except decimal point)
        value = re.sub(r'[^\d.]', '', value.strip())
        # Ensure only one decimal point
        parts = value.split('.')
        if len(parts) > 2:
            value = parts[0] + '.' + ''.join(parts[1:])
        # Handle empty or invalid cases
        if not value or value == '.':
            return '0'
        try:
            float_value = float(value)
            current_app.logger.debug(f"Cleaned value: '{value}' -> {float_value}", extra={'session_id': session.get('sid', 'unknown')})
            return str(float_value)
        except ValueError as e:
            current_app.logger.warning(f"Invalid value: '{value}' - Error: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
            return '0'
    return str(float(value))

def strip_commas(value):
    """Strip commas from string values, delegating to clean_currency."""
    if isinstance(value, str):
        return clean_currency(value)
    return str(value)

def format_currency(value):
    """Format a numeric value with comma separation, no currency symbol."""
    try:
        if isinstance(value, str):
            cleaned_value = clean_currency(value)
            numeric_value = float(cleaned_value)
        else:
            numeric_value = float(value)
        formatted = f"{numeric_value:,.2f}"
        current_app.logger.debug(f"Formatted value: input={value}, output={formatted}", extra={'session_id': session.get('sid', 'unknown')})
        return formatted
    except (ValueError, TypeError) as e:
        current_app.logger.warning(f"Format Error: input={value}, error={str(e)}", extra={'session_id': session.get('sid', 'unknown')})
        return "0.00"

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
            current_app.logger.warning(f"Email required for notifications for session {session.get('sid', 'no-session-id')}", extra={'session_id': session.get('sid', 'no-session-id')})
            raise ValidationError(trans('budget_email_required', session.get('lang', 'en')))
        if field.data:
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(email_pattern, field.data):
                current_app.logger.warning(f"Invalid email format for session {session.get('sid', 'no-session-id')}: {field.data}", extra={'session_id': session.get('sid', 'no-session-id')})
                raise ValidationError(trans('general_email_invalid', session.get('lang', 'en')))

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators):
            return False
        for field in [self.income, self.housing, self.food, self.transport, self.dependents, self.miscellaneous, self.others, self.savings_goal]:
            try:
                cleaned_value = clean_currency(str(field.data or '0'))
                field.data = float(cleaned_value)
                current_app.logger.debug(f"Validated {field.name}: raw={field.data}, cleaned={cleaned_value}", extra={'session_id': session.get('sid', 'no-session-id')})
            except (ValueError, TypeError) as e:
                current_app.logger.warning(f"Invalid {field.name} value: raw={field.data}, error={str(e)}", extra={'session_id': session.get('sid', 'no-session-id')})
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
        form_data['email'] = current_user.email or ''
        form_data['first_name'] = current_user.get_first_name() or ''
    form = BudgetForm(data=form_data)
    db = get_mongo_db()
    
    # Get active tab from query parameter (defaults to 'create-budget')
    active_tab = request.args.get('tab', 'create-budget')
    
    try:
        log_tool_usage(
            tool_name='budget',
            db=db,
            user_id=current_user.id if current_user.is_authenticated else None,
            session_id=session.get('sid', 'unknown'),
            action='main_view'
        )
    except Exception as e:
        current_app.logger.error(f"Failed to log tool usage: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
        flash(trans('budget_log_error', default='Error logging budget activity. Please try again.'), 'warning')
    
    # Fetch recent activities for the current user or session
    try:
        activities = get_all_recent_activities(
            db=db,
            user_id=current_user.id if current_user.is_authenticated else None,
            session_id=session.get('sid', 'unknown') if not current_user.is_authenticated else None,

        )
        current_app.logger.debug(f"Fetched {len(activities)} recent activities for {'user ' + str(current_user.id) if current_user.is_authenticated else 'session ' + session.get('sid', 'unknown')}", extra={'session_id': session.get('sid', 'unknown')})
    except Exception as e:
        current_app.logger.error(f"Failed to fetch recent activities: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
        flash(trans('budget_activities_load_error', default='Error loading recent activities.'), 'warning')
        activities = []
    
    try:
        filter_criteria = {} if is_admin() else {'user_id': current_user.id} if current_user.is_authenticated else {'session_id': session['sid']}
        if request.method == 'POST':
            action = request.form.get('action')
            if action == 'create_budget' and form.validate_on_submit():
                try:
                    log_tool_usage(
                        tool_name='budget',
                        db=db,
                        user_id=current_user.id if current_user.is_authenticated else None,
                        session_id=session.get('sid', 'unknown'),
                        action='create_budget'
                    )
                except Exception as e:
                    current_app.logger.error(f"Failed to log budget creation: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
                    flash(trans('budget_log_error', default='Error logging budget creation. Continuing with submission.'), 'warning')
                
                # Use raw float values for calculations
                income = float(form.income.data)
                expenses = sum([
                    float(form.housing.data),
                    float(form.food.data),
                    float(form.transport.data),
                    float(form.dependents.data),
                    float(form.miscellaneous.data),
                    float(form.others.data)
                ])
                savings_goal = float(form.savings_goal.data)
                surplus_deficit = income - expenses
                budget_data = {
                    '_id': ObjectId(),
                    'user_id': current_user.id if current_user.is_authenticated else None,
                    'session_id': session['sid'],
                    'user_email': form.email.data,
                    'income': income,
                    'fixed_expenses': expenses,
                    'variable_expenses': 0.0,
                    'savings_goal': savings_goal,
                    'surplus_deficit': surplus_deficit,
                    'housing': float(form.housing.data),
                    'food': float(form.food.data),
                    'transport': float(form.transport.data),
                    'dependents': float(form.dependents.data),
                    'miscellaneous': float(form.miscellaneous.data),
                    'others': float(form.others.data),
                    'created_at': datetime.utcnow()
                }
                current_app.logger.debug(f"Saving budget data: {budget_data}", extra={'session_id': session['sid']})
                try:
                    db.budgets.insert_one(budget_data)
                    current_app.logger.info(f"Budget saved successfully to MongoDB for session {session['sid']}", extra={'session_id': session['sid']})
                    flash(trans("budget_completed_success", default='Budget created successfully!'), "success")
                    # Redirect to dashboard tab after successful budget creation
                    return redirect(url_for('budget.main', tab='dashboard'))
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
                        activities=activities,
                        tool_title=trans('budget_title', default='Budget Planner'),
                        active_tab='create-budget'
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
                                "income": format_currency(income),
                                "expenses": format_currency(expenses),
                                "housing": format_currency(float(form.housing.data)),
                                "food": format_currency(float(form.food.data)),
                                "transport": format_currency(float(form.transport.data)),
                                "dependents": format_currency(float(form.dependents.data)),
                                "miscellaneous": format_currency(float(form.miscellaneous.data)),
                                "others": format_currency(float(form.others.data)),
                                "savings_goal": format_currency(savings_goal),
                                "surplus_deficit": format_currency(surplus_deficit),
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
                    log_tool_usage(
                        tool_name='budget',
                        db=db,
                        user_id=current_user.id if current_user.is_authenticated else None,
                        session_id=session.get('sid', 'unknown'),
                        action='delete_budget'
                    )
                    result = db.budgets.delete_one({'_id': ObjectId(budget_id), **filter_criteria})
                    if result.deleted_count > 0:
                        current_app.logger.info(f"Deleted budget ID {budget_id} for session {session['sid']}", extra={'session_id': session['sid']})
                        flash(trans("budget_deleted_success", default='Budget deleted successfully!'), "success")
                    else:
                        current_app.logger.warning(f"Budget ID {budget_id} not found for session {session['sid']}", extra={'session_id': session['sid']})
                        flash(trans("budget_not_found", default='Budget not found.'), "danger")
                except Exception as e:
                    current_app.logger.error(f"Failed to delete budget ID {budget_id} for session {session['sid']}: {str(e)}", extra={'session_id': session['sid']})
                    flash(trans("budget_delete_failed", default='Error deleting budget.'), "danger")
        budgets = list(db.budgets.find(filter_criteria).sort('created_at', -1))
        current_app.logger.info(f"Read {len(budgets)} records from MongoDB budgets collection [session: {session['sid']}]", extra={'session_id': session['sid']})
        budgets_dict = {}
        latest_budget = None
        for budget in budgets:
            budget_data = {
                'id': str(budget['_id']),
                'user_id': budget.get('user_id'),
                'session_id': budget.get('session_id'),
                'user_email': budget.get('user_email', ''),
                'income': format_currency(float(budget.get('income', 0.0))),
                'income_raw': float(budget.get('income', 0.0)),
                'fixed_expenses': format_currency(float(budget.get('fixed_expenses', 0.0))),
                'fixed_expenses_raw': float(budget.get('fixed_expenses', 0.0)),
                'variable_expenses': format_currency(float(budget.get('variable_expenses', 0.0))),
                'variable_expenses_raw': float(budget.get('variable_expenses', 0.0)),
                'savings_goal': format_currency(float(budget.get('savings_goal', 0.0))),
                'savings_goal_raw': float(budget.get('savings_goal', 0.0)),
                'surplus_deficit': float(budget.get('surplus_deficit', 0.0)),
                'surplus_deficit_formatted': format_currency(float(budget.get('surplus_deficit', 0.0))),
                'housing': format_currency(float(budget.get('housing', 0.0))),
                'housing_raw': float(budget.get('housing', 0.0)),
                'food': format_currency(float(budget.get('food', 0.0))),
                'food_raw': float(budget.get('food', 0.0)),
                'transport': format_currency(float(budget.get('transport', 0.0))),
                'transport_raw': float(budget.get('transport', 0.0)),
                'dependents': format_currency(float(budget.get('dependents', 0.0))),
                'dependents_raw': float(budget.get('dependents', 0.0)),
                'miscellaneous': format_currency(float(budget.get('miscellaneous', 0.0))),
                'miscellaneous_raw': float(budget.get('miscellaneous', 0.0)),
                'others': format_currency(float(budget.get('others', 0.0))),
                'others_raw': float(budget.get('others', 0.0)),
                'created_at': budget.get('created_at').strftime('%Y-%m-%d') if budget.get('created_at') else 'N/A'
            }
            budgets_dict[budget_data['id']] = budget_data
            if not latest_budget or (budget.get('created_at') and (latest_budget['created_at'] == 'N/A' or budget.get('created_at') > datetime.strptime(latest_budget['created_at'], '%Y-%m-%d'))):
                latest_budget = budget_data
        if not latest_budget:
            latest_budget = {
                'id': None,
                'user_id': None,
                'session_id': session.get('sid', 'unknown'),
                'user_email': '',
                'income': format_currency(0.0),
                'income_raw': 0.0,
                'fixed_expenses': format_currency(0.0),
                'fixed_expenses_raw': 0.0,
                'variable_expenses': format_currency(0.0),
                'variable_expenses_raw': 0.0,
                'savings_goal': format_currency(0.0),
                'savings_goal_raw': 0.0,
                'surplus_deficit': 0.0,
                'surplus_deficit_formatted': format_currency(0.0),
                'housing': format_currency(0.0),
                'housing_raw': 0.0,
                'food': format_currency(0.0),
                'food_raw': 0.0,
                'transport': format_currency(0.0),
                'transport_raw': 0.0,
                'dependents': format_currency(0.0),
                'dependents_raw': 0.0,
                'miscellaneous': format_currency(0.0),
                'miscellaneous_raw': 0.0,
                'others': format_currency(0.0),
                'others_raw': 0.0,
                'created_at': 'N/A'
            }
        categories = {
            trans('budget_housing_rent', default='Housing/Rent'): latest_budget.get('housing_raw', 0.0),
            trans('budget_food', default='Food'): latest_budget.get('food_raw', 0.0),
            trans('budget_transport', default='Transport'): latest_budget.get('transport_raw', 0.0),
            trans('budget_dependents_support', default='Dependents Support'): latest_budget.get('dependents_raw', 0.0),
            trans('budget_miscellaneous', default='Miscellaneous'): latest_budget.get('miscellaneous_raw', 0.0),
            trans('budget_others', default='Others'): latest_budget.get('others_raw', 0.0)
        }
        # Filter out zero-value categories to avoid empty chart
        categories = {k: v for k, v in categories.items() if v > 0}
        tips = [
            trans("budget_tip_track_expenses", default='Track your expenses daily to stay within budget.'),
            trans("budget_tip_ajo_savings", default='Contribute to ajo savings for financial discipline.'),
            trans("budget_tip_data_subscriptions", default='Optimize data subscriptions to reduce costs.'),
            trans("budget_tip_plan_dependents", default='Plan for dependents’ expenses in advance.')
        ]
        insights = []
        try:
            income_float = float(latest_budget.get('income_raw', 0.0))
            surplus_deficit_float = float(latest_budget.get('surplus_deficit', 0.0))
            savings_goal_float = float(latest_budget.get('savings_goal_raw', 0.0))
            if income_float > 0:
                if surplus_deficit_float < 0:
                    insights.append(trans("budget_insight_budget_deficit", default='Your expenses exceed your income. Consider reducing costs.'))
                elif surplus_deficit_float > 0:
                    insights.append(trans("budget_insight_budget_surplus", default='You have a surplus. Consider increasing savings.'))
                if savings_goal_float == 0:
                    insights.append(trans("budget_insight_set_savings_goal", default='Set a savings goal to build financial security.'))
        except (ValueError, TypeError) as e:
            current_app.logger.warning(f"Error parsing budget amounts for insights: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
        current_app.logger.debug(f"Latest budget: {latest_budget}", extra={'session_id': session.get('sid', 'unknown')})
        current_app.logger.debug(f"Categories: {categories}", extra={'session_id': session.get('sid', 'unknown')})
        return render_template(
            'personal/BUDGET/budget_main.html',
            form=form,
            budgets=budgets_dict,
            latest_budget=latest_budget,
            categories=categories,
            tips=tips,
            insights=insights,
            activities=activities,
            tool_title=trans('budget_title', default='Budget Planner'),
            active_tab=active_tab
        )
    except Exception as e:
        current_app.logger.error(f"Unexpected error in personal/BUDGET/budget_main ethnic_tab: {active_tab}", extra={'session_id': session.get('sid', 'unknown')})
        flash(trans Tina/trans('budget_dashboard_load_error', default='Error loading budget dashboard.'), "danger")
        return render_template(
            'personal/BUDGET/budget_main.html',
            form=form,
            budgets={},
            latest_budget={
                'id': None,
                'user_id': None,
                'session_id': session.get('sid', 'unknown'),
                'user_email': '',
                'income': format_currency(0.0),
                'income_raw': 0.0,
                'fixed_expenses': format_currency(0.0),
                'fixed_expenses_raw': 0.0,
                'variable_expenses': format_currency(0.0),
                'variable_expenses_raw': 0.0,
                'savings_goal': format_currency(0.0),
                'savings_goal_raw': 0.0,
                'surplus_deficit': 0.0,
                'surplus_deficit_formatted': format_currency(0.0),
                'housing': format_currency(0.0),
                'housing_raw': 0.0,
                'food': format_currency(0.0),
                'food_raw': 0.0,
                'transport': format_currency(0.0),
                'transport_raw': 0.0,
                'dependents': format_currency(0.0),
                'dependents_raw': 0.0,
                'miscellaneous': format_currency(0.0),
                'miscellaneous_raw': 0.0,
                'others': format_currency(0.0),
                'others_raw': 0.0,
                'created_at': 'N/A'
            },
            categories={},
            tips=[],
            insights=[],
            activities=activities,
            tool_title=trans('budget_title', default='Budget Planner'),
            active_tab=active_tab
        ), 500

@budget_bp.route('/summary')
@login_required
@requires_role(['personal', 'admin'])
def summary():
    """Return summary of the latest budget for the current user."""
    db = get_mongo_db()
    try:
        log_tool_usage(
            tool_name='budget',
            db=db,
            user_id=current_user.id if current_user.is_authenticated else None,
            session_id=session.get('sid', 'unknown'),
            action='summary_view'
        )
        filter_criteria = {} if is_admin() else {'user_id': current_user.id}
        budgets_collection = db.budgets
        latest_budget = budgets_collection.find(filter_criteria).sort('created_at', -1).limit(1)
        latest_budget = list(latest_budget)
        if not latest_budget:
            current_app.logger.info(f"No budget found for user {current_user.id}", extra={'session_id': session.get('sid', 'unknown')})
            return jsonify({'totalBudget': format_currency(0.0)})
        total_budget = float(latest_budget[0].get('income', 0.0))
        current_app.logger.info(f"Fetched budget summary for user {current_user.id}: {total_budget}", extra={'session_id': session.get('sid', 'unknown')})
        return jsonify({'totalBudget': format_currency(total_budget)})
    except Exception as e:
        current_app.logger.error(f"Error in budget.summary: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
        return jsonify({'totalBudget': format_currency(0.0)}), 500

@budget_bp.errorhandler(CSRFError)
def handle_csrf_error(e):
    """Handle CSRF errors with user-friendly message."""
    current_app.logger.error(f"CSRF error on {request.path}: {e.description}", extra={'session_id': session.get('sid', 'unknown')})
    flash(trans('budget_csrf_error', default='Form submission failed due to a missing security token. Please refresh and try again.'), 'danger')
    return redirect(url_for('personal.index')), 400
