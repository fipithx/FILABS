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
from wtforms import DateField, StringField, SubmitField
from wtforms.validators import Optional
import csv
import logging

logger = logging.getLogger(__name__)

class ReportForm(FlaskForm):
    start_date = DateField(trans('reports_start_date', default='Start Date'), validators=[Optional()])
    end_date = DateField(trans('reports_end_date', default='End Date'), validators=[Optional()])
    category = StringField(trans('general_category', default='Category'), validators=[Optional()])
    submit = SubmitField(trans('reports_generate_report', default='Generate Report'))

class InventoryReportForm(FlaskForm):
    item_name = StringField(trans('inventory_item_name', default='Item Name'), validators=[Optional()])
    submit = SubmitField(trans('reports_generate_report', default='Generate Report'))

reports_bp = Blueprint('reports', __name__, url_prefix='/reports')

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
    # TEMPORARY: Bypass coin check for admin during testing
    # TODO: Restore original check_coin_balance(1) for production
    if not utils.is_admin() and not utils.check_coin_balance(1):
        flash(trans('reports_insufficient_coins', default='Insufficient coins to generate a report. Purchase more coins.'), 'danger')
        return redirect(url_for('coins.purchase'))
    cashflows = []
    # TEMPORARY: Allow admin to view all cashflows during testing
    # TODO: Restore original user_id filter {'user_id': str(current_user.id)} for production
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
            # TEMPORARY: Skip coin deduction for admin during testing
            # TODO: Restore original coin deduction for production
            if not utils.is_admin():
                user_query = utils.get_user_query(str(current_user.id))
                db.users.update_one(
                    user_query,
                    {'$inc': {'coin_balance': -1}}
                )
                db.coin_transactions.insert_one({
                    'user_id': str(current_user.id),
                    'amount': -1,
                    'type': 'spend',
                    'date': datetime.utcnow(),
                    'ref': 'Profit/Loss report generation'
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
    # TEMPORARY: Bypass coin check for admin during testing
    # TODO: Restore original check_coin_balance(1) for production
    if not utils.is_admin() and not utils.check_coin_balance(1):
        flash(trans('reports_insufficient_coins', default='Insufficient coins to generate a report. Purchase more coins.'), 'danger')
        return redirect(url_for('coins.purchase'))
    items = []
    # TEMPORARY: Allow admin to view all inventory items during testing
    # TODO: Restore original user_id filter {'user_id': str(current_user.id)} for production
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
            # TEMPORARY: Skip coin deduction for admin during testing
            # TODO: Restore original coin deduction for production
            if not utils.is_admin():
                user_query = utils.get_user_query(str(current_user.id))
                db.users.update_one(
                    user_query,
                    {'$inc': {'coin_balance': -1}}
                )
                db.coin_transactions.insert_one({
                    'user_id': str(current_user.id),
                    'amount': -1,
                    'type': 'spend',
                    'date': datetime.utcnow(),
                    'ref': 'Inventory report generation'
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

def generate_profit_loss_pdf(cashflows):
    """Generate PDF for profit/loss report."""
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
    p.drawString(6.5 * inch, y, trans('general PX0Hgeneral_category', default='Category'))
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
    """Generate CSV for profit/loss report."""
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
    """Generate PDF for inventory report."""
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
    """Generate CSV for inventory report."""
    output = []
    output.append([trans('inventory_item_name', default='Item Name'), trans('inventory_quantity', default='Quantity'), trans('inventory_unit', default='Unit'), trans('inventory_buying_price', default='Buying Price'), trans('inventory_selling_price', default='Selling Price'), trans('inventory_threshold', default='Threshold')])
    for item in items:
        output.append([item['item_name'], item['qty'], trans(item['unit'], default=item['unit']), utils.format_currency(item['buying_price']), utils.format_currency(item['selling_price']), item.get('threshold', 5)])
    buffer = BytesIO()
    writer = csv.writer(buffer, lineterminator='\n')
    writer.writerows(output)
    buffer.seek(0)
    return Response(buffer, mimetype='text/csv', headers={'Content-Disposition': 'attachment;filename=inventory.csv'})
