from flask import Blueprint, request, session, redirect, url_for, render_template, flash, current_app, jsonify
from flask_wtf import FlaskForm
from flask_wtf.csrf import CSRFProtect, CSRFError
from wtforms import BooleanField, SubmitField, FloatField
from wtforms.validators import DataRequired, NumberRange, Optional, ValidationError
from flask_login import current_user, login_required
from datetime import datetime
from bson import ObjectId
from utils import get_all_recent_activities, requires_role, is_admin, get_mongo_db, limiter, log_tool_usage, check_ficore_credit_balance 
from mailersend_email import send_email, EMAIL_CONFIG
from translations import trans
from session_utils import create_anonymous_session

financial_health_bp = Blueprint(
    'financial_health',
    __name__,
    template_folder='templates/personal/HEALTHSCORE',
    url_prefix='/health_score'
)

# CSRF protection (must be initialized with app in main app setup)
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

def strip_commas(value):
    """Strip commas from string values."""
    if isinstance(value, str):
        return value.replace(',', '')
    return value

def clean_currency(value):
    """Clean and convert currency string to float."""
    if value is None:
        return None
    try:
        if isinstance(value, str):
            value = value.replace(',', '').replace('$', '').strip()
        return float(value)
    except (ValueError, TypeError):
        return None

def format_currency(value):
    """Format a number as currency."""
    try:
        return f"${value:,.2f}"
    except (ValueError, TypeError):
        return "$0.00"

def deduct_ficore_credits(db, user_id, amount, action, budget_id=None):
    """Deduct Ficore Credits from user balance and log the transaction."""
    try:
        user = db.users.find_one({'_id': user_id})
        if not user:
            return False
        current_balance = user.get('ficore_credit_balance', 0)
        if current_balance < amount:
            return False
        result = db.users.update_one(
            {'_id': user_id},
            {'$inc': {'ficore_credit_balance': -amount}}
        )
        if result.modified_count == 0:
            return False
        transaction = {
            '_id': ObjectId(),
            'user_id': user_id,
            'action': action,
            'amount': -amount,
            'budget_id': str(budget_id) if budget_id else None,
            'timestamp': datetime.utcnow(),
            'session_id': session.get('sid', 'unknown'),
            'status': 'completed'
        }
        db.credit_transactions.insert_one(transaction)
        return True
    except Exception:
        return False

class FinancialHealthForm(FlaskForm):
    send_email = BooleanField(
        trans('general_send_email', default='Send Email'),
        default=False
    )
    income = FloatField(
        trans('financial_health_monthly_income', default='Monthly Income'),
        filters=[strip_commas],
        validators=[
            DataRequired(message=trans('financial_health_income_required', default='Please enter your monthly income.')),
            NumberRange(min=0, max=10000000000, message=trans('financial_health_income_max', default='Income must be positive and reasonable.'))
        ]
    )
    expenses = FloatField(
        trans('financial_health_monthly_expenses', default='Monthly Expenses'),
        filters=[strip_commas],
        validators=[
            DataRequired(message=trans('financial_health_expenses_required', default='Please enter your monthly expenses.')),
            NumberRange(min=0, max=10000000000, message=trans('financial_health_expenses_max', default='Expenses must be positive and reasonable.'))
        ]
    )
    debt = FloatField(
        trans('financial_health_total_debt', default='Total Debt'),
        filters=[strip_commas],
        validators=[
            Optional(),
            NumberRange(min=0, max=10000000000, message=trans('financial_health_debt_max', default='Debt must be positive and reasonable.'))
        ]
    )
    submit = SubmitField(trans('financial_health_submit', default='Submit'))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        lang = session.get('lang', 'en')
        self.send_email.label.text = trans('general_send_email', lang) or 'Send Email'
        self.income.label.text = trans('financial_health_monthly_income', lang) or 'Monthly Income'
        self.expenses.label.text = trans('financial_health_monthly_expenses', lang) or 'Monthly Expenses'
        self.debt.label.text = trans('financial_health_total_debt', lang) or 'Total Debt'
        self.submit.label.text = trans('financial_health_submit', lang) or 'Submit'

    def validate_income(self, field):
        """Custom validator to handle comma-separated numbers."""
        if field.data is None:
            return
        try:
            field.data = clean_currency(field.data)
            if field.data is None:
                raise ValueError("Invalid income format")
            current_app.logger.debug(f"Validated income for session {session.get('sid', 'no-session-id')}: {field.data}")
        except ValueError:
            current_app.logger.warning(f"Invalid income value for session {session.get('sid', 'no-session-id')}: {field.data}")
            raise ValidationError(trans('financial_health_income_invalid', default='Invalid income format'))

    def validate_expenses(self, field):
        """Custom validator to handle comma-separated numbers."""
        if field.data is None:
            return
        try:
            field.data = clean_currency(field.data)
            if field.data is None:
                raise ValueError("Invalid expenses format")
            current_app.logger.debug(f"Validated expenses for session {session.get('sid', 'no-session-id')}: {field.data}")
        except ValueError:
            current_app.logger.warning(f"Invalid expenses value for session {session.get('sid', 'no-session-id')}: {field.data}")
            raise ValidationError(trans('financial_health_expenses_invalid', default='Invalid expenses format'))

    def validate_debt(self, field):
        """Custom validator to handle comma-separated numbers."""
        if field.data is None:
            return
        try:
            field.data = clean_currency(field.data)
            if field.data is None:
                raise ValueError("Invalid debt format")
            current_app.logger.debug(f"Validated debt for session {session.get('sid', 'no-session-id')}: {field.data}")
        except ValueError:
            current_app.logger.warning(f"Invalid debt value for session {session.get('sid', 'no-session-id')}: {field.data}")
            raise ValidationError(trans('financial_health_debt_invalid', default='Invalid debt format'))

@financial_health_bp.route('/main', methods=['GET', 'POST'])
@custom_login_required
@requires_role(['personal', 'admin'])
@limiter.limit("10 per minute")
def main():
    """Main financial health interface with tabbed layout."""
    if 'sid' not in session:
        create_anonymous_session()
        current_app.logger.debug(f"New anonymous session created with sid: {session['sid']}", extra={'session_id': session['sid']})
    session.permanent = True
    session.modified = True

    form = FinancialHealthForm()
    db = get_mongo_db()
    valid_tabs = ['assessment', 'dashboard']
    active_tab = request.args.get('tab', 'assessment')
    if active_tab not in valid_tabs:
        active_tab = 'assessment'

    try:
        log_tool_usage(
            tool_name='financial_health',
            db=db,
            user_id=current_user.id if current_user.is_authenticated else None,
            session_id=session.get('sid', 'unknown'),
            action='main_view'
        )
    except Exception as e:
        current_app.logger.error(f"Failed to log tool usage: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
        flash(trans('financial_health_log_error', default='Error logging financial health activity. Please try again.'), 'warning')

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
        flash(trans('financial_health_activities_load_error', default='Error loading recent activities.'), 'warning')
        activities = []

    try:
        filter_criteria = {} if is_admin() else {'user_id': current_user.id} if current_user.is_authenticated else {'session_id': session['sid']}

        if request.method == 'POST':
            action = request.form.get('action')
            if action == 'calculate_score' and form.validate_on_submit():
                if current_user.is_authenticated and not is_admin():
                    if not check_ficore_credit_balance(required_amount=1, user_id=current_user.id):
                        current_app.logger.warning(f"Insufficient Ficore Credits for calculating score by user {current_user.id}", extra={'session_id': session.get('sid', 'unknown')})
                        flash(trans('financial_health_insufficient_credits', default='Insufficient Ficore Credits to calculate score. Please purchase more credits.'), 'danger')
                        return redirect(url_for('agents_bp.manage_credits'))

                try:
                    log_tool_usage(
                        tool_name='financial_health',
                        db=db,
                        user_id=current_user.id if current_user.is_authenticated else None,
                        session_id=session.get('sid', 'unknown'),
                        action='calculate_score'
                    )
                except Exception as e:
                    current_app.logger.error(f"Failed to log financial health score calculation: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
                    flash(trans('financial_health_log_error', default='Error logging financial health score calculation. Continuing with submission.'), 'warning')

                debt = form.debt.data or 0
                income = form.income.data
                expenses = form.expenses.data

                if income <= 0:
                    current_app.logger.error(f"Income is zero or negative for session {session['sid']}", extra={'session_id': session['sid']})
                    flash(trans("financial_health_income_zero_error", default='Income must be greater than zero.'), "danger")
                    return redirect(url_for('personal.financial_health.main', tab='assessment'))

                # Calculate metrics
                debt_to_income = (debt / income * 100) if income > 0 else 0
                savings = income - expenses
                savings_rate = (savings / income * 100) if income > 0 else 0
                expense_ratio = (expenses / income * 100) if income > 0 else 100

                # Debt-to-Income Ratio Score (50 points)
                if debt_to_income <= 20:
                    dti_score = 50
                elif debt_to_income <= 35:
                    dti_score = 40
                elif debt_to_income <= 50:
                    dti_score = 30
                elif debt_to_income <= 65:
                    dti_score = 20
                else:
                    dti_score = 10

                # Savings Rate Score (30 points)
                if savings_rate >= 20:
                    savings_score = 30
                elif savings_rate >= 10:
                    savings_score = 20
                elif savings_rate >= 5:
                    savings_score = 10
                else:
                    savings_score = 0

                # Expense Management Score (20 points)
                if expense_ratio <= 50:
                    expense_score = 20
                elif expense_ratio <= 70:
                    expense_score = 15
                elif expense_ratio <= 90:
                    expense_score = 10
                else:
                    expense_score = 5

                # Total Score
                score = dti_score + savings_score + expense_score
                score = max(0, min(100, round(score)))

                # Status
                if score >= 80:
                    status_key = "excellent"
                    status = trans("financial_health_status_excellent", default='Excellent')
                elif score >= 60:
                    status_key = "good"
                    status = trans("financial_health_status_good", default='Good')
                else:
                    status_key = "needs_improvement"
                    status = trans("financial_health_status_needs_improvement", default='Needs Improvement')

                # Badges
                badges = []
                if score >= 80:
                    badges.append(trans("financial_health_badge_financial_star", default='Financial Star'))
                if debt_to_income <= 20:
                    badges.append(trans("financial_health_badge_debt_manager", default='Debt Manager'))
                if savings_rate >= 20:
                    badges.append(trans("financial_health_badge_savings_pro", default='Savings Pro'))
                if expense_ratio <= 50:
                    badges.append(trans("financial_health_badge_expense_master", default='Expense Master'))

                record_data = {
                    '_id': ObjectId(),
                    'user_id': current_user.id if current_user.is_authenticated else None,
                    'session_id': session['sid'],
                    'user_email': current_user.email if current_user.is_authenticated else None,
                    'income': income,
                    'expenses': expenses,
                    'debt': debt,
                    'debt_to_income': debt_to_income,
                    'savings_rate': savings_rate,
                    'expense_ratio': expense_ratio,
                    'dti_score': dti_score,
                    'savings_score': savings_score,
                    'expense_score': expense_score,
                    'score': score,
                    'status': status,
                    'status_key': status_key,
                    'badges': badges,
                    'send_email': form.send_email.data,
                    'created_at': datetime.utcnow()
                }

                try:
                    db.financial_health.insert_one(record_data)
                    if current_user.is_authenticated and not is_admin():
                        if not deduct_ficore_credits(db, current_user.id, 1, 'calculate_score', record_data['_id']):
                            db.financial_health.delete_one({'_id': record_data['_id']})  # Rollback on failure
                            current_app.logger.error(f"Failed to deduct Ficore Credit for calculating score {record_data['_id']} by user {current_user.id}", extra={'session_id': session.get('sid', 'unknown')})
                            flash(trans('financial_health_credit_deduction_failed', default='Failed to deduct Ficore Credit for calculating score.'), 'danger')
                            return redirect(url_for('personal.financial_health.main', tab='assessment'))
                    current_app.logger.info(f"Financial health data saved to MongoDB with ID {record_data['_id']} for session {session['sid']}", extra={'session_id': session['sid']})
                    flash(trans("financial_health_completed_success", default='Financial health score calculated successfully!'), "success")
                except Exception as e:
                    current_app.logger.error(f"Failed to save financial health data to MongoDB: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
                    flash(trans("financial_health_storage_error", default='Error saving financial health score.'), "danger")
                    return redirect(url_for('personal.financial_health.main', tab='assessment'))

                if form.send_email.data and current_user.is_authenticated:
                    try:
                        config = EMAIL_CONFIG["financial_health"]
                        subject = trans(config["subject_key"], default='Your Financial Health Score')
                        template = config["template"]
                        send_email(
                            app=current_app,
                            logger=current_app.logger,
                            to_email=current_user.email,
                            subject=subject,
                            template_name=template,
                            data={
                                "first_name": current_user.get_first_name(),
                                "score": score,
                                "status": status,
                                "income": format_currency(income),
                                "expenses": format_currency(expenses),
                                "debt": format_currency(debt),
                                "debt_to_income": f"{debt_to_income:.2f}%",
                                "savings_rate": f"{savings_rate:.2f}%",
                                "expense_ratio": f"{expense_ratio:.2f}%",
                                "dti_score": dti_score,
                                "savings_score": savings_score,
                                "expense_score": expense_score,
                                "badges": badges,
                                "created_at": record_data['created_at'].strftime('%Y-%m-%d'),
                                "cta_url": url_for('personal.financial_health.main', _external=True),
                                "unsubscribe_url": url_for('personal.financial_health.unsubscribe', _external=True)
                            },
                            lang=session.get('lang', 'en')
                        )
                        current_app.logger.info(f"Email sent to {current_user.email} for session {session['sid']}", extra={'session_id': session['sid']})
                    except Exception as e:
                        current_app.logger.error(f"Failed to send email: {str(e)}", extra={'session_id': session['sid']})
                        flash(trans("general_email_send_failed", default='Failed to send email.'), "warning")

                return redirect(url_for('personal.financial_health.main', tab='dashboard'))

        stored_records = list(db.financial_health.find(filter_criteria).sort('created_at', -1))
        current_app.logger.info(f"Read {len(stored_records)} records from MongoDB financial_health collection [session: {session['sid']}]", extra={'session_id': session['sid']})

        records = []
        for record in stored_records:
            record_data = {
                'id': str(record['_id']),
                'user_id': record.get('user_id'),
                'session_id': record.get('session_id'),
                'user_email': record.get('user_email'),
                'income': float(record.get('income', 0)),
                'income_formatted': format_currency(record.get('income', 0)),
                'income_raw': float(record.get('income', 0)),
                'expenses': float(record.get('expenses', 0)),
                'expenses_formatted': format_currency(record.get('expenses', 0)),
                'expenses_raw': float(record.get('expenses', 0)),
                'debt': float(record.get('debt', 0)),
                'debt_formatted': format_currency(record.get('debt', 0)),
                'debt_raw': float(record.get('debt', 0)),
                'debt_to_income': float(record.get('debt_to_income', 0)),
                'debt_to_income_formatted': f"{float(record.get('debt_to_income', 0)):.2f}%",
                'savings_rate': float(record.get('savings_rate', 0)),
                'savings_rate_formatted': f"{float(record.get('savings_rate', 0)):.2f}%",
                'expense_ratio': float(record.get('expense_ratio', 0)),
                'expense_ratio_formatted': f"{float(record.get('expense_ratio', 0)):.2f}%",
                'dti_score': record.get('dti_score', 0),
                'savings_score': record.get('savings_score', 0),
                'expense_score': record.get('expense_score', 0),
                'score': record.get('score', 0),
                'status': record.get('status', 'Unknown'),
                'status_key': record.get('status_key', 'unknown'),
                'badges': record.get('badges', []),
                'send_email': record.get('send_email', False),
                'created_at': record.get('created_at').strftime('%Y-%m-%d') if record.get('created_at') else 'N/A'
            }
            records.append((record_data['id'], record_data))

        latest_record = records[0][1] if records else {
            'id': None,
            'user_id': None,
            'session_id': session.get('sid', 'unknown'),
            'user_email': current_user.email if current_user.is_authenticated else '',
            'score': 0,
            'status': 'Unknown',
            'status_key': 'unknown',
            'income': 0.0,
            'income_formatted': format_currency(0.0),
            'income_raw': 0.0,
            'expenses': 0.0,
            'expenses_formatted': format_currency(0.0),
            'expenses_raw': 0.0,
            'debt': 0.0,
            'debt_formatted': format_currency(0.0),
            'debt_raw': 0.0,
            'debt_to_income': 0.0,
            'debt_to_income_formatted': '0.00%',
            'savings_rate': 0.0,
            'savings_rate_formatted': '0.00%',
            'expense_ratio': 0.0,
            'expense_ratio_formatted': '0.00%',
            'dti_score': 0,
            'savings_score': 0,
            'expense_score': 0,
            'badges': [],
            'created_at': 'N/A'
        }

        all_records = list(db.financial_health.find())
        all_scores_for_comparison = [record['score'] for record in all_records if record.get('score') is not None]

        total_users = len(all_scores_for_comparison)
        rank = 0
        average_score = 0
        if all_scores_for_comparison:
            all_scores_for_comparison.sort(reverse=True)
            user_score = latest_record.get("score", 0)
            rank = sum(1 for s in all_scores_for_comparison if s > user_score) + 1
            average_score = sum(all_scores_for_comparison) / total_users if total_users else 0

        insights = []
        cross_tool_insights = []
        try:
            debt_to_income_float = float(latest_record['debt_to_income'])
            savings_rate_float = float(latest_record['savings_rate'])
            expense_ratio_float = float(latest_record['expense_ratio'])

            if debt_to_income_float > 35:
                insights.append(trans("financial_health_insight_high_debt", default='Your debt-to-income ratio is high. Consider reducing debt.'))
            elif debt_to_income_float <= 20:
                insights.append(trans("financial_health_insight_low_debt", default='Great job keeping your debt-to-income ratio low!'))
            if savings_rate_float < 5:
                insights.append(trans("financial_health_insight_low_savings", default='Your savings rate is low or negative. Review your budget to increase savings.'))
            elif savings_rate_float >= 20:
                insights.append(trans("financial_health_insight_good_savings", default='Great job maintaining a strong savings rate!'))
            if expense_ratio_float > 70:
                insights.append(trans("financial_health_insight_high_expenses", default='Your expenses are high relative to income. Consider cutting unnecessary costs.'))
            elif expense_ratio_float <= 50:
                insights.append(trans("financial_health_insight_good_expenses", default='Excellent expense management! Keep your expenses low.'))
            if total_users >= 5:
                if rank <= total_users * 0.1:
                    insights.append(trans("financial_health_insight_top_10", default='You are in the top 10% of users!'))
                elif rank <= total_users * 0.3:
                    insights.append(trans("financial_health_insight_top_30", default='You are in the top 30% of users.'))
                else:
                    insights.append(trans("financial_health_insight_below_30", default='Your score is below the top 30%. Keep improving!'))
            else:
                insights.append(trans("financial_health_insight_not_enough_users", default='Not enough users for ranking comparison.'))
        except (ValueError, TypeError) as e:
            current_app.logger.warning(f"Error parsing amounts for insights: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})

        filter_kwargs_budget = {'user_id': current_user.id} if current_user.is_authenticated else {'session_id': session['sid']}
        budget_data = db.budgets.find(filter_kwargs_budget).sort('created_at', -1)
        budget_data = list(budget_data)
        if budget_data:
            latest_budget = budget_data[0]
            if latest_budget.get('income') and latest_budget.get('fixed_expenses'):
                savings_possible = float(latest_budget['income']) - float(latest_budget['fixed_expenses'])
                if savings_possible > 0:
                    cross_tool_insights.append(trans(
                        'financial_health_cross_tool_savings_possible',
                        default='Your budget shows {amount} available for savings monthly.',
                        amount=format_currency(savings_possible)
                    ))

        return render_template(
            'personal/HEALTHSCORE/health_score_main.html',
            form=form,
            records=records,
            latest_record=latest_record,
            insights=insights,
            cross_tool_insights=cross_tool_insights,
            activities=activities,
            tips=[
                trans("financial_health_tip_track_expenses", default='Track your expenses to identify savings opportunities.'),
                trans("financial_health_tip_ajo_savings", default='Contribute to ajo savings for financial discipline.'),
                trans("financial_health_tip_pay_debts", default='Prioritize paying off high-interest debts.'),
                trans("financial_health_tip_plan_expenses", default='Plan your expenses to maintain a positive savings rate.')
            ],
            rank=rank,
            total_users=total_users,
            average_score=average_score,
            tool_title=trans('financial_health_title', default='Financial Health Score'),
            active_tab=active_tab
        )

    except Exception as e:
        current_app.logger.error(f"Unexpected error in financial_health.main active_tab: {active_tab}: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
        flash(trans('financial_health_dashboard_load_error', default='Error loading financial health dashboard.'), 'danger')
        return render_template(
            'personal/HEALTHSCORE/health_score_main.html',
            form=form,
            records=[],
            latest_record={
                'id': None,
                'user_id': None,
                'session_id': session.get('sid', 'unknown'),
                'user_email': current_user.email if current_user.is_authenticated else '',
                'score': 0,
                'status': 'Unknown',
                'status_key': 'unknown',
                'income': 0.0,
                'income_formatted': format_currency(0.0),
                'income_raw': 0.0,
                'expenses': 0.0,
                'expenses_formatted': format_currency(0.0),
                'expenses_raw': 0.0,
                'debt': 0.0,
                'debt_formatted': format_currency(0.0),
                'debt_raw': 0.0,
                'debt_to_income': 0.0,
                'debt_to_income_formatted': '0.00%',
                'savings_rate': 0.0,
                'savings_rate_formatted': '0.00%',
                'expense_ratio': 0.0,
                'expense_ratio_formatted': '0.00%',
                'dti_score': 0,
                'savings_score': 0,
                'expense_score': 0,
                'badges': [],
                'created_at': 'N/A'
            },
            insights=[trans("financial_health_insight_no_data", default='No financial health data available.')],
            cross_tool_insights=[],
            activities=activities,
            tips=[
                trans("financial_health_tip_track_expenses", default='Track your expenses to identify savings opportunities.'),
                trans("financial_health_tip_ajo_savings", default='Contribute to ajo savings for financial discipline.'),
                trans("financial_health_tip_pay_debts", default='Prioritize paying off high-interest debts.'),
                trans("financial_health_tip_plan_expenses", default='Plan your expenses to maintain a positive savings rate.')
            ],
            rank=0,
            total_users=0,
            average_score=0,
            tool_title=trans('financial_health_title', default='Financial Health Score'),
            active_tab=active_tab
        ), 500

@financial_health_bp.route('/summary')
@login_required
@requires_role(['personal', 'admin'])
@limiter.limit("5 per minute")
def summary():
    """Return the latest financial health score for the current user."""
    db = get_mongo_db()
    try:
        log_tool_usage(
            tool_name='financial_health',
            db=db,
            user_id=current_user.id if current_user.is_authenticated else None,
            session_id=session.get('sid', 'unknown'),
            action='summary_view'
        )
        filter_criteria = {} if is_admin() else {'user_id': current_user.id}
        latest_record = db.financial_health.find_one(filter_criteria, sort=[('created_at', -1)])

        if not latest_record:
            current_app.logger.info(f"No financial health record found for user {current_user.id}", extra={'session_id': session.get('sid', 'unknown')})
            return jsonify({
                'financialHealthScore': 0,
                'user_email': current_user.email if current_user.is_authenticated else ''
            })

        score = latest_record.get('score', 0)
        current_app.logger.info(f"Fetched financial health summary for user {current_user.id}: {score}", extra={'session_id': session.get('sid', 'unknown')})
        return jsonify({
            'financialHealthScore': score,
            'user_email': latest_record.get('user_email', current_user.email if current_user.is_authenticated else '')
        })
    except Exception as e:
        current_app.logger.error(f"Error in financial_health.summary: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
        return jsonify({
            'financialHealthScore': 0,
            'user_email': current_user.email if current_user.is_authenticated else ''
        }), 500

@financial_health_bp.route('/unsubscribe', methods=['POST'])
@custom_login_required
@requires_role(['personal', 'admin'])
@limiter.limit("5 per minute")
def unsubscribe():
    """Unsubscribe user from financial health emails."""
    db = get_mongo_db()
    if 'sid' not in session:
        create_anonymous_session()
        current_app.logger.debug(f"New anonymous session created with sid: {session['sid']}", extra={'session_id': session['sid']})
    session.permanent = True
    session.modified = True

    try:
        log_tool_usage(
            tool_name='financial_health',
            db=db,
            user_id=current_user.id if current_user.is_authenticated else None,
            session_id=session.get('sid', 'unknown'),
            action='unsubscribe'
        )
        filter_kwargs = {'user_email': current_user.email} if current_user.is_authenticated else {'session_id': session['sid']}
        result = db.financial_health.update_many(
            filter_kwargs,
            {'$set': {'send_email': False}}
        )
        if result.modified_count > 0:
            current_app.logger.info(f"Unsubscribed email {current_user.email} for session {session['sid']}", extra={'session_id': session['sid']})
            flash(trans("financial_health_unsubscribed_success", default='Successfully unsubscribed from email notifications.'), "success")
        else:
            current_app.logger.warning(f"No records found to unsubscribe email {current_user.email} for session {session['sid']}", extra={'session_id': session['sid']})
            flash(trans("financial_health_unsubscribe_error", default='No email notifications found for this email.'), "danger")
        return redirect(url_for('personal.financial_health.main', tab='dashboard'))
    except Exception as e:
        current_app.logger.error(f"Error in financial_health.unsubscribe for session {session.get('sid', 'unknown')}: {str(e)}", extra={'session_id': session['sid']})
        flash(trans("financial_health_unsubscribe_error", default='Error unsubscribing from email notifications.'), "danger")
        return redirect(url_for('personal.financial_health.main', tab='dashboard'))

@financial_health_bp.errorhandler(CSRFError)
def handle_csrf_error(e):
    """Handle CSRF errors with user-friendly message."""
    current_app.logger.error(f"CSRF error on {request.path}: {e.description}", extra={'session_id': session.get('sid', 'unknown')})
    flash(trans('financial_health_csrf_error', default='Form submission failed due to a missing security token. Please refresh and try again.'), 'danger')
    return redirect(url_for('personal.financial_health.main', tab='assessment')), 400
