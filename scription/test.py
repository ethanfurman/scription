from __future__ import print_function
import os
import sys
sys.path.insert(0, os.path.split(os.path.split(__file__)[0]))

from aenum import version as aenum_version
from antipathy import Path
from scription import *
from scription import _usage, version, empty, pocket, ormclassmethod
from scription import pyver, PY2, PY25, PY33
from textwrap import dedent
from unittest import skip, skipUnless, SkipTest, TestCase as unittest_TestCase, main
import datetime
import errno
import functools
import pty
import re
import scription
import shlex
import shutil
import tempfile
import threading
import time
import warnings
try:
    import hypothesis
    from hypothesis import given as st # strategies as settings
except ImportError:
    hypothesis = None
scription.VERBOSITY = 0

try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO
remove = []
INCLUDE_SLOW = UNITTEST_VERBOSE = False
for i, arg in enumerate(sys.argv):
    if arg.lower().replace('_','-') == '--include-slow':
        remove.append(i)
        INCLUDE_SLOW = True
    elif arg.lower() == '-v':
        UNITTEST_VERBOSE = True
for i in remove[::-1]:
    sys.argv.pop(i)
del remove

is_win = sys.platform.startswith('win')
gubed = False

class UTC(datetime.tzinfo):
    """UTC"""
    def utcoffset(self, dt):
        return datetime.timedelta(0)
    def tzname(self, dt):
        return "UTC"
    def dst(self, dt):
        return datetime.timedelta(0)
UTC = UTC()

print('Scription %s.%s.%s, aenum %s.%s.%s -- Python %d.%d' % (version[:3] + aenum_version[:3] + pyver), verbose=0)

def test_func_parsing(obj, func, tests, test_type=False):
    global gubed, script_name, script_main, script_commands, script_command, script_commandname
    try:
        for i, (params, main_args, main_kwds, sub_args, sub_kwds) in enumerate(tests):
            if UNITTEST_VERBOSE:
                echo(i, end=' ')
            have_gubed = verbose = False
            if '--gubed' in params:
                have_gubed = True
            if '-v' in params or '--verbose' in params or '--verbose=1' in params:
                verbose = 1
            elif '-vv' in params or '--verbose=2' in params:
                verbose = 2
            res_main_args, res_main_kwds, res_sub_args, res_sub_kwds = _usage(func, params)
            obj.assertEqual(
                    res_main_args, main_args,
                    "[main args] expected: %r, got: %r  (iteration %d)" % (main_args, res_main_args, i),
                    )
            obj.assertEqual(
                    res_main_kwds, main_kwds,
                    "[main kwds] expected: %r, got: %r  (iteration %d)" % (main_kwds, res_main_kwds, i),
                    )
            obj.assertEqual(
                    res_sub_args, sub_args,
                    "[sub args] expected: %r, got: %r  (iteration %d)" % (sub_args, res_sub_args, i),
                    )
            obj.assertEqual(
                    res_sub_kwds, sub_kwds,
                    "[sub kwds] expected: %r, got: %r  (iteration %d)" % (sub_kwds, res_sub_kwds, i),
                    )
            if have_gubed:
                obj.assertTrue(script_module['gubed'], "gubed is not True (iteration %d)" % i)
            if verbose:
                obj.assertEqual(scription.VERBOSITY, verbose)
            if test_type:
                for rval, val in zip(res_main_args, main_args):
                    obj.assertTrue(type(rval) is type(val), 'type(%r) is not type(%r) (%s != %s)' % (rval, val, type(rval), type(val)))
                for rkey, rval in res_main_kwds.items():
                    obj.assertTrue(type(rval) is type(main_kwds[rkey]), 'type(%r) is not type(%r) (%s != %s)' % (rval, main_kwds[rkey], type(rval), type(main_kwds[rkey])))
                for rval, val in zip(res_sub_args, sub_args):
                    obj.assertTrue(type(rval) is type(val), 'type(%r) is not type(%r) (%s != %s)' % (rval, val, type(rval), type(val)))
                for rkey, rval in res_sub_kwds.items():
                    obj.assertTrue(type(rval) is type(sub_kwds[rkey]), 'type(%r) is not type(%r) (%s != %s)' % (rval, sub_kwds[rkey], type(rval), type(sub_kwds[rkey])))

            gubed = False
            scription.VERBOSITY = 0
            for spec in set(func.__scription__.values()):
                spec._cli_value = empty
    finally:
        module = scription.script_module
        module['script_name'] = '<unknown>'
        module['script_fullname'] = '<unknown>'
        module['script_main'] = None
        module['script_commands'] = {}
        module['script_command'] = None
        module['script_commandname'] = ''
        module['script_exception_lines'] = ''

def test_func_docstrings(obj, func, docstring):
    try:
        obj.assertEqual(func.__doc__, docstring)
    finally:
        script_main = None
        script_commands = {}
        script_main, script_commands

class TestCase(unittest_TestCase):

    run_so_far = []

    def __init__(self, *args, **kwds):
        regex = getattr(self, 'assertRaisesRegex', None)
        if regex is None:
            self.assertRaisesRegex = getattr(self, 'assertRaisesRegexp')
        super(TestCase, self).__init__(*args, **kwds)

    @classmethod
    def setUpClass(cls, *args, **kwds):
        cls.run_so_far.append(cls.__name__)
        super(TestCase, cls).setUpClass(*args, **kwds)
        # filter warnings
        warnings.filterwarnings(
                'ignore',
                'inspect\.getargspec\(\) is deprecated',
                DeprecationWarning,
                'scription',
                0,
                )
        # double check existence of temp dir
        if not os.path.exists(tempdir):
            echo('\n'.join(cls.run_so_far))
            raise SystemExit('tempdir is missing')

if hypothesis:
    class TestHypothesis(TestCase):

        @hypothesis.given(a=st.integers(), b=st.none(), c=st.booleans(), d=st.floats())
        def test_pocket(self, a, b, c, d):
            for value  in (a, b, c, d, (a, b, c, d), (a, c), [b, d]):
                def this_thing(val=pocket(value=value)):
                    return pocket.value
                test_value = this_thing(value)
                self.assertTrue(value is test_value or value == test_value)

class TestPocket(TestCase):

    def test_single_arg_is_arg(self):
        if not (pocket(value=3)):
            self.assertTrue(False, "pocket() did not return value")
        else:
            self.assertEqual(3, pocket.value)
        if (pocket(value=None)):
            self.assertTrue(False, "pocket() did not return None")
        else:
            self.assertIs(None, pocket.value)

    def test_multi_args(self):
        val = pocket(value1=3, value2=7)
        self.assertIs(type(val), tuple)
        self.assertEqual(len(val), 2)
        self.assertTrue(3 in val)
        self.assertTrue(7 in val)
        self.assertEqual(pocket.value1, 3)
        self.assertEqual(pocket.value2, 7)

class TestVar(TestCase):

    def test_function(self):
        match = Var(re.match)
        if match(r"it.*(worked)!", "it   worked!"):
            self.assertEqual(match().groups(), ('worked', ))
        else:
            self.assertTrue(False, 'match returned %r' % match())

    def test_no_function_single_arg(self):
        var = Var()
        if var(3+8):
            self.assertEqual(var(), 11)
        else:
            self.assertTrue(False, 'var returned %r (should be 11)' % var())

    def test_no_function_multi_arg(self):
        var = Var()
        if var(3+8, 7*7):
            self.assertEqual(var(), (11, 49))
        else:
            self.assertTrue(False, 'var returned %r (should be (11, 49))' % (var(), ))

    def test_data_attributes(self):
        match = Var(re.match)
        if match(r"it.*(worked)!", "it   worked!"):
            self.assertEqual(match.groups(), ('worked', ))
        else:
            self.assertTrue(False, 'match returned %r' % match())


class TestExports(TestCase):

    def test_speckind_exported(self):
        for member in scription.SpecKind:
            self.assertTrue(member.name in globals(), '%s is missing from globals()' % member)
            self.assertIs(globals()[member.name], member)


class TestCommandlineProcessing(TestCase):

    def setUp(self):
        module = scription.script_module
        module['script_name'] = '<unknown>'
        module['script_fullname'] = '<unknown>'
        module['script_main'] = None
        module['script_commands'] = {}
        module['script_command'] = None
        module['script_commandname'] = ''
        module['script_aliases'] = ''
        module['script_exception_lines'] = ''

    def test_envvar(self):
        @Command(
                req=Spec('something goes here', 'required', envvar='SCRIPTION-TEST-REQ'),
                maybe=Spec('and a flag here', 'flag', envvar='SCRIPTION-TEST-MAYBE'),
                centi=Spec('an option here', 'option', envvar='SCRIPTION-TEST-CENTI'),
                pedes=Spec('many options here', 'multi', envvar='SCRIPTION-TEST-PEDES', type=float),
                )
        def tester(req, maybe, centi, pedes):
            pass
        tests = (
                ('tester'.split(), (), {}, ('scription', True, 'python', (2.7, 3.3, 3.6)), {} ),
                )
        try:
            os.environ['SCRIPTION-TEST-REQ'] = 'scription'
            os.environ['SCRIPTION-TEST-MAYBE'] = 'on'
            os.environ['SCRIPTION-TEST-CENTI'] = 'python'
            os.environ['SCRIPTION-TEST-PEDES'] = '2.7,3.3,3.6'
            test_func_parsing(self, tester, tests)
        finally:
            del os.environ['SCRIPTION-TEST-REQ']
            del os.environ['SCRIPTION-TEST-MAYBE']
            del os.environ['SCRIPTION-TEST-CENTI']
            del os.environ['SCRIPTION-TEST-PEDES']

    def test_trivalent_flag(self):
        @Command(
                binary=('copy in binary mode', 'flag', 'b', Trivalent),
                )
        def copy(binary):
            pass
        tests = (
                ('copy'.split(), (), {}, (Unknown, ), {} ),
                ('copy -b'.split(), (), {}, (Truthy, ), {} ),
                ('copy -b'.split(), (), {}, (True, ), {} ),
                ('copy --binary'.split(), (), {}, (Truthy, ), {} ),
                ('copy --binary'.split(), (), {}, (True, ), {} ),
                ('copy --no-binary'.split(), (), {}, (Falsey, ), {} ),
                ('copy --no-binary'.split(), (), {}, (False, ), {} ),
                )
        test_func_parsing(self, copy, tests)

    def test_trivalent_flag_type(self):
        @Command(
                binary=Spec('copy in binary mode', 'flag', force_default=Unknown),
                )
        def copy(binary):
            pass
        tests = (
                ('copy'.split(), (), {}, (Unknown, ), {} ),
                ('copy -b'.split(), (), {}, (Truthy, ), {} ),
                ('copy -b'.split(), (), {}, (True, ), {} ),
                ('copy --binary'.split(), (), {}, (Truthy, ), {} ),
                ('copy --binary'.split(), (), {}, (True, ), {} ),
                ('copy --no-binary'.split(), (), {}, (Falsey, ), {} ),
                ('copy --no-binary'.split(), (), {}, (False, ), {} ),
                )
        test_func_parsing(self, copy, tests)

    def test_multi_with_choices(self):
        @Command(
                huh=Spec('misc options', 'multi', choices=['mine', 'yours', 'theirs']),
                )
        def tester(huh):
            pass
        tests = (
                ( 'tester'.split(), (), {}, (tuple(), ), {} ),
                ( 'tester -h theirs'.split(), (), {}, (('theirs', ), ), {} ),
                ( 'tester -h mine -h yours'.split(), (), {}, (('mine', 'yours'), ), {} ),
                )
        test_func_parsing(self, tester, tests)

    def test_multi_with_choices_as_string(self):
        @Command(
                huh=Spec('misc options', 'multi', choices='mine yours theirs'),
                )
        def tester(huh):
            pass
        tests = (
                ( 'tester'.split(), (), {}, (tuple(), ), {} ),
                ( 'tester -h theirs'.split(), (), {}, (('theirs', ), ), {} ),
                ( 'tester -h mine -h yours'.split(), (), {}, (('mine', 'yours'), ), {} ),
                )
        test_func_parsing(self, tester, tests)

    def test_multi_with_bad_choices(self):
        @Command(
                huh=Spec('misc options', 'multi', choices=['mine', 'yours', 'theirs']),
                )
        def tester(huh):
            pass
        self.assertRaisesRegex(
                ScriptionError,
                r"HUH: 'ours' not in \[ mine | yours | theirs \]",
                _usage,
                tester,
                "tester --huh ours".split(),
                )

    def test_multi_with_bad_choices_as_string(self):
        @Command(
                huh=Spec('misc options', 'multi', choices='mine yours theirs'),
                )
        def tester(huh):
            pass
        self.assertRaisesRegex(
                ScriptionError,
                r"HUH: 'ours' not in \[ mine | yours | theirs \]",
                _usage,
                tester,
                "tester --huh ours".split(),
                )

    def test_multi(self):
        @Command(
                huh=('misc options', 'multi'),
                )
        def tester(huh):
            pass
        tests = (
                ( 'tester'.split(), (), {}, (tuple(), ), {} ),
                ( 'tester -h file1'.split(), (), {}, (('file1', ), ), {} ),
                ( 'tester -h file1 -h file2'.split(), (), {}, (('file1', 'file2'), ), {} ),
                )
        test_func_parsing(self, tester, tests)

    def test_multi_with_private(self):
        @Command(
                huh=('misc options', 'multi'),
                )
        def tester(huh, _mine=''):
            pass
        tests = (
                ( 'tester -h file1'.split(), (), {}, (('file1', ), ), {} ),
                ( 'tester -h file1 -h file2'.split(), (), {}, (('file1', 'file2'), ), {} ),
                )
        test_func_parsing(self, tester, tests)

    def test_multi_with_comma(self):
        @Command(
                huh=('misc options', 'multi'),
                )
        def tester(huh):
            pass
        tests = (
                ( 'tester --huh=one,two,three'.split(), (), {}, (('one', 'two', 'three'), ), {} ),
                ( 'tester --huh one,two,three'.split(), (), {}, (('one', 'two', 'three'), ), {} ),
                ( 'tester -h one,two -h three,four'.split(), (), {}, (('one', 'two', 'three', 'four'), ), {} ),
                )
        test_func_parsing(self, tester, tests)

    def test_multi_with_comma_and_quotes(self):
        @Command(
                huh=('misc options', 'multi'),
                )
        def tester(huh):
            pass
        tests = (
                ( shlex.split('tester --huh="one,two,three four"'), (), {}, (('one', 'two', 'three four'), ), {}),
                ( shlex.split('tester --huh "one,two nine,three"'), (), {}, (('one', 'two nine', 'three'), ), {}),
                ( shlex.split('tester -h one,two -h "three,four teen"'), (), {}, (('one', 'two', 'three', 'four teen'), ), {}),
                )
        test_func_parsing(self, tester, tests)

    def test_multi_with_comma_and_quotes_and_private(self):
        @Command(
                huh=('misc options', 'multi'),
                )
        def tester(huh, _still_private=None):
            pass
        tests = (
                ( shlex.split('tester --huh="one,two,three four"'), (), {}, (('one', 'two', 'three four'), ), {}),
                ( shlex.split('tester --huh "one,two nine,three"'), (), {}, (('one', 'two nine', 'three'), ), {}),
                ( shlex.split('tester -h one,two -h "three,four teen"'), (), {}, (('one', 'two', 'three', 'four teen'), ), {}),
                )
        test_func_parsing(self, tester, tests)

    def test_multi_with_option(self):
        @Command(
                huh=('misc options', 'multi'),
                wow=('oh yeah', 'option'),
                )
        def tester(huh, wow):
            pass
        tests = (
                ( 'tester -h file1'.split(), (), {}, (('file1', ), None), {} ),
                ( 'tester -h file1 -w google'.split(), (), {}, (('file1', ), 'google'), {} ),
                ( 'tester -h file1 -h file2'.split(), (), {}, (('file1', 'file2'), None), {} ),
                ( 'tester -h file1 -h file2 -w frizzle'.split(), (), {}, (('file1', 'file2'), 'frizzle'), {} ),
                )
        test_func_parsing(self, tester, tests)

    def test_multi_with_Spec_default_str(self):
        @Command(
                huh=Spec('misc options', 'multi', default='woo', force_default=True),
                )
        def tester(huh):
            pass
        tests = (
                ( 'tester'.split(), (), {}, (('woo', ), ), {} ),
                ( 'tester --huh=file1'.split(), (), {}, (('file1', ), ), {} ),
                ( 'tester -h file1 -h file2'.split(), (), {}, (('file1', 'file2'), ), {} ),
                )
        test_func_parsing(self, tester, tests)

    def test_multi_with_Spec_default_tuple(self):
        @Command(
                huh=Spec('misc options', 'multi', default=('woo', ), force_default=True),
                )
        def tester(huh):
            pass
        tests = (
                ( 'tester'.split(), (), {}, (('woo', ), ), {} ),
                ( 'tester --huh=file1'.split(), (), {}, (('file1', ), ), {} ),
                ( 'tester -h file1 -h file2'.split(), (), {}, (('file1', 'file2'), ), {} ),
                )
        test_func_parsing(self, tester, tests)

    def test_multi_with_Spec_default_int(self):
        @Command(
                huh=Spec('misc options', 'multi', default=7, force_default=True),
                )
        def tester(huh):
            pass
        tests = (
                ( 'tester'.split(), (), {}, ((7, ), ), {} ),
                ( 'tester --huh=1'.split(), (), {}, ((1, ), ), {} ),
                ( 'tester -h 11 -h 13'.split(), (), {}, ((11, 13), ), {} ),
                )
        test_func_parsing(self, tester, tests)

    def test_multi_with_Spec_default_int_in_tuple(self):
        @Command(
                huh=Spec('misc options', 'multi', default=(7, ), force_default=True),
                )
        def tester(huh):
            pass
        tests = (
                ( 'tester'.split(), (), {}, ((7, ), ), {} ),
                ( 'tester --huh=1'.split(), (), {}, ((1, ), ), {} ),
                ( 'tester -h 11 -h 13'.split(), (), {}, ((11, 13), ), {} ),
                )
        test_func_parsing(self, tester, tests)

    def test_required_with_equal(self):
        @Command(
                huh=('required option that should accept =', 'required'),
                )
        def tester(huh):
            pass
        tests = (
                ( 'tester file1=that'.split(), (), {}, ('file1=that', ), {} ),
                ( shlex.split('tester file2="woohoo"'), (), {}, ('file2=woohoo', ), {} ),
                )
        test_func_parsing(self, tester, tests)

    def test_multireq(self):
        @Command(
                huh=('required option that accepts several values', 'multireq'),
                )
        def tester(huh):
            pass
        tests = (
                ( 'tester'.split(), (), {}, (tuple(), ), {} ),
                ( 'tester file1'.split(), (), {}, ( ('file1',) , ), {} ),
                ( 'tester file1,file2'.split(), (), {}, (('file1', 'file2'), ), {} ),
                )
        test_func_parsing(self, tester, tests)

    def test_multireq_with_private(self):
        @Command(
                huh=('misc options', 'multireq'),
                )
        def tester(huh, _mine=''):
            pass
        tests = (
                ( 'tester file1'.split(), (), {}, (('file1', ), ), {} ),
                ( 'tester file1,file2'.split(), (), {}, (('file1', 'file2'), ), {} ),
                )
        test_func_parsing(self, tester, tests)

    def test_multireq_with_comma_and_quotes(self):
        @Command(
                huh=('misc options', 'multireq'),
                )
        def tester(huh):
            pass
        tests = (
                ( shlex.split('tester "one,two,three four"'), (), {}, (('one', 'two', 'three four'), ), {}),
                ( shlex.split('tester "one,two nine,three"'), (), {}, (('one', 'two nine', 'three'), ), {}),
                )
        test_func_parsing(self, tester, tests)

    def test_multireq_with_comma_and_quotes_and_private(self):
        @Command(
                huh=('misc options', 'multireq'),
                )
        def tester(huh, _still_private=None):
            pass
        tests = (
                ( shlex.split('tester "one,two,three four"'), (), {}, (('one', 'two', 'three four'), ), {}),
                ( shlex.split('tester "one,two nine,three"'), (), {}, (('one', 'two nine', 'three'), ), {}),
                )
        test_func_parsing(self, tester, tests)

    def test_multireq_with_option(self):
        @Command(
                huh=('misc options', 'multireq'),
                wow=('oh yeah', 'option'),
                )
        def tester(huh, wow):
            pass
        tests = (
                ( 'tester file1'.split(), (), {}, (('file1', ), None), {} ),
                ( 'tester file1 -w google'.split(), (), {}, (('file1', ), 'google'), {} ),
                ( 'tester file1,file2'.split(), (), {}, (('file1', 'file2'), None), {} ),
                ( 'tester file1,file2 -w frizzle'.split(), (), {}, (('file1', 'file2'), 'frizzle'), {} ),
                )
        test_func_parsing(self, tester, tests)

    def test_multireq_with_Spec_default_str(self):
        @Command(
                huh=Spec('misc options', 'multireq', default='woo', force_default=True),
                )
        def tester(huh):
            pass
        tests = (
                ( 'tester'.split(), (), {}, (('woo', ), ), {} ),
                ( 'tester file1'.split(), (), {}, (('file1', ), ), {} ),
                ( 'tester file1,file2'.split(), (), {}, (('file1', 'file2'), ), {} ),
                )
        test_func_parsing(self, tester, tests)

    def test_multireq_with_Spec_default_tuple(self):
        @Command(
                huh=Spec('misc options', 'multireq', default=('woo', ), force_default=True),
                )
        def tester(huh):
            pass
        tests = (
                ( 'tester'.split(), (), {}, (('woo', ), ), {} ),
                ( 'tester file1'.split(), (), {}, (('file1', ), ), {} ),
                ( 'tester file1,file2'.split(), (), {}, (('file1', 'file2'), ), {} ),
                )
        test_func_parsing(self, tester, tests)

    def test_multireq_with_Spec_default_int(self):
        @Command(
                huh=Spec('misc options', 'multireq', default=7, force_default=True),
                )
        def tester(huh):
            pass
        tests = (
                ( 'tester'.split(), (), {}, ((7, ), ), {} ),
                ( 'tester 1'.split(), (), {}, ((1, ), ), {} ),
                ( 'tester 11,13'.split(), (), {}, ((11, 13), ), {} ),
                )
        test_func_parsing(self, tester, tests)

    def test_multireq_with_Spec_default_int_in_tuple(self):
        @Command(
                huh=Spec('misc options', 'multireq', default=(7, ), force_default=True),
                )
        def tester(huh):
            pass
        tests = (
                ( 'tester'.split(), (), {}, ((7, ), ), {} ),
                ( 'tester 1'.split(), (), {}, ((1, ), ), {} ),
                ( 'tester 11,13'.split(), (), {}, ((11, 13), ), {} ),
                )
        test_func_parsing(self, tester, tests)

    def test_multireq_with_choices(self):
        @Command(
                huh=Spec('misc options', 'multireq', choices=['7','8','9'], type=int),
                )
        def tester(huh):
            pass
        tests = (
                ( 'tester 8,9'.split(), (), {}, ((8, 9), ), {} ),
                ( 'tester 7'.split(), (), {}, ((7, ), ), {} ),
                ( 'tester 8'.split(), (), {}, ((8, ), ), {} ),
                )
        test_func_parsing(self, tester, tests)

    def test_multireq_with_bad_choices(self):
        @Command(
            word=Spec('a silly argument', MULTIREQ, choices=['this', 'that']),
            )
        def test_choices(word):
            pass
        self.assertRaisesRegex(
                ScriptionError,
                r"WORD: 'gark' not in \[ this \| that \]",
                _usage,
                test_choices,
                'test_choices gark'.split(),
                )


    def test_option_with_default_in_command(self):
        @Command(
                huh=('misc options', 'option'),
                wow=Spec('oh yeah', 'option', default='spam!'),
                )
        def tester(huh, wow):
            pass
        tests = (
                ( 'tester'.split(), (), {}, (None, None), {} ),
                ( 'tester -w'.split(), (), {}, (None, 'spam!'), {} ),
                ( 'tester -w google'.split(), (), {}, (None, 'google'), {} ),
                ( 'tester -h file1'.split(), (), {}, ('file1', None), {} ),
                ( 'tester -h file1 -w'.split(), (), {}, ('file1', 'spam!'), {} ),
                ( 'tester -h file1 -w google'.split(), (), {}, ('file1', 'google'), {} ),
                ( 'tester -h file2 -w frizzle'.split(), (), {}, ('file2', 'frizzle'), {} ),
                )
        test_func_parsing(self, tester, tests)

    def test_option_with_default_in_header(self):
        @Command(
                huh=('misc options', 'option'),
                wow=Spec('oh yeah', 'option'),
                )
        def tester(huh, wow='eggs!'):
            pass
        tests = (
                ( 'tester'.split(), (), {}, (None, 'eggs!'), {} ),
                ( 'tester -w'.split(), (), {}, (None, 'eggs!'), {} ),
                ( 'tester -w google'.split(), (), {}, (None, 'google'), {} ),
                ( 'tester -h file1'.split(), (), {}, ('file1', 'eggs!'), {} ),
                ( 'tester -h file1 -w'.split(), (), {}, ('file1', 'eggs!'), {} ),
                ( 'tester -h file1 -w google'.split(), (), {}, ('file1', 'google'), {} ),
                ( 'tester -h file2 -w frizzle'.split(), (), {}, ('file2', 'frizzle'), {} ),
                )
        test_func_parsing(self, tester, tests)

    def test_flags(self):
        @Command(
                cardboard=('use cardboard', 'flag'),
                plastic=('use plastic', 'flag'),
                )
        def tester(cardboard, plastic=True):
            pass
        tests = (
                ( 'tester'.split(), (), {}, (False, True), {} ),
                ( 'tester -c'.split(), (), {}, (True, True), {} ),
                ( 'tester -p'.split(), (), {}, (False, True), {} ),
                ( 'tester -c -p'.split(), (), {}, (True, True), {} ),
                ( 'tester --cardboard --plastic'.split(), (), {}, (True, True), {} ),
                ( 'tester --cardboard=yes --plastic'.split(), (), {}, (True, True), {} ),
                ( 'tester --no-plastic'.split(), (), {}, (False, False), {} ),
                ( 'tester --plastic=off'.split(), (), {}, (False, False), {} ),
                )
        test_func_parsing(self, tester, tests)

    def test_positional_only(self):
        @Command(
                file1=('source file', ),
                file2=('dest file', ),
                )
        def copy(file1, file2):
            pass
        tests = (
                ('copy file1 file2'.split(), (), {}, ('file1', 'file2'), {} ),
                )
        test_func_parsing(self, copy, tests)

    def test_positional_with_flag(self):
        @Command(
                file1=('source file', ),
                file2=('dest file', ),
                binary=('copy in binary mode', 'flag',),
                )
        def copy(file1, file2, binary):
            pass
        tests = (
                ('copy file1 file2'.split(), (), {}, ('file1', 'file2', False), {} ),
                ('copy file1 file2 -b'.split(), (), {}, ('file1', 'file2', True), {} ),
                )
        test_func_parsing(self, copy, tests)

    def test_positional_with_var(self):
        @Command(
                file1=('source file', ),
                file2=('dest file', ),
                comment=('misc comment for testing', 'option',),
                )
        def copy(file1, file2, comment):
            pass
        tests = (
                ('copy file1 file2'.split(), (), {}, ('file1', 'file2', None), {} ),
                ('copy file1 file2 --comment=howdy!'.split(), (), {}, ('file1', 'file2',  'howdy!'), {} ),
                ('copy file1 file2 --comment howdy!'.split(), (), {}, ('file1', 'file2',  'howdy!'), {} ),
                (shlex.split('copy file1 file2 --comment="howdy doody!"'), (), {}, ('file1', 'file2', 'howdy doody!'), {} ),
                (shlex.split('copy file1 file2 --comment "howdy doody!"'), (), {}, ('file1', 'file2', 'howdy doody!'), {} ),
                )
        test_func_parsing(self, copy, tests)

    def test_positional_with_flag_and_var(self):
        @Command(
                file1=('source file', ),
                file2=('dest file', ),
                binary=('copy in binary mode', 'flag',),
                comment=('misc comment for testing', 'option',),
                )
        def copy(file1, file2, binary=True, comment=''):
            pass
        tests = (
                ('copy file1 file2'.split(), (), {}, ('file1', 'file2', True, ''), {} ),
                ('copy file1 file2 --no-binary'.split(), (), {}, ('file1', 'file2', False, ''), {} ),
                ('copy file1 file2 --comment howdy!'.split(), (), {}, ('file1', 'file2', True, 'howdy!'), {} ),
                ('copy file1 file2 --comment=howdy!'.split(), (), {}, ('file1', 'file2', True, 'howdy!'), {} ),
                ('copy file1 file2 --no-binary --comment=howdy!'.split(), (), {}, ('file1', 'file2', False, 'howdy!'), {} ),
                ('copy file1 file2 --comment howdy!'.split(), (), {}, ('file1', 'file2', True, 'howdy!'), {} ),
                ('copy file1 file2 --no-binary --comment howdy!'.split(), (), {}, ('file1', 'file2', False, 'howdy!'), {} ),
                (shlex.split('copy file1 file2 --comment "howdy doody!"'), (), {}, ('file1', 'file2', True, 'howdy doody!'), {} ),
                (shlex.split('copy file1 file2 --comment="howdy doody!"'), (), {}, ('file1', 'file2', True, 'howdy doody!'), {} ),
                (shlex.split('copy file1 file2 --no-binary --comment="howdy doody!"'), (), {}, ('file1', 'file2', False, 'howdy doody!'), {} ),
                (shlex.split('copy file1 file2 --comment "howdy doody!"'), (), {}, ('file1', 'file2', True, 'howdy doody!'), {} ),
                (shlex.split('copy file1 file2 --no-binary --comment "howdy doody!"'), (), {}, ('file1', 'file2', False, 'howdy doody!'), {} ),
                )
        test_func_parsing(self, copy, tests)

    def test_positional_with_flag_and_var_and_private(self):
        @Command(
                file1=('source file', ),
                file2=('dest file', ),
                binary=('copy in binary mode', 'flag',),
                comment=('misc comment for testing', 'option',),
                )
        def copy(file1, file2, binary=True, comment='', _cache=[]):
            pass
        tests = (
                ('copy file1 file2'.split(), (), {}, ('file1', 'file2', True, ''), {} ),
                ('copy file1 file2 --no-binary'.split(), (), {}, ('file1', 'file2', False, ''), {} ),
                ('copy file1 file2 --comment howdy!'.split(), (), {}, ('file1', 'file2', True, 'howdy!'), {} ),
                ('copy file1 file2 --comment=howdy!'.split(), (), {}, ('file1', 'file2', True, 'howdy!'), {} ),
                ('copy file1 file2 --no-binary --comment=howdy!'.split(), (), {}, ('file1', 'file2', False, 'howdy!'), {} ),
                ('copy file1 file2 --comment howdy!'.split(), (), {}, ('file1', 'file2', True, 'howdy!'), {} ),
                ('copy file1 file2 --no-binary --comment howdy!'.split(), (), {}, ('file1', 'file2', False, 'howdy!'), {} ),
                (shlex.split('copy file1 file2 --comment "howdy doody!"'), (), {}, ('file1', 'file2', True, 'howdy doody!'), {} ),
                (shlex.split('copy file1 file2 --comment="howdy doody!"'), (), {}, ('file1', 'file2', True, 'howdy doody!'), {} ),
                (shlex.split('copy file1 file2 --no-binary --comment="howdy doody!"'), (), {}, ('file1', 'file2', False, 'howdy doody!'), {} ),
                (shlex.split('copy file1 file2 --comment "howdy doody!"'), (), {}, ('file1', 'file2', True, 'howdy doody!'), {} ),
                (shlex.split('copy file1 file2 --no-binary --comment "howdy doody!"'), (), {}, ('file1', 'file2', False, 'howdy doody!'), {} ),
                )
        test_func_parsing(self, copy, tests)

    def test_type(self):
        class Path(str):
            pass
        @Command(
                one=Spec('integer', REQUIRED, type=int),
                two=Spec('string', OPTION, type=str),
                three=Spec('path', MULTI, None, type=Path),
                )
        def tester(one='1', two=2, three='/some/path/to/nowhere'):
            pass
        tests = (
                (['tester'], (), {}, (1, str('2'), (Path('/some/path/to/nowhere'), )), {} ),
                (str('tester 3 -t 4 --three /somewhere/over/the/rainbow').split(), (), {}, (3, str('4'), (Path('/somewhere/over/the/rainbow'), )), {} ),
                (str('tester 5 -t 6 --three=/yellow/brick/road.txt').split(), (), {}, (5, str('6'), (Path('/yellow/brick/road.txt'), )), {} ),
                )
        test_func_parsing(self, tester, tests, test_type=True)

    def test_main_with_feeling(self):
        @Script(
                gubed=False,
                password=('super secret hash code', 'option', None),
                )
        def main(password):
            pass
        @Command(
                database=('Oe database', 'required',),
                )
        def query(database):
            pass
        tests = (
                ('query blahblah'.split(), (None, ), {}, ('blahblah', ), {}),
                ('query booboo --password banana'.split(), ('banana', ), {}, ('booboo', ), {}),
                ('query beebee --password banana --gubed'.split(), ('banana', ), {}, ('beebee', ), {}),
                )
        test_func_parsing(self, query, tests)

    def test_varargs(self):
        @Command(
                files=('files to destroy', 'required', None),
                )
        def rm(*files):
            pass
        tests = (
                ('rm this.txt'.split(), (), {}, ('this.txt', ), {} ),
                ('rm those.txt that.doc'.split(), (), {}, ('those.txt', 'that.doc'), {} ),
                )
        test_func_parsing(self, rm, tests)

    def test_varargs_with_regular_args(self):
        @Command(
                these=('some of these please', ),
                those=('maybe those', 'flag', ),
                them=('most important!', 'required'),
                )
        def sassy(these, those, *them):
            pass
        tests = (
                ('sassy biscuit and gravy'.split(), (), {}, ('biscuit', False, 'and' ,'gravy'), {}),
                ('sassy --those biscuit and gravy'.split(), (), {}, ('biscuit', True, 'and' ,'gravy'), {}),
                ('sassy biscuit --those and gravy'.split(), (), {}, ('biscuit', True, 'and' ,'gravy'), {}),
                )
        test_func_parsing(self, sassy, tests)

    def test_varargs_with_regular_args_and_private(self):
        @Command(
                these=('some of these please', ),
                those=('maybe those', 'flag', ),
                them=('most important!', 'required'),
                )
        def sassy(these, those, _un_cache={}, *them):
            pass
        tests = (
                ('sassy biscuit and gravy'.split(), (), {}, ('biscuit', False, 'and' ,'gravy'), {}),
                ('sassy --those biscuit and gravy'.split(), (), {}, ('biscuit', True, 'and' ,'gravy'), {}),
                ('sassy biscuit --those and gravy'.split(), (), {}, ('biscuit', True, 'and' ,'gravy'), {}),
                )
        test_func_parsing(self, sassy, tests)

    def test_varargs_do_not_autoconsume_after_first(self):
        @Command(
                job=('job, job args, etc',),
                )
        def do_job(*job):
            pass
        self.assertRaisesRegex(
                ScriptionError,
                '-r not valid',
                _usage,
                do_job,
                'do_job hg diff -r 199'.split(),
                )
        self.assertRaisesRegex(
                ScriptionError,
                '-c not valid',
                _usage,
                do_job,
                'do_job hg diff -c 201'.split(),
                )
        self.assertRaisesRegex(
                ScriptionError,
                '-m not valid',
                _usage,
                do_job,
                shlex.split('do_job hg commit -m "a message"'),
                )

    def test_varargs_after_forced_default_arg(self):
        @Command(
                source=Spec('source file', OPTION, force_default='the cloud'),
                stuff=Spec('bunches', ),
                )
        def do_job(source, *stuff):
            pass
        tests = (
                ('do_job --source -vv biscuit and gravy'.split(), (), {}, ('the cloud', 'biscuit', 'and' ,'gravy'), {}),
                ('do_job biscuit and gravy'.split(), (), {}, ('the cloud', 'biscuit', 'and' ,'gravy'), {}),
                )
        test_func_parsing(self, do_job, tests)

    def test_kwds(self):
        @Command(
                hirelings=('who to boss around', ),
                )
        def bossy(**hirelings):
            pass
        tests = (
                (str('bossy larry=stupid curly=lazy moe=dumb').split(), (), {}, (), {'larry':'stupid', 'curly':'lazy', 'moe':'dumb'}),
                )
        test_func_parsing(self, bossy, tests)

    def test_short(self):
        @Command(
                here=('first test', FLAG),
                there=('second test', FLAG),
                everywhere=('third test', FLAG),
                )
        def blargh(here, there, everywhere):
            pass
        tests = (
                ('blargh -hte'.split(), (), {}, (True, True, True), {}),
                ('blargh -he'.split(), (), {}, (True, False, True), {}),
                ('blargh -ht --no-everywhere'.split(), (), {}, (True, True, False), {}),
                )
        test_func_parsing(self, blargh, tests)

    def test_verbosity(self):
        @Command(
                )
        def debugger():
            pass
        tests = (
                ('debugger'.split(), (), {}, (), {}),
                ('debugger -v'.split(), (), {}, (), {}),
                ('debugger -vv'.split(), (), {}, (), {}),
                ('debugger --verbose'.split(), (), {}, (), {}),
                ('debugger --verbose=2'.split(), (), {}, (), {}),
                )
        test_func_parsing(self, debugger, tests)

    def test_param_type_from_header(self):
        @Command(
                value1=('some value', ),
                value2=('another value', OPTION, None),
                value3=('and yet more values', MULTI, None),
                value4=('possible None option', OPTION, None),
                value5=('possible None multi', MULTI, None),
                value6=('possible tuple multi', MULTI, None),
                )
        def type_tester(value1=7, value2=3.1415, value3=3.0j, value4=None, value5=None, value6=()):
            pass
        tests = (
                ('type_tester 9 --value2 31.25 --value3 14'.split(), (), {}, (9, 31.25, (14+0j, ), None, None, ()), {}),
                ('type_tester 9 --value2 31.25 --value3=14'.split(), (), {}, (9, 31.25, (14+0j, ), None, None, ()), {}),
                ('type_tester 9 --value2 31.25 --value3=14,15+3j'.split(), (), {}, (9, 31.25, (14+0j, 15+3j), None, None, ()), {}),
                ('type_tester 9 --value2 31.25 --value5=this,that'.split(), (), {}, (9, 31.25, (3.0j, ), None, ('this', 'that'), ()), {}),
                (shlex.split('type_tester 9 --value2 31.25 --value4="woo hoo"'), (), {}, (9, 31.25, (3.0j, ), 'woo hoo', None, ()), {}),
                ('type_tester 9 --value2 31.25 --value6 71'.split(), (), {}, (9, 31.25, (3.0j, ), None, None, ('71', )), {}),
                )
        test_func_parsing(self, type_tester, tests)

    def test_abbreviations(self):
        @Command(
                value1=('some value', ),
                value2=('another value', OPTION, 'b'),
                value3=('and yet more values', MULTI, ('c', 'cee')),
                value4=('possible None option', OPTION, ('d', 'Z')),
                value5=('possible None multi', MULTI, 'value8'),
                value6=('possible tuple multi', MULTI, ('source', 'q')),
                value7=('i do not remember', OPTION, 'z'),
                )
        def type_tester(value1=7, value2=3.1415, value3=3.0j, value4=None, value5=None, value6=(), value7=None):
            pass
        tests = (
                ('type_tester 9 -b 31.25 -c 14'.split(), (), {}, (9, 31.25, (14+0j, ), None, None, (), None), {}),
                ('type_tester 9 -b 31.25 --cee=14'.split(), (), {}, (9, 31.25, (14+0j, ), None, None, (), None), {}),
                ('type_tester 9 --value2 31.25 --value3=14,15+3j'.split(), (), {}, (9, 31.25, (14+0j, 15+3j), None, None, (), None), {}),
                ('type_tester 9 -b 31.25 --value8=this,that'.split(), (), {}, (9, 31.25, (3.0j, ), None, ('this', 'that'), (), None), {}),
                (shlex.split('type_tester 9 --value2 31.25 -Z "woo hoo"'), (), {}, (9, 31.25, (3.0j, ), 'woo hoo', None, (), None), {}),
                ('type_tester 9 --value2 31.25 -z 71'.split(), (), {}, (9, 31.25, (3.0j, ), None, None, (), '71' ), {}),
                )
        test_func_parsing(self, type_tester, tests)

    def test_abbreviations_script_command_conflict(self):
        with self.assertRaisesRegex(ScriptionError, "abbreviation 'h' is duplicate of 'hello' in Script command 'main'"):
            @Script(
                    hello=Spec('hello', OPTION),
                    )
            def main(hello):
                pass
            @Command(
                    high=Spec('higher', OPTION),
                    )
            def sub(high):
                pass

    def test_command_before_script_fails(self):
        with self.assertRaisesRegex(ScriptionError, "Script must be defined before any Command"):
            @Command(
                    high=Spec('higher', OPTION),
                    )
            def sub(high):
                pass
            @Script(
                    hello=Spec('hello', OPTION),
                    )
            def main(hello):
                pass

    def test_no_multi(self):
        @Command(
                some=Spec('an option with a forced default', MULTI, force_default=('hi mom!', 'hi dad!')),
                )
        def some_default(some):
            pass
        tests = (
                ('some_default'.split(), (), {}, (('hi mom!', 'hi dad!'),), {}),
                ('some_default -s'.split(), (), {}, (('hi mom!', 'hi dad!'),), {}),
                ('some_default -s none'.split(), (), {}, (('none',),), {}),
                ('some_default --some thing'.split(), (), {}, (('thing',),), {}),
                ('some_default --no-some'.split(), (), {}, (tuple(), ), {}),
                )
        test_func_parsing(self, some_default, tests)

    def test_no_multi_with_header_default(self):
        @Command(
                some=Spec('an option with a header default', MULTI),
                )
        def some_default(some=('hi mom!', 'hi dad!')):
            pass
        tests = (
                ('some_default'.split(), (), {}, (('hi mom!', 'hi dad!'),), {}),
                ('some_default -s'.split(), (), {}, (('hi mom!', 'hi dad!'),), {}),
                ('some_default -s none'.split(), (), {}, (('none',),), {}),
                ('some_default --some thing'.split(), (), {}, (('thing',),), {}),
                ('some_default --no-some'.split(), (), {}, (tuple(),), {}),
                )
        test_func_parsing(self, some_default, tests)

    def test_no_option_option_default(self):
        @Command(
                some=Spec('an option with a forced default', OPTION, default='howdy'),
                thing=Spec('an option without a default', OPTION),
                )
        def some_default(some, thing):
            pass
        tests = (
                ('some_default'.split(), (), {}, (None, None), {}),
                ('some_default -s'.split(), (), {}, ('howdy', None), {}),
                ('some_default -s none'.split(), (), {}, ('none', None), {}),
                ('some_default --some --thing else'.split(), (), {}, ('howdy', 'else'), {}),
                )
        test_func_parsing(self, some_default, tests)

    def test_no_option(self):
        @Command(
                some=Spec('an option with a forced default', OPTION, force_default='hi mom!'),
                )
        def some_default(some):
            pass
        tests = (
                ('some_default'.split(), (), {}, ('hi mom!',), {}),
                ('some_default -s'.split(), (), {}, ('hi mom!',), {}),
                ('some_default -s none'.split(), (), {}, ('none',), {}),
                ('some_default --some thing'.split(), (), {}, ('thing',), {}),
                ('some_default --no-some'.split(), (), {}, (None,), {}),
                )
        test_func_parsing(self, some_default, tests)

    def test_no_option_with_header_default(self):
        @Command(
                some=Spec('an option with a forced default', OPTION),
                )
        def some_default(some='hi dad!'):
            pass
        tests = (
                ('some_default'.split(), (), {}, ('hi dad!',), {}),
                ('some_default -s'.split(), (), {}, ('hi dad!',), {}),
                ('some_default -s none'.split(), (), {}, ('none',), {}),
                ('some_default --some thing'.split(), (), {}, ('thing',), {}),
                ('some_default --no-some'.split(), (), {}, (None,), {}),
                )
        test_func_parsing(self, some_default, tests)

    def test_no_option_with_choices(self):
        @Command(
                some=Spec('an option with a forced default', OPTION, force_default='mom', choices=['mom', 'none', 'thing']),
                )
        def some_default(some):
            pass
        tests = (
                ('some_default'.split(), (), {}, ('mom',), {}),
                ('some_default -s'.split(), (), {}, ('mom',), {}),
                ('some_default -s none'.split(), (), {}, ('none',), {}),
                ('some_default --some thing'.split(), (), {}, ('thing',), {}),
                ('some_default --no-some'.split(), (), {}, (None,), {}),
                )
        test_func_parsing(self, some_default, tests)

    def test_param_type_from_spec(self):
        @Command(
                value1=Spec('some value', default=7, force_default=True),
                value2=Spec('another value', OPTION, None, default=3.1415, force_default=True),
                value3=Spec('and yet more values', MULTI, None, default=3.0j, force_default=True),
                value4=Spec('possible None option', OPTION, None, default=None, force_default=True),
                value5=Spec('possible None multi', MULTI, None, default=None, force_default=True),
                value6=Spec('possible tuple multi', MULTI, None, default=(), force_default=True),
                )
        def type_tester(value1, value2, value3, value4, value5, value6):
            pass
        tests = (
                ('type_tester 9 --value2 31.25 --value3 14'.split(), (), {}, (9, 31.25, (14+0j, ), None, None, ()), {}),
                ('type_tester 9 --value2 31.25 --value3=14'.split(), (), {}, (9, 31.25, (14+0j, ), None, None, ()), {}),
                ('type_tester 9 --value2 31.25 --value3=14,15+3j'.split(), (), {}, (9, 31.25, (14+0j, 15+3j), None, None, ()), {}),
                ('type_tester 9 --value2 31.25 --value5=this,that'.split(), (), {}, (9, 31.25, (3.0j, ), None, ('this', 'that'), ()), {}),
                (shlex.split('type_tester 9 --value2 31.25 --value4="woo hoo"'), (), {}, (9, 31.25, (3.0j, ), 'woo hoo', None, ()), {}),
                ('type_tester 9 --value2 31.25 --value6 71'.split(), (), {}, (9, 31.25, (3.0j, ), None, None, ('71', )), {}),
                )
        test_func_parsing(self, type_tester, tests)

    def test_option_with_int_choices(self):
        @Command(
                huh=Spec('misc options', 'option', choices=[1, 2, 3], type=int),
                )
        def tester(huh):
            pass
        tests = (
                ( 'tester'.split(), (), {}, (None, ), {} ),
                ( 'tester -h 1'.split(), (), {}, (1, ), {} ),
                ( 'tester -h 3'.split(), (), {}, (3, ), {} ),
                )
        test_func_parsing(self, tester, tests)

    def test_option_with_range_choices(self):
        @Command(
                huh=Spec('misc options', 'option', choices=range(4), type=int),
                )
        def tester(huh):
            pass
        tests = (
                ( 'tester'.split(), (), {}, (None, ), {} ),
                ( 'tester -h 1'.split(), (), {}, (1, ), {} ),
                ( 'tester -h 3'.split(), (), {}, (3, ), {} ),
                )
        test_func_parsing(self, tester, tests)

    def test_option_with_bad_choices(self):
        @Command(
            parent=Spec('an option with choices', OPTION, choices=['mom', 'none', 'thing']),
            )
        def test_choices(parent):
            pass
        self.assertRaisesRegex(
                ScriptionError,
                "PARENT: 'dad' not in \[ mom \| none \| thing \]",
                _usage,
                test_choices,
                # with = sign
                'test_choices --parent=dad'.split(),
                )
        self.assertRaisesRegex(
                ScriptionError,
                "PARENT: 'dad' not in \[ mom \| none \| thing \]",
                _usage,
                test_choices,
                # without = sign
                'test_choices --parent dad'.split(),
                )

    def test_required_with_bad_choices(self):
        @Command(
            word=Spec('a silly argument', choices=['this', 'that']),
            )
        def test_choices(word):
            pass
        self.assertRaisesRegex(
                ScriptionError,
                r"WORD: 'gark' not in \[ this \| that \]",
                _usage,
                test_choices,
                'test_choices gark'.split(),
                )

    def test_radio_single(self):
        @Command(
            csv=Spec('output is csv', FLAG, radio='output'),
            xls=Spec('output is xls', FLAG, radio='output'),
            txt=Spec('output is fixed-width text', FLAG, radio='output'),
            output=Spec('output type', OPTION, choices=['csv','xls','txt'], radio='output'),
            )
        def test_radio(csv, xls, txt, output):
            pass
        tests = (
                ('test_radio'.split(), (), {}, (False, False, False, None), {}),
                ('test_radio -c'.split(), (), {}, (True, False, False, None), {}),
                ('test_radio -x'.split(), (), {}, (False, True, False, None), {}),
                ('test_radio -t'.split(), (), {}, (False, False, True, None), {}),
                ('test_radio -o xls'.split(), (), {}, (False, False, False, 'xls'), {}),
                )
        test_func_parsing(self, test_radio, tests)
        self.assertRaisesRegex(
                ScriptionError,
                'only one of CSV, OUTPUT, TXT, and XLS may be specified',
                _usage,
                test_radio,
                'test_radio -c -t'.split(),
                )
        self.assertRaisesRegex(
                ScriptionError,
                'only one of CSV, OUTPUT, TXT, and XLS may be specified',
                _usage,
                test_radio,
                'test_radio -x -o xls'.split(),
                )

    def test_radio_multiple(self):
        @Command(
            csv=Spec('output is csv', FLAG, radio='output'),
            xls=Spec('output is xls', FLAG, radio='output'),
            txt=Spec('output is fixed-width text', FLAG, radio='output'),
            output=Spec('output type', OPTION, choices=['csv','xls','txt'], radio='output'),
            red=Spec('highlight color', FLAG, radio='color'),
            yellow=Spec('highlight color', FLAG, radio='color'),
            )
        def test_radio(csv, xls, txt, output, red, yellow):
            pass
        tests = (
                ('test_radio'.split(), (), {}, (False, False, False, None, False, False), {}),
                ('test_radio -c -r'.split(), (), {}, (True, False, False, None, True, False), {}),
                ('test_radio -x -y'.split(), (), {}, (False, True, False, None, False, True), {}),
                ('test_radio -t -y'.split(), (), {}, (False, False, True, None, False, True), {}),
                ('test_radio -o xls -r'.split(), (), {}, (False, False, False, 'xls', True, False), {}),
                )
        test_func_parsing(self, test_radio, tests)
        self.assertRaisesRegex(
                ScriptionError,
                'only one of RED and YELLOW may be specified',
                _usage,
                test_radio,
                'test_radio -c -r -y'.split(),
                )
        self.assertRaisesRegex(
                ScriptionError,
                'only one of RED and YELLOW may be specified',
                _usage,
                test_radio,
                'test_radio -r -y -t -o blah'.split(),
                )

    def test_radio_all(self):
        @Command(
                huh=Spec('what', 'flag', radio='aches'),
                uhuh=Spec('no way', 'flag', radio='aches'),
                wuhuh=Spec('yeah huh', 'flag', radio='aches'),
                ow=Spec('oh no', 'option', radio='w'),
                toohoo=Spec('yes way', 'option', radio='w'),
                gosh=Spec('really', 'multi', radio='explete'),
                darn=Spec('argghhh', 'multi', radio='explete'),
                )
        def tester(huh, uhuh, wuhuh, ow, toohoo, gosh, darn):
            pass
        tests = (
                ( 'tester -h '.split(), (), {}, (True, False, False, None, None, (), ()), {} ),
                ( 'tester -u -o google'.split(), (), {}, (False, True, False, 'google', None, (), ()), {} ),
                ( 'tester -w -t file2'.split(), (), {}, (False, False, True, None, 'file2', (), ()), {} ),
                ( 'tester -h -g ick'.split(), (), {}, (True, False, False, None, None, ('ick', ), ()), {} ),
                ( 'tester -u -o google -d ack'.split(), (), {}, (False, True, False, 'google', None, (), ('ack', )), {} ),
                ( 'tester -w -t file2 -g ick,ack'.split(), (), {}, (False, False, True, None, 'file2', ('ick', 'ack'), ()), {} ),
                )
        test_func_parsing(self, tester, tests)
        #
        self.assertRaisesRegex(
                ScriptionError,
                'only one of HUH, UHUH, and WUHUH may be specified',
                _usage, tester, 'tester -h -u'.split(),
                )
        #
        self.assertRaisesRegex(
                ScriptionError,
                'only one of HUH, UHUH, and WUHUH may be specified',
                _usage, tester, 'tester -h -w'.split(),
                )
        #
        self.assertRaisesRegex(
                ScriptionError,
                'only one of HUH, UHUH, and WUHUH may be specified',
                _usage, tester, 'tester -w -u'.split(),
                )
        #
        self.assertRaisesRegex(
                ScriptionError,
                'only one of HUH, UHUH, and WUHUH may be specified',
                _usage, tester, 'tester -h -u -o maybe'.split(),
                )
        #
        self.assertRaisesRegex(
                ScriptionError,
                'only one of HUH, UHUH, and WUHUH may be specified',
                _usage, tester, 'tester -h -u -t definitely'.split(),
                )
        #
        self.assertRaisesRegex(
                ScriptionError,
                'only one of OW and TOOHOO may be specified',
                _usage, tester, 'tester -o=google -t yahoo'.split(),
                )
        #
        self.assertRaisesRegex(
                ScriptionError,
                'only one of OW and TOOHOO may be specified',
                _usage, tester, 'tester -h -o google --toohoo=yahoo'.split(),
                )
        #
        self.assertRaisesRegex(
                ScriptionError,
                'only one of OW and TOOHOO may be specified',
                _usage, tester, 'tester -u -o google -t yahoo'.split(),
                )
        #
        self.assertRaisesRegex(
                ScriptionError,
                'only one of OW and TOOHOO may be specified',
                _usage, tester, 'tester --ow=google -t=yahoo'.split(),
                )
        #
        self.assertRaisesRegex(
                ScriptionError,
                'only one of DARN and GOSH may be specified',
                _usage, tester, 'tester -o google --darn=ack -g ick'.split(),
                )

    def test_target_1(self):
        @Command(
                config=Spec('use the specified Markdoc configuration', OPTION, type=Path),
                log_level=Spec('how verbose to be in the log file', OPTION, choices=['DEBUG','INFO','WARN','ERROR'], force_default='INFO', radio='log'),
                quiet=Spec('alias for --log-level=ERROR', FLAG, None, default='ERROR', target='log_level', radio='log'),
                verbose=Spec('alias for --log-level=DEBUG', FLAG, None, default='DEBUG', target='log_level', radio='log'),
                )
        def tester(config, log_level):
            pass
        tests = (
                ( 'tester'.split(), (), {}, (None, 'INFO'), {}),
                ( 'tester -c /here/stuff.text --log-level WARN'.split(), (), {}, (Path('/here/stuff.text'), 'WARN'), {}),
                ( 'tester --quiet'.split(), (), {}, (None, 'ERROR'), {}),
                )
        test_func_parsing(self, tester, tests)
        #
        self.assertRaisesRegex(
                ScriptionError,
                'only one of LOG_LEVEL, QUIET, and VERBOSE may be specified',
                _usage, tester, 'tester --quiet --verbose'.split(),
                )

    def test_target_2(self):
        from dbf import Date
        @Command(
                date=Spec('date to examine', OPTION, type=Date, radio='date'),
                email=Spec('send email to these addresses', MULTI),
                yesterday=Spec('examine yesterday', FLAG, target='date', radio='date', default=Date.today().replace(delta_day=-1)),
                )
        def tester(date, email):
            pass
        tests = (
                ( 'tester'.split(), (), {}, (None, ()), {}),
                ( 'tester -d 2023-01-17'.split(), (), {}, (Date(2023, 1, 17), ()), {}),
                ( 'tester --yesterday'.split(), (), {}, (Date.today().replace(delta_day=-1), ()), {}),
                )
        test_func_parsing(self, tester, tests)
        self.assertRaisesRegex(
                ScriptionError,
                'only one of DATE and YESTERDAY may be specified',
                _usage, tester, 'tester --date=2023-01-17 --yesterday'.split(),
                )


class TestParamRemoval(TestCase):

    template = (
            "from __future__ import print_function\n"
            "import sys\n"
            "sys.path.insert(0, %r)\n"
            "from scription import *\n"
            "\n"
            "@Command(\n"
            "        test=Spec('does this get removed?', %s, remove=True),\n"
            "        )\n"
            "def removal_script(test):\n"
            "    if isinstance(test, tuple):\n"
            "        for t in test:\n"
            "            if t in sys.argv:\n"
            "                print('failure', verbose=0)\n"
            "        else:\n"
            "            print('success!', verbose=0)\n"
            "    else:\n"
            "        if test not in sys.argv:\n"
            "            print('success!', verbose=0)\n"
            "        else:\n"
            "            print(sys.argv, verbose=0)\n"
            "\n"
            "Main()"
            )

    def write_script(self, test_type):
        target_dir = os.path.join(os.getcwd(), os.path.split(os.path.split(scription.__file__)[0])[0])
        file_path = os.path.join(tempdir, 'removal_script')
        file = open(file_path, 'w')
        try:
            file.write(self.template % (target_dir, test_type))
            return file_path
        finally:
            file.close()

    def test_required(self):
        test_file = self.write_script('REQUIRED')
        result = Execute([sys.executable, test_file, 'haha!'], timeout=300)
        self.assertEqual(result.stdout, 'success!\n', result.stdout + '\n' + result.stderr)

    def test_option(self):
        test_file = self.write_script('OPTION')
        result = Execute([sys.executable, test_file, '--test', 'haha!'], timeout=300)
        self.assertEqual(result.stdout, 'success!\n', result.stdout + '\n' + result.stderr)

    def test_flag(self):
        test_file = self.write_script('FLAG')
        result = Execute([sys.executable, test_file, '--test'], timeout=300)
        self.assertEqual(result.stdout, 'success!\n', result.stdout + '\n' + result.stderr)

    def test_multi1(self):
        test_file = self.write_script('MULTI')
        result = Execute([sys.executable, test_file, '--test', 'boo'], timeout=300)
        self.assertEqual(result.stdout, 'success!\n', result.stdout + '\n' + result.stderr)

    def test_multi2(self):
        test_file = self.write_script('MULTI')
        result = Execute([sys.executable, test_file, '--test', 'boo,hoo'], timeout=300)
        self.assertEqual(result.stdout, 'success!\n', result.stdout + '\n' + result.stderr)

    def test_multi3(self):
        test_file = self.write_script('MULTI')
        result = Execute([sys.executable, test_file, '--test', 'boo', '--test', 'hoo'], timeout=300)
        self.assertEqual(result.stdout, 'success!\n', result.stdout + '\n' + result.stderr)

    @skip('not implemented')
    def test_with_default_in_command(self):
        @Command(
                huh=('misc options', 'option'),
                wow=Spec('oh yeah', 'option', default='spam!'),
                )
        def tester(huh, wow):
            pass
        tests = (
                ( 'tester'.split(), (), {}, (None, None), {} ),
                ( 'tester -w'.split(), (), {}, (None, 'spam!'), {} ),
                ( 'tester -w google'.split(), (), {}, (None, 'google'), {} ),
                ( 'tester -h file1'.split(), (), {}, ('file1', None), {} ),
                ( 'tester -h file1 -w'.split(), (), {}, ('file1', 'spam!'), {} ),
                ( 'tester -h file1 -w google'.split(), (), {}, ('file1', 'google'), {} ),
                ( 'tester -h file2 -w frizzle'.split(), (), {}, ('file2', 'frizzle'), {} ),
                )
        test_func_parsing(self, tester, tests)

class TestCommandNames(TestCase):

    def setUp(self):
        target_dir = os.path.join(os.getcwd(), os.path.split(os.path.split(scription.__file__)[0])[0])
        self.command_file = command_file_name = os.path.join(tempdir, 'Some_Script')
        command_file = open(command_file_name, 'w')
        try:
            command_file.write(
                "'just a test doc'\n"
                "from __future__ import print_function\n"
                "import sys\n"
                "sys.path.insert(0, %r)\n"
                "from scription import *\n"
                "\n"
                "@Command(\n"
                "        huh=('misc options', 'multi'),\n"
                "        wow=('oh yeah', 'option'),\n"
                "        )\n"
                "def test_dash(huh, wow):\n"
                "    'testing dashes in name'\n"
                "    print('success!', verbose=0)\n"
                "\n"
                "@Command(\n"
                "        hah=('misc options', 'flag'),\n"
                "        wow=('oh yeah', 'option'),\n"
                "        )\n"
                "def test_Capital(hah, wow):\n"
                "    'testing capital in name'\n"
                "    print('it worked!!', verbose=0)\n"
                "\n"
                "@Command()\n"
                "def some_script():\n"
                "    'testing caps in name'\n"
                "    print('aint that nice.', verbose=0)\n"
                "\n"
                "Run()\n"
                % target_dir
                )
        finally:
            command_file.close()

    def test_dash_in_name(self):
        for name in ('test_dash', 'test-dash'):
            cmdline = ' '.join([sys.executable, self.command_file, name])
            result = Execute(cmdline, timeout=10)
            self.assertTrue(result.returncode == 0, '%r failed! [%r]\n%r\n%r' % (cmdline, result.returncode, result.stdout, result.stderr))
            self.assertEqual(result.stderr, '', '%r failed!\n%r\n%r' % (cmdline, result.stdout, result.stderr))
            self.assertEqual(result.stdout, 'success!\n', '%r failed!\n%r\n%r' % (cmdline, result.stdout, result.stderr))

    def test_capital_in_command_name(self):
        for name in ('test_capital', 'Test-CAPITAL'):
            cmdline = ' '.join([sys.executable, self.command_file, name])
            result = Execute(cmdline, timeout=10)
            self.assertTrue(result.returncode == 0, '%r failed! [%r]\n%r\n%r' % (cmdline, result.returncode, result.stdout, result.stderr))
            self.assertEqual(result.stderr, '', '%r failed!\n%r\n%r' % (cmdline, result.stdout, result.stderr))
            self.assertEqual(result.stdout, 'it worked!!\n', '%r failed!\n%r\n%r' % (cmdline, result.stdout, result.stderr))

    def test_capital_in_command_line(self):
        cmdline = ' '.join([sys.executable, self.command_file])
        result = Execute(cmdline, timeout=10)
        self.assertTrue(result.returncode == 0, '%r failed! [%r]\n%r\n%r' % (cmdline, result.returncode, result.stdout, result.stderr))
        self.assertEqual(result.stderr, '', '%r failed!\n%r\n%r' % (cmdline, result.stdout, result.stderr))
        self.assertEqual(result.stdout, 'aint that nice.\n', '%r failed!\n%r\n%r' % (cmdline, result.stdout, result.stderr))
        cmdline = ' '.join([sys.executable, self.command_file, '--help'])
        result = Execute(cmdline, timeout=10)
        self.assertTrue(result.returncode == 0, '%r failed! [%r]\n%r\n%r' % (cmdline, result.returncode, result.stdout, result.stderr))
        self.assertEqual(result.stderr, '', '%r failed!\n%r\n%r' % (cmdline, result.stdout, result.stderr))
        self.assertEqual(
                result.stdout,
                'just a test doc\n   some-script   testing caps in name\n   test-capital  testing capital in name\n   test-dash     testing dashes in name\n',
                '%r failed!\nstdout: %r\nstderr: %r' % (cmdline, result.stdout, result.stderr),
                )

class TestHelp(TestCase):

    def write_script(self, test_data):
        target_dir = os.path.join(os.getcwd(), os.path.split(os.path.split(scription.__file__)[0])[0])
        file_path = os.path.join(tempdir, 'help_test')
        file = open(file_path, 'w')
        try:
            file.write(test_data % target_dir)
            return file_path
        finally:
            file.close()

    def test_single_command(self):
        file_data = (
                "import sys\n"
                "sys.path.insert(0, %r)\n"
                "from scription import *\n"
                "\n"
                "@Script(\n"
                "        conf=('configuration file', OPTION),\n"
                "        )\n"
                "def main():\n"
                "    pass\n"
                "\n"
                "@Command(\n"
                "        this=('this argument',),\n"
                "        that=('that argument',),\n"
                "        )\n"
                "def whatever(this, that):\n"
                "    pass\n"
                "\n"
                "\n"
                "Main()\n"
                )
        target_result = (
                "global settings: --conf CONF\n"
                "\n"
                "    CONF   configuration file\n"
                "\n"
                "whatever THIS THAT\n"
                "\n"
                "    THIS   this argument    \n"
                "    THAT   that argument    \n"
                )
        test_file = self.write_script(file_data)
        result = Execute([sys.executable, test_file, '--help'], timeout=300)
        self.assertMultiLineEqual(result.stdout.strip(), target_result.strip())
        result = Execute([sys.executable, test_file, '--help'], pty=True, timeout=300)
        self.assertMultiLineEqual(result.stdout.strip(), target_result.strip())

    def test_alias_command(self):
        file_data = (
                "import sys\n"
                "sys.path.insert(0, %r)\n"
                "from scription import *\n"
                "\n"
                "@Script(\n"
                "        conf=('configuration file', OPTION),\n"
                "        )\n"
                "def main():\n"
                "    pass\n"
                "\n"
                "@Command(\n"
                "        this=('this argument',),\n"
                "        that=('that argument',),\n"
                "        )\n"
                "@Alias('another-thing')\n"
                "def whatever(this, that):\n"
                "    pass\n"
                "\n"
                "\n"
                "Main()\n"
                )
        target_result = (
                "global settings: --conf CONF\n"
                "\n"
                "    CONF   configuration file\n"
                "\n"
                "whatever THIS THAT\n"
                "\n"
                "    THIS   this argument    \n"
                "    THAT   that argument    \n"
                )
        test_file = self.write_script(file_data)
        result = Execute([sys.executable, test_file, '--help'], timeout=300)
        self.assertMultiLineEqual(result.stdout.strip(), target_result.strip())

    def test_alias_command_canonical(self):
        file_data = (
                "import sys\n"
                "sys.path.insert(0, %r)\n"
                "from scription import *\n"
                "\n"
                "@Script(\n"
                "        conf=('configuration file', OPTION),\n"
                "        )\n"
                "def main():\n"
                "    pass\n"
                "\n"
                "@Alias('another-thing', canonical=True)\n"
                "@Command(\n"
                "        this=('this argument',),\n"
                "        that=('that argument',),\n"
                "        )\n"
                "def whatever(this, that):\n"
                "    pass\n"
                "\n"
                "\n"
                "Main()\n"
                )
        target_result = (
                "global settings: --conf CONF\n"
                "\n"
                "    CONF   configuration file\n"
                "\n"
                "another-thing THIS THAT\n"
                "\n"
                "    THIS   this argument    \n"
                "    THAT   that argument    \n"
                )
        test_file = self.write_script(file_data)
        result = Execute([sys.executable, test_file, '--help'], timeout=300)
        self.assertMultiLineEqual(result.stdout.strip(), target_result.strip(), result.stderr)

    def test_alias_matches_script_name(self):
        file_data = (
                "import sys\n"
                "sys.path.insert(0, %r)\n"
                "from scription import *\n"
                "\n"
                "@Script(\n"
                "        conf=('configuration file', OPTION),\n"
                "        )\n"
                "def main():\n"
                "    pass\n"
                "\n"
                "@Command(\n"
                "        this=('this argument',),\n"
                "        that=('that argument',),\n"
                "        )\n"
                "@Alias('help-test')\n"
                "def whatever(this, that):\n"
                "    pass\n"
                "\n"
                "\n"
                "Main()\n"
                )
        target_result = (
                "global settings: --conf CONF\n"
                "\n"
                "    CONF   configuration file\n"
                "\n"
                "help-test THIS THAT\n"
                "\n"
                "    THIS   this argument    \n"
                "    THAT   that argument    \n"
                )
        test_file = self.write_script(file_data)
        result = Execute([sys.executable, test_file, '--help'], timeout=300)
        self.assertMultiLineEqual(result.stdout.strip(), target_result.strip())

    def test_multiple_commands(self):
        file_data = (
                "import sys\n"
                "sys.path.insert(0, %r)\n"
                "from scription import *\n"
                "\n"
                "@Script(\n"
                "        conf=('configuration file', OPTION),\n"
                "        )\n"
                "def main():\n"
                "    pass\n"
                "\n"
                "@Command(\n"
                "        this=('this argument',),\n"
                "        that=('that argument',),\n"
                "        )\n"
                "@Alias('another-thing')\n"
                "def whatever(this, that):\n"
                "    pass\n"
                "\n"
                "@Command(\n"
                "        other=('an other argumant', ),\n"
                "        )\n"
                "def that_thing(other):\n"
                "    pass\n"
                "\n"
                "\n"
                "Main()\n"
                )
        target_result = (
                "Available commands/options in help_test\n"
                "\n"
                "   global settings: --conf CONF\n"
                "\n"
                "   that-thing     OTHER\n"
                "   whatever       THIS THAT\n"
                )
        test_file = self.write_script(file_data)
        result = Execute([sys.executable, test_file, '--help'], timeout=300)
        self.assertMultiLineEqual(result.stdout.strip(), target_result.strip())


class TestDocStrings(TestCase):

    def setUp(self):
        module = scription.script_module
        module['script_name'] = '<unknown>'
        module['script_fullname'] = '<unknown>'
        module['script_main'] = None
        module['script_commands'] = {}
        module['script_command'] = None
        module['script_commandname'] = ''
        module['script_exception_lines'] = ''

    def test_single_line(self):
        @Script()
        def main():
            "a single-line test"

        @Command()
        def sub():
            "another one-liner"

        test_func_docstrings(self, main, "a single-line test")
        test_func_docstrings(self, sub, "another one-liner")

    def test_one_line(self):
        @Script()
        def main():
            """
            a single-line in three
            """

        @Command()
        def sub():
            """
            another one-liner in three
            """

        test_func_docstrings(self, main, "a single-line in three")
        test_func_docstrings(self, sub, "another one-liner in three")

    def test_two_lines(self):
        @Script()
        def main():
            """this is the first line
            and this is indented
            """

        @Command()
        def sub():
            """another first line
            and another indented
            """

        test_func_docstrings(self, main, "this is the first line\n            and this is indented")
        test_func_docstrings(self, sub, "another first line\n            and another indented")

    def test_two_lines_in_three(self):
        @Script()
        def main():
            """
            this is the first line
            and this is the same indentation
            """

        @Command()
        def sub():
            """
            another first line
            and another indented the same
            """

        test_func_docstrings(self, main, "this is the first line\nand this is the same indentation")
        test_func_docstrings(self, sub, "another first line\nand another indented the same")

    def test_two_lines_with_good_indentation(self):
        @Script()
        def main():
            """
            this is the first line
                and this is indented
            """

        @Command()
        def sub():
            """
            another first line
                with good indentation
            """

        test_func_docstrings(self, main, "this is the first line\n    and this is indented")
        test_func_docstrings(self, sub, "another first line\n    with good indentation")


class TestExecution(TestCase):

    def setUp(self):
        self.good_file = good_file_path = os.path.join(tempdir, 'good_output')
        good_file = open(good_file_path, 'w')
        try:
            good_file.write("print('good output here!')")
        finally:
            good_file.close()
        #
        self.bad_file = bad_file_path = os.path.join(tempdir, 'bad_output')
        bad_file = open(bad_file_path, 'w')
        try:
            bad_file.write("raise ValueError('uh-oh -- bad value!')")
        finally:
            bad_file.close()
        #
        self.dead_file = dead_file_path = os.path.join(tempdir, 'dead_file')
        dead_file = open(dead_file_path, 'w')
        try:
            dead_file.write("print('usage message here')\nraise SystemExit(1)")
        finally:
            dead_file.close()
        #
        self.mixed_file = mixed_file_name = os.path.join(tempdir, 'mixed_output')
        mixed_file = open(mixed_file_name, 'w')
        try:
            mixed_file.write(
                    "print('good night')\n"
                    "print('sweetheart!')\n"
                    "raise KeyError('the key is missing?')"
                    )
        finally:
            mixed_file.close()
        #
        self.pty_password_file = password_file_name = os.path.join(tempdir, 'get_pty_pass')
        password_file = open(password_file_name, 'w')
        try:
            password_file.write(
                    "from getpass import getpass\n"
                    "print('super secret santa soda sizzle?')\n"
                    "password = getpass('make sure no one is watching you type!: ')\n"
                    "print('%r?  Are you sure??' % password)"
                    )
        finally:
            password_file.close()
        #
        self.subp_password_file = password_file_name = os.path.join(tempdir, 'get_subp_pass')
        password_file = open(password_file_name, 'w')
        try:
            password_file.write(
                    "print('super secret santa soda sizzle?')\n"
                    "password = %sinput('make sure no one is watching you type!: ')\n"
                    "print('%%r?  Are you sure??' %% password)"
                    % ('', 'raw_')[PY2]
                    )
        finally:
            password_file.close()
        #
        self.echo_off_file = echo_off_name = os.path.join(tempdir, 'echo_off')
        echo_off = open(echo_off_name, 'w')
        try:
            echo_off.write(
                    "import termios, sys\n"
                    "try:\n"
                    "    input = raw_input\n"
                    "except NameError:\n"
                    "    pass\n"
                    "fd = sys.stdin.fileno()\n"
                    "old = termios.tcgetattr(fd)\n"
                    "new = termios.tcgetattr(fd)\n"
                    "new[3] = new[3] & ~termios.ECHO          # lflags\n"
                    "try:\n"
                    "    termios.tcsetattr(fd, termios.TCSADRAIN, new)\n"
                    "    passwd = input('gimme some!')\n"
                    "finally:\n"
                    "    termios.tcsetattr(fd, termios.TCSADRAIN, old)\n"
                    )
        finally:
            echo_off.close()
        #
        self.long_sleeper_file = sleeper = os.path.join(tempdir, 'bad_sleeper')
        sleeper = open(sleeper, 'w')
        try:
            sleeper.write(
                    "import time\n"
                    "time.sleep(15)\n"
                    )
        finally:
            sleeper.close()

    def test_bad_timeout(self):
        job = Job([sys.executable, self.pty_password_file], pty=True)
        self.assertRaises(
                ValueError,
                job.communicate,
                timeout=2,
                password_timeout=10,
                )

    if not is_win:
        def test_pty(self):
            command = Execute([sys.executable, self.good_file], pty=True, timeout=600)
            self.assertEqual(command.stdout, 'good output here!\n')
            self.assertEqual(command.stderr, '')
            command = Execute([sys.executable, self.bad_file], pty=True, timeout=600)
            self.assertEqual(command.stdout, '')
            self.assertTrue(command.stderr.endswith('ValueError: uh-oh -- bad value!\n'))
            command = Execute([sys.executable, self.mixed_file], pty=True, timeout=600)
            self.assertEqual(command.stdout, 'good night\nsweetheart!\n')
            self.assertTrue(command.stderr.endswith("KeyError: 'the key is missing?'\n"),
                    'Failed (actual results):\n%s' % command.stderr)
            command = Execute([sys.executable, self.pty_password_file], password='Salutations!', pty=True, timeout=600)
            self.assertEqual(
                    command.stdout,
                    "super secret santa soda sizzle?\nmake sure no one is watching you type!: \n'Salutations!'?  Are you sure??\n",
                    )
            self.assertEqual(
                    command.stderr,
                    '',
                    )

        def test_pty_with_dead_file(self):
            job = Job([sys.executable, self.dead_file], pty=True)
            try:
                job.communicate(input='anybody there?\n', timeout=60)
            except OSError as exc:
                if exc.errno != errno.ECHILD:
                    raise
                self.assertEqual(job.stdout, 'usage message here\n')
            else:
                self.assertEqual(job.stdout, 'anybody there?\nusage message here\n')
            self.assertTrue(job.returncode)

    if is_win:
        if pyver >= PY33:
            def test_timeout(self):
                "test timeout with subprocess alone"
                command = Execute([sys.executable, '-c', 'import time; time.sleep(30)'], timeout=3, pty=False)
                self.assertTrue(command.returncode)
        else:
            def test_timeout(self):
                "no timeout in this version"
                self.assertRaises(
                        OSError,
                        Execute,
                        [sys.executable, '-c', 'import time; time.sleep(30)'],
                        timeout=3,
                        pty=False,
                        )
                self.assertRaises(
                        OSError,
                        Execute,
                        [sys.executable, '-c', 'import time; time.sleep(30)'],
                        timeout=3,
                        pty=True,
                        )
    else:
        def test_timeout(self):
            "test timeout with pty, and with subprocess/signals"
            command = Job(
                    [sys.executable, '-c', 'import time; time.sleep(30); raise Exception("did not time out!")'],
                    pty=True,
                    )
            self.assertRaises(
                    TimeoutError,
                    command.communicate,
                    timeout=3,
                    )
            self.assertTrue('TIMEOUT' in command.stderr)
            self.assertTrue(command.returncode)
            command = Job(
                    [sys.executable, '-c', 'import time; time.sleep(30); raise Exception("did not time out!")'],
                    pty=False,
                    )
            self.assertRaises(
                    TimeoutError,
                    command.communicate,
                    timeout=3,
                    )
            self.assertTrue('TIMEOUT' in command.stderr)
            self.assertTrue(command.returncode)

    def test_environ(self):
        "test setting environment"
        command = Execute(
                [sys.executable, '-c', 'import os; print("I found: " + os.environ["HAPPYDAY"])'],
                timeout=300,
                pty=False,
                HAPPYDAY='fonzirelli',
                )
        self.assertIn('fonzirelli', command.stdout)
        command = Execute(
                [sys.executable, '-c', 'import os; print("I found: " + os.environ["HAPPYDAY"])'],
                timeout=300,
                pty=True,
                HAPPYDAY='fonzirelli',
                )
        self.assertIn('fonzirelli', command.stdout)

    def test_subprocess(self):
        command = Execute(
                [sys.executable, self.good_file],
                pty=False,
                timeout=300,
                )
        self.assertEqual(command.stdout, 'good output here!\n')
        self.assertEqual(command.stderr, '')
        command = Execute(
                [sys.executable, self.bad_file],
                pty=False,
                timeout=300,
                )
        self.assertEqual(command.stdout, '')
        self.assertTrue(command.stderr.endswith('ValueError: uh-oh -- bad value!\n'))
        command = Execute(
                [sys.executable, self.mixed_file],
                pty=False,
                timeout=300,
                )
        self.assertEqual(command.stdout, 'good night\nsweetheart!\n')
        self.assertTrue(command.stderr.endswith("KeyError: 'the key is missing?'\n"),
                'Failed (actual results):\n%r' % command.stderr)
        command = Execute(
                [sys.executable, self.subp_password_file],
                pty=False,
                password='Salutations!',
                timeout=300,
                )
        self.assertEqual(
                command.stdout,
                "super secret santa soda sizzle?\nmake sure no one is watching you type!: 'Salutations!'?  Are you sure??\n",
                'Failed (actual results):\n%r' % command.stdout,
                )
        self.assertEqual(command.stderr, '')

    def test_unmangled_password(self):
        command = Execute(
                [sys.executable, self.subp_password_file],
                pty=False,
                password=unicode('Salutations!'),
                timeout=300,
                )
        self.assertEqual(
                command.stdout,
                "super secret santa soda sizzle?\nmake sure no one is watching you type!: 'Salutations!'?  Are you sure??\n",
                'Failed (actual results):\nstdout:\n%s\nstderr:\n%s' % (command.stdout, command.stderr),
                )
        self.assertEqual(command.stderr, '')

    def test_input_with_echo_off(self):
        try:
            command = Job(
                    [sys.executable, self.echo_off_file],
                    pty=True,
                    )
            command.communicate(
                    input=unicode('Salutations!\n'),
                    timeout=30,
                    )
        except IOError as exc:
            raise Exception('%s occured;\n%s\n%s' % (exc, command.stdout, command.stderr))

    # def test_locked_pty(self):
    #     """
    #     simulate a locked job (real life example: trying to query a dropped mount)
    #     """
    #     raise NotImplementedError()



class TestOrm(TestCase):

    def setUp(self):
        self.orm_file = orm_file_name = os.path.join(tempdir, 'test.orm')
        orm_file = open(orm_file_name, 'w')
        try:
            orm_file.write(
                    "home = /usr/bin\n"
                    'who = "ethan"\n'
                    'why = why not?\n'
                    'why_not = True\n'
                    'where = False\n'
                    "\n"
                    '[not_used]\n'
                    'this = "that"\n'
                    'these = "those"\n'
                    "[hg]\n"
                    "home = /usr/local/bin\n"
                    "when = 12:45\n"
                    'why_not = None\n'
                    '[data_types]\n'
                    'list = [1, 2, 3]\n'
                    'tuple = (4, 5, 6)\n'
                    'dict = {7:8, 9:10}\n'
                    )
        finally:
            orm_file.close()
        self.orm_file_plain = orm_file_name = os.path.join(tempdir, 'test-plain.orm')
        orm_file = open(orm_file_name, 'w')
        try:
            orm_file.write(
                    'who = ethan\n'
                    "home = \n"
                    "\n"
                    "what = False\n"
                    "where = True\n"
                    "when = 12.45\n"
                    'why = None\n'
                    "how = 33\n"
                    )
        finally:
            orm_file.close()
        self.orm_file_sub = orm_file_name = os.path.join(tempdir, 'test-sub.orm')
        orm_file = open(orm_file_name, 'w')
        try:
            orm_file.write(
                    "[postgres]\n"
                    "psql = /usr/lib/postgresql/9.1/bin/psql\n"
                    "\n"
                    "[postgres.v901]\n"
                    "pg_dump = /usr/lib/postgres/9.1/bin/pg_dump\n"
                    "pg_dumpall = /usr/lib/postgres/9.1/bin/pg_dumpall\n"
                    "\n"
                    "[postgres.v903]\n"
                    "pg_dump = /usr/lib/postgres/9.3/bin/pg_dump\n"
                    "pg_dumpall = /usr/lib/postgres/9.3/bin/pg_dumpall\n"
                    "\n"
                    "[postgres.v905]\n"
                    "pg_dump = /usr/lib/postgres/9.5/bin/pg_dump\n"
                    "pg_dumpall = /usr/lib/postgres/9.5/bin/pg_dumpall\n"
                    )
        finally:
            orm_file.close()

    def test_plain(self):
        'test plain conversion'
        # test whole thing
        complete = OrmFile(self.orm_file_plain, plain=True)
        root = list(complete)
        self.assertEqual(len(root), 7)
        self.assertTrue(('home', '') in root)
        self.assertTrue(('who', 'ethan') in root)
        self.assertTrue(('what', False) in root)
        self.assertTrue(('where', True) in root)
        self.assertTrue(('when', 12.45) in root)
        self.assertTrue(('why', None) in root)
        self.assertTrue(('how', 33) in root)

    def test_iteration(self):
        'test iteration'
        # test whole thing
        complete = OrmFile(self.orm_file)
        hg = list(complete.hg)
        root = list(complete)
        self.assertEqual(len(root), 8)
        self.assertTrue(('home', '/usr/bin') in root)
        self.assertTrue(('who', 'ethan') in root)
        self.assertTrue(('why', 'why not?') in root)
        self.assertTrue(('why_not', True) in root)
        self.assertTrue(('where', False) in root)
        self.assertTrue(('hg', complete.hg) in root)
        self.assertEqual(len(hg), 6)
        self.assertTrue(('home', '/usr/local/bin') in hg)
        self.assertTrue(('who', 'ethan') in hg)
        self.assertTrue(('why', 'why not?') in hg)
        self.assertTrue(('when', datetime.time(12, 45)) in hg)
        self.assertTrue(('why_not', None) in hg)
        # test subsection
        hg_only = OrmFile(self.orm_file, section='hg')
        hg = list(hg_only)
        self.assertEqual(len(hg), 6)
        self.assertTrue(('home', '/usr/local/bin') in hg)
        self.assertTrue(('who', 'ethan') in hg)
        self.assertTrue(('why', 'why not?') in hg)
        self.assertTrue(('when', datetime.time(12, 45)) in hg)
        self.assertTrue(('why_not', None) in hg)

    def test_standard(self):
        'test standard data types'
        complete = OrmFile(self.orm_file)
        self.assertEqual(complete.home, '/usr/bin')
        self.assertEqual(complete.who, 'ethan')
        self.assertEqual(complete.why, 'why not?')
        self.assertEqual(complete.why_not, True)
        self.assertEqual(complete.where, False)
        self.assertEqual(complete.hg.home, '/usr/local/bin')
        self.assertEqual(complete.hg.who, 'ethan')
        self.assertEqual(complete.hg.when, datetime.time(12, 45))
        self.assertEqual(complete.hg.why_not, None)
        self.assertEqual(complete.data_types.list, [1, 2, 3])
        self.assertEqual(complete.data_types.tuple, (4, 5, 6))
        self.assertEqual(complete.data_types.dict, {7:8, 9:10})
        self.assertTrue(type(complete.home) is unicode)
        self.assertTrue(type(complete.who) is unicode)
        self.assertTrue(type(complete.hg.when) is datetime.time)
        self.assertTrue(type(complete.why_not) is bool)
        self.assertTrue(type(complete.where) is bool)
        self.assertTrue(type(complete.data_types.list) is list)
        self.assertTrue(type(complete.data_types.tuple) is tuple)
        self.assertTrue(type(complete.data_types.dict) is dict)
        hg = OrmFile(self.orm_file, section='hg')
        self.assertEqual(hg.home, '/usr/local/bin')
        self.assertEqual(hg.who, 'ethan')
        self.assertEqual(hg.when, datetime.time(12, 45))
        self.assertTrue(type(hg.home) is unicode)
        self.assertTrue(type(hg.who) is unicode)
        self.assertTrue(type(hg.when) is datetime.time)
        self.assertTrue(type(hg.why_not) is type(None))

    def test_limited_defaults(self):
        'ensure default changes in one section do not affect peer sections'
        complete = OrmFile(self.orm_file)
        self.assertEqual(complete.home, '/usr/bin')
        self.assertEqual(complete.hg.home, '/usr/local/bin')
        self.assertEqual(complete.data_types.home, '/usr/bin')

    def test_custom(self):
        'test custom data types'
        class Path(unicode):
            pass
        class Time(datetime.time):
            pass
        complete = OrmFile(self.orm_file, types={'_path':Path, '_time':Time, '_str':str})
        self.assertEqual(complete.home, '/usr/bin')
        self.assertEqual(complete.who, 'ethan')
        self.assertEqual(complete.hg.home, '/usr/local/bin')
        self.assertEqual(complete.hg.who, 'ethan')
        self.assertEqual(complete.hg.when, datetime.time(12, 45))
        self.assertTrue(type(complete.home) is Path)
        self.assertTrue(type(complete.hg.who) is str)
        self.assertTrue(type(complete.hg.when) is Time)
        hg = OrmFile(self.orm_file, section='hg', types={'_path':Path, '_time':Time, '_str':str})
        self.assertEqual(hg.home, '/usr/local/bin')
        self.assertEqual(hg.who, 'ethan')
        self.assertEqual(hg.when, datetime.time(12, 45))
        self.assertTrue(type(hg.home) is Path)
        self.assertTrue(type(hg.who) is str)
        self.assertTrue(type(hg.when) is Time)

    def test_order_kept(self):
        complete = OrmFile(self.orm_file)
        self.assertEqual(
                [t[0] for t in list(complete)[:5]],
                ['home', 'who', 'why', 'why_not', 'where'],
                )
        self.assertEqual(list(complete)[5][0], 'not_used')
        self.assertEqual(list(complete)[6][0], 'hg')
        self.assertEqual(list(complete)[7][0], 'data_types')
        self.assertEqual(
                [t[0] for t in list(list(complete)[5][1])],
                ['home', 'who', 'why', 'why_not', 'where', 'this', 'these'],
                )
        self.assertEqual(
                [t[0] for t in list(list(complete)[6][1])],
                ['home', 'who', 'why', 'why_not', 'where', 'when'],
                )
        self.assertEqual(
                [t[0] for t in list(list(complete)[7][1])],
                ['home', 'who', 'why', 'why_not', 'where', 'list', 'tuple', 'dict'],
                )


    def test_subheader(self):
        complete = OrmFile(self.orm_file_sub)
        postgres = complete.postgres
        postgres91 = complete.postgres.v901
        postgres93 = complete.postgres.v903
        postgres95 = complete.postgres.v905
        self.assertEqual(len(list(complete)), 1)
        self.assertEqual(len(list(postgres)), 4)
        self.assertTrue(('postgres', complete.postgres) in list(complete))
        self.assertTrue(('v901', postgres.v901) in list(postgres))
        self.assertTrue(('v903', postgres.v903) in list(postgres))
        self.assertTrue(('v905', postgres.v905) in list(postgres))
        self.assertEqual(len(list(postgres)), 4)
        self.assertTrue(('psql', "/usr/lib/postgresql/9.1/bin/psql") in list(postgres))
        self.assertEqual(len(list(postgres91)), 3)
        self.assertTrue(('pg_dump', '/usr/lib/postgres/9.1/bin/pg_dump') in list(postgres91))
        self.assertTrue(('pg_dumpall', '/usr/lib/postgres/9.1/bin/pg_dumpall') in list(postgres91))
        self.assertEqual(len(list(postgres93)), 3)
        self.assertTrue(('pg_dump', '/usr/lib/postgres/9.3/bin/pg_dump') in list(postgres93))
        self.assertTrue(('pg_dumpall', '/usr/lib/postgres/9.3/bin/pg_dumpall') in list(postgres93))
        self.assertEqual(len(list(postgres95)), 3)
        self.assertTrue(('pg_dump', '/usr/lib/postgres/9.5/bin/pg_dump') in list(postgres95))
        self.assertTrue(('pg_dumpall', '/usr/lib/postgres/9.5/bin/pg_dumpall') in list(postgres95))

    def test_subheader_section(self):
        postgres95 = OrmFile(self.orm_file_sub, section='postgres.v905')
        self.assertEqual(len(list(postgres95)), 3)
        self.assertTrue(('psql', "/usr/lib/postgresql/9.1/bin/psql") in list(postgres95))
        self.assertTrue(('pg_dump', '/usr/lib/postgres/9.5/bin/pg_dump') in list(postgres95))
        self.assertTrue(('pg_dumpall', '/usr/lib/postgres/9.5/bin/pg_dumpall') in list(postgres95))

    def test_section_with_subheader(self):
        postgres = OrmFile(self.orm_file_sub, section='postgres')
        self.assertEqual(len(list(postgres)), 4)
        self.assertTrue(('psql', "/usr/lib/postgresql/9.1/bin/psql") in list(postgres))
        self.assertTrue(('v901', postgres.v901) in list(postgres))
        self.assertTrue(('v903', postgres.v903) in list(postgres))
        self.assertTrue(('v905', postgres.v905) in list(postgres))

    def test_write(self):
        test_orm_file_name = os.path.join(tempdir, 'written.orm')
        huh = OrmFile(test_orm_file_name)

        huh.home = '/usr/bin'
        huh.who = "ethan"
        huh.why = 'why not?'
        huh.why_not = True
        huh.where = False

        huh.not_used = OrmSection()
        huh.not_used.this = "that"
        huh.not_used.these = "those"

        huh.hg = OrmSection()
        huh.hg.home = '/usr/local/bin'
        huh.hg.when = datetime.time(12, 45)
        huh.hg.why_not = None

        huh.data_types = OrmSection()
        huh.data_types.list = [1, 2, 3]
        huh.data_types.tuple = (4, 5, 6)
        huh.data_types.dict = {7:8, 9:10}

        OrmFile.save(huh)
        # sanity check
        heh = OrmFile(self.orm_file)
        hah = OrmFile(self.orm_file)
        self.assertEqual(heh, hah)
        # and piecemeal
        self.assertEqual(huh.home, hah.home)
        self.assertEqual(huh.who, hah.who)
        self.assertEqual(huh.why, hah.why)
        self.assertEqual(huh.why_not, hah.why_not)
        self.assertEqual(huh.where, hah.where)
        self.assertEqual(huh.not_used.this, hah.not_used.this)
        self.assertEqual(huh.not_used.these, hah.not_used.these)
        self.assertEqual(huh.hg.home, hah.hg.home)
        self.assertEqual(huh.hg.when, hah.hg.when)
        self.assertEqual(huh.hg.why_not, hah.hg.why_not)
        self.assertEqual(huh.data_types.list, hah.data_types.list)
        self.assertEqual(huh.data_types.tuple, hah.data_types.tuple)
        self.assertEqual(huh.data_types.dict, hah.data_types.dict)
        # now a real check
        # piecemeal
        hah = OrmFile(test_orm_file_name)
        self.assertEqual(huh.home, hah.home)
        self.assertEqual(huh.who, hah.who)
        self.assertEqual(huh.why, hah.why)
        self.assertEqual(huh.why_not, hah.why_not)
        self.assertEqual(huh.where, hah.where)
        self.assertEqual(huh.not_used.this, hah.not_used.this)
        self.assertEqual(huh.not_used.these, hah.not_used.these)
        self.assertEqual(huh.hg.home, hah.hg.home)
        self.assertEqual(huh.hg.when, hah.hg.when)
        self.assertEqual(huh.hg.why_not, hah.hg.why_not)
        self.assertEqual(huh.data_types.list, hah.data_types.list)
        self.assertEqual(huh.data_types.tuple, hah.data_types.tuple)
        self.assertEqual(huh.data_types.dict, hah.data_types.dict)
        # and whole enchilada
        self.assertEqual(heh._settings, hah._settings)
        self.assertEqual(heh, hah)
        plain = OrmFile(self.orm_file_plain, plain=True)
        self.assertNotEqual(plain, hah)
        # and test .save not in settings
        with self.assertRaisesRegex(OrmError, 'no section/default named'):
            hah.save()

    def test_write_from_index(self):
        test_orm_file_name = os.path.join(tempdir, 'written_from_index.orm')
        huh = OrmFile(test_orm_file_name)

        huh['home'] = '/usr/bin'
        huh['who'] = "ethan"
        huh['why'] = 'why not?'
        huh['why_not'] = True
        huh['where'] = False

        huh['not_used'] = OrmSection('nothing to see here')
        huh['not_used']['this'] = "that"
        huh['not_used']['these'] = "those"

        huh['hg'] = OrmSection('cvs: active\ntype: hg')
        huh['hg']['home'] = '/usr/local/bin'
        huh['hg']['when'] = datetime.time(12, 45)
        huh['hg']['why_not'] = None

        huh['data_types'] = OrmSection()
        huh['data_types']['list'] = [1, 2, 3]
        huh['data_types']['tuple'] = (4, 5, 6)
        huh['data_types']['dict'] = {7:8, 9:10}

        OrmFile.save(huh)
        # sanity check
        heh = OrmFile(self.orm_file)
        hah = OrmFile(self.orm_file)
        self.assertEqual(heh, hah)
        # and piecemeal
        self.assertEqual(huh.home, hah.home)
        self.assertEqual(huh.who, hah.who)
        self.assertEqual(huh.why, hah.why)
        self.assertEqual(huh.why_not, hah.why_not)
        self.assertEqual(huh.where, hah.where)
        self.assertEqual(huh.not_used.this, hah.not_used.this)
        self.assertEqual(huh.not_used.these, hah.not_used.these)
        self.assertEqual(huh.hg.home, hah.hg.home)
        self.assertEqual(huh.hg.when, hah.hg.when)
        self.assertEqual(huh.hg.why_not, hah.hg.why_not)
        self.assertEqual(huh.data_types.list, hah.data_types.list)
        self.assertEqual(huh.data_types.tuple, hah.data_types.tuple)
        self.assertEqual(huh.data_types.dict, hah.data_types.dict)
        # now a real check
        # piecemeal
        hah = OrmFile(test_orm_file_name)
        self.assertEqual(huh.home, hah.home)
        self.assertEqual(huh.who, hah.who)
        self.assertEqual(huh.why, hah.why)
        self.assertEqual(huh.why_not, hah.why_not)
        self.assertEqual(huh.where, hah.where)
        self.assertEqual(huh.not_used.this, hah.not_used.this)
        self.assertEqual(huh.not_used.these, hah.not_used.these)
        self.assertEqual(huh.hg.home, hah.hg.home)
        self.assertEqual(huh.hg.when, hah.hg.when)
        self.assertEqual(huh.hg.why_not, hah.hg.why_not)
        self.assertEqual(huh.data_types.list, hah.data_types.list)
        self.assertEqual(huh.data_types.tuple, hah.data_types.tuple)
        self.assertEqual(huh.data_types.dict, hah.data_types.dict)
        # and whole enchilada
        self.assertEqual(heh._settings, hah._settings)
        self.assertEqual(heh, hah)
        plain = OrmFile(self.orm_file_plain, plain=True)
        self.assertNotEqual(plain, hah)
        # and test .save not in settings
        with self.assertRaisesRegex(OrmError, 'no section/default named'):
            hah.save()

    def test_namespace(self):
        one = NameSpace({'one': 1, 'two':2})
        two = NameSpace(dict(two=2, one=1))
        three = NameSpace()
        three.one = 1
        three.two = 2
        self.assertEqual(one, two)
        self.assertEqual(two, three)
        self.assertEqual(three, one)
        three.three = 3
        self.assertNotEqual(one, three)
        self.assertNotEqual(two, three)
        self.assertEqual(one, two)

    def test_ormclassmethod(self):
        class Test(object):
            name = None
            @ormclassmethod
            def huh(thing):
                return "%s is huhified" % thing.name
        t1 = Test()
        t1.name = 't1'
        self.assertRaisesRegex(AttributeError, "'Test' instance has no attribute 'huh'")
        self.assertEqual(Test.huh(t1), "t1 is huhified")
        t2 = Test()
        t2.name = 't2'
        t2.huh = 9
        self.assertEqual(t2.huh, 9)
        self.assertEqual(Test.huh(t2), "t2 is huhified")


class TestResponse(TestCase):

    class raw_input_cm(object):
        'context manager for mocking raw_input'
        def __init__(self, reply, allowed_attempts=1):
            self.reply = reply
            self.allowed = allowed_attempts
            self.attempted = 0
        def __call__(self, prompt):
            self.attempted += 1
            if self.attempted > self.allowed:
                raise Exception('too many attempts to get correct reply')
            self.prompt = prompt
            return self.reply
        def __enter__(self):
            scription.raw_input = self
            return self
        def __exit__(self, *args):
            scription.raw_input = raw_input
            return

    def test_yesno(self):
        for reply in ('y', 'Y', 'yes', 'Yes', 'YeS', 'YES', 't', 'trUE'):
            with self.raw_input_cm(reply):
                ans = get_response('Having fun?')
            self.assertTrue(ans)
        for reply in ('n', 'N', 'no', 'No', 'NO', 'f', 'fAlSe'):
            with self.raw_input_cm(reply):
                ans = get_response('Wanna quit?')
            self.assertFalse(ans)

    def test_multiple_choice_in_many_blocks(self):
        for reply in ('y', 'yes', 'Yes'):
            with self.raw_input_cm(reply):
                ans = get_response('copy files? [y]es/[n]o/[a]ll/[m]aybe')
                self.assertEqual(ans, 'yes')
        for reply in ('n', 'no', 'No'):
            with self.raw_input_cm(reply):
                ans = get_response('copy files? [y]es/[n]o/[a]ll/[m]aybe')
                self.assertEqual(ans, 'no')
        for reply in ('a', 'all', 'All'):
            with self.raw_input_cm(reply):
                ans = get_response('copy files? [y]es/[n]o/[a]ll/[m]aybe')
                self.assertEqual(ans, 'all')
        for reply in ('m', 'maybe', 'MayBe'):
            with self.raw_input_cm(reply) as ric:
                ans = get_response('copy files? [y]es/[n]o/[a]ll/[m]aybe')
                self.assertEqual(ans, 'maybe')
                self.assertEqual(ric.prompt, 'copy files? [y]es/[n]o/[a]ll/[m]aybe ')

    def test_multiple_choice_in_one_block(self):
        for reply in ('y', 'yes', 'Yes'):
            with self.raw_input_cm(reply):
                ans = get_response('copy files? [Yes/no/all/maybe]')
                self.assertEqual(ans, 'yes')
        for reply in ('n', 'no', 'No'):
            with self.raw_input_cm(reply) as ric:
                ans = get_response('copy files? [Yes/No/All/maYbe]')
                self.assertEqual(ans, 'no')
                self.assertEqual(ric.prompt, 'copy files? [Yes/No/All/maYbe] ')
        for reply in ('a', 'all', 'All'):
            with self.raw_input_cm(reply):
                ans = get_response('copy files? [yes/no/All/maybe]')
                self.assertEqual(ans, 'all')
        for reply in ('m', 'maybe', 'MayBe'):
            with self.raw_input_cm(reply):
                ans = get_response('copy files? [yes/no/all/maybe]')
                self.assertEqual(ans, 'maybe')

    def test_anything_goes(self):
        for reply in ('17', 'me', 'Right!'):
            with self.raw_input_cm(reply):
                ans = get_response('gimme sum data!')
                self.assertEqual(ans, reply)

    def test_default_yesno(self):
        for default in ('y', 'Y', 'yes', 'Yes', 'YeS', 'YES', 't', 'trUE'):
            with self.raw_input_cm(reply=''):
                ans = get_response('Having fun?', default=default)
            self.assertTrue(ans)
        for default in ('n', 'N', 'no', 'No', 'NO', 'f', 'fAlSe'):
            with self.raw_input_cm(reply=''):
                ans = get_response('Wanna quit?', default=default)
            self.assertFalse(ans)

    def test_default_multiple_choice_in_one_block(self):
        for default, output in (
                ('yes', 'copy files? [-yes-/no/all/maybe] '),
                ('no', 'copy files? [yes/-no-/all/maybe] '),
                ('all', 'copy files? [yes/no/-all-/maybe] '),
                ('maybe', 'copy files? [yes/no/all/-maybe-] '),
                ):
            with self.raw_input_cm(reply='') as ri:
                ans = get_response('copy files? [yes/no/all/maybe]', default=default)
                self.assertEqual(ans, default)
                self.assertEqual(output, ri.prompt)

    def test_default_multiple_choice_in_multiple_blocks(self):
        for default, result, output in (
                ('y', 'yes', 'copy files? [Y]es/[no]/[a]ll/[may]be '),
                ('no', 'no', 'copy files? [y]es/[NO]/[a]ll/[may]be '),
                ('a', 'all', 'copy files? [y]es/[no]/[A]ll/[may]be '),
                ('may', 'maybe', 'copy files? [y]es/[no]/[a]ll/[MAY]be '),
                ):
            with self.raw_input_cm(reply='') as ri:
                ans = get_response('copy files? [y]es/[no]/[a]ll/[may]be', default=default)
                self.assertEqual(ans, result)
                self.assertEqual(output, ri.prompt)


class TestExecutionThreads(TestCase):
    "Testing thread generation and reaping"

    template = (
            "from __future__ import print_function\n"
            "import sys\n"
            "sys.path.insert(0, %r)\n"
            "try:\n"
            "    raw_input\n"
            "except NameError:\n"
            "    raw_input = input\n"
            "\n"
            "%s\n"
            # "\n"
            # "Main()"
            )

    def write_script(self, script):
        target_dir = os.path.join(os.getcwd(), os.path.split(os.path.split(scription.__file__)[0])[0])
        file_path = os.path.join(tempdir, 'test_threads')
        file = open(file_path, 'w')
        try:
            file.write(self.template % (target_dir, script))
            return file_path
        finally:
            file.close()

    def test_noninteractive_process(self):
        thread_count = threading.active_count()
        job = Execute('ls -lad', pty=False)
        self.assertEqual(thread_count, threading.active_count())
        self.assertEqual(job.returncode, 0, '\n"ls -lad"\n-- stdout --\n%s\n-- stderr --\n%s' % (job.stdout, job.stderr))

    def test_noninteractive_pty(self):
        thread_count = threading.active_count()
        job = Execute('ls -lad', pty=True)
        self.assertEqual(thread_count, threading.active_count())
        self.assertEqual(job.returncode, 0, 'ls -lad:\n-- stdout --\n%s\n-- stderr --\n%s' % (job.stdout, job.stderr))

    def test_interactive_process(self):
        thread_count = threading.active_count()
        test_file = self.write_script('print(raw_input("howdy! "))')
        job = Execute([sys.executable, test_file], pty=False, timeout=300, input='Bye!\n')
        self.assertEqual(thread_count, threading.active_count())
        self.assertEqual(job.stdout.strip(), 'howdy! Bye!', '\n out: %r\n err: %r' % (job.stdout, job.stderr))
        self.assertEqual(job.returncode, 0, '-- stdout --\n%s\n-- stderr --\n%s' % (job.stdout, job.stderr))

    def test_interactive_pty(self):
        thread_count = threading.active_count()
        test_file = self.write_script(
                '''from getpass import getpass\n'''
                '''print(getpass('howdy!'))\n'''
                )
        job = Execute([sys.executable, test_file], pty=True, timeout=600, password='Bye!')
        self.assertEqual(thread_count, threading.active_count())
        self.assertEqual(job.stdout.strip().replace('\n', ' '), 'howdy! Bye!', '\n out: %r\n err: %r' % (job.stdout, job.stderr))
        self.assertEqual(job.returncode, 0, '-- stdout --\n%s\n-- stderr --\n%s' % (job.stdout, job.stderr))

    def test_killed_process(self):
        thread_count = threading.active_count()
        test_file = self.write_script(
                '''import time\n'''
                '''time.sleep(5)\n'''
                )
        job = Job([sys.executable, test_file], pty=False)
        self.assertRaises(
                TimeoutError,
                job.communicate,
                timeout=3,
                )
        self.assertEqual(thread_count, threading.active_count())
        self.assertEqual(job.stderr.strip(), 'TIMEOUT: process failed to complete in 3 seconds', '\n out: %r\n err: %r' % (job.stdout, job.stderr))
        self.assertNotEqual(job.returncode, 0, '-- stdout --\n%s\n-- stderr --\n%s' % (job.stdout, job.stderr))

    def test_killed_pty(self):
        thread_count = threading.active_count()
        test_file = self.write_script(
                '''import time\n'''
                '''time.sleep(5)\n'''
                )
        job = Job([sys.executable, test_file], pty=True)
        self.assertRaises(
                TimeoutError,
                job.communicate,
                timeout=3,
                )
        self.assertEqual(thread_count, threading.active_count())
        self.assertEqual(
                job.stderr.strip(),
                'TIMEOUT: process failed to complete in 3 seconds',
                '\n out: %r\n err: %r' % (job.stdout, job.stderr),
                )
        self.assertNotEqual(job.returncode, 0, '-- stdout --\n%s\n-- stderr --\n%s' % (job.stdout, job.stderr))

    def test_died_process(self):
        thread_count = threading.active_count()
        test_file = self.write_script(
                '''import time\n'''
                '''def hello(x\n'''
                '''time.sleep(5)\n'''
                )
        job = Execute([sys.executable, test_file], pty=False, timeout=3)
        self.assertEqual(thread_count, threading.active_count())
        self.assertTrue('TIMEOUT: process failed to complete in 3 seconds' not in job.stdout)
        self.assertNotEqual(job.returncode, 0, '-- stdout --\n%s\n-- stderr --\n%s' % (job.stdout, job.stderr))

    def test_died_pty(self):
        thread_count = threading.active_count()
        test_file = self.write_script(
                '''import time\n'''
                '''time.sleep(600)\n'''
                )
        job = Job([sys.executable, test_file], pty=True)
        self.assertRaises(TimeoutError, job.communicate, timeout=3)
        self.assertEqual(thread_count, threading.active_count())
        self.assertTrue('TIMEOUT: process failed to complete in 3 seconds' not in job.stdout)
        self.assertNotEqual(job.returncode, 0, '-- stdout --\n%s\n-- stderr --\n%s' % (job.stdout, job.stderr))


class TestEnums(TestCase):

    def test_color_bitwise_or(self):
        C = scription.Color
        red, white = C.FG_Red, C.BG_White
        # error(red, type(red), repr(red.value), repr(red.code))
        # error(white, type(white), repr(white.value), repr(white.code))
        # error(white.value | red.value)
        barber = red | white
        new_value = '\x1b[31;47m'
        self.assertEqual(barber, new_value, "%r != %r" % (str(barber), new_value))
        self.assertEqual(barber.value, red.value | white.value)
        self.assertEqual(barber.code, ';'.join([red.code, white.code]))
        self.assertEqual(repr(barber), '<Color: FG_Red|BG_White>')
        self.assertEqual(str(barber), new_value)

    def test_docenum(self):
        from scription import SpecKind
        self.assertEqual(SpecKind.REQUIRED.value, 'required')
        self.assertEqual(SpecKind.FLAG._name_, 'FLAG')
        self.assertEqual(SpecKind.MULTI.__doc__, 'multiple values per name (list form, no whitespace)')


class TestBox(TestCase):

    def test_flag(self):
        self.assertEqual(
                box('hello', 'flag'),
                "--------\n"
                "| hello \n"
                "--------",
                )
        self.assertEqual(
                box('hello\nworld', 'flag'),
                "--------\n"
                "| hello \n"
                "| world \n"
                "--------",
                )
        self.assertEqual(
                box('hello\nworlds', 'flag'),
                "---------\n"
                "| hello  \n"
                "| worlds \n"
                "---------",
                )

    def test_box(self):
        self.assertEqual(
                box('hello', 'box'),
                dedent('''\
                        ---------
                        | hello |
                        ---------'''),
                )
        self.assertEqual(
                box('hello\nworld', 'box'),
                dedent('''\
                        ---------
                        | hello |
                        | world |
                        ---------'''),
                )
        self.assertEqual(
                box('hello\nworlds', 'box'),
                dedent('''\
                        ----------
                        | hello  |
                        | worlds |
                        ----------'''),
                )

    def test_fancy_box(self):
        self.assertEqual(
                box('a very fancy box', 'box', '* *', '**'),
                dedent('''\
                        * ** ** ** ** ** ** **
                        ** a very fancy box **
                        * ** ** ** ** ** ** **'''),
                )

    def test_overline(self):
        self.assertEqual(
                box('hello', 'overline'),
                dedent('''\
                        -----
                        hello'''),
                )
        self.assertEqual(
                box('hello\nworld', 'overline'),
                dedent('''\
                        -----
                        hello
                        world'''),
                )
        self.assertEqual(
                box('hello\nworlds', 'overline'),
                "------\n"
                "hello \n"
                "worlds",
                )

    def test_underline(self):
        self.assertEqual(
                box('hello', 'underline'),
                dedent('''\
                          hello
                          -----'''),
                )
        self.assertEqual(
                box('hello\nworld', 'underline'),
                dedent('''\
                          hello
                          world
                          -----'''),
                )
        self.assertEqual(
                box('hello\nworlds', 'underline'),
                "hello \n"
                "worlds\n"
                "------",
                )

    def test_lined(self):
        self.assertEqual(
                box('hello', 'lined'),
                dedent('''\
                          -----
                          hello
                          -----'''),
                )
        self.assertEqual(
                box('hello\nworld', 'lined'),
                dedent('''\
                          -----
                          hello
                          world
                          -----'''),
                )
        self.assertEqual(
                box('hello\nworlds', 'lined'),
                "------\n"
                "hello \n"
                "worlds\n"
                "------",
                )


class TestTable(TestCase):
    maxDiff = None

    def test_header_separation(self):
        rows = (
            ('id', 'name', 'age', 'income', 'married'),
            None,
            (1, 'Ethan', 33, 134000, True),
            (2, 'Allen', 49, 67500, False),
            (3, 'Bartholomew', 11, 67, False),
            (4, 'Ed', 101, 0, True),
            )
        should_be = dedent("""\
                ---------------------------------------------
                | id | name        | age | income | married |
                | -- | ----------- | --- | ------ | ------- |
                |  1 | Ethan       |  33 | 134000 |    T    |
                |  2 | Allen       |  49 |  67500 |    f    |
                |  3 | Bartholomew |  11 |     67 |    f    |
                |  4 | Ed          | 101 |      0 |    T    |
                ---------------------------------------------
                """)
        buffer = StringIO()
        echo(rows, border='table', file=buffer)
        self.assertEqual(buffer.getvalue(), should_be, '\n%s\n%s' % (buffer.getvalue(), should_be))

    def test_explicit_table_size(self):
        rows = [
                ('header1', 'header2', 'header3'),
                None,
                (None, 'data 2\ndata 3', 'data 4\ndata 5'),
                '-',
                'a bunch of text, like a lot',
                '-',
                ('data 6', 'data 7', 'data 8'),
                ]
        buffer = StringIO()
        echo(rows, border='table', table_specs=(('','',''),(10, 7, 13)), table_display_none='x', file=buffer)
        self.assertEqual(
                buffer.getvalue(),
                dedent('''\
                    ----------------------------------------
                    | header1    | header2 | header3       |
                    | ---------- | ------- | ------------- |
                    |    xxxx    | data 2  | data 4        |
                    |            | data 3  | data 5        |
                    | ------------------------------------ |
                    | a bunch of text, like a lot          |
                    | ------------------------------------ |
                    | data 6     | data 7  | data 8        |
                    ----------------------------------------
                    '''),
                )

    def test_explicit_table_by_table(self):
        rows = [
                ('header1', 'header2', 'header3'),
                None,
                (None, 'data 2\ndata 3', 'data 4\ndata 5'),
                '-',
                'a bunch of text, like a lot',
                '-',
                ('data 6', 'data 7', 'data 8'),
                ]
        buffer = StringIO()
        echo(table_display(rows , types=('','',''), widths=(10, 7, 13), display_none='x'), file=buffer)
        actual = buffer.getvalue()
        expected = dedent('''\
                    ----------------------------------------
                    | header1    | header2 | header3       |
                    | ---------- | ------- | ------------- |
                    |    xxxx    | data 2  | data 4        |
                    |            | data 3  | data 5        |
                    | ------------------------------------ |
                    | a bunch of text, like a lot          |
                    | ------------------------------------ |
                    | data 6     | data 7  | data 8        |
                    ----------------------------------------
                    ''')
        self.assertEqual(actual, expected, '%s\n%s' % (actual, expected))

    def test_multiple_internal_lines_in_last_row(self):
        rows = [
                ('header1', 'header2', 'header3'),
                None,
                ('data 1', 'data 2', 'data 3\ndata 4'),
                ('data 5', 'data 6', 'data 7'),
                ]
        buffer = StringIO()
        echo(rows, border='table', file=buffer)
        self.assertEqual(
                buffer.getvalue(),
                dedent('''\
                    -------------------------------
                    | header1 | header2 | header3 |
                    | ------- | ------- | ------- |
                    | data 1  | data 2  | data 3  |
                    |         |         | data 4  |
                    | data 5  | data 6  | data 7  |
                    -------------------------------
                    '''),
                )

    def test_multiple_internal_lines_in_middle_row(self):
        rows = [
                ('header1', 'header2', 'header3'),
                None,
                ('data 1', 'data 2\ndata 3', 'data 4'),
                ('data 5', 'data 6', 'data 7'),
                ]
        buffer = StringIO()
        echo(rows, border='table', file=buffer)
        self.assertEqual(
                buffer.getvalue(),
                dedent('''\
                    -------------------------------
                    | header1 | header2 | header3 |
                    | ------- | ------- | ------- |
                    | data 1  | data 2  | data 4  |
                    |         | data 3  |         |
                    | data 5  | data 6  | data 7  |
                    -------------------------------
                    '''),
                )

    def test_multiple_internal_lines_in_middle_and_last_row(self):
        rows = [
                ('header1', 'header2', 'header3'),
                None,
                ('data 1', 'data 2\ndata 3', 'data 4\ndata 5'),
                ('data 6', 'data 7', 'data 8'),
                ]
        buffer = StringIO()
        echo(rows, border='table', file=buffer)
        self.assertEqual(
                buffer.getvalue(),
                dedent('''\
                    -------------------------------
                    | header1 | header2 | header3 |
                    | ------- | ------- | ------- |
                    | data 1  | data 2  | data 4  |
                    |         | data 3  | data 5  |
                    | data 6  | data 7  | data 8  |
                    -------------------------------
                    '''),
                )

    def test_entire_joined_short_row(self):
        rows = [
                ('header1', 'header2', 'header3'),
                None,
                ('data 1', 'data 2\ndata 3', 'data 4\ndata 5'),
                'some text',
                ('data 6', 'data 7', 'data 8'),
                ]
        buffer = StringIO()
        echo(rows, border='table', file=buffer)
        self.assertEqual(
                buffer.getvalue(),
                dedent('''\
                    -------------------------------
                    | header1 | header2 | header3 |
                    | ------- | ------- | ------- |
                    | data 1  | data 2  | data 4  |
                    |         | data 3  | data 5  |
                    | some text                   |
                    | data 6  | data 7  | data 8  |
                    -------------------------------
                    '''),
                )

    def test_entire_joined_fitting_row(self):
        rows = [
                ('header1', 'header2', 'header3'),
                None,
                ('data 1', 'data 2\ndata 3', 'data 4\ndata 5'),
                'a bunch of text, like a lot',
                ('data 6', 'data 7', 'data 8'),
                ]
        buffer = StringIO()
        echo(rows, border='table', file=buffer)
        self.assertEqual(
                buffer.getvalue(),
                dedent('''\
                    -------------------------------
                    | header1 | header2 | header3 |
                    | ------- | ------- | ------- |
                    | data 1  | data 2  | data 4  |
                    |         | data 3  | data 5  |
                    | a bunch of text, like a lot |
                    | data 6  | data 7  | data 8  |
                    -------------------------------
                    '''),
                )

    def test_entire_joined_too_big_exact_row(self):
        rows = [
                ('header1', 'header2', 'header3'),
                None,
                ('data 1', 'data 2\ndata 3', 'data 4\ndata 5'),
                'a bunch of text, like a big bunch of real lot',
                ('data 6', 'data 7', 'data 8'),
                ]
        buffer = StringIO()
        echo(rows, border='table', file=buffer)
        self.assertEqual(
                buffer.getvalue(),
                dedent('''\
                    -------------------------------
                    | header1 | header2 | header3 |
                    | ------- | ------- | ------- |
                    | data 1  | data 2  | data 4  |
                    |         | data 3  | data 5  |
                    | a bunch of text, like a big |
                    | bunch of real lot           |
                    | data 6  | data 7  | data 8  |
                    -------------------------------
                    '''),
                )

    def test_entire_joined_too_big_row(self):
        rows = [
                ('header1', 'header2', 'header3'),
                None,
                ('data 1', 'data 2\ndata 3', 'data 4\ndata 5'),
                'a bunch of text, like a real lot',
                ('data 6', 'data 7', 'data 8'),
                ]
        buffer = StringIO()
        echo(rows, border='table', file=buffer)
        self.assertEqual(
                buffer.getvalue(),
                dedent('''\
                    -------------------------------
                    | header1 | header2 | header3 |
                    | ------- | ------- | ------- |
                    | data 1  | data 2  | data 4  |
                    |         | data 3  | data 5  |
                    | a bunch of text, like a     |
                    | real lot                    |
                    | data 6  | data 7  | data 8  |
                    -------------------------------
                    '''),
                )

    def test_entire_joined_row_top_line(self):
        rows = [
                ('header1', 'header2', 'header3'),
                None,
                ('data 1', 'data 2\ndata 3', 'data 4\ndata 5'),
                '=',
                'a bunch of text, like a lot',
                ('data 6', 'data 7', 'data 8'),
                ]
        buffer = StringIO()
        echo(rows, border='table', file=buffer)
        self.assertEqual(
                buffer.getvalue(),
                dedent('''\
                    -------------------------------
                    | header1 | header2 | header3 |
                    | ------- | ------- | ------- |
                    | data 1  | data 2  | data 4  |
                    |         | data 3  | data 5  |
                    | =========================== |
                    | a bunch of text, like a lot |
                    | data 6  | data 7  | data 8  |
                    -------------------------------
                    '''),
                )

    def test_entire_joined_row_bottom_line(self):
        rows = [
                ('header1', 'header2', 'header3'),
                None,
                ('data 1', 'data 2\ndata 3', 'data 4\ndata 5'),
                ' ',
                'a bunch of text, like a lot',
                '-',
                ('data 6', 'data 7', 'data 8'),
                ]
        buffer = StringIO()
        echo(rows, border='table', file=buffer)
        self.assertEqual(
                buffer.getvalue(),
                dedent('''\
                    -------------------------------
                    | header1 | header2 | header3 |
                    | ------- | ------- | ------- |
                    | data 1  | data 2  | data 4  |
                    |         | data 3  | data 5  |
                    |                             |
                    | a bunch of text, like a lot |
                    | --------------------------- |
                    | data 6  | data 7  | data 8  |
                    -------------------------------
                    '''),
                )

    def test_entire_joined_row_top_bottom_line(self):
        rows = [
                ('header1', 'header2', 'header3'),
                None,
                ('data 1', 'data 2\ndata 3', 'data 4\ndata 5'),
                '-',
                'a bunch of text, like a lot',
                '-',
                ('data 6', 'data 7', 'data 8'),
                ]
        buffer = StringIO()
        echo(rows, border='table', file=buffer)
        self.assertEqual(
                buffer.getvalue(),
                dedent('''\
                    -------------------------------
                    | header1 | header2 | header3 |
                    | ------- | ------- | ------- |
                    | data 1  | data 2  | data 4  |
                    |         | data 3  | data 5  |
                    | --------------------------- |
                    | a bunch of text, like a lot |
                    | --------------------------- |
                    | data 6  | data 7  | data 8  |
                    -------------------------------
                    '''),
                )

    def test_none_in_row_default(self):
        rows = [
                ('header1', 'header2', 'header3'),
                None,
                (None, 'data 2\ndata 3', 'data 4\ndata 5'),
                '-',
                'a bunch of text, like a lot',
                '-',
                ('data 6', 'data 7', 'data 8'),
                ]
        buffer = StringIO()
        echo(rows, border='table', table_display_none='x', file=buffer)
        self.assertEqual(
                buffer.getvalue(),
                dedent('''\
                    -------------------------------
                    | header1 | header2 | header3 |
                    | ------- | ------- | ------- |
                    |   xxx   | data 2  | data 4  |
                    |         | data 3  | data 5  |
                    | --------------------------- |
                    | a bunch of text, like a lot |
                    | --------------------------- |
                    | data 6  | data 7  | data 8  |
                    -------------------------------
                    '''),
                )

    def test_none_in_row_none(self):
        rows = [
                ('header1', 'header2', 'header3'),
                None,
                (None, 'data 2\ndata 3', 'data 4\ndata 5'),
                '-',
                'a bunch of text, like a lot',
                '-',
                ('data 6', 'data 7', 'data 8'),
                ]
        buffer = StringIO()
        echo(rows, border='table', table_display_none='-none-', file=buffer)
        self.assertEqual(
                buffer.getvalue(),
                dedent('''\
                    -------------------------------
                    | header1 | header2 | header3 |
                    | ------- | ------- | ------- |
                    |  -none- | data 2  | data 4  |
                    |         | data 3  | data 5  |
                    | --------------------------- |
                    | a bunch of text, like a lot |
                    | --------------------------- |
                    | data 6  | data 7  | data 8  |
                    -------------------------------
                    '''),
                )

    def test_none_in_row_small_column(self):
        rows = [
                ('h1', 'header2', 'header3'),
                None,
                (None, 'data 2\ndata 3', 'data 4\ndata 5'),
                '-',
                'a bunch of text, like a lot',
                '-',
                ('dat', 'data 7', 'data 8'),
                ]
        buffer = StringIO()
        echo(rows, border='table', table_display_none='!', file=buffer)
        self.assertEqual(
                buffer.getvalue(),
                dedent('''\
                    ---------------------------
                    | h1  | header2 | header3 |
                    | --- | ------- | ------- |
                    |  !  | data 2  | data 4  |
                    |     | data 3  | data 5  |
                    | ----------------------- |
                    | a bunch of text, like a |
                    | lot                     |
                    | ----------------------- |
                    | dat | data 7  | data 8  |
                    ---------------------------
                    '''),
                )

    def test_none_in_row_smaller_column(self):
        rows = [
                ('h1', 'header2', 'header3'),
                None,
                (None, 'data 2\ndata 3', 'data 4\ndata 5'),
                '-',
                'a bunch of text, like a lot',
                '-',
                ('da', 'data 7', 'data 8'),
                ]
        buffer = StringIO()
        echo(rows, border='table', table_display_none='!', file=buffer)
        self.assertEqual(
                buffer.getvalue(),
                dedent('''\
                    --------------------------
                    | h1 | header2 | header3 |
                    | -- | ------- | ------- |
                    | !! | data 2  | data 4  |
                    |    | data 3  | data 5  |
                    | ---------------------- |
                    | a bunch of text, like  |
                    | a lot                  |
                    | ---------------------- |
                    | da | data 7  | data 8  |
                    --------------------------
                    '''),
                )

    def test_none_in_row_smallest_column(self):
        rows = [
                ('h', 'header2', 'header3'),
                None,
                (None, 'data 2\ndata 3', 'data 4\ndata 5'),
                '-',
                'a bunch of text, like a lot',
                '-',
                ('d', 'data 7', 'data 8'),
                ]
        buffer = StringIO()
        echo(rows, border='table', table_display_none='!', file=buffer)
        self.maxDiff = None
        self.assertEqual(
                buffer.getvalue(),
                dedent('''\
                    -------------------------
                    | h | header2 | header3 |
                    | - | ------- | ------- |
                    | ! | data 2  | data 4  |
                    |   | data 3  | data 5  |
                    | --------------------- |
                    | a bunch of text, like |
                    | a lot                 |
                    | --------------------- |
                    | d | data 7  | data 8  |
                    -------------------------
                    '''),
                )

    def test_number_in_column(self):
        rows = [
                ('first', 'second', 'third'),
                None,
                (1, 2.0, 3.14285714),
                (0.68421062631, 777, 3.14),
                ]
        buffer = StringIO()
        echo(rows, border='table', file=buffer)
        self.maxDiff = None
        self.assertEqual(
                buffer.getvalue(),
                dedent('''\
                    ---------------------------------------
                    |         first | second |      third |
                    | ------------- | ------ | ---------- |
                    |             1 |    2.0 | 3.14285714 |
                    | 0.68421062631 |    777 |       3.14 |
                    ---------------------------------------
                    '''),
                )

    def test_naive_datetime_in_column(self):
        rows = [
                ('name', 'date', 'passed', 'score'),
                None,
                ('Ethianski', datetime.datetime(1970, 5, 20, 7, 47, 32), True, 93),
                ('Alexis', datetime.datetime(2001, 7, 4, 13, 39, 1), False, 26),
                ('Vinni', datetime.datetime(2012, 1, 31, 3, 45, 59), False, 47),
                ]
        buffer = StringIO()
        echo(rows, border='table', file=buffer)
        self.maxDiff = None
        self.assertEqual(
                buffer.getvalue(),
                dedent('''\
                    ----------------------------------------------------
                    | name      |        date         | passed | score |
                    | --------- | ------------------- | ------ | ----- |
                    | Ethianski | 1970-05-20 07:47:32 |   T    |    93 |
                    | Alexis    | 2001-07-04 13:39:01 |   f    |    26 |
                    | Vinni     | 2012-01-31 03:45:59 |   f    |    47 |
                    ----------------------------------------------------
                    '''),
                )

    def test_aware_datetime_in_column(self):
        rows = [
                ('name', 'date', 'passed', 'score'),
                None,
                ('Ethianski', datetime.datetime(1970, 5, 20, 7, 47, 32, tzinfo=UTC), True, 93),
                ('Alexis', datetime.datetime(2001, 7, 4, 13, 39, 1, tzinfo=UTC), False, 26),
                ('Vinni', datetime.datetime(2012, 1, 31, 3, 45, 59), False, 47),
                ]
        buffer = StringIO()
        echo(rows, border='table', file=buffer, table_display_tz=True)
        self.maxDiff = None
        self.assertEqual(
                buffer.getvalue(),
                dedent('''\
                    ----------------------------------------------------------
                    | name      |           date            | passed | score |
                    | --------- | ------------------------- | ------ | ----- |
                    | Ethianski | 1970-05-20 07:47:32 +0000 |   T    |    93 |
                    | Alexis    | 2001-07-04 13:39:01 +0000 |   f    |    26 |
                    | Vinni     | 2012-01-31 03:45:59 <unk> |   f    |    47 |
                    ----------------------------------------------------------
                    '''),
                )

    def test_naive_time_in_column(self):
        rows = [
                ('name', 'time', 'passed', 'score'),
                None,
                ('Ethianski', datetime.time(7, 47, 32), True, 93),
                ('Alexis', datetime.time(13, 39, 1), False, 26),
                ('Vinni', datetime.time(3, 45, 59), False, 47),
                ]
        buffer = StringIO()
        echo(rows, border='table', file=buffer)
        self.maxDiff = None
        self.assertEqual(
                buffer.getvalue(),
                dedent('''\
                    -----------------------------------------
                    | name      |   time   | passed | score |
                    | --------- | -------- | ------ | ----- |
                    | Ethianski | 07:47:32 |   T    |    93 |
                    | Alexis    | 13:39:01 |   f    |    26 |
                    | Vinni     | 03:45:59 |   f    |    47 |
                    -----------------------------------------
                    '''),
                )

    def test_aware_time_in_column(self):
        rows = [
                ('name', 'time', 'passed', 'score'),
                None,
                ('Ethianski', datetime.time(7, 47, 32, tzinfo=UTC), True, 93),
                ('Alexis', datetime.time(13, 39, 1, tzinfo=UTC), False, 26),
                ('Vinni', datetime.time(3, 45, 59), False, 47),
                ]
        buffer = StringIO()
        echo(rows, border='table', file=buffer, table_display_tz=True)
        self.maxDiff = None
        self.assertEqual(
                buffer.getvalue(),
                dedent('''\
                    -----------------------------------------------
                    | name      |      time      | passed | score |
                    | --------- | -------------- | ------ | ----- |
                    | Ethianski | 07:47:32 +0000 |   T    |    93 |
                    | Alexis    | 13:39:01 +0000 |   f    |    26 |
                    | Vinni     | 03:45:59 <unk> |   f    |    47 |
                    -----------------------------------------------
                    '''),
                )

    def test_date_in_column(self):
        rows = [
                ('name', 'date', 'passed', 'score'),
                None,
                ('Ethianski', datetime.date(2009, 11, 24), True, 93),
                ('Alexis', datetime.date(2015, 3, 15), False, 26),
                ('Vinni', datetime.date(2021, 7, 31), False, 47),
                ]
        buffer = StringIO()
        echo(rows, border='table', file=buffer, table_display_tz=True)
        self.maxDiff = None
        self.assertEqual(
                buffer.getvalue(),
                dedent('''\
                    -------------------------------------------
                    | name      |    date    | passed | score |
                    | --------- | ---------- | ------ | ----- |
                    | Ethianski | 2009-11-24 |   T    |    93 |
                    | Alexis    | 2015-03-15 |   f    |    26 |
                    | Vinni     | 2021-07-31 |   f    |    47 |
                    -------------------------------------------
                    '''),
                )


if not is_win:
    @skipUnless(INCLUDE_SLOW, 'skipping slow tests')
    class TestExecutionPtys(TestCase):
        "test interaction with ptys"

        ok = True

        @classmethod
        def setUpClass(cls, *args, **kwds):
            super(TestExecutionPtys, cls).setUpClass(*args, **kwds)
            with open('/proc/sys/kernel/pty/max') as pty_num:
                cls.total_pty = int(pty_num.read())

        def skipIfPointless(func):
            @functools.wraps(func)
            def check_if_pointless(self, *args, **kwds):
                if self.ok:
                    try:
                        return func(self, *args, **kwds)
                    except OSError:
                        _, exc, _ = sys.exc_info()
                        if 'out of pty devices' in str(exc):
                            self.__class__.ok = False
                        raise
                else:
                    raise SkipTest('all ptys have been used')
            return check_if_pointless

        @skipIfPointless
        def test_00_pty_acquire_and_release(self):
            "use all ptys, release all, use again"
            used = []
            for i in range(self.total_pty):
                try:
                    pid, fd = pty.fork()
                except OSError:
                    break
                else:
                    if pid == 0:
                        # child
                        time.sleep(60)
                        os._exit(0)
                    used.append(fd)
            for fd in used:
                os.close(fd)
            used[:] = []
            pid, fd = pty.fork()
            if pid == 0:
                os._exit(0)
            os.close(fd)

        @skipIfPointless
        def test_01_finished_pty(self):
            "finished ptys don't leave dangling pipes"
            for i in range(self.total_pty + 100):
                Execute('bash -c exit', pty=True)

        @skipIfPointless
        def test_errored_pty(self):
            "errored ptys don't leave dangling pipes"
            for i in range(self.total_pty + 100):
                Execute('bashh -c exit', pty=True)

        del skipIfPointless


class TestTrivalent(TestCase):
    "Testing Trivalent"

    def test_unknown(self):
        "Unknown"
        for unk in '', '?', ' ', None, Unknown, 0, empty:
            huh = Trivalent(unk)
            self.assertEqual(huh == None, True, "huh is %r from %r, which is not None" % (huh, unk))
            self.assertEqual(huh != None, False, "huh is %r from %r, which is not None" % (huh, unk))
            self.assertEqual(huh != True, True, "huh is %r from %r, which is not None" % (huh, unk))
            self.assertEqual(huh == True, False, "huh is %r from %r, which is not None" % (huh, unk))
            self.assertEqual(huh != False, True, "huh is %r from %r, which is not None" % (huh, unk))
            self.assertEqual(huh == False, False, "huh is %r from %r, which is not None" % (huh, unk))
            self.assertEqual((0, 1, -1)[huh], 0)
        self.assertRaises(ValueError, bool, huh)

    def test_true(self):
        "true"
        for true in 'True', 'yes', 't', 'Y', True, 1:
            huh = Trivalent(true)
            self.assertEqual(huh == True, True)
            self.assertEqual(huh != True, False)
            self.assertEqual(huh == False, False, "%r is not True" % true)
            self.assertEqual(huh != False, True)
            self.assertEqual(huh == None, False)
            self.assertEqual(huh != None, True)
            if pyver >= PY25:
                self.assertEqual((0, 1, -1)[huh], 1)
        self.assertTrue(bool(true))

    def test_false(self):
        "false"
        for false in 'false', 'No', 'F', 'n', -1, False:
            huh = Trivalent(false)
            self.assertEqual(huh != False, False)
            self.assertEqual(huh == False, True)
            self.assertEqual(huh != True, True)
            self.assertEqual(huh == True, False)
            self.assertEqual(huh != None, True)
            self.assertEqual(huh == None, False)
            if pyver >= PY25:
                self.assertEqual((0, 1, -1)[huh], -1)
        self.assertFalse(bool(false))

    def test_singletons(self):
        "singletons"
        heh = Trivalent(True)
        hah = Trivalent('Yes')
        ick = Trivalent(False)
        ack = Trivalent(-1)
        bla = Trivalent(None)
        unk = Trivalent('?')
        self.assertEqual(heh is hah, True)
        self.assertEqual(ick is ack, True)
        self.assertEqual(unk is bla, True)

    def test_error(self):
        "errors"
        self.assertRaises(ValueError, Trivalent, 'wrong')
        self.assertRaises(ValueError, Trivalent, [])

    def test_and(self):
        "and"
        true = Trivalent(True)
        false = Trivalent(False)
        unknown = Trivalent(None)
        self.assertEqual((true & true) is true, True)
        self.assertEqual((true & false) is false, True)
        self.assertEqual((false & true) is false, True)
        self.assertEqual((false & false) is false, True)
        self.assertEqual((true & unknown) is unknown, True)
        self.assertEqual((false & unknown) is false, True)
        self.assertEqual((unknown & true) is unknown, True)
        self.assertEqual((unknown & false) is false, True)
        self.assertEqual((unknown & unknown) is unknown, True)
        self.assertEqual((true & True) is true, True)
        self.assertEqual((true & False) is false, True)
        self.assertEqual((false & True) is false, True)
        self.assertEqual((false & False) is false, True)
        self.assertEqual((true & None) is unknown, True)
        self.assertEqual((false & None) is false, True)
        self.assertEqual((unknown & True) is unknown, True)
        self.assertEqual((unknown & False) is false, True)
        self.assertEqual((unknown & None) is unknown, True)
        self.assertEqual((True & true) is true, True)
        self.assertEqual((True & false) is false, True)
        self.assertEqual((False & true) is false, True)
        self.assertEqual((False & false) is false, True)
        self.assertEqual((True & unknown) is unknown, True)
        self.assertEqual((False & unknown) is false, True)
        self.assertEqual((None & true) is unknown, True)
        self.assertEqual((None & false) is false, True)
        self.assertEqual((None & unknown) is unknown, True)
        t = true
        t &= true
        self.assertEqual(t is true, True)
        t = true
        t &= false
        self.assertEqual(t is false, True)
        f = false
        f &= true
        self.assertEqual(f is false, True)
        f = false
        f &= false
        self.assertEqual(f is false, True)
        t = true
        t &= unknown
        self.assertEqual(t is unknown, True)
        f = false
        f &= unknown
        self.assertEqual(f is false, True)
        u = unknown
        u &= true
        self.assertEqual(u is unknown, True)
        u = unknown
        u &= false
        self.assertEqual(u is false, True)
        u = unknown
        u &= unknown
        self.assertEqual(u is unknown, True)
        t = true
        t &= True
        self.assertEqual(t is true, True)
        t = true
        t &= False
        self.assertEqual(t is false, True)
        f = false
        f &= True
        self.assertEqual(f is false, True)
        f = false
        f &= False
        self.assertEqual(f is false, True)
        t = true
        t &= None
        self.assertEqual(t is unknown, True)
        f = false
        f &= None
        self.assertEqual(f is false, True)
        u = unknown
        u &= True
        self.assertEqual(u is unknown, True)
        u = unknown
        u &= False
        self.assertEqual(u is false, True)
        u = unknown
        u &= None
        self.assertEqual(u is unknown, True)
        t = True
        t &= true
        self.assertEqual(t is true, True)
        t = True
        t &= false
        self.assertEqual(t is false, True)
        f = False
        f &= true
        self.assertEqual(f is false, True)
        f = False
        f &= false
        self.assertEqual(f is false, True)
        t = True
        t &= unknown
        self.assertEqual(t is unknown, True)
        f = False
        f &= unknown
        self.assertEqual(f is false, True)
        u = None
        u &= true
        self.assertEqual(u is unknown, True)
        u = None
        u &= false
        self.assertEqual(u is false, True)
        u = None
        u &= unknown
        self.assertEqual(u is unknown, True)

    def test_or(self):
        "or"
        true = Trivalent(True)
        false = Trivalent(False)
        unknown = Trivalent(None)
        self.assertEqual((true | true) is true, True)
        self.assertEqual((true | false) is true, True)
        self.assertEqual((false | true) is true, True)
        self.assertEqual((false | false) is false, True)
        self.assertEqual((true | unknown) is true, True)
        self.assertEqual((false | unknown) is unknown, True)
        self.assertEqual((unknown | true) is true, True)
        self.assertEqual((unknown | false) is unknown, True)
        self.assertEqual((unknown | unknown) is unknown, True)
        self.assertEqual((true | True) is true, True)
        self.assertEqual((true | False) is true, True)
        self.assertEqual((false | True) is true, True)
        self.assertEqual((false | False) is false, True)
        self.assertEqual((true | None) is true, True)
        self.assertEqual((false | None) is unknown, True)
        self.assertEqual((unknown | True) is true, True)
        self.assertEqual((unknown | False) is unknown, True)
        self.assertEqual((unknown | None) is unknown, True)
        self.assertEqual((True | true) is true, True)
        self.assertEqual((True | false) is true, True)
        self.assertEqual((False | true) is true, True)
        self.assertEqual((False | false) is false, True)
        self.assertEqual((True | unknown) is true, True)
        self.assertEqual((False | unknown) is unknown, True)
        self.assertEqual((None | true) is true, True)
        self.assertEqual((None | false) is unknown, True)
        self.assertEqual((None | unknown) is unknown, True)
        t = true
        t |= true
        self.assertEqual(t is true, True)
        t = true
        t |= false
        self.assertEqual(t is true, True)
        f = false
        f |= true
        self.assertEqual(f is true, True)
        f = false
        f |= false
        self.assertEqual(f is false, True)
        t = true
        t |= unknown
        self.assertEqual(t is true, True)
        f = false
        f |= unknown
        self.assertEqual(f is unknown, True)
        u = unknown
        u |= true
        self.assertEqual(u is true, True)
        u = unknown
        u |= false
        self.assertEqual(u is unknown, True)
        u = unknown
        u |= unknown
        self.assertEqual(u is unknown, True)
        t = true
        t |= True
        self.assertEqual(t is true, True)
        t = true
        t |= False
        self.assertEqual(t is true, True)
        f = false
        f |= True
        self.assertEqual(f is true, True)
        f = false
        f |= False
        self.assertEqual(f is false, True)
        t = true
        t |= None
        self.assertEqual(t is true, True)
        f = false
        f |= None
        self.assertEqual(f is unknown, True)
        u = unknown
        u |= True
        self.assertEqual(u is true, True)
        u = unknown
        u |= False
        self.assertEqual(u is unknown, True)
        u = unknown
        u |= None
        self.assertEqual(u is unknown, True)
        t = True
        t |= true
        self.assertEqual(t is true, True)
        t = True
        t |= false
        self.assertEqual(t is true, True)
        f = False
        f |= true
        self.assertEqual(f is true, True)
        f = False
        f |= false
        self.assertEqual(f is false, True)
        t = True
        t |= unknown
        self.assertEqual(t is true, True)
        f = False
        f |= unknown
        self.assertEqual(f is unknown, True)
        u = None
        u |= true
        self.assertEqual(u is true, True)
        u = None
        u |= false
        self.assertEqual(u is unknown, True)
        u = None
        u |= unknown
        self.assertEqual(u is unknown, True)

    def test_xor(self):
        "xor"
        true = Trivalent(True)
        false = Trivalent(False)
        unknown = Trivalent(None)
        self.assertEqual((true ^ true) is false, True)
        self.assertEqual((true ^ false) is true, True)
        self.assertEqual((false ^ true) is true, True)
        self.assertEqual((false ^ false) is false, True)
        self.assertEqual((true ^ unknown) is unknown, True)
        self.assertEqual((false ^ unknown) is unknown, True)
        self.assertEqual((unknown ^ true) is unknown, True)
        self.assertEqual((unknown ^ false) is unknown, True)
        self.assertEqual((unknown ^ unknown) is unknown, True)
        self.assertEqual((true ^ True) is false, True)
        self.assertEqual((true ^ False) is true, True)
        self.assertEqual((false ^ True) is true, True)
        self.assertEqual((false ^ False) is false, True)
        self.assertEqual((true ^ None) is unknown, True)
        self.assertEqual((false ^ None) is unknown, True)
        self.assertEqual((unknown ^ True) is unknown, True)
        self.assertEqual((unknown ^ False) is unknown, True)
        self.assertEqual((unknown ^ None) is unknown, True)
        self.assertEqual((True ^ true) is false, True)
        self.assertEqual((True ^ false) is true, True)
        self.assertEqual((False ^ true) is true, True)
        self.assertEqual((False ^ false) is false, True)
        self.assertEqual((True ^ unknown) is unknown, True)
        self.assertEqual((False ^ unknown) is unknown, True)
        self.assertEqual((None ^ true) is unknown, True)
        self.assertEqual((None ^ false) is unknown, True)
        self.assertEqual((None ^ unknown) is unknown, True)
        t = true
        t ^= true
        self.assertEqual(t is false, True)
        t = true
        t ^= false
        self.assertEqual(t is true, True)
        f = false
        f ^= true
        self.assertEqual(f is true, True)
        f = false
        f ^= false
        self.assertEqual(f is false, True)
        t = true
        t ^= unknown
        self.assertEqual(t is unknown, True)
        f = false
        f ^= unknown
        self.assertEqual(f is unknown, True)
        u = unknown
        u ^= true
        self.assertEqual(u is unknown, True)
        u = unknown
        u ^= false
        self.assertEqual(u is unknown, True)
        u = unknown
        u ^= unknown
        self.assertEqual(u is unknown, True)
        t = true
        t ^= True
        self.assertEqual(t is false, True)
        t = true
        t ^= False
        self.assertEqual(t is true, True)
        f = false
        f ^= True
        self.assertEqual(f is true, True)
        f = false
        f ^= False
        self.assertEqual(f is false, True)
        t = true
        t ^= None
        self.assertEqual(t is unknown, True)
        f = false
        f ^= None
        self.assertEqual(f is unknown, True)
        u = unknown
        u ^= True
        self.assertEqual(u is unknown, True)
        u = unknown
        u ^= False
        self.assertEqual(u is unknown, True)
        u = unknown
        u ^= None
        self.assertEqual(u is unknown, True)
        t = True
        t ^= true
        self.assertEqual(t is false, True)
        t = True
        t ^= false
        self.assertEqual(t is true, True)
        f = False
        f ^= true
        self.assertEqual(f is true, True)
        f = False
        f ^= false
        self.assertEqual(f is false, True)
        t = True
        t ^= unknown
        self.assertEqual(t is unknown, True)
        f = False
        f ^= unknown
        self.assertEqual(f is unknown, True)
        u = None
        u ^= true
        self.assertEqual(u is unknown, True)
        u = None
        u ^= false
        self.assertEqual(u is unknown, True)
        u = None
        u ^= unknown
        self.assertEqual(u is unknown, True)

    def test_invert(self):
        "~ operator"
        true = Trivalent(True)
        false = Trivalent(False)
        unknown = Trivalent(None)
        self.assertEqual(~true, false)
        self.assertEqual(~false, true)
        self.assertEqual(~unknown, unknown)

    def test_int(self):
        "int"
        true = Trivalent(True)
        false = Trivalent(False)
        unknown = Trivalent(None)
        self.assertEqual(int(true), 1)
        self.assertEqual(int(false), -1)
        self.assertEqual(int(unknown), 0)


if __name__ == '__main__':
    scription.HAS_BEEN_RUN = True
    tempdir = tempfile.mkdtemp()
    try:
        main()
    finally:
        try:
            shutil.rmtree(tempdir)
        except:
            pass
