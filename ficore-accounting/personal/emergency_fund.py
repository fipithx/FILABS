from flask import Blueprint, request, session, redirect, url_for, render_template, flash, current_app, jsonify
from flask_wtf import FlaskForm
from flask_wtf.csrf import CSRFProtect, CSRFError
from wtforms import StringField, FloatField, IntegerField, SelectField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Optional, Email, NumberRange, ValidationError
from flask_login import current_user, login_required
from mailersend_email import send_email, EMAIL_CONFIG
from datetime import datetime
from bson import ObjectId
from translations import trans
from models import log_tool_usage
from session_utils import create_anonymous_session
from utils import requires_role, is_admin, get_mongo_db, format_currency, limiter

emergency_fund_bp = Blueprint(
    'emergency_fund',
    __name__,
    template_folder='templates/EMERGENCYFUND',
    url_prefix='/emergency_fund'
)

csrf = CSRFProtect()

def custom_login_required(f):
    """Custom login decorator that allows both authenticated users and anonymous sessions."""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.is_authenticated or session.get('is_anonymous', False):
            return f(*args, **kwargs)
        return redirect(url_for('users.login', next=request.url))
    return decorated_function

class CommaSeparatedFloatField(FloatField):
    def process_formdata(self, valuelist):
        if valuelist:
            try:
                self.data = float(valuelist[0].replace(',', ''))
            except ValueError:
                self.data = None
                raise ValidationError(self.gettext('Not a valid number'))

class CommaSeparatedIntegerField(IntegerField):
    def process_formdata(self, valuelist):
        if valuelist:
            try:
                self.data = int(valuelist[0].replace(',', ''))
            except ValueError:
                self.data = None
                raise ValidationError(self.gettext('Not a valid integer'))

class EmergencyFundForm(FlaskForm):
    first_name = StringField(
        trans('general_first_name', default='First Name'),
        validators=[DataRequired(message=trans('general_first_name_required', default='Please enter your first name.'))]
    )
    email = StringField(
        trans('general_email', default='Email'),
        validators=[Optional(), Email(message=trans('general_email_invalid', default='Please enter a valid email address.'))]
    )
    email_opt_in = BooleanField(
        trans('general_send_email', default='Send Email'),
        default=False
    )
    monthly_expenses = CommaSeparatedFloatField(
        trans('emergency_fund_monthly_expenses', default='Monthly Expenses'),
        validators=[
            DataRequired(message=trans('emergency_fund_monthly_expenses_required', default='Please enter your monthly expenses.')),
            NumberRange(min=0, max=10000000000, message=trans('emergency_fund_monthly_exceed', default='Amount exceeds maximum limit.'))
        ]
    )
    monthly_income = CommaSeparatedFloatField(
        trans('emergency_fund_monthly_income', default='Monthly Income'),
        validators=[
            Optional(),
            NumberRange(min=0, max=10000000000, message=trans('emergency_fund_monthly_exceed', default='Amount exceeds maximum limit.'))
        ]
    )
    current_savings = CommaSeparatedFloatField(
        trans('emergency_fund_current_savings', default='Current Savings'),
        validators=[
            Optional(),
            NumberRange(min=0, max=10000000000, message=trans('emergency_fund_savings_max', default='Amount exceeds maximum limit.'))
        ]
    )
    risk_tolerance_level = SelectField(
        trans('emergency_fund_risk_tolerance_level', default='Risk Tolerance Level'),
        validators=[DataRequired(message=trans('emergency_fund_risk_tolerance_required', default='Please select your risk tolerance.'))],
        choices=[
            ('low', trans('emergency_fund_risk_tolerance_level_low', default='Low')),
            ('medium', trans('emergency_fund_risk_tolerance_level_medium', default='Medium')),
            ('high', trans('emergency_fund_risk_tolerance_level_high', default='High'))
        ]
    )
    dependents = CommaSeparatedIntegerField(
        trans('emergency_fund_dependents', default='Dependents'),
        validators=[
            Optional(),
            NumberRange(min=0, max=100, message=trans('emergency_fund_dependents_max', default='Number of dependents exceeds maximum.'))
        ]
    )
    timeline = SelectField(
        trans('emergency_fund_timeline', default='Timeline'),
        validators=[DataRequired(message=trans('emergency_fund_timeline_required', default='Please select a timeline.'))],
        choices=[
            ('6', trans('emergency_fund_6_months', default='6 Months')),
            ('12', trans('emergency_fund_12_months', default='12 Months')),
            ('18', trans('emergency_fund_18_months', default='18 Months'))
        ]
    )
    submit = SubmitField(trans('emergency_fund_calculate_button', default='Calculate'))

    def validate_email(self, field):
        if self.email_opt_in.data and not field.data:
            current_app.logger.warning(f"Email required for notifications for session {session.get('sid', 'no-session-id')}", extra={'session_id': session.get('sid', 'no-session-id')})
            raise ValidationError(trans('emergency_fund_email_required', default='Valid email is required for notifications'))

@emergency_fund_bp.route('/main', methods=['GET', 'POST'])
@custom_login_required
@requires_role(['personal', 'admin'])
def main():
    """Main emergency fund interface with tabbed layout."""
    if 'sid' not in session:
        create_anonymous_session()
        current_app.logger.debug(f"New anonymous session created with sid: {session['sid']}", extra={'session_id': session['sid']})
    session.permanent = True
    session.modified = True
    form_data = {}
    if current_user.is_authenticated:
        form_data['email'] = current_user.email
        form_data['first_name'] = current_user.get_first_name()
    form = EmergencyFundForm(data=form_data)
    try:
        log_tool_usage(
            tool_name='emergency_fund',
            user_id=current_user.id if current_user.is_authenticated else None,
            session_id=session['sid'],
            action='main_view',
            mongo=get_mongo_db()
        )
    except Exception as e:
        current_app.logger.error(f"Failed to log tool usage: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
        flash(trans('emergency_fund_log_error', default='Error logging emergency fund activity. Please try again.'), 'warning')
    
    try:
        filter_kwargs = {} if is_admin() else {'user_id': current_user.id} if current_user.is_authenticated else {'session_id': session['sid']}
        if request.method == 'POST':
            action = request.form.get('action')
            if action == 'create_plan' and form.validate_on_submit():
                try:
                    log_tool_usage(
                        tool_name='emergency_fund',
                        user_id=current_user.id if current_user.is_authenticated else None,
                        session_id=session['sid'],
                        action='create_plan',
                        mongo=get_mongo_db()
                    )
                except Exception as e:
                    current_app.logger.error(f"Failed to log emergency fund plan creation: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
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
                    badges.append('Planner')
                if form.dependents.data and form.dependents.data >= 2:
                    badges.append('Protector')
                if gap <= 0:
                    badges.append('Steady Saver')
                if (form.current_savings.data or 0) >= target_amount:
                    badges.append('Fund Master')
                emergency_fund = {
                    '_id': ObjectId(),
                    'user_id': current_user.id if current_user.is_authenticated else None,
                    'session_id': session['sid'],
                    'first_name': form.first_name.data,
                    'email': form.email.data,
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
                    get_mongo_db().emergency_funds.insert_one(emergency_fund)
                    current_app.logger.info(f"Emergency fund record saved to MongoDB with ID {emergency_fund['_id']}", extra={'session_id': session['sid']})
                    flash(trans('emergency_fund_completed_successfully', default='Emergency fund calculation completed successfully!'), 'success')
                except Exception as e:
                    current_app.logger.error(f"Failed to save emergency fund record to MongoDB: {str(e)}", extra={'session_id': session['sid']})
                    flash(trans('emergency_fund_storage_error', default='Error saving emergency fund plan.'), 'danger')
                    return render_template(
                        'personal/EMERGENCYFUND/emergency_fund_main.html',
                        form=form,
                        records=[],
                        latest_record={},
                        insights=[],
                        cross_tool_insights=[],
                        tips=[],
                        tool_title=trans('emergency_fund_title', default='Emergency Fund Calculator')
                    )
                if form.email_opt_in.data and form.email.data:
                    try:
                        config = EMAIL_CONFIG["emergency_fund"]
                        subject = trans(config["subject_key"], default='Your Emergency Fund Plan')
                        template = config["template"]
                        send_email(
                            app=current_app,
                            logger=current_app.logger,
                            to_email=form.email.data,
                            subject=subject,
                            template_name=template,
                            data={
                                'first_name': form.first_name.data,
                                'lang': session.get('lang', 'en'),
                                'monthly_expenses': format_currency(form.monthly_expenses.data),
                                'monthly_income': format_currency(form.monthly_income.data) if form.monthly_income.data else 'N/A',
                                'current_savings': format_currency(form.current_savings.data or 0),
                                'risk_tolerance_level': form.risk_tolerance_level.data,
                                'dependents': form.dependents.data or 0,
                                'timeline': months,
                                'recommended_months': recommended_months,
                                'target_amount': format_currency(target_amount),
                                'savings_gap': format_currency(gap),
                                'monthly_savings': format_currency(monthly_savings),
                                'percent_of_income': f"{percent_of_income:.2f}%" if percent_of_income else 'N/A',
                                'badges': badges,
                                'created_at': emergency_fund['created_at'].strftime('%Y-%m-%d'),
                                'cta_url': url_for('emergency_fund.main', _external=True),
                                'unsubscribe_url': url_for('emergency_fund.unsubscribe', email=form.email.data, _external=True)
                            },
                            lang=session.get('lang', 'en')
                        )
                        current_app.logger.info(f"Email sent to {form.email.data}", extra={'session_id': session['sid']})
                    except Exception as e:
                        current_app.logger.error(f"Failed to send email: {str(e)}", extra={'session_id': session['sid']})
                        flash(trans("general_email_send_failed", default='Failed to send email.'), "danger")
        user_data = get_mongo_db().emergency_funds.find(filter_kwargs).sort('created_at', -1)
        user_data = list(user_data)
        current_app.logger.info(f"Retrieved {len(user_data)} records from MongoDB for user {current_user.id if current_user.is_authenticated else 'anonymous'}", extra={'session_id': session['sid']})
        if not user_data and current_user.is_authenticated and current_user.email:
            user_data = get_mongo_db().emergency_funds.find({'email': current_user.email}).sort('created_at', -1)
            user_data = list(user_data)
            current_app.logger.info(f"Retrieved {len(user_data)} records for email {current_user.email}", extra={'session_id': session['sid']})
        records = []
        for record in user_data:
            record_data = {
                'id': str(record['_id']),
                'user_id': record.get('user_id'),
                'session_id': record.get('session_id'),
                'first_name': record.get('first_name'),
                'email': record.get('email'),
                'email_opt_in': record.get('email_opt_in'),
                'lang': record.get('lang'),
                'monthly_expenses': format_currency(record.get('monthly_expenses', 0)),
                'monthly_income': format_currency(record.get('monthly_income', 0)) if record.get('monthly_income') else 'N/A',
                'current_savings': format_currency(record.get('current_savings', 0)),
                'risk_tolerance_level': record.get('risk_tolerance_level'),
                'dependents': record.get('dependents', 0),
                'timeline': record.get('timeline', 0),
                'recommended_months': record.get('recommended_months', 0),
                'target_amount': format_currency(record.get('target_amount', 0)),
                'savings_gap': format_currency(record.get('savings_gap', 0)),
                'monthly_savings': format_currency(record.get('monthly_savings', 0)),
                'percent_of_income': f"{record.get('percent_of_income'):.2f}%" if record.get('percent_of_income') else 'N/A',
                'badges': record.get('badges', []),
                'created_at': record.get('created_at').strftime('%Y-%m-%d') if record.get('created_at') else 'N/A'
            }
            records.append((record_data['id'], record_data))
        latest_record = records[-1][1] if records else {
            'monthly_expenses': format_currency(0),
            'monthly_income': 'N/A',
            'current_savings': format_currency(0),
            'risk_tolerance_level': '',
            'dependents': 0,
            'timeline': 0,
            'recommended_months': 0,
            'target_amount': format_currency(0),
            'savings_gap': format_currency(0),
            'monthly_savings': format_currency(0),
            'percent_of_income': 'N/A',
            'badges': [],
            'created_at': 'N/A'
        }
        insights = []
        if latest_record and float(latest_record['target_amount'].replace(',', '')) > 0:
            if float(latest_record['savings_gap'].replace(',', '')) <= 0:
                insights.append(trans('emergency_fund_insight_fully_funded', default='Your emergency fund is fully funded! Great job!'))
            else:
                insights.append(trans('emergency_fund_insight_savings_gap', default='You need to save {savings_gap} over {months} months.', savings_gap=latest_record.get('savings_gap'), months=latest_record.get('timeline')))
                if latest_record.get('percent_of_income') != 'N/A' and float(latest_record['percent_of_income'].replace('%', '')) > 30:
                    insights.append(trans('emergency_fund_insight_high_income_percentage', default='Your monthly savings goal is over 30% of your income. Consider extending your timeline.'))
                if latest_record.get('dependents', 0) > 2:
                    insights.append(trans('emergency_fund_insight_large_family', default='With {dependents} dependents, consider a {recommended_months}-month fund.', dependents=latest_record.get('dependents', 0), recommended_months=latest_record.get('recommended_months', 0)))
        cross_tool_insights = []
        filter_kwargs_budget = {} if is_admin() else {'user_id': current_user.id} if current_user.is_authenticated else {'session_id': session['sid']}
        budget_data = get_mongo_db().budgets.find(filter_kwargs_budget).sort('created_at', -1)
        budget_data = list(budget_data)
        if budget_data and latest_record and float(latest_record['savings_gap'].replace(',', '')) > 0:
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
            tool_title=trans('emergency_fund_title', default='Emergency Fund Calculator')
        )
    except Exception as e:
        current_app.logger.error(f"Error in emergency_fund.main for session {session.get('sid', 'unknown')}: {str(e)}", extra={'session_id': session['sid']})
        flash(trans('emergency_fund_load_dashboard_error', default='Error loading emergency fund dashboard.'), 'danger')
        return render_template(
            'personal/EMERGENCYFUND/emergency_fund_main.html',
            form=form,
            records=[],
            latest_record={
                'monthly_expenses': format_currency(0),
                'monthly_income': 'N/A',
                'current_savings': format_currency(0),
                'risk_tolerance_level': '',
                'dependents': 0,
                'timeline': 0,
                'recommended_months': 0,
                'target_amount': format_currency(0),
                'savings_gap': format_currency(0),
                'monthly_savings': format_currency(0),
                'percent_of_income': 'N/A',
                'badges': [],
                'created_at': 'N/A'
            },
            insights=[],
            cross_tool_insights=[],
            tips=[],
            tool_title=trans('emergency_fund_title', default='Emergency Fund Calculator')
        ), 500

@emergency_fund_bp.route('/summary')
@login_required
@requires_role(['personal', 'admin'])
def summary():
    """Return the latest emergency fund target amount or savings gap for the current user."""
    try:
        filter_criteria = {} if is_admin() else {'user_id': current_user.id}
        collection = get_mongo_db().emergency_funds
        latest_record = collection.find(filter_criteria).sort('created_at', -1).limit(1)
        latest_record = list(latest_record)
        if not latest_record:
            current_app.logger.info(f"No emergency fund record found for user {current_user.id}", extra={'session_id': session.get('sid', 'unknown')})
            return jsonify({'targetAmount': 0.0, 'savingsGap': 0.0})
        target_amount = latest_record[0].get('target_amount', 0.0)
        savings_gap = latest_record[0].get('savings_gap', 0.0)
        current_app.logger.info(f"Fetched emergency fund summary for user {current_user.id}: target_amount={target_amount}, savings_gap={savings_gap}", extra={'session_id': session.get('sid', 'unknown')})
        return jsonify({'targetAmount': target_amount, 'savingsGap': savings_gap})
    except Exception as e:
        current_app.logger.error(f"Error in emergency_fund.summary: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
        return jsonify({'targetAmount': 0.0, 'savingsGap': 0.0}), 500

@emergency_fund_bp.route('/unsubscribe/<email>')
@custom_login_required
@requires_role(['personal', 'admin'])
def unsubscribe(email):
    """Unsubscribe user from emergency fund emails."""
    if 'sid' not in session:
        create_anonymous_session()
        current_app.logger.debug(f"New anonymous session created with sid: {session['sid']}", extra={'session_id': session['sid']})
    session.permanent = True
    session.modified = True
    try:
        try:
            log_tool_usage(
                tool_name='emergency_fund',
                user_id=current_user.id if current_user.is_authenticated else None,
                session_id=session['sid'],
                action='unsubscribe',
                mongo=get_mongo_db()
            )
        except Exception as e:
            current_app.logger.error(f"Failed to log unsubscribe action: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
            flash(trans('emergency_fund_log_error', default='Error logging unsubscribe action. Continuing with unsubscription.'), 'warning')
        
        filter_kwargs = {'email': email}
        if current_user.is_authenticated and not is_admin():
            filter_kwargs['user_id'] = current_user.id
        result = get_mongo_db().emergency_funds.update_many(
            filter_kwargs,
            {'$set': {'email_opt_in': False}}
        )
        if result.modified_count > 0:
            current_app.logger.info(f"Unsubscribed email {email} for session {session['sid']}", extra={'session_id': session['sid']})
            flash(trans("emergency_fund_unsubscribed_success", default='Successfully unsubscribed from email notifications.'), "success")
        else:
            current_app.logger.warning(f"No records found to unsubscribe email {email} for session {session['sid']}", extra={'session_id': session['sid']})
            flash(trans("emergency_fund_unsubscribe_error", default='No email notifications found for this email.'), "danger")
        return redirect(url_for('personal.index'))
    except Exception as e:
        current_app.logger.error(f"Error in emergency_fund.unsubscribe for session {session.get('sid', 'unknown')}: {str(e)}", extra={'session_id': session['sid']})
        flash(trans("emergency_fund_unsubscribe_error", default='Error unsubscribing from email notifications.'), "danger")
        return redirect(url_for('personal.index'))

@emergency_fund_bp.errorhandler(CSRFError)
def handle_csrf_error(e):
    """Handle CSRF errors with user-friendly message."""
    current_app.logger.error(f"CSRF error on {request.path}: {e.description}", extra={'session_id': session.get('sid', 'unknown')})
    flash(trans('emergency_fund_csrf_error', default='Form submission failed due to a missing security token. Please refresh and try again.'), 'danger')
    return redirect(url_for('personal.index')), 400
