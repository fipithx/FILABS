from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_required, current_user
from translations import trans
import utils
from bson import ObjectId
from datetime import datetime
from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, FloatField, SubmitField
from wtforms.validators import DataRequired, Optional, NumberRange
import logging

logger = logging.getLogger(__name__)

class InventoryForm(FlaskForm):
    item_name = StringField(trans('inventory_item_name', default='Item Name'), validators=[DataRequired()])
    qty = IntegerField(trans('inventory_quantity', default='Quantity'), validators=[DataRequired(), NumberRange(min=0)])
    unit = StringField(trans('inventory_unit', default='Unit'), validators=[DataRequired()])
    buying_price = FloatField(trans('inventory_buying_price', default='Buying Price'), validators=[DataRequired(), NumberRange(min=0)])
    selling_price = FloatField(trans('inventory_selling_price', default='Selling Price'), validators=[DataRequired(), NumberRange(min=0)])
    threshold = IntegerField(trans('inventory_threshold', default='Low Stock Threshold'), validators=[Optional(), NumberRange(min=0)])
    submit = SubmitField(trans('inventory_add_item', default='Add Item'))

class StockAdjustForm(FlaskForm):
    qty = IntegerField(trans('inventory_quantity', default='Quantity'), validators=[DataRequired(), NumberRange(min=1)])
    submit = SubmitField(trans('inventory_adjust_stock', default='Adjust Stock'))

inventory_bp = Blueprint('inventory', __name__, url_prefix='/inventory')

@inventory_bp.route('/')
@login_required
@utils.requires_role('trader')
def index():
    """List all inventory items for the current user."""
    try:
        db = utils.get_mongo_db()
        query = {} if utils.is_admin() else {'user_id': str(current_user.id)}
        items = list(db.inventory.find(query).sort('created_at', -1))
        
        return render_template(
            'inventory/index.html',
            items=items,
            format_currency=utils.format_currency,
            title=trans('inventory_title', default='Inventory', lang=session.get('lang', 'en'))
        )
    except Exception as e:
        logger.error(f"Error fetching inventory for user {current_user.id}: {str(e)}")
        flash(trans('inventory_fetch_error', default='An error occurred'), 'danger')
        return redirect(url_for('dashboard.index'))

@inventory_bp.route('/manage')
@login_required
@utils.requires_role('trader')
def manage():
    """List all inventory items for management (edit/delete/add stock/remove stock) by the current user."""
    try:
        db = utils.get_mongo_db()
        query = {} if utils.is_admin() else {'user_id': str(current_user.id)}
        items = list(db.inventory.find(query).sort('created_at', -1))
        
        return render_template(
            'inventory/manage_inventory.html',
            items=items,
            format_currency=utils.format_currency,
            title=trans('inventory_manage_title', default='Manage Inventory', lang=session.get('lang', 'en'))
        )
    except Exception as e:
        logger.error(f"Error fetching inventory for manage page for user {current_user.id}: {str(e)}")
        flash(trans('inventory_fetch_error', default='An error occurred'), 'danger')
        return redirect(url_for('inventory.index'))

@inventory_bp.route('/low_stock')
@login_required
@utils.requires_role('trader')
def low_stock():
    """List inventory items with low stock."""
    try:
        db = utils.get_mongo_db()
        base_query = {} if utils.is_admin() else {'user_id': str(current_user.id)}
        query = {**base_query, '$expr': {'$lte': ['$qty', '$threshold']}}
        low_stock_items = list(db.inventory.find(query).sort('qty', 1))
        
        return render_template(
            'inventory/low_stock.html',
            items=low_stock_items,
            format_currency=utils.format_currency,
            title=trans('inventory_low_stock_title', default='Low Stock Inventory', lang=session.get('lang', 'en'))
        )
    except Exception as e:
        logger.error(f"Error fetching low stock items for user {current_user.id}: {str(e)}")
        flash(trans('inventory_low_stock_error', default='An error occurred'), 'danger')
        return redirect(url_for('inventory.index'))

@inventory_bp.route('/add', methods=['GET', 'POST'])
@login_required
@utils.requires_role('trader')
def add():
    """Add a new inventory item."""
    form = InventoryForm()
    if not utils.is_admin() and not utils.check_ficore_credit_balance(1):
        flash(trans('debtors_insufficient_credits', default='Insufficient credits to add an item. Request more credits.'), 'danger')
        return redirect(url_for('credits.request_credits'))
    if form.validate_on_submit():
        try:
            db = utils.get_mongo_db()
            item = {
                'user_id': str(current_user.id),
                'item_name': form.item_name.data,
                'qty': form.qty.data,
                'unit': form.unit.data,
                'buying_price': form.buying_price.data,
                'selling_price': form.selling_price.data,
                'threshold': form.threshold.data or 5,
                'created_at': datetime.utcnow()
            }
            db.inventory.insert_one(item)
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
                    'ref': f"Inventory item creation: {item['item_name']} (Ficore Credits)"
                })
            flash(trans('inventory_add_success', default='Inventory item added successfully'), 'success')
            return redirect(url_for('inventory.index'))
        except Exception as e:
            logger.error(f"Error adding inventory item for user {current_user.id}: {str(e)}")
            flash(trans('inventory_add_error', default='An error occurred'), 'danger')
    
    return render_template(
        'inventory/add.html',
        form=form,
        title=trans('inventory_add_title', default='Add Inventory Item', lang=session.get('lang', 'en'))
    )

@inventory_bp.route('/edit/<id>', methods=['GET', 'POST'])
@login_required
@utils.requires_role('trader')
def edit(id):
    """Edit an existing inventory item."""
    try:
        db = utils.get_mongo_db()
        query = {'_id': ObjectId(id)} if utils.is_admin() else {'_id': ObjectId(id), 'user_id': str(current_user.id)}
        item = db.inventory.find_one(query)
        if not item:
            flash(trans('inventory_item_not_found', default='Item not found'), 'danger')
            return redirect(url_for('inventory.index'))
        form = InventoryForm(data={
            'item_name': item['item_name'],
            'qty': item['qty'],
            'unit': item['unit'],
            'buying_price': item['buying_price'],
            'selling_price': item['selling_price'],
            'threshold': item.get('threshold', 5)
        })
        if form.validate_on_submit():
            try:
                updated_item = {
                    'item_name': form.item_name.data,
                    'qty': form.qty.data,
                    'unit': form.unit.data,
                    'buying_price': form.buying_price.data,
                    'selling_price': form.selling_price.data,
                    'threshold': form.threshold.data or 5,
                    'updated_at': datetime.utcnow()
                }
                db.inventory.update_one(
                    {'_id': ObjectId(id)},
                    {'$set': updated_item}
                )
                flash(trans('inventory_edit_success', default='Inventory item updated successfully'), 'success')
                return redirect(url_for('inventory.index'))
            except Exception as e:
                logger.error(f"Error updating inventory item {id} for user {current_user.id}: {str(e)}")
                flash(trans('inventory_edit_error', default='An error occurred'), 'danger')
        
        return render_template(
            'inventory/edit.html',
            form=form,
            item=item,
            title=trans('inventory_edit_title', default='Edit Inventory Item', lang=session.get('lang', 'en'))
        )
    except Exception as e:
        logger.error(f"Error fetching inventory item {id} for user {current_user.id}: {str(e)}")
        flash(trans('inventory_item_not_found', default='Item not found'), 'danger')
        return redirect(url_for('inventory.index'))

@inventory_bp.route('/delete/<id>', methods=['POST'])
@login_required
@utils.requires_role('trader')
def delete(id):
    """Delete an inventory item."""
    try:
        db = utils.get_mongo_db()
        query = {'_id': ObjectId(id)} if utils.is_admin() else {'_id': ObjectId(id), 'user_id': str(current_user.id)}
        item = db.inventory.find_one(query)
        if not item:
            flash(trans('inventory_item_not_found', default='Item not found'), 'danger')
            return redirect(url_for('inventory.index'))
        result = db.inventory.delete_one(query)
        if result.deleted_count:
            db.inventory_transactions.insert_one({
                'user_id': str(current_user.id),
                'item_id': str(item['_id']),
                'item_name': item['item_name'],
                'type': 'delete',
                'qty_change': 0,
                'date': datetime.utcnow(),
                'ref': f"Deleted inventory item: {item['item_name']}"
            })
            flash(trans('inventory_delete_success', default='Inventory item deleted successfully'), 'success')
        else:
            flash(trans('inventory_item_not_found', default='Item not found'), 'danger')
    except Exception as e:
        logger.error(f"Error deleting inventory item {id} for user {current_user.id}: {str(e)}")
        flash(trans('inventory_delete_error', default='An error occurred'), 'danger')
    return redirect(url_for('inventory.index'))

@inventory_bp.route('/add_stock/<id>', methods=['GET', 'POST'])
@login_required
@utils.requires_role('trader')
def add_stock(id):
    """Add stock to an existing inventory item."""
    try:
        db = utils.get_mongo_db()
        query = {'_id': ObjectId(id)} if utils.is_admin() else {'_id': ObjectId(id), 'user_id': str(current_user.id)}
        item = db.inventory.find_one(query)
        if not item:
            flash(trans('inventory_item_not_found', default='Item not found'), 'danger')
            return redirect(url_for('inventory.index'))
        
        form = StockAdjustForm()
        if form.validate_on_submit():
            try:
                qty_to_add = form.qty.data
                db.inventory.update_one(
                    {'_id': ObjectId(id)},
                    {'$inc': {'qty': qty_to_add}, '$set': {'updated_at': datetime.utcnow()}}
                )
                db.inventory_transactions.insert_one({
                    'user_id': str(current_user.id),
                    'item_id': str(item['_id']),
                    'item_name': item['item_name'],
                    'type': 'add_stock',
                    'qty_change': qty_to_add,
                    'date': datetime.utcnow(),
                    'ref': f"Added {qty_to_add} {item['unit']} to {item['item_name']}"
                })
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
                        'ref': f"Added stock to inventory item: {item['item_name']} (Ficore Credits)"
                    })
                flash(trans('inventory_add_stock_success', default='Stock added successfully'), 'success')
                return redirect(url_for('inventory.manage'))
            except Exception as e:
                logger.error(f"Error adding stock to item {id} for user {current_user.id}: {str(e)}")
                flash(trans('inventory_add_stock_error', default='An error occurred'), 'danger')
        
        return render_template(
            'inventory/add_stock.html',
            form=form,
            item=item,
            title=trans('inventory_add_stock_title', default='Add Stock', lang=session.get('lang', 'en'))
        )
    except Exception as e:
        logger.error(f"Error fetching inventory item {id} for add stock for user {current_user.id}: {str(e)}")
        flash(trans('inventory_item_not_found', default='Item not found'), 'danger')
        return redirect(url_for('inventory.index'))

@inventory_bp.route('/remove_stock/<id>', methods=['GET', 'POST'])
@login_required
@utils.requires_role('trader')
def remove_stock(id):
    """Remove stock from an existing inventory item."""
    try:
        db = utils.get_mongo_db()
        query = {'_id': ObjectId(id)} if utils.is_admin() else {'_id': ObjectId(id), 'user_id': str(current_user.id)}
        item = db.inventory.find_one(query)
        if not item:
            flash(trans('inventory_item_not_found', default='Item not found'), 'danger')
            return redirect(url_for('inventory.index'))
        
        form = StockAdjustForm()
        if form.validate_on_submit():
            try:
                qty_to_remove = form.qty.data
                if qty_to_remove > item['qty']:
                    flash(trans('inventory_insufficient_stock', default='Cannot remove more stock than available'), 'danger')
                    return redirect(url_for('inventory.manage'))
                db.inventory.update_one(
                    {'_id': ObjectId(id)},
                    {'$inc': {'qty': -qty_to_remove}, '$set': {'updated_at': datetime.utcnow()}}
                )
                db.inventory_transactions.insert_one({
                    'user_id': str(current_user.id),
                    'item_id': str(item['_id']),
                    'item_name': item['item_name'],
                    'type': 'remove_stock',
                    'qty_change': -qty_to_remove,
                    'date': datetime.utcnow(),
                    'ref': f"Removed {qty_to_remove} {item['unit']} from {item['item_name']}"
                })
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
                        'ref': f"Removed stock from inventory item: {item['item_name']} (Ficore Credits)"
                    })
                flash(trans('inventory_remove_stock_success', default='Stock removed successfully'), 'success')
                return redirect(url_for('inventory.manage'))
            except Exception as e:
                logger.error(f"Error removing stock from item {id} for user {current_user.id}: {str(e)}")
                flash(trans('inventory_remove_stock_error', default='An error occurred'), 'danger')
        
        return render_template(
            'inventory/remove_stock.html',
            form=form,
            item=item,
            title=trans('inventory_remove_stock_title', default='Remove Stock', lang=session.get('lang', 'en'))
        )
    except Exception as e:
        logger.error(f"Error fetching inventory item {id} for remove stock for user {current_user.id}: {str(e)}")
        flash(trans('inventory_item_not_found', default='Item not found'), 'danger')
        return redirect(url_for('inventory.index'))
