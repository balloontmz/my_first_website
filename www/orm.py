#!/usr/bin/env python3
# -*- coding: utf-8 -*-

' a new orm'

__author__ = 'tomtiddler'

import asyncio, logging

import aiomysql


def log(sql, arsg=()):
    logging.info('SQL: %s' % sql)


async def create_pool(loop, **kw):  # 创建全局连接池，用于复用数据库连接 # 没有定义关函数，猜测为长期打开状态
    logging.info('create database connection pool...')
    global __pool
    __pool = await aiomysql.create_pool(
        host=kw.get('host', 'localhost'),
        port=kw.get('port', 3306),
        user=kw['user'],
        password=kw['password'],
        db=kw['db'],
        charset=kw.get('charset', 'utf8'),
        autocommit=kw.get('autocommit', True),
        maxsize=kw.get('maxsize', 10),
        minsize=kw.get('minsize', 1),
        loop=loop
    )


# 此函数与教程部分冲突
async def select(sql, args, size=None):  # 用于执行SELECT语句，需传入SQL语句和SQL参数
    log(sql, args)
    global __pool  #
    async with __pool.acquire() as conn:  # 此处教程为get函数，（官网调用后关闭了，当然此处不应关闭，但是否应该有清理缓存一类的操作
        async with conn.cursor(aiomysql.DictCursor) as cur: # cursor的参数,查看文档表示为将结果作为字典返回
            # 替换‘？’为‘%s'，前者为sql占位符，后者为mysql。始终使用带参数的sql语句，防止sql注入
            await cur.execute(sql.replace('?', '%s'), args or ())
            if size:
                rs = await cur.fetchmany(size)  # size的用法？？获取最多指定数量的记录？
            else:
                rs = await cur.fetchall()  # 获取所有记录？
        logging.info('rows returned: %s' % len(rs))
        return rs


# 此函数与教程部分冲突，查看文档所得
async def execute(sql, args, autocommit=True):  # INSERT、UPDATE、DELETE语句的通用函数
    log(sql)
    async with __pool.acquire() as conn:  # async with __pool.get() as conn: # 暂未理解此种替换
        if not autocommit:
            await conn.begin()
        try:
            async with conn.cursor(aiomysql.DictCursor) as cur:  # async with conn.cursor(aiomysql.DictCursor) as cur
                await cur.execute(sql.replace('?', '%s'), args)
                affected = cur.rowcount  # 返回结果数？ # Returns the number of rows that has been produced of affected.
            if not autocommit:
                await conn.commit()
        except BaseException as e:
            if not autocommit:
                await conn.rollback()
            raise
        return affected


# 此函数暂时用于返回数据库的字段条数
def create_args_string(num):
    L = []
    for n in range(num):
        L.append('?')
    return ', '.join(L)


# Field：字段。所有字段类的基类
class Field(object):

    def __init__(self, name, column_type, primary_key, default):
        self.name = name
        self.column_type = column_type  # column type:列类型
        self.primary_key = primary_key
        self.default = default

    def __str__(self):
        return '<%s, %s:%s>' % (self.__class__.__name__, self.column_type, self.name)


#
class StringField(Field):

    def __init__(self, name=None, primary_key=False, default=None, ddl='varchar(100)'):
        super().__init__(name, ddl, primary_key, default)


class BooleanField(Field):

    def __init__(self, name=None, default=False):
        super().__init__(name, 'boolean', False, default)


class IntegerField(Field):

    def __init__(self, name=None, primary_key=False, default=0):
        super().__init__(name, 'bigint', primary_key, default)


class FloatField(Field):

    def __init__(self, name=None, primary_key=False, default=0.0):
        super().__init__(name, 'real', primary_key, default)


class TextField(Field):

    def __init__(self, name=None, default=None):
        super().__init__(name, 'text', False, default)


# 元类，Model类的核心类，定制__new__函数。
class ModelMetaclass(type):

    def __new__(cls, name, bases, attrs):  # 关于new方法的参数
        # 排除Model类本身：
        if name == 'Model':
            return type.__new__(cls, name, bases, attrs)
        # 获取table名称：
        tableName = attrs.get('__table__', None) or name
        logging.info('found model: %s (table: %s)' % (name, tableName))
        # 获取所有的Field和主键名：
        mappings = dict()
        fields = []
        primarykey = None
        for k, v in attrs.items():
            if isinstance(v, Field):
                logging.info('    found mapping: %s ==> %s' % (k, v))
                mappings[k] = v  # 将类属性存入dict：mappings，保存的value是一个Field对象
                if v.primary_key:
                    # 找到主键
                    if primarykey:
                        raise RuntimeError('Duplicate primary key for field: %s' % k)
                    primarykey = k  # 将主键属性名赋予primary，判断主键是否重复 Duplicate
                else:
                    fields.append(k)
        if not primarykey:
            raise RuntimeError('Primary key not found')
        for k in mappings.keys():
            attrs.pop(k)  # 删除类属性，防止实例属性覆盖类属性
        escaped_fields = list(map(lambda f: '`%s`' % f, fields)) # 此处应该注意
        attrs['__mappings__'] = mappings  # 保存属性和列的映射关系
        attrs['__table__'] = tableName
        attrs['__primary_key__'] = primarykey  # 主键属性名
        attrs['__fields__'] = fields  # 除主键外的属性名
        # 构造默认的SELECT、INSERT、UPDATE和DELETE语句：(``反单引号用于表名、字段名等值，不可替换为单引号。单引号用于字符权常量）
        # 以下代码定义的ORM显示，数据库操作过程中，主键只能创建时和删除时修改，数据修改时无法修改主键
        attrs['__select__'] = 'select `%s`, %s from `%s`' % (primarykey, ', '.join(escaped_fields), tableName)
        attrs['__insert__'] = 'insert into `%s` (%s, `%s`) values (%s)' % (
            tableName, ', '.join(escaped_fields), primarykey, create_args_string(len(escaped_fields) + 1))
        attrs['__update__'] = 'update `%s` set %s where `%s`=?' % (
            tableName, ', '.join(map(lambda f: '`%s`=?' % (mappings.get(f).name or f), fields)), primarykey)
        attrs['__delete__'] = 'delete from `%s` where `%s`=?' % (tableName, primarykey)
        return type.__new__(cls, name, bases, attrs)


# 数据库对象的父类，实现对象的操作方法
class Model(dict, metaclass=ModelMetaclass):

    def __init__(self, **kw):
        super(Model, self).__init__(**kw)

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(r"'Model' object has no attribute '%s'" % key)

    def __setattr__(self, key, value):
        self[key] = value

    def getValue(self, key):
        return getattr(self, key, None)

    # 一点理解如下
    # mappings中保存的value是一个Field对象！！！，所以有default属性
    def getValueOrDefault(self, key):
        value = getattr(self, key, None)
        if value is None:
            field = self.__mappings__[key]
            if field.default is not None:
                value = field.default() if callable(field.default) else field.default
                logging.debug('using default value for %s: %s' % (key, str(value)))
                setattr(self, key, value)
        return value

    # 这个类还没搞懂
    @classmethod
    async def findAll(cls, where=None, args=None, **kw):  # 根据where条件查找
        ' find objects by where clause.'
        sql = [cls.__select__]  # 定义为列表，手动加粗
        if where:
            sql.append('where')
            sql.append(where)
            if args is None:
                args = []
            orderBy = kw.get('orderBy', None)
            if orderBy:
                sql.append('order by')
                sql.append(orderBy)
            limit = kw.get('limit', None)
            if limit is not None:
                sql.append('limit')
                if isinstance(limit, int):
                    sql.append('?')
                    args.append(limit)
                elif isinstance(limit, tuple) and len(limit) == 2:
                    sql.append('?, ?')
                    args.extend(limit)
                else:
                    raise ValueError('Invalid limit value: %s' % str(limit))
            rs = await select(' '.join(sql), args)  # 以空格为间隔符合并
            return [cls(**r) for r in rs]

    @classmethod
    async def findNumber(cls, selectField, where=None, args=None):  # where查找，返回的是整数
        ' find number by select and where '
        sql = ['select %s _num_ from `%s`' % (selectField, cls.__table__)]
        if where:
            sql.append('where')
            sql.append(where)
        rs = await select(' '.join(sql), args, 1)  # 此句的join用处
        if len(rs) == 0:
            return None
        return rs[0]['_num_']  # 此参数 _num_ 的出处暂未明白

    # 主键查找
    @classmethod
    async def find(cls, pk):
        ' find object by primary key'
        rs = await select('%s where `%s`=?' % (cls.__select__, cls.__primary_key__), [pk], 1)
        if len(rs) == 0:
            return None
        return cls(**rs[0])

    async def save(self):
        args = list(map(self.getValueOrDefault, self.__fields__))
        args.append(self.getValueOrDefault(self.__primary_key__))
        rows = await execute(self.__insert__, args)
        if rows != 1:
            logging.warning('failed to insert record: affected rows: %s' % rows)

    async def update(self):
        args = list(map(self.getValue, self.__fields__))
        args.append(self.getValue(self.__primary_key__))
        rows = await execute(self.__update__, args)
        if rows != 1:
            logging.warning('failed to update by primary key: affected rows: %s' % rows)

    async def remove(self):
        args = [self.getValue(self.__primary_key__)]
        rows = await execute(self.__delete__, args)
        if rows != 1:
            logging.warning('failed to remove by primary key: affected rows: %s' % rows)
