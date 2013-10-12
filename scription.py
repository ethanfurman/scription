"intelligently parses command lines"

import inspect
import sys
import traceback
from syslog import syslog

"-flags -f --flag -o=foo --option4=bar param1 param2 ..."

"""
(help, kind, abbrev, type, choices, metavar)

  - help --> the help message

  - kind --> what kind of parameter
    - flag       --> simple boolean
    - option     --> option_name=value
    - positional --> just like it says (default)n

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
# metavar has two meanings. For a positional argument it is used to change the
# argument name in the usage message (and only there). By default the metavar is
# None and the name in the usage message is the same as the argument name. For an
# option the metavar is used differently in the usage message, which has now the
# form [--option-name METAVAR]. If the metavar is None, then it is equal to the
# uppercased name of the argument, unless the argument has a default: then it is
# equal to the stringified form of the default.

# data
__all__ = ('Command', 'Script', 'Run', 'InputFile', 'Bool')

def log_exception():
    exc, err, tb = sys.exc_info()
    lines = traceback.format_list(traceback.extract_tb(tb))
    lines.append('%s: %s\n' % (exc.__name__, err))
    syslog('Traceback (most recent call last):')
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
    "tuple with named attributes for representing a command-line paramter"
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
            args[1] = 'positional'
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
    def __init__(self, **annotations):
        self.annotations = annotations
    def __call__(self, func):
        _add_annotations(func, self.annotations)
        Script.command = staticmethod(func)
        return func

def _add_annotations(func, annotations):
    argspec = inspect.getargspec(func)
    names = argspec.args + [argspec.varargs, argspec.keywords]
    errors = []
    for spec in annotations:
        if spec not in names:
            errors.append(spec)
    if errors:  
        raise ScriptionError("names %r not in %s's signature" % (errors, func.__name__))
    func.__annotations__ = annotations

def usage(func):
    params, vararg, keywordarg, defaults = inspect.getargspec(func)
    params = list(params)
    vararg = [vararg] if vararg else []
    keywordarg = [keywordarg] if keywordarg else []
    defaults = list(defaults) if defaults else []
    max_pos = len(params) - len(defaults)
    if not params:
        raise ScriptionError("No parameters -- what's the point?")
    annotations = getattr(func, '__annotations__', {})
    indices = {}
    for i, name in enumerate(params + vararg + keywordarg):
        spec = annotations.get(name, '')
        help, kind, abbrev, type, choices, metavar = Spec(spec)
        if kind == 'flag' and not abbrev:
            abbrev = name[0]
        if abbrev in annotations:
            raise ScriptionError('duplicate abbreviations: %r' % abbrev)
        spec = Spec(help, kind, abbrev, type, choices, metavar)
        annotations[i] = spec
        annotations[name] = spec
        indices[name] = i
        if abbrev is not None:
            annotations[abbrev] = spec
            indices[abbrev] = i


    if not vararg or annotations[vararg[0]].type is None:
        vararg_type = lambda x: x
    else:
        vararg_type = annotations[vararg[0]].type
    if not keywordarg or annotations[keywordarg[0]].type is None:
        keywordarg_type = lambda x: x
    else:
        keywordarg_type = annotations[keywordarg[0]].type
    program = sys.argv[0]
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
    positional = [None] * (len(params) - len(defaults)) + defaults
    usage.extend(["arguments:", ''])
    for i, name in enumerate(params):
        annote = annotations[name]
        usage.append('    %-15s %-15s %s %s' % (
            annote.metavar or name,
            positional[i],
            annote.help,
            annote.choices or '',
            ))
    for name in  (vararg + keywordarg):
        usage.append('    %-15s %-15s %s' % (name, '', annotations[name].help))

    func.__usage__ = '\n'.join(usage)
    args = []
    kwargs = {}
    pos = 0
    print_help = False
    for item in sys.argv[1:]:
        if item.startswith(('-', '--')):
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
                raise ScriptionError('%s not valid' % item)
            index = indices[item]
            annote = annotations[item]
            value = annote.type(value)
            positional[index] = value
        elif '=' in item:
            item, value = item.split('=')
            if item in params:
                raise ScriptionError('%s must be specified as a %s' % (item, annotations[item].kind))
            value = keywordarg_type(value)
            kwargs[item] = value
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
        print func.__usage__ + '\n00\n'
        sys.exit(-1)
    if not all([p is not None for p in positional]):
        print func.__usage__ + '\n01\n'
        sys.exit(-1)
    if args and not vararg or kwargs and not keywordarg:
        print func.__usage__ + '\n02\n'
        sys.exit(-1)
    return positional + args, kwargs

def Run():
    "parses command-line and compares with either func or, if None, Script.command"
    #print repr(Script.command), repr(Command.subcommands)
    if Script.command and Command.subcommands:
        raise ScriptionError("scription does not support both Script and Command in the same file")
    if Script.command is None and not Command.subcommands:
        raise ScriptionError("either Script or Command must be specified")
    if Command.subcommands:
        func = Command.subcommands.get(sys.argv[1], None)
        if func is None:
            print "usage: %s [%s]" % (sys.argv[0], ' | '.join(sorted(Command.subcommands.keys())))
            return
        sys.argv.pop(1)
    else:
        func = Script.command
    args, kwargs = usage(func)

    return func(*args, **kwargs)

def InputFile(arg):
    return file(arg)

def Bool(arg):
    if arg in (True, False):
        return arg
    return arg.lower() in "true t yes y 1 on".split()
