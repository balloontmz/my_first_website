#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
这个toDict的主要功能是添加一种取值方式a_dict.key，相当于a_dict['key']，这个功能不是必要的.
"""

__author__ = 'tomtiddler'

from www import config_default


class Dict(dict):
    '''
    Simple dict but support access as x.y style
    '''

    def __init__(self, names=(), values=(), **kw):
        super(Dict, self).__init__(**kw)
        for k, v in zip(names, values):
            self[k] = v

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(r"'Dict' object has no attribute '%s'" % key)

    def __setattr__(self, key, value):
        self[key] = value


def toDict(d):
    D = Dict()
    for k, v in d.items():
        D[k] = toDict(v) if isinstance(v, dict) else v  # 字典的多层迭代？
    return D


def merge(defaults, override):
    r = {}
    for k, v in defaults.items():
        if k in override:  # 判断是否在自配置文件中
            if isinstance(v, dict):
                r[k] = merge(v, override[k])  # 字典的多层迭代？？？可否有必要？
            else:
                r[k] = override[k]
        else:
            r[k] = v
    return r


configs = config_default.configs
try:
    from www import config_override
    configs = merge(configs, config_override.configs)
except ImportError:
    raise


configs = toDict(configs)  # 将配置字典转换为自定义字典以增加功能