"""
intelligently parses command lines

flags: true/false values
options: other specified value (e.g. user name)
global script variables:  i.e. debug=True (python expression)
"""

import email
import inspect
import os
import pty
import resource
import select
import signal
import smtplib
import socket
import sys
import tempfile
import termios
import time
import traceback
from enum import Enum
from path import Path
from syslog import syslog

"-flags -f --flag -o=foo --option4=bar param1 param2 ..."

"""
(help, kind, abbrev, type, choices, metavar)

  - help --> the help message

  - kind --> what kind of parameter
    - flag       --> simple boolean
    - option     --> option_name value
    - keyword    --> key=value syntax (no dashes, key can be any
                     valid Python identifier)
    - required   --> just like it says (default)

  - abbrev is a one-character string (defaults to first letter of
    argument)

  - type is a callable that converts the arguments to any Python
    type; by default there is no conversion and type=None 

  - choices is a discrete sequence of values used to restrict the
    number of the valid options; by default there are no restrictions
    (i.e. choices=None)

  - metavar is used as the name of the parameter in the help message
"""

# TODO - understand this
# metavar has two meanings. For a required argument it is used to change the
# argument name in the usage message (and only there). By default the metavar is
# None and the name in the usage message is the same as the argument name. For an
# option the metavar is used differently in the usage message, which has now the
# form [--option-name METAVAR]. If the metavar is None, then it is equal to the
# uppercased name of the argument, unless the argument has a default: then it is
# equal to the stringified form of the default.

# data
__all__ = (
    'Command', 'Script', 'Run',
    'InputFile', 'Bool',
    'FLAG', 'OPTION', 'KEYWORD', 'REQUIRED',
    'ScriptionError',
    )

version = 0, 45, 2

try:
    bytes
except NameError:
    bytes = str

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
        if len(args) == 1 and isinstance(args[0], (str, unicode)):
            self.__doc__ = args[0]
        elif args:
            raise TypeError('%s not dealt with -- need custom __init__' % (args,))

    def __eq__(self, other):
        if isinstance(other, (str, unicode)):
            return self._value_ == other.lower()
        elif not isinstance(other, self.__class__):
            return NotImplemented
        return self is other

    def __ne__(self, other):
        return not self == other


class SpecKind(DocEnum):
    FLAG = "True/False setting"
    OPTION = "variable setting"
    KEYWORD = "global setting (useful for @Command scripts)"
    REQUIRED = "required setting"
globals().update(SpecKind.__members__)

class ExecutionError(Exception):
    "errors raised by Execute"

class Execute(object):
    "runs command in forked process"

    def __init__(self, args, bufsize=-1, cwd=None, password=None, **kwds):
        self.env = None
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
            except Exception, exc:
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
        while self.is_alive():
            if not self.get_echo() and password and submission_received:
                self.write(password + '\r\n')
                submission_received = False
            while pocket(self.read(1024)):
                output.append(pocket())
                submission_received = True
            time.sleep(0.1)
        while pocket(self.read(1024)):
            output.append(pocket())
            time.sleep(0.1)
        self.stdout = ''.join(output)
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


def log_exception(tb=None):
    if tb is None:
        exc, err, tb = sys.exc_info()
        lines = traceback.format_list(traceback.extract_tb(tb))
        lines.append('%s: %s\n' % (exc.__name__, err))
        syslog('Traceback (most recent call last):')
    else:
        lines = tb.split('\\n')
    for line in lines:
        for ln in line.rstrip().split('\n'):
            syslog(ln)
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
    except socket.error, exc:
        send_errs = {}
        for rec in receiver:
            send_errs[rec] = (server, exc.args)
    else:
        try:
            send_errs = smtp.sendmail(sender, receiver, message.as_string())
        except smtplib.SMTPRecipientsRefused, exc:
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
            except socket.error, exc:
                errs[user] = [send_errs[user], (server, exc.args)]
            else:
                try:
                    smtp.sendmail(sender, [user], message.as_string())
                except smtplib.SMTPRecipientsRefused, exc:
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

class ScriptionError(Exception):
    "raised for errors"
    def __init__(self, msg=None, command_line=None):
        super(ScriptionError, self).__init__(msg)
        self.command_line = command_line

class Spec(tuple):
    """tuple with named attributes for representing a command-line paramter

    help, kind, abbrev, type, choices, metavar
    """

    __slots__= ()
    def __new__(cls, *args):
        if not args or isinstance(args[0], (str, unicode)):
            pass
        else:
            args = args[0]
        args = list(args) + [None] * (6 - len(args))
        if not args[0]:
            args[0] = ''
        if not args[1]:
            args[1] = 'required'
        if not args[3]:
            args[3] = lambda x: x
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
    def metavar(self):
        return self[5]

class Command(object):
    "adds __annotations__ to decorated function, and adds func to Command.subcommands"
    subcommands = {}
    def __init__(self, **annotations):
        self.annotations = annotations
    def __call__(self, func):
        _add_annotations(func, self.annotations)
        Command.subcommands[func.__name__] = func
        return func

class Script(object):
    "adds __annotations__ to decorated function, and stores func in Script.command"
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
    func.__annotations__ = annotations

class empty(object):
    def __nonzero__(self):
        return False
    def __repr__(self):
        return '<empty>'
empty = empty()

def usage(func, param_line_args):
    params, vararg, keywordarg, defaults = inspect.getargspec(func)
    params = list(params)
    vararg = [vararg] if vararg else []
    keywordarg = [keywordarg] if keywordarg else []
    defaults = list(defaults) if defaults else []
    annotations = getattr(func, '__annotations__', {})
    indices = {}
    max_pos = 0
    positional = []
    for i, name in enumerate(params + vararg + keywordarg):
        spec = annotations.get(name, '')
        help, kind, abbrev, type, choices, metavar = Spec(spec)
        if name in keywordarg:
            kind = 'keyword'
        if kind == 'required' and name not in vararg + keywordarg:
            max_pos += 1
            positional.append(empty)
        elif kind == 'flag':
            positional.append(False)
            if not abbrev:
                abbrev = name[0]
        elif kind == 'option':
            positional.append(None)
        elif kind == 'keyword':
            pass
        if abbrev in annotations:
            raise ScriptionError('duplicate abbreviations: %r' % abbrev, ' '.join(param_line_args))
        spec = Spec(help, kind, abbrev, type, choices, metavar)
        annotations[i] = spec
        annotations[name] = spec
        indices[name] = i
        if abbrev is not None:
            annotations[abbrev] = spec
            indices[abbrev] = i
    if defaults:
        new_defaults = []
        for name, dflt in zip(reversed(params), reversed(defaults)):
            if isinstance(dflt, (str, unicode)):
                new_defaults.append(annotations[name].type(dflt))
            else:
                new_defaults.append(dflt)
        defaults = list(reversed(new_defaults))
        positional[-len(defaults):] = defaults
    if not vararg or annotations[vararg[0]].type is None:
        vararg_type = lambda x: x
    else:
        vararg_type = annotations[vararg[0]].type
    if not keywordarg or annotations[keywordarg[0]].type is None:
        keywordarg_type = lambda k, v: (k, v)
    else:
        kywd_func = annotations[keywordarg[0]].type
        if isinstance(kywd_func, tuple):
            keywordarg_type = lambda k, v: (kywd_func[0](k), kywd_func[1](v))
        else:
            keywordarg_type = lambda k, v: (k, kywd_func(v))
    program = param_line_args[0]
    print_params = []
    for param in params:
        if annotations[param].kind == 'flag':
            print_params.append('--' + param)
        elif annotations[param].kind == 'option':
            print_params.append('--' + param + ' ...')
        else:
            print_params.append(param)
    usage = ["usage:", program] + print_params
    if vararg:
        usage.append("[%s [%s [...]]]" % (vararg[0], vararg[0]))
    if keywordarg:
        usage.append("[%s=value [%s=value [...]]]" % (keywordarg[0], keywordarg[0]))
    usage = ['', ' '.join(usage), '']
    if func.__doc__:
        usage.extend(['    ' + func.__doc__.strip(), ''])
    for i, name in enumerate(params):
        posi = positional[i]
        if posi is empty:
            posi = ''
        else:
            posi = 'default: ' + repr(posi)
        annote = annotations[name]
        choices = ''
        if annote.choices:
            choices = '[ %s ]' % ' | '.join(annote.choices)
        usage.append('    %-15s %s %s %s' % (
            annote.metavar or name,
            annote.help,
            posi,
            choices,
            ))
    for name in (vararg + keywordarg):
        usage.append('    %-15s %s' % (annotations[name].metavar or name, annotations[name].help))

    func.__usage__ = '\n'.join(usage)
    args = []
    kwargs = {}
    pos = 0
    print_help = False
    value = None
    rest = []
    doubledash = False
    for item in param_line_args[1:] + [None]:
        # required arguments /should/ be kept together
        # once an option is found all text until the next option/flag/variable
        # is part of that option
        original_item = item
        if value is not None:
            if item is None or item.startswith('-') or '=' in item:
                raise ScriptionError('%s has no value' % last_item)
            else:
                value = annote.type(item)
                positional[index] = value
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
            if item not in annotations:
                if item in Script.settings or item in ('SCRIPTION_DEBUG', ):
                    Script.settings[item] = value
                    value = None
                    continue
                else:
                    raise ScriptionError('%s not valid' % original_item, ' '.join(param_line_args))
            index = indices[item]
            annote = annotations[item]
            if annote.kind == 'option' and value in (True, False):
                value = ''
                last_item = item
            elif annote.kind == 'flag':
                value = annote.type(value)
                positional[index] = value
                value = None
        elif '=' in item:
            item, value = item.split('=')
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
        print func.__usage__
        sys.exit()
    if not all([p is not empty for p in positional]):
        raise ScriptionError('\n01 - Invalid command line:  %s' % ' '.join(param_line_args))
    if args and not vararg:
        raise ScriptionError("\n02 - don't know what to do with %s" % ', '.join(args))
    elif kwargs and not keywordarg:
        raise ScriptionError("\n03 - don't know what to do with %s" % ', '.join(['%s=%s' % (k, v) for k, v in kwargs.items()]))
    elif vararg and annotations[vararg[0]].kind == 'required' and not args:
        raise ScriptionError('\n04 - %s values are required\n' % vararg[0])
    return tuple(positional + args), kwargs

def Run(logger=None):
    "parses command-line and compares with either func or, if None, Script.command"
    module = None
    debug = Script.settings.get('SCRIPTION_DEBUG')
    try:
        prog_name = Path(sys.argv[0]).filename
        if logger:
            logger.openlog(str(prog_name.filename), logger.LOG_PID)
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
                module = func.func_globals
                prog_name = func_name[0]
                param_line = [prog_name] + sys.argv[2:]
            else:
                func = Command.subcommands.get(prog_name, None)
                if func is not None:
                    module = func.func_globals
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
            module = func.func_globals
        args, kwargs = usage(func, param_line)
        func.func_globals.update(Script.settings)
        result = func(*args, **kwargs)
        if logger:
            logger.syslog('done')
            logger.closelog()
        return result
    except Exception:
        exc = sys.exc_info()[1]
        if debug:
            print exc
        if logger:
            result = log_exception()
            if module:
                module['exception_lines'] = result
        if isinstance(exc, ScriptionError):
            raise SystemExit(str(exc))
        raise

def InputFile(arg):
    return open(arg)

def Bool(arg):
    if arg in (True, False):
        return arg
    return arg.lower() in "true t yes y 1 on".split()


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
