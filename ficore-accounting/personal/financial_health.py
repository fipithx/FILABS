from flask import Blueprint, request, session, redirect, url_for, render_template, flash, current_app, jsonify
from flask_wtf import FlaskForm
from flask_wtf.csrf import CSRFProtect, CSRFError
from wtforms import StringField, SelectField, BooleanField, SubmitField, FloatField
from wtforms.validators import DataRequired, NumberRange, Optional, Email, ValidationError
from flask_login import current_user, login_required
from datetime import datetime
from bson import ObjectId
from mailersend_email import send_email, EMAIL_CONFIG
from translations import trans
from models import log_tool_usage
from session_utils import create_anonymous_session
from utils import requires_role, is_admin, get_mongo_db, format_currency, limiter

financial_health_bp = Blueprint(
    'financial_health',
    __name__,
    template_folder='templates/personal/HEALTHSCORE',
    url_prefix='/health_score'
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

def get_mongo_collection():
    return get_mongo_db()['financial_health_scores']

class CommaSeparatedFloatField(FloatField):
    def process_formdata(self, valuelist):
        if valuelist:
            try:
                self.data = float(valuelist[0].replace(',', ''))
            except ValueError:
                self.data = None
                raise ValidationError(self.gettext('Not a valid number'))

class FinancialHealthForm(FlaskForm):
    first_name = StringField(
        trans('general_first_name', default='First Name'),
        validators=[DataRequired(message=trans('general_first_name_required', default='Please enter your first name.'))]
    )
    email = StringField(
        trans('general_email', default='Email'),
        validators=[Optional(), Email(message=trans('general_email_invalid', default='Please enter a valid email address.'))]
    )
    user_type = SelectField(
        trans('financial_health_user_type', default='User Type'),
        choices=[
            ('individual', trans('financial_health_user_type_individual', default='Individual')),
            ('business', trans('financial_health_user_type_business', default='Business'))
        ]
    )
    send_email = BooleanField(
        trans('general_send_email', default='Send Email'),
        default=False
    )
    income = CommaSeparatedFloatField(
        trans('financial_health_monthly_income', default='Monthly Income'),
        validators=[
            DataRequired(message=trans('financial_health_income_required', default='Please enter your monthly income.')),
            NumberRange(min=0, max=10000000000, message=trans('financial_health_income_max', default='Income exceeds maximum limit.'))
        ]
    )
    expenses = CommaSeparatedFloatField(
        trans('financial_health_monthly_expenses', default='Monthly Expenses'),
        validators=[
            DataRequired(message=trans('financial_health_expenses_required', default='Please enter your monthly expenses.')),
            NumberRange(min=0, max=10000000000, message=trans('financial_health_expenses_max', default='Expenses exceed maximum limit.'))
        ]
    )
    debt = CommaSeparatedFloatField(
        trans('financial_health_total_debt', default='Total Debt'),
        validators=[
            Optional(),
            NumberRange(min=0, max=10000000000, message=trans('financial_health_debt_max', default='Debt exceeds maximum limit.'))
        ]
    )
    interest_rate = CommaSeparatedFloatField(
        trans('financial_health_average_interest_rate', default='Average Interest Rate'),
        validators=[
            Optional(),
            NumberRange(min=0, message=trans('financial_health_interest_rate_positive', default='Interest rate must be positive.'))
        ]
    )
    submit = SubmitField(trans('financial_health_submit', default='Submit'))

    def validate_email(self, field):
        if self.send_email.data and not field.data:
            current_app.logger.warning(f"Email required for notifications for session {session.get('sid', 'no-session-id')}", extra={'session_id': session.get('sid', 'no-session-id')})
            raise ValidationError(trans('general_email_required', default='Valid email is required for notifications'))

@financial_health_bp.route('/main', methods=['GET', 'POST'])
@custom_login_required
@requires_role(['personal', 'admin'])
def main():
    """Main financial health interface with tabbed layout."""
    if 'sid' not in session:
        create_anonymous_session()
        current_app.logger.debug(f"New anonymous session created with sid: {session['sid']}", extra={'session_id': session['sid']})
    session.permanent = True
    session.modified = True
    
    form_data = {}
    if current_user.is_authenticated:
        form_data['email'] = current_user.email
        form_data['first_name'] = current_user.get_first_name()
    
    form = FinancialHealthForm(data=form_data)
    
    current_app.logger.info(f"Starting main for session {session['sid']} {'(anonymous)' if session.get('is_anonymous') else ''}", extra={'session_id': session['sid']})
    try:
        log_tool_usage(
            tool_name='financial_health',
            user_id=current_user.id if current_user.is_authenticated else None,
            session_id=session['sid'],
            action='main_view',
            mongo=get_mongo_db()
        )
    except Exception as e:
        current_app.logger.error(f"Failed to log tool usage: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
        flash(trans('financial_health_log_error', default='Error logging financial health activity. Please try again.'), 'warning')
    
    try:
        filter_criteria = {} if is_admin() else {'user_id': current_user.id} if current_user.is_authenticated else {'session_id': session['sid']}
        
        if request.method == 'POST':
            action = request.form.get('action')
            
            if action == 'calculate_score' and form.validate_on_submit():
                try:
                    log_tool_usage(
                        tool_name='financial_health',
                        user_id=current_user.id if current_user.is_authenticated else None,
                        session_id=session['sid'],
                        action='calculate_score',
                        mongo=get_mongo_db()
                    )
                except Exception as e:
                    current_app.logger.error(f"Failed to log financial health score calculation: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
                    flash(trans('financial_health_log_error', default='Error logging financial health score calculation. Continuing with submission.'), 'warning')
                
                debt = float(form.debt.data) if form.debt.data else 0
                interest_rate = float(form.interest_rate.data) if form.interest_rate.data else 0
                income = form.income.data
                expenses = form.expenses.data

                if income <= 0:
                    current_app.logger.error(f"Income is zero or negative for session {session['sid']}", extra={'session_id': session['sid']})
                    flash(trans("financial_health_income_zero_error", default='Income must be greater than zero.'), "danger")
                    return redirect(url_for('financial_health.main'))

                debt_to_income = (debt / income * 100) if income > 0 else 0
                savings_rate = ((income - expenses) / income * 100) if income > 0 else 0
                interest_burden = ((interest_rate * debt / 100) / 12) / income * 100 if debt > 0 and income > 0 else 0

                score = 100
                if debt_to_income > 0:
                    score -= min(debt_to_income / 50, 50)
                if savings_rate < 0:
                    score -= min(abs(savings_rate), 30)
                elif savings_rate > 0:
                    score += min(savings_rate / 2, 20)
                score -= min(interest_burden, 20)
                score = max(0, min(100, round(score)))

                if score >= 80:
                    status_key = "excellent"
                    status = trans("financial_health_status_excellent", default='Excellent')
                elif score >= 60:
                    status_key = "good"
                    status = trans("financial_health_status_good", default='Good')
                else:
                    status_key = "needs_improvement"
                    status = trans("financial_health_status_needs_improvement", default='Needs Improvement')

                badges = []
                if score >= 80:
                    badges.append(trans("financial_health_badge_financial_star", default='Financial Star'))
                if debt_to_income < 20:
                    badges.append(trans("financial_health_badge_debt_manager", default='Debt Manager'))
                if savings_rate >= 20:
                    badges.append(trans("financial_health_badge_savings_pro", default='Savings Pro'))
                if interest_burden == 0 and debt > 0:
                    badges.append(trans("financial_health_badge_interest_free", default='Interest Free'))

                collection = get_mongo_collection()
                record_data = {
                    '_id': ObjectId(),
                    'user_id': current_user.id if current_user.is_authenticated else None,
                    'session_id': session['sid'],
                    'first_name': form.first_name.data,
                    'email': form.email.data,
                    'user_type': form.user_type.data,
                    'income': income,
                    'expenses': expenses,
                    'debt': debt,
                    'interest_rate': interest_rate,
                    'debt_to_income': debt_to_income,
                    'savings_rate': savings_rate,
                    'interest_burden': interest_burden,
                    'score': score,
                    'status': status,
                    'status_key': status_key,
                    'badges': badges,
                    'send_email': form.send_email.data,
                    'created_at': datetime.utcnow()
                }

                try:
                    collection.insert_one(record_data)
                    current_app.logger.info(f"Financial health data saved to MongoDB with ID {record_data['_id']} for session {session['sid']}", extra={'session_id': session['sid']})
                    flash(trans("financial_health_completed_success", default='Financial health score calculated successfully!'), "success")
                except Exception as e:
                    current_app.logger.error(f"Failed to save financial health data to MongoDB: {str(e)}", extra={'session_id': session['sid']})
                    flash(trans("financial_health_storage_error", default='Error saving financial health score.'), "danger")
                    return redirect(url_for('financial_health.main'))

                if form.send_email.data and form.email.data:
                    try:
                        config = EMAIL_CONFIG["financial_health"]
                        subject = trans(config["subject_key"], default='Your Financial Health Score')
                        template = config["template"]
                        send_email(
                            app=current_app,
                            logger=current_app.logger,
                            to_email=form.email.data,
                            subject=subject,
                            template_name=template,
                            data={
                                "first_name": form.first_name.data,
                                "score": score,
                                "status": status,
                                "income": format_currency(income),
                                "expenses": format_currency(expenses),
                                "debt": format_currency(debt),
                                "interest_rate": f"{interest_rate:.2f}%",
                                "debt_to_income": f"{debt_to_income:.2f}%",
                                "savings_rate": f"{savings_rate:.2f}%",
                                "interest_burden": f"{interest_burden:.2f}%",
                                "badges": badges,
                                "created_at": record_data['created_at'].strftime('%Y-%m-%d'),
                                "cta_url": url_for('financial_health.main', _external=True),
                                "unsubscribe_url": url_for('financial_health.unsubscribe', email=form.email.data, _external=True)
                            },
                            lang=session.get('lang', 'en')
                        )
                        current_app.logger.info(f"Email sent to {form.email.data} for session {session['sid']}", extra={'session_id': session['sid']})
                    except Exception as e:
                        current_app.logger.error(f"Failed to send email: {str(e)}", extra={'session_id': session['sid']})
                        flash(trans("general_email_send_failed", default='Failed to send email.'), "warning")

        collection = get_mongo_collection()
        stored_records = list(collection.find(filter_criteria).sort('created_at', -1))
        
        records = []
        for record in stored_records:
            record_data = {
                'id': str(record['_id']),
                'user_id': record.get('user_id'),
                'session_id': record.get('session_id'),
                'first_name': record.get('first_name'),
                'email': record.get('email'),
                'user_type': record.get('user_type'),
                'income': format_currency(record.get('income', 0)),
                'expenses': format_currency(record.get('expenses', 0)),
                'debt': format_currency(record.get('debt', 0)),
                'interest_rate': f"{record.get('interest_rate', 0):.2f}%",
                'debt_to_income': f"{record.get('debt_to_income', 0):.2f}%",
                'savings_rate': f"{record.get('savings_rate', 0):.2f}%",
                'interest_burden': f"{record.get('interest_burden', 0):.2f}%",
                'score': record.get('score', 0),
                'status': record.get('status', 'Unknown'),
                'status_key': record.get('status_key', 'unknown'),
                'badges': record.get('badges', []),
                'send_email': record.get('send_email', False),
                'created_at': record.get('created_at').strftime('%Y-%m-%d') if record.get('created_at') else 'N/A'
            }
            records.append((record_data['id'], record_data))
        
        latest_record = records[0][1] if records else {
            'score': 0,
            'status': 'Unknown',
            'savings_rate': '0.00%',
            'income': format_currency(0),
            'expenses': format_currency(0),
            'debt': format_currency(0),
            'interest_rate': '0.00%',
            'debt_to_income': '0.00%',
            'interest_burden': '0.00%',
            'badges': [],
            'created_at': 'N/A'
        }

        all_records = list(collection.find({}))
        all_scores_for_comparison = [record['score'] for record in all_records if record.get('score') is not None]

        total_users = len(all_scores_for_comparison)
        rank = 0
        average_score = 0
        if all_scores_for_comparison:
            all_scores_for_comparison.sort(reverse=True)
            user_score = latest_record.get("score", 0)
            rank = sum(1 for s in all_scores_for_comparison if s > user_score) + 1
            average_score = sum(all_scores_for_comparison) / total_users

        insights = []
        cross_tool_insights = []
        if latest_record and latest_record['score'] > 0:
            if float(latest_record['debt_to_income'].replace('%', '')) > 40:
                insights.append(trans("financial_health_insight_high_debt", default='Your debt-to-income ratio is high. Consider reducing debt.'))
            if float(latest_record['savings_rate'].replace('%', '')) < 0:
                insights.append(trans("financial_health_insight_negative_savings", default='Your expenses exceed your income. Review your budget.'))
            elif float(latest_record['savings_rate'].replace('%', '')) >= 20:
                insights.append(trans("financial_health_insight_good_savings", default='Great job maintaining a strong savings rate!'))
            if float(latest_record['interest_burden'].replace('%', '')) > 10:
                insights.append(trans("financial_health_insight_high_interest", default='High interest burden detected. Consider refinancing.'))
            if total_users >= 5:
                if rank <= total_users * 0.1:
                    insights.append(trans("financial_health_insight_top_10", default='You are in the top 10% of users!'))
                elif rank <= total_users * 0.3:
                    insights.append(trans("financial_health_insight_top_30", default='You are in the top 30% of users.'))
                else:
                    insights.append(trans("financial_health_insight_below_30", default='Your score is below the top 30%. Keep improving!'))
            else:
                insights.append(trans("financial_health_insight_not_enough_users", default='Not enough users for ranking comparison.'))
        
        filter_kwargs_budget = {'user_id': current_user.id} if current_user.is_authenticated else {'session_id': session['sid']}
        budget_data = get_mongo_db().budgets.find(filter_kwargs_budget).sort('created_at', -1)
        budget_data = list(budget_data)
        if budget_data and latest_record and latest_record.get('score', 0) < 80:
            latest_budget = budget_data[0]
            if latest_budget.get('income') and latest_budget.get('fixed_expenses'):
                savings_possible = latest_budget['income'] - latest_budget['fixed_expenses']
                if savings_possible > 0:
                    cross_tool_insights.append(trans('financial_health_cross_tool_savings_possible', default='Your budget shows {amount} available for savings monthly.', amount=format_currency(savings_possible)))

        return render_template(
            'personal/HEALTHSCORE/health_score_main.html',
            form=form,
            records=records,
            latest_record=latest_record,
            insights=insights,
            cross_tool_insights=cross_tool_insights,
            tips=[
                trans("financial_health_tip_track_expenses", default='Track your expenses to identify savings opportunities.'),
                trans("financial_health_tip_ajo_savings", default='Contribute to ajo savings for financial discipline.'),
                trans("financial_health_tip_pay_debts", default='Prioritize paying off high-interest debts.'),
                trans("financial_health_tip_plan_expenses", default='Plan your expenses to maintain a positive savings rate.')
            ],
            rank=rank,
            total_users=total_users,
            average_score=average_score,
            tool_title=trans('financial_health_title', default='Financial Health Score')
        )

    except Exception as e:
        current_app.logger.error(f"Error in financial_health.main for session {session.get('sid', 'unknown')}: {str(e)}", extra={'session_id': session['sid']})
        flash(trans("financial_health_dashboard_load_error", default='Error loading financial health dashboard.'), "danger")
        return render_template(
            'personal/HEALTHSCORE/health_score_main.html',
            form=form,
            records=[],
            latest_record={
                'score': 0,
                'status': 'Unknown',
                'savings_rate': '0.00%',
                'income': format_currency(0),
                'expenses': format_currency(0),
                'debt': format_currency(0),
                'interest_rate': '0.00%',
                'debt_to_income': '0.00%',
                'interest_burden': '0.00%',
                'badges': [],
                'created_at': 'N/A'
            },
            insights=[trans("financial_health_insight_no_data", default='No financial health data available.')],
            cross_tool_insights=[],
            tips=[
                trans("financial_health_tip_track_expenses", default='Track your expenses to identify savings opportunities.'),
                trans("financial_health_tip_ajo_savings", default='Contribute to ajo savings for financial discipline.'),
                trans("financial_health_tip_pay_debts", default='Prioritize paying off high-interest debts.'),
                trans("financial_health_tip_plan_expenses", default='Plan your expenses to maintain a positive savings rate.')
            ],
            rank=0,
            total_users=0,
            average_score=0,
            tool_title=trans('financial_health_title', default='Financial Health Score')
        ), 500

@financial_health_bp.route('/summary')
@login_required
@requires_role(['personal', 'admin'])
def summary():
    """Return the latest financial health score for the current user."""
    try:
        filter_criteria = {} if is_admin() else {'user_id': current_user.id}
        collection = get_mongo_collection()
        
        latest_record = collection.find(filter_criteria).sort('created_at', -1).limit(1)
        latest_record = list(latest_record)
        
        if not latest_record:
            current_app.logger.info(f"No financial health record found for user {current_user.id}", 
                                  extra={'session_id': session.get('sid', 'unknown')})
            return jsonify({'financialHealthScore': 0})
        
        score = latest_record[0].get('score', 0)
        current_app.logger.info(f"Fetched financial health summary for user {current_user.id}: {score}", 
                              extra={'session_id': session.get('sid', 'unknown')})
        return jsonify({'financialHealthScore': score})
    except Exception as e:
        current_app.logger.error(f"Error in financial_health.summary: {str(e)}", 
                                extra={'session_id': session.get('sid', 'unknown')})
        return jsonify({'financialHealthScore': 0}), 500

@financial_health_bp.route('/unsubscribe/<email>')
@custom_login_required
@requires_role(['personal', 'admin'])
def unsubscribe(email):
    """Unsubscribe user from financial health emails."""
    if 'sid' not in session:
        create_anonymous_session()
        current_app.logger.debug(f"New anonymous session created with sid: {session['sid']}", extra={'session_id': session['sid']})
    session.permanent = True
    session.modified = True
    
    try:
        try:
            log_tool_usage(
                tool_name='financial_health',
                user_id=current_user.id if current_user.is_authenticated else None,
                session_id=session['sid'],
                action='unsubscribe',
                mongo=get_mongo_db()
            )
        except Exception as e:
            current_app.logger.error(f"Failed to log unsubscribe action: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
            flash(trans('financial_health_log_error', default='Error logging unsubscribe action. Continuing with unsubscription.'), 'warning')
        
        filter_kwargs = {'email': email} if is_admin() else {'email': email, 'user_id': current_user.id} if current_user.is_authenticated else {'email': email, 'session_id': session['sid']}
        result = get_mongo_collection().update_many(
            filter_kwargs,
            {'$set': {'send_email': False}}
        )
        if result.modified_count > 0:
            current_app.logger.info(f"Unsubscribed email {email} for session {session['sid']}", extra={'session_id': session['sid']})
            flash(trans("financial_health_unsubscribed_success", default='Successfully unsubscribed from email notifications.'), "success")
        else:
            current_app.logger.warning(f"No records found to unsubscribe email {email} for session {session['sid']}", extra={'session_id': session['sid']})
            flash(trans("financial_health_unsubscribe_error", default='No email notifications found for this email.'), "danger")
        return redirect(url_for('personal.index'))
    except Exception as e:
        current_app.logger.error(f"Error in financial_health.unsubscribe for session {session.get('sid', 'unknown')}: {str(e)}", extra={'session_id': session['sid']})
        flash(trans("financial_health_unsubscribe_error", default='Error unsubscribing from email notifications.'), "danger")
        return redirect(url_for('personal.index'))

@financial_health_bp.errorhandler(CSRFError)
def handle_csrf_error(e):
    """Handle CSRF errors with user-friendly message."""
    current_app.logger.error(f"CSRF error on {request.path}: {e.description}", extra={'session_id': session.get('sid', 'unknown')})
    flash(trans('financial_health_csrf_error', default='Form submission failed due to a missing security token. Please refresh and try again.'), 'danger')
    return redirect(url_for('personal.index')), 400
