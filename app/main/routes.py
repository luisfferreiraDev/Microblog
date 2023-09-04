from datetime import datetime
from flask import render_template, flash, redirect, url_for, request, g, current_app, session, jsonify
from flask_login import current_user, login_required
from flask_babel import _, get_locale
from langdetect import detect, LangDetectException

from app import db
from app.main.forms import EditProfileForm, EmptyForm, PostForm
from app.models import User, Post
from app.main import bp


@bp.before_request
def before_request():
    if current_user.is_authenticated:
        current_user.last_seen = datetime.utcnow()
        db.session.commit()
    g.locale = str(get_locale())


@bp.route('/', methods=['GET', 'POST'])
@bp.route('/index', methods=['GET', 'POST'])
@login_required
def index():
    form = PostForm()
    if form.validate_on_submit():
        try:
            language = detect(form.post.data)
        except LangDetectException:
            language = ''
        post = Post(body=form.post.data, author=current_user, language=language)
        db.session.add(post)
        db.session.commit()
        flash(_('Your post is now live!'))
        return redirect(url_for('main.index'))
    
    page = request.args.get('page', 1, type=int)
    posts = current_user.followed_posts().paginate(page=page, per_page=current_app.config['POSTS_PER_PAGE'], error_out=False)
    
    next_url = url_for('main.index', page=posts.next_num) if posts.has_next else None
    prev_url = url_for('main.index', page=posts.prev_num) if posts.has_prev else None

    return render_template('index.html', title='Home', form=form, posts=posts.items, next_url=next_url, prev_url=prev_url)


@bp.route('/explore')
@login_required
def explore():
    page = request.args.get('page', 1, type=int)
    posts = Post.query.order_by(Post.timestamp.desc()).paginate(
        page=page, per_page=current_app.config['POSTS_PER_PAGE'], error_out=False)
    
    next_url = url_for('main.explore', page=posts.next_num) if posts.has_next else None
    prev_url = url_for('main.explore', page=posts.prev_num) if posts.has_prev else None

    return render_template("index.html", title='Explore', posts=posts.items, next_url=next_url, prev_url=prev_url )


@bp.route('/user/<username>')
@login_required
def user(username):
    user = User.query.filter_by(username=username).first_or_404()

    page = request.args.get('page', 1, type=int)

    posts = user.posts.order_by(Post.timestamp.desc()).paginate(
        page=page, per_page=current_app.config['POSTS_PER_PAGE'], error_out=False
    )

    next_url = url_for('main.user', page=posts.next_num) if posts.has_next else None
    prev_url = url_for('main.user', page=posts.prev_num) if posts.has_prev else None

    saved_posts = current_user.saved_posts.all()
    post_ids = [saved_post.post_id for saved_post in saved_posts]
    saved_posts_list = Post.query.filter(Post.id.in_(post_ids)).all()

    form = EmptyForm()
    return render_template('user.html', user=user, posts = posts.items, form=form, next_url=next_url, prev_url=prev_url, saved_posts=saved_posts_list )


@bp.route('/edit_profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    form = EditProfileForm(current_user.username)
    if form.validate_on_submit():
        current_user.username = form.username.data
        current_user.about_me = form.about_me.data
        db.session.commit()
        flash(_('Changes saved!'))
    elif request.method == 'GET':
        form.username.data = current_user.username
        form.about_me.data = current_user.about_me

    return render_template('edit_profile.html', title='Edit Profile', form=form)


@bp.route('/follow/<username>', methods=['POST'])
@login_required
def follow(username):
    form = EmptyForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=username).first()
        if user is None:
            flash(_('User %(username)s not found.', username=username))
            return redirect(url_for('main.index'))
        if user == current_user:
            flash(_('You cannot follow yourself!'))
            return redirect(url_for('main.user', username=username))
        current_user.follow(user)
        db.session.commit()
        flash(_('You are following %(username)s!', username=username))
        return redirect(url_for('main.user', username=username))
    else:
        return redirect(url_for('main.index'))
    

@bp.route('/unfollow/<username>', methods=['POST'])
@login_required
def unfollow(username):
    form = EmptyForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=username).first()
        if user is None:
            flash(_('User %(username)s not found.', username=username))
            return redirect(url_for('main.index'))
        if user == current_user:
            flash(_('You cannot unfollow yourself!'))
            return redirect(url_for('main.user', username=username))
        current_user.unfollow(user)
        db.session.commit()
        flash(_('You are not following %(username)s.', username=username))
        return redirect(url_for('main.user', username=username))
    else:
        return redirect(url_for('main.index'))
    

@bp.route('/upvote_post/<int:post_id>', methods=['POST'])
@login_required
def upvote_post(post_id):
    post = Post.query.get_or_404(post_id)
    if current_user.has_downvoted(post):
        current_user.remove_downvote(post)
    current_user.upvote(post)
    db.session.commit()
    upvotes_count = post.upvotes.count()
    downvotes_count = post.downvotes.count()
    response_data = {
        'downvotes': downvotes_count,
        'upvotes': upvotes_count
    }
    return jsonify(response_data)


@bp.route('/downvote_post/<int:post_id>', methods=['POST'])
@login_required
def downvote_post(post_id):
    post = Post.query.get_or_404(post_id)
    if current_user.has_upvoted(post):
        current_user.remove_upvote(post)
    current_user.downvote(post)
    db.session.commit()
    downvotes_count = post.downvotes.count()
    upvotes_count = post.upvotes.count()
    response_data = {
        'downvotes': downvotes_count,
        'upvotes': upvotes_count
    }

    return jsonify(response_data)

    
@bp.route('/save_post/<int:post_id>', methods=['POST'])
@login_required
def save_toggle(post_id):
    post = Post.query.get_or_404(post_id)
    
    if current_user.has_saved_post(post):
        current_user.unsave_post(post)
        saved = False
    else:
        current_user.save_post(post)
        saved = True
    
    return jsonify({"saved": saved})