import re
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from flask import Blueprint, current_app, jsonify, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from models import Admin, Opportunity, db

bp = Blueprint('api', __name__)
EMAIL_RE = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
ALLOWED_CATEGORIES = {
    'technology': 'Technology',
    'business': 'Business',
    'design': 'Design',
    'marketing': 'Marketing',
    'data': 'Data Science',
    'other': 'Other'
}


def serialize_user(user):
    return {
        'id': user.id,
        'full_name': user.full_name,
        'email': user.email
    }


def serialize_opportunity(opportunity):
    return {
        'id': opportunity.id,
        'name': opportunity.name,
        'duration': opportunity.duration,
        'start_date': opportunity.start_date,
        'description': opportunity.description,
        'skills': [skill.strip() for skill in opportunity.skills.split(',') if skill.strip()],
        'category': opportunity.category,
        'future_opportunities': opportunity.future_opportunities,
        'max_applicants': opportunity.max_applicants,
        'admin_id': opportunity.admin_id
    }


def get_serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'])


@bp.route('/api/signup', methods=['POST'])
def signup():
    payload = request.get_json() or {}
    full_name = payload.get('full_name', '').strip()
    email = payload.get('email', '').strip().lower()
    password = payload.get('password', '')
    confirm_password = payload.get('confirm_password', '')

    if not full_name or not email or not password or not confirm_password:
        return jsonify(error='All fields are required'), 400
    if not EMAIL_RE.match(email):
        return jsonify(error='Please enter a valid email address'), 400
    if len(password) < 8:
        return jsonify(error='Password must be at least 8 characters'), 400
    if password != confirm_password:
        return jsonify(error='Passwords do not match'), 400

    existing = Admin.query.filter_by(email=email).first()
    if existing:
        return jsonify(error='An account already exists with this email'), 409

    hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
    admin = Admin(full_name=full_name, email=email, password_hash=hashed_password)
    db.session.add(admin)
    db.session.commit()

    return jsonify(status='success', message='Account created successfully'), 201


@bp.route('/api/login', methods=['POST'])
def login():
    payload = request.get_json() or {}
    email = payload.get('email', '').strip().lower()
    password = payload.get('password', '')
    remember = bool(payload.get('remember', False))

    if not email or not password:
        return jsonify(error='Invalid email or password'), 401
    admin = Admin.query.filter_by(email=email).first()
    if not admin or not check_password_hash(admin.password_hash, password):
        return jsonify(error='Invalid email or password'), 401

    login_user(admin, remember=remember)
    return jsonify(status='success', data=serialize_user(admin)), 200


@bp.route('/api/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    return jsonify(status='success', message='Logged out successfully'), 200


@bp.route('/api/forgot-password', methods=['POST'])
def forgot_password():
    payload = request.get_json() or {}
    email = payload.get('email', '').strip().lower()
    message = 'If your email is registered, a password reset link has been sent.'

    if email and EMAIL_RE.match(email):
        admin = Admin.query.filter_by(email=email).first()
        if admin:
            serializer = get_serializer()
            token = serializer.dumps(email, salt=current_app.config['SECURITY_PASSWORD_SALT'])
            reset_url = url_for('api.reset_password_token', token=token, _external=True)
            current_app.logger.info('Password reset link for %s: %s', email, reset_url)

    return jsonify(status='success', message=message), 200


@bp.route('/api/reset-password/<token>', methods=['GET'])
def reset_password_token(token):
    serializer = get_serializer()
    try:
        email = serializer.loads(token, salt=current_app.config['SECURITY_PASSWORD_SALT'], max_age=3600)
        return jsonify(status='success', email=email), 200
    except SignatureExpired:
        return jsonify(error='Reset link has expired'), 400
    except BadSignature:
        return jsonify(error='Invalid reset token'), 400


@bp.route('/api/reset-password/<token>', methods=['POST'])
def reset_password(token):
    payload = request.get_json() or {}
    password = payload.get('password', '')
    confirm_password = payload.get('confirm_password', '')
    if not password or len(password) < 8:
        return jsonify(error='Password must be at least 8 characters'), 400
    if password != confirm_password:
        return jsonify(error='Passwords do not match'), 400

    serializer = get_serializer()
    try:
        email = serializer.loads(token, salt=current_app.config['SECURITY_PASSWORD_SALT'], max_age=3600)
    except SignatureExpired:
        return jsonify(error='Reset link has expired'), 400
    except BadSignature:
        return jsonify(error='Invalid reset token'), 400

    admin = Admin.query.filter_by(email=email).first()
    if not admin:
        return jsonify(error='Invalid reset token'), 400

    admin.password_hash = generate_password_hash(password, method='pbkdf2:sha256')
    db.session.commit()
    return jsonify(status='success', message='Password updated successfully'), 200


@bp.route('/api/me', methods=['GET'])
def me():
    if not current_user.is_authenticated:
        return jsonify(error='Unauthorized'), 401
    return jsonify(status='success', data=serialize_user(current_user)), 200


@bp.route('/api/opportunities', methods=['GET'])
@login_required
def get_opportunities():
    opportunities = Opportunity.query.filter_by(admin_id=current_user.id).order_by(Opportunity.created_at.desc()).all()
    return jsonify(status='success', data=[serialize_opportunity(op) for op in opportunities]), 200


@bp.route('/api/opportunities', methods=['POST'])
@login_required
def create_opportunity():
    payload = request.get_json() or {}
    name = payload.get('name', '').strip()
    duration = payload.get('duration', '').strip()
    start_date = payload.get('start_date', '').strip()
    description = payload.get('description', '').strip()
    skills = payload.get('skills', [])
    category = payload.get('category', '').strip().lower()
    future_opportunities = payload.get('future_opportunities', '').strip()
    max_applicants = payload.get('max_applicants')

    if not name or not duration or not start_date or not description or not skills or not category or not future_opportunities:
        return jsonify(error='Please fill all required fields'), 400
    if category not in ALLOWED_CATEGORIES:
        return jsonify(error='Invalid category'), 400
    if not isinstance(skills, list) or not any(skill.strip() for skill in skills):
        return jsonify(error='Skills must be provided as a non-empty list'), 400

    skills_str = ','.join([skill.strip() for skill in skills if skill.strip()])
    if max_applicants:
        try:
            max_applicants = int(max_applicants)
        except (ValueError, TypeError):
            return jsonify(error='Maximum applicants must be a number'), 400
    else:
        max_applicants = None

    opportunity = Opportunity(
        name=name,
        duration=duration,
        start_date=start_date,
        description=description,
        skills=skills_str,
        category=ALLOWED_CATEGORIES[category],
        future_opportunities=future_opportunities,
        max_applicants=max_applicants,
        admin_id=current_user.id
    )
    db.session.add(opportunity)
    db.session.commit()
    return jsonify(status='success', data=serialize_opportunity(opportunity)), 201


@bp.route('/api/opportunities/<int:opportunity_id>', methods=['GET'])
@login_required
def get_opportunity(opportunity_id):
    opportunity = Opportunity.query.get_or_404(opportunity_id)
    if opportunity.admin_id != current_user.id:
        return jsonify(error='Forbidden'), 403
    return jsonify(status='success', data=serialize_opportunity(opportunity)), 200


@bp.route('/api/opportunities/<int:opportunity_id>', methods=['PUT'])
@login_required
def update_opportunity(opportunity_id):
    opportunity = Opportunity.query.get_or_404(opportunity_id)
    if opportunity.admin_id != current_user.id:
        return jsonify(error='Forbidden'), 403

    payload = request.get_json() or {}
    name = payload.get('name', '').strip()
    duration = payload.get('duration', '').strip()
    start_date = payload.get('start_date', '').strip()
    description = payload.get('description', '').strip()
    skills = payload.get('skills', [])
    category = payload.get('category', '').strip().lower()
    future_opportunities = payload.get('future_opportunities', '').strip()
    max_applicants = payload.get('max_applicants')

    if not name or not duration or not start_date or not description or not skills or not category or not future_opportunities:
        return jsonify(error='Please fill all required fields'), 400
    if category not in ALLOWED_CATEGORIES:
        return jsonify(error='Invalid category'), 400
    if not isinstance(skills, list) or not any(skill.strip() for skill in skills):
        return jsonify(error='Skills must be provided as a non-empty list'), 400

    skills_str = ','.join([skill.strip() for skill in skills if skill.strip()])
    if max_applicants:
        try:
            max_applicants = int(max_applicants)
        except (ValueError, TypeError):
            return jsonify(error='Maximum applicants must be a number'), 400
    else:
        max_applicants = None

    opportunity.name = name
    opportunity.duration = duration
    opportunity.start_date = start_date
    opportunity.description = description
    opportunity.skills = skills_str
    opportunity.category = ALLOWED_CATEGORIES[category]
    opportunity.future_opportunities = future_opportunities
    opportunity.max_applicants = max_applicants
    db.session.commit()

    return jsonify(status='success', message='Opportunity updated successfully', data=serialize_opportunity(opportunity)), 200


@bp.route('/api/opportunities/<int:opportunity_id>', methods=['DELETE'])
@login_required
def delete_opportunity(opportunity_id):
    opportunity = Opportunity.query.get_or_404(opportunity_id)
    if opportunity.admin_id != current_user.id:
        return jsonify(error='Forbidden'), 403
    db.session.delete(opportunity)
    db.session.commit()
    return jsonify(status='success', message='Opportunity deleted successfully'), 200
