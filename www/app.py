#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
 __main__ app.py
第一次调试成功，切记关闭chorme的本地代理sock5插件
头文件载入在服务器中应取消www，或者用import sys方式改变运行时环境变量，可查。
ctrl+shift+f 可查找代码
"""

__author__ = 'tomtiddler'

import logging;

logging.basicConfig(level=logging.INFO)

import asyncio, os, json, time
from datetime import datetime

from aiohttp import web
from jinja2 import Environment, FileSystemLoader

from www import orm
from www.coroweb import add_routes, add_static
from www.config import configs
from www.handlers import cookie2user, COOKIE_NAME


def init_jinja2(app, **kw):  # options：设置
    # jinjia2的一些设置
    logging.info('init jinja...')
    options = dict(
        autoescape=kw.get('autoescape', True),  # escape：被忽视
        block_start_string=kw.get('block_start_string', '{%'),
        block_end_string=kw.get('block_end_sting', '%}'),
        variable_start_string=kw.get('variable_start_string', '{{'),
        variable_end_string=kw.get('variable_end_string', '}}'),
        auto_reload=kw.get('auto_reload', True)
    )
    path = kw.get('path', None)
    if path is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
    logging.info('set jinja2 template path: %s' % path)
    # 设置templating path？
    env = Environment(loader=FileSystemLoader(path), **options)
    filters = kw.get('filters', None)  # filter：过滤/filter（）函数：过滤器，教程中有用来生成素数的筛选算法用到
    if filters is not None:
        for name, f in filters.items():
            env.filters[name] = f
    app['__templating__'] = env


async def logger_factory(app, handler):
    async def logger(request):
        logging.info('Request: %s %s' % (request.method, request.path))
        # await asyncio.sleep(0.3)
        return (await handler(request))

    return logger


async def auth_factory(app, handler):
    async def auth(request):
        logging.info('check user: %s %s' % (request.method, request.path))
        request.__user__ = None
        cookie_str = request.cookies.get(COOKIE_NAME)
        if cookie_str:
            user = await cookie2user(cookie_str)
            request.__user__ = user
        # 进入管理界面前验证是否为管理员身份   应该想到的  差点想到的
        if request.path.startswith('/manage/') and (request.__user__ is None or not request.__user__.admin):
            return web.HTTPFound('/signin')
        return await handler(request)

    return auth


# 此函数用于何处？ 应该是解析关于 request的前置处理函数
async def data_factory(app, handler):
    async def parse_data(request):
        if request.method == 'POST':
            if request.content_type.startswith('application/json'):
                request.__data__ = await request.json()
                logging.info('request json: %s' % str(request.__data__))
            elif request.content_type.startswith('application/x-www-form-urlencoded'):
                request.__data__ = await request.post()
                logging.info('request json: %s' % str(request.__data__))
        return (await handler(request))

    return parse_data


# 将HandlerRequest函数返回的参数进行处理,整合的拦截器（middlerwares)
async def response_factory(app, handler):  # 猜测：两层函数，第一次调用实例化，第二次调用运行，和HandlerRequest函数功能类似
    async def respones(request):
        logging.info('Responnse handler...')
        r = await handler(request)
        if isinstance(r, web.StreamResponse):
            return r
        if isinstance(r, bytes):
            resp = web.Response(body=r)
            resp.content_type = 'application/octet-stream'
            return resp
        if isinstance(r, str):
            if r.startswith('redirect:'):
                return web.HTTPFound(r[9:])
            resp = web.Response(body=r.encode('utf-8'))
            resp.content_type = 'text/html;charset=utf-8'
            return resp
        if isinstance(r, dict):
            template = r.get('__template__')
            if template is None:  # 路由返回值为json？
                # 下列函数用到json序列化
                resp = web.Response(
                    body=json.dumps(r, ensure_ascii=False, default=lambda o: o.__dict__).encode('utf-8'))
                resp.content_type = 'application/json;charset=utf-8'
                return resp
            else:
                r['__user__'] = request.__user__  # 好想来个语法高亮显示此时的心情。应该想到的。判断是否为登录用户。在这统一加入
                resp = web.Response(body=app['__templating__'].get_template(template).render(**r).encode('utf-8'))
                resp.content_type = 'text/html;charset=utf-8'
                return resp
        if isinstance(r, int) and (r in range(100, 600)):
            return web.Response(r)
        if isinstance(r, tuple) and len(r) == 2:
            t, m = r
            if isinstance(t, int) and (t in range(100, 600)):
                return web.Response(t, str(m))
        # default
        resp = web.Response(body=str(r).encode('utf-8'))
        resp.content_type = 'text/plain;charset=utf-8'
        return resp

    return respones


# 一个插件，用于在模板中插入函数处理后格式化的时间
def datetime_filter(t):
    delta = int(time.time() - t)
    if delta < 60:
        return u'1分钟前'
    if delta < 3600:
        return u'%s分钟前' % (delta // 60)
    if delta < 86400:
        return u'%s分钟前' % (delta // 3600)
    if delta < 604800:
        return u'%s分钟前' % (delta // 86400)
    dt = datetime.fromtimestamp(t)
    return u'%s年%s月%s日' % (dt.year, dt.month, dt.day)


async def init(loop):
    await orm.create_pool(loop=loop, **configs.db)
    app = web.Application(loop=loop,
                          middlewares=[logger_factory, auth_factory, response_factory])  # middlerwares:中间件，factory：工厂函数
    init_jinja2(app, filters=dict(datetime=datetime_filter))  # 模板的传入参数
    add_routes(app, 'handlers')
    add_static(app)  # 和init_jinja2 两个函数都是需要访问文件夹的。注意路径
    srv = await loop.create_server(app._make_handler(), '127.0.0.1', 9000)
    logging.info('server started at http://127.0.0.1:9000...')
    return srv


loop = asyncio.get_event_loop()
loop.run_until_complete(init(loop))
loop.run_forever()
