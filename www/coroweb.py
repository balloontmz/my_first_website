#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
a new uncomplete web paltform
关于fn，即装饰器装饰后的handler（handlers文件夹中）
服务器初始化阶段：引用fn
服务器监听阶段：调用fn
"""

__author__ = 'tomtiddler'

# inspect: 用于收集Python的对象信息，可以获取类或者函数的参数的信息等等
import asyncio, os, inspect, logging, functools

from urllib import parse

from aiohttp import web

from www.apis import APIError


def get(path):
    '''
    Define decorator @get('/path')
    '''

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kw):
            return func(*args, **kw)

        wrapper.__method__ = 'GET'
        wrapper.__route__ = path
        return wrapper

    return decorator


def post(path):
    '''
       Define decorator @get('/path')
    '''

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kw):
            return func(*args, **kw)

        wrapper.__method__ = 'POST'
        wrapper.__route__ = path
        return wrapper

    return decorator


# 以下几个函数处理URL函数并返回RequestHandler需要的参数
# 关于request传入的参数，应该更多了解，以下主要两个需要注意的KEYWORD_ONLY & VAR_KEYWORD
def get_required_kw_args(fn):
    args = []
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if param.kind == inspect.Parameter.KEYWORD_ONLY and param.default == inspect.Parameter.empty:
            args.append(name)
    return tuple(args)


def get_name_kw_args(fn):
    args = []
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if param.kind == inspect.Parameter.KEYWORD_ONLY:
            args.append(name)
    return tuple(args)


def has_named_kw_args(fn):
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if param.kind == inspect.Parameter.KEYWORD_ONLY:
            return True


def has_var_kw_args(fn):
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if param.kind == inspect.Parameter.VAR_KEYWORD:
            return True


def has_request_args(fn):
    sig = inspect.signature(fn)
    params = inspect.signature(fn).parameters
    found = False
    for name, param in params.items():
        if name == 'request':
            found = True
            continue
        if found and (
                param.kind != inspect.Parameter.VAR_POSITIONAL and param.kind != inspect.Parameter.KEYWORD_ONLY and param.kind != inspect.Parameter.VAR_KEYWORD):
            raise ValueError(
                'request parameter must be the last named parameter in function: %s%s' % (fn.__name__, str(sig)))
    return found


class RequestHandler(object):

    # 下列实例参数为服务端初始化时调用，运行时不调用，是固定数据
    def __init__(self, app, fn):
        self._app = app
        self._func = fn
        self._has_request_args = has_request_args(fn)  # 服务器初始化阶段，引用fn
        self._has_var_kw_args = has_var_kw_args(fn)
        self._has_named_kw_args = has_named_kw_args(fn)
        self._named_kw_args = get_name_kw_args(fn)
        self._required_kw_args = get_required_kw_args(fn)

    # 此函数代表类的实例可视为函数，监听时调用，使用协程
    async def __call__(self, request):
        kw = None
        # 一系列的对request传入参数的处理
        if self._has_var_kw_args or self._has_named_kw_args or self._required_kw_args:
            if request.method == 'POST':
                if not request.content_type:
                    return web.HTTPBadRequest('Missing Content-type.')  # web的引用
                ct = request.content_type.lower()
                if ct.startswith('application/json'):  # startswith:包含字符串
                    params = await request.json()
                    if not isinstance(params, dict):
                        return web.HTTPBadRequest('JSON must be object')
                    kw = params
                elif ct.startswith('application/x-www-form-urlencoded') or ct.startswith('multipart/form-data'):
                    params = await request.post()
                    kw = dict(**params)
                else:
                    return web.HTTPBadRequest('Unsupported Content-Type: %s' % request.content_type)
            if request.method == 'GET':
                qs = request.query_string
                if qs:
                    kw = dict()
                    for k, v in parse.parse_qs(qs, True).items():
                        kw[k] = v[0]
        if kw is None:  # 如果第一层未给kw赋值
            kw = dict(**request.match_info)
        else:
            if not self._has_var_kw_args and self._named_kw_args:
                # 干嘛的
                # remove all unamed kw:
                copy = dict()
                for name in self._named_kw_args:
                    if name in kw:
                        copy[name] = kw[name]
                kw = copy
            # check named arg:
            for k, v in request.match_info.items():  # 此处曾出错
                if k in kw:
                    logging.warning('Duplicate arg name in named arg and kw args: %s' % k)
                kw[k] = v
        if self._has_request_args:
            kw['request'] = request
        # check required kw:
        if self._required_kw_args:
            for name in self._required_kw_args:
                if not name in kw:
                    return web.HTTPBadRequest('Missing argument: %s' % name)
        logging.info('call with args: %s' % str(kw))
        # 将处理完的URL函数参数(**kw)传入fn进行处理
        try:
            # HandlerRequest函数的返回值
            r = await self._func(**kw)  # 监听阶段，调用fn
            return r
        except APIError as e:
            return dict(error=e.error, data=e.data, message=e.message)


def add_static(app):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
    app.router.add_static('/static/', path)
    logging.info('add static %s => %s' % ('/static/', path))  # 将当前文件夹下的static注册为静态资源


# 注册URL处理函数 # 这个是服务器端初始化时才运行的，监听时不运行
def add_route(app, fn):
    method = getattr(fn, '__method__', None)  # 这个函数是如何取到装饰器@get和@post中的属性的呢
    path = getattr(fn, '__route__', None)
    if path is None or method is None:
        raise ValueError('@get or @post not defined in %s' % str(fn))  # 此函数能判定是否采用了URL处理函数？？？
    if not asyncio.iscoroutinefunction(fn) and not inspect.isgeneratorfunction(fn):
        fn = asyncio.coroutine(fn)  # 此过程检测是否为协程， 如果不是，就粗暴地设置为协程？？？
    # 以下的inspect函数没搞懂，为日志写入，不太影响主程序
    logging.info(
        'add route %s %s => %s(%s)' % (method, path, fn.__name__, ', '.join(inspect.signature(fn).parameters.keys())))
    # 根据下列函数的调用， 监听时，在内部调用RequesHandler函数
    app.router.add_route(method, path, RequestHandler(app, fn))  # 此处为加入路由的基础方法，然后通过封装做成服务器批量处理的方法(Is coroutine)


# 对module_name文件中的URL处理函数进行批量注册
def add_routes(app, module_name):
    n = module_name.rfind('.')  # 以'.'为分割符查找module_name，主要是处理module__name是否带后缀的问题
    # 可在Console中进行测试，用以大概明白了流程
    if n == (-1):  # 不存在时的返回值
        mod = __import__(module_name, globals(), locals())
    else:
        # 以下处理未完全明白
        name = module_name[n + 1:]
        mod = getattr(__import__(module_name[:n], globals(), locals(), [name]), name)
    for attr in dir(mod):
        if attr.startswith('_'):  # 如果是内置函数或属性，则跳过进行下次循环
            continue
        fn = getattr(mod, attr)  # 取得类或者函数的引用，attr只是单纯的属性名
        if callable(fn):
            method = getattr(fn, '__method__', None)
            path = getattr(fn, '__route__', None)
            if method and path:  # 在add_route中也有判断函数，不清楚为何要两次判断
                add_route(app, fn)  # 不清楚这个高亮的原因，猜测无影响
