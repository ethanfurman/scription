from __future__ import print_function
"""
intelligently parses command lines

flags: true/false values
options: other specified value (e.g. user name)
global script variables:  i.e. debug=True (python expression)
"""

import sys
py_ver = sys.version_info[:2]
is_win = sys.platform.startswith('win')
if not is_win:
    from pty import fork
    import resource
    import termios
    from syslog import syslog
    import signal
    KILL_SIGNALS = signal.SIGHUP, signal.SIGINT
elif py_ver >= (2, 7):
    import signal
    KILL_SIGNALS = signal.CTRL_C_EVENT, signal.CTRL_BREAK_EVENT
else:
    KILL_SIGNALS = ()
if py_ver < (3, 0):
    from __builtin__ import print as _print
else:
    from builtins import print as _print
import datetime
import email
import inspect
import locale
import logging
import os
import re
import select
import shlex
import smtplib
import socket
import tempfile
import textwrap
import time
import traceback
from enum import Enum
from functools import partial
from subprocess import Popen, PIPE, STDOUT
from sys import stdout, stderr

"""
(help, kind, abbrev, type, choices, usage_name, remove)

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
"""

version = 0, 74, 31

# data
__all__ = (
    'Alias', 'Command', 'Script', 'Main', 'Run', 'Spec',
    'Bool','InputFile', 'OutputFile',
    'IniError', 'IniFile', 'OrmError', 'OrmFile',
    'FLAG', 'KEYWORD', 'OPTION', 'MULTI', 'REQUIRED',
    'ScriptionError', 'ExecuteError', 'Execute',
    'abort', 'get_response', 'help', 'mail', 'user_ids', 'print',
    'stdout', 'stderr', 'wait_and_check',
    )

VERBOSITY = 0
SCRIPTION_DEBUG = 0
LOCALE_ENCODING = locale.getpreferredencoding() or 'utf-8'


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

module = globals()
script_module = None

registered = False
run_once = False

if py_ver < (3, 0):
    bytes = str
else:
    raw_input = input
    basestring = str
    unicode = str

# the __version__ and __VERSION__ are for compatibility with existing code,
# but those names are reserved by the Python interpreter and should not be
# used
_version_strings = 'version', 'VERSION', '__version__', '__VERSION__'

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

class DocEnum(Enum):
    """compares equal to all cased versions of its name
    accepts a doctring for each member
    """

    def __new__(cls, *args):
        """Ignores arguments (will be handled in __init__)"""
        obj = object.__new__(cls)
        obj._value_ = None
        return obj

    def __init__(self, *args):
        """Can handle 0 or 1 argument; more requires a custom __init__.
        0  = auto-number w/o docstring
        1  = auto-number w/ docstring
        2+ = needs custom __init__
        """
        # first, fix _value_
        self._value_ = self._name_.lower()
        if len(args) == 1 and isinstance(args[0], basestring):
            self.__doc__ = args[0]
        elif args:
            raise TypeError('%s not dealt with -- need custom __init__' % (args,))

    def __eq__(self, other):
        if isinstance(other, basestring):
            return self._value_ == other.lower()
        elif not isinstance(other, self.__class__):
            return NotImplemented
        return self is other

    def __ne__(self, other):
        return not self == other

    @classmethod
    def export_to(cls, namespace):
        namespace.update(cls.__members__)


class SpecKind(DocEnum):
    REQUIRED = "required value"
    OPTION = "single value per name"
    MULTI = "multiple values per name (list form)"
    FLAG = "boolean value per name"
    KEYWORD = 'unknown options'
SpecKind.export_to(module)


class ExecuteError(Exception):
    "errors raised by Execute"
    def __init__(self, msg=None, process=None):
        self.process = process
        Exception.__init__(self, msg)


class ExecuteTimeoutError(ExecuteError):
    "Execute timed out"

# deprecated
ExecutionError = ExecuteError


class OrmError(ValueError):
    """
    used to signify errors in the ORM file
    """


class ScriptionError(Exception):
    "raised for errors in user script"


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


class Alias(object):
    "adds aliases for the function"
    def __init__(self, *aliases):
        debug('recording aliases', aliases, verbose=2)
        self.aliases = aliases
    def __call__(self, func):
        debug('applying aliases to', func, verbose=2)
        for alias in self.aliases:
            Command.subcommands[alias] = func
        return func


class Command(object):
    "adds __scription__ to decorated function, and adds func to Command.subcommands"
    subcommands = {}
    def __init__(self, **annotations):
        debug('Command -> initializing', verbose=1)
        debug(annotations, verbose=2)
        for name, annotation in annotations.items():
            spec = Spec(annotation)
            annotations[name] = spec
        self.annotations = annotations
    def __call__(self, func):
        debug('Command -> applying to', func, verbose=1)
        global script_module
        if script_module is None:
            script_module = _func_globals(func)
            script_module['module'] = _namespace(script_module)
            script_module['script_name'] = '<unknown>'
        if func.__doc__ is not None:
            func.__doc__ = textwrap.dedent(func.__doc__).strip()
        _add_annotations(func, self.annotations)
        func_name = func.__name__.replace('_', '-')
        Command.subcommands[func_name] = func
        _help(func)
        return func


class Execute(object):
    """
    if pty is True runs command in a forked process, otherwise runs in a subprocess
    """

    def __init__(self, args, bufsize=-1, cwd=None, password=None, timeout=None, pty=False, interactive=False):
        # args        -> command to run
        # cwd         -> directory to run in
        # password    -> d'oh
        # timeout     -> raise exception of not complete in timeout seconds
        # pty         -> False = subprocess, True = fork
        # interactive -> False = record only, 'echo' = echo output as we get it
        self.env = None
        if isinstance(args, basestring):
            args = shlex.split(args)
        else:
            new_args = []
            for arg in args:
                if any(ws in arg for ws in ' \n\r\t'):
                    new_args.append('"%s"' % arg)
                else:
                    new_args.append(arg)
            args = new_args
        if not pty:
            # use subprocess
            debug('subprocess args:', args)
            process = Popen(args, stdin=PIPE, stdout=PIPE, stderr=PIPE, cwd=cwd)
            if password is not None:
                if not isinstance(password, bytes):
                    password = (password+'\n').encode('utf-8')
                else:
                    password += '\n'.encode('utf-8')
            stdout, stderr = process.communicate(input=password)
            self.stdout = stdout.decode('utf-8').replace('\r\n', '\n')
            self.stderr = stderr.decode('utf-8').replace('\r\n', '\n')
            self.returncode = process.returncode
            self.closed = True
            self.terminated = True
            self.signal = None
            if interactive == 'echo':
                if self.stdout:
                    print(self.stdout)
                if self.stderr:
                    print(self.stderr, file=stderr)
            return
        if is_win:
            raise OSError("pty support for Execute not currently implemented for Windows")
        error_read, error_write = os.pipe()
        self.pid, self.child_fd = fork()
        if self.pid == 0: # child process
            os.close(error_read)
            self.child_fd = sys.stdout.fileno()
            os.dup2(error_write, 2)
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
        self.error_pipe = error_read
        self.returncode = None
        self.signal = None
        output = []
        self.stderr = []
        self.error_available = False
        self.closed = False
        self.terminated = False
        submission_received = True
        timed_out = False
        # loop to read output
        time.sleep(0.1)
        last_comms = time.time()
        while self.is_alive():
            if not self.get_echo() and password and submission_received:
                # discard any output before password was requested
                self.read(1024)
                output[:] = []
                self.write(password)
                self.write('\r\n')
                submission_received = False
            while _pocket(self.read(1024)):
                output.append(_pocket())
                submission_received = True
                last_comms = time.time()
            time.sleep(0.01)
            if timeout and time.time() - last_comms > timeout:
                timed_out = True
                self.terminate()
        while _pocket(self.read(1024)):
            output.append(_pocket())
            if timed_out:
                break
            time.sleep(0.01)
        while self.error_available:
            self._read_error()
            if timed_out:
                break
        self.stdout = ''.join(output).replace('\r\n', '\n')
        self.stderr = ''.join(self.stderr).replace('\r\n', '\n')
        if password and self.stdout[0] == '\n':
            self.stdout = self.stdout[1:]
        if interactive == 'echo':
            if self.stdout:
                print(self.stdout)
            if self.stderr:
                print(self.stderr, file=stderr)
        try:
            if timed_out:
                raise ExecuteTimeoutError('process failed to complete in %s seconds' % timeout, process=self)
        finally:
            self.close()

    def close(self, force=True,):
        if not self.closed:
            os.close(self.error_pipe)
            os.close(self.child_fd)
            time.sleep(0.1)
            if self.is_alive():
                if not self.terminate(force):
                    raise ExecuteError("Could not terminate the child.", process=self)
            self.child_fd = -1
            self.closed = True

    def fileno(self):
        return self.child_fd

    def get_echo(self):
        "return the child's terminal echo status (True is on)"
        attr = termios.tcgetattr(self.child_fd)
        if attr[3] & termios.ECHO:
            return True
        return False

    def isatty(self):
        return os.isatty(self.child_fd)

    def is_alive(self):
        if self.terminated:
            return False
        pid, status = os.waitpid(self.pid, os.WNOHANG)
        if pid != 0:
            self.signal = status % 256
            self.returncode = status >> 8
            self.terminated = True
            return False
        return True

    def read(self, size=1, timeout=10):
        "non-blocking read (should only be called by the parent)"
        if self.closed:
            raise ValueError("I/O operation on closed file.")
        r, w, x = select.select([self.child_fd, self.error_pipe], [], [], 0)
        if not r:
            return unicode()
        result = None
        if self.child_fd in r:
            try:
                result = os.read(self.child_fd, size).decode('utf-8')
            except OSError:
                result = unicode()
        if self.error_pipe in r:
            self.error_available = True
            return result or unicode()
        if result is not None:
            return result
        raise ExecuteError('unknown problem with read', process=self)

    def _read_error(self):
        "only call if error output is available"
        try:
            result = os.read(self.error_pipe, 1024)
        except OSError:
            result = '<unknown error>'.encode('latin1')
        result = result.decode('utf-8')
        if not result:
            self.error_available = False
        else:
            self.stderr.append(result)

    def terminate(self, force=False):
        if not self.is_alive():
            return True
        for sig in KILL_SIGNALS:
            os.kill(self.pid, sig)
            time.sleep(0.1)
            if not self.is_alive():
                self.terminated = True
                return True
        if force:
            os.kill(self.pid, signal.SIGKILL)
            time.sleep(0.1)
            if not self.is_alive():
                self.terminated = True
                return True
        return False

    def write(self, data):
        if not isinstance(data, bytes):
            data = data.encode('utf-8')
        os.write(self.child_fd, data)

    def write_error(self, data):
        if not isinstance(data, bytes):
            data = data.encode('utf-8')
        os.write(self.error_pipe, data)


def Main():
    "calls Run() only if the script is being run as __main__"
    debug('Main entered')
    if script_module['__name__'] == '__main__':
        return Run()


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
        defaults = {}
        settings = self._settings = _namespace()
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
                        new_section = _namespace()
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

    def __getattr__(self, name):
        if name in self._settings.__dict__:
            return getattr(self._settings, name)
        raise IniError("'settings' has no section/default named %r" % name)

    def __getitem__(self, name):
        return self._settings[name]

    def __setattr__(self, name, value):
        if name in ('_settings', '_str', '_path', '_date', '_time', '_datetime', '_bool', '_float', '_int'):
            object.__setattr__(self, name, value)
        else:
            self._settings[name] = value

    def __setitem__(self, name, value):
        self._settings[name] = value

    def _verify_name(self, name):
        name = name.strip().lower()
        if not name[0].isalpha():
            raise IniError('names must start with a letter')
        if re.sub('\w*', '', name):
            # illegal characters in name
            raise IniError('names can only contain letters, digits, and the underscore [%r]' % name)
        return name

    def _verify_section_header(self, section):
        section = section.strip().lower()
        if not section[0].isalpha():
            raise IniError('names must start with a letter')
        if re.sub('\w*', '', section):
            # illegal characters in section
            raise IniError('names can only contain letters, digits, and the underscore [%r]' % section)
        if section in self.__dict__:
            # section already exists
            raise IniError('section %r is a duplicate, or already exists as a default value' % section)
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
            if value[0] != value[-1]:
                raise IniError('string must be quoted at both ends [%r]' % value)
            start, end = 1, -1
            if value[:3] in ('"""', "'''"):
                if value[:3] != value[-3:] or len(value) < 6:
                    raise IniError('invalid string value: %r' % value)
                start, end = 3, -3
            return self._str(value[start:end])
        elif '/' in value or '\\' in value:
            return self._path(value)
        elif ':' in value and '-' in value:
            # datetime
            try:
                date = map(int, value[:10].split('-'))
                time = map(int, value[11:].split(':'))
                return self._datetime(*(date+time))
            except ValueError:
                raise IniError('invalid datetime value: %r' % value)
        elif '-' in value:
            # date
            try:
                date = map(int, value.split('-'))
                return self._date(date)
            except ValueError:
                raise IniError('invalid date value: %r' % value)
        elif ':' in value:
            # time
            try:
                time = map(int, value.split(':'))
                return self._time(*time)
            except ValueError:
                raise IniError('invalid time value: %r' % value)
        elif '.' in value:
            try:
                value = self._float(value)
            except ValueError:
                raise IniError('invalid float value: %r' % value)
        elif value.lower() == 'true':
            return self._bool(True)
        elif value.lower() == 'false':
            return self._bool(False)
        else:
            return self._int(value)
# deprecated, will remove at some point
IniError = OrmError
IniFile = OrmFile


def Run():
    "parses command-line and compares with either func or, if None, Script.command"
    global SYS_ARGS
    debug('Run entered')
    if module.get('HAS_BEEN_RUN'):
        debug('Run already called once, returning')
        return
    module['HAS_BEEN_RUN'] = True
    if py_ver < (3, 0):
        SYS_ARGS = [arg.decode(LOCALE_ENCODING) for arg in sys.argv]
    else:
        SYS_ARGS = sys.argv[:]
    try:
        prog_path, prog_name = os.path.split(SYS_ARGS[0])
        if prog_name == '__main__.py':
            # started with python -m, get actual package name for prog_name
            prog_name = os.path.split(prog_path)[1]
        debug(prog_name, verbose=2)
        script_module['script_name'] = prog_name
        prog_name = prog_name.replace('_','-')
        if not Command.subcommands:
            raise ScriptionError("no Commands defined in script")
        func_name = SYS_ARGS[1:2]
        if not func_name:
            func_name = None
        else:
            func_name = func_name[0].lower()
            if func_name == '--version':
                _print(_get_version(script_module['module']))
                raise SystemExit
            elif func_name in ('--all-versions', '--all_versions'):
                _print('\n'.join(_get_all_versions(script_module)))
                raise SystemExit
            else:
                func_name = func_name.replace('_', '-')
        func = Command.subcommands.get(func_name)
        if func is not None:
            prog_name = SYS_ARGS[1:2]
            param_line = [prog_name] + SYS_ARGS[2:]
        else:
            func = Command.subcommands.get(prog_name.lower(), None)
            if func is not None and func_name != '--help':
                param_line = [prog_name] + SYS_ARGS[1:]
            else:
                prog_name_is_command = prog_name.lower() in Command.subcommands
                if script_module['__doc__']:
                    _print(script_module['__doc__'].strip())
                if len(Command.subcommands) == 1:
                    _detail_help = True
                else:
                    _detail_help = False
                    _name_length = max([len(name) for name in Command.subcommands])
                if Script.__usage__ and _detail_help:
                    _print("\nglobal options: %s" % Script.__usage__)
                for name, func in sorted(Command.subcommands.items()):
                    if _detail_help:
                        if not prog_name_is_command or name != prog_name:
                            name = '%s %s' % (prog_name, name)
                        _print("\n%s %s" % (name, func.__usage__))
                    else:
                        doc = (func.__doc__ or '').split('\n')[0]
                        _print("   %*s  %s" % (_name_length, name, doc))
                raise SystemExit
        main_args, main_kwds, sub_args, sub_kwds = _usage(func, param_line)
        main_cmd = Script.command
        subcommand = _run_once(func, sub_args, sub_kwds)
        script_module['script_command'] = subcommand
        script_module['script_command_name'] = func_name
        script_module['script_verbosity'] = VERBOSITY
        if main_cmd:
            main_cmd(*main_args, **main_kwds)
        return subcommand()
    except Exception:
        exc = sys.exc_info()[1]
        debug(exc)
        result = log_exception()
        script_module['exception_lines'] = result
        if isinstance(exc, ScriptionError):
            raise SystemExit(str(exc))
        raise


class Script(object):
    "adds __scription__ to decorated function, and stores func in Script.command"
    command = None
    settings = {}
    names = []
    all_params = []
    named_params = []
    __usage__ = None
    def __init__(self, **settings):
        debug('Script -> recording', verbose=1)
        debug(settings, verbose=2)
        if Script.command is not None:
            raise ScriptionError("Script can only be used once")
        for name, annotation in settings.items():
            if isinstance(annotation, (Spec, tuple)):
                spec = Spec(annotation)
                if spec.kind == 'required':
                    # TODO:  allow this
                    raise ScriptionError('REQUIRED not (yet) allowed for Script')
            else:
                if isinstance(annotation, bool):
                    kind = 'flag'
                else:
                    kind = 'option'
                spec = Spec('', kind, None, type(annotation), default=annotation)
            if spec.usage is empty:
                spec.usage = name.upper()
            settings[name] = spec
        Script.settings = settings
        Script.names = sorted(settings.keys())
        num_keys = len(Script.names)
        for i, name in enumerate(Script.names):
            settings[name]._order = i + num_keys
        def psyche():
            pass
        _add_annotations(psyche, settings, script=True)
        _help(psyche)
        Script.names = psyche.names
        Script.__usage__ = psyche.__usage__.strip()
    def __call__(self, func):
        debug('Script -> applying to', func, verbose=1)
        if Script.command is not None:
            raise ScriptionError("Script can only be used once")
        func_name = func.__name__.replace('_', '-')
        if func_name in Command.subcommands:
            raise ScriptionError('%r cannot be both Command and Scription' % func_name)
        global script_module
        if script_module is None:
            script_module = _func_globals(func)
            script_module['module'] = _namespace(script_module)
            script_module['script_name'] = '<unknown>'
        if func.__doc__ is not None:
            func.__doc__ = textwrap.dedent(func.__doc__).strip()
        _add_annotations(func, Script.settings, script=True)
        _help(func)
        Script.all_params = func.all_params
        Script.named_params = func.named_params
        Script.settings = func.__scription__
        Script.__usage__ = func.__usage__.strip()
        Script.command = staticmethod(func)
        return func


class Spec(object):
    """tuple with named attributes for representing a command-line paramter

    help, kind, abbrev, type, choices, usage_name, remove, default
    """

    def __init__(self,
            help=empty, kind=empty, abbrev=empty, type=empty,
            choices=empty, usage=empty, remove=False, default=empty,
            ):
        if isinstance(help, Spec):
            self.__dict__.update(help.__dict__)
            return
        if isinstance(help, tuple):
            args = list(help) + [empty] * (8 - len(help))
            help, kind, abbrev, type, choices, usage, remove, default = args
        if not help:
            help = ''
        if not kind:
            kind = 'required'
        if not type:
            type = _identity
        if not choices:
            choices = []
        arg_type_default = empty
        if kind not in ('required', 'option', 'multi', 'flag'):
            raise ScriptionError('unknown parameter kind: %r' % kind)
        if kind == 'flag':
            arg_type_default = False
        elif kind == 'option':
            arg_type_default = None
        elif kind == 'multi':
            arg_type_default = tuple()
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
        self._global = False

    def __iter__(self):
        return iter((self.help, self.kind, self.abbrev, self.type, self.choices, self.usage, self.remove, self._script_default))

    def __repr__(self):
        return "Spec(help=%r, kind=%r, abbrev=%r, type=%r, choices=%r, usage=%r, remove=%r)" % (
                self.help, self.kind, self.abbrev, self.type, self.choices, self.usage, self.remove)

    @property
    def value(self):
        if self._cli_value is not empty:
            value = self._cli_value
        elif self._script_default is not empty:
            value = self._script_default
        elif self._type_default is not empty:
            value = self._type_default
        else:
            raise ScriptionError('no value specified for %s' % self.usage)
        return value


def abort(msg, returncode=1):
    "prints msg to stderr, raises SystemExit with returncode"
    print('%s: %s' % (script_module['script_name'], msg), file=stderr)
    raise SystemExit(returncode)

def debug(*values, **kwds):
    # kwds can contain sep (' ), end ('\n'), file (sys.stdout), and
    # verbose (1)
    verbose_level = kwds.pop('verbose', 1)
    if 'file' not in kwds:
        kwds['file'] = stderr
    if verbose_level > SCRIPTION_DEBUG:
        return
    _print('scription> ', *values, **kwds)

def get_response(
        question,
        validate=None,
        type=None,
        retry='bad response, please try again',
        ):
    if '[' not in question and question.rstrip().endswith('?'):
        # yes/no question
        if type is None:
            type = lambda ans:ans.lower() in ('y', 'yes', 't', 'true')
        if validate is None:
            validate = lambda ans: ans.lower() in ('y', 'yes', 'n', 'no', 't', 'true', 'f', 'false')
    elif '[' not in question:
        # answer can be anything
        if type is None:
            type = str
        if validate is None:
            validate = lambda ans: type(ans.strip())
    else:
        # responses are embedded in question between '[]'
        actual_question = []
        allowed_responses = {}
        current_response = []
        current_word = []
        in_response = False
        capture_word = False
        for ch in question:
            if ch == '[':
                in_response = True
                capture_word = True
            elif ch == ']':
                in_response = False
                response = ''.join(current_response).lower()
                allowed_responses[response] = response
                current_response = []
            elif ch not in ('abcdefghijklmnopqrstuvwxyz_ABCDEFGHIJKLMNOPQRSTUVWXYZ'):
                if capture_word:
                    allowed_responses[response] = ''.join(current_word)
                capture_word = False
                current_word = []
            actual_question.append(ch)
            if ch not in '[]':
                if in_response:
                    current_response.append(ch.lower())
                if capture_word:
                    current_word.append(ch)
        if in_response:
            raise ScriptionError('question missing closing "]"')
        question = ''.join(actual_question)
        if type is None:
            type = lambda ans: allowed_responses[ans.strip().lower()]
        else:
            old_type = type
            type = lambda ans: old_type(allowed_responses[ans.strip().lower()])
        if validate is None:
            validate = lambda ans: ans.strip().lower() in allowed_responses
    if not question[-1:] in (' ','\n', ''):
        question += ' '
    # setup is done, ask question and get answer
    while 'answer is unacceptable':
        answer = raw_input(question)
        if validate(answer):
            break
        _print(retry)
    return type(answer)

def help(msg, returncode=1):
    "conditionally adds reference to --help"
    if '--help' not in msg:
        msg += ' (use --help for more information)'
    abort(msg, returncode)

def log_exception(tb=None):
    if tb is None:
        exc, err, tb = sys.exc_info()
        lines = traceback.format_list(traceback.extract_tb(tb))
        lines.append('%s: %s\n' % (exc.__name__, err))
        logger.critical('Traceback (most recent call last):')
    else:
        lines = tb.split('\\n')
    for line in lines:
        for ln in line.rstrip().split('\n'):
            logger.critical(ln)
    return lines

def mail(server=None, port=25, message=None):
    """
    sends email.message to server:port

    if message is a str, will break apart To, Cc, and Bcc at commas
    """
    receivers = []
    if message is None:
        raise ValueError('message not specified')
    elif isinstance(message, basestring):
        debug('converting string -> email.message')
        debug(message, verbose=2)
        message = email.message_from_string(message)
        for targets in ('To', 'Cc', 'Bcc'):
            debug('   recipient target:', targets, verbose=2)
            groups = message.get_all(targets, [])
            debug('      groups:', groups, verbose=2)
            del message[targets]
            for group in groups:
                debug('      group:', group, verbose=2)
                addresses = group.split(',')
                for target in addresses:
                    debug('         individual:', target, verbose=2)
                    target = target.strip()
                    message[targets] = target
                    receivers.append(target)
    debug('receivers:', receivers, verbose=2)
    if 'date' not in message:
        message['date'] = email.utils.formatdate(localtime=True)
    sender = message['From']
    if server is None:
        debug('skipping stage 1', verbose=2)
        send_errs = dict.fromkeys(receivers)
    else:
        try:
            debug('stage 1: connect to smtp server', server, port)
            smtp = smtplib.SMTP(server, port)
        except socket.error:
            exc = sys.exc_info()[1]
            debug('error:', exc)
            send_errs = {}
            for rec in receivers:
                send_errs[rec] = (server, exc.args)
        else:
            try:
                debug('         sending mail')
                send_errs = smtp.sendmail(sender, receivers, message.as_string())
            except smtplib.SMTPRecipientsRefused:
                exc = sys.exc_info()[1]
                debug('error:', exc)
                send_errs = {}
                for user, detail in exc.recipients.items():
                    send_errs[user] = (server, detail)
            finally:
                debug('         quiting')
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

_pocket_sentinel = object()
def _pocket(value=_pocket_sentinel, _pocket=[]):
    if value is not _pocket_sentinel:
        _pocket[:] = [value]
    return _pocket[0]

def print(*values, **kwds):
    # kwds can contain sep (' '), end ('\n'), file (sys.stdout), and
    # verbose (1)
    verbose_level = kwds.pop('verbose', 1)
    target = kwds.get('file')
    if verbose_level > VERBOSITY and target is not stderr:
        return
    _print(*values, **kwds)

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
                version = ' '.join(_get_all_versions(from_module, _try_other=False))
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
                    version = getattr(module.ver)
                    if not isinstance(version, basestring):
                        version = '.'.join(['%s' % x for x in version])
                    versions.append('%s=%s' % (name, version))
                    break
    versions.append('python=%s' % '.'.join([str(i) for i in sys.version_info]))
    return versions

def _help(func):
    '''
    create help from __scription__ annotations
    '''
    params, vararg, keywordarg, defaults = inspect.getargspec(func)
    params = func.params = list(params)
    vararg = func.vararg = [vararg] if vararg else []
    keywordarg = func.keywordarg = [keywordarg] if keywordarg else []
    vararg_type = _identity
    keywordarg_type = _identity
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
        help, kind, abbrev, arg_type, choices, usage_name, remove, default = spec
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
                abbrev = name[0]
        elif kind == 'option':
            if abbrev is empty:
                abbrev = name[0]
        elif kind == 'multi':
            if abbrev is empty:
                abbrev = name[0]
            if default:
                if isinstance(default, list):
                    default = tuple(default)
                elif not isinstance(default, tuple):
                    default = (default, )
        else:
            raise ValueError('unknown kind: %r' % kind)
        if abbrev in annotations:
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
            annotations[abbrev] = spec
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
    if vararg:
        vararg_type = annotations[vararg[0]].type
    if keywordarg:
        kywd_func = annotations[keywordarg[0]].type
        if isinstance(kywd_func, tuple):
            keywordarg_type = lambda k, v: (kywd_func[0](k), kywd_func[1](v))
        else:
            keywordarg_type = lambda k, v: (k, kywd_func(v))
    # also prepare help for global options
    global_params = [n for n in func.names if n not in func.all_params]
    print_params = []
    for param in global_params + params:
        if param[0] == '_':
            # ignore private params
            continue
        example = annotations[param].usage
        if annotations[param].kind == 'flag':
            print_params.append('--%s' % param)
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
        if annote._script_default is empty or annote._script_default is None or '[default: ' in annote.help:
            posi = ''
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

class _namespace(object):
    def __init__(self, wrapped_dict=None):
        if wrapped_dict is not None:
            self.__dict__ = wrapped_dict
    def __contains__(self, name):
        return name in self.__dict__
    def __getitem__(self, name):
        try:
            return self.__dict__[name]
        except KeyError:
            raise ScriptionError("namespace object has nothing named %r" % name)
    def __setitem__(self, name, value):
        self.__dict__[name] = value
    def get(self, key, default=None):
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
    debug('creating run_once function')
    cache = []
    def later():
        debug('running later')
        global run_once
        if run_once:
            debug('returning cached value')
            return cache[0]
        run_once = True
        debug('calling function')
        result = func(*args, **kwds)
        cache.append(result)
        return result
    debug('returning <later>')
    return later

def _split_on_comma(text):
    debug('_split_on_comma(%r)' % text, verbose=2)
    if ',' not in text:
        debug('  -> %r' % ([text], ), verbose=2)
        return [text]
    elif '\\,' not in text:
        debug('  -> %r' % text.split(','), verbose=2)
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
        debug('  -> %r' % values, verbose=2)
        return values

def _usage(func, param_line_args):
    global VERBOSITY, SCRIPTION_DEBUG
    program, param_line_args = param_line_args[0], _rewrite_args(param_line_args[1:])
    pos = 0
    max_pos = func.max_pos
    print_help = print_version = print_all_versions = False
    value = None
    annotations = func.__scription__
    var_arg_spec = kwd_arg_spec = None
    if Script.command:
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
    for offset, item in enumerate(param_line_args + [None]):
        offset += 1
        original_item = item
        if value is not None:
            if item is None or item.startswith('-') or '=' in item:
                help('%s has no value' % last_item)
            if annote.remove:
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
                help("don't know what to do with %r" % item)
            var_arg_spec._cli_value += (var_arg_spec.type(item), )
            continue
        if item.startswith('-'):
            # (multi)option or flag
            if item.lower() == '--help':
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
                    abort('invalid verbosity level: %r' % value)
                value = None
                continue
            if item in annotations:
                annote = annotations[item]
            elif item in Script.settings:
                annote = Script.settings[item]
            elif item in ('SCRIPTION_DEBUG', ):
                SCRIPTION_DEBUG = value
                value = None
                continue
            else:
                help('%s not valid' % original_item)
            if annote.remove:
                to_be_removed.append(offset)
            if annote.kind in ('multi', 'option'):
                if value in (True, False):
                    value = []
                    last_item = item
                else:
                    if annote.kind == 'option':
                        annote._cli_value = annote.type(value)
                    else:
                        # value could be a list of comma-separated values
                        debug('_usage:multi ->', annote.type, verbose=2)
                        annote._cli_value += tuple([annote.type(a) for a in _split_on_comma(value)])
                        debug('_usage:multi ->', annote._cli_value, verbose=2)
                    value = None
            elif annote.kind == 'flag':
                value = annote.type(value)
                annote._cli_value = value
                value = None
            else:
                help('%s argument %s should not be introduced with --' % (annote.kind, item))
        elif '=' in item:
            # no lead dash, keyword args
            if kwd_arg_spec is None:
                help("don't know what to do with %r" % item)
            item, value = item.split('=')
            item = item.replace('-','_')
            if item in func.named_params:
                help('%s must be specified as a %s' % (item, annotations[item].kind))
            item, value = kwd_arg_spec.type(item, value)
            if not isinstance(item, str):
                help('keyword names must be strings')
            kwd_arg_spec._cli_value[item] = value
            value = None
        else:
            # positional (required?) argument
            if pos < max_pos:
                annote = annotations[pos]
                # check for choices membership before transforming into a type
                if annote.choices and item not in annote.choices:
                    help('%s: %r not in [ %s ]' % (annote.usage, item, ' | '.join(annote.choices)))
                item = annote.type(item)
                annote._cli_value = item
                pos += 1
            else:
                if var_arg_spec is None:
                    help("don't know what to do with %r" % item)
                var_arg_spec._cli_value += (var_arg_spec.type(item), )
    exc = None
    if print_help:
        _print()
        if Script.__usage__:
            _print('global options: ' + Script.__usage__ + '\n')
        _print('%s %s' % (program, func.__usage__))
        _print()
        raise SystemExit
    elif print_version:
        _print(_get_version(script_module['module']))
        raise SystemExit
    elif print_all_versions:
        _print('\n'.join(_get_all_versions(script_module)))
        raise SystemExit
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

def Bool(arg):
    if arg in (True, False):
        return arg
    return arg.lower() in "true t yes y 1 on".split()

def InputFile(arg):
    return open(arg)

def OutputFile(arg):
    return open(arg, 'w')


