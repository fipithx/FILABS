from flask import Blueprint, jsonify, current_app
from flask_login import current_user, login_required
from datetime import datetime
from utils import get_mongo_db, trans, format_currency
import logging

business = Blueprint('business', __name__, url_prefix='/business')

# Configure logging
logger = logging.getLogger('ficore_app')
logger.setLevel(logging.INFO)

@business.route('/debt/summary')
@login_required
@utils.requires_role(['trader', 'admin'])
def debt_summary():
    """Fetch debt summary (I Owe, I Am Owed) for the authenticated user."""
    try:
        db = get_mongo_db()
        user_id = current_user.id
        creditors_pipeline = [
            {'$match': {'user_id': user_id, 'type': 'creditor'}},
            {'$group': {'_id': None, 'total': {'$sum': '$amount_owed'}}}
        ]
        creditors_result = list(db.records.aggregate(creditors_pipeline))
        total_i_owe = creditors_result[0]['total'] if creditors_result else 0
        debtors_pipeline = [
            {'$match': {'user_id': user_id, 'type': 'debtor'}},
            {'$group': {'_id': None, 'total': {'$sum': '$amount_owed'}}}
        ]
        debtors_result = list(db.records.aggregate(debtors_pipeline))
        total_i_am_owed = debtors_result[0]['total'] if debtors_result else 0
        logger.info(f"Fetched debt summary for user {user_id}: I Owe={total_i_owe}, I Am Owed={total_i_am_owed}", 
                    extra={'session_id': session.get('sid', 'no-session-id'), 'ip_address': request.remote_addr})
        return jsonify({
            'totalIOwe': total_i_owe,
            'totalIAmOwed': total_i_am_owed
        })
    except Exception as e:
        logger.error(f"Error fetching debt summary for user {user_id}: {str(e)}", 
                     extra={'session_id': session.get('sid', 'no-session-id'), 'ip_address': request.remote_addr})
        return jsonify({'error': trans('debt_summary_error')}), 500

@business.route('/coins/get_balance')
@login_required
@utils.requires_role(['trader', 'admin'])
def get_balance():
    """Fetch the wallet balance for the authenticated user."""
    try:
        db = get_mongo_db()
        user = db.users.find_one({'_id': current_user.id})
        coin_balance = user.get('coin_balance', 0) if user else 0
        logger.info(f"Fetched coin balance for user {current_user.id}: {coin_balance}", 
                    extra={'session_id': session.get('sid', 'no-session-id'), 'ip_address': request.remote_addr})
        return jsonify({'coin_balance': coin_balance})
    except Exception as e:
        logger.error(f"Error fetching coin balance for user {current_user.id}: {str(e)}", 
                     extra={'session_id': session.get('sid', 'no-session-id'), 'ip_address': request.remote_addr})
        return jsonify({'error': trans('coin_balance_error')}), 500

@business.route('/cashflow/summary')
@login_required
@utils.requires_role(['trader', 'admin'])
def cashflow_summary():
    """Fetch the net cashflow (month-to-date) for the authenticated user."""
    try:
        db = get_mongo_db()
        user_id = current_user.id
        today = datetime.utcnow()
        start_of_month = datetime(today.year, today.month, 1)
        receipts_pipeline = [
            {'$match': {'user_id': user_id, 'type': 'receipt', 'created_at': {'$gte': start_of_month}}},
            {'$group': {'_id': None, 'total': {'$sum': '$amount'}}}
        ]
        receipts_result = list(db.cashflows.aggregate(receipts_pipeline))
        total_receipts = receipts_result[0]['total'] if receipts_result else 0
        payments_pipeline = [
            {'$match': {'user_id': user_id, 'type': 'payment', 'created_at': {'$gte': start_of_month}}},
            {'$group': {'_id': None, 'total': {'$sum': '$amount'}}}
        ]
        payments_result = list(db.cashflows.aggregate(payments_pipeline))
        total_payments = payments_result[0]['total'] if payments_result else 0
        net_cashflow = total_receipts - total_payments
        logger.info(f"Fetched cashflow summary for user {user_id}: Net Cashflow={net_cashflow}", 
                    extra={'session_id': session.get('sid', 'no-session-id'), 'ip_address': request.remote_addr})
        return jsonify({
            'netCashflow': net_cashflow,
            'totalReceipts': total_receipts,
            'totalPayments': total_payments
        })
    except Exception as e:
        logger.error(f"Error fetching cashflow summary for user {user_id}: {str(e)}", 
                     extra={'session_id': session.get('sid', 'no-session-id'), 'ip_address': request.remote_addr})
        return jsonify({'error': trans('cashflow_error')}), 500

@business.route('/inventory/summary')
@login_required
@utils.requires_role(['trader', 'admin'])
def inventory_summary():
    """Fetch the total inventory value for the authenticated user."""
    try:
        db = get_mongo_db()
        user_id = current_user.id
        pipeline = [
            {'$match': {'user_id': user_id}},
            {'$addFields': {
                'item_total': {
                    '$multiply': ['$item_qty', '$default_price']
                }
            }},
            {'$group': {'_id': None, 'totalValue': {'$sum': '$item_total'}}}
        ]
        result = list(db.inventory.aggregate(pipeline))
        total_value = result[0]['totalValue'] if result else 0
        logger.info(f"Fetched inventory summary for user {user_id}: Total Value={total_value}", 
                    extra={'session_id': session.get('sid', 'no-session-id'), 'ip_address': request.remote_addr})
        return jsonify({'totalValue': total_value})
    except Exception as e:
        logger.error(f"Error fetching inventory summary for user {user_id}: {str(e)}", 
                     extra={'session_id': session.get('sid', 'no-session-id'), 'ip_address': request.remote_addr})
        return jsonify({'error': trans('inventory_error')}), 500

@business.route('/recent_activity')
@login_required
@utils.requires_role(['trader', 'admin'])
def recent_activity():
    """Fetch recent activities (debts, cashflows) for the authenticated user."""
    try:
        db = get_mongo_db()
        user_id = current_user.id
        activities = []
        
        # Fetch recent debt records
        records = db.records.find({'user_id': user_id}).sort('created_at', -1).limit(3)
        for record in records:
            activity_type = 'debt_added' if record.get('type') == 'debtor' else 'trader_registered'
            description = f'{"Owe" if record.get("type") == "debtor" else "Owed by"} {record.get("name")}'
            activities.append({
                'type': activity_type,
                'description': description,
                'amount': record.get('amount_owed', 0),
                'timestamp': record.get('created_at').isoformat()
            })
        
        # Fetch recent cashflows
        cashflows = db.cashflows.find({'user_id': user_id}).sort('created_at', -1).limit(3)
        for cashflow in cashflows:
            activity_type = 'money_in' if cashflow.get('type') == 'receipt' else 'money_out'
            description = f'{"Received from" if cashflow.get("type") == "receipt" else "Paid to"} {cashflow.get("party_name")}'
            activities.append({
                'type': activity_type,
                'description': description,
                'amount': cashflow.get('amount', 0),
                'timestamp': cashflow.get('created_at').isoformat()
            })
        
        # Sort activities by timestamp (descending)
        activities.sort(key=lambda x: x['timestamp'], reverse=True)
        activities = activities[:5]
        
        logger.info(f"Fetched {len(activities)} recent activities for user {user_id}", 
                    extra={'session_id': session.get('sid', 'no-session-id'), 'ip_address': request.remote_addr})
        return jsonify(activities)
    except Exception as e:
        logger.error(f"Error fetching recent activity for user {user_id}: {str(e)}", 
                     extra={'session_id': session.get('sid', 'no-session-id'), 'ip_address': request.remote_addr})
        return jsonify({'error': trans('activity_error')}), 500