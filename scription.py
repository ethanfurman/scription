from __future__ import print_function
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

version = 0, 70, 6

module = globals()

py_ver = sys.version_info[:2]

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

    class _namespace(object):
        def __getitem__(self, name):
            try:
                return self.__dict__[name]
            except KeyError:
                raise IniError("'settings' has nothing named %r" % name)

    def __init__(self, filename, section=None, export_to=None):
        # if section, only return defaults merged with section
        # if export_to, it should be a mapping, and will be populated
        # with the settings
        if section:
            section = section.lower()
        target_section = section
        defaults = {}
        settings = self._settings = self._namespace()
        with open(filename) as fh:
            section = None
            for line in fh:
                line = line.strip()
                if not line or line.startswith(('#',';')):
                    continue
                if line[0] + line[-1] == '[]':
                    # section header
                    section = self._verify_section_header(line[1:-1])
                    if target_section is None:
                        new_section = self._namespace()
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

class Spec(tuple):
    """tuple with named attributes for representing a command-line paramter

    help, kind, abbrev, type, choices, usage_name
    """

    __slots__= ()
    def __new__(cls, help=empty, kind=empty, abbrev=empty, type=empty, choices=empty, usage=empty, remove=False):
        if isinstance(help, tuple):
            args = help
        else:
            args = (help, kind, abbrev, type, choices, usage, remove)
        args = list(args) + [empty] * (7 - len(args))
        if not args[0]:
            args[0] = ''
        if not args[1]:
            args[1] = 'required'
        if not args[3]:
            args[3] = _identity
        if not args[4]:
            args[4] = []
        return tuple.__new__(cls, args)
    @property
    def help(self):
        return self[0]
    @property
    def kind(self):
        return self[1]
    @property
    def abbrev(self):
        return self[2]
    @property
    def type(self):
        return self[3]
    @property
    def choices(self):
        return self[4]
    @property
    def usage_name(self):
        return self[5]
    @property
    def remove(self):
        return self[6]


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
        self.annotations = annotations
    def __call__(self, func):
        _add_annotations(func, self.annotations)
        Command.subcommands[func.__name__] = func
        return func

class Script(object):
    "adds __scription__ to decorated function, and stores func in Script.command"
    command = None
    settings = {}
    def __init__(self, **annotations):
        self.annotations = annotations
        if not Script.settings:
            Script.settings = annotations
    def __call__(self, func):
        if Script.settings == self.annotations:
            Script.settings = {}
        _add_annotations(func, self.annotations)
        Script.command = staticmethod(func)
        return func

def _add_annotations(func, annotations):
    params, varargs, keywords, defaults = inspect.getargspec(func)
    names = params + [varargs, keywords]
    errors = []
    for spec in annotations:
        if spec not in names:
            errors.append(spec)
    if errors:  
        raise ScriptionError("names %r not in %s's signature" % (errors, func.__name__))
    func.__scription__ = annotations

def _func_globals(func):
    if py_ver < (3, 0):
        return func.func_globals
    else:
        return func.__globals__

def _identity(*args):
    if len(args) == 1:
        return args[0]
    return args
    

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
            raise ScriptionError('trailing "\" in argument %r' % text)
        return values

def usage(func, param_line_args):
    params, vararg, keywordarg, defaults = inspect.getargspec(func)
    params = list(params)
    vararg = [vararg] if vararg else []
    keywordarg = [keywordarg] if keywordarg else []
    defaults = list(defaults) if defaults else []
    annotations = getattr(func, '__scription__', {})
    indices = {}
    max_pos = 0
    positional = []
    to_be_removed = []
    multi_options = []
    for i, name in enumerate(params + vararg + keywordarg):
        spec = annotations.get(name, None)
        if spec is None:
            raise ScriptionError('%s not annotated' % name)
        help, kind, abbrev, type, choices, usage_name, remove = Spec(spec)
        if name in vararg + keywordarg:
            if kind is empty:
                kind = 'option'
        elif kind == 'required':
            max_pos += 1
            positional.append(empty)
        elif kind == 'flag':
            positional.append(False)
            if abbrev is empty:
                abbrev = name[0]
        elif kind == 'option':
            positional.append(None)
            if abbrev is empty:
                abbrev = name[0]
        elif kind == 'multi':
            if abbrev is empty:
                abbrev = name[0]
            multi_options.append(len(positional))
            positional.append(tuple())
        else:
            raise ValueError('unknown kind: %r' % kind)
        if abbrev in annotations:
            raise ScriptionError('duplicate abbreviations: %r' % abbrev, ' '.join(param_line_args))
        if usage_name is empty:
            usage_name = name.upper()
        spec = Spec(help, kind, abbrev, type, choices, usage_name, remove)
        annotations[i] = spec
        annotations[name] = spec
        indices[name] = i
        if abbrev not in (None, empty):
            annotations[abbrev] = spec
            indices[abbrev] = i
    if defaults:
        new_defaults = []
        for name, dflt in zip(reversed(params), reversed(defaults)):
            new_defaults.append(annotations[name].type(dflt))
        defaults = list(reversed(new_defaults))
        positional[-len(defaults):] = defaults
    # if any MULTI parameters have default values, wrap them in a list
    for i in multi_options:
        if not isinstance(positional[i], tuple):
            positional[i] = (positional[i], )
    if not vararg or annotations[vararg[0]].type is None:
        vararg_type = _identity
    else:
        vararg_type = annotations[vararg[0]].type
    if not keywordarg: #or annotations[keywordarg[0]].type is None:
        keywordarg_type = _identity #lambda k, v: (k, v)
    else:
        kywd_func = annotations[keywordarg[0]].type
        if isinstance(kywd_func, tuple):
            keywordarg_type = lambda k, v: (kywd_func[0](k), kywd_func[1](v))
        else:
            keywordarg_type = lambda k, v: (k, kywd_func(v))
    program = param_line_args[0]
    print_params = []
    for param in params:
        example = annotations[param].usage_name
        if annotations[param].kind == 'flag':
            print_params.append('--%s' % param)
        elif annotations[param].kind == 'option':
            print_params.append('--%s %s' % (param, example))
        elif annotations[param].kind == 'multi':
            print_params.append('--%s %s [--%s ...]' % (param, example, param))
        else:
            print_params.append(example)
    usage = ["usage:", program] + print_params
    if vararg:
        usage.append("[%s [%s [...]]]" % (vararg[0], vararg[0]))
    if keywordarg:
        usage.append("[name1=value1 [name2=value2 [...]]]")
    usage = ['', ' '.join(usage), '']
    if func.__doc__:
        usage.extend(['    ' + func.__doc__.strip(), ''])
    for i, name in enumerate(params):
        annote = annotations[name]
        choices = ''
        posi = positional[i]
        if posi is empty or posi is None or '[default: ' in annote.help:
            posi = ''
        else:
            posi = '[default: ' + repr(posi) + ']'
        if annote.choices:
            print(type(annote.choices))
            choices = '[ %s ]' % ' | '.join(annote.choices)
        usage.append('    %-15s %s %s %s' % (
            annote.usage_name,
            annote.help,
            posi,
            choices,
            ))
    for name in (vararg + keywordarg):
        usage.append('    %-15s %s' % (name, annotations[name].help))

    func.__usage__ = '\n'.join(usage)
    args = []
    kwargs = {}
    pos = 0
    print_help = False
    value = None
    rest = []
    doubledash = False
    for offset, item in enumerate(param_line_args[1:] + [None]):
        offset += 1
        original_item = item
        if value is not None:
            if item is None or item.startswith('-') or '=' in item:
                raise ScriptionError('%s has no value' % last_item)
            to_be_removed.append(offset)
            value.append(item)
            if value[0][0] == '"':
                if value[-1][-1] != '"':
                    continue
                value = ' '.join(value).strip('"')
            else:
                [value] = value
            if annote.kind == 'option':
                value = annote.type(value)
                positional[index] = value
            elif annote.kind == 'multi':
                positional[index] = positional[index] + tuple([annote.type(a) for a in _split_on_comma(value)])
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
            if item not in annotations:
                if item in Script.settings or item in ('SCRIPTION_DEBUG', ):
                    Script.settings[item] = value
                    value = None
                    continue
                else:
                    raise ScriptionError('%s not valid' % original_item, ' '.join(param_line_args))
            index = indices[item]
            annote = annotations[item]
            if annote.remove:
                to_be_removed.append(offset)
            if annote.kind in ('multi', 'option'):
                if annote.kind == 'multi':
                    if index in multi_options:
                        multi_options.remove(index)
                        positional[index] = tuple()
                if value in (True, False):
                    value = []
                    last_item = item
                elif value[0] == '"':
                    value = [value]
                else:
                    if annote.kind == 'option':
                        positional[index] = annote.type(value)
                    else:
                        # value could be a list of comma-separated values
                        positional[index] = positional[index] + tuple([annote.type(a) for a in _split_on_comma(value)])
                    value = None
            elif annote.kind == 'flag':
                value = annote.type(value)
                positional[index] = value
                value = None
        elif '=' in item:
            item, value = item.split('=')
            item = item.replace('-','_')
            if item in params:
                raise ScriptionError('%s must be specified as a %s' % (item, annotations[item].kind))
            item, value = keywordarg_type(item, value)
            if not isinstance(item, str):
                raise ScriptionError('keyword names must be strings', ' '.join(param_line_args))
            kwargs[item] = value
            value = None
        else:
            if pos < max_pos:
                annote = annotations[pos]
                # check for choices membership before transforming into a type
                if annote.choices and item not in annote.choices:
                    raise ScriptionError('%r not in [ %s ]' % (item, ' | '.join(annote.choices)))
                item = annote.type(item)
                positional[pos] = item
                pos += 1
            else:
                item = vararg_type(item)
                args.append(item)
    exc = None
    if args and rest:
        raise ScriptionError('-- should be used to separate %s arguments from the rest' % program)
    elif rest:
        args = rest
    if print_help:
        print(func.__usage__)
        sys.exit()
    if not all([p is not empty for p in positional]):
        raise ScriptionError('\n01 - Invalid command line:  %s' % ' '.join(param_line_args))
    if args and not vararg:
        raise ScriptionError("\n02 - don't know what to do with %s" % ', '.join(args))
    elif kwargs and not keywordarg:
        raise ScriptionError("\n03 - don't know what to do with %s" % ', '.join(['%s=%s' % (k, v) for k, v in kwargs.items()]))
    elif vararg and annotations[vararg[0]].kind == 'required' and not args:
        raise ScriptionError('\n04 - %s values are required\n' % vararg[0])
    # remove any command line args that shouldn't be passed on
    sys.argv[:] = [arg for (i, arg) in enumerate(sys.argv) if i not in to_be_removed]
    return tuple(positional + args), kwargs

def Run():
    "parses command-line and compares with either func or, if None, Script.command"
    module = None
    debug = Script.settings.get('SCRIPTION_DEBUG')
    try:
        # prog_name = Path(sys.argv[0]).filename
        prog_name = os.path.split(sys.argv[0])[1]
        if debug:
            print(prog_name.filename)
        if Script.command and Command.subcommands:
            raise ScriptionError("scription does not support both Script and Command in the same file")
        if Script.command is None and not Command.subcommands:
            raise ScriptionError("either Script or Command must be specified")
        if Command.subcommands:
            func_name = sys.argv[1:2]
            if not func_name:
                func = None
            else:
                func = Command.subcommands.get(func_name[0])
            if func is not None:
                module = _func_globals(func)
                prog_name = func_name[0]
                param_line = [prog_name] + sys.argv[2:]
            else:
                func = Command.subcommands.get(prog_name, None)
                if func is not None:
                    module = _func_globals(func)
                    param_line = [prog_name] + sys.argv[1:]
                else:
                    for name, func in sorted(Command.subcommands.items()):
                        try:
                            usage(func, [name, '--help'])
                        except SystemExit:
                            print
                            continue
                    sys.exit(-1)
        else:
            param_line = sys.argv[:]
            func = Script.command
            module = _func_globals(func)
        args, kwargs = usage(func, param_line)
        _func_globals(func).update(Script.settings)
        result = func(*args, **kwargs)
        return result
    except Exception:
        exc = sys.exc_info()[1]
        if debug:
            print(exc)
        result = log_exception()
        if module:
            module['exception_lines'] = result
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
