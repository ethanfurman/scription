"intelligently parses command lines"

import inspect
import smtplib
import sys
import traceback
from email.mime.text import MIMEText
from path import Path
from syslog import syslog

"-flags -f --flag -o=foo --option4=bar param1 param2 ..."

"""
(help, kind, abbrev, type, choices, metavar)

  - help --> the help message

  - kind --> what kind of parameter
    - flag       --> simple boolean
    - option     --> option_name=value
    - keyword    --> key=value syntax (no dashes, key can be any
                     valid Python identifier)
    - required --> just like it says (default)

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
__all__ = ('Command', 'Script', 'Run', 'InputFile', 'Bool')

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
    """sends email.message to server:port"""
    receiver = []
    msg = MIMEText(message.get_payload())
    msg['From'] = message.get('From')
    for to in ('To', 'Cc', 'Bcc'):
        for address in message.get_all(to, []):
            msg[to] = address
            receiver.append(address)
    for header, value in message.items():
        if header in ('To','From', 'Cc', 'Bcc'):
            continue
        msg[header] = value
    smtp = smtplib.SMTP(server, port)
    try:
        send_errs = smtp.sendmail(msg['From'], receiver, msg.as_string())
    except smtplib.SMTPRecipientsRefused, exc:
        send_errs = exc.recipients
    smtp.quit()
    errs = {}
    if send_errs:
        for user in send_errs:
            server = 'mail.' + user.split('@')[1]
            smtp = smtplib.SMTP(server, 25)
            try:
                smtp.sendmail(msg['From'], [user], msg.as_string())
            except smtplib.SMTPRecipientsRefused, exc:
                errs[user] = [send_errs[user], exc.recipients[user]]
            smtp.quit()
    for user, errors in errs.items():
        for code, response in errors:
            syslog.syslog('%s --> %s: %s' % (user, code, response))

class ScriptionError(Exception):
    "raised for errors"

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
    #if not params:
    #    raise ScriptionError("No parameters -- what's the point?")
    annotations = getattr(func, '__annotations__', {})
    indices = {}
    max_pos = 0
    positional = []
    for i, name in enumerate(params + vararg + keywordarg):
        spec = annotations.get(name, '')
        help, kind, abbrev, type, choices, metavar = Spec(spec)
        if kind == 'required':
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
            raise ScriptionError('duplicate abbreviations: %r' % abbrev)
        spec = Spec(help, kind, abbrev, type, choices, metavar)
        annotations[i] = spec
        annotations[name] = spec
        indices[name] = i
        if abbrev is not None:
            annotations[abbrev] = spec
            indices[abbrev] = i
    if defaults:
        positional[-len(defaults):] = defaults

    if not vararg or annotations[vararg[0]].type is None:
        vararg_type = lambda x: x
    else:
        vararg_type = annotations[vararg[0]].type
    if not keywordarg or annotations[keywordarg[0]].type is None:
        keywordarg_type = lambda x: x
    else:
        keywordarg_type = annotations[keywordarg[0]].type
    program = param_line_args[0]
    if '/' in program:
        program = program.rsplit('/')[1]
    print_params = []
    for param in params:
        if annotations[param].kind in ('flag', 'option'):
            print_params.append('--' + param)
        else:
            print_params.append(param)
    usage = ["usage:", program] + print_params
    if vararg:
        usage.append("[{0} [{0} [...]]]".format(vararg[0]))
    if keywordarg:
        usage.append("[{0}=value [{0}=value [...]]]".format(keywordarg[0]))
    usage = ['', ' '.join(usage), '']
    if func.__doc__:
        usage.extend([func.__doc__, ''])
    usage.extend(["arguments:", ''])
    for i, name in enumerate(params):
        posi = positional[i]
        if posi is empty:
            posi = ''
        else:
            posi = 'default: ' + repr(posi)
        annote = annotations[name]
        usage.append('    %-15s %s %s %s' % (
            annote.metavar or name,
            annote.help,
            posi,
            annote.choices or '',
            ))
    for name in (vararg + keywordarg):
        usage.append('    %-15s %-15s %s' % (name, '', annotations[name].help))

    func.__usage__ = '\n'.join(usage)
    args = []
    kwargs = {}
    pos = 0
    print_help = False
    value = None
    for item in param_line_args[1:] + [None]:
        # required arguments /should/ be kept together
        # once an option is found all text until the next option/flag/variable
        # is part of that option
        if value is not None:
            if item is None or item.startswith('-') or '=' in item:
                value = annote.type(value.strip())
                positional[index] = value
                value = None
            else:
                value += ' ' + item
                continue
        if item is None:
            break
        if item.startswith('-'):
            item = item.lstrip('-')
            if item in ('h', 'help'):
                print_help = True
                continue
            value = True
            if item.startswith('no-') and '=' not in item:
                value = False
                item = item[3:]
            elif '=' in item:
                item, value = item.split('=', 1)
            if item not in annotations:
                if item in Script.settings:
                    Script.settings[item] = value
                else:
                    raise ScriptionError('%s not valid' % item)
            index = indices[item]
            annote = annotations[item]
            if annote.kind == 'option' and value in (True, False):
                value = ''
            elif annote.kind == 'flag':
                value = annote.type(value)
                positional[index] = value
                value = None
        elif '=' in item:
            item, value = item.split('=')
            if item in params:
                raise ScriptionError('%s must be specified as a %s' % (item, annotations[item].kind))
            value = keywordarg_type(value)
            kwargs[item] = value
            value = None
        else:
            if pos < max_pos:
                annote = annotations[pos]
                item = annote.type(item)
                positional[pos] = item
                pos += 1
            else:
                item = vararg_type(item)
                args.append(item)
    if print_help:
        print func.__usage__
        sys.exit(-1)
    if not all([p is not empty for p in positional]):
        print func.__usage__
        sys.exit(-1)
    if args and not vararg or kwargs and not keywordarg:
        print func.__usage__
        sys.exit(-1)
    return tuple(positional + args), kwargs

def Run(logger=None):
    "parses command-line and compares with either func or, if None, Script.command"
    module = None
    try:
        prog_name = Path(sys.argv[0]).filename
        if logger:
            logger.openlog(str(prog_name.filename), logger.LOG_PID)
        if Script.command and Command.subcommands:
            raise ScriptionError("scription does not support both Script and Command in the same file")
        if Script.command is None and not Command.subcommands:
            raise ScriptionError("either Script or Command must be specified")
        if Command.subcommands:
            func = Command.subcommands.get(prog_name, None)
            if func is not None:
                module = func.func_globals
                prog_name = sys.argv[0]
                param_line = [prog_name] + sys.argv[1:]
            else:
                func_name = sys.argv[1:2]
                if not func_name:
                    func = None
                else:
                    func = Command.subcommands.get(func_name[0])
                if func and func is not None:
                    module = func.func_globals
                    prog_name = ' '.join(sys.argv[:2])
                    param_line = [prog_name] + sys.argv[2:]
                else:
                    for name, func in sorted(Command.subcommands.items()):
                        try:
                            usage(func, [name])
                        except SystemExit:
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
        if logger:
            result = log_exception()
            if module:
                module['exception_lines'] = result
        raise

def InputFile(arg):
    return open(arg)

def Bool(arg):
    if arg in (True, False):
        return arg
    return arg.lower() in "true t yes y 1 on".split()
