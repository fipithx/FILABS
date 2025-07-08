from flask import Blueprint, request, session, redirect, url_for, render_template, flash, current_app
from flask_wtf import FlaskForm
from flask_wtf.csrf import CSRFProtect, CSRFError
from wtforms import StringField, FloatField, SelectField, BooleanField, IntegerField, DateField
from wtforms.validators import DataRequired, NumberRange, Email, Optional
from flask_login import current_user, login_required
from mailersend_email import send_email, EMAIL_CONFIG
from datetime import datetime, date, timedelta
from translations import trans
from pymongo.errors import DuplicateKeyError
from flask import jsonify
from bson import ObjectId
from utils import requires_role, is_admin, get_mongo_db, limiter
from models import log_tool_usage

bill_bp = Blueprint('bill', __name__, template_folder='templates/personal/BILL')

csrf = CSRFProtect()

def strip_commas(value):
    """Remove commas from string values for numerical fields."""
    if isinstance(value, str):
        return value.replace(',', '')
    return value

def calculate_next_due_date(due_date, frequency):
    """Calculate the next due date based on frequency."""
    if frequency == 'weekly':
        return due_date + timedelta(days=7)
    elif frequency == 'monthly':
        return due_date + timedelta(days=30)
    elif frequency == 'quarterly':
        return due_date + timedelta(days=90)
    return due_date

class BillForm(FlaskForm):
    first_name = StringField(trans('general_first_name', default='First Name'), validators=[DataRequired()])
    email = StringField(trans('general_email', default='Email'), validators=[DataRequired(), Email()])
    bill_name = StringField(trans('bill_bill_name', default='Bill Name'), validators=[DataRequired()])
    amount = FloatField(trans('bill_amount', default='Amount'), filters=[strip_commas], validators=[DataRequired(), NumberRange(min=0, max=10000000000)])
    due_date = DateField(trans('bill_due_date', default='Due Date'), validators=[DataRequired()])
    frequency = SelectField(trans('bill_frequency', default='Frequency'), choices=[
        ('one-time', trans('bill_frequency_one_time', default='One-Time')),
        ('weekly', trans('bill_frequency_weekly', default='Weekly')),
        ('monthly', trans('bill_frequency_monthly', default='Monthly')),
        ('quarterly', trans('bill_frequency_quarterly', default='Quarterly'))
    ], default='one-time', validators=[DataRequired()])
    category = SelectField(trans('general_category', default='Category'), choices=[
        ('utilities', trans('bill_category_utilities', default='Utilities')),
        ('rent', trans('bill_category_rent', default='Rent')),
        ('data_internet', trans('bill_category_data_internet', default='Data/Internet')),
        ('ajo_esusu_adashe', trans('bill_category_ajo_esusu_adashe', default='Ajo/Esusu/Adashe')),
        ('food', trans('bill_category_food', default='Food')),
        ('transport', trans('bill_category_transport', default='Transport')),
        ('clothing', trans('bill_category_clothing', default='Clothing')),
        ('education', trans('bill_category_education', default='Education')),
        ('healthcare', trans('bill_category_healthcare', default='Healthcare')),
        ('entertainment', trans('bill_category_entertainment', default='Entertainment')),
        ('airtime', trans('bill_category_airtime', default='Airtime')),
        ('school_fees', trans('bill_category_school_fees', default='School Fees')),
        ('savings_investments', trans('bill_category_savings_investments', default='Savings/Investments')),
        ('other', trans('general_other', default='Other'))
    ], default='utilities', validators=[DataRequired()])
    status = SelectField(trans('bill_status', default='Status'), choices=[
        ('unpaid', trans('bill_status_unpaid', default='Unpaid')),
        ('paid', trans('bill_status_paid', default='Paid')),
        ('pending', trans('bill_status_pending', default='Pending')),
        ('overdue', trans('bill_status_overdue', default='Overdue'))
    ], default='unpaid', validators=[DataRequired()])
    send_email = BooleanField(trans('general_send_email', default='Send Email Reminders'), default=False)
    reminder_days = IntegerField(trans('bill_reminder_days', default='Reminder Days'), default=7, validators=[Optional(), NumberRange(min=1, max=30)])

class EditBillForm(FlaskForm):
    frequency = SelectField(trans('bill_frequency', default='Frequency'), choices=[
        ('one-time', trans('bill_frequency_one_time', default='One-Time')),
        ('weekly', trans('bill_frequency_weekly', default='Weekly')),
        ('monthly', trans('bill_frequency_monthly', default='Monthly')),
        ('quarterly', trans('bill_frequency_quarterly', default='Quarterly'))
    ], default='one-time', validators=[DataRequired()])
    category = SelectField(trans('general_category', default='Category'), choices=[
        ('utilities', trans('bill_category_utilities', default='Utilities')),
        ('rent', trans('bill_category_rent', default='Rent')),
        ('data_internet', trans('bill_category_data_internet', default='Data/Internet')),
        ('ajo_esusu_adashe', trans('bill_category_ajo_esusu_adashe', default='Ajo/Esusu/Adashe')),
        ('food', trans('bill_category_food', default='Food')),
        ('transport', trans('bill_category_transport', default='Transport')),
        ('clothing', trans('bill_category_clothing', default='Clothing')),
        ('education', trans('bill_category_education', default='Education')),
        ('healthcare', trans('bill_category_healthcare', default='Healthcare')),
        ('entertainment', trans('bill_category_entertainment', default='Entertainment')),
        ('airtime', trans('bill_category_airtime', default='Airtime')),
        ('school_fees', trans('bill_category_school_fees', default='School Fees')),
        ('savings_investments', trans('bill_category_savings_investments', default='Savings/Investments')),
        ('other', trans('general_other', default='Other'))
    ], default='utilities', validators=[DataRequired()])
    status = SelectField(trans('bill_status', default='Status'), choices=[
        ('unpaid', trans('bill_status_unpaid', default='Unpaid')),
        ('paid', trans('bill_status_paid', default='Paid')),
        ('pending', trans('bill_status_pending', default='Pending')),
        ('overdue', trans('bill_status_overdue', default='Overdue'))
    ], default='unpaid', validators=[DataRequired()])
    send_email = BooleanField(trans('general_send_email', default='Send Email Reminders'), default=False)
    reminder_days = IntegerField(trans('bill_reminder_days', default='Reminder Days'), default=7, validators=[Optional(), NumberRange(min=1, max=30)])

@bill_bp.route('/main', methods=['GET', 'POST'])
@login_required
@requires_role(['personal', 'admin'])
def main():
    """Main bill management interface with tabbed layout."""
    form = BillForm(data={
        'email': current_user.email if current_user.is_authenticated else '',
        'first_name': current_user.get_first_name() if current_user.is_authenticated else ''
    })
    try:
        log_tool_usage(
            get_mongo_db(),
            tool_name='bill',
            user_id=current_user.id,
            session_id=session.get('sid', 'unknown'),
            action='main_view'
        )
    except Exception as e:
        current_app.logger.error(f"Failed to log tool usage: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
        flash(trans('bill_log_error', default='Error logging bill activity. Please try again.'), 'warning')
    
    tips = [
        trans('bill_tip_pay_early', default='Pay bills early to avoid penalties.'),
        trans('bill_tip_energy_efficient', default='Use energy-efficient appliances to reduce utility bills.'),
        trans('bill_tip_plan_monthly', default='Plan monthly expenses to manage cash flow.'),
        trans('bill_tip_ajo_reminders', default='Set reminders for ajo contributions.'),
        trans('bill_tip_data_topup', default='Schedule data top-ups to avoid service interruptions.')
    ]
    try:
        filter_kwargs = {} if is_admin() else {'user_id': current_user.id}
        bills_collection = get_mongo_db().bills
        if request.method == 'POST':
            action = request.form.get('action')
            if action == 'add_bill' and form.validate_on_submit():
                try:
                    log_tool_usage(
                        get_mongo_db(),
                        tool_name='bill',
                        user_id=current_user.id,
                        session_id=session.get('sid', 'unknown'),
                        action='add_bill'
                    )
                except Exception as e:
                    current_app.logger.error(f"Failed to log bill addition: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
                    flash(trans('bill_log_error', default='Error logging bill addition. Continuing with submission.'), 'warning')
                
                due_date = form.due_date.data
                if due_date < date.today():
                    flash(trans('bill_due_date_future_validation', default='Due date must be today or in the future.'), 'danger')
                    return redirect(url_for('bill.main'))
                status = form.status.data
                if status not in ['paid', 'pending'] and due_date < date.today():
                    status = 'overdue'
                bill_data = {
                    '_id': ObjectId(),
                    'user_id': current_user.id,
                    'user_email': form.email.data,
                    'first_name': form.first_name.data,
                    'bill_name': form.bill_name.data,
                    'amount': float(form.amount.data),
                    'due_date': due_date.isoformat(),
                    'frequency': form.frequency.data,
                    'category': form.category.data,
                    'status': status,
                    'send_email': form.send_email.data,
                    'reminder_days': form.reminder_days.data if form.send_email.data else None,
                    'created_at': datetime.utcnow()
                }
                bills_collection.insert_one(bill_data)
                current_app.logger.info(f"Bill added successfully for {form.email.data}: {bill_data['bill_name']}")
                flash(trans('bill_added_success', default='Bill added successfully!'), 'success')
                if form.send_email.data and form.email.data:
                    try:
                        config = EMAIL_CONFIG['bill_reminder']
                        subject = trans(config['subject_key'], default='Your Bill Reminder')
                        send_email(
                            app=current_app,
                            logger=current_app.logger,
                            to_email=form.email.data,
                            subject=subject,
                            template_name=config['template'],
                            data={
                                'first_name': form.first_name.data,
                                'bills': [bill_data],
                                'cta_url': url_for('bill.main', _external=True),
                                'unsubscribe_url': url_for('bill.unsubscribe', email=form.email.data, _external=True)
                            },
                            lang=session.get('lang', 'en')
                        )
                        current_app.logger.info(f"Email sent to {form.email.data}")
                    except Exception as e:
                        current_app.logger.error(f"Failed to send email: {str(e)}")
                        flash(trans('general_email_send_failed', default='Failed to send email.'), 'warning')
            elif action in ['update_bill', 'delete_bill', 'toggle_status']:
                bill_id = request.form.get('bill_id')
                bill = bills_collection.find_one({'_id': ObjectId(bill_id), **filter_kwargs})
                if not bill:
                    current_app.logger.warning(f"Bill {bill_id} not found for update/delete/toggle")
                    flash(trans('bill_not_found', default='Bill not found.'), 'danger')
                    return redirect(url_for('bill.main'))
                if action == 'update_bill':
                    edit_form = EditBillForm(formdata=request.form, bill=bill)
                    if edit_form.validate():
                        update_data = {
                            'frequency': edit_form.frequency.data,
                            'category': edit_form.category.data,
                            'status': edit_form.status.data,
                            'send_email': edit_form.send_email.data,
                            'reminder_days': edit_form.reminder_days.data if edit_form.send_email.data else None,
                            'updated_at': datetime.utcnow()
                        }
                        bills_collection.update_one({'_id': ObjectId(bill_id), **filter_kwargs}, {'$set': update_data})
                        current_app.logger.info(f"Bill {bill_id} updated successfully")
                        flash(trans('bill_updated_success', default='Bill updated successfully!'), 'success')
                    else:
                        current_app.logger.error(f"Edit form validation failed: {edit_form.errors}")
                        flash(trans('bill_update_failed', default='Failed to update bill.'), 'danger')
                elif action == 'delete_bill':
                    bills_collection.delete_one({'_id': ObjectId(bill_id), **filter_kwargs})
                    current_app.logger.info(f"Bill {bill_id} deleted successfully")
                    flash(trans('bill_deleted_success', default='Bill deleted successfully!'), 'success')
                elif action == 'toggle_status':
                    new_status = 'paid' if bill['status'] == 'unpaid' else 'unpaid'
                    bills_collection.update_one({'_id': ObjectId(bill_id), **filter_kwargs}, {'$set': {'status': new_status, 'updated_at': datetime.utcnow()}})
                    if new_status == 'paid' and bill['frequency'] != 'one-time':
                        try:
                            due_date = datetime.strptime(bill['due_date'], '%Y-%m-%d').date()
                            new_due_date = calculate_next_due_date(due_date, bill['frequency'])
                            new_bill = bill.copy()
                            new_bill['_id'] = ObjectId()
                            new_bill['due_date'] = new_due_date.isoformat()
                            new_bill['status'] = 'unpaid'
                            new_bill['created_at'] = datetime.utcnow()
                            bills_collection.insert_one(new_bill)
                            current_app.logger.info(f"Recurring bill created for {bill['bill_name']}")
                            flash(trans('bill_new_recurring_bill_success', default='New recurring bill created for {bill_name}.').format(bill_name=bill['bill_name']), 'success')
                        except Exception as e:
                            current_app.logger.error(f"Error creating recurring bill: {str(e)}")
                    current_app.logger.info(f"Bill {bill_id} status toggled to {new_status}")
                    flash(trans('bill_status_toggled_success', default='Bill status toggled successfully!'), 'success')
        bills = bills_collection.find(filter_kwargs)
        bills_data = []
        edit_forms = {}
        for bill in bills:
            bill_id = str(bill['_id'])
            try:
                bill['due_date'] = datetime.strptime(bill['due_date'], '%Y-%m-%d').date()
            except (ValueError, TypeError):
                current_app.logger.warning(f"Invalid due_date for bill {bill_id}: {bill.get('due_date')}")
                bill['due_date'] = date.today()
            edit_form = EditBillForm(bill=bill)
            bills_data.append((bill_id, bill, edit_form))
            edit_forms[bill_id] = edit_form
        paid_count = unpaid_count = overdue_count = pending_count = 0
        total_paid = total_unpaid = total_overdue = total_bills = 0.0
        categories = {}
        due_today = due_week = due_month = upcoming_bills = []
        today = date.today()
        for bill_id, bill, edit_form in bills_data:
            try:
                bill_amount = float(bill['amount'])
                total_bills += bill_amount
                cat = bill['category']
                categories[cat] = categories.get(cat, 0) + bill_amount
                if bill['status'] == 'paid':
                    paid_count += 1
                    total_paid += bill_amount
                elif bill['status'] == 'unpaid':
                    unpaid_count += 1
                    total_unpaid += bill_amount
                elif bill['status'] == 'overdue':
                    overdue_count += 1
                    total_overdue += bill_amount
                elif bill['status'] == 'pending':
                    pending_count += 1
                bill_due_date = bill['due_date']
                if bill_due_date == today:
                    due_today.append((bill_id, bill, edit_form))
                if today <= bill_due_date <= (today + timedelta(days=7)):
                    due_week.append((bill_id, bill, edit_form))
                if today <= bill_due_date <= (today + timedelta(days=30)):
                    due_month.append((bill_id, bill, edit_form))
                if today < bill_due_date:
                    upcoming_bills.append((bill_id, bill, edit_form))
            except (ValueError, TypeError):
                current_app.logger.warning(f"Invalid amount for bill {bill_id}: {bill.get('amount')}")
                continue
        return render_template(
            'personal/BILL/bill_main.html',
            form=form,
            bills_data=bills_data,
            edit_forms=edit_forms,
            paid_count=paid_count,
            unpaid_count=unpaid_count,
            overdue_count=overdue_count,
            pending_count=pending_count,
            total_paid=total_paid,
            total_unpaid=total_unpaid,
            total_overdue=total_overdue,
            total_bills=total_bills,
            categories=categories,
            due_today=due_today,
            due_week=due_week,
            due_month=due_month,
            upcoming_bills=upcoming_bills,
            tips=tips,
            tool_title=trans('bill_title', default='Bill Manager')
        )
    except Exception as e:
        current_app.logger.error(f"Error in bill.main: {str(e)}")
        flash(trans('bill_dashboard_load_error', default='Error loading bill dashboard.'), 'danger')
        return render_template(
            'personal/BILL/bill_main.html',
            form=form,
            bills_data=[],
            edit_forms={},
            paid_count=0,
            unpaid_count=0,
            overdue_count=0,
            pending_count=0,
            total_paid=0.0,
            total_unpaid=0.0,
            total_overdue=0.0,
            total_bills=0.0,
            categories={},
            due_today=[],
            due_week=[],
            due_month=[],
            upcoming_bills=[],
            tips=tips,
            tool_title=trans('bill_title', default='Bill Manager')
        ), 500

@bill_bp.route('/summary')
@login_required
@requires_role(['personal', 'admin'])
def summary():
    """Return summary of upcoming bills for the current user."""
    try:
        filter_kwargs = {} if is_admin() else {'user_id': current_user.id}
        bills_collection = get_mongo_db().bills
        today = date.today()
        pipeline = [
            {'$match': {**filter_kwargs, 'status': {'$ne': 'paid'}, 'due_date': {'$gte': today.isoformat()}}},
            {'$group': {'_id': None, 'totalUpcomingBills': {'$sum': '$amount'}}}
        ]
        result = list(bills_collection.aggregate(pipeline))
        total_upcoming_bills = result[0]['totalUpcomingBills'] if result else 0.0
        current_app.logger.info(f"Fetched bill summary for user {current_user.id}: {total_upcoming_bills}")
        return jsonify({'totalUpcomingBills': total_upcoming_bills})
    except Exception as e:
        current_app.logger.error(f"Error in bill.summary: {str(e)}")
        return jsonify({'totalUpcomingBills': 0.0}), 500

@bill_bp.route('/unsubscribe/<email>')
@login_required
@requires_role(['personal', 'admin'])
def unsubscribe(email):
    """Unsubscribe user from bill email notifications."""
    try:
        try:
            log_tool_usage(
                get_mongo_db(),
                tool_name='bill',
                user_id=current_user.id,
                session_id=session.get('sid', 'unknown'),
                action='unsubscribe'
            )
        except Exception as e:
            current_app.logger.error(f"Failed to log unsubscribe action: {str(e)}", extra={'session_id': session.get('sid', 'unknown')})
            flash(trans('bill_log_error', default='Error logging unsubscribe action. Continuing with unsubscription.'), 'warning')
        
        filter_criteria = {'user_email': email, 'user_id': current_user.id} if not is_admin() else {'user_email': email}
        bills_collection = get_mongo_db().bills
        result = bills_collection.update_many(filter_criteria, {'$set': {'send_email': False}})
        if result.modified_count > 0:
            current_app.logger.info(f"Successfully unsubscribed email {email}")
            flash(trans('bill_unsubscribe_success', default='Successfully unsubscribed from bill emails.'), 'success')
        else:
            current_app.logger.warning(f"No records updated for email {email} during unsubscribe")
            flash(trans('bill_unsubscribe_failed', default='No matching email found or already unsubscribed.'), 'danger')
        return redirect(url_for('bill.main'))
    except Exception as e:
        current_app.logger.error(f"Error in bill.unsubscribe: {str(e)}")
        flash(trans('bill_unsubscribe_error', default='Error processing unsubscribe request.'), 'danger')
        return redirect(url_for('personal.index'))
