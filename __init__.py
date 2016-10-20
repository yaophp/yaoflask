#! /usr/bin/python3
__author__ = 'yao'

import time,os, errno, random, json, datetime, uuid, re
import pymysql,sqlalchemy,flask_sqlalchemy
from werkzeug.datastructures import CallbackDict
from werkzeug.contrib.cache import FileSystemCache,MemcachedCache,RedisCache
from flask.sessions import SessionInterface, SessionMixin
from flask_sqlalchemy import SQLAlchemy,_BoundDeclarativeMeta,make_url,_record_queries,_EngineDebuggingSignalEvents,_EngineConnector
from flask import Flask,Blueprint,session,url_for,request,render_template,Config,redirect,jsonify,Response
from flask_session import Session,sessions
from functools import wraps,partial
import pickle

###################################
#
#           配置相关
#
###################################


class MyConfig(Config):
    """
    系统默认配置文件，不推荐直接修改
    如果有多套配置文件可指定引入并覆盖
    """
    DEBUG = False
    PHP_LOVER = True


    # 会话session
    # SESSION_TYPE = 'memcached'
    # SESSION_TYPE = 'sqlalchemy'
    SESSION_COOKIE_NAME = ''  # session前缀返回给浏览器，默认session
    SESSION_KEY_PREFIX = 'PHPSESSID'    # memcached时的前缀
    SESSION_CACHE_PATH = ''  # session以文件存储时的路径
    SESSION_CACHE_TABLE = 'session'  # session以数据库存放时的table名
    # PERMANENT_SESSION_LIFETIME = 60  # 秒
    PERMANENT_SESSION_LIFETIME = 7200  # 秒
    SESSION_GC_ENABLE = True  # 开关打开时启用服务端session垃圾回收
    SESSION_GC_RANDINT = 10  # 默认session垃圾回收概率表示 1/1000 (最小是1表示100%)
    SECRET_KEY = '}ON&^-F9#R;,!LyXeI{"SdQDqMGH0`K.<m$/n>Ti)17ZkB5' # 默认session secret_key

    # 缓存
    MEMCACHED_HOST = ['127.0.0.1:11211']

    # 数据库
    SQLALCHEMY_DATABASE_URI = 'mysql+pymysql://root:ldy4caocao@localhost:3306/steam'
    # SQLALCHEMY_DATABASE_URI = 'mysql+pymysql://root:ldy4caocao@localhost:3306/thinkflask'
    SQLALCHEMY_TRACK_MODIFICATIONS = True # 上线推荐false
    # SQLALCHEMY_ECHO = True # 输出sql语句，开发环境推荐打开
    # SQLALCHEMY_CONNECT_ARGS = {'connect_args':{ 'cursorclass': pymysql.cursors.DictCursor }}

    # 模板
    TEMPLATES_AUTO_RELOAD = True,
    TMPL_FUNCTION = [],  # 可供模板调用的自定义函数
    # TMPL_SUCCESS = 'success.html',
    # TMPL_ERROR = 'error.html',
    TMPL_404 = '404.html'


def start(self, **kwargs):
    """
    系统开始  : 参数同flask -> run
    todo 尝试自动加载视图
    :param self:
    :param kwargs:
    :return:
    """
    for (k,v) in _APP_MODULE.items() :
        try:
            # __import__(k)
            self.register_blueprint(v)
        except (ImportError, ImportWarning) as e:
            print(e)

    # dump(self)
    self.run(**kwargs)

Flask.start = start
APP = Flask(__name__)
APP.config.from_object(MyConfig)
# Session(APP)
# APP.session_interface = ItsdangerousSessionInterface()


_APP_MODULE = {}  # 应用模块


def bind(name, **kwargs):
    """
    绑定并注册蓝图，所有参数同蓝图参数，可防止新手犯错
    :param name:
    :param kwargs:
    :return:
    """
    global _APP_MODULE
    if name in _APP_MODULE.keys():
        return _APP_MODULE[name]
    else:
        value = name.split('.')[-1]
        config = {
            'url_prefix': '/' + value
        }
        configs = config.copy()
        configs.update(**kwargs)

        if not hasattr(Blueprint, 'R'):
            def _rote(self, rules='', **options):
                """Like :meth:`Flask.route` but for a blueprint.  The endpoint for the
                :func:`url_for` function is prefixed with the name of the blueprint.
                """
                def decorator(f):
                    endpoint = options.pop("endpoint", f.__name__)
                    rule = rules
                    if not rule:
                        rule = f.__name__.replace('_', '/')
                        prefix = getattr(self, 'url_prefix')
                        if not prefix or prefix[-1] != '/':
                            rule = '/' + rule
                    self.add_url_rule(rule, endpoint, f, **options)
                    return f
                return decorator
            Blueprint.R = _rote
        module = Blueprint(value, value, **configs)
        _APP_MODULE[name] = module
        return module


##############################################
#
#           控制器相关
#  todo
##############################################
def display(template='', **kwargs):
    """
    自动载入模板
    :param template: 默认自动载入，可手动指定模板文件
    :param kwargs: 渲染的变量
    :return:
    """
    if not template:
        template = request.endpoint.replace('.', '/') + '.html'
    return render_template(template, session=session, **kwargs)


def IS_(method):
    """判断请求类型如：get、post、ajax等"""
    return method.upper() == request.method if method.upper() != 'AJAX' else 'XMLHttpRequest' == request.headers.get('X-Requested-With' , False)


def I(key='', default=''):
    method = request.method.lower()
    if method == 'post':
        data = request.form.copy()
    else:
        data = request.args.copy()
    return data.get(key, default) if key else {k: data[k] for k in data.keys()}


def dump(obj):
    """对象打印输出，用于调试和查看对象。注意type对象（抽象对象）暂不支持打印"""
    print('')
    if hasattr(obj,'__doc__'):
        print('++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++')
        print('%-30s : %s'%('__doc__' ,obj.__doc__))
        print('++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++','\n')
    for x in dir(obj):
        if x != '__doc__':
            print('%-30s : %s' % (x, getattr(obj, x)))
        # print('%-30s : %s'%(x,getattr(obj,x))) if x != '__doc__' else ''
    print('')
    print('print')
    print(obj)


################################################
#
#           模型相关
# 需要安装flask_sqlalchemy 扩展
# 需要注意的是：sqlalchemy的query使用的session是scoped_session 默认：db.session 没开启autoflush=False
# 而flask_sqlalchemy的Basequery使用的是SignallingSession 如:M('user').query.session 开启autoflush=True
#
################################################


db = SQLAlchemy(APP)
_APP_MODEL = {}


class _FieldMeta(_BoundDeclarativeMeta):
    """自动映射表结构，如果使用自定义模型并定义字段，则保留自定义字段
    数据模型除非指定__tablename__，否则默认是根据类名小写按照去映射表
    推荐数据表使用：小蛇命名(如：user_profile)
    """
    def __new__(cls, name, parent_tuple, self_dict):
        if self_dict.get('__abstract__'):
            return super(_FieldMeta, cls).__new__(cls, name, parent_tuple, self_dict)

        table = self_dict.get('__tablename__') or name.lower()
        try:
            fields = db.session.execute('show COLUMNS from ' + table).fetchall()
        except:
            raise RuntimeError("check your database status and make sure table: " + table + " exists")
        map = {
            'int': db.INT,
            'smallint': db.SMALLINT,
            'tinyint': db.SMALLINT,
            'bigint': db.BIGINT,
            'char': db.CHAR,
            'varchar': db.VARCHAR,
            'time': db.TIME,
            'datetime': db.DATETIME,
            'date': db.DATE,
            'timestamp': db.TIMESTAMP,
            'blob': db.BLOB,
            'text': db.TEXT,
            'decimal': db.DECIMAL,
            'float': db.FLOAT,
            'boolen': db.BOOLEAN
        }
        keyindex = {
            'PRI': 'primary_key',
            'UNI': 'unique',
            'MUL': 'index'
        }
        self_dict['_primary_key'] = []
        self_dict['_model_field'] = []
        for field, type, null, key, default, extra in fields:
            self_dict['_model_field'].append(field)
            if self_dict.__contains__(field):
                continue
            kwd = {}
            length = type.find('(')
            k = type[:length] if length != -1 else type
            if keyindex.get(key):
                kwd[keyindex[key]] = True

            if extra == 'auto_increment':
                kwd['autoincrement'] = 'auto'  # 'auto' or True
            if default is not None:
                kwd['default'] = default
            elif null == 'NO' and default is None:
                kwd['default'] = ''
            if kwd.get('primary_key') and kwd.get('autoincrement'):
                self_dict['_primary_key'].append(field)  # 仅存储自增主键，一般的不存
            if not map.get(k):
                raise RuntimeError("Please send your table: " + table + " struct to yaophp@163.com to fix this bug")
            self_dict[field] = db.Column(map[k], **kwd)

        self_dict['__tablename__'] = table
        self_dict['__table_args__'] = {'extend_existing': True}
        return super(_FieldMeta, cls).__new__(cls, name, parent_tuple, self_dict)


class Model(db.Model, metaclass=_FieldMeta):
    """系统基本模型类，推荐使用该模型定义系统模型orm类
    如果要定义自定义基类模型，请显式定义 __abstract__ = True
    """
    __abstract__ = True

    _validate = []       # 自动验证(字段，规则，失败提示信息,['insert'|'update'|'both']) 若使用unique，推荐unique 和 'both'联用，create会自动识别insert或update的情况
    _auto = []           # 自动完成（字段，函数字符串/函数运行结果，['insert'|'update'|'both'],[默认auto自动执行，存在该值则字段不存在不执行])
    _error_msg = ''

    def __init__(self,**kwargs):
        self._initialize()
        if not kwargs:
            return

        # 要不要允许设置主键
        # for f in (i for i in self._model_field if i not in self._primary_key):
        #     if kwargs.get(f) is not None:
        #         setattr(self,f,kwargs.get(f))
        for f in self._model_field:
            if kwargs.get(f) is not None:
                setattr(self, f, kwargs[f])

    def _initialize(self,**kwargs): pass  # 预留初始化接口


    def create(self, types=None, **kwargs):
        """用于启动自动验证和自动完成"""
        if not kwargs:
            self._error_msg = '无数据输入'
            return False
        types = ['insert'] if types is None else list(types)
        if types == ['insert']:
            for t in self._primary_key:
                if getattr(self,t) is not None:
                    types = ['update']
                    break
            types.append('both')
        for field, rule, msg, type in self._validate:
            if type in types and field in kwargs.keys():
                if rule == 'unique':
                    result = self.query.filter_by(**{field: kwargs.get(field)}).first()
                    if result:
                        for pk in self._primary_key:
                            if result.__dict__.get(pk) != self.__dict__.get(pk):
                                self._error_msg = msg
                                return False
                else:
                    if not re.match(rule, str(kwargs.get(field))):
                        self._error_msg = msg
                        return False
        for field, func, type, *extra in self._auto:
            if type in types:
                if not extra:
                    setattr(self, field, func if not callable(eval(str(func))) else eval(func)())
                else:
                    kwargs[field] = func if not callable(eval(str(func))) else eval(func)(kwargs.get(field))
        for f in (i for i in self._model_field if i not in self._primary_key):
            if kwargs.get(f) is not None:
                setattr(self, f, kwargs[f])
        return True

    def get_error(self):
        return self._error_msg

    def orm_to_dict(self):
        """
        对查询结果orm对象转dict，仅限单条，若是多条要for遍历
        :param self:
        :return:
        """
        column_name_list = [
            value[0] for value in self._sa_instance_state.attrs.items()
            ]
        return dict(
            (column_name, getattr(self, column_name, None)) \
            for column_name in column_name_list
        )

    def query_to_dict(tuple, *args):
        """通常多表查询时指定字段的查询会返回包含tuple的list(实际上sqlalchemy.util._collections.result)
        将结果映射成dict
        也可以不转，因为他默认提供了遍历方法，具体dump出来看看他的_fields(注意，可以使用label修改同名字段)
        如：result = db.Q(M('user').name,M('role').name.label(role_name)).all()
        然后：for r in result:
                print(r.name, r.role_name)
        另外，sqlalchemy.util._collections.result 提供_asdict()可将结果装换成dict，效果比本函数好
        需要注意:如果查询时的字段有orm对象，则结果中包含orm对象
        """
        return list(map(lambda x: dict(zip(args, x)), tuple))

    # def __repr__(self):
    #     return ', '.join(['%s : %s' % (k,v) for k,v in self.__dict__.items() if k[0:1] != '_'])


def M(table):
    """
    M函数自动生成普通orm类，数据库中要存在该表
    如果要引用自定义高级orm类，请手动定义一个类继承Model并import
    :param table: 表名
    :return: orm类
    """
    global _APP_MODEL
    if table not in _APP_MODEL.keys():
        _APP_MODEL[table] = type(table, (Model,), {'__table_args__': {'extend_existing': True}})
    return _APP_MODEL[table]


def Q(*args):
    """安全使用Basequery查询数据库，
    为了使事务安全，应该获取一致session
    该session与M()、Model及继承Model的ORM类的session一致
    """
    return db.Query(args, db.session())

#####################################################
#
#       会话相关
#   启用的是服务端session，支持file、mysql、memcached
#   宁可使用flask默认的，也不建议使用flask_session那个扩展！
#####################################################


class _ServiceSessionClass(CallbackDict, SessionMixin):
    def __init__(self, id=None, data=None, expire=0):
        """
        默认的服务端session_class
        :param id: session id
        :param data: session data
        :param expire: session expire (timestamp)
        """
        self.id = id
        self.expire = expire
        def on_update(self):
            self.modified = True
        CallbackDict.__init__(self, data, on_update)
        self.modified = False

    def need_update(self, app):
        """用于判断是否要为活跃session续命"""
        return True if (self.expire - time.time()) * 4 < app.config.get('PERMANENT_SESSION_LIFETIME') else False


class _ServiceSessionIterface(SessionInterface):
    """session驱动基类"""
    session_class = _ServiceSessionClass

    def open_session(self, app, request):
        session_id = request.cookies.get(app.session_cookie_name)
        if not session_id:
            return self.session_class(self.uuid())
        result = self.open_handler(session_id)
        return result if result else self.session_class()

    def save_session(self, app, session, response):
        domain = self.get_cookie_domain(app)
        path = self.get_cookie_path(app)
        # Delete case.  If there is no session we bail early.
        # If the session was modified to be empty we remove the
        # whole cookie.
        if not session.id or not session:
            if not session.id or session.modified:
                response.delete_cookie(app.session_cookie_name,
                                       domain=domain, path=path)
            return

        if not self.should_set_cookie(app, session) and not session.need_update(app):
            return

        self.save_handler(session)
        if app.config.get('SESSION_GC_ENABLE') is True and random.randint(1,app.config.get('SESSION_GC_RANDINT', 1000)) == 1:
            self.gc_session()

        httponly = self.get_cookie_httponly(app)
        secure = self.get_cookie_secure(app)
        response.set_cookie(app.session_cookie_name, session.id,
                            expires=self.get_expire(), httponly=httponly,
                            domain=domain, path=path, secure=secure)

    def open_handler(self, session_id):
        """
        需实现
        :param session_id: session id
        :return: 返回session_class 对象
        """
        raise NotImplementedError()

    def save_handler(self, session):
        """
        需实现, 将session_class对象序列化后存储
        :param session: session_class 对象
        :return:
        """
        raise NotImplementedError()

    def gc_session(self):
        """
        需实现， 回收过期垃圾session
        :return:
        """
        raise NotImplementedError()

    def get_expire(self,timetype='timestamp'):
        """获取过期时间，默认return时间戳，输入参数则返回date"""
        # day = datetime.datetime.utcnow() + APP.permanent_session_lifetime
        # return time.mktime(day.timetuple()) if timetype == 'timestamp' else day
        return time.time() + APP.config.get('PERMANENT_SESSION_LIFETIME')

    def uuid(self):
        """生成session id，如果要跟php的应用通信，则修改"""
        return str(uuid.uuid4()).replace('-','')

    def dumps(self,data):
        return json.dumps(data).encode()

    def loads(self,data):
        return json.loads(data.decode())


class MysqlSessionInterface(_ServiceSessionIterface):
    """数据结构同Thinkphp的mysql的session驱动，可实现与PHP应用共享
    create table if not exists session(
        session_id char(64) not null primary key,
        session_data blod
        session_expire int(10) unsigned not null
    )engine=myisam default charset=utf8 comment='session表'
    """

    def __init__(self):
        self.Table = M(APP.config.get('SESSION_CACHE_TABLE', 'session'))

    def open_handler(self, session_id):
        result = self.Table.query.filter(self.Table.session_id == session_id).first()
        if result and result.session_expire >= int(time.time()):
            if result.session_expire >= int(time.time()):
                data = self.loads(result.session_data)
                return self.session_class(session_id, data, result.session_expire)
            else:  # 过期
                self.Table.query.session.delete(result)
                self.Table.query.session.commit()
                return self.session_class()
        else:
            return self.session_class()

    def save_handler(self, session):
        result = self.Table.query.filter(self.Table.session_id == session.id).first()
        if result and result.session_expire >= int(time.time()):
            self.Table.query.filter_by(session_id=session.id).update({'session_data': self.dumps(session),'session_expire': self.get_expire()})
            self.Table.query.session.commit()
        else:
            self.Table.query.session.add(self.Table(session_id=session.id, session_data=self.dumps(session),session_expire=self.get_expire()))
            self.Table.query.session.commit()

    def gc_session(self):
        try:
            self.Table.query.filter(self.Table.session_expire < int(time.time())).delete()
            self.Table.query.session.commit()
        except:
            self.Table.query.session.rollback()


class MemcachedSessionInterface(_ServiceSessionIterface):
    """鉴于memcached的特殊，需手动加入时间戳实现给session续命
    注意：如果重启memcached服务，需要重启应用
    """
    def __init__(self):
        servers = APP.config.get('MEMCACHED_HOST')
        if servers is None or isinstance(servers, (list, tuple)):
            if servers is None:
                servers = ['127.0.0.1:11211']
            self.cache = self.engin(servers)
            if self.cache is None:
                raise RuntimeError('no memcache module found')
        else:
            # NOTE: servers is actually an already initialized memcache
            # client.
            self.cache = servers

        self._key_prefix = APP.config.get('SESSION_KEY_PREFIX','session_')
        # 测试链接
        if not self.cache.set('test_connect', 'memcached is ok!', 30):
            raise RuntimeError("memcached connect failed! please check your memcached service status")

    def engin(self, servers):
        try:
            import pylibmc
        except ImportError:
            pass
        else:
            return pylibmc.Client(servers)

        try:
            from google.appengine.api import memcache
        except ImportError:
            pass
        else:
            return memcache.Client()

        try:
            import memcache
        except ImportError:
            pass
        else:
            return memcache.Client(servers)

    def dumps(self, data):
        """重写该方法"""
        return json.dumps({'data': data, 'expire': self.get_expire()})

    def loads(self, data):
        """重写该方法"""
        return json.loads(data)

    def open_handler(self, session_id):
        result = self.cache.get(self._key_prefix + session_id)
        if result:
            data = self.loads(result)
            return self.session_class(session_id, data['data'], data['expire'])
        else:
            return self.session_class()

    def save_handler(self, session):
        return self.cache.set(self._key_prefix + session.id, self.dumps(session), self.get_expire())

    def gc_session(self):
        """memcached会自己处理垃圾"""
        return


class FileSessionInterface(_ServiceSessionIterface):
        """session服务器端文件类型驱动"""
        def __init__(self):
            self.session_dir = APP.config.get('SESSION_CACHE_PATH') if APP.config.get('SESSION_CACHE_PATH') else os.path.join(os.getcwd(), 'runtime', 'session')
            # self.session_dir = session_dir if session_dir else os.path.join(os.getcwd(), 'runtime', 'session')
            try:
                if not os.path.isdir(self.session_dir):
                    os.makedirs(self.session_dir)
            except OSError as ex:
                if ex.errno != errno.EEXIST:
                    raise

        def open_handler(self, session_id):
            file = os.path.join(self.session_dir, session_id)
            if os.path.isfile(file):
                try:
                    expire = os.stat(file).st_mtime + APP.config.get('PERMANENT_SESSION_LIFETIME')
                    if expire > time.time():
                        with open(file, 'rb') as f:
                            data = f.read()
                        return self.session_class(session_id, self.loads(data), expire)
                    else:
                        os.remove(file)
                        return self.session_class()
                except (IOError, OSError):
                    return self.session_class()
            else:
                return self.session_class()


        def save_handler(self, session):
            try:
                with open(os.path.join(self.session_dir, session.id),'wb') as f:
                    f.write(self.dumps(session))
            except (IOError, OSError):
                pass

        def gc_session(self):
            """垃圾回收"""
            expire = APP.config.get('PERMANENT_SESSION_LIFETIME', 60*60*2)
            now = time.time()
            for x in (os.path.join(self.session_dir, i) for i in os.listdir(self.session_dir)):
                try:
                    if os.stat(x).st_mtime + expire < now:
                        os.remove(x)
                except (IOError, OSError):
                    continue


APP.session_interface = FileSessionInterface()


############################################
#
#           其他扩展
#
#############################################
def show_page(paginate, viewfunc=None, **kwargs):
    """
    分页函数，注意jinja默认对模板变量过滤，请对该变量使用|safe
    需注意：flask_sqlalchemy查询绑定的是Basequery才有paginate方法，
    原生的sqlalchemy的query是没有该属性的,而本框架的Q函数是封装的Basequery，推荐使用：
    You can still use sqlalchemy and sqlalchemy.orm directly,
    but note that Flask-SQLAlchemy customizations are available only through an instance of this SQLAlchemy class.
    Query classes default to BaseQuery for db.Query, db.Model.query_class,
    and the default query_class for db.relationship and db.backref.
    :param paginate: query分页方法返回的对象
    :param viewfunc: 默认是当前请求的路由的分页，可手动指定
    :return: str
    """
    if not viewfunc:
        viewfunc = request.endpoint
    p = ''
    args = request.view_args.copy()
    left_edge = kwargs.get('left_edge',1)
    left_current = kwargs.get('left_current',4)
    right_current = kwargs.get('right_current',5)
    right_edge = kwargs.get('right_edge',1)
    for page in paginate.iter_pages(left_edge, left_current, right_current, right_edge):
        if page:
            if page != paginate.page:
                args['page'] = page
                p += "<a href=' " + url_for(viewfunc, **args) +" '>"+ str(page) +"</a>"
            else:
                p += "<span><strong>" + str(page) + "</strong></span>"
        else:
            pass
            # p += "<strong  class=ellipsis>…</strong>"
    if paginate.has_prev:
        args['page'] = paginate.prev_num
        p += "<a href=' " + url_for(viewfunc, **args) + " '>上一页</a>"
    if paginate.has_next:
        args['page'] = paginate.next_num
        p += "<a href=' " + url_for(viewfunc, **args) + " '>下一页</a>"
    return p

flask_sqlalchemy.Pagination.show_page = show_page


def _tips(*args):
    args = list(args)

    def func(*ar):
        for k, v in enumerate(ar):
            args[k] = v
        if IS_('ajax'):
            return jsonify(info=args[0], url=args[1], status=args[4])
        else:
            return render_template(args[3], info=args[0], url=args[1], time=args[2], status=args[4])
    return func
success = _tips('操作成功', '', 1, APP.config.setdefault('TMPL_SUCCESS', 'tips.html'), 1)
error = _tips('操作失败', '', 3, APP.config.setdefault('TMPL_ERROR', 'tips.html'), 0)


# alias别名
U = url_for
ajaxReturn = jsonify


def get_client_ip(*args,**kwargs):
    return request.remote_addr


# 模板过滤函数注册
# 或者使用 APP.add_template_filter(date)
@APP.template_filter('date')
def date(timestamp=0, format=''):
    """
    时间戳转日期
    :param timestamp: 时间戳
    :param format:  日期格式
    :return: 格式化的日期字符串
    """
    t = time.localtime(timestamp) if timestamp else time.localtime()
    f = format if format else '%Y-%m-%d %H:%M:%S'
    return time.strftime(f, t)


@APP.errorhandler(404)
def error_page(error):
    return render_template('404.html'), 404


class PHPResponse(Response):
    """自定义响应方式"""
    def __init__(self,response=None, status=None, headers=None, mimetype=None, content_type=None, direct_passthrough=False):
        super(PHPResponse, self).__init__(response, status, headers, mimetype, content_type, direct_passthrough)
        self.headers['X-Power-By'] = 'PHP/5.4.41'


def php_lover():
    """无意义，仅演示自定义Response用法"""
    if APP.config.get('PHP_LOVER'):
        APP.config['SESSION_COOKIE_NAME'] = 'PHPSESSID'
        APP.response_class = PHPResponse
php_lover()

