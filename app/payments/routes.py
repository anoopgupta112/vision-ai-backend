"""
Payment routes - API endpoints for Razorpay integration
"""
import csv
import io

from flask import Blueprint, Response, request, jsonify, current_app
from app.core.middleware import auth_required, get_current_user
from app.payments import service, model
from app.lead_gen.credits import model as credits_model

bp = Blueprint('payments', __name__, url_prefix='/api/payments')


def _format_timestamp(value):
    if not value:
        return ''
    return value.isoformat()

@bp.route('/packages', methods=['GET'])
def get_packages():
    """Get available credit packages"""
    packages = service.get_packages()
    return jsonify({'packages': packages}), 200

@bp.route('/create-order', methods=['POST'])
@auth_required
def create_order():
    """
    Create a Razorpay order for purchasing credits
    
    Request body:
        package_id: ID of the credit package to purchase
        
    Returns:
        Order details for Razorpay checkout
    """
    user = get_current_user()
    data = request.get_json()
    
    package_id = data.get('package_id')
    if not package_id:
        return jsonify({'error': 'package_id is required'}), 400
    
    try:
        # Create Razorpay order
        order_details = service.create_order(package_id, str(user['_id']))
        
        # Store transaction in pending state
        model.create_transaction(
            user_id=str(user['_id']),
            order_id=order_details['order_id'],
            package_id=package_id,
            amount=order_details['amount'],
            credits=order_details['package']['credits']
        )
        
        return jsonify(order_details), 200
        
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        current_app.logger.error(f"Error creating order: {str(e)}")
        return jsonify({'error': 'Failed to create order'}), 500

@bp.route('/verify', methods=['POST'])
@auth_required
def verify_payment():
    """
    Verify payment after Razorpay checkout completion
    
    Request body:
        razorpay_order_id: Order ID from Razorpay
        razorpay_payment_id: Payment ID from Razorpay
        razorpay_signature: Signature for verification
        
    Returns:
        Success status and updated credit balance
    """
    user = get_current_user()
    data = request.get_json()
    
    razorpay_order_id = data.get('razorpay_order_id')
    razorpay_payment_id = data.get('razorpay_payment_id')
    razorpay_signature = data.get('razorpay_signature')
    
    if not all([razorpay_order_id, razorpay_payment_id, razorpay_signature]):
        return jsonify({'error': 'Missing payment verification data'}), 400
    
    # Get transaction
    transaction = model.get_transaction_by_order_id(razorpay_order_id)
    if not transaction:
        return jsonify({'error': 'Transaction not found'}), 404
    
    # Verify user owns this transaction
    if str(transaction['user_id']) != str(user['_id']):
        return jsonify({'error': 'Unauthorized'}), 403
    
    # Already processed
    if transaction['status'] == model.STATUS_SUCCESS:
        balance = credits_model.get_balance(str(user['_id']))
        return jsonify({
            'success': True,
            'message': 'Payment already verified',
            'credits_added': transaction['credits'],
            'new_balance': balance
        }), 200
    
    # Verify signature
    is_valid = service.verify_payment_signature(
        razorpay_order_id,
        razorpay_payment_id,
        razorpay_signature
    )
    
    if not is_valid:
        model.update_transaction_failed(razorpay_order_id, 'Invalid signature')
        return jsonify({'error': 'Payment verification failed'}), 400
    
    # Update transaction status
    model.update_transaction_success(razorpay_order_id, razorpay_payment_id)
    
    # Add credits to user
    credits_model.add(
        user_id=str(user['_id']),
        amount=transaction['credits'],
        reason=credits_model.REASON_PURCHASE,
        note=f"Purchased {transaction['package_id']} package via Razorpay"
    )
    
    # Get updated balance
    balance = credits_model.get_balance(str(user['_id']))
    
    return jsonify({
        'success': True,
        'message': 'Payment verified successfully',
        'credits_added': transaction['credits'],
        'new_balance': balance
    }), 200

@bp.route('/webhook', methods=['POST'])
def webhook():
    """
    Handle Razorpay webhook events
    
    This is called by Razorpay for asynchronous payment status updates
    """
    signature = request.headers.get('X-Razorpay-Signature')
    
    if not signature:
        return jsonify({'error': 'Missing signature'}), 400
    
    # Verify webhook signature
    if not service.verify_webhook_signature(request.data, signature):
        return jsonify({'error': 'Invalid signature'}), 400
    
    payload = request.get_json()
    event = payload.get('event')
    
    if event == 'payment.captured':
        payment_entity = payload.get('payload', {}).get('payment', {}).get('entity', {})
        order_id = payment_entity.get('order_id')
        payment_id = payment_entity.get('id')
        
        if order_id and payment_id:
            transaction = model.get_transaction_by_order_id(order_id)
            
            if transaction and transaction['status'] == model.STATUS_PENDING:
                # Update transaction
                model.update_transaction_success(order_id, payment_id)
                
                # Add credits
                credits_model.add(
                    user_id=str(transaction['user_id']),
                    amount=transaction['credits'],
                    reason=credits_model.REASON_PURCHASE,
                    note=f"Purchased {transaction['package_id']} package via Razorpay (webhook)"
                )
    
    elif event == 'payment.failed':
        payment_entity = payload.get('payload', {}).get('payment', {}).get('entity', {})
        order_id = payment_entity.get('order_id')
        error_desc = payment_entity.get('error_description', 'Payment failed')
        
        if order_id:
            model.update_transaction_failed(order_id, error_desc)
    
    return jsonify({'status': 'ok'}), 200

@bp.route('/history', methods=['GET'])
@auth_required
def get_payment_history():
    """Get user's payment history"""
    user = get_current_user()
    limit = request.args.get('limit', 50, type=int)
    
    transactions = model.get_user_transactions(str(user['_id']), limit)
    
    return jsonify({
        'transactions': [model.to_response(t) for t in transactions]
    }), 200


@bp.route('/history/export', methods=['GET'])
@auth_required
def export_payment_history():
    """Download the authenticated user's payment history as CSV"""
    user = get_current_user()
    transactions = model.get_user_transactions(str(user['_id']), 10000)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'Order ID',
        'Payment ID',
        'Package ID',
        'Amount',
        'Currency',
        'Credits Purchased',
        'Payment Status',
        'Created At',
        'Updated At',
    ])

    for transaction in transactions:
        writer.writerow([
            transaction.get('razorpay_order_id', ''),
            transaction.get('razorpay_payment_id', ''),
            transaction.get('package_id', ''),
            transaction.get('amount', ''),
            transaction.get('currency', 'INR'),
            transaction.get('credits', ''),
            transaction.get('status', ''),
            _format_timestamp(transaction.get('created_at')),
            _format_timestamp(transaction.get('updated_at')),
        ])

    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=payment_history.csv'},
    )
