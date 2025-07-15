from flask import Blueprint, request, session, redirect, url_for, render_template, flash, current_app, jsonify
from flask_wtf import FlaskForm
from flask_wtf.csrf import CSRFProtect, CSRFError
from wtforms import FloatField, IntegerField, SelectField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Optional, NumberRange, ValidationError
from flask_login import current_user, login_required
from mailersend_email import send_email, EMAIL_CONFIG
from datetime import datetime
from bson import ObjectId
from translations import trans
from utils import get_all_recent_activities, requires_role, is_admin, get_mongo_db, limiter, log_tool_usage
from session_utils import create_anonymous_session
import re

emergency_fund_bp = Blueprint(
    'emergency_fund',
    __name__,
    template_folder='templates/personal/EMERGENCYFUND',
    url_prefix='/emergency_fund'
)

csrf = CSRFProtect()

def custom_login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.is_authenticated or session.get('is_anonymous', False):
            return f(*args, **kwargs)
        return redirect(url_for('users.login', next=request.url))
    return decorated_function

def clean_currency(value):
    """Transform input into a float, returning None for invalid cases."""
    if not value or value == '0':
        return 0.0
    if isinstance(value, str):
        value = re.sub(r'[^\d.]', '', value.strip())
        parts = value.split('.')
        if len(parts) > 2:
            value = parts[0] + '.' + ''.join(parts[1:])
        if not value or value == '.':
            return 0.0
        try:
            float_value = float(value)
            if float_value > 1e308:
                return None  # Exceeds float limit
            return float_value
        except ValueError:
            return None
    return float(value) if value else 0.0

def strip_commas(value):
    """Filter to remove commas and return a float."""
    return clean_currency(value)

def format_currency(value):
    """Format a numeric value with comma separation, no currency symbol."""
    try:
        numeric_value = float(value)
        formatted = f"{numeric_value:,.2f}"
        return formatted
    except (ValueError, TypeError):
        return "0.00"

class CommaSeparatedIntegerField(IntegerField):
    def process_formdata(self, valuelist):
        if valuelist:
            try:
                cleaned_value = clean_currency(valuelist[0])
                self.data = int(cleaned_value) if cleaned_value is not None else None
            except (ValueError, TypeError):
                self.data = None
                raise ValidationError(trans('emergency_fund_dependents_invalid', default='Not a valid integer'))

class EmergencyFundForm(FlaskForm):
    email_opt_in = BooleanField(
        trans('emergency_fund_send_email', default='Send me my plan by email'),
        default=False
    )
    monthly_expenses = FloatField(
        trans('emergency_fund_monthly_expenses', default='Monthly Expenses'),
        filters=[strip_commas],
        validators=[
            DataRequired(message=trans('emergency_fund_monthly_expenses_required', default='Monthly expenses are required')),
            NumberRange(min=0, max=10000000000, message=trans('emergency_fund_monthly_exceed', default='Amount must be between 0 and 10 billion'))
        ]
    )
    monthly_income = FloatField(
        trans('emergency_fund_monthly_income', default='Monthly Income'),
        filters=[strip_commas],
        validators=[
            Optional(),
            NumberRange(min=0, max=10000000000, message=trans('emergency_fund_monthly_exceed', default='Amount must be between 0 and 10 billion'))
        ]
    )
    current_savings = FloatField(
        trans('emergency_fund_current_savings', default='Current Savings'),
        filters=[strip_commas],
        validators=[
            Optional(),
            NumberRange(min=0, max=10000000000, message=trans('emergency_fund_savings_max', default='Amount must be between 0 and 10 billion'))
        ]
    )
    risk_tolerance_level = SelectField(
        trans('emergency_fund_risk_tolerance_level', default='Risk Tolerance Level'),
        validators=[DataRequired(message=trans('emergency_fund_risk_tolerance_required', default='Risk level is required'))],
        choices=[
            ('low', trans('emergency_fund_risk_tolerance_level_low', default='Low')),
            ('medium', trans('emergency_fund_risk_tolerance_level_medium', default='Medium')),
            ('high', trans('emergency_fund_risk_tolerance_level_high', default='High'))
        ]
    )
    dependents = CommaSeparatedIntegerField(
        trans('emergency_fund_dependents', default='Number of Dependents'),
        validators=[
            Optional(),
            NumberRange(min=0, max=100, message=trans('emergency_fund_dependents_max', default='Number of dependents cannot exceed 100'))
        ]
    )
    timeline = SelectField(
        trans('emergency_fund_timeline', default='Savings Timeline'),
        validators=[DataRequired(message=trans('emergency_fund_timeline_required', default='Timeline is required'))],
        choices=[
            ('6', trans('emergency_fund_6_months', default='6 Months')),
            ('12', trans('emergency_fund_12_months', default='12 Months')),
            ('18', trans('emergency_fund_18_months', default='18 Months'))
        ]
    )
    submit = SubmitField(trans('emergency_fund_calculate_button', default='Calculate Emergency Fund'))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        lang = session.get('lang', 'en')
        self.email_opt_in.label.text = trans('emergency_fund_send_email', lang) or 'Send me my plan by email'
        self.monthly_expenses.label.text = trans('emergency_fund_monthly_expenses', lang) or 'Monthly Expenses'
        self.monthly_income.label.text = trans('emergency_fund_monthly_income', lang) or 'Monthly Income'
        self.current_savings.label.text = trans('emergency_fund_current_savings', lang) or 'Current Savings'
        self.risk_tolerance_level.label.text = trans('emergency_fund_risk_tolerance_level', lang) or 'Risk Tolerance Level'
        self.dependents.label.text = trans('emergency_fund_dependents', lang) or 'Number of Dependents'
        self.timeline.label.text = trans('emergency_fund_timeline', lang) or 'Savings Timeline'
        self.submit.label.text = trans('emergency_fund_calculate_button', lang) or 'Calculate Emergency Fund'

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators):
            return False
        if self.email_opt_in.data and not current_user.is_authenticated:
            self.email_opt_in.errors.append(trans('emergency_fund_email_required', session.get('lang', 'en')) or 'Email notifications require an authenticated user')
            return False
        return True

@emergency_fund_bp.route('/main', methods=['GET', 'POST'])
@custom_login_required
@requires_role(['personal', 'admin'])
@limiter.limit("10 per minute")
def main():
    if 'sid' not in session:
        create_anonymous_session()
        session['is_anonymous'] = True
        current_app.logger.debug(f"New anonymous session created with sid: {session['sid']}", extra={'session_id': session['sid']})
    session.permanent = True
    session.modified = True
    form = EmergencyFundForm()
    db = get_mongo_db()
    valid_tabs = ['create-plan', 'dashboard']
    active_tab = request.args.get('tab', 'create-plan')
    if active_tab not in valid_tabs:
        active_tab = 'create-plan'

    try:
        log_tool_usage(
            tool_name='emergency_fund',
            db=db,
            user_id=current_user.id if current_user.is_authenticated else None,
            session_id=session.get('sid', 'unknown'),
            action='main_view'
        )
    except Exception as e:
        current_app.logger.error(f"Failed to log tool usage: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
        flash(trans('emergency_fund_log_error', default='Error logging emergency fund activity. Please try again.'), 'warning')

    try:
        activities = get_all_recent_activities(
            db=db,
            user_id=current_user.id if current_user.is_authenticated else None,
            session_id=session.get('sid', 'unknown') if not current_user.is_authenticated else None,
            limit=10
        )
        current_app.logger.debug(f"Fetched {len(activities)} recent activities for {'user ' + str(current_user.id) if current_user.is_authenticated else 'session ' + session.get('sid', 'unknown')}", extra={'session_id': session.get('sid', 'unknown')})
    except Exception as e:
        current_app.logger.error(f"Failed to fetch recent activities: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
        flash(trans('emergency_fund_activities_load_error', default='Error loading recent activities.'), 'warning')
        activities = []

    try:
        filter_kwargs = {} if is_admin() else {'user_id': current_user.id} if current_user.is_authenticated else {'session_id': session['sid']}
        if request.method == 'POST':
            action = request.form.get('action')
            if action == 'create_plan' and form.validate_on_submit():
                try:
                    log_tool_usage(
                        tool_name='emergency_fund',
                        db=db,
                        user_id=current_user.id if current_user.is_authenticated else None,
                        session_id=session.get('sid', 'unknown'),
                        action='create_plan'
                    )
                except Exception as e:
                    current_app.logger.error(f"Failed to log Sfemergency fund plan creation: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
                    flash(trans('emergency_fund_log_error', default='Error logging emergency fund plan creation. Continuing with submission.'), 'warning')

                months = int(form.timeline.data)
                base_target = form.monthly_expenses.data * months
                recommended_months = months
                if form.risk_tolerance_level.data == 'high':
                    recommended_months = max(12, months)
                elif form.risk_tolerance_level.data == 'low':
                    recommended_months = min(6, months)
                if form.dependents.data and form.dependents.data >= 2:
                    recommended_months += 2
                target_amount = form.monthly_expenses.data * recommended_months
                gap = target_amount - (form.current_savings.data or 0)
                monthly_savings = gap / months if gap > 0 else 0
                percent_of_income = None
                if form.monthly_income.data and form.monthly_income.data > 0:
                    percent_of_income = (monthly_savings / form.monthly_income.data) * 100

                badges = []
                if form.timeline.data in ['6', '12']:
                    badges.append(trans('emergency_fund_badge_planner', default='Planner'))
                if form.dependents.data and form.dependents.data >= 2:
                    badges.append(trans('emergency_fund_badge_protector', default='Protector'))
                if gap <= 0:
                    badges.append(trans('emergency_fund_badge_steady_saver', default='Steady Saver'))
                if (form.current_savings.data or 0) >= target_amount:
                    badges.append(trans('emergency_fund_badge_fund_master', default='Fund Master'))

                emergency_fund = {
                    '_id': ObjectId(),
                    'user_id': current_user.id if current_user.is_authenticated else None,
                    'session_id': session['sid'],
                    'first_name': current_user.get_first_name() if current_user.is_authenticated else '',
                    'email': current_user.email if current_user.is_authenticated else '',
                    'email_opt_in': form.email_opt_in.data,
                    'lang': session.get('lang', 'en'),
                    'monthly_expenses': form.monthly_expenses.data,
                    'monthly_income': form.monthly_income.data,
                    'current_savings': form.current_savings.data or 0,
                    'risk_tolerance_level': form.risk_tolerance_level.data,
                    'dependents': form.dependents.data or 0,
                    'timeline': months,
                    'recommended_months': recommended_months,
                    'target_amount': target_amount,
                    'savings_gap': gap,
                    'monthly_savings': monthly_savings,
                    'percent_of_income': percent_of_income,
                    'badges': badges,
                    'created_at': datetime.utcnow()
                }

                try:
                    db.emergency_funds.insert_one(emergency_fund)
                    current_app.logger.info(f"Emergency fund record saved to MongoDB with ID {emergency_fund['_id']}", extra={'session_id': session.get('sid', 'unknown')})
                    flash(trans('emergency_fund_completed_successfully', default='Emergency fund calculation completed successfully!'), 'success')
                    if form.email_opt_in.data and current_user.is_authenticated and emergency_fund['email']:
                        try:
                            config = EMAIL_CONFIG["emergency_fund"]
                            subject = trans(config["subject_key"], default='Your Emergency Fund Plan')
                            template = config["template"]
                            created_at_str = emergency_fund['created_at'].strftime('%Y-%m-%d') if emergency_fund.get('created_at') else 'N/A'
                            send_email(
                                app=current_app,
                                logger=current_app.logger,
                                to_email=emergency_fund['email'],
                                subject=subject,
                                template_name=template,
                                data={
                                    'first_name': emergency_fund['first_name'],
                                    'lang': session.get('lang', 'en'),
                                    'monthly_expenses': format_currency(emergency_fund['monthly_expenses']),
                                    'monthly_income': format_currency(emergency_fund['monthly_income']) if emergency_fund['monthly_income'] else 'N/A',
                                    'current_savings': format_currency(emergency_fund['current_savings']),
                                    'risk_tolerance_level': emergency_fund['risk_tolerance_level'],
                                    'dependents': emergency_fund['dependents'],
                                    'timeline': emergency_fund['timeline'],
                                    'recommended_months': emergency_fund['recommended_months'],
                                    'target_amount': format_currency(emergency_fund['target_amount']),
                                    'savings_gap': format_currency(emergency_fund['savings_gap']),
                                    'monthly_savings': format_currency(emergency_fund['monthly_savings']),
                                    'percent_of_income': f"{emergency_fund['percent_of_income']:.2f}%" if emergency_fund['percent_of_income'] else 'N/A',
                                    'badges': emergency_fund['badges'],
                                    'created_at': created_at_str,
                                    'cta_url': url_for('personal.emergency_fund.main', _external=True),
                                    'unsubscribe_url': url_for('personal.emergency_fund.unsubscribe', _external=True)
                                },
                                lang=session.get('lang', 'en')
                            )
                            current_app.logger.info(f"Email sent to {emergency_fund['email']}", extra={'session_id': session.get('sid', 'unknown')})
                        except Exception as e:
                            current_app.logger.error(f"Failed to send email: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
                            flash(trans("general_email_send_failed", default='Failed to send email.'), "danger")
                    return redirect(url_for('personal.emergency_fund.main', tab='dashboard'))
                except Exception as e:
                    current_app.logger.error(f"Failed to save emergency fund record to MongoDB: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
                    flash(trans('emergency_fund_storage_error', default='Error saving emergency fund plan.'), 'danger')
                    return redirect(url_for('personal.emergency_fund.main', tab='create-plan'))

        user_data = db.emergency_funds.find(filter_kwargs).sort('created_at', -1)
        user_data = list(user_data)
        current_app.logger.info(f"Retrieved {len(user_data)} records from MongoDB for {'user ' + str(current_user.id) if current_user.is_authenticated else 'session ' + session.get('sid', 'unknown')}", extra={'session_id': session.get('sid', 'unknown')})

        records = []
        for record in user_data:
            created_at_str = record.get('created_at').strftime('%Y-%m-%d') if record.get('created_at') and isinstance(record.get('created_at'), datetime) else 'N/A'
            record_data = {
                'id': str(record['_id']),
                'user_id': record.get('user_id'),
                'session_id': record.get('session_id'),
                'first_name': record.get('first_name'),
                'email': record.get('email'),
                'email_opt_in': record.get('email_opt_in'),
                'lang': record.get('lang'),
                'monthly_expenses': format_currency(record.get('monthly_expenses', 0)),
                'monthly_expenses_raw': float(record.get('monthly_expenses', 0)),
                'monthly_income': format_currency(record.get('monthly_income', 0)) if record.get('monthly_income') else 'N/A',
                'monthly_income_raw': float(record.get('monthly_income', 0)) if record.get('monthly_income') else None,
                'current_savings': format_currency(record.get('current_savings', 0)),
                'current_savings_raw': float(record.get('current_savings', 0)),
                'risk_tolerance_level': record.get('risk_tolerance_level'),
                'dependents': record.get('dependents', 0),
                'timeline': record.get('timeline', 0),
                'recommended_months': record.get('recommended_months', 0),
                'target_amount': format_currency(record.get('target_amount', 0)),
                'target_amount_raw': float(record.get('target_amount', 0)),
                'savings_gap': format_currency(record.get('savings_gap', 0)),
                'savings_gap_raw': float(record.get('savings_gap', 0)),
                'monthly_savings': format_currency(record.get('monthly_savings', 0)),
                'monthly_savings_raw': float(record.get('monthly_savings', 0)),
                'percent_of_income': f"{record.get('percent_of_income'):.2f}%" if record.get('percent_of_income') else 'N/A',
                'badges': record.get('badges', []),
                'created_at': created_at_str
            }
            records.append((record_data['id'], record_data))

        latest_record = records[-1][1] if records else {
            'monthly_expenses': format_currency(0),
            'monthly_expenses_raw': 0.0,
            'monthly_income': 'N/A',
            'monthly_income_raw': None,
            'current_savings': format_currency(0),
            'current_savings_raw': 0.0,
            'risk_tolerance_level': '',
            'dependents': 0,
            'timeline': 0,
            'recommended_months': 0,
            'target_amount': format_currency(0),
            'target_amount_raw': 0.0,
            'savings_gap': format_currency(0),
            'savings_gap_raw': 0.0,
            'monthly_savings': format_currency(0),
            'monthly_savings_raw': 0.0,
            'percent_of_income': 'N/A',
            'badges': [],
            'created_at': 'N/A'
        }

        insights = []
        try:
            if latest_record and latest_record['target_amount_raw'] > 0:
                if latest_record['savings_gap_raw'] <= 0:
                    insights.append(trans('emergency_fund_insight_fully_funded', default='Your emergency fund is fully funded! Great job!'))
                else:
                    insights.append(trans('emergency_fund_insight_savings_gap', default='You need to save {savings_gap} over {months} months.', savings_gap=latest_record.get('savings_gap'), months=latest_record.get('timeline')))
                    if latest_record.get('percent_of_income') != 'N/A':
                        percent_float = float(latest_record['percent_of_income'].replace('%', '')) if latest_record['percent_of_income'] != 'N/A' else 0
                        if percent_float > 30:
                            insights.append(trans('emergency_fund_insight_high_income_percentage', default='Your monthly savings goal is over 30% of your income. Consider extending your timeline.'))
                    if latest_record.get('dependents', 0) > 2:
                        insights.append(trans('emergency_fund_insight_large_family', default='With {dependents} dependents, consider a {recommended_months}-month fund.', dependents=latest_record.get('dependents', 0), recommended_months=latest_record.get('recommended_months', 0)))
        except (ValueError, TypeError) as e:
            current_app.logger.warning(f"Error parsing amounts for insights: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})

        cross_tool_insights = []
        filter_kwargs_budget = {} if is_admin() else {'user_id': current_user.id} if current_user.is_authenticated else {'session_id': session['sid']}
        budget_data = db.budgets.find(filter_kwargs_budget).sort('created_at', -1)
        budget_data = list(budget_data)
        if budget_data and latest_record and latest_record['savings_gap_raw'] > 0:
            latest_budget = budget_data[0]
            if latest_budget.get('income') and latest_budget.get('fixed_expenses'):
                savings_possible = latest_budget['income'] - latest_budget['fixed_expenses']
                if savings_possible > 0:
                    cross_tool_insights.append(trans('emergency_fund_cross_tool_savings_possible', default='Your budget shows {amount} available for savings monthly.', amount=format_currency(savings_possible)))

        return render_template(
            'personal/EMERGENCYFUND/emergency_fund_main.html',
            form=form,
            records=records,
            latest_record=latest_record,
            insights=insights,
            cross_tool_insights=cross_tool_insights,
            tips=[
                trans('emergency_fund_tip_automate_savings', default='Automate your savings to build your fund consistently.'),
                trans('budget_tip_ajo_savings', default='Contribute to ajo savings for financial discipline.'),
                trans('emergency_fund_tip_track_expenses', default='Track expenses to find extra savings opportunities.'),
                trans('budget_tip_monthly_savings', default='Set a monthly savings goal to stay on track.')
            ],
            activities=activities,
            tool_title=trans('emergency_fund_title', default='Emergency Fund Calculator'),
            active_tab=active_tab
        )
    except Exception as e:
        current_app.logger.error(f"Error in emergency_fund.main for session {session.get('sid', 'unknown')}: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
        flash(trans('emergency_fund_load_dashboard_error', default='Error loading emergency fund dashboard.'), 'danger')
        return render_template(
            'personal/EMERGENCYFUND/emergency_fund_main.html',
            form=form,
            records=[],
            latest_record={
                'monthly_expenses': format_currency(0),
                'monthly_expenses_raw': 0.0,
                'monthly_income': 'N/A',
                'monthly_income_raw': None,
                'current_savings': format_currency(0),
                'current_savings_raw': 0.0,
                'risk_tolerance_level': '',
                'dependents': 0,
                'timeline': 0,
                'recommended_months': 0,
                'target_amount': format_currency(0),
                'target_amount_raw': 0.0,
                'savings_gap': format_currency(0),
                'savings_gap_raw': 0.0,
                'monthly_savings': format_currency(0),
                'monthly_savings_raw': 0.0,
                'percent_of_income': 'N/A',
                'badges': [],
                'created_at': 'N/A'
            },
            insights=[],
            cross_tool_insights=[],
            tips=[],
            activities=activities,
            tool_title=trans('emergency_fund_title', default='Emergency Fund Calculator'),
            active_tab=active_tab
        ), 500

@emergency_fund_bp.route('/summary')
@login_required
@requires_role(['personal', 'admin'])
@limiter.limit("5 per minute")
def summary():
    db = get_mongo_db()
    try:
        log_tool_usage(
            tool_name='emergency_fund',
            db=db,
            user_id=current_user.id if current_user.is_authenticated else None,
            session_id=session.get('sid', 'unknown'),
            action='summary_view'
        )
        filter_criteria = {} if is_admin() else {'user_id': current_user.id}
        collection = db.emergency_funds
        latest_record = collection.find(filter_criteria).sort('created_at', -1).limit(1)
        latest_record = list(latest_record)
        if not latest_record:
            current_app.logger.info(f"No emergency fund record found for user {current_user.id}", extra={'session_id': session.get('sid', 'unknown')})
            return jsonify({'targetAmount': format_currency(0.0), 'savingsGap': format_currency(0.0)})
        target_amount = float(latest_record[0].get('target_amount', 0.0))
        savings_gap = float(latest_record[0].get('savings_gap', 0.0))
        current_app.logger.info(f"Fetched emergency fund summary for user {current_user.id}: target_amount={target_amount}, savings_gap={savings_gap}", extra={'session_id': session.get('sid', 'unknown')})
        return jsonify({'targetAmount': format_currency(target_amount), 'savingsGap': format_currency(savings_gap)})
    except Exception as e:
        current_app.logger.error(f"Error in emergency_fund.summary: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
        return jsonify({'targetAmount': format_currency(0.0), 'savingsGap': format_currency(0.0)}), 500

@emergency_fund_bp.route('/unsubscribe', methods=['GET', 'POST'])
@custom_login_required
@requires_role(['personal', 'admin'])
@limiter.limit("5 per minute")
def unsubscribe():
    db = get_mongo_db()
    if 'sid' not in session:
        create_anonymous_session()
        session['is_anonymous'] = True
        current_app.logger.debug(f"New anonymous session created with sid: {session['sid']}", extra={'session_id': session['sid']})
    session.permanent = True
    session.modified = True
    try:
        log_tool_usage(
            tool_name='emergency_fund',
            db=db,
            user_id=current_user.id if current_user.is_authenticated else None,
            session_id=session.get('sid', 'unknown'),
            action='unsubscribe'
        )
        filter_kwargs = {'email': current_user.email if current_user.is_authenticated else ''}
        if current_user.is_authenticated and not is_admin():
            filter_kwargs['user_id'] = current_user.id
        result = db.emergency_funds.update_many(
            filter_kwargs,
            {'$set': {'email_opt_in': False}}
        )
        if result.modified_count > 0:
            current_app.logger.info(f"Unsubscribed email {current_user.email if current_user.is_authenticated else 'anonymous'} for session {session.get('sid', 'unknown')}", extra={'session_id': session.get('sid', 'unknown')})
            flash(trans("emergency_fund_unsubscribed_success", default='Successfully unsubscribed from email notifications.'), "success")
        else:
            current_app.logger.warning(f"No records found to unsubscribe email {current_user.email if current_user.is_authenticated else 'anonymous'} for session {session.get('sid', 'unknown')}", extra={'session_id': session.get('sid', 'unknown')})
            flash(trans("emergency_fund_unsubscribe_error", default='No email notifications found for this user.'), "danger")
        return redirect(url_for('personal.emergency_fund.main', tab='dashboard'))
    except Exception as e:
        current_app.logger.error(f"Error in emergency_fund.unsubscribe for session {session.get('sid', 'unknown')}: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
        flash(trans("emergency_fund_unsubscribe_error", default='Error unsubscribing from email notifications.'), "danger")
        return redirect(url_for('personal.emergency_fund.main', tab='dashboard'))

@emergency_fund_bp.errorhandler(CSRFError)
def handle_csrf_error(e):
    current_app.logger.error(f"CSRF error on {request.path}: {e.description}", extra={'session_id': session.get('sid', 'unknown')})
    flash(trans('emergency_fund_csrf_error', default='Form submission failed due to a missing security token. Please refresh and try again.'), 'danger')
    return redirect(url_for('personal.emergency_fund.main', tab='create-plan')), 403
