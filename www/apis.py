#!/usr/bin/env python3
# -*- coding: utf-8 -*-

'''
JSON API definition
暂不清楚作用，猜测为自定义的Error返回值
'''

__author__ = 'tomtiddler'

import json, logging, inspect, functools


class APIError(Exception):  # exception：例外，异常
    '''
    the base APIError which contains（包含，内容） error(required), data(optional) and message(optional)
    optional:可选的
    '''

    def __init__(self, error, data='', message=''):
        super(APIError, self).__init__(message)
        self.error = error
        self.data = data
        self.message = message


class APIValueError(APIError):
    '''
    Indicate(表明，指出） the input value has error or invalid（无效的）. The data specified the error field of input form
    '''

    def __init__(self, field, message=''):
        super(APIValueError, self).__init__('value:invalid', field, message)


class APIResourceNotFoundError(APIError):
    '''
    Indicate the resource was not found, The data specifies(指定） the resource name.
    '''

    def __init__(self, field, message=''):
        super(APIResourceNotFoundError, self).__init__('value:notfound', field, message)


class APIPermissionError(APIError):
    '''
    Indicate the api has no permission.
    '''

    def __init__(self, message=''):
        super(APIPermissionError, self).__init__('permission:forbidden', 'permission', message)
