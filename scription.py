"""
intelligently parses command lines

flags: true/false values
options: other specified value (e.g. user name)
global script variables:  i.e. debug=True (python expression)
"""

import sys
is_win = sys.platform.startswith('win')
if not is_win:
    import pty
    import resource
    import signal
    import termios

import atexit
import datetime
import email
import inspect
import logging
import os
import re
import select
import shlex
import smtplib
import socket
import tempfile
import time
import traceback
from enum import Enum
from functools import partial
from subprocess import Popen, PIPE, STDOUT
from syslog import syslog

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

# data
__all__ = (
    'Alias', 'Command', 'Script', 'Run', 'Spec',
    'Bool','InputFile', 'OutputFile', 'IniFile',
    'FLAG', 'KEYWORD', 'OPTION', 'MULTI', 'REQUIRED',
    'ScriptionError', 'ExecuteError', 'Execute',
    'get_response', 'user_ids',
    )

version = 0, 70, 82

module = globals()
script_module = None

py_ver = sys.version_info[:2]
registered = False
run_once = False

if py_ver < (3, 0):
    bytes = str
else:
    raw_input = input
    basestring = str

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
# deprecated
ExecutionError = ExecuteError

class Execute(object):
    """
    if password specified, runs command in forked process, otherwise runs in subprocess
    """

    def __init__(self, args, bufsize=-1, cwd=None, password=None, timeout=None):
        self.env = None
        if isinstance(args, basestring):
            args = shlex.split(args)
        if password is None:
            # use subprocess instead
            process = Popen(args, stdout=PIPE, stderr=PIPE, cwd=cwd)
            self.stdout = process.stdout.read().rstrip()
            self.returncode = 0
            self.stderr = process.stderr.read().rstrip()
            if self.stderr:
                self.returncode = -1
            self.closed = True
            self.terminated = True
            self.signal = None
            return
        if is_win:
            raise OSError("password support for Execute not currently implemented for Windows")
        self.pid, self.child_fd = pty.fork()
        if self.pid == 0: # child process
            self.child_fd = sys.stdout.fileno()
            os.dup2(1, 2)
            max_fd = resource.getrlimit(resource.RLIMIT_NOFILE)[1]
            for fd in range(3, max_fd):
                try:
                    os.close(fd)
                except OSError:
                    pass
            if cwd:
                os.chdir(cwd)
            try:
                if self.env:
                    os.execvpe(args[0], args, self.env)
                else:
                    os.execvp(args[0], args)
            except Exception:
                exc = sys.exc_info()[1]
                print("%s:  %s" % (exc.__class__.__name__, ' - '.join([str(a) for a in exc.args])))
                os._exit(-1)
        # parent process
        self.returncode = None
        self.signal = None
        output = []
        self.closed = False
        self.terminated = False
        submission_received = True
        # loop to read output
        time.sleep(0.25)
        last_comms = time.time()
        while self.is_alive():
            if not self.get_echo() and password and submission_received:
                self.write(password + '\r\n')
                submission_received = False
            while pocket(self.read(1024)):
                output.append(pocket())
                submission_received = True
                last_comms = time.time()
            time.sleep(0.1)
            if timeout and time.time() - last_comms > timeout:
                self.close()
        while pocket(self.read(1024)):
            output.append(pocket())
            time.sleep(0.1)
        self.stdout = ''.join(output).rstrip()
        self.stderr = ''
        self.close()

    def close(self, force=True):
        if not self.closed:
            os.close(self.child_fd)
            time.sleep(1)
            if self.is_alive():
                if not self.terminate(force):
                    raise ExecutionError("Could not terminate the child.")
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
        "non-blocking read"
        if self.closed:
            raise ValueError("I/O operation on closed file.")
        r, w, x = select.select([self.child_fd], [], [], 0)
        if not r:
            return ''
        if self.child_fd in r:
            try:
                result = os.read(self.child_fd, size)
            except OSError:
                result = ''
            return result.decode('utf-8')
        raise ExecutionException('unknown problem with read')


    def terminate(self, force=False):
        if not self.is_alive():
            return True
        for sig in (signal.SIGHUP, signal.SIGINT):
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
        print(retry)
    return type(answer)

class IniError(ValueError):
    """
    used to signify errors in the ini file
    """

class IniFile(object):
    """
    read and make available the settings of an ini file, converting
    the values as str, int, float, date, time, datetime based on:
      - presence of quotes
      - presenc of colons and/or hyphens
      - presence of period
    """
    _str = str
    _path = str
    _date = datetime.date
    _time = datetime.time
    _datetime = datetime.datetime
    _bool = bool
    _float = float
    _int = int

    def __init__(self, filename, section=None, export_to=None):
        # if section, only return defaults merged with section
        # if export_to, it should be a mapping, and will be populated
        # with the settings
        if section:
            section = section.lower()
        target_section = section
        defaults = {}
        settings = self._settings = _namespace()
        fh = open(filename)
        try:
            section = None
            for line in fh:
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

def mail(server, port, message):
    """sends email.message to server:port
    """
    if isinstance(message, basestring):
        message = email.message_from_string(message)
    receiver = message.get_all('To', []) + message.get_all('Cc', []) + message.get_all('Bcc', [])
    sender = message['From']
    try:
        smtp = smtplib.SMTP(server, port)
    except socket.error:
        exc = sys.exc_info()[1]
        send_errs = {}
        for rec in receiver:
            send_errs[rec] = (server, exc.args)
    else:
        try:
            send_errs = smtp.sendmail(sender, receiver, message.as_string())
        except smtplib.SMTPRecipientsRefused:
            exc = sys.exc_info()[1]
            send_errs = {}
            for user, detail in exc.recipients.items():
                send_errs[user] = (server, detail)
        finally:
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
    for user, errors in errs.items():
        for server, (code, response) in errors:
            syslog('%s: %s --> %s: %s' % (server, user, code, response))

def pocket(value=None, _pocket=[]):
    if value is not None:
        _pocket[:] = [value]
    return _pocket[0]

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


class ScriptionError(Exception):
    "raised for errors"
    def __init__(self, msg=None, command_line=None):
        super(ScriptionError, self).__init__(msg)
        self.command_line = command_line

class Spec(object):
    """tuple with named attributes for representing a command-line paramter

    help, kind, abbrev, type, choices, usage_name, remove, default
    """

    def __init__(self, help=empty, kind=empty, abbrev=empty, type=empty, choices=empty, usage=empty, remove=False, default=empty):
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
            if default and not isinstance(default, tuple):
                default = (default, )
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

    @property
    def value(self):
        if self._cli_value is not empty:
            value = self._cli_value
        elif self._script_default is not empty:
            value = self._script_default
        elif self._type_default is not empty:
            value = self._type_default
        else:
            raise ScriptionError('Spec object has no value (<%r, %r, %r, %r, %r, %r>)' %
                    (self.help, self.kind, self.abbrev, self.type, self.choices, self._type_default))
        return value

class Alias(object):
    "adds aliases for the function"
    def __init__(self, *aliases):
        self.aliases = aliases
    def __call__(self, func):
        for alias in self.aliases:
            Command.subcommands[alias] = func
        return func

class Command(object):
    "adds __scription__ to decorated function, and adds func to Command.subcommands"
    subcommands = {}
    def __init__(self, **annotations):
        for name, annotation in annotations.items():
            spec = Spec(annotation)
            annotations[name] = spec
        self.annotations = annotations
    def __call__(self, func):
        global script_module
        if script_module is None:
            script_module = _func_globals(func)
            script_module['script_module'] = _namespace(script_module)
        func.names = list(self.annotations.keys())
        _add_annotations(func, self.annotations)
        Command.subcommands[func.__name__] = func
        if not module['registered']:
            atexit.register(Main)
            module['registered'] = True
        _help(func)
        return func

class Script(object):
    "adds __scription__ to decorated function, and stores func in Script.command"
    command = None
    settings = {}
    names = []
    def __init__(self, **settings):
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
                spec._global = True
            settings[name] = spec
        Script.settings = settings
        Script.names = list(settings.keys())
    def __call__(self, func):
        if Script.command is not None:
            raise ScriptionError("Script can only be used once")
        global script_module
        script_module = _func_globals(func)
        script_module['script_module'] = _namespace(script_module)
        _add_annotations(func, Script.settings, script=True)
        _help(func)
        Script.settings = func.__scription__
        Script.command = staticmethod(func)
        if not module['registered']:
            atexit.register(Main)
            module['registered'] = True
        return func

def _add_annotations(func, annotations, script=False):
    '''
    add annotations as __scription__ to func
    '''
    params, varargs, keywords, defaults = inspect.getargspec(func)
    names = params + [varargs, keywords]
    errors = []
    for spec in annotations:
        if spec not in names:
            if not script:
                errors.append(spec)
    if errors:  
        raise ScriptionError("names %r not in %s's signature" % (errors, func.__name__))
    func.__scription__ = annotations

def _func_globals(func):
    '''
    return the function's globals
    '''
    if py_ver < (3, 0):
        return func.func_globals
    else:
        return func.__globals__

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
        spec = annotations.get(name, None)
        pos = None
        if spec is None:
            raise ScriptionError('%s not annotated' % name)
        help, kind, abbrev, arg_type, choices, usage_name, remove, default = spec
        arg_type_default = empty
        if name in vararg + keywordarg:
            if kind is empty:
                kind = 'option'
        elif kind == 'required':
            pos = max_pos
            max_pos += 1
        elif kind == 'flag':
            arg_type_default = False
            if abbrev is empty:
                abbrev = name[0]
        elif kind == 'option':
            arg_type_default = None
            if abbrev is empty:
                abbrev = name[0]
        elif kind == 'multi':
            arg_type_default = tuple()
            if abbrev is empty:
                abbrev = name[0]
            if default and not isinstance(default, tuple):
                default = (default, )
        else:
            raise ValueError('unknown kind: %r' % kind)
        if abbrev in annotations:
            raise ScriptionError('duplicate abbreviations: %r' % abbrev)
        if usage_name is empty:
            usage_name = name.upper()
        if arg_type is _identity and default is not empty:
            arg_type = type(default)
        # spec = Spec(help, kind, abbrev, arg_type, choices, usage_name, remove, default)
        spec.kind = kind
        spec.abbrev = abbrev
        spec.type = arg_type
        spec.usage = usage_name
        spec._script_default = default
        spec._type_default = arg_type_default
        if pos != max_pos:
            annotations[i] = spec
        annotations[name] = spec
        func._var_arg = func._kwd_arg = None
        if vararg:
            func._var_arg = annotations[vararg[0]]
        if keywordarg:
            func._kwd_arg = annotations[keywordarg[0]]
        if abbrev not in (None, empty):
            annotations[abbrev] = spec
    if defaults:
        for name, dflt in zip(reversed(params), reversed(defaults)):
            annote = annotations[name]
            if annote._script_default:
                # default specified in two places
                raise ScriptionError('default value for %s specified in Spec and in header (%r, %r)' %
                        (name, annote._script_default, dflt))
            if annote.kind != 'multi':
                annote._script_default = annote.type(dflt)
            else:
                if not isinstance(dflt, tuple):
                    dflt = (dflt, )
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
    print_params = []
    for param in params:
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
        usage.append("[%s [%s [...]]]" % (vararg[0], vararg[0]))
    if keywordarg:
        usage.append("[name1=value1 [name2=value2 [...]]]")
    usage = ['', ' '.join(usage), '']
    if func.__doc__:
        usage.extend(['    ' + func.__doc__.strip(), ''])
    for name in params:
        annote = annotations[name]
        choices = ''
        if annote._script_default is empty or annote._script_default is None or '[default: ' in annote.help:
            posi = ''
        else:
            posi = '[default: ' + repr(annote._script_default) + ']'
        if annote.choices:
            choices = '[ %s ]' % ' | '.join(annote.choices)
        usage.append('    %-15s %s %s %s' % (
            annote.usage,
            annote.help,
            posi,
            choices,
            ))
    for name in (vararg + keywordarg):
        usage.append('    %-15s %s' % (name, annotations[name].help))
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
    def __getitem__(self, name):
        try:
            return self.__dict__[name]
        except KeyError:
            raise ScriptionError("namespace object has nothing named %r" % name)
    def __setitem__(self, name, value):
        self.__dict__[name] = value

def _run_once(func, kwds):
    cache = []
    def later():
        global run_once
        if run_once:
            return cache[0]
        run_once = True
        result = func(**kwds)
        cache.append(result)
        return result
    return later

def _split_on_comma(text):
    if ',' not in text:
        return [text]
    elif '\\,' not in text:
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
        return values

def _usage(func, param_line_args):
    program = param_line_args[0]
    args = []
    kwargs = {}
    pos = 0
    max_pos = func.max_pos
    print_help = False
    value = None
    rest = []
    doubledash = False
    annotations = func.__scription__
    script_annotations = Script.settings
    var_arg_spec = kwd_arg_spec = None
    if Script.command:
        var_arg_spec = Script.command._var_arg
        kwd_arg_spec = Script.command._kwd_arg
    if func._var_arg:
        var_arg_spec = func._var_arg
    if func._kwd_arg:
        kwd_arg_spec = func._kwd_arg
    to_be_removed = []
    param_line_args = shlex.split(' '.join(param_line_args[1:]))
    for offset, item in enumerate(param_line_args + [None]):
        offset += 1
        original_item = item
        if value is not None:
            if item is None or item.startswith('-') or '=' in item:
                raise ScriptionError('%s has no value' % last_item)
            if annote.remove:
                to_be_removed.append(offset)
            value = item
            if annote.kind == 'option':
                annote._cli_value = annote.type(value)
            elif annote.kind == 'multi':
                annote._cli_value += tuple([annote.type(a) for a in _split_on_comma(value)])
            else:
                raise ScriptionError('Error: kind %r not in (multi, option)' % annote.kind)
            value = None
            continue
        if item is None:
            break
        if doubledash:
            rest.append(item)
            continue
        if item == '--':
            doubledash = True
            continue
        if item.startswith('-'):
            # (multi)option or flag
            if item.lower() == '--help':
                print_help = True
                continue
            item = item.lstrip('-')
            value = True
            if item.lower().startswith('no-') and '=' not in item:
                value = False
                item = item[3:]
            elif '=' in item:
                item, value = item.split('=', 1)
            item = item.replace('-','_')
            if item in annotations:
                annote = annotations[item]
            elif item in script_annotations:
                annote = script_annotations[item]
            elif item in ('SCRIPTION_DEBUG', ):
                Script.settings[item] = value
                value = None
                continue
            else:
                raise ScriptionError('%s not valid' % original_item, ' '.join(param_line_args))
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
                        annote._cli_value += tuple([annote.type(a) for a in _split_on_comma(value)])
                    value = None
            elif annote.kind == 'flag':
                value = annote.type(value)
                annote._cli_value = value
                value = None
        elif '=' in item:
            # no lead dash, keyword args
            if kwd_arg_spec is None:
                raise ScriptionError("don't know what to do with %r" % item)
            item, value = item.split('=')
            item = item.replace('-','_')
            if item in params:
                raise ScriptionError('%s must be specified as a %s' % (item, annotations[item].kind))
            item, value = kwd_arg_spec.type(item, value)
            if not isinstance(item, str):
                raise ScriptionError('keyword names must be strings', ' '.join(param_line_args))
            kwargs[item] = value
            value = None
        else:
            # positional (required?) argument
            if pos < max_pos:
                annote = annotations[pos]
                # check for choices membership before transforming into a type
                if annote.choices and item not in annote.choices:
                    raise ScriptionError('%r not in [ %s ]' % (item, ' | '.join(annote.choices)))
                item = annote.type(item)
                annote._cli_value = item
                pos += 1
            else:
                if var_arg_spec is None:
                    raise ScriptionError("don't know what to do with %r" % item)
                item = var_arg_spec.type(item)
                args.append(item)
    exc = None
    if args and rest:
        raise ScriptionError('-- should be used to separate %s arguments from the rest' % program)
    elif rest:
        args = rest
    if print_help:
        print('%s: usage -->' % program, program, func.__usage__)
        sys.exit()
    # if pos < max_pos:
    for setting in set(func.__scription__.values()):
        if setting.kind == 'required':
            setting.value
        # raise ScriptionError('\n01 - Invalid command line:  %r' % ' '.join(param_line_args))
    if args and not _var_arg_spec:
        raise ScriptionError("\n02 - don't know what to do with %r" % ', '.join(args))
    elif args:
        var_arg_spec._cli_value = args
    if kwargs and not kwd_arg_spec:
        raise ScriptionError("\n03 - don't know what to do with %r" % ', '.join(['%s=%s' % (k, v) for k, v in kwargs.items()]))
    elif kwargs:
        kwd_arg_spec._cli_value = kwangs
    if var_arg_spec and var_arg_spec.kind == 'required' and not args:
        raise ScriptionError('\n04 - %r values are required\n' % vararg[0])
    # remove any command line args that shouldn't be passed on
    new_args = []
    for i, arg in enumerate(param_line_args):
        if i not in to_be_removed:
            if ' ' in arg:
                new_args.extend(('"' + arg.replace('"','\\"') + '"').split())
    sys.argv[1:] = new_args
    main = {}
    for name in Script.names:
        annote = Script.settings[name]
        value = annote.value
        if annote._global:
            script_module[name] = value
        else:
            main[name] = value
    sub = {}
    for name in func.names:
        annote = func.__scription__[name]
        value = annote.value
        sub[name] = value
    return main, sub

def Main():
    "calls Run() only if the script is being run as __main__"
    if script_module['__name__'] == '__main__':
        return Run()

def Run():
    "parses command-line and compares with either func or, if None, Script.command"
    if module.get('HAS_BEEN_RUN'):
        return
    module['HAS_BEEN_RUN'] = True
    debug = Script.settings.get('SCRIPTION_DEBUG')
    try:
        prog_name = os.path.split(sys.argv[0])[1]
        if debug:
            print(prog_name.filename)
        if not Command.subcommands:
            raise ScriptionError("no Commands defined in script")
        func_name = sys.argv[1:2]
        if not func_name:
            func = None
        else:
            func = Command.subcommands.get(func_name[0])
        if func is not None:
            prog_name = func_name[0]
            param_line = [prog_name] + sys.argv[2:]
        else:
            func = Command.subcommands.get(prog_name, None)
            if func is not None:
                param_line = [prog_name] + sys.argv[1:]
            else:
                for name, func in sorted(Command.subcommands.items()):
                    print func.__usage__
                    # try:
                    #     _usage(func, [name, '--help'])
                    # except SystemExit:
                    #     print
                    #     continue
                sys.exit(-1)
        main, sub = _usage(func, param_line)
        main_cmd = Script.command
        # script_module.update(Script.settings)
        if main_cmd:
            script_module['script_command'] = subcommand = _run_once(_func, sub)
            main_cmd(**main)
            return subcommand()
        else:
            # no Script command, only subcommand
            return func(**sub)
    except Exception:
        exc = sys.exc_info()[1]
        if debug:
            print(exc)
        result = log_exception()
        script_module['exception_lines'] = result
        if isinstance(exc, ScriptionError):
            raise SystemExit(str(exc))
        raise

def Bool(arg):
    if arg in (True, False):
        return arg
    return arg.lower() in "true t yes y 1 on".split()

def InputFile(arg):
    return open(arg)

def OutputFile(arg):
    return open(arg, 'w')


# from scription.api import *

class fake_module(object):

    def __init__(self, name, *args):
        self.name = name
        self.__all__ = []
        all_objects = globals()
        for name in args:
            self.__dict__[name] = all_objects[name]
            self.__all__.append(name)

    def register(self):
        sys.modules["%s.%s" % (__name__, self.name)] = self

fake_module('api', *__all__).register()
