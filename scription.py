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
    command = [None]
    def __init__(self, **annotations):
        self.annotations = annotations
    def __call__(self, func):
        _add_annotations(func, self.annotations)
        Script.command[0] = func
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
    func.__annotations__ = self.annotations

def run(func=None):
    "parses command-line and compares with either func or, if None, Script.command"
    if func is None:
        func = Script.command[0]
        if func is None:
            raise TypeError("'run' must be called with a function, or a function must"
                    " have been declared with @Script")
    params, vararg, keywordarg, defaults = inspect.getargspec(func)
    params = list(params)
    vararg = [vararg] if vararg else []
    keywordarg = [keywordarg] if keywordarg else []
    defaults = list(defaults) if defaults else []
    if not params:
        return func()
    annotations = getattr(func, '__annotations__', {})
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
        usage.append('    %-15s %-15s %s' % (name, positional[i], annotations.get(name, '')))
    for name in  (vararg + keywordarg):
        usage.append('    %-15s %-15s %s' % (name, '', annotations.get(name, '')))
    func.__usage__ = '\n'.join(usage)

    if not sys.argv[1:]:
        print func.__usage__ + '\n00'
        return

    args = []
    kwargs = {}
    pos = 0
    for item in sys.argv[1:]:
        if item.startswith('--'):
            raise TypeError("--options not currently supported")
        elif item.startswith('-'):
            raise TypeError("-flags not currently supported")
        elif '=' in item:
            name, value = item.split('=')
            if name in params:
                loc = params.index(name)
                positional[loc] = value
            else:
                kwargs[name] = value
        else:
            if pos < len(positional):
                positional[pos] = item
                pos += 1
            else:
                args.append(item)
    if not all([p != '' for p in positional]):
        print func.__usage__ + '\n01'
        return
    if args and not vararg:
        print func.__usage__ + '\n02'
        return
    #for name in kwargs.keys():
    #    if name not in keywordarg:
    #        print func.__usage__ + '\n03'
    #        return
    args = positional + vararg
    return func(*args, **kwargs)
