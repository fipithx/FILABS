import logging
from bson import ObjectId
from flask import Blueprint, render_template, redirect, url_for, flash, request, session, jsonify
from flask_login import login_required, current_user
from translations import trans
import utils
import bleach
import datetime

logger = logging.getLogger(__name__)

news_bp = Blueprint('news_bp', __name__, template_folder='templates/news')

# Sanitize HTML inputs to prevent XSS
def sanitize_input(text):
    allowed_tags = ['p', 'b', 'i', 'strong', 'em', 'ul', 'ol', 'li', 'a']
    allowed_attributes = {'a': ['href', 'target']}
    return bleach.clean(text, tags=allowed_tags, attributes=allowed_attributes)

@news_bp.route('/news', methods=['GET'])
@utils.requires_role(['personal', 'trader', 'agent', 'admin'])
@login_required
def news_list():
    db = utils.get_mongo_db()
    search_query = request.args.get('search', '')
    category = request.args.get('category', '')
    query = {'is_active': True}
    
    if search_query:
        query['$or'] = [
            {'title': {'$regex': search_query, '$options': 'i'}},
            {'content': {'$regex': search_query, '$options': 'i'}}
        ]
    if category:
        query['category'] = category
    
    articles = list(db.news.find(query).sort('published_at', -1))
    for article in articles:
        article['_id'] = str(article['_id'])
    categories = db.news.distinct('category')
    logger.info(f"News list queried: user={current_user.id}, search={search_query}, category={category}, articles={len(articles)}")
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify([{
            'id': str(article['_id']),
            'title': article['title'],
            'category': article.get('category', ''),
            'published_at': article['published_at'].strftime('%Y-%m-%d'),
            'content': article['content'][:100] + '...' if len(article['content']) > 100 else article['content']
        } for article in articles])
    
    return render_template(
        'news/news.html',
        section='list',
        articles=articles,
        categories=categories,
        title=trans('news_list_title', default='News', lang=session.get('lang', 'en'))
    )

@news_bp.route('/news/<article_id>', methods=['GET'])
@utils.requires_role(['personal', 'trader', 'agent', 'admin'])
@login_required
def news_detail(article_id):
    db = utils.get_mongo_db()
    try:
        article = db.news.find_one({'_id': ObjectId(article_id), 'is_active': True})
    except Exception as e:
        logger.error(f"Error fetching news article {article_id}: {str(e)}")
        article = None
    
    if not article:
        logger.warning(f"News article not found: id={article_id}")
        flash(trans('news_article_not_found', default='Article not found'), 'danger')
        return redirect(url_for('news_bp.news_list'))
    
    article['_id'] = str(article['_id'])
    logger.info(f"News detail viewed: id={article_id}, title={article['title']}, user={current_user.id}")
    return render_template(
        'news/news.html',
        section='detail',
        article=article,
        title=trans('news_detail_title', default='Article', lang=session.get('lang', 'en'))
    )

@news_bp.route('/admin/news_management', methods=['GET', 'POST'])
@utils.requires_role('admin')
@login_required
def news_management():
    db = utils.get_mongo_db()
    if request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')
        source_link = request.form.get('source_link')
        category = request.form.get('category')
        is_active = 'is_active' in request.form
        
        if not title or not content:
            logger.error(f"News creation failed: title={title}, content={content}, user={current_user.id}")
            flash(trans('news_title_content_required', default='Title and content are required'), 'danger')
        else:
            sanitized_content = sanitize_input(content)
            article = {
                'title': title,
                'content': sanitized_content,
                'source_link': source_link if source_link else None,
                'category': category if category else None,
                'is_active': is_active,
                'published_at': datetime.datetime.utcnow(),
                'created_by': current_user.id
            }
            db.news.insert_one(article)
            logger.info(f"News article created: title={title}, user={current_user.id}")
            flash(trans('news_article_added', default='News article added successfully'), 'success')
            return redirect(url_for('news_bp.news_management'))
    
    articles = list(db.news.find().sort('published_at', -1))
    for article in articles:
        article['_id'] = str(article['_id'])
    return render_template(
        'news/news.html',
        section='admin',
        articles=articles,
        title=trans('news_management_title', default='News Management', lang=session.get('lang', 'en'))
    )

@news_bp.route('/admin/news_management/edit/<article_id>', methods=['GET', 'POST'])
@utils.requires_role('admin')
@login_required
def edit_news(article_id):
    db = utils.get_mongo_db()
    try:
        article = db.news.find_one({'_id': ObjectId(article_id)})
    except Exception as e:
        logger.error(f"Error fetching news article for edit {article_id}: {str(e)}")
        article = None
    
    if not article:
        logger.warning(f"Edit news article not found: id={article_id}, user={current_user.id}")
        flash(trans('news_article_not_found', default='Article not found'), 'danger')
        return redirect(url_for('news_bp.news_management'))
    
    if request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')
        source_link = request.form.get('source_link')
        category = request.form.get('category')
        is_active = 'is_active' in request.form
        
        if not title or not content:
            logger.error(f"News update failed: title={title}, content={content}, user={current_user.id}")
            flash(trans('news_title_content_required', default='Title and content are required'), 'danger')
        else:
            sanitized_content = sanitize_input(content)
            db.news.update_one(
                {'_id': ObjectId(article_id)},
                {'$set': {
                    'title': title,
                    'content': sanitized_content,
                    'source_link': source_link if source_link else None,
                    'category': category if category else None,
                    'is_active': is_active,
                    'updated_at': datetime.datetime.utcnow()
                }}
            )
            logger.info(f"News article updated: id={article_id}, title={title}, user={current_user.id}")
            flash(trans('news_article_updated', default='News article updated successfully'), 'success')
            return redirect(url_for('news_bp.news_management'))
    
    article['_id'] = str(article['_id'])
    return render_template(
        'news/news.html',
        section='edit',
        article=article,
        title=trans('news_edit_title', default='Edit News Article', lang=session.get('lang', 'en'))
    )

@news_bp.route('/admin/news_management/delete/<article_id>', methods=['POST'])
@utils.requires_role('admin')
@login_required
def delete_news(article_id):
    db = utils.get_mongo_db()
    try:
        result = db.news.delete_one({'_id': ObjectId(article_id)})
        if result.deleted_count > 0:
            logger.info(f"News article deleted: id={article_id}, user={current_user.id}")
            flash(trans('news_article_deleted', default='News article deleted successfully'), 'success')
        else:
            logger.warning(f"News article not found for deletion: id={article_id}, user={current_user.id}")
            flash(trans('news_article_not_found', default='Article not found'), 'danger')
    except Exception as e:
        logger.error(f"Error deleting news article: id={article_id}, user={current_user.id}, error={str(e)}")
        flash(trans('news_error', default='Error deleting article'), 'danger')
    return redirect(url_for('news_bp.news_management'))

def seed_news():
    db = utils.get_mongo_db()
    if db.news.count_documents({}) == 0:
        articles = [
            {
                'title': 'Welcome to iHatch Cohort 4 – Next Steps & Resources',
                'content': """
                    <p>Congratulations to all innovators selected for the iHatch Startup Support Programme Cohort 4, a 5-month intensive incubation program by NITDA and JICA, running from October 2024 to March 2025. This program empowers early-stage Nigerian startups in sectors like fintech, agritech, and healthtech with mentorship, training, and resources to scale their ventures.</p>
                    <p><strong>Next Steps:</strong></p>
                    <p>Let's work together to empower Nigeria's innovation landscape, one startup at a time!</p>
                """,
                'source_link': 'https://programs.startup.gov.ng/ihatch',
                'category': 'Startups',
                'is_active': True,
                'published_at': datetime.datetime(2025, 6, 2),
                'created_by': 'admin'
            },
            {
                'title': 'Fintech Innovations Driving Financial Inclusion in Nigeria',
                'content': """
                    <p>Nigerian fintech startups are revolutionizing access to financial services. Companies like Paystack and Flutterwave are enabling seamless digital payments, while others like PiggyVest are promoting savings and investment among the youth.</p>
                    <p>These innovations align with Nigeria's Digital Economy Policy, fostering economic growth and job creation.</p>
                """,
                'source_link': None,
                'category': 'Fintech',
                'is_active': True,
                'published_at': datetime.datetime(2025, 6, 1),
                'created_by': 'admin'
            },
            {
                'title': 'Agritech Solutions Transforming Nigerian Agriculture',
                'content': """
                    <p>Agritech startups are addressing challenges in Nigeria's agricultural sector by providing farmers with access to markets, financing, and technology. Innovations like precision farming tools and mobile apps for market data are boosting productivity.</p>
                    <p>These solutions support sustainable development and food security across the nation.</p>
                """,
                'source_link': None,
                'category': 'Agritech',
                'is_active': True,
                'published_at': datetime.datetime(2025, 5, 30),
                'created_by': 'admin'
            },
            {
                'title': 'Nigeria’s Startup Ecosystem: Opportunities in 2025',
                'content': """
                    <p>Nigeria’s startup ecosystem continues to thrive, with increased investments in fintech, agritech, and healthtech. Programs like iHatch Cohort 4 are empowering entrepreneurs with resources and mentorship.</p>
                    <p>In 2025, expect more focus on AI-driven solutions and sustainable business models to address local challenges.</p>
                """,
                'source_link': None,
                'category': 'Startups',
                'is_active': True,
                'published_at': datetime.datetime(2025, 6, 3),
                'created_by': 'admin'
            }
        ]
        db.news.insert_many(articles)
        logger.info("Seeded initial news articles")
