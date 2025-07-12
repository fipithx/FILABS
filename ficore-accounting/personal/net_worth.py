from flask import Blueprint, jsonify, current_app, redirect, url_for, flash, render_template, request, session
from flask_wtf import FlaskForm
from flask_wtf.csrf import CSRFProtect, CSRFError
from wtforms import StringField, BooleanField, SubmitField, FloatField
from wtforms.validators import DataRequired, NumberRange, Optional, Email, ValidationError
from flask_login import current_user, login_required
from translations import trans
from mailersend_email import send_email, EMAIL_CONFIG
from datetime import datetime
from utils import get_all_recent_activities, requires_role, is_admin, get_mongo_db, limiter, format_currency, clean_currency
from bson import ObjectId
from models import log_tool_usage
from session_utils import create_anonymous_session

net_worth_bp = Blueprint(
    'net_worth',
    __name__,
    template_folder='templates/personal/NETWORTH',
    url_prefix='/NET_WORTH'
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

class NetWorthForm(FlaskForm):
    first_name = StringField(
        trans('general_first_name', default='First Name'),
        validators=[DataRequired(message=trans('general_first_name_required', default='Please enter your first name.'))]
    )
    email = StringField(
        trans('general_email', default='Email'),
        validators=[Optional(), Email(message=trans('general_email_invalid', default='Please enter a valid email address.'))]
    )
    send_email = BooleanField(
        trans('general_send_email', default='Send Email'),
        default=False
    )
    cash_savings = CommaSeparatedFloatField(
        trans('net_worth_cash_savings', default='Cash & Savings'),
        validators=[
            DataRequired(message=trans('net_worth_cash_savings_required', default='Please enter your cash and savings.')),
            NumberRange(min=0, max=10000000000, message=trans('net_worth_cash_savings_max', default='Cash & Savings exceeds maximum limit.'))
        ]
    )
    investments = CommaSeparatedFloatField(
        trans('net_worth_investments', default='Investments'),
        validators=[
            DataRequired(message=trans('net_worth_investments_required', default='Please enter your investments.')),
            NumberRange(min=0, max=10000000000, message=trans('net_worth_investments_max', default='Investments exceed maximum limit.'))
        ]
    )
    property = CommaSeparatedFloatField(
        trans('net_worth_property', default='Physical Property'),
        validators=[
            DataRequired(message=trans('net_worth_property_required', default='Please enter your physical property value.')),
            NumberRange(min=0, max=10000000000, message=trans('net_worth_property_max', default='Physical Property exceeds maximum limit.'))
        ]
    )
    loans = CommaSeparatedFloatField(
        trans('net_worth_loans', default='Loans & Debts'),
        validators=[
            Optional(),
            NumberRange(min=0, max=10000000000, message=trans('net_worth_loans_max', default='Loans exceed maximum limit.'))
        ]
    )
    submit = SubmitField(trans('net_worth_submit', default='Submit'))

    def validate_email(self, field):
        if self.send_email.data and not field.data:
            current_app.logger.warning(f"Email required for notifications for session {session.get('sid', 'no-session-id')}", extra={'session_id': session.get('sid', 'no-session-id')})
            raise ValidationError(trans('general_email_required', default='Valid email is required for notifications'))

@net_worth_bp.route('/main', methods=['GET', 'POST'])
@custom_login_required
@requires_role(['personal', 'admin'])
def main():
    """Main net worth interface with tabbed layout."""
    db = get_mongo_db()
    try:
        activities = get_all_recent_activities(db=db, user_id=current_user.id, limit=10)
        current_app.logger.debug(f"Fetched {len(activities)} recent activities for user {current_user.id}", extra={'session_id': session.get('sid', 'unknown')})
    except Exception as e:
        current_app.logger.error(f"Failed to fetch recent activities: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
        flash(trans('bill_activities_load_error', default='Error loading recent activities.'), 'warning')
        activities = []
    
    if 'sid' not in session:
        create_anonymous_session()
        current_app.logger.debug(f"New anonymous session created with sid: {session['sid']}", extra={'session_id': session['sid']})
    session.permanent = True
    session.modified = True
    
    form_data = {}
    if current_user.is_authenticated:
        form_data['email'] = current_user.email
        form_data['first_name'] = current_user.get_first_name()
    
    form = NetWorthForm(data=form_data)
    
    try:
        log_tool_usage(
            db=db,
            user_id=current_user.id if current_user.is_authenticated else None,
            session_id=session.get('sid', 'unknown'),
            action='main_view'
        )
        
        filter_criteria = {} if is_admin() else {'user_id': current_user.id} if current_user.is_authenticated else {'session_id': session['sid']}
        
        if request.method == 'POST':
            action = request.form.get('action')
            
            if action == 'calculate_net_worth' and form.validate_on_submit():
                log_tool_usage(
                    db=db,
                    user_id=current_user.id if current_user.is_authenticated else None,
                    session_id=session.get('sid', 'unknown'),
                    action='calculate_net_worth'
                )
                
                cash_savings = float(form.cash_savings.data)
                investments = float(form.investments.data)
                property = float(form.property.data)
                loans = float(form.loans.data or 0)

                total_assets = cash_savings + investments + property
                total_liabilities = loans
                net_worth = total_assets - total_liabilities

                badges = []
                if net_worth > 0:
                    badges.append(trans("net_worth_badge_wealth_builder", default='Wealth Builder'))
                if total_liabilities == 0:
                    badges.append(trans("net_worth_badge_debt_free", default='Debt Free'))
                if cash_savings >= total_assets * 0.3:
                    badges.append(trans("net_worth_badge_savings_champion", default='Savings Champion'))
                if property >= total_assets * 0.5:
                    badges.append(trans("net_worth_badge_property_mogul", default='Property Mogul'))

                net_worth_record = {
                    '_id': ObjectId(),
                    'user_id': current_user.id if current_user.is_authenticated else None,
                    'session_id': session['sid'],
                    'first_name': form.first_name.data,
                    'email': form.email.data,
                    'send_email': form.send_email.data,
                    'cash_savings': cash_savings,
                    'investments': investments,
                    'property': property,
                    'loans': loans,
                    'total_assets': total_assets,
                    'total_liabilities': total_liabilities,
                    'net_worth': net_worth,
                    'badges': badges,
                    'created_at': datetime.utcnow(),
                    'currency': 'NGN'
                }
                
                try:
                    db.net_worth_data.insert_one(net_worth_record)
                    current_app.logger.info(f"Successfully saved record {net_worth_record['_id']} for session {session.get('sid', 'unknown')}", extra={'session_id': session.get('sid', 'unknown')})
                    flash(trans("net_worth_success", default="Net worth calculated successfully"), "success")
                except Exception as e:
                    current_app.logger.error(f"Failed to save net worth data to MongoDB: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
                    flash(trans("net_worth_storage_error", default="Error saving net worth data."), "danger")
                    return redirect(url_for('net_worth.main'))

                if form.send_email.data and form.email.data:
                    try:
                        config = EMAIL_CONFIG["net_worth"]
                        subject = trans(config["subject_key"], default='Your Net Worth Summary')
                        email_data = {
                            "first_name": net_worth_record['first_name'],
                            "cash_savings": format_currency(net_worth_record['cash_savings'], net_worth_record.get('currency', 'NGN')),
                            "investments": format_currency(net_worth_record['investments'], net_worth_record.get('currency', 'NGN')),
                            "property": format_currency(net_worth_record['property'], net_worth_record.get('currency', 'NGN')),
                            "loans": format_currency(net_worth_record['loans'], net_worth_record.get('currency', 'NGN')),
                            "total_assets": format_currency(net_worth_record['total_assets'], net_worth_record.get('currency', 'NGN')),
                            "total_liabilities": format_currency(net_worth_record['total_liabilities'], net_worth_record.get('currency', 'NGN')),
                            "net_worth": format_currency(net_worth_record['net_worth'], net_worth_record.get('currency', 'NGN')),
                            "badges": badges,
                            "created_at": net_worth_record['created_at'].strftime('%Y-%m-%d'),
                            "cta_url": url_for('net_worth.main', _external=True),
                            "unsubscribe_url": url_for('net_worth.unsubscribe', email=form.email.data, _external=True),
                            "currency": net_worth_record.get('currency', 'NGN')
                        }
                        send_email(
                            app=current_app,
                            logger=current_app.logger,
                            to_email=form.email.data,
                            subject=subject,
                            template_name=config["template"],
                            data=email_data,
                            lang=session.get('lang', 'en')
                        )
                        current_app.logger.info(f"Email sent to {form.email.data} for session {session.get('sid', 'unknown')}", extra={'session_id': session.get('sid', 'unknown')})
                    except Exception as e:
                        current_app.logger.error(f"Failed to send email: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
                        flash(trans("general_email_action", default="Failed to send email"), "warning")

        user_records = db.net_worth_data.find(filter_criteria).sort('created_at', -1)
        if db.net_worth_data.count_documents(filter_criteria) == 0 and current_user.is_authenticated and current_user.email:
            user_records = db.net_worth_data.find({'email': current_user.email}).sort('created_at', -1)
        
        records_data = []
        for record in user_records:
            record_data = {
                'id': str(record.get('_id')),
                'user_id': record.get('user_id'),
                'session_id': record.get('session_id'),
                'first_name': record.get('first_name'),
                'email': record.get('email'),
                'send_email': record.get('send_email', False),
                'cash_savings': float(record.get('cash_savings', 0)),
                'cash_savings_formatted': format_currency(float(record.get('cash_savings', 0)), record.get('currency', 'NGN')),
                'investments': float(record.get('investments', 0)),
                'investments_formatted': format_currency(float(record.get('investments', 0)), record.get('currency', 'NGN')),
                'property': float(record.get('property', 0)),
                'property_formatted': format_currency(float(record.get('property', 0)), record.get('currency', 'NGN')),
                'loans': float(record.get('loans', 0)),
                'loans_formatted': format_currency(float(record.get('loans', 0)), record.get('currency', 'NGN')),
                'total_assets': float(record.get('total_assets', 0)),
                'total_assets_formatted': format_currency(float(record.get('total_assets', 0)), record.get('currency', 'NGN')),
                'total_liabilities': float(record.get('total_liabilities', 0)),
                'total_liabilities_formatted': format_currency(float(record.get('total_liabilities', 0)), record.get('currency', 'NGN')),
                'net_worth': float(record.get('net_worth', 0)),
                'net_worth_formatted': format_currency(float(record.get('net_worth', 0)), record.get('currency', 'NGN')),
                'badges': record.get('badges', []),
                'created_at': record.get('created_at').strftime('%b %d, %Y') if record.get('created_at') else None,
                'currency': record.get('currency', 'NGN')
            }
            records_data.append((record_data['id'], record_data))
        
        latest_record = records_data[0][1] if records_data else {
            'cash_savings': 0.0,
            'cash_savings_formatted': format_currency(0.0, 'NGN'),
            'investments': 0.0,
            'investments_formatted': format_currency(0.0, 'NGN'),
            'property': 0.0,
            'property_formatted': format_currency(0.0, 'NGN'),
            'loans': 0.0,
            'loans_formatted': format_currency(0.0, 'NGN'),
            'total_assets': 0.0,
            'total_assets_formatted': format_currency(0.0, 'NGN'),
            'total_liabilities': 0.0,
            'total_liabilities_formatted': format_currency(0.0, 'NGN'),
            'net_worth': 0.0,
            'net_worth_formatted': format_currency(0.0, 'NGN'),
            'badges': [],
            'created_at': None,
            'currency': 'NGN'
        }

        all_records = list(db.net_worth_data.find({'currency': 'NGN'}))
        all_net_worths = [float(record['net_worth']) for record in all_records if record.get('net_worth') is not None]
        total_users = len(all_net_worths)
        rank = 0
        average_net_worth = 0.0
        if all_net_worths:
            all_net_worths.sort(reverse=True)
            user_net_worth = float(latest_record['net_worth'])
            rank = sum(1 for nw in all_net_worths if nw > user_net_worth) + 1
            average_net_worth = sum(all_net_worths) / total_users if total_users else 0.0

        insights = []
        try:
            net_worth_float = float(latest_record['net_worth'])
            total_liabilities_float = float(latest_record['total_liabilities'])
            total_assets_float = float(latest_record['total_assets'])
            cash_savings_float = float(latest_record['cash_savings'])
            investments_float = float(latest_record['investments'])
            
            if net_worth_float != 0:
                if total_liabilities_float > total_assets_float * 0.5:
                    insights.append(trans("net_worth_insight_high_liabilities", default="Your liabilities are high relative to assets."))
                if cash_savings_float < total_assets_float * 0.1:
                    insights.append(trans("net_worth_insight_low_cash_savings", default="Consider increasing your cash savings."))
                if investments_float >= total_assets_float * 0.3:
                    insights.append(trans("net_worth_insight_strong_investment", default="Strong investment portfolio detected."))
                if net_worth_float <= 0:
                    insights.append(trans("net_worth_insight_negative_net_worth", default="Your net worth is negative; focus on reducing liabilities."))
                if total_users >= 5:
                    if rank <= total_users * 0.1:
                        insights.append(trans("net_worth_insight_top_10", default="You're in the top 10% of users!"))
                    elif rank <= total_users * 0.3:
                        insights.append(trans("net_worth_insight_top_30", default="You're in the top 30% of users."))
                    else:
                        insights.append(trans("net_worth_insight_below_30", default="Your net worth is below the top 30%. Keep improving!"))
                else:
                    insights.append(trans("net_worth_insight_not_enough_users", default="Not enough users for ranking comparison."))
        except (ValueError, TypeError) as e:
            current_app.logger.warning(f"Error parsing amounts for insights: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})

        cross_tool_insights = []
        filter_kwargs_health = {'user_id': current_user.id} if current_user.is_authenticated else {'session_id': session.get('sid', 'unknown')}
        health_data = db.financial_health_scores.find(filter_kwargs_health).sort('created_at', -1)
        health_data = list(health_data)
        if health_data and net_worth_float <= 0:
            latest_health = health_data[0]
            if latest_health.get('savings_rate', 0) > 0:
                cross_tool_insights.append(trans(
                    'net_worth_cross_tool_savings_rate',
                    default='Your financial health score indicates a positive savings rate of {rate}%, which could help improve your net worth.',
                    rate=f"{latest_health['savings_rate']:.2f}"
                ))

        current_app.logger.info(f"Rendering net worth main page with {len(records_data)} records for session {session.get('sid', 'unknown')}", extra={'session_id': session.get('sid', 'unknown')})
        return render_template(
            'personal/NETWORTH/net_worth_main.html',
            form=form,
            records=records_data,
            latest_record=latest_record,
            activities=activities,
            insights=insights,
            cross_tool_insights=cross_tool_insights,
            tips=[
                trans("net_worth_tip_track_ajo", default="Track your contributions to ajo or other savings groups."),
                trans("net_worth_tip_review_property", default="Review property valuations annually."),
                trans("net_worth_tip_pay_loans_early", default="Pay off high-interest loans early"),
                trans("net_worth_tip_diversify_investments", default="Diversify investments to reduce risk")
            ],
            rank=rank,
            total_users=total_users,
            average_net_worth=format_currency(average_net_worth, 'NGN'),
            tool_title=trans('net_worth_title', default='Net Worth Calculator')
        )

    except Exception as e:
        current_app.logger.error(f"Error in net_worth.main for session {session.get('sid', 'unknown')}: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
        flash(trans("net_worth_dashboard_load_error", default="Unable to load net worth dashboard. Please try again."), "danger")
        return render_template(
            'personal/NETWORTH/net_worth_main.html',
            form=form,
            records=[],
            latest_record={
                'cash_savings': 0.0,
                'cash_savings_formatted': format_currency(0.0, 'NGN'),
                'investments': 0.0,
                'investments_formatted': format_currency(0.0, 'NGN'),
                'property': 0.0,
                'property_formatted': format_currency(0.0, 'NGN'),
                'loans': 0.0,
                'loans_formatted': format_currency(0.0, 'NGN'),
                'total_assets': 0.0,
                'total_assets_formatted': format_currency(0.0, 'NGN'),
                'total_liabilities': 0.0,
                'total_liabilities_formatted': format_currency(0.0, 'NGN'),
                'net_worth': 0.0,
                'net_worth_formatted': format_currency(0.0, 'NGN'),
                'badges': [],
                'created_at': None,
                'currency': 'NGN'
            },
            activities=activities,
            insights=[],
            cross_tool_insights=[],
            tips=[
                trans("net_worth_tip_track_ajo", default="Track your contributions to ajo or other savings groups."),
                trans("net_worth_tip_review_property", default="Review property valuations annually"),
                trans("net_worth_tip_pay_loans_early", default="Pay off high-interest loans early"),
                trans("net_worth_tip_diversify_investments", default="Diversify investments to reduce risk")
            ],
            rank=0,
            total_users=0,
            average_net_worth=format_currency(0.0, 'NGN'),
            tool_title=trans('net_worth_title', default='Net Worth Calculator')
        )

@net_worth_bp.route('/summary')
@login_required
@requires_role(['personal', 'admin'])
def summary():
    """Return the latest net worth for the current user."""
    db = get_mongo_db()
    try:
        log_tool_usage(
            db=db,
            user_id=current_user.id if current_user.is_authenticated else None,
            session_id=session.get('sid', 'unknown'),
            action='summary_view'
        )
        
        filter_criteria = {} if is_admin() else {'user_id': current_user.id}
        net_worth_collection = db.net_worth_data
        
        latest_record = net_worth_collection.find(filter_criteria).sort('created_at', -1).limit(1)
        latest_records = list(latest_record)
        
        if not latest_records:
            current_app.logger.info(f"No net worth found for user {current_user.id}", extra={'session_id': session.get('sid', 'unknown')})
            return jsonify({'net_worth': format_currency(0.0, 'NGN'), 'currency': 'NGN'})
        
        net_worth = float(latest_records[0].get('net_worth', 0.0))
        currency = latest_records[0].get('currency', 'NGN')
        current_app.logger.info(f"Fetched net worth summary for user {current_user.id}: {net_worth} {currency}", extra={'session_id': session.get('sid', 'unknown')})
        return jsonify({'net_worth': format_currency(net_worth, currency=currency), 'currency': currency})
    except Exception as e:
        current_app.logger.error(f"Error in net_worth.summary: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
        return jsonify({'net_worth': format_currency(0.0, 'NGN'), 'currency': 'NGN'}), 500

@net_worth_bp.route('/unsubscribe/<email>')
@login_required
@custom_login_required
@requires_role(['personal', 'admin'])
def unsubscribe(email):
    """Unsubscribe user from net worth emails using MongoDB."""
    db = get_mongo_db()
    if 'sid' not in session:
        create_anonymous_session()
        current_app.logger.info(f"New anonymous session created with sid {session['sid']}", extra={'session_id': session.get('sid', 'unknown')})
    
    try:
        log_tool_usage(
            db=db,
            user_id=current_user.id if current_user.is_authenticated else None,
            session_id=session.get('sid', 'unknown'),
            action='unsubscribe'
        )
        
        filter_criteria = {'email': email} if is_admin() else {'email': email, 'user_id': current_user.id} if current_user.is_authenticated else {'email': email, 'session_id': session.get('sid', 'unknown')}
        
        net_worth_collection = db.net_worth_data
        existing_record = net_worth_collection.find_one(filter_criteria)
        if not existing_record:
            current_app.logger.warning(f"No matching email found for {email} to unsubscribe for session {session.get('sid', 'unknown')}", extra={'session_id': session.get('sid', 'unknown')})
            flash(trans("net_worth_unsubscribe_failed", default="Unable to find matching email or already unsubscribed"), "danger")
            return redirect(url_for('personal.index'))

        success = net_worth_collection.update_one(
            filter_criteria,
            {'$set': {'send_email': False}}
        )
        if success.modified_count > 0:
            current_app.logger.info(f"Successfully unsubscribed email {email} for session {session.get('sid', 'unknown')}", extra={'session_id': session.get('sid', 'unknown')})
            flash(trans("net_worth_unsubscribe_success", default="Successfully unsubscribed from emails"), "success")
        else:
            current_app.logger.warning(f"No emails updated for {email} during unsubscribe for session {session.get('sid', 'unknown')}", extra={'session_id': session.get('sid', 'unknown')})
            flash(trans("net_worth_unsubscribe_failed", default="Failed to unsubscribe. Email not found or already unsubscribed."), "danger")
        return redirect(url_for('personal.index'))
    except Exception as e:
        current_app.logger.error(f"Error in net_worth.unsubscribe: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
        flash(trans("net_worth_unsubscribe_error", default="Failed to process unsubscribe request"), "danger")
        return redirect(url_for('personal.index'))

@net_worth_bp.errorhandler(CSRFError)
def handle_csrf_error(e):
    """Handle CSRF errors with a user-friendly message."""
    current_app.logger.error(f"CSRF error on {request.path}: {e}", extra={'session_id': session.get('sid', 'unknown')})
    flash("Form submission failed due to missing security token. Please refresh and try again.", "error")
    return redirect(url_for('personal.index')), 400
