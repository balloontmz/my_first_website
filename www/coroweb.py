#!/usr/bin/env python3
# -*- coding: utf-8 -*-

' a new complete orm'

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


class RequestHandler(object):

    def __init__(self, app, fn):
        pass

    async def __call__(self, request):
        pass

# 注册URL处理函数
def add_route(app, fn):
    method = getattr(fn, '__method__', None) # 这个函数是如何取到装饰器@get和@post中的属性的呢
    path = getattr(fn, '__method__', None)
    if path is None or method is None:
        raise ValueError('@get or @post not defined in %s' % str(fn)) # 此函数能判定是否采用了URL处理函数？？？
    if not asyncio.iscoroutinefunction(fn) and not inspect.isgeneratorfunction(fn):
        fn = asyncio.coroutine(fn) # 此过程检测是否为协程， 如果不是，就粗暴地设置为协程？？？
    # 以下的inspect函数没搞懂
    logging.info('add route %s %s => %s(%s)' % (method, path, fn.__name__, ', '.join(inspect.signature(fn).parameters.keys())))
    app.router.add_route(method, path, RequestHandler(app, fn)) # 此处为加入路由的基础方法，然后通过封装做成服务器批量处理的方法


