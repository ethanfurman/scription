"intelligently parses command lines"

import inspect
import sys

"-flags -o1 -o2 --option3 --option4 param1 param2 ..."

"""
(help, kind, abbrev, type, choices, metavar)

where help is the help message, kind is a string in the set { "flag", "option",
"positional"}, abbrev is a one-character string or None, type is a callable
taking a string in input, choices is a discrete sequence of values and metavar
is a string.

type is used to automagically convert the command line arguments from the
string type to any Python type; by default there is no conversion and type=None.

choices is used to restrict the number of the valid options; by default there
is no restriction i.e. choices=None.

metavar has two meanings. For a positional argument it is used to change the
argument name in the usage message (and only there). By default the metavar is
None and the name in the usage message is the same as the argument name. For an
option the metavar is used differently in the usage message, which has now the
form [--option-name METAVAR]. If the metavar is None, then it is equal to the
uppercased name of the argument, unless the argument has a default: then it is
equal to the stringified form of the default.
"""

# data
__all__ = ('Command', 'Script', 'Run', 'InputFile', 'Bool')

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
        raise TypeError("names %r not in %s's signature" % (errors, func.__name__))
    func.__annotations__ = annotations

def usage(func):
    params, vararg, keywordarg, defaults = inspect.getargspec(func)
    params = list(params)
    vararg = [vararg] if vararg else []
    keywordarg = [keywordarg] if keywordarg else []
    defaults = list(defaults) if defaults else []
    if not params:
        raise ScriptionError("No parameters -- what's the point?")
        #return func()
    annotations = getattr(func, '__annotations__', {})
    for name in params + vararg + keywordarg:
        spec = annotations.get(name, '')
        help, kind, abbrev, type, choices, metavar = Spec(spec)
        if kind == 'flag' and not abbrev:
            abbrev = name[0]
        annotations[name] = Spec(help, kind, abbrev, type, choices, metavar)


    if not vararg or annotations[vararg[0]].type is None:
        vararg_type = lambda x: x
    else:
        vararg_type = annotations[vararg[0]].type
    if not keywordarg or annotations[keywordarg[0]].type is None:
        keywordarg_type = lambda x: x
    else:
        keywordarg_type = annotations[keywordarg[0]].type
    program = sys.argv[0]
    usage = ["usage:", program] + params
    if vararg:
        usage.append("[{0} [{0} [...]]]".format(vararg[0]))
    if keywordarg:
        usage.append("[{0}=value [{0}=value [...]]]".format(keywordarg[0]))
    usage = ['', ' '.join(usage), '']
    if func.__doc__:
        usage.extend([func.__doc__, ''])
    positional = [''] * (len(params) - len(defaults)) + defaults
    usage.extend(["arguments:", ''])
    for i, name in enumerate(params):
        usage.append('    %-15s %-15s %s' % (annotations[name].metavar or name, positional[i], annotations[name].help))
    for name in  (vararg + keywordarg):
        usage.append('    %-15s %-15s %s' % (name, '', annotations[name].help))
    func.__usage__ = '\n'.join(usage)
    args = []

    kwargs = {}
    pos = 0
    flags = []
    for item in sys.argv[1:]:
        if item.startswith('--'):
            item = item[2:]
            if len(item) < 2:
                raise ScriptionError('double-dash flags must be spelled out')
            flags.append(item)
        elif item.startswith('-'):
            item = item[1:]
            if len(item) != 1:
                raise ScriptionError('dash flags must be a single character')
            flags.append(item)
        elif '=' in item:
            name, value = item.split('=')
            if name in params:
                print "%s: '=' not allowed with positional arguments\n" % sys.argv[0] + func.__usage__ + '\n00'
                sys.exit(-1)
            kwargs[name] = value
        else:
            if pos < len(positional):
                positional[pos] = item
                pos += 1
            else:
                args.append(item)
    if flags and flags[0] in ('h','help'):
        print func.__usage__ + '\n00\n'
        sys.exit(-1)
    for flag in flags:
        if len(flag) == 1:  # find the full name
            for name, annote in annotations.items():
                if annote.abbrev == flag:
                    flag = name
                    break
        if flag not in annotations:
            raise ScriptionError('%s is not a valid flag' % flag)
        index = params.index(flag)
        positional[index] = True
    if not all([p != '' for p in positional]):
        print func.__usage__ + '\n01\n'
        sys.exit(-1)
    if args and not vararg:
        print func.__usage__ + '\n02\n'
        sys.exit(-1)
    for i, value in enumerate(positional):
        #print params[i], ': ', value, '-->',
        annote = annotations[params[i]]
        if annote.kind != 'positional' and value not in (True, False):
            raise ScriptionError("%s is a %s, not a positional" % (params[i], annote.kind))
        positional[i] = annotations[params[i]].type(value)
        #print positional[i]
    for i, value in enumerate(args):
        positional[i] = vararg_type(value)
    for key, value in kwargs.items():
        kwargs[key] = keywordarg_type(value)
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
