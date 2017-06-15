"""
intelligently parses command lines

flags: true/false values
options: other specified value (e.g. user name)
"""
# imports
from __future__ import print_function

import sys
py_ver = sys.version_info[:2]
is_win = sys.platform.startswith('win')
if is_win:
    import signal
    KILL_SIGNALS = [getattr(signal, sig) for sig in ('SIGTERM') if hasattr(signal, sig)]
    from subprocess import Popen, PIPE
else:
    from pty import fork
    import resource
    import termios
    # from syslog import syslog
    import signal
    KILL_SIGNALS = [getattr(signal, sig) for sig in ('SIGTERM', 'SIGQUIT', 'SIGKILL') if hasattr(signal, sig)]
    from subprocess import Popen, PIPE
from threading import Thread
try:
    from Queue import Queue
except ImportError:
    from queue import Queue
import datetime
import email
import errno
import inspect
import locale
import logging
import os
import re
import shlex
import smtplib
import socket
import textwrap
import threading
import time
import traceback
from scription._aenum import Enum, IntEnum, AutoNumber, export
from math import floor
from sys import stdout, stderr

# locks, etc.
print_lock = threading.RLock()
io_lock = threading.Lock()

"""
(help, kind, abbrev, type, choices, usage_name, remove, default)

  - help --> the help message

  - kind --> what kind of parameter
    - flag       --> simple boolean
    - option     --> option_name value
    - multi      --> option_name value option_name value
    - required   --> required_name value

  - abbrev is a one-character string (defaults to first letter of
    argument)

  - type is a callable that converts the arguments to any Python
    type; by default there is no conversion and type is effectively str

  - choices is a discrete sequence of values used to restrict the
    number of the valid options; by default there are no restrictions
    (i.e. choices=None)

  - usage_name is used as the name of the parameter in the help message

  - remove determines if this argument is removed from sys.argv

  - default is the default value, either converted with type if type is
    specified, or type becomes the default value's type if unspecified
"""

version = 0, 80, 5

# data
__all__ = (
    'Alias', 'Command', 'Script', 'Main', 'Run', 'Spec',
    'Bool','InputFile', 'OutputFile', 'IniError', 'IniFile', 'OrmError', 'OrmFile', 'NameSpace',
    'FLAG', 'KEYWORD', 'OPTION', 'MULTI', 'REQUIRED',
    'ScriptionError', 'ExecuteError', 'FailedPassword', 'TimeoutError', 'Execute', 'Job', 'ProgressView',
    'abort', 'echo', 'error', 'get_response', 'help', 'mail', 'user_ids', 'print',
    'stdout', 'stderr', 'wait_and_check', 'b', 'u',
    'Trivalent', 'Truthy', 'Unknown', 'Falsey', 'Exit',
    # the following are actually injected directly into the calling module, but are
    # added here as well for pylakes' benefit
    'script_main',          # Script decorator instance if used
    'script_commands',      # defined commands
    'script_command',       # callback to run chosen command function
    'script_command_name',  # name of above
    'script_fullname',      # sys.argv[0]
    'script_name',          # above without path
    'script_verbosity',     # vebosity level from command line
    'script_module',        # module that imported scription
    'module',               # same as above
    'script_abort_message', # copy of message sent to abort()
    'script_exception_lines', # traceback from unhandled exception
    )

VERBOSITY = 0
SCRIPTION_DEBUG = 0
LOCALE_ENCODING = locale.getpreferredencoding() or 'utf-8'
THREAD_STORAGE = threading.local()
THREAD_STORAGE.script_main = None

# bootstrap SCRIPTION_DEBUG
for arg in sys.argv:
    if arg.startswith(('--SCRIPTION_DEBUG', '--SCRIPTION-DEBUG')):
        SCRIPTION_DEBUG = 1
        if arg[17:] == '=2':
            SCRIPTION_DEBUG = 2
        elif arg[17:] == '=3':
            SCRIPTION_DEBUG = 3
        elif arg[17:] == '=4':
            SCRIPTION_DEBUG = 4
        elif arg[17:] == '=5':
            SCRIPTION_DEBUG = 5

module = script_module = script_main = script_commands = None
script_fullname = script_name = script_verbosity = script_command = script_command_name = None
script_abort_message = script_exception_lines = None

registered = False
run_once = False

# py 2/3 compatibility shims
raise_with_traceback = None
if py_ver < (3, 0):
    bytes = str
    b = str
    u = unicode
    from __builtin__ import print as _print
    exec(textwrap.dedent('''\
        def raise_with_traceback(exc, tb):
            raise exc, None, tb
            '''))
else:
    raw_input = input
    basestring = str
    unicode = str
    b = bytes
    u = unicode
    from builtins import print as _print
    exec(textwrap.dedent('''\
        def raise_with_traceback(exc, tb):
            raise exc.with_traceback(tb)
            '''))

class undefined(object):
    def __repr__(self):
        return '<undefined>'
    def __bool__(self):
        return False
    __nonzero__ = __bool__
undefined = undefined()

# back-compatibility
# the __version__ and __VERSION__ are for compatibility with existing code,
# but those names are reserved by the Python interpreter and should not be
# used
_version_strings = 'version', 'VERSION', '__version__', '__VERSION__'

# set logging
class NullHandler(logging.Handler):
    """
    This handler does nothing. It's intended to be used to avoid the
    "No handlers could be found for logger XXX" one-off warning. This is
    important for library code, which may contain code to log events. If a user
    of the library does not configure logging, the one-off warning might be
    produced; to avoid this, the library developer simply needs to instantiate
    a NullHandler and add it to the top-level logger of the library module or
    package.

    Taken from 2.7 lib.
    """
    def handle(self, record):
        """Stub."""

    def emit(self, record):
        """Stub."""

    def createLock(self):
        self.lock = None

logger = logging.getLogger('scription')
logger.addHandler(NullHandler())

# enumerations
class DocEnum(Enum):
    """
    compares equal to all cased versions of its name
    accepts a docstring for each member
    """
    _settings_ = AutoNumber

    def __init__(self, value, doc=None):
        # first, fix _value_
        self._value_ = self._name_.lower()
        self.__doc__ = doc

    def __eq__(self, other):
        if isinstance(other, basestring):
            return self._value_ == other.lower()
        elif isinstance(other, self.__class__):
            return self is other
        else:
            return NotImplemented

    def __ne__(self, other):
        return not self == other

    def __repr__(self):
        return '<%s.%s>' % (self.__class__.__name__, self._name_)

@export(globals())
class Exit(IntEnum):
    '''
    Non-zero values indicate an error
    '''
    _init_ = 'value __doc__'
    _ignore_ = 'v name text sig'

    Success         =   0, 'ran successfully'
    Unknown         =   1, 'unspecified error'
    ScriptionError  =  63, 'fatal scription error'
    Usage           =  64, 'command line usage error'
    DataError       =  65, 'data format error'
    NoInput         =  66, 'cannot open input'
    NoUser          =  67, 'user unknown'
    NoHost          =  68, 'host unknown'
    Unavailable     =  69, 'service unavailable'
    Software        =  70, 'internal error'
    OsError         =  71, 'system error'
    OsFile          =  72, 'critical OS file missing'
    CantCreate      =  73, 'cannot create (user) output file'
    IoError         =  74, 'input/output error'
    TempFail        =  75, 'temp failure; user is invited to retry'
    Protocol        =  76, 'remote error in protocol'
    NoPermission    =  77, 'permission denied'
    Config          =  78, 'configuration error'
    CannotExecute   = 126, 'command invoked cannot execute'
    ExitOutOfRange  = 255, 'exit code out of range'
    InvalidExitCode = 127, 'invalid argument to exit'

    # add signal exit codes
    v = vars()
    for name, text in (
            ('SIGHUP',  'controlling process died'),
            ('SIGINT',  'interrupt from keyboard'),
            ('SIGQUIT', 'quit from keyboard'),
            ('SIGILL',  'illegal instruction (machine code)'),
            ('SIGABRT', 'abort from abort(3)'),
            ('SIGBUS',  'bus error (bad memory address)'),
            ('SIGFPE',  'floating point exception'),
            ('SIGKILL', 'kill'),
            ('SIGUSR1', 'user-defined signal 1'),
            ('SIGSEGV', 'invalid memory reference'),
            ('SIGUSR2', 'user-defined signal 2'),
            ('SIGPIPE', 'broken pipe, or write to read pipe'),
            ('SIGALRM', 'timer expired'),
            ('SIGTERM', 'terminate'),
            ('SIGCHILD', 'child error'),
        ):
        sig = getattr(signal, name, None)
        if sig is not None:
            v[name] = sig, name
        else:
            v['SIGNKWN'] = 128, 'invalid signal'

    def __bool__(self):
        return self.value == 0
    __nonzero__ = __bool__


@export(globals())
class SpecKind(DocEnum):
    REQUIRED = "required value"
    OPTION = "single value per name"
    MULTI = "multiple values per name (list form, no whitespace)"
    FLAG = "boolean/trivalent value per name"
    KEYWORD = 'unknown options'


# exceptions
class ExecuteError(Exception):
    "errors raised by Execute"
    def __init__(self, msg=None, process=None):
        self.process = process
        Exception.__init__(self, msg)

class FailedPassword(ExecuteError):
    "Bad or too few passwords"

class TimeoutError(ExecuteError):
    "Execute timed out"

ExecutionError = ExecuteError   # deprecated
ExecuteTimeout = TimeoutError   # deprecated

class OrmError(ValueError):
    """
    used to signify errors in the ORM file
    """

class ScriptionError(Exception):
    "raised for errors in user script"

# internal
def _add_annotations(func, annotations, script=False):
    '''
    add annotations as __scription__ to func
    '''
    params, varargs, keywords, defaults = inspect.getargspec(func)
    names = params
    if varargs:
        names.append(varargs)
    if keywords:
        names.append(keywords)
    errors = []
    for spec in annotations:
        if spec not in names:
            if not script:
                errors.append(spec)
            annotations[spec]._global = True
        else:
            annotations[spec]._global = False
    if errors:
        raise ScriptionError("names %r not in %s's signature" % (errors, func.__name__))
    func.__scription__ = annotations
    func.names = sorted(annotations.keys())
    func.all_params = sorted(names)
    func.named_params = sorted(params)

class empty(object):
    def __add__(self, other):
        # adding emptiness to something else is just something else
        return other
    def __nonzero__(self):
        return False
    __bool__ = __nonzero__
    def __repr__(self):
        return '<empty>'
    def __str__(self):
        return ''
empty = empty()

def _func_globals(func):
    '''
    return the function's globals
    '''
    if py_ver < (3, 0):
        return func.func_globals
    else:
        return func.__globals__

def _get_version(from_module, _try_other=True):
    for ver in _version_strings:
        if from_module.get(ver):
            version = getattr(from_module, ver)
            if not isinstance(version, basestring):
                version = '.'.join([str(x) for x in version])
            break
    else:
        # try to find package name
        try:
            package = os.path.split(os.path.split(sys.modules['__main__'].__file__)[0])[1]
        except IndexError:
            version = 'unknown'
        else:
            if package in sys.modules and any(hasattr(sys.modules[package], v) for v in _version_strings):
                version = sys.modules[package].version
                if not isinstance(version, basestring):
                    version = '.'.join([str(x) for x in version])
            elif _try_other:
                version = ' / '.join(_get_all_versions(from_module, _try_other=False))
            if not version.strip():
                version = 'unknown'
    return version + ' running on Python %s' % '.'.join([str(i) for i in sys.version_info])

def _get_all_versions(from_module, _try_other=True):
    versions = []
    for name, module in sys.modules.items():
        fm_obj = from_module.get(name)
        if fm_obj is module:
            for ver in _version_strings:
                if hasattr(module, ver):
                    version = getattr(module, ver)
                    if not isinstance(version, basestring):
                        version = '.'.join(['%s' % x for x in version])
                    versions.append('%s=%s' % (name, version))
                    break
    versions.append('python=%s' % '.'.join([str(i) for i in sys.version_info]))
    return versions

def _help(func):
    '''
    create help from __scription__ annotations and header defaults
    '''
    params, vararg, keywordarg, defaults = inspect.getargspec(func)
    params = func.params = list(params)
    vararg = func.vararg = [vararg] if vararg else []
    keywordarg = func.keywordarg = [keywordarg] if keywordarg else []
    # vararg_type = _identity
    # keywordarg_type = _identity
    annotations = func.__scription__
    pos = None
    max_pos = 0
    for i, name in enumerate(params + vararg + keywordarg):
        if name[0] == '_':
            # ignore private params
            continue
        spec = annotations.get(name, None)
        pos = None
        if spec is None:
            raise ScriptionError('%s not annotated' % name)
        help, kind, abbrev, arg_type, choices, usage_name, remove, default, envvar = spec
        if name in vararg:
            spec._type_default = tuple()
            if kind is empty:
                kind = 'multi'
        elif name in keywordarg:
            spec._type_default = dict()
            if kind is empty:
                kind = 'option'
        elif kind == 'required':
            pos = max_pos
            max_pos += 1
        elif kind == 'flag':
            if abbrev is empty:
                abbrev = (name[0], )
        elif kind == 'option':
            if abbrev is empty:
                abbrev = (name[0], )
        elif kind == 'multi':
            if abbrev is empty:
                abbrev = (name[0], )
            if default:
                if isinstance(default, list):
                    default = tuple(default)
                elif not isinstance(default, tuple):
                    default = (default, )
        else:
            raise ValueError('unknown kind: %r' % kind)
        for ab in abbrev or ():
            if ab in annotations:
               raise ScriptionError('duplicate abbreviations: %r' % abbrev)
        if usage_name is empty:
            usage_name = name.upper()
        if arg_type is _identity and default is not empty and default is not None:
            if kind == 'multi':
                if default:
                    arg_type = type(default[0])
            else:
                arg_type = type(default)
        spec._order = i
        spec.kind = kind
        spec.abbrev = abbrev
        spec.type = arg_type
        spec.usage = usage_name
        spec._script_default = default
        if pos != max_pos:
            annotations[i] = spec
        annotations[name] = spec
        if abbrev not in (None, empty):
            for ab in abbrev:
                annotations[ab] = spec
    usage_max = 0
    help_max = 0
    for annote in annotations.values():
        usage_max = max(usage_max, len(annote.usage))
        help_max = max(help_max, len(annote.help))
    func._var_arg = func._kwd_arg = None
    if vararg:
        func._var_arg = annotations[vararg[0]]
    if keywordarg:
        func._kwd_arg = annotations[keywordarg[0]]
    if defaults:
        # check the defaults in the header
        for name, dflt in zip(reversed(params), reversed(defaults)):
            if name[0] == '_':
                # ignore private params
                continue
            annote = annotations[name]
            if annote._script_default:
                # default specified in two places
                raise ScriptionError('default value for %s specified in Spec and in header (%r, %r)' %
                        (name, annote._script_default, dflt))
            annote._use_default = True
            if annote.kind != 'multi':
                if annote.type is _identity and dflt is not None:
                    annote.type = type(dflt)
                annote._script_default = annote.type(dflt)
            else:
                if dflt is None:
                    annote._script_default = dflt
                else:
                    if not isinstance(dflt, tuple):
                        dflt = (dflt, )
                    if annote.type is _identity and dflt:
                        annote.type = type(dflt[0])
                    new_dflt = []
                    for d in dflt:
                        new_dflt.append(annote.type(d))
                    annote._script_default = tuple(new_dflt)
    # if vararg:
    #     vararg_type = annotations[vararg[0]].type
    # if keywordarg:
    #     kywd_func = annotations[keywordarg[0]].type
    #     if isinstance(kywd_func, tuple):
    #         keywordarg_type = lambda k, v: (kywd_func[0](k), kywd_func[1](v))
    #     else:
    #         keywordarg_type = lambda k, v: (k, kywd_func(v))
    # also prepare help for global options
    global_params = [n for n in func.names if n not in func.all_params]
    print_params = []
    for param in global_params + params:
        if param[0] == '_':
            # ignore private params
            continue
        example = annotations[param].usage
        if annotations[param].kind == 'flag':
            print_params.append('--[no-]%s' % param)
        elif annotations[param].kind == 'option':
            print_params.append('--%s %s' % (param, example))
        elif annotations[param].kind == 'multi':
            print_params.append('--%s %s [--%s ...]' % (param, example, param))
        else:
            print_params.append(example)
    usage = print_params
    if vararg:
        usage.append("[%s [%s [...]]]" % (func._var_arg.usage, func._var_arg.usage))
    if keywordarg:
        usage.append("[name1=value1 [name2=value2 [...]]]")
    usage = [' '.join(usage), '']
    if func.__doc__:
        for line in func.__doc__.split('\n'):
            usage.append('    ' + line)
        usage.append('')
    for name in global_params + params + vararg + keywordarg:
        if name[0] == '_':
            # ignore private params
            continue
        annote = annotations[name]
        choices = ''
        if annote._script_default in (empty, None) or '[default: ' in annote.help:
            posi = ''
        elif not annote._use_default:
            posi = '[option default: ' + repr(annote._script_default) + ']'
        else:
            posi = '[default: ' + repr(annote._script_default) + ']'
        if annote.choices:
            choices = '[ %s ]' % ' | '.join(annote.choices)
        usage.append('    %-*s   %-*s   %s %s' % (
            usage_max,
            annote.usage,
            help_max,
            annote.help,
            posi,
            choices,
            ))
    func.max_pos = max_pos
    func.__usage__ = '\n'.join(usage)

def _identity(*args):
    if len(args) == 1:
        return args[0]
    return args

def _init_script_module(func):
    scription_debug('creating script_module', verbose=2)
    global script_module
    script_module = _func_globals(func)
    script_module['module'] = NameSpace(script_module)
    script_module['script_module'] = script_module['module']
    script_module['script_name'] = '<unknown>'
    script_module['script_main'] = THREAD_STORAGE.script_main
    script_module['script_commands'] = {}
    script_module['script_command'] = None
    script_module['script_command_name'] = ''
    script_module['script_fullname'] = ''
    script_module['script_verbosity'] = 0
    script_module['script_abort_message'] = ''
    script_module['script_exception_lines'] = []

class NameSpace(object):
    def __init__(self, wrapped_dict=None):
        if wrapped_dict is not None:
            self.__dict__ = wrapped_dict
    def __repr__(self):
        return '%s(%r)' % (self.__class__.__name__, self.__dict__)
    def __contains__(self, name):
        return name in self.__dict__
    def __iter__(self):
        for key, value in sorted(self.__dict__.items()):
            yield key, value
    def __getitem__(self, name):
        try:
            return self.__dict__[name]
        except KeyError:
            raise ScriptionError("namespace object has nothing named %r" % name)
    def __setitem__(self, name, value):
        self.__dict__[name] = value
    def get(self, key, default=None):
        # deprecated, will be removed by 1.0
        try:
            return self.__dict__[key]
        except KeyError:
            return default

def _rewrite_args(args):
    "prog -abc heh --foo bar  -->  prog -a -b -c heh --foo bar"
    new_args = []
    pass_through = False
    for arg in args:
        if arg == '--':
            pass_through = True
        if pass_through:
            new_args.append(arg)
            continue
        if arg.startswith('--') or not arg.startswith('-'):
            new_args.append(arg)
            continue
        for ch in arg[1:]:
            new_args.append('-%s' % ch)
    return new_args

def _run_once(func, args, kwds):
    scription_debug('creating run_once function')
    cache = []
    def later():
        scription_debug('running later')
        global run_once
        if run_once:
            scription_debug('returning cached value')
            return cache[0]
        run_once = True
        scription_debug('calling function')
        result = func(*args, **kwds)
        cache.append(result)
        return result
    scription_debug('returning <later>')
    return later

def _split_on_comma(text):
    scription_debug('_split_on_comma(%r)' % (text,), verbose=2)
    if ',' not in text:
        scription_debug('  -> %r' % ([text], ), verbose=2)
        return [text]
    elif '\\,' not in text:
        scription_debug('  -> %r' % text.split(','), verbose=2)
        return text.split(',')
    else:
        values = []
        new_value = []
        last_ch = None
        for ch in text+',':
            if last_ch == '\\':
                new_value.append(ch)
            elif ch == '\\':
                pass
            elif ch == ',':
                values.append(''.join(new_value))
                new_value = []
            else:
                new_value.append(ch)
            last_ch = ch
        if new_value:
            raise ScriptionError('trailing "\\" in argument %r' % text)
        scription_debug('  -> %r' % values, verbose=2)
        return values

def _usage(func, param_line_args):
    global VERBOSITY, SCRIPTION_DEBUG
    Script = script_module['script_main']
    # Command = script_module['script_commands']
    program, param_line_args = param_line_args[0], _rewrite_args(param_line_args[1:])
    pos = 0
    max_pos = func.max_pos
    print_help = print_version = print_all_versions = False
    value = None
    annotations = func.__scription__
    var_arg_spec = kwd_arg_spec = None
    if Script and Script.command:
        var_arg_spec = getattr(Script.command, '_var_arg', None)
        kwd_arg_spec = getattr(Script.command, '_kwd_arg', None)
    if func._var_arg:
        var_arg_spec = func._var_arg
    if func._kwd_arg:
        kwd_arg_spec = func._kwd_arg
    if kwd_arg_spec:
        kwd_arg_spec._cli_value = {}
    to_be_removed = []
    all_to_varargs = False
    annote = last_item = None
    for offset, item in enumerate(param_line_args + [None]):
        original_item = item
        if value is not None:
            if item is None or item.startswith('-') or '=' in item:
                # check for default
                if annote._script_default:
                    annote._cli_value = annote._script_default
                else:
                    help('%s has no value' % last_item, Exit.ScriptionError)
            else:
                if annote.remove:
                    # only remove if not using the annotation default
                    to_be_removed.append(offset)
                value = item
                if annote.kind == 'option':
                    annote._cli_value = annote.type(value)
                elif annote.kind == 'multi':
                    values = [annote.type(a) for a in _split_on_comma(value)]
                    annote._cli_value += tuple(values)
                else:
                    raise ScriptionError("Error: %s's kind %r not in (multi, option)" % (last_item, annote.kind))
                value = None
                continue
        last_item = item
        if item is None:
            break
        elif item == '--':
            all_to_varargs = True
            continue
        if all_to_varargs:
            if var_arg_spec is None:
                help("don't know what to do with %r" % item, Exit.ScriptionError)
            var_arg_spec._cli_value += (var_arg_spec.type(item), )
            continue
        if item.startswith('-'):
            # (multi)option or flag
            if item.lower() == '--help' or item == '-h' and 'h' not in annotations:
                print_help = True
                continue
            elif item.lower() == '--version':
                print_version = True
                continue
            elif item.lower() in ('--all-versions', '--all_versions'):
                print_all_versions = True
                continue
            elif item == '-v' and 'v' not in annotations:
                VERBOSITY += 1
                continue
            item = item.lstrip('-')
            value = True
            if item.lower().startswith('no-') and '=' not in item:
                value = False
                item = item[3:]
            elif '=' in item:
                item, value = item.split('=', 1)
            item = item.replace('-','_')
            if item.lower() == 'verbose':
                try:
                    VERBOSITY = int(value)
                except ValueError:
                    help('invalid verbosity level: %r' % value, Exit.ScriptionError)
                value = None
                continue
            if item in annotations:
                annote = annotations[item]
            elif Script and item in Script.settings:
                annote = Script.settings[item]
            elif item in ('SCRIPTION_DEBUG', ):
                SCRIPTION_DEBUG = int(value)
                value = None
                continue
            else:
                help('%s not valid' % original_item, Exit.ScriptionError)
            if annote.remove:
                to_be_removed.append(offset)
            if annote.kind in ('multi', 'option'):
                if value is True:
                    last_item = item
                elif value is False:
                    annote._cli_value = annote._type_default
                    value = None
                else:
                    if annote.kind == 'option':
                        annote._cli_value = annote.type(value)
                    else:
                        # value could be a list of comma-separated values
                        scription_debug('_usage:multi ->', annote.type, verbose=2)
                        annote._cli_value += tuple([annote.type(a) for a in _split_on_comma(value)])
                        scription_debug('_usage:multi ->', annote._cli_value, verbose=2)
                    value = None
            elif annote.kind == 'flag':
                value = annote.type(value)
                annote._cli_value = value
                value = None
            else:
                help('%s argument %s should not be introduced with --' % (annote.kind, item), Exit.ScriptionError)
        elif '=' in item:
            # no lead dash, keyword args
            if kwd_arg_spec is None:
                help("don't know what to do with %r" % item, Exit.ScriptionError)
            item, value = item.split('=')
            item = item.replace('-','_')
            if item in func.named_params:
                help('%s must be specified as a %s' % (item, annotations[item].kind), Exit.ScriptionError)
            item, value = kwd_arg_spec.type(item, value)
            if not isinstance(item, str):
                help('keyword names must be strings', Exit.ScriptionError)
            kwd_arg_spec._cli_value[item] = value
            value = None
        else:
            # positional (required?) argument
            if pos < max_pos:
                annote = annotations[pos]
                if annote.remove:
                    to_be_removed.append(offset)
                # check for choices membership before transforming into a type
                if annote.choices and item not in annote.choices:
                    help('%s: %r not in [ %s ]' % (annote.usage, item, ' | '.join(annote.choices)), Exit.ScriptionError)
                item = annote.type(item)
                annote._cli_value = item
                pos += 1
            else:
                if var_arg_spec is None:
                    help("don't know what to do with %r" % item, Exit.ScriptionError)
                var_arg_spec._cli_value += (var_arg_spec.type(item), )
                all_to_varargs = True
    # exc = None
    if print_help:
        _print()
        if Script and Script.__usage__:
            _print('global options: ' + Script.__usage__ + '\n')
        _print('%s %s' % (program, func.__usage__))
        _print()
        sys.exit(Exit.Success)
    elif print_version:
        _print(_get_version(script_module['module']))
        sys.exit(Exit.Success)
    elif print_all_versions:
        _print('\n'.join(_get_all_versions(script_module)))
        sys.exit(Exit.Success)
    for setting in set(func.__scription__.values()):
        if setting.kind == 'required':
            setting.value
    if var_arg_spec and var_arg_spec.kind == 'required':
        var_arg_spec.value
    # remove any command line args that shouldn't be passed on
    new_args = []
    for i, arg in enumerate(param_line_args):
        if i not in to_be_removed:
            new_args.append(arg)
    sys.argv[1:] = new_args
    main_args, main_kwds = [], {}
    args, varargs = [], None
    if Script:
        for name in Script.names:
            annote = Script.settings[name]
            value = annote.value
            if annote._global:
                script_module[name] = value
            else:
                if annote is var_arg_spec:
                    varargs = value
                elif annote is kwd_arg_spec:
                    main_kwds = value
                else:
                    args.append(annote)
    args = [arg.value for arg in sorted(args, key=lambda a: a._order)]
    if varargs is not None:
        main_args = tuple(args) + varargs
    else:
        main_args = tuple(args)
    sub_args, sub_kwds = [], {}
    args, varargs = [], None
    for name in func.all_params:
        if name[0] == '_':
            # ignore private params
            continue
        annote = func.__scription__[name]
        value = annote.value
        if annote is var_arg_spec:
            varargs = value
        elif annote is kwd_arg_spec:
            sub_kwds = value
        else:
            args.append(annote)
    args = [arg.value for arg in sorted(args, key=lambda a: a._order)]
    if varargs is not None:
        sub_args = tuple(args) + varargs
    else:
        sub_args = tuple(args)
    return main_args, main_kwds, sub_args, sub_kwds

# API

## required
class Alias(object):
    "adds aliases for the function"
    def __init__(self, *aliases):
        scription_debug('recording aliases', aliases, verbose=2)
        self.aliases = aliases
    def __call__(self, func):
        scription_debug('applying aliases to', func.__name__, verbose=2)
        if script_module is None:
            _init_script_module(func)
        for alias in self.aliases:
            alias_name = alias.replace('_', '-')
            script_module['script_commands'][alias_name] = func
        return func


class Command(object):
    "adds __scription__ to decorated function, and adds func to Command.subcommands"
    def __init__(self, **annotations):
        scription_debug('Command -> initializing', verbose=1)
        scription_debug(annotations, verbose=2)
        for name, annotation in annotations.items():
            spec = Spec(annotation)
            annotations[name] = spec
        self.annotations = annotations
    def __call__(self, func):
        scription_debug('Command -> applying to', func.__name__, verbose=1)
        if script_module is None:
            _init_script_module(func)
        if func.__doc__ is not None:
            func.__doc__ = textwrap.dedent(func.__doc__).strip()
        _add_annotations(func, self.annotations)
        func_name = func.__name__.replace('_', '-')
        script_module['script_commands'][func_name] = func
        _help(func)
        return func


class Script(object):
    """
    adds __scription__ to decorated function, and stores func in self.command
    """
    def __init__(self, **settings):
        scription_debug('Script -> recording', verbose=1)
        scription_debug(settings, verbose=2)
        for name, annotation in settings.items():
            if isinstance(annotation, (Spec, tuple)):
                spec = Spec(annotation)
                if spec.kind == 'required':
                    # TODO:  allow this
                    raise ScriptionError('REQUIRED not (yet) allowed for Script')
            else:
                if isinstance(annotation, (bool, Trivalent)):
                    kind = 'flag'
                else:
                    kind = 'option'
                spec = Spec('', kind, None, type(annotation), default=annotation)
            if spec.usage is empty:
                spec.usage = name.upper()
            settings[name] = spec
        self.settings = settings
        self.names = sorted(settings.keys())
        num_keys = len(self.names)
        for i, name in enumerate(self.names):
            settings[name]._order = i + num_keys
        def dummy():
            pass
        _add_annotations(dummy, settings, script=True)
        _help(dummy)
        # self.names = dummy.names
        self.__usage__ = dummy.__usage__.strip()
        self.command = dummy
        self.all_params = dummy.all_params
        self.named_params = dummy.named_params
        self.settings = dummy.__scription__
        THREAD_STORAGE.script_main = self
    def __call__(self, func):
        scription_debug('Script -> applying to', func, verbose=1)
        THREAD_STORAGE.script_main = None
        if script_module is None:
            _init_script_module(func)
        func_name = func.__name__.replace('_', '-')
        if func_name in script_module['script_commands']:
            raise ScriptionError('%r cannot be both Command and Scription' % func_name)
        if func.__doc__ is not None:
            func.__doc__ = textwrap.dedent(func.__doc__).strip()
        _add_annotations(func, self.settings, script=True)
        _help(func)
        self.all_params = func.all_params
        self.named_params = func.named_params
        self.settings = func.__scription__
        self.__usage__ = func.__usage__.strip()
        self.command = func
        script_module['script_main'] = self
        return func


class Spec(object):
    """tuple with named attributes for representing a command-line paramter

    help, kind, abbrev, type, choices, usage_name, remove, default, envvar
    """

    def __init__(self,
            help=empty, kind=empty, abbrev=empty, type=empty,
            choices=empty, usage=empty, remove=False, default=empty,
            envvar=empty, force_default=empty,
            ):
        if isinstance(help, Spec):
            self.__dict__.update(help.__dict__)
            return
        if isinstance(help, tuple):
            args = list(help) + [empty] * (10 - len(help))
            help, kind, abbrev, type, choices, usage, remove, default, envvar, force_default = args
        if not help:
            help = ''
        if not kind:
            kind = 'required'
        if not type:
            type = _identity
        if not choices:
            choices = []
        arg_type_default = empty
        use_default = False
        if default is not empty and force_default == True:
            # support use of force_default as flag for default
            use_default = True
        elif force_default is not empty:
            # otherwise force_default is the always used default itself
            default = force_default
            use_default = True
        if kind not in ('required', 'option', 'multi', 'flag'):
            raise ScriptionError('unknown parameter kind: %r' % kind)
        if kind == 'flag':
            if type is Trivalent:
                arg_type_default = Unknown
            else:
                arg_type_default = False
                if type is _identity:
                    type = Bool
        elif kind == 'option':
            arg_type_default = None
        elif kind == 'multi':
            arg_type_default = tuple()
        elif default is not empty:
            arg_type_default = type(default)
        if abbrev not in(empty, None) and not isinstance(abbrev, tuple):
            abbrev = (abbrev, )
        self.help = help
        self.kind = kind
        self.abbrev = abbrev
        self.type = type
        self.choices = choices
        self.usage = usage
        self.remove = remove
        self._cli_value = empty
        self._script_default = default
        self._type_default = arg_type_default
        self._use_default = use_default
        self._global = False
        self._envvar = envvar

    def __iter__(self):
        return iter((self.help, self.kind, self.abbrev, self.type, self.choices, self.usage, self.remove, self._script_default, self._envvar))

    def __repr__(self):
        return "Spec(help=%r, kind=%r, abbrev=%r, type=%r, choices=%r, usage=%r, remove=%r, default=%r, envvar=%r)" % (
                self.help, self.kind, self.abbrev, self.type, self.choices, self.usage, self.remove, self._script_default, self._envvar)

    @property
    def value(self):
        if self._cli_value is not empty:
            value = self._cli_value
        elif self._envvar is not empty and pocket(value=os.environ.get(self._envvar)):
            value = pocket.value
            if self.kind == 'multi':
                value = tuple([self.type(v) for v in _split_on_comma(value)])
            else:
                value = self.type(value)
        elif self._script_default is not empty and self._use_default:
            value = self._script_default
        elif self._type_default is not empty:
            value = self._type_default
        else:
            raise ScriptionError('no value specified for %s' % self.usage)
        return value

def Main(module=None):
    "calls Run() only if the script is being run as __main__"
    scription_debug('Main entered')
    # TODO: replace the frame hack if a blessed way to know the calling
    # module is ever developed
    if module is None:
        try:
            module = sys._getframe(1).f_globals['__name__']
        except (AttributeError, KeyError):
            module = script_module['__name__']
    if module == '__main__':
        result = Run()
        sys.exit(result)


def Run():
    "parses command-line and compares with either func or, if None, script_module['script_main']"
    global SYS_ARGS
    scription_debug('Run entered')
    if globals().get('HAS_BEEN_RUN'):
        scription_debug('Run already called once, returning')
        return
    globals()['HAS_BEEN_RUN'] = True
    if py_ver < (3, 0):
        SYS_ARGS = [arg.decode(LOCALE_ENCODING) for arg in sys.argv]
    else:
        SYS_ARGS = sys.argv[:]
    Script = script_module['script_main']
    Command = script_module['script_commands']
    try:
        prog_path, prog_name = os.path.split(SYS_ARGS[0])
        if prog_name == '__main__.py':
            # started with python -m, get actual package name for prog_name
            prog_name = os.path.split(prog_path)[1]
        scription_debug(prog_name, verbose=2)
        script_module['script_fullname'] = SYS_ARGS[0]
        script_module['script_name'] = prog_name
        prog_name = prog_name.replace('_','-')
        if not Command:
            raise ScriptionError("no Commands defined in script")
        func_name = SYS_ARGS[1:2]
        if not func_name:
            func_name = None
        else:
            func_name = func_name[0].lower()
            if func_name == '--version':
                _print(_get_version(script_module['module']))
                sys.exit(Exit.Success)
            elif func_name in ('--all-versions', '--all_versions'):
                _print('\n'.join(_get_all_versions(script_module)))
                sys.exit(Exit.Success)
            else:
                func_name = func_name.replace('_', '-')
        func = Command.get(func_name)
        if func is not None:
            prog_name = SYS_ARGS[1].lower()
            param_line = [prog_name] + SYS_ARGS[2:]
        else:
            func = Command.get(prog_name.lower(), None)
            if func is not None and func_name != '--help':
                param_line = [prog_name] + SYS_ARGS[1:]
            else:
                prog_name_is_command = prog_name.lower() in Command
                if script_module['__doc__']:
                    _print(script_module['__doc__'].strip())
                if len(Command) == 1:
                    _detail_help = True
                else:
                    _detail_help = False
                    _name_length = max([len(name) for name in Command])
                if not (_detail_help or script_module['__doc__']):
                    _print("Available commands/options in", script_module['script_name'])
                if Script and Script.__usage__:
                    if _detail_help:
                        _print("\nglobal options: %s" % Script.__usage__)
                    else:
                        _print("\n   global options: %s\n" % Script.__usage__.split('\n')[0])
                for name, func in sorted(Command.items()):
                    if _detail_help:
                        if not (prog_name_is_command or name != prog_name) and len(Command) > 1:
                            continue
                            name = '%s %s' % (prog_name, name)
                        _print("\n%s %s" % (name, func.__usage__))
                    else:
                        doc = (func.__doc__ or func.__usage__.split('\n')[0]).split('\n')[0]
                        _print("   %*s  %s" % (-_name_length, name, doc))

                if func_name in ('-h', '--help'):
                    sys.exit(Exit.Success)
                else:
                    sys.exit(Exit.ScriptionError)
        main_args, main_kwds, sub_args, sub_kwds = _usage(func, param_line)
        main_cmd = Script and Script.command
        subcommand = _run_once(func, sub_args, sub_kwds)
        script_module['script_command'] = subcommand
        script_module['script_command_name'] = func.__name__
        script_module['script_verbosity'] = VERBOSITY
        if main_cmd:
            main_cmd(*main_args, **main_kwds)
        return subcommand()
    except Exception:
        exc = sys.exc_info()[1]
        scription_debug(exc)
        result = log_exception()
        script_module['script_exception_lines'] = result
        if isinstance(exc, ScriptionError):
            abort(str(exc), Exit.ScriptionError)
        raise


## optional
def Execute(args, cwd=None, password=None, input=None, timeout=None, pty=None, interactive=None, env=None, **new_env_vars):
    scription_debug('creating job:', args)
    job = Job(args, cwd=cwd, pty=pty, env=env, **new_env_vars)
    try:
        scription_debug('communicating')
        job.communicate(timeout=timeout, interactive=interactive, password=password, input=input)
    except TimeoutError:
        scription_debug('TimeoutError')
        pass
    finally:
        job.close()
    scription_debug('returning')
    return job

class Job(object):
    """
    if pty is True runs command in a forked process, otherwise runs in a subprocess
    """

    # subprocess is used record the process
    process = None
    returncode = None
    # if killed by a signal, record it
    signal = None
    # if job is no longer alive
    terminated = False
    # if job has been closed
    closed = False
    # str of stdout and stderr from job
    stdout = None
    stderr = None
    # any exception that occured (just the first one)
    exception = None

    def __init__(self, args, cwd=None, pty=None, env=None, **new_env_vars):
        # args        -> command to run
        # cwd         -> directory to run in
        # pty         -> False = subprocess, True = fork
        self._process_thread = None
        env = self.env = (env or os.environ).copy()
        if new_env_vars:
            env.update(new_env_vars)
        if pty and is_win:
            raise OSError("pty support for Job not currently implemented for Windows")
        self.kill_signals = list(KILL_SIGNALS)
        if isinstance(args, basestring):
            args = shlex.split(args)
        else:
            args = list(args)
        if not pty:
            # use subprocess
            scription_debug('subprocess args:', args)
            self.process = process = Popen(args, stdin=PIPE, stdout=PIPE, stderr=PIPE, cwd=cwd, env=env)
            self.pid = process.pid
            self.child_fd_out = process.stdout
            self.child_fd_in = process.stdin
            self.child_fd_err = process.stderr
            self.poll = self._log_wrap(process.poll, 'polling')
            self.terminate = self._log_wrap(process.terminate, 'terminating')
            self.kill = self._log_wrap(process.kill, 'killing')
            self.send_signal = self._log_wrap(process.send_signal, 'sending signal')
        else:
            error_read, error_write = os.pipe()
            self.pid, self.child_fd = fork()
            if self.pid == 0: # child process
                os.close(error_read)
                self.child_fd_out = sys.stdout.fileno()
                os.dup2(error_write, 2)
                os.close(error_write)
                self.error_pipe = 2
                try:
                    max_fd = resource.getrlimit(resource.RLIMIT_NOFILE)[1]
                    for fd in range(3, max_fd):
                        try:
                            os.close(fd)
                        except OSError:
                            pass
                    if cwd:
                        os.chdir(cwd)
                    if self.env:
                        os.execvpe(args[0], args, self.env)
                    else:
                        os.execvp(args[0], args)
                except Exception:
                    exc = sys.exc_info()[1]
                    self.write_error("%s:  %s" % (exc.__class__.__name__, ' - '.join([str(a) for a in exc.args])))
                    os._exit(-1)
            # parent process
            os.close(error_write)
            self.child_fd_out = self.child_fd
            self.child_fd_in = self.child_fd
            self.child_fd_err = error_read
        # start reading output
        self._all_output = Queue()
        self._all_input = Queue()
        self._stdout = []
        self._stderr = []
        self._stdout_history = []
        self._stderr_history = []
        def read_comm(name, channel, q):
            try:
                if isinstance(channel, int):
                    read = lambda size: os.read(channel, size)
                else:
                    read = channel.read
                while True:
                    scription_debug('reading', name)
                    data = read(1024)
                    with io_lock:
                        scription_debug('putting %s %r (%d bytes)' % (name, data, len(data)))
                        if not data:
                            data = None
                        q.put((name, data))
                        if data is None:
                            break
            except Exception:
                _, exc, tb = sys.exc_info()
                with io_lock:
                    q.put((name, None))
                    scription_debug('dying %s (from exception %s)' % (name, exc))
                    if not isinstance(exc, OSError) or exc.errno not in (errno.EBADF, errno.EIO):
                        raise self._set_exc(exc, tb)
        def write_comm(channel, q):
            try:
                if isinstance(channel, int):
                    write = lambda data: os.write(channel, data)
                    flush = lambda: ''
                else:
                    write = channel.write
                    flush = channel.flush
                while True:
                    scription_debug('stdin waiting')
                    data = q.get()
                    with io_lock:
                        if data is None:
                            scription_debug('dying stdin')
                            break
                        scription_debug('stdin writing', repr(data))
                        write(data)
                        flush()
            except Exception:
                _, exc, tb = sys.exc_info()
                raise self._set_exc(exc, tb)
        t = Thread(target=read_comm, name='stdout', args=('stdout', self.child_fd_out, self._all_output))
        t.daemon = True
        t.start()
        t = Thread(target=read_comm, name='stderr', args=('stderr', self.child_fd_err, self._all_output))
        t.daemon = True
        t.start()
        t = Thread(target=write_comm, name='stdin', args=(self.child_fd_in, self._all_input))
        t.daemon = True
        t.start()
        # do not add the stdin thread to the list of threads that automatically die if the job dies, as
        # it has to be manually ended

    def _log_wrap(self, func, msg):
        def wrapper(*args, **kwds):
            scription_debug(msg, args, kwds)
            return func(*args, **kwds)
        return wrapper

    def _set_exc(self, exc, tb=None):
        'sets self.exception if not already set, or unsets if exc is None'
        scription_debug('setting exception to: %r' % (exc,))
        if self.exception is None and exc is not None:
            self.exception = exc, tb
        elif exc is None:
            self.exception = None
        return exc

    def communicate(self, input=None, password=None, timeout=None, interactive=None, encoding='utf-8'):
        # password    -> single password or tuple of passwords (pty=True only)
        # timeout     -> raise exception of not complete in timeout seconds
        # interactive -> False = record only, 'echo' = echo output as we get it
        try:
            deadman_switch = None
            if timeout is not None:
                def prejudice():
                    scription_debug('timed out')
                    message = '\nTIMEOUT: process failed to complete in %s seconds\n' % timeout
                    with io_lock:
                        self._stderr.append(message)
                    self._set_exc(TimeoutError(message.strip()))
                    self.kill()
                deadman_switch = threading.Timer(timeout, prejudice)
                deadman_switch.name = 'deadman'
                deadman_switch.start()
            if self._process_thread is None:
                def process_comm():
                    active = 2
                    while active:
                        # check if any threads still alive
                        stream, data = self._all_output.get()
                        with io_lock:
                            if data is None:
                                active -= 1
                                scription_debug('dead thread:', stream)
                                continue
                            if encoding is not None:
                                data = data.decode(encoding)
                            scription_debug('adding %r to %s' % (data, stream))
                            if stream == 'stdout':
                                self._stdout.append(data)
                                if interactive == 'echo':
                                    echo(data, end='')
                                    sys.stdout.flush()
                            elif stream == 'stderr':
                                self._stderr.append(data)
                                if interactive == 'echo':
                                    echo(data, end='', file=stderr)
                                    sys.stderr.flush()
                            else:
                                try:
                                    raise Exception('unknown stream: %r' % stream)
                                except Exception:
                                    _, exc, tb = sys.exc_info()
                                    self._set_exc(exc, tb)
                                    self.kill()
                process_thread = self._process_thread = Thread(target=process_comm, name='process')
                process_thread.start()
            passwords = []
            if input is not None:
                if not isinstance(input, bytes):
                    input = input.encode('utf-8')
            if password is None:
                password = ()
            elif isinstance(password, basestring):
                password = (password, )
            for pwd in password:
                if not isinstance(pwd, bytes):
                    passwords.append((pwd + '\n').encode('utf-8'))
                else:
                    passwords.append(pwd + '\n'.encode('utf-8'))
            if passwords or input:
                while passwords:
                    if self.process:
                        # feed all passwords at once, after a short delay
                        time.sleep(0.1)
                        pwd = passwords[0]
                        for next_pwd in passwords[1:]:
                            pwd += next_pwd
                        try:
                            self.write(pwd, block=False)
                        except IOError:
                            # ignore write errors (probably due to password not needed and job finishing)
                            self._set_exc(None)
                        passwords = []
                    else:
                        try:
                            # pty -- look for echo off first
                            while self.get_echo() and self.is_alive():
                                time.sleep(0.1)
                            pw, passwords = passwords[0], passwords[1:]
                            self.write(pw, block=False)
                        except IOError:
                            # ignore get_echo and write errors (probably due to password not needed and job finishing)
                            self._set_exc(None)
                            break
                if input is not None:
                    time.sleep(0.1)
                    self.write(input, block=False)
                    time.sleep(0.1)
            scription_debug('joining process thread...')
            process_thread.join()
            scription_debug('process thread joined')
        finally:
            if deadman_switch is not None:
                scription_debug('cancelling deadman switch')
                deadman_switch.cancel()
                deadman_switch.join()
            scription_debug('closing job')
            self.close()
            if self.exception is not None:
                exc, tb = self.exception
                if tb is None:
                    raise exc
                else:
                    raise_with_traceback(exc, tb)

    def close(self, force=True):
        'parent method'
        try:
            if not self.closed:
                if self.is_alive():
                    self.terminate()
                    time.sleep(0.1)
                    if force and self.is_alive():
                        self.kill()
                        time.sleep(0.1)
                        self.is_alive()
                # shutdown stdin thread
                self._all_input.put(None)
                # close handles and pipes
                if self.process is not None:
                    self.child_fd_in.close()
                    self.child_fd_out.close()
                    self.child_fd_err.close()
                else:
                    for fd in (self.child_fd, self.child_fd_err):
                        try:
                            os.close(fd)
                        except OSError:
                            exc_type, exc, tb = sys.exc_info()
                            if exc_type is OSError and exc.errno == errno.EBADF:
                                pass
                            else:
                                self._set_exc(exc, tb)
                self.child_fd = -1
                self.child_fd_in = -1
                self.child_fd_out = -1
                self.child_fd_err = -1
                time.sleep(0.1)
                self.closed = True
        finally:
            with io_lock:
                scription_debug('saving stdout')
                self.stdout = ''.join(self._stdout).replace('\r\n', '\n')
                scription_debug('saving stderr')
                self.stderr = ''.join(self._stderr).replace('\r\n', '\n')

    def fileno(self):
        'parent method'
        return self.child_fd

    def get_echo(self):
        "return the child's terminal echo status (True is on) (parent method)"
        try:
            child_fd = self.child_fd
        except AttributeError:
            return True
        try:
            attr = termios.tcgetattr(child_fd)
        except Exception:
            _, exc, tb = sys.exc_info()
            raise self._set_exc(IOError(errno.EBADF, str(exc)), tb)
        else:
            if attr[3] & termios.ECHO:
                return True
        return False

    def isatty(self):
        'parent method'
        return os.isatty(self.child_fd)

    def is_alive(self):
        'parent method'
        time.sleep(0.1)
        if self.terminated:
            return False
        try:
            pid, status = os.waitpid(self.pid, os.WNOHANG)
        except Exception:
            _, exc, tb = sys.exc_info()
            if isinstance(exc, OSError) and exc.errno == errno.ECHILD:
                return False
            exc = ExecuteError(str(exc))
            raise self._set_exc(exc, tb)
        if pid != 0:
            self.signal = status % 256
            if self.signal:
                self.returncode = -self.signal
            else:
                self.returncode = status >> 8
            self.terminated = True
            return False
        return True

    def kill(self):
        '''kills child job, and self if child will not die

        parent method'''
        scription_debug('killing')
        for s in self.kill_signals:
            try:
                scription_debug('checking job for life')
                if not self.is_alive():
                    scription_debug('dead, exiting')
                    break
                scription_debug('killing with', s)
                self.send_signal(s)
                time.sleep(0.1)
            except Exception:
                cls, exc = sys.exc_info()[:2]
                scription_debug('received', exc)
                if cls in (IOError, OSError) and exc.errno in (errno.ESRCH, errno.ECHILD):
                    break
        else:
            # unable to kill job
            if self.exception is not None:
                message = self.exception[0].args[0]
            else:
                message = ''
            message = message.strip() + '; unable to kill job -- killing self\n'
            error(message)
            os.kill(os.getpid(), signal.SIGKILL)

    def poll(self):
        scription_debug('polling')
        if self.is_alive():
            return None
        else:
            return self.returncode

    def read(self, max_size, block=True, encoding='utf-8'):
        # if block is False, return None if no data ready
        # otherwise, encode to string with encoding, or raw if
        # encoding is None
        #
        # check for any unread data
        while "looking for data":
            while self._all_output.qsize() or block:
                stream, data = self._all_output.get()
                if encoding is not None:
                    data = data.decode(encoding)
                if stream == 'stdout':
                    self._stdout.append(data)
                elif stream == 'stderr':
                    self._stderr.append(data)
                else:
                    try:
                        raise Exception('unknown stream: %r' % stream)
                    except Exception:
                        _, exc, tb = sys.exc_info()
                        raise self._set_exc(exc, tb)
                if self._stdout:
                    break
            if self._stdout:
                # TODO: make test case to expose below bug (self.pop)
                data = self.pop(0)
                if len(data) > max_size:
                    # trim
                    self._stdout.insert(0, data[max_size:])
                self._stdout_history.append(data)
                return data
            elif not block:
                return None

    def send_signal(self, signal):
        "parent method"
        scription_debug('sending signal:', signal)
        os.kill(self.pid, signal)
        time.sleep(0.1)

    def terminate(self):
        'parent method'
        scription_debug('terminating')
        if self.is_alive() and self.kill_signals:
            sig = self.kill_signals[0]
            os.kill(self.pid, sig)
            time.sleep(0.1)

    def write(self, data, block=True):
        'parent method'
        if not self.is_alive():
            try:
                raise IOError(errno.EPIPE, 'Broken pipe.')
            except Exception:
                _, exc, tb = sys.exc_info()
                raise self._set_exc(exc, tb)
        if not isinstance(data, bytes):
            data = data.encode('utf-8')
        self._all_input.put(data)
        if block:
            while not self._all_input.empty():
                time.sleep(0.1)
        return len(data)

    def write_error(self, data):
        'child method'
        if not isinstance(data, bytes):
            data = data.encode('utf-8')
        os.write(self.error_pipe, data)

class OrmFile(object):
    """
    lightweight ORM for scalar values

    read and make available the settings of a configuration file,
    converting the values as str, int, float, date, time, or
    datetime based on:
      - presence of quotes
      - presence of colons and/or hyphens
      - presence of period
    """
    _str = unicode
    _path = unicode
    _date = datetime.date
    _time = datetime.time
    _datetime = datetime.datetime
    _bool = bool
    _float = float
    _int = int

    def __init__(self, filename, section=None, export_to=None, types={}, encoding='utf-8'):
        # if section, only return defaults merged with section
        # if export_to, it should be a mapping, and will be populated
        # with the settings
        # if types, use those instead of the default orm types
        for n, t in types.items():
            if n not in (
                    '_str', '_path', '_date', '_time', '_datetime',
                    '_bool', '_float', '_int',
                    ):
                raise TypeError('invalid orm type: %r' % n)
            setattr(self, n, t)
        if section:
            section = section.lower()
        target_section = section
        self._section = target_section
        self._filename = filename
        defaults = {}
        settings = self._settings = NameSpace()
        if py_ver < (3, 0):
            fh = open(filename)
        else:
            fh = open(filename, encoding=encoding)
        try:
            section = None
            for line in fh:
                if py_ver < (3, 0):
                    line = line.decode(encoding)
                line = line.strip()
                if not line or line.startswith(('#',';')):
                    continue
                if line[0] + line[-1] == '[]':
                    # section header
                    section = self._verify_section_header(line[1:-1])
                    if target_section is None:
                        new_section = NameSpace()
                        for key, value in defaults.items():
                            setattr(new_section, key, value)
                        setattr(settings, section, new_section)
                else:
                    # setting
                    name, value = line.split('=', 1)
                    name = self._verify_name(name)
                    value = self._verify_value(value)
                    if section:
                        if target_section is None:
                            setattr(new_section, name, value)
                        elif target_section == section:
                            setattr(settings, name, value)
                    else:
                        setattr(settings, name, value)
                        defaults[name] = value
        finally:
            fh.close()
        if export_to is not None:
            for name, value in settings.__dict__.items():
                if name[0] != '_':
                    export_to[name] = value

    def __repr__(self):
        if self._section is None:
            return '%s(%r)' % (self.__class__.__name__, self._filename)
        else:
            return '%s(%r, section=%r)' % (self.__class__.__name__, self._filename, self._section)

    def __iter__(self):
        values = []
        sections = []
        for key, value in self._settings:
            if isinstance(value, NameSpace):
                sections.append((key, value))
            else:
                values.append((key, value))
        for key, value in values:
            yield key, value
        for key, value in sections:
            yield key, value
        return
        raise Exception('%s: iteration not supported' % self.__class__.__name__)

    def __getattr__(self, name):
        name = name.lower()
        if name in self._settings.__dict__:
            return getattr(self._settings, name)
        raise OrmError("'settings' has no section/default named %r" % name)

    def __getitem__(self, name):
        return self._settings[name]

    def __setattr__(self, name, value):
        if name in (
                '_settings', '_filename', '_section',
                '_str', '_path', '_date', '_time', '_datetime', '_bool', '_float', '_int',
                ):
            object.__setattr__(self, name, value)
        else:
            self._settings[name] = value

    def __setitem__(self, name, value):
        self._settings[name] = value

    def _verify_name(self, name):
        name = name.strip().lower()
        if not name[0].isalpha():
            raise OrmError('names must start with a letter')
        if re.sub('\w*', '', name):
            # illegal characters in name
            raise OrmError('names can only contain letters, digits, and the underscore [%r]' % name)
        return name

    def _verify_section_header(self, section):
        section = section.strip().lower()
        if not section[0].isalpha():
            raise OrmError('names must start with a letter')
        if re.sub('\w*', '', section):
            # illegal characters in section
            raise OrmError('names can only contain letters, digits, and the underscore [%r]' % section)
        if section in self.__dict__:
            # section already exists
            raise OrmError('section %r is a duplicate, or already exists as a default value' % section)
        return section

    def _verify_value(self, value):
        # quotes indicate a string
        # / or \ indicates a path
        # : or - indicates time, date, datetime
        # . indicates float
        # True/False indicates True/False
        # anything else is fed through int()
        value = value.strip()
        if value[0] in ('"', "'"):
            # definitely a string
            if value[0] != value[-1]:
                raise OrmError('string must be quoted at both ends [%r]' % value)
            start, end = 1, -1
            if value[:3] in ('"""', "'''"):
                if value[:3] != value[-3:] or len(value) < 6:
                    raise OrmError('invalid string value: %r' % value)
                start, end = 3, -3
            return self._str(value[start:end])
        elif '/' in value or '\\' in value:
            # path
            return self._path(value)
        elif ':' in value and '-' in value:
            # datetime
            try:
                date = map(int, value[:10].split('-'))
                time = map(int, value[11:].split(':'))
                return self._datetime(*(date+time))
            except ValueError:
                raise OrmError('invalid datetime value: %r' % value)
        elif '-' in value:
            # date
            try:
                date = map(int, value.split('-'))
                return self._date(date)
            except ValueError:
                raise OrmError('invalid date value: %r' % value)
        elif ':' in value:
            # time
            try:
                time = map(int, value.split(':'))
                return self._time(*time)
            except ValueError:
                raise OrmError('invalid time value: %r' % value)
        elif '.' in value:
            # float
            try:
                value = self._float(value)
            except ValueError:
                raise OrmError('invalid float value: %r' % value)
        elif value.lower() == 'true':
            # boolean - True
            return self._bool(True)
        elif value.lower() in ('false', ''):
            # boolean - False
            return self._bool(False)
        elif any(c.isdigit() for c in value):
            # int
            try:
                return self._int(value)
            except ValueError:
                raise OrmError('invalid integer value: %r' % value)
        else:
            # must be a string
            return value
IniError = OrmError     # deprecated, will be removed by 1.0
IniFile = OrmFile       # deprecated, will be removed by 1.0

class ProgressView(object):
    """
    Displays progress as a bar or a numeric count.
    """
    ViewType = Enum('ViewType', (('Bar', 'bar'), ('Percent', 'percent'), ('Count', 'count')))
    export(ViewType, vars())

    def __init__(self, total=None, view_type='count', message=None, bar_char='*', iterable=None):
        try:
            os.ttyname(stdout.fileno())
            headless = False
        except OSError:
            headless = True
        if total is None and iterable is None:
            raise ValueError('total must be specified if not wrapping an iterable')
        elif total is None:
            try:
                total = len(iterable)
            except TypeError:
                get_hint = getattr(iterable, '__length_hint__', None)
                try:
                    total = get_hint(iterable)
                except TypeError:
                    pass
                if total is None:
                    view_type = 'count'
        self.blank = VERBOSITY < 1
        self.iterator = iter(iterable)
        self.current_count = 0
        self.total = total
        self.blockcount = 0
        self.bar_char = bar_char
        self.view_type = self.ViewType(view_type)
        self.last_percent = 0
        self.last_count = 0
        self.last_time = time.time()
        self.f = sys.stdout
        if not self.blank:
            if message is not None:
                if total is not None:
                    message = message.replace('$total', str(total))
                else:
                    message = ' '.join([w for w in message.split() if w != '$total'])
                self.f.write('\n%s' % message)
                if headless:
                    if total is not None:
                        self.f.write(': %s\n' % (total, ))
                    else:
                        self.f.write('\n')
                    self.blank = True
                    return
                if self.view_type is not self.Bar:
                    self.f.write(': ')
            if self.view_type is self.Percent:
                self.progress = self._bar_progress
                self.f.write('  0%')
            elif self.view_type is self.Bar:
                self.progress = self._bar_progress
                self.f.write('\n-------------------- % Progress ---------------- 1\n')
                self.f.write('    1    2    3    4    5    6    7    8    9    0\n')
                self.f.write('    0    0    0    0    0    0    0    0    0    0\n')
            elif self.view_type is self.Count:
                self.progress = self._count_progress
                self.time = time.time()
                self.f.write('0')
            else:
                raise Exception('unknown value for view_type: %r' % self.view_type)
            self.f.flush()

    def __iter__(self):
        return self

    def __next__(self):
        try:
            obj = next(self.iterator)
        except StopIteration:
            self.progress(self.current_count, done=True)
            raise
        self.progress(self.current_count+1)
        return obj
    next = __next__

    def _count_progress(self, count, done=False):
        """
        Calculate current count, update views.
        """
        if self.blank:
            return
        self.current_count = count
        now = time.time()
        if now - self.last_time < 1 and not done:
            return
        self.f.write(''*len(str(self.last_count))+str(count))
        self.f.flush()
        self.last_count = count
        self.last_time = now
        if done:
            self.f.write('\n')
            self.f.flush()

    def _bar_progress(self, count, done=False):
        """
        Calculate current percent, update views.
        """
        if self.blank:
            return
        self.current_count = count
        count = min(count, self.total)
        if self.total == count or not self.total:
            complete = 100
        else:
            complete = int(floor(100.0*count/self.total))
        if complete <= self.last_percent:
            return
        self.last_percent = complete
        if self.view_type is self.Percent:
            self.f.write('%3d%%' % complete)
        elif self.view_type is self.Bar:
            blockcount = int(complete//2)
            if blockcount <= self.blockcount:
                return
            for i in range(self.blockcount, blockcount):
                self.f.write(self.bar_char)
            self.blockcount = blockcount
        else:
            raise Exception('unknown value for view_type: %r' % self.view_type)
        if complete == 100:
            self.f.write('\n')
        self.f.flush()

    def progress(self, count, done=False):
        if done:
            self.f.write('\n')
            self.f.flush()
        pass

    def tick(self):
        """
        Add one to counter, possibly update view.
        """
        self.current_count += 1
        self.progress(self.current_count)


class Trivalent(object):
    """
    three-value logic

    Accepts values of True, False, or None/empty.
    boolean value of Unknown is Unknown, and will raise.
    Truthy value is +1
    Unknown value is 0
    Falsey value is -1
    """
    def __new__(cls, value=None):
        if isinstance(value, cls):
            return value
        elif value in (None, empty):
            return cls.unknown
        elif isinstance(value, bool):
            return (cls.false, cls.true)[value]
        elif value in (-1, 0, +1):
            return (cls.unknown, cls.true, cls.false)[value]
        elif isinstance(value, basestring):
            if value.lower() in ('t', 'true', 'y', 'yes', 'on'):
                return cls.true
            elif value.lower() in ('f', 'false', 'n', 'no', 'off'):
                return cls.false
            elif value.lower() in ('?', 'unknown', 'null', 'none', ' ', ''):
                return cls.unknown
        raise ValueError('unknown value for %s: %s' % (cls.__name__, value))

    def __hash__(x):
        return hash(x.value)

    def __index__(x):
        return x.value

    def __int__(x):
        return x.value

    def __invert__(x):
        cls = x.__class__
        if x is cls.true:
            return cls.false
        elif x is cls.false:
            return cls.true
        return x

    def __and__(x, y):
        """
        AND (conjunction) x & y:
        True iff both x,y are True
        False iff at least one of x,y is False

              F   U   T
         ---+---+---+---
         F  | F | F | F
         ---+---+---+---
         U  | F | U | U
         ---+---+---+---
         T  | F | U | T
        """
        cls = x.__class__
        if not isinstance(y, cls) and y not in (None, empty, True, False):
            return NotImplemented
        y = cls(y)
        if x == y == cls.true:
            return cls.true
        elif x is cls.false or y is cls.false:
            return cls.false
        else:
            return cls.unknown
    __rand__ = __and__

    def __or__(x, y):
        """
        OR (disjunction): x | y:
        True iff at least one of x,y is True
        False iif both x,y are False

              F   U   T
         ---+---+---+---
         F  | F | U | T
         ---+---+---+---
         U  | U | U | T
         ---+---+---+---
         T  | T | T | T
        """
        cls = x.__class__
        if not isinstance(y, cls) and y not in (None, empty, True, False):
            return NotImplemented
        y = cls(y)
        if x is y is cls.false:
            return cls.false
        elif x is cls.true or y is cls.true:
            return cls.true
        else:
            return cls.unknown
    __ror__ = __or__

    def __xor__(x, y):
        """
        XOR (parity) x ^ y:
        True iff only one of x,y is True and other of x,y is False
        False iff both of x,y are False or both of x,y are True

              F   U   T
         ---+---+---+---
         F  | F | U | T
         ---+---+---+---
         U  | U | U | U
         ---+---+---+---
         T  | T | U | F
        """
        cls = x.__class__
        if not isinstance(y, cls) and y not in (None, empty, True, False):
            return NotImplemented
        y = cls(y)
        if x is cls.unknown or y is cls.unknown:
            return cls.unknown
        elif x is cls.true and y is cls.false or x is cls.false and y is cls.true:
            return cls.true
        else:
            return cls.false
    __rxor__ = __xor__

    def __bool__(x):
        """
        boolean value of Unknown is Unknown, and will raise
        """
        if x.value is 1:
            return True
        elif x.value is -1:
            return False
        else:
            raise ValueError('cannot determine boolean value of Unknown')

    def __eq__(x, y):
        cls = x.__class__
        if not isinstance(y, cls) and y not in (None, empty, True, False):
            return NotImplemented
        y = cls(y)
        return x.value == y.value

    def __ge__(x, y):
        cls = x.__class__
        if not isinstance(y, cls) and y not in (None, empty, True, False):
            return NotImplemented
        y = cls(y)
        return x.value >= y.value

    def __gt__(x, y):
        cls = x.__class__
        if not isinstance(y, cls) and y not in (None, empty, True, False):
            return NotImplemented
        y = cls(y)
        return x.value > y.value

    def __le__(x, y):
        cls = x.__class__
        if not isinstance(y, cls) and y not in (None, empty, True, False):
            return NotImplemented
        y = cls(y)
        return x.value <= y.value

    def __lt__(x, y):
        cls = x.__class__
        if not isinstance(y, cls) and y not in (None, empty, True, False):
            return NotImplemented
        y = cls(y)
        return x.value < y.value

    def __ne__(x, y):
        cls = x.__class__
        if not isinstance(y, cls) and y not in (None, empty, True, False):
            return NotImplemented
        y = cls(y)
        return x.value != y.value

    def __repr__(x):
        return "%s.%s: %r" % (x.__class__.__name__, x.name, x.value)

    def __str__(x):
        return x.name

Trivalent.true = object.__new__(Trivalent)
Trivalent.true.value = +1
Trivalent.true.name = 'Truthy'
Trivalent.false = object.__new__(Trivalent)
Trivalent.false.value = -1
Trivalent.false.name = 'Falsey'
Trivalent.unknown = object.__new__(Trivalent)
Trivalent.unknown.value = 0
Trivalent.unknown.name = 'Unknown'
Truthy = Trivalent.true
Unknown = Trivalent.unknown
Falsey = Trivalent.false

## casting for types of arguments
def Bool(arg):
    if arg in (True, False):
        return arg
    return arg.lower() in "true t yes y 1 on".split()

def InputFile(arg):
    return open(arg)

def OutputFile(arg):
    return open(arg, 'w')

## utilities

### quiting
def abort(msg=None, returncode=Exit.Unknown):
    "prints msg to stderr, calls sys.exit() with returncode"
    with print_lock:
        if msg:
            if VERBOSITY > 0:
                progname = script_module['script_fullname']
            else:
                progname = script_module['script_name']
            result = '%s: %s' % (progname, msg)
            script_module['script_abort_message'] = result
            print(result, file=stderr)
        sys.exit(returncode)

def help(msg, returncode=Exit.ScriptionError):
    "conditionally adds reference to --help"
    if '--help' not in msg:
        msg += ' (use --help for more information)'
    abort(msg, returncode)

### printing
def scription_debug(*values, **kwds):
    # kwds can contain sep (' '), end ('\n'), file (sys.stdout), and
    # verbose (1)
    with print_lock:
        verbose_level = kwds.pop('verbose', 1)
        if 'file' not in kwds:
            kwds['file'] = stderr
        if verbose_level > SCRIPTION_DEBUG:
            return
        _print('scription> ', *values, **kwds)

def debug(*args, **kwds):
    with print_lock:
        kwds['verbose'] = kwds.pop('verbose', 2)
        print(*args, **kwds)

def echo(*args, **kwds):
    with print_lock:
        kwds['verbose'] = kwds.pop('verbose', 0)
        print(*args, **kwds)

def error(*args, **kwds):
    with print_lock:
        returncode = kwds.pop('returncode', None)
        kwds['file'] = stderr
        kwds.pop('verbose', 0)
        print(*args, **kwds)
        if returncode:
            abort(returncode=returncode)

def info(*args, **kwds):
    with print_lock:
        kwds['verbose'] = kwds.pop('verbose', 1)
        print(*args, **kwds)

def print(*values, **kwds):
    # kwds can contain sep (' '), end ('\n'), file (sys.stdout), and
    # verbose (1)
    with print_lock:
        verbose_level = kwds.pop('verbose', 1)
        target = kwds.get('file')
        if verbose_level > VERBOSITY and target is not stderr:
            return
        try:
            _print(*values, **kwds)
            if target:
                target.flush()
            else:
                sys.stdout.flush()
        except IOError:
            cls, exc, tb = sys.exc_info()
            if exc.errno == errno.EPIPE:
                sys.exit(Exit.IoError)
            raise

def log_exception(tb=None):
    if tb is None:
        cls, exc, tb = sys.exc_info()
        lines = traceback.format_list(traceback.extract_tb(tb))
        lines.append('%s: %s\n' % (cls.__name__, exc))
        logger.critical('Traceback (most recent call last):')
    else:
        lines = tb.split('\\n')
    for line in lines:
        for ln in line.rstrip().split('\n'):
            logger.critical(ln)
    return lines


### interaction
def get_response(
        question,
        validate=None,
        type=None,
        retry='bad response, please try again',
        default=undefined,
        ):
    # True/False: no square brackets, ends with '?'
    #   'Do you like green eggs and ham?'
    # Multiple Choice: square brackets
    #   'Delete files matching *.xml? [N/y/a]'
    #   'Are hamburgers good? [Always/sometimes/never]'
    # Anything: no square brackets, does not end in '?'
    #   'name'
    #   'age'
    if default:
        default = default.lower()
    if '[' not in question and question.rstrip().endswith('?'):
        # yes/no question
        if type is None:
            type = lambda ans: ans.lower() in ('y', 'yes', 't', 'true')
        if validate is None:
            validate = lambda ans: ans.lower() in ('y', 'yes', 'n', 'no', 't', 'true', 'f', 'false')
    elif '[' not in question:
        # answer can be anything
        if type is None:
            type = str
        if validate is None:
            validate = lambda ans: type(ans.strip())
    else:
        # two supported options:
        #   'some question [always/maybe/never]'
        # and
        #   'some question:\n[a]ways\n[m]aybe\n[n]ever'
        # responses are embedded in question between '[]' and consist
        # of first letter if all lowercase, else first capital letter
        actual_question = []
        allowed_responses = {}
        left_brackets = question.count('[')
        right_brackets = question.count(']')
        if left_brackets != right_brackets:
            raise ScriptionError('mismatched [ ]')
        elif left_brackets == 1:
            # first option
            current_word = []
            in_response = False
            for ch in question:
                if ch == '[':
                    in_response = True
                elif in_response and ch not in ('abcdefghijklmnopqrstuvwxyz_ABCDEFGHIJKLMNOPQRSTUVWXYZ'):
                    word = ''.join(current_word)
                    current_word = []
                    if not word:
                        raise ScriptionError('empty choice')
                    uppers = ''.join([l for l in word if l == l.upper()])
                    word = word.lower()
                    if not uppers:
                        uppers = word[0]
                    allowed_responses[word] = word
                    allowed_responses[uppers] = word
                    if default in (word, uppers):
                        actual_question.append('-')
                        actual_question.extend([c for c in word])
                        actual_question.append('-')
                    else:
                        actual_question.extend([c for c in word])
                    if ch == ']':
                        in_response = False
                elif in_response:
                    current_word.append(ch)
                    continue
                actual_question.append(ch)
        else:
            # second option
            current_response = []
            current_word = []
            in_response = False
            capture_word = False
            for ch in question+' ':
                if ch == '[':
                    in_response = True
                    capture_word = True
                elif ch == ']':
                    in_response = False
                    response = ''.join(current_response).lower()
                    allowed_responses[response] = response
                    current_response = []
                    if response == default:
                        response = response.upper()
                    actual_question.extend([c for c in response])
                elif ch not in ('abcdefghijklmnopqrstuvwxyz_ABCDEFGHIJKLMNOPQRSTUVWXYZ'):
                    if capture_word:
                        word = ''.join(current_word).lower()
                        allowed_responses[response.lower()] = word
                        allowed_responses[word] = word
                    capture_word = False
                    current_word = []
                if ch not in '[]':
                    if capture_word:
                        current_word.append(ch)
                    if in_response:
                        current_response.append(ch.lower())
                        # and skip adding to question
                        continue
                actual_question.append(ch)
            if in_response:
                raise ScriptionError('question missing closing "]"')
        question = ''.join(actual_question)
        if type is None:
            type = lambda ans: allowed_responses[ans.strip().lower()]
        else:
            old_type = type
            type = lambda ans: old_type(allowed_responses[ans.strip().lower()])
        if validate is None:
            validate = lambda ans: ans and ans.strip().lower() in allowed_responses
    if not question[-1:] in (' ','\n', ''):
        question += ' '
    # check that a supplied default is valid
    if default and not validate(default):
        raise ScriptionError('supplied default is not valid')
    # setup is done, ask question and get answer
    while 'answer is unacceptable':
        answer = raw_input(question)
        answer = answer or default
        if validate(answer):
            break
    return type(answer)

def mail(server=None, port=25, message=None):
    """
    sends email.message to server:port

    if message is a str, will break apart To, Cc, and Bcc at commas
    """
    receivers = []
    if message is None:
        raise ValueError('message not specified')
    elif isinstance(message, basestring):
        scription_debug('converting string -> email.message')
        scription_debug(message, verbose=2)
        message = email.message_from_string(message)
        for targets in ('To', 'Cc', 'Bcc'):
            scription_debug('   recipient target:', targets, verbose=2)
            groups = message.get_all(targets, [])
            scription_debug('      groups:', groups, verbose=2)
            del message[targets]
            for group in groups:
                scription_debug('      group:', group, verbose=2)
                addresses = group.split(',')
                for target in addresses:
                    scription_debug('         individual:', target, verbose=2)
                    target = target.strip()
                    message[targets] = target
                    receivers.append(target)
    scription_debug('receivers:', receivers, verbose=2)
    if 'date' not in message:
        message['date'] = email.utils.formatdate(localtime=True)
    sender = message['From']
    if server is None:
        scription_debug('skipping stage 1', verbose=2)
        send_errs = dict.fromkeys(receivers)
    else:
        try:
            scription_debug('stage 1: connect to smtp server', server, port)
            smtp = smtplib.SMTP(server, port)
        except socket.error:
            exc = sys.exc_info()[1]
            scription_debug('error:', exc)
            send_errs = {}
            for rec in receivers:
                send_errs[rec] = (server, exc.args)
        else:
            try:
                scription_debug('         sending mail')
                send_errs = smtp.sendmail(sender, receivers, message.as_string())
            except smtplib.SMTPRecipientsRefused:
                exc = sys.exc_info()[1]
                scription_debug('error:', exc)
                send_errs = {}
                for user, detail in exc.recipients.items():
                    send_errs[user] = (server, detail)
            finally:
                scription_debug('         quiting')
                smtp.quit()
    errs = {}
    if send_errs:
        for user in send_errs:
            try:
                server = 'mail.' + user.split('@')[1]
                smtp = smtplib.SMTP(server, 25)
            except socket.error:
                exc = sys.exc_info()[1]
                errs[user] = [send_errs[user], (server, exc.args)]
            else:
                try:
                    smtp.sendmail(sender, [user], message.as_string())
                except smtplib.SMTPRecipientsRefused:
                    exc = sys.exc_info()[1]
                    errs[user] = [send_errs[user], (server, exc.recipients[user])]
                finally:
                    smtp.quit()
    return errs

### miscellaneous
class pocket(object):
    '''
    container to save values from intermediate expressions

    nb: return value is unordered
    '''
    pocket = threading.local()

    def __call__(self, **kwds):
        res = []
        # setattr(self.pocket, 'data', {})
        level = self.pocket.data = {}
        for names, value in kwds.items():
            names = names.split('.')
            for name in names[:-1]:
                if name not in level:
                    level[name] = {}
                    level = level[name]
            name = names[-1]
            level[name] = value
            res.append(value)
        if len(res) == 1:
            [res] = res
        else:
            res = tuple(res)
        return res

    def __getattr__(self, name):
        try:
            return self.pocket.data[name]
        except KeyError:
            raise AttributeError('%s has not been saved' % name)
pocket = pocket()

class user_ids(object):
    """
    maintains root as one of the ids
    """
    def __init__(self, uid, gid):
        self.target_uid = uid
        self.target_gid = gid
        self.saved_uids = os.getuid(), os.geteuid()
        self.saved_gids = os.getgid(), os.getegid()
    def __enter__(self):
        os.seteuid(0)
        os.setegid(0)
        os.setregid(0, self.target_gid)
        os.setreuid(0, self.target_uid)
    def __exit__(self, *args):
        os.seteuid(0)
        os.setegid(0)
        os.setregid(*self.saved_gids)
        os.setreuid(*self.saved_uids)

class wait_and_check(object):
    'is True until <seconds> have passed; waits <period> seconds on each check'
    def __init__(self, seconds, period=1):
        if seconds < 0:
            raise ValueError('seconds cannot be less than zero')
        if period <= 0:
            raise ValueError('period must be greater than zero')
        self.limit = time.time() + seconds
        self.period = period
    def __bool__(self):
        if time.time() < self.limit:
            time.sleep(self.period)
            if time.time() < self.limit:
                return True
        return False
    __nonzero__ = __bool__
