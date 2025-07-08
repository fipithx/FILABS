from flask import Blueprint, jsonify, current_app, redirect, url_for, flash, render_template, request, session
from flask_wtf import FlaskForm
from flask_wtf.csrf import CSRFProtect, CSRFError
from wtforms import StringField, BooleanField, SubmitField, FloatField
from wtforms.validators import DataRequired, NumberRange, Optional, Email, ValidationError
from flask_login import current_user, login_required
from translations import trans
from mailersend_email import send_email, EMAIL_CONFIG
from datetime import datetime
from bson import ObjectId
from models import log_tool_usage
from session_utils import create_anonymous_session
from utils import requires_role, is_admin, get_mongo_db, format_currency, limiter

net_worth_bp = Blueprint(
    'net_worth',
    __name__,
    template_folder='templates/personal/NETWORTH',
    url_prefix='/NETWORTH'
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
        try:
            log_tool_usage(
                tool_name='net_worth',
                user_id=current_user.id if current_user.is_authenticated else None,
                session_id=session['sid'],
                action='main_view',
                mongo=get_mongo_db()
            )
        except Exception as e:
            current_app.logger.error(f"Failed to log tool usage: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
            flash(trans('net_worth_log_error', default='Error logging net worth activity. Please try again.'), 'warning')
        
        filter_criteria = {} if is_admin() else {'user_id': current_user.id} if current_user.is_authenticated else {'session_id': session['sid']}
        
        if request.method == 'POST':
            action = request.form.get('action')
            
            if action == 'calculate_net_worth' and form.validate_on_submit():
                try:
                    log_tool_usage(
                        tool_name='net_worth',
                        user_id=current_user.id if current_user.is_authenticated else None,
                        session_id=session['sid'],
                        action='calculate_net_worth',
                        mongo=get_mongo_db()
                    )
                except Exception as e:
                    current_app.logger.error(f"Failed to log calculate_net_worth action: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
                    flash(trans('net_worth_log_error', default='Error logging net worth calculation. Continuing with calculation.'), 'warning')
                
                cash_savings = form.cash_savings.data
                investments = form.investments.data
                property = form.property.data
                loans = form.loans.data or 0

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
                    get_mongo_db().net_worth_data.insert_one(net_worth_record)
                    current_app.logger.info(f"Successfully saved record {net_worth_record['_id']} for session {session['sid']}", extra={'session_id': session['sid']})
                    flash(trans("net_worth_success", default="Net worth calculated successfully"), "success")
                except Exception as e:
                    current_app.logger.error(f"Failed to save net worth data to MongoDB: {str(e)}", extra={'session_id': session['sid']})
                    flash(trans("net_worth_storage_error", default="Error saving net worth data."), "danger")
                    return redirect(url_for('net_worth.main'))

                if form.send_email.data and form.email.data:
                    try:
                        config = EMAIL_CONFIG["net_worth"]
                        subject = trans(config["subject_key"], default='Your Net Worth Summary')
                        template = config["template"]
                        send_email(
                            app=current_app,
                            logger=current_app.logger,
                            to_email=form.email.data,
                            subject=subject,
                            template_name=template,
                            data={
                                "first_name": net_worth_record['first_name'],
                                "cash_savings": format_currency(net_worth_record['cash_savings']),
                                "investments": format_currency(net_worth_record['investments']),
                                "property": format_currency(net_worth_record['property']),
                                "loans": format_currency(net_worth_record['loans']),
                                "total_assets": format_currency(net_worth_record['total_assets']),
                                "total_liabilities": format_currency(net_worth_record['total_liabilities']),
                                "net_worth": format_currency(net_worth_record['net_worth']),
                                "badges": net_worth_record['badges'],
                                "created_at": net_worth_record['created_at'].strftime('%Y-%m-%d'),
                                "cta_url": url_for('net_worth.main', _external=True),
                                "unsubscribe_url": url_for('net_worth.unsubscribe', email=form.email.data, _external=True),
                                "currency": net_worth_record['currency']
                            },
                            lang=session.get('lang', 'en')
                        )
                        current_app.logger.info(f"Email sent to {form.email.data} for session {session['sid']}", extra={'session_id': session['sid']})
                    except Exception as e:
                        current_app.logger.error(f"Failed to send email: {str(e)}", extra={'session_id': session['sid']})
                        flash(trans("general_email_send_failed", default="Failed to send email"), "warning")

        user_records = get_mongo_db().net_worth_data.find(filter_criteria).sort('created_at', -1)
        
        if user_records.count() == 0 and current_user.is_authenticated and current_user.email:
            user_records = get_mongo_db().net_worth_data.find({'email': current_user.email}).sort('created_at', -1)
        
        records = []
        for record in user_records:
            record_data = {
                'id': str(record['_id']),
                'user_id': record.get('user_id'),
                'session_id': record.get('session_id'),
                'first_name': record.get('first_name'),
                'email': record.get('email'),
                'send_email': record.get('send_email', False),
                'cash_savings': format_currency(record.get('cash_savings', 0)),
                'investments': format_currency(record.get('investments', 0)),
                'property': format_currency(record.get('property', 0)),
                'loans': format_currency(record.get('loans', 0)),
                'total_assets': format_currency(record.get('total_assets', 0)),
                'total_liabilities': format_currency(record.get('total_liabilities', 0)),
                'net_worth': format_currency(record.get('net_worth', 0)),
                'badges': record.get('badges', []),
                'created_at': record.get('created_at').strftime('%Y-%m-%d') if record.get('created_at') else 'N/A',
                'currency': record.get('currency', 'NGN')
            }
            records.append((record_data['id'], record_data))
        
        latest_record = records[0][1] if records else {
            'cash_savings': format_currency(0),
            'investments': format_currency(0),
            'property': format_currency(0),
            'loans': format_currency(0),
            'total_assets': format_currency(0),
            'total_liabilities': format_currency(0),
            'net_worth': format_currency(0),
            'badges': [],
            'created_at': 'N/A',
            'currency': 'NGN'
        }

        all_records = list(get_mongo_db().net_worth_data.find({'currency': 'NGN'}))
        all_net_worths = [record['net_worth'] for record in all_records if record.get('net_worth') is not None]
        total_users = len(all_net_worths)
        rank = 0
        average_net_worth = 0
        if all_net_worths:
            all_net_worths.sort(reverse=True)
            user_net_worth = float(latest_record['net_worth'].replace(',', '')) if latest_record['net_worth'] != format_currency(0) else 0
            rank = sum(1 for nw in all_net_worths if nw > user_net_worth) + 1
            average_net_worth = sum(all_net_worths) / total_users

        insights = []
        cross_tool_insights = []
        if latest_record and float(latest_record['net_worth'].replace(',', '')) != 0:
            if float(latest_record['total_liabilities'].replace(',', '')) > float(latest_record['total_assets'].replace(',', '')) * 0.5:
                insights.append(trans("net_worth_insight_high_loans", default="Your liabilities are high relative to assets."))
            if float(latest_record['cash_savings'].replace(',', '')) < float(latest_record['total_assets'].replace(',', '')) * 0.1:
                insights.append(trans("net_worth_insight_low_cash", default="Consider increasing cash savings."))
            if float(latest_record['investments'].replace(',', '')) >= float(latest_record['total_assets'].replace(',', '')) * 0.3:
                insights.append(trans("net_worth_insight_strong_investments", default="Strong investment portfolio detected."))
            if float(latest_record['net_worth'].replace(',', '')) <= 0:
                insights.append(trans("net_worth_insight_negative_net_worth", default="Your net worth is negative; focus on reducing liabilities."))
            if total_users >= 5:
                if rank <= total_users * 0.1:
                    insights.append(trans("net_worth_insight_top_10", default="You are in the top 10% of users!"))
                elif rank <= total_users * 0.3:
                    insights.append(trans("net_worth_insight_top_30", default="You are in the top 30% of users."))
                else:
                    insights.append(trans("net_worth_insight_below_30", default="Your net worth is below the top 30%. Keep improving!"))
            else:
                insights.append(trans("net_worth_insight_not_enough_users", default="Not enough users for ranking comparison."))

        filter_kwargs_health = {'user_id': current_user.id} if current_user.is_authenticated else {'session_id': session['sid']}
        health_data = get_mongo_db().financial_health_scores.find(filter_kwargs_health).sort('created_at', -1)
        health_data = list(health_data)
        if health_data and latest_record and float(latest_record['net_worth'].replace(',', '')) <= 0:
            latest_health = health_data[0]
            if latest_health.get('savings_rate', 0) > 0:
                cross_tool_insights.append(trans(
                    'net_worth_cross_tool_savings_rate',
                    default='Your financial health score indicates a positive savings rate of {rate}%, which can help improve your net worth.',
                    rate=f"{latest_health['savings_rate']:.2f}"
                ))

        current_app.logger.info(f"Rendering net worth main page with {len(records)} records for session {session['sid']}", extra={'session_id': session['sid']})
        return render_template(
            'personal/NETWORTH/net_worth_main.html',
            form=form,
            records=records,
            latest_record=latest_record,
            insights=insights,
            cross_tool_insights=cross_tool_insights,
            tips=[
                trans("net_worth_tip_track_ajo", default="Track your contributions to ajo or other savings groups."),
                trans("net_worth_tip_review_property", default="Review property valuations annually."),
                trans("net_worth_tip_pay_loans_early", default="Pay off high-interest loans early."),
                trans("net_worth_tip_diversify_investments", default="Diversify investments to reduce risk.")
            ],
            rank=rank,
            total_users=total_users,
            average_net_worth=format_currency(average_net_worth),
            tool_title=trans('net_worth_title', default='Net Worth Calculator')
        )

    except Exception as e:
        current_app.logger.error(f"Error in net_worth.main for session {session.get('sid', 'unknown')}: {str(e)}", extra={'session_id': session['sid']})
        flash(trans("net_worth_dashboard_load_error", default="Error loading net worth dashboard"), "danger")
        return render_template(
            'personal/NETWORTH/net_worth_main.html',
            form=form,
            records=[],
            latest_record={
                'cash_savings': format_currency(0),
                'investments': format_currency(0),
                'property': format_currency(0),
                'loans': format_currency(0),
                'total_assets': format_currency(0),
                'total_liabilities': format_currency(0),
                'net_worth': format_currency(0),
                'badges': [],
                'created_at': 'N/A',
                'currency': 'NGN'
            },
            insights=[],
            cross_tool_insights=[],
            tips=[
                trans("net_worth_tip_track_ajo", default="Track your contributions to ajo or other savings groups."),
                trans("net_worth_tip_review_property", default="Review property valuations annually."),
                trans("net_worth_tip_pay_loans_early", default="Pay off high-interest loans early."),
                trans("net_worth_tip_diversify_investments", default="Diversify investments to reduce risk.")
            ],
            rank=0,
            total_users=0,
            average_net_worth=format_currency(0),
            tool_title=trans('net_worth_title', default='Net Worth Calculator')
        ), 500

@net_worth_bp.route('/summary')
@login_required
@requires_role(['personal', 'admin'])
def summary():
    """Return the latest net worth for the current user."""
    try:
        try:
            log_tool_usage(
                tool_name='net_worth',
                user_id=current_user.id if current_user.is_authenticated else None,
                session_id=session.get('sid', 'unknown'),
                action='summary_view',
                mongo=get_mongo_db()
            )
        except Exception as e:
            current_app.logger.error(f"Failed to log summary action: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
            flash(trans('net_worth_log_error', default='Error logging summary view. Continuing with summary retrieval.'), 'warning')
        
        filter_criteria = {} if is_admin() else {'user_id': current_user.id}
        net_worth_collection = get_mongo_db().net_worth_data
        
        latest_record = net_worth_collection.find(filter_criteria).sort('created_at', -1).limit(1)
        latest_record = list(latest_record)
        
        if not latest_record:
            current_app.logger.info(f"No net worth record found for user {current_user.id}", extra={'session_id': session.get('sid', 'unknown')})
            return jsonify({'netWorth': format_currency(0.0), 'currency': 'NGN'})
        
        net_worth = latest_record[0].get('net_worth', 0.0)
        currency = latest_record[0].get('currency', 'NGN')
        current_app.logger.info(f"Fetched net worth summary for user {current_user.id}: {net_worth} {currency}", extra={'session_id': session.get('sid', 'unknown')})
        return jsonify({'netWorth': format_currency(net_worth), 'currency': currency})
    except Exception as e:
        current_app.logger.error(f"Error in net_worth.summary: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
        return jsonify({'netWorth': format_currency(0.0), 'currency': 'NGN'}), 500

@net_worth_bp.route('/unsubscribe/<email>')
@custom_login_required
@requires_role(['personal', 'admin'])
def unsubscribe(email):
    """Unsubscribe user from net worth emails using MongoDB."""
    if 'sid' not in session:
        create_anonymous_session()
        current_app.logger.debug(f"New anonymous session created with sid: {session['sid']}", extra={'session_id': session['sid']})
    session.permanent = True
    session.modified = True
    
    try:
        try:
            log_tool_usage(
                tool_name='net_worth',
                user_id=current_user.id if current_user.is_authenticated else None,
                session_id=session['sid'],
                action='unsubscribe',
                mongo=get_mongo_db()
            )
        except Exception as e:
            current_app.logger.error(f"Failed to log unsubscribe action: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
            flash(trans('net_worth_log_error', default='Error logging unsubscribe action. Continuing with unsubscription.'), 'warning')
        
        filter_criteria = {'email': email} if is_admin() else {'email': email, 'user_id': current_user.id} if current_user.is_authenticated else {'email': email, 'session_id': session['sid']}
        
        existing_record = get_mongo_db().net_worth_data.find_one(filter_criteria)
        if not existing_record:
            current_app.logger.warning(f"No matching record found for email {email} to unsubscribe for session {session['sid']}", extra={'session_id': session['sid']})
            flash(trans("net_worth_unsubscribe_failed", default="No matching email found or already unsubscribed"), "danger")
            return redirect(url_for('personal.index'))

        result = get_mongo_db().net_worth_data.update_many(
            filter_criteria,
            {'$set': {'send_email': False}}
        )
        if result.modified_count > 0:
            current_app.logger.info(f"Successfully unsubscribed email {email} for session {session['sid']}", extra={'session_id': session['sid']})
            flash(trans("net_worth_unsubscribed_success", default="Successfully unsubscribed from emails"), "success")
        else:
            current_app.logger.warning(f"No records updated for email {email} during unsubscribe for session {session['sid']}", extra={'session_id': session['sid']})
            flash(trans("net_worth_unsubscribe_failed", default="Failed to unsubscribe. Email not found or already unsubscribed."), "danger")
        return redirect(url_for('personal.index'))
    except Exception as e:
        current_app.logger.error(f"Error in net_worth.unsubscribe for session {session.get('sid', 'unknown')}: {str(e)}", extra={'session_id': session['sid']})
        flash(trans("net_worth_unsubscribe_error", default="Error processing unsubscribe request"), "danger")
        return redirect(url_for('personal.index'))

@net_worth_bp.errorhandler(CSRFError)
def handle_csrf_error(e):
    """Handle CSRF errors with user-friendly message."""
    current_app.logger.error(f"CSRF error on {request.path}: {e.description}", extra={'session_id': session.get('sid', 'unknown')})
    flash(trans("net_worth_csrf_error", default="Form submission failed due to a missing security token. Please refresh and try again."), "danger")
    return redirect(url_for('personal.index')), 400
