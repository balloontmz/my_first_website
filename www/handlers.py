#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
handlers
"""

__author__ = 'tomtiddler'

from www.coroweb import get, post
from www.models import User, Blog, Comment, next_id
from www.apis import APIError, APIPermissionError, APIResourceNotFoundError, APIValueError, Page
from www.config import configs
import time, re, hashlib, json, logging, asyncio
from aiohttp import web
import markdown2

COOKIE_NAME = 'websession'
_COOKIE_KEY = configs.session.secret


def user2cookie(user, max_age):
    '''
    Generate cookie str by user
    '''
    # build cookie string by: id-expires-sha1
    expires = str(int(time.time() + max_age))  # 过期时间
    s = '%s-%s-%s-%s' % (user.id, user.passwd, expires, _COOKIE_KEY)  # 组合cookie, cookie_key 取自配置文件
    ls = [user.id, expires, hashlib.sha1(s.encode('utf-8')).hexdigest()]
    return '-'.join(ls)


# 本函数暂时用于auth_factory 验证登录用户
async def cookie2user(cookie_str):
    '''
    Parse cookie and load user if cookie is valid
    '''
    if not cookie_str:
        return None
    try:
        L = cookie_str.split('-')
        if len(L) != 3:
            return None
        uid, expires, sha1 = L
        if int(expires) < time.time():
            return None
        user = await User.find(uid)
        if user is None:
            return None
        s = '%s-%s-%s-%s' % (uid, user.passwd, expires, _COOKIE_KEY)
        if sha1 != hashlib.sha1(s.encode('utf-8')).hexdigest():
            logging.info('invalid sha1')
            return None
        user.passwd = '******'
        return user
    except Exception as e:
        logging.exception(e)
        return None


def check_admin(request):  # 查看是否是管理员。manage 选项
    if request.__user__ is None or not request.__user__.admin:
        raise APIPermissionError()


# 将字符串页码转换为整数
def get_page_index(page_str):
    p = 1
    try:
        p = int(page_str)
    except ValueError as e:
        pass
    if p < 1:
        p = 1
    return p


def text2html(text):  # 对多文本的处理，尚未完全明白
    lines = map(lambda s: '<p>%s</p>' % s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'),
                filter(lambda s: s.strip() != '', text.split('\n')))  # filter:过滤器
    return ''.join(lines)


@get('/')
async def index(*, page='1'):
    page_index = get_page_index(page)
    num = await Blog.findNumber('count(id)')
    page = Page(num, page_index=page_index, page_size=3)  # 传入所有日志数, 当前页码， 单页最大日志数
    if num == 0:
        blogs = []
    else:
        blogs = await Blog.findAll(orderBy='created_at desc', limit=(page.offset, page.limit))  # limit指定的是起始数和限制的个数
    return {
        '__template__': 'blogs.html',
        'page': page,  # page 对象
        'blogs': blogs
        # '__user__': request.__user__  # 解决无法显示已登录用户的问题 ,在 response_factory 中统一加入了，在那能处理所有登录用户问题
    }


@get('/register')
def register():
    return {
        '__template__': 'register.html'
    }


@get('/signin')
def signin():
    return {
        '__template__': 'signin.html'
    }


@get('/signout')  # 这个URL处理函数有通过中间件吗?
def signout(request):
    referer = request.headers.get('Referer')
    r = web.HTTPFound(referer or '/')
    r.set_cookie(COOKIE_NAME, '-deleted-', max_age=0, httponly=True)
    logging.info('user signed out.')
    return r


# 日志读取页？？？  关于输出日志的格式问题尚未解决
@get('/blog/{id}')
async def get_blog(id):
    blog = await Blog.find(id)
    comments = await Comment.findAll('blog_id=?', [id], orderBy='created_at desc')  # 读取所有该 id 的留言
    for c in comments:
        c.html_content = text2html(c.content)
    blog.html_content = markdown2.markdown(blog.content)  # 格式化文章输出，靠这个的吗？那么怎么操作呢，可能需要读取源码的吗？
    return {
        '__template__': 'blog.html',
        'blog': blog,
        'comments': comments
    }


@get('/manage/')
def manage():
    return 'redirect:/manage/blogs'


# 用户管理页
@get('/manage/users')
def manage_users(*, page='1'):
    return {
        '__template__': 'manage_users.html',
        'page_index': get_page_index(page)
    }


# 留言管理页
@get('/manage/comments')
def manage_comments(*, page='1'):
    return {
        '__template__': 'manage_comments.html',
        'page_index': get_page_index(page)
    }


# 日志管理页
@get('/manage/blogs')
def manage_blogs(*, page='1'):
    return {
        '__template__': 'manage_blogs.html',
        'page_index': get_page_index(page)
    }


@get('/manage/blogs/create')  # update users admin=1 where name='tomtiddler' 创建超级用户
def manage_create_blog():
    return {
        '__template__': 'manage_blog_edit.html',
        'id': '',
        'action': '/api/blogs'
    }


@get('/manage/blogs/edit')  # update users admin=1 where name='tomtiddler' 创建超级用户
def manage_edit_blog(*, id):
    return {
        '__template__': 'manage_blog_edit.html',
        'id': id,
        'action': '/api/blogs/%s' % id
    }


'''
# 第一个api
@get('/api/users')
async def api_get_users():
    users = await User.findAll(orderBy='created_at desc')
    for u in users:
        u.password = '******'
    return dict(users=users)
'''

# 正则表达式，由于浏览器端已经把email地址小写化了，所以不需要匹配大写
_RE_EMAIL = re.compile(r'^[a-z0-9\.\-\_]+\@[a-z0-9\-\_]+(\.[a-z0-9\-\_]+){1,4}$')
_RE_SHA1 = re.compile(r'^[0-9a-f]{40}$')  # 16进制字符串？


@get('/api/users')  # 获取具体某页的全部blogs  用于 manage_blogs 的数据获取 model, 传入参数page，由 manage_blogs 给予
async def api_users(*, page='1'):
    page_index = get_page_index(page)
    num = await User.findNumber('count(id)')
    p = Page(num, page_index)  # p是一个page对象
    if num == 0:
        return dict(page=p, users=())
    users = await User.findAll(orderBy='created_at desc', limit=(p.offset, p.limit))
    return dict(page=p, users=users)


@post('/api/users')  # 用于注册
async def api_register_user(*, email, name, passwd):
    if not name or not name.strip():
        raise APIValueError('name')
    if not email or not _RE_EMAIL.match(email):
        raise APIValueError('mail')
    if not passwd or not _RE_SHA1.match(passwd):
        raise APIValueError('passwd')
    users = await User.findAll('email=?', [email])
    if len(users) > 0:
        raise APIError('register:failed', 'email', 'Email is already in use.')
    uid = next_id()
    sha1_password = '%s:%s' % (uid, passwd)  # passwd 是客户端经过计算后的口令，不是原始口令
    user = User(id=uid, name=name.strip(), email=email, passwd=hashlib.sha1(sha1_password.encode('utf-8')).hexdigest(),
                image='http://www.gravatar.com/avatar/%s?d=mm&s=120' % hashlib.md5(
                    email.encode('utf-8')).hexdigest())  # 关于图片不甚了解
    await user.save()
    # make session cookie:
    r = web.Response()
    r.set_cookie(COOKIE_NAME, user2cookie(user, 86400), max_age=86400, httponly=True)
    user.passwd = '******'  # 其实密码已经经过了二次sha1计算了
    r.content_type = 'application/json'
    r.body = json.dumps(user, ensure_ascii=False).encode('utf-8')  # 关于json的序列化操作
    return r


@post('/api/authenticate')  # 用于登录
async def authenticate(*, email, passwd):
    if not email:
        raise APIValueError('email', 'Invalid email.')
    if not passwd:
        raise APIValueError('passwd', 'Invalid passwd')
    users = await User.findAll('email=?', [email])
    if len(users) == 0:
        raise APIValueError('email', 'Email not exist.')
    user = users[0]
    #  check passwd:
    sha1 = hashlib.sha1()
    sha1.update(user.id.encode('utf-8'))
    sha1.update(b':')
    sha1.update(passwd.encode('utf-8'))
    if user.passwd != sha1.hexdigest():
        raise APIValueError('passwd', 'Invalid password.')
    # authenticate ok ,set cookie 跟注册一样传输JSON COOKIE
    r = web.Response()
    r.set_cookie(COOKIE_NAME, user2cookie(user, 86400), max_age=86400, httponly=True)
    user.passwd = '******'  # 其实密码已经经过了二次sha1计算了
    r.content_type = 'application/json'
    r.body = json.dumps(user, ensure_ascii=False).encode('utf-8')  # 关于json的序列化操作
    return r


# 用于获取某个具体的blog？ 日志修改页的js函数有调用此api
@get('/api/blogs/{id}')
async def api_get_blog(*, id):
    blog = await Blog.find(id)
    return blog


# 关于传入参数的猜想， 此处由于url中带有参数id，所以可以作为首要第一位置参数传入，同时由于传入的对象拥有id这个属性，所以应该也可以关键字传入？
@post('/api/blogs/{id}')
async def api_update_blog(id, request, *, name, summary, content):  # id 也可以作为关键词参数传入
    check_admin(request)
    blog = await Blog.find(id)  # 此处忘记加 await 导致没有调用方法而是引用
    if not name or not name.strip():  # 此处表达式曾出错
        raise APIValueError('name', 'name cannot be empty.')
    if not summary or not summary.strip():
        raise APIValueError('summary', 'summary cannot be empty.')
    if not content or not content.strip():
        raise APIValueError('content', 'content cannot be empty.')
    blog.name = name.strip()
    blog.summary = summary.strip()
    blog.content = content.strip()
    await blog.update()
    return blog


@get('/api/blogs')  # 获取具体某页的全部blogs  用于 manage_blogs 的数据获取 model, 传入参数page，由 manage_blogs 给予
async def api_blogs(*, page='1'):
    page_index = get_page_index(page)
    num = await Blog.findNumber('count(id)')
    p = Page(num, page_index)  # p是一个page对象
    if num == 0:
        return dict(page=p, blogs=())
    blogs = await Blog.findAll(orderBy='created_at desc', limit=(p.offset, p.limit))
    return dict(page=p, blogs=blogs)


# 用于创建一个 blog ， 来自网页/manage/blogs/create
@post('/api/blogs')
async def api_create_blog(request, *, name, summary, content):
    check_admin(request)  # 判断是否为管理员
    if not name or not name.strip():
        raise APIValueError('name', 'name cannot be empty.')
    if not summary or not summary.strip():
        raise APIValueError('summary', 'summary cannot be empty.')
    if not content or not content.strip():
        raise APIValueError('content', 'content cannot be empty.')
    blog = Blog(user_id=request.__user__.id, user_name=request.__user__.name, user_image=request.__user__.image,
                name=name.strip(), summary=summary.strip(), content=content.strip())
    await blog.save()
    return blog


@post('/api/blogs/{id}/delete')  # 删除指定日志，在日志列表页的 api
async def api_delete_blog(request, *, id):  # 此处函数名出错了一次
    check_admin(request)
    blog = await Blog.find(id)
    await blog.remove()
    return dict(id=id)


@post('/api/blogs/{id}/comments')  # 用于创建评论，来自日志页
async def api_create_comment(id, request, *, content):
    user = request.__user__
    if user is None:
        raise APIPermissionError('Please signin first')
    if not content or not content.strip():
        raise APIValueError('content')
    blog = await Blog.find(id)
    if blog is None:
        raise APIResourceNotFoundError('BLog')
    comment = Comment(blog_id=blog.id, user_id=user.id, user_name=user.name, user_image=user.image, content=content.strip())
    await comment.save()
    return comment


@get('/api/comments')
async def api_comments(*, page='1'):
    page_index = get_page_index(page)
    num = await Comment.findNumber('count(id)')
    p = Page(num, page_index)  # p是一个page对象
    if num == 0:
        return dict(page=p, comments=())
    comments = await Comment.findAll(orderBy='created_at desc', limit=(p.offset, p.limit))  # 此处代码忘记修改
    return dict(page=p, comments=comments)


@post('/api/comments/{id}/delete')  # 删除指定日志，在日志列表页的 api
async def api_blog(request, *, id):
    check_admin(request)
    comment = await Comment.find(id)
    await comment.remove()
    return dict(id=id)
