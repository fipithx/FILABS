from flask import Blueprint, render_template, Response, flash, request, session
from flask_login import login_required, current_user
from translations import trans
import utils
from bson import ObjectId
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import inch
from io import BytesIO
from flask_wtf import FlaskForm
from wtforms import DateField, StringField, SubmitField, SelectField
from wtforms.validators import Optional
import csv
import logging

logger = logging.getLogger(__name__)

reports_bp = Blueprint('reports', __name__, url_prefix='/reports')

class ReportForm(FlaskForm):
    start_date = DateField(trans('reports_start_date', default='Start Date'), validators=[Optional()])
    end_date = DateField(trans('reports_end_date', default='End Date'), validators=[Optional()])
    category = StringField(trans('general_category', default='Category'), validators=[Optional()])
    submit = SubmitField(trans('reports_generate_report', default='Generate Report'))

class InventoryReportForm(FlaskForm):
    item_name = StringField(trans('inventory_item_name', default='Item Name'), validators=[Optional()])
    submit = SubmitField(trans('reports_generate_report', default='Generate Report'))

class CustomerReportForm(FlaskForm):
    role = SelectField('User Role', choices=[('', 'All'), ('personal', 'Personal'), ('trader', 'Trader'), ('agent', 'Agent'), ('admin', 'Admin')], validators=[Optional()])
    format = SelectField('Format', choices=[('html', 'HTML'), ('pdf', 'PDF'), ('csv', 'CSV')], default='html')
    submit = SubmitField('Generate Report')

def to_dict_financial_health(record):
    if not record:
        return {'score': None, 'status': None}
    return {
        'score': record.get('score'),
        'status': record.get('status'),
        'debt_to_income': record.get('debt_to_income'),
        'savings_rate': record.get('savings_rate'),
        'interest_burden': record.get('interest_burden'),
        'badges': record.get('badges', []),
        'created_at': record.get('created_at')
    }

def to_dict_budget(record):
    if not record:
        return {'surplus_deficit': None, 'savings_goal': None}
    return {
        'income': record.get('income', 0),
        'fixed_expenses': record.get('fixed_expenses', 0),
        'variable_expenses': record.get('variable_expenses', 0),
        'savings_goal': record.get('savings_goal', 0),
        'surplus_deficit': record.get('surplus_deficit', 0),
        'housing': record.get('housing', 0),
        'food': record.get('food', 0),
        'transport': record.get('transport', 0),
        'dependents': record.get('dependents', 0),
        'miscellaneous': record.get('miscellaneous', 0),
        'others': record.get('others', 0),
        'created_at': record.get('created_at')
    }

def to_dict_bill(record):
    if not record:
        return {'amount': None, 'status': None}
    return {
        'id': str(record.get('_id', '')),
        'bill_name': record.get('bill_name', ''),
        'amount': record.get('amount', 0),
        'due_date': record.get('due_date', ''),
        'frequency': record.get('frequency', ''),
        'category': record.get('category', ''),
        'status': record.get('status', ''),
        'send_email': record.get('send_email', False),
        'reminder_days': record.get('reminder_days'),
        'user_email': record.get('user_email', ''),
        'first_name': record.get('first_name', '')
    }

def to_dict_net_worth(record):
    if not record:
        return {'net_worth': None, 'total_assets': None}
    return {
        'cash_savings': record.get('cash_savings', 0),
        'investments': record.get('investments', 0),
        'property': record.get('property', 0),
        'loans': record.get('loans', 0),
        'total_assets': record.get('total_assets', 0),
        'total_liabilities': record.get('total_liabilities', 0),
        'net_worth': record.get('net_worth', 0),
        'badges': record.get('badges', []),
        'created_at': record.get('created_at')
    }

def to_dict_emergency_fund(record):
    if not record:
        return {'target_amount': None, 'savings_gap': None}
    return {
        'monthly_expenses': record.get('monthly_expenses', 0),
        'monthly_income': record.get('monthly_income', 0),
        'current_savings': record.get('current_savings', 0),
        'risk_tolerance_level': record.get('risk_tolerance_level', ''),
        'dependents': record.get('dependents', 0),
        'timeline': record.get('timeline', 0),
        'recommended_months': record.get('recommended_months', 0),
        'target_amount': record.get('target_amount', 0),
        'savings_gap': record.get('savings_gap', 0),
        'monthly_savings': record.get('monthly_savings', 0),
        'percent_of_income': record.get('percent_of_income'),
        'badges': record.get('badges', []),
        'created_at': record.get('created_at')
    }

def to_dict_learning_progress(record):
    if not record:
        return {'lessons_completed': [], 'quiz_scores': {}}
    return {
        'course_id': record.get('course_id', ''),
        'lessons_completed': record.get('lessons_completed', []),
        'quiz_scores': record.get('quiz_scores', {}),
        'current_lesson': record.get('current_lesson')
    }

def to_dict_quiz_result(record):
    if not record:
        return {'personality': None, 'score': None}
    return {
        'personality': record.get('personality', ''),
        'score': record.get('score', 0),
        'badges': record.get('badges', []),
        'insights': record.get('insights', []),
        'tips': record.get('tips', []),
        'created_at': record.get('created_at')
    }

def to_dict_tax_reminder(record):
    if not record:
        return {'tax_type': None, 'amount': None}
    return {
        'id': str(record.get('_id', '')),
        'user_id': record.get('user_id', ''),
        'tax_type': record.get('tax_type', ''),
        'due_date': record.get('due_date'),
        'amount': record.get('amount', 0),
        'status': record.get('status', ''),
        'created_at': record.get('created_at'),
        'notification_id': record.get('notification_id'),
        'sent_at': record.get('sent_at'),
        'payment_location_id': record.get('payment_location_id')
    }

@reports_bp.route('/')
@login_required
@utils.requires_role('trader')
def index():
    """Display report selection page."""
    try:
        return render_template(
            'reports/index.html',
            title=utils.trans('reports_index', default='Reports', lang=session.get('lang', 'en'))
        )
    except Exception as e:
        logger.error(f"Error loading reports index for user {current_user.id}: {str(e)}")
        flash(trans('reports_load_error', default='An error occurred'), 'danger')
        return redirect(url_for('dashboard.index'))

@reports_bp.route('/profit_loss', methods=['GET', 'POST'])
@login_required
@utils.requires_role('trader')
def profit_loss():
    """Generate profit/loss report with filters."""
    form = ReportForm()
    if not utils.is_admin() and not utils.check_ficore_credit_balance(1):
        flash(trans('debtors_insufficient_credits', default='Insufficient credits to generate a report. Request more credits.'), 'danger')
        return redirect(url_for('credits.request_credits'))
    cashflows = []
    query = {} if utils.is_admin() else {'user_id': str(current_user.id)}
    if form.validate_on_submit():
        try:
            db = utils.get_mongo_db()
            if form.start_date.data:
                query['created_at'] = {'$gte': form.start_date.data}
            if form.end_date.data:
                query['created_at'] = query.get('created_at', {}) | {'$lte': form.end_date.data}
            if form.category.data:
                query['category'] = form.category.data
            cashflows = list(db.cashflows.find(query).sort('created_at', -1))
            output_format = request.form.get('format', 'html')
            if output_format == 'pdf':
                return generate_profit_loss_pdf(cashflows)
            elif output_format == 'csv':
                return generate_profit_loss_csv(cashflows)
            if not utils.is_admin():
                user_query = utils.get_user_query(str(current_user.id))
                db.users.update_one(
                    user_query,
                    {'$inc': {'ficore_credit_balance': -1}}
                )
                db.credit_transactions.insert_one({
                    'user_id': str(current_user.id),
                    'amount': -1,
                    'type': 'spend',
                    'date': datetime.utcnow(),
                    'ref': 'Profit/Loss report generation (Ficore Credits)'
                })
        except Exception as e:
            logger.error(f"Error generating profit/loss report for user {current_user.id}: {str(e)}")
            flash(trans('reports_generation_error', default='An error occurred'), 'danger')
    else:
        db = utils.get_mongo_db()
        cashflows = list(db.cashflows.find(query).sort('created_at', -1))
    return render_template(
        'reports/profit_loss.html',
        form=form,
        cashflows=cashflows,
        title=utils.trans('reports_profit_loss', default='Profit/Loss Report', lang=session.get('lang', 'en'))
    )

@reports_bp.route('/inventory', methods=['GET', 'POST'])
@login_required
@utils.requires_role('trader')
def inventory():
    """Generate inventory report with filters."""
    form = InventoryReportForm()
    if not utils.is_admin() and not utils.check_ficore_credit_balance(1):
        flash(trans('debtors_insufficient_credits', default='Insufficient credits to generate a report. Request more credits.'), 'danger')
        return redirect(url_for('credits.request_credits'))
    items = []
    query = {} if utils.is_admin() else {'user_id': str(current_user.id)}
    if form.validate_on_submit():
        try:
            db = utils.get_mongo_db()
            if form.item_name.data:
                query['item_name'] = {'$regex': form.item_name.data, '$options': 'i'}
            items = list(db.inventory.find(query).sort('item_name', 1))
            output_format = request.form.get('format', 'html')
            if output_format == 'pdf':
                return generate_inventory_pdf(items)
            elif output_format == 'csv':
                return generate_inventory_csv(items)
            if not utils.is_admin():
                user_query = utils.get_user_query(str('current_user.id'))
                db.users.update_one(
                    user_query,
                    {'$inc': {'ficore_credit_balance': -1}}
                )
                db.credit_transactions.insert_one({
                    'user_id': str(current_user.id),
                    'amount': -1,
                    'type': 'spend',
                    'date': datetime.utcnow(),
                    'ref': 'Inventory report generation (Ficore Credits)'
                })
        except Exception as e:
            logger.error(f"Error generating inventory report for user {current_user.id}: {str(e)}")
            flash(trans('reports_generation_error', default='An error occurred'), 'danger')
    else:
        db = utils.get_mongo_db()
        items = list(db.inventory.find(query).sort('item_name', 1))
    return render_template(
        'reports/inventory.html',
        form=form,
        items=items,
        title=utils.trans('reports_inventory', default='Inventory Report', lang=session.get('lang', 'en'))
    )

@reports_bp.route('/admin/customer-reports', methods=['GET', 'POST'])
@login_required
@utils.requires_role('admin')
def customer_reports():
    """Generate customer reports for admin."""
    form = CustomerReportForm()
    if form.validate_on_submit():
        role = form.role.data if form.role.data else None
        report_format = form.format.data
        try:
            db = utils.get_mongo_db()
            pipeline = [
                {'$match': {'role': role}} if role else {},
                {'$lookup': {
                    'from': 'financial_health_scores',
                    'let': {'user_id': '$_id'},
                    'pipeline': [
                        {'$match': {'$expr': {'$eq': ['$user_id', '$$user_id']}}},
                        {'$sort': {'created_at': -1}},
                        {'$limit': 1}
                    ],
                    'as': 'latest_financial_health'
                }},
                {'$lookup': {
                    'from': 'budgets',
                    'let': {'user_id': '$_id'},
                    'pipeline': [
                        {'$match': {'$expr': {'$eq': ['$user_id', '$$user_id']}}},
                        {'$sort': {'created_at': -1}},
                        {'$limit': 1}
                    ],
                    'as': 'latest_budget'
                }},
                {'$lookup': {
                    'from': 'bills',
                    'let': {'user_id': '$_id'},
                    'pipeline': [
                        {'$match': {'$expr': {'$eq': ['$user_id', '$$user_id']}}},
                        {'$group': {
                            '_id': '$status',
                            'count': {'$sum': 1}
                        }}
                    ],
                    'as': 'bill_status_counts'
                }},
                {'$lookup': {
                    'from': 'net_worth_data',
                    'let': {'user_id': '$_id'},
                    'pipeline': [
                        {'$match': {'$expr': {'$eq': ['$user_id', '$$user_id']}}},
                        {'$sort': {'created_at': -1}},
                        {'$limit': 1}
                    ],
                    'as': 'latest_net_worth'
                }},
                {'$lookup': {
                    'from': 'emergency_funds',
                    'let': {'user_id': '$_id'},
                    'pipeline': [
                        {'$match': {'$expr': {'$eq': ['$user_id', '$$user_id']}}},
                        {'$sort': {'created_at': -1}},
                        {'$limit': 1}
                    ],
                    'as': 'latest_emergency_fund'
                }},
                {'$lookup': {
                    'from': 'learning_materials',
                    'let': {'user_id': '$_id'},
                    'pipeline': [
                        {'$match': {'$expr': {'$eq': ['$user_id', '$$user_id']}}},
                        {'$group': {
                            '_id': None,
                            'total_lessons_completed': {'$sum': {'$size': '$lessons_completed'}}
                        }}
                    ],
                    'as': 'learning_progress'
                }},
                {'$lookup': {
                    'from': 'quiz_responses',
                    'let': {'user_id': '$_id'},
                    'pipeline': [
                        {'$match': {'$expr': {'$eq': ['$user_id', '$$user_id']}}},
                        {'$sort': {'created_at': -1}},
                        {'$limit': 1}
                    ],
                    'as': 'latest_quiz_result'
                }},
                {'$lookup': {
                    'from': 'tax_reminders',
                    'let': {'user_id': '$_id'},
                    'pipeline': [
                        {'$match': {'$expr': {'$eq': ['$user_id', '$$user_id']}, 'due_date': {'$gte': datetime.utcnow()}}},
                        {'$sort': {'due_date': 1}},
                        {'$limit': 1}
                    ],
                    'as': 'next_tax_reminder'
                }},
            ]
            users = list(db.users.aggregate(pipeline))
            report_data = []
            for user in users:
                financial_health = to_dict_financial_health(user['latest_financial_health'][0] if user['latest_financial_health'] else None)
                budget = to_dict_budget(user['latest_budget'][0] if user['latest_budget'] else None)
                bill_counts = {status['_id']: status['count'] for status in user['bill_status_counts']} if user['bill_status_counts'] else {'pending': 0, 'paid': 0, 'overdue': 0}
                net_worth = to_dict_net_worth(user['latest_net_worth'][0] if user['latest_net_worth'] else None)
                emergency_fund = to_dict_emergency_fund(user['latest_emergency_fund'][0] if user['latest_emergency_fund'] else None)
                learning_progress = user['learning_progress'][0]['total_lessons_completed'] if user['learning_progress'] else 0
                quiz_result = to_dict_quiz_result(user['latest_quiz_result'][0] if user['latest_quiz_result'] else None)
                tax_reminder = to_dict_tax_reminder(user['next_tax_reminder'][0] if user['next_tax_reminder'] else None)

                data = {
                    'username': user['_id'],
                    'email': user.get('email', ''),
                    'role': user.get('role', ''),
                    'ficore_credit_balance': user.get('ficore_credit_balance', 0),
                    'language': user.get('language', 'en'),
                    'financial_health_score': financial_health['score'] if financial_health['score'] is not None else '-',
                    'financial_health_status': financial_health['status'] if financial_health['status'] is not None else '-',
                    'debt_to_income': financial_health['debt_to_income'] if financial_health['debt_to_income'] is not None else '-',
                    'savings_rate': financial_health['savings_rate'] if financial_health['savings_rate'] is not None else '-',
                    'budget_income': budget['income'] if budget['income'] is not None else '-',
                    'budget_fixed_expenses': budget['fixed_expenses'] if budget['fixed_expenses'] is not None else '-',
                    'budget_variable_expenses': budget['variable_expenses'] if budget['variable_expenses'] is not None else '-',
                    'budget_surplus_deficit': budget['surplus_deficit'] if budget['surplus_deficit'] is not None else '-',
                    'pending_bills': bill_counts.get('pending', 0),
                    'paid_bills': bill_counts.get('paid', 0),
                    'overdue_bills': bill_counts.get('overdue', 0),
                    'net_worth': net_worth['net_worth'] if net_worth['net_worth'] is not None else '-',
                    'total_assets': net_worth['total_assets'] if net_worth['total_assets'] is not None else '-',
                    'total_liabilities': net_worth['total_liabilities'] if net_worth['total_liabilities'] is not None else '-',
                    'emergency_fund_target': emergency_fund['target_amount'] if emergency_fund['target_amount'] is not None else '-',
                    'emergency_fund_savings': emergency_fund['current_savings'] if emergency_fund['current_savings'] is not None else '-',
                    'emergency_fund_gap': emergency_fund['savings_gap'] if emergency_fund['savings_gap'] is not None else '-',
                    'lessons_completed': learning_progress,
                    'quiz_personality': quiz_result['personality'] if quiz_result['personality'] is not None else '-',
                    'quiz_score': quiz_result['score'] if quiz_result['score'] is not None else '-',
                    'next_tax_due_date': utils.format_date(tax_reminder['due_date']) if tax_reminder['due_date'] else '-',
                    'next_tax_amount': tax_reminder['amount'] if tax_reminder['amount'] is not None else '-'
                }
                report_data.append(data)

            if report_format == 'html':
                return render_template('reports/customer_reports.html', report_data=report_data, title=' Facore Credits')
            elif report_format == 'pdf':
                return generate_customer_report_pdf(report_data)
            elif report_format == 'csv':
                return generate_customer_report_csv(report_data)
        except Exception as e:
            logger.error(f"Error generating customer report: {str(e)}")
            flash('An error occurred while generating the report', 'danger')
    return render_template('reports/customer_reports_form.html', form=form, title='Generate Customer Report')

def generate_profit_loss_pdf(cashflows):
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    p.setFont("Helvetica", 12)
    p.drawString(1 * inch, 10.5 * inch, trans('reports_profit_loss_report', default='Profit/Loss Report'))
    p.drawString(1 * inch, 10.2 * inch, f"{trans('reports_generated_on', default='Generated on')}: {utils.format_date(datetime.utcnow())}")
    y = 9.5 * inch
    p.setFillColor(colors.black)
    p.drawString(1 * inch, y, trans('general_date', default='Date'))
    p.drawString(2.5 * inch, y, trans('general_party_name', default='Party Name'))
    p.drawString(4 * inch, y, trans('general_type', default='Type'))
    p.drawString(5 * inch, y, trans('general_amount', default='Amount'))
    p.drawString(6.5 * inch, y, trans('general_category', default='Category'))
    y -= 0.3 * inch
    total_income = 0
    total_expense = 0
    for t in cashflows:
        p.drawString(1 * inch, y, utils.format_date(t['created_at']))
        p.drawString(2.5 * inch, y, t['party_name'])
        p.drawString(4 * inch, y, trans(t['type'], default=t['type']))
        p.drawString(5 * inch, y, utils.format_currency(t['amount']))
        p.drawString(6.5 * inch, y, trans(t.get('category', ''), default=t.get('category', '')))
        if t['type'] == 'receipt':
            total_income += t['amount']
        else:
            total_expense += t['amount']
        y -= 0.3 * inch
        if y < 1 * inch:
            p.showPage()
            y = 10.5 * inch
    y -= 0.3 * inch
    p.drawString(1 * inch, y, f"{trans('reports_total_income', default='Total Income')}: {utils.format_currency(total_income)}")
    y -= 0.3 * inch
    p.drawString(1 * inch, y, f"{trans('reports_total_expense', default='Total Expense')}: {utils.format_currency(total_expense)}")
    y -= 0.3 * inch
    p.drawString(1 * inch, y, f"{trans('reports_net_profit', default='Net Profit')}: {utils.format_currency(total_income - total_expense)}")
    p.showPage()
    p.save()
    buffer.seek(0)
    return Response(buffer, mimetype='application/pdf', headers={'Content-Disposition': 'attachment;filename=profit_loss.pdf'})

def generate_profit_loss_csv(cashflows):
    output = []
    output.append([trans('general_date', default='Date'), trans('general_party_name', default='Party Name'), trans('general_type', default='Type'), trans('general_amount', default='Amount'), trans('general_category', default='Category')])
    total_income = 0
    total_expense = 0
    for t in cashflows:
        output.append([utils.format_date(t['created_at']), t['party_name'], trans(t['type'], default=t['type']), utils.format_currency(t['amount']), trans(t.get('category', ''), default=t.get('category', ''))])
        if t['type'] == 'receipt':
            total_income += t['amount']
        else:
            total_expense += t['amount']
    output.append(['', '', '', f"{trans('reports_total_income', default='Total Income')}: {utils.format_currency(total_income)}", ''])
    output.append(['', '', '', f"{trans('reports_total_expense', default='Total Expense')}: {utils.format_currency(total_expense)}", ''])
    output.append(['', '', '', f"{trans('reports_net_profit', default='Net Profit')}: {utils.format_currency(total_income - total_expense)}", ''])
    buffer = BytesIO()
    writer = csv.writer(buffer, lineterminator='\n')
    writer.writerows(output)
    buffer.seek(0)
    return Response(buffer, mimetype='text/csv', headers={'Content-Disposition': 'attachment;filename=profit_loss.csv'})

def generate_inventory_pdf(items):
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    p.setFont("Helvetica", 12)
    p.drawString(1 * inch, 10.5 * inch, trans('reports_inventory_report', default='Inventory Report'))
    p.drawString(1 * inch, 10.2 * inch, f"{trans('reports_generated_on', default='Generated on')}: {utils.format_date(datetime.utcnow())}")
    y = 9.5 * inch
    p.setFillColor(colors.black)
    p.drawString(1 * inch, y, trans('inventory_item_name', default='Item Name'))
    p.drawString(2.5 * inch, y, trans('inventory_quantity', default='Quantity'))
    p.drawString(3.5 * inch, y, trans('inventory_unit', default='Unit'))
    p.drawString(4.5 * inch, y, trans('inventory_buying_price', default='Buying Price'))
    p.drawString(5.5 * inch, y, trans('inventory_selling_price', default='Selling Price'))
    p.drawString(6.5 * inch, y, trans('inventory_threshold', default='Threshold'))
    y -= 0.3 * inch
    for item in items:
        p.drawString(1 * inch, y, item['item_name'])
        p.drawString(2.5 * inch, y, str(item['qty']))
        p.drawString(3.5 * inch, y, trans(item['unit'], default=item['unit']))
        p.drawString(4.5 * inch, y, utils.format_currency(item['buying_price']))
        p.drawString(5.5 * inch, y, utils.format_currency(item['selling_price']))
        p.drawString(6.5 * inch, y, str(item.get('threshold', 5)))
        y -= 0.3 * inch
        if y < 1 * inch:
            p.showPage()
            y = 10.5 * inch
    p.showPage()
    p.save()
    buffer.seek(0)
    return Response(buffer, mimetype='application/pdf', headers={'Content-Disposition': 'attachment;filename=inventory.pdf'})

def generate_inventory_csv(items):
    output = []
    output.append([trans('inventory_item_name', default='Item Name'), trans('inventory_quantity', default='Quantity'), trans('inventory_unit', default='Unit'), trans('inventory_buying_price', default='Buying Price'), trans('inventory_selling_price', default='Selling Price'), trans('inventory_threshold', default='Threshold')])
    for item in items:
        output.append([item['item_name'], item['qty'], trans(item['unit'], default=item['unit']), utils.format_currency(item['buying_price']), utils.format_currency(item['selling_price']), item.get('threshold', 5)])
    buffer = BytesIO()
    writer = csv.writer(buffer, lineterminator='\n')
    writer.writerows(output)
    buffer.seek(0)
    return Response(buffer, mimetype='text/csv', headers={'Content-Disposition': 'attachment;filename=inventory.csv'})

def generate_customer_report_pdf(report_data):
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    p.setFont("Helvetica", 8)
    p.drawString(0.5 * inch, 10.5 * inch, trans('reports_customer_report', default='Customer Report'))
    p.drawString(0.5 * inch, 10.2 * inch, f"{trans('reports_generated_on', default='Generated on')}: {utils.format_date(datetime.utcnow())}")
    y = 9.5 * inch
    headers = [
        'Username', 'Email', 'Role', 'Credits', 'Lang', 'FH Score', 'FH Status', 'DTI', 'Savings',
        'Income', 'Fixed Exp', 'Var Exp', 'Surplus', 'Pending Bills', 'Paid Bills', 'Overdue Bills',
        'Net Worth', 'Assets', 'Liabs', 'EF Target', 'EF Savings', 'EF Gap', 'Lessons', 'Quiz Pers', 'Quiz Score',
        'Tax Due', 'Tax Amt'
    ]
    x_positions = [0.5 * inch + i * 0.3 * inch for i in range(len(headers))]
    for header, x in zip(headers, x_positions):
        p.drawString(x, y, header)
    y -= 0.2 * inch
    for data in report_data:
        values = [
            data['username'], data['email'], data['role'], str(data['ficore_credit_balance']), data['language'],
            str(data['financial_health_score']), data['financial_health_status'], str(data['debt_to_income']), str(data['savings_rate']),
            str(data['budget_income']), str(data['budget_fixed_expenses']), str(data['budget_variable_expenses']), str(data['budget_surplus_deficit']),
            str(data['pending_bills']), str(data['paid_bills']), str(data['overdue_bills']),
            str(data['net_worth']), str(data['total_assets']), str(data['total_liabilities']),
            str(data['emergency_fund_target']), str(data['emergency_fund_savings']), str(data['emergency_fund_gap']),
            str(data['lessons_completed']), data['quiz_personality'], str(data['quiz_score']),
            data['next_tax_due_date'], str(data['next_tax_amount'])
        ]
        for value, x in zip(values, x_positions):
            p.drawString(x, y, str(value)[:15])  # Truncate long values
        y -= 0.2 * inch
        if y < 0.5 * inch:
            p.showPage()
            y = 10.5 * inch
    p.showPage()
    p.save()
    buffer.seek(0)
    return Response(buffer, mimetype='application/pdf', headers={'Content-Disposition': 'attachment;filename=customer_report.pdf'})

def generate_customer_report_csv(report_data):
    output = []
    headers = [
        'Username', 'Email', 'Role', 'Ficore Credit Balance', 'Language',
        'Financial Health Score', 'Financial Health Status', 'Debt-to-Income', 'Savings Rate',
        'Budget Income', 'Budget Fixed Expenses', 'Budget Variable Expenses', 'Budget Surplus/Deficit',
        'Pending Bills', 'Paid Bills', 'Overdue Bills',
        'Net Worth', 'Total Assets', 'Total Liabilities',
        'Emergency Fund Target', 'Emergency Fund Savings', 'Emergency Fund Gap',
        'Lessons Completed', 'Quiz Personality', 'Quiz Score',
        'Next Tax Due Date', 'Next Tax Amount'
    ]
    output.append(headers)
    for data in report_data:
        row = [
            data['username'], data['email'], data['role'], data['ficore_credit_balance'], data['language'],
            data['financial_health_score'], data['financial_health_status'], data['debt_to_income'], data['savings_rate'],
            data['budget_income'], data['budget_fixed_expenses'], data['budget_variable_expenses'], data['budget_surplus_deficit'],
            data['pending_bills'], data['paid_bills'], data['overdue_bills'],
            data['net_worth'], data['total_assets'], data['total_liabilities'],
            data['emergency_fund_target'], data['emergency_fund_savings'], data['emergency_fund_gap'],
            data['lessons_completed'], data['quiz_personality'], data['quiz_score'],
            data['next_tax_due_date'], data['next_tax_amount']
        ]
        output.append(row)
    buffer = BytesIO()
    writer = csv.writer(buffer, lineterminator='\n')
    writer.writerows(output)
    buffer.seek(0)
    return Response(buffer, mimetype='text/csv', headers={'Content-Disposition': 'attachment;filename=customer_report.csv'})
