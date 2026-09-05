from flask import Blueprint, request, jsonify, Response
from app.core.middleware import auth_required, get_current_user
from app.core.exceptions import AppException
from app.projects.lead_gen.leads import pipeline, model
import csv
import io
from datetime import datetime

bp = Blueprint('lead_gen_leads', __name__, url_prefix='/api/lead_gen/leads')

@bp.route('/job/<job_id>', methods=['GET'])
@auth_required
def get_by_job(job_id):
    user = get_current_user()
    limit = request.args.get('limit', 1000, type=int)
    skip = request.args.get('skip', 0, type=int)
    
    try:
        leads = pipeline.get_leads_for_job(job_id, str(user['_id']), limit, skip)
        return jsonify({
            'leads': [model.to_response(l) for l in leads],
            'count': len(leads)
        }), 200
    except AppException as e:
        return jsonify({'error': e.message}), e.status_code

@bp.route('/job/<job_id>/download', methods=['GET'])
@auth_required
def download_csv(job_id):
    user = get_current_user()
    
    try:
        leads = pipeline.get_leads_for_job(job_id, str(user['_id']), limit=10000)
    except AppException as e:
        return jsonify({'error': e.message}), e.status_code
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Name', 'Phone', 'Email', 'Website', 'Address'])
    
    for lead in leads:
        writer.writerow([
            lead.get('name', ''),
            lead.get('phone', ''),
            lead.get('email', ''),
            lead.get('website', ''),
            lead.get('address', '')
        ])
    
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=leads_{job_id}.csv'}
    )


@bp.route('/job/<job_id>/download-excel', methods=['GET'])
@auth_required
def download_excel(job_id):
    user = get_current_user()
    try:
        leads = pipeline.get_leads_for_job(job_id, str(user['_id']), limit=10000)
    except AppException as e:
        return jsonify({'error': e.message}), e.status_code

    lead_rows = [
        {
            'name': lead.get('name', ''),
            'phone': lead.get('phone', ''),
            'email': lead.get('email', ''),
            'website': lead.get('website', ''),
            'address': lead.get('address', '')
        }
        for lead in leads
    ]

    from app.core import excel_styler
    excel_bytes = excel_styler.create_styled_excel(
        rows=lead_rows,
        title="B2B Business Leads Intelligence Report",
        sheet_name="Leads",
        subtitle=f"Generated: {datetime.utcnow().strftime('%b %d, %Y %H:%M UTC')} • {len(lead_rows)} Verified Business Leads • Google Maps Precision",
        headers=['name', 'phone', 'email', 'website', 'address']
    )

    return Response(
        excel_bytes,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename=leads_{job_id}.xlsx'}
    )

