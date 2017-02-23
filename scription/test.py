from __future__ import print_function
from scription import *
from scription import _usage, version, empty, pocket
from unittest import skip, skipUnless, SkipTest, TestCase as unittest_TestCase, main
import datetime
import functools
import os
import pty
import scription
import shlex
import shutil
import sys
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
py_ver = sys.version_info[:2]
gubed = False
print('Scription %s.%s.%s -- Python %d.%d' % (version[:3] + py_ver), verbose=0)

if py_ver >= (3, 0):
    unicode = str
    raw_input = input

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
                obj.assertTrue(gubed)
            if verbose:
                obj.assertEqual(scription.VERBOSITY, verbose)
            if test_type:
                for rval, val in zip(res_main_args, main_args):
                    obj.assertTrue(type(rval) is type(val))
                for rkey, rval in res_main_kwds.items():
                    obj.assertTrue(type(rval) is type(main_kwds[rkey]))
                for rval, val in zip(res_sub_args, sub_args):
                    obj.assertTrue(type(rval) is type(val))
                for rkey, rval in res_sub_kwds.items():
                    obj.assertTrue(type(rval) is type(sub_kwds[rkey]))

            gubed = False
            scription.VERBOSITY = 0
            for spec in set(func.__scription__.values()):
                spec._cli_value = empty
    finally:
        script_name = '<unknown>'
        script_fullname = '<unknown>'
        script_main = None
        script_commands = {}
        script_command = None
        script_commandname = ''
        script_exception_lines = ''
        script_fullname, script_exception_lines

def test_func_docstrings(obj, func, docstring):
    try:
        obj.assertEqual(func.__doc__, docstring)
    finally:
        script_main = None
        script_commands = {}
        script_main, script_commands

class TestCase(unittest_TestCase):

    run_so_far = []

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
        if (pocket(value=3)):
            self.assertEqual(3, pocket.value)
        if not (pocket(value=None)):
            self.assertIs(None, pocket.value)

    def test_multi_args(self):
        val = pocket(value1=3, value2=7)
        self.assertIs(type(val), tuple)
        self.assertEqual(len(val), 2)
        self.assertTrue(3 in val)
        self.assertTrue(7 in val)
        self.assertEqual(pocket.value1, 3)
        self.assertEqual(pocket.value2, 7)


class TestCommandlineProcessing(TestCase):

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
                (['tester'], (), {}, (1, '2', (Path('/some/path/to/nowhere'), )), {} ),
                ('tester 3 -t 4 --three /somewhere/over/the/rainbow'.split(), (), {}, (3, '4', (Path('/somewhere/over/the/rainbow'), )), {} ),
                ('tester 5 -t 6 --three=/yellow/brick/road.txt'.split(), (), {}, (5, '6', (Path('/yellow/brick/road.txt'), )), {} ),
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

    def test_varargs_autoconsume_after_first(self):
        @Command(
                job=('job, job args, etc',),
                )
        def do_job(*job):
            pass
        tests = (
                ('do_job hg st'.split(), (), {}, ('hg', 'st'), {}),
                ('do_job hg diff -r 199'.split(), (), {}, ('hg', 'diff', '-r', '199'), {}),
                ('do_job hg diff -c 201'.split(), (), {}, ('hg', 'diff', '-c', '201'), {}),
                (shlex.split('do_job hg commit -m "a message"'), (), {}, ('hg', 'commit', '-m', 'a message'), {}),
                )
        test_func_parsing(self, do_job, tests)

    def test_kwds(self):
        @Command(
                hirelings=('who to boss around', ),
                )
        def bossy(**hirelings):
            pass
        tests = (
                ('bossy larry=stupid curly=lazy moe=dumb'.split(), (), {}, (), {'larry':'stupid', 'curly':'lazy', 'moe':'dumb'}),
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
        result = Execute([sys.executable, test_file, 'haha!'], timeout=10)
        self.assertEqual(result.stdout, 'success!\n', result.stdout + '\n' + result.stderr)

    def test_option(self):
        test_file = self.write_script('OPTION')
        result = Execute([sys.executable, test_file, '--test', 'haha!'], timeout=10)
        self.assertEqual(result.stdout, 'success!\n', result.stdout + '\n' + result.stderr)

    def test_flag(self):
        test_file = self.write_script('FLAG')
        result = Execute([sys.executable, test_file, '--test'], timeout=10)
        self.assertEqual(result.stdout, 'success!\n', result.stdout + '\n' + result.stderr)

    def test_multi1(self):
        test_file = self.write_script('MULTI')
        result = Execute([sys.executable, test_file, '--test', 'boo'], timeout=10)
        self.assertEqual(result.stdout, 'success!\n', result.stdout + '\n' + result.stderr)

    def test_multi2(self):
        test_file = self.write_script('MULTI')
        result = Execute([sys.executable, test_file, '--test', 'boo,hoo'], timeout=10)
        self.assertEqual(result.stdout, 'success!\n', result.stdout + '\n' + result.stderr)

    def test_multi3(self):
        test_file = self.write_script('MULTI')
        result = Execute([sys.executable, test_file, '--test', 'boo', '--test', 'hoo'], timeout=10)
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
            self.assertTrue(result.returncode == 0, '%s failed!\n%s\n%s' % (cmdline, result.stdout, result.stderr))
            self.assertEqual(result.stderr, '', '%s failed!\n%s\n%s' % (cmdline, result.stdout, result.stderr))
            self.assertEqual(result.stdout, 'success!\n', '%s failed!\n%s\n%s' % (cmdline, result.stdout, result.stderr))

    def test_capital_in_name(self):
        cmdline = ' '.join([sys.executable, self.command_file])
        result = Execute(cmdline, timeout=10)
        self.assertTrue(result.returncode == 0, '%s failed!\n%s\n%s' % (cmdline, result.stdout, result.stderr))
        self.assertEqual(result.stderr, '', '%s failed!\n%s\n%s' % (cmdline, result.stdout, result.stderr))
        self.assertEqual(result.stdout, 'aint that nice.\n', '%s failed!\n%s\n%s' % (cmdline, result.stdout, result.stderr))
        cmdline = ' '.join([sys.executable, self.command_file, '--help'])
        result = Execute(cmdline, timeout=10)
        self.assertTrue(result.returncode == 0, '%s failed!\n%s\n%s' % (cmdline, result.stdout, result.stderr))
        self.assertEqual(result.stderr, '', '%s failed!\n%s\n%s' % (cmdline, result.stdout, result.stderr))
        self.assertEqual(
                result.stdout,
                'just a test doc\n   some-script  testing caps in name\n   test-dash    testing dashes in name\n',
                '%s failed!\nstdout: %r\nstderr: %r' % (cmdline, result.stdout, result.stderr),
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
                "global options: --conf CONF\n"
                "\n"
                "    CONF   configuration file\n"
                "\n"
                "whatever THIS THAT\n"
                "\n"
                "    THIS   this argument    \n"
                "    THAT   that argument    \n"
                )
        test_file = self.write_script(file_data)
        result = Execute([sys.executable, test_file, '--help'], timeout=10)
        self.assertMultiLineEqual(result.stdout.strip(), target_result.strip())
        result = Execute([sys.executable, test_file, '--help'], pty=True, timeout=10)
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
                "Available commands/options in help_test\n"
                "\n"
                "   global options: --conf CONF\n"
                "\n"
                "   another-thing  THIS THAT\n"
                "   whatever       THIS THAT\n"
                )
        test_file = self.write_script(file_data)
        result = Execute([sys.executable, test_file, '--help'], timeout=10)
        self.assertMultiLineEqual(result.stdout.strip(), target_result.strip())

    # def test_alias_matches_script_name(self):
    #     file_data = (
    #             "import sys\n"
    #             "sys.path.insert(0, %r)\n"
    #             "from scription import *\n"
    #             "\n"
    #             "@Script(\n"
    #             "        conf=('configuration file', OPTION),\n"
    #             "        )\n"
    #             "def main():\n"
    #             "    pass\n"
    #             "\n"
    #             "@Command(\n"
    #             "        this=('this argument',),\n"
    #             "        that=('that argument',),\n"
    #             "        )\n"
    #             "@Alias('help-test')\n"
    #             "def whatever(this, that):\n"
    #             "    pass\n"
    #             "\n"
    #             "\n"
    #             "Main()\n"
    #             )
    #     target_result = (
    #             "Available commands/options in help_test\n"
    #             "\n"
    #             "   global options: --conf CONF\n"
    #             "\n"
    #             "   help_test  THIS THAT\n"
    #             )
    #     test_file = self.write_script(file_data)
    #     result = Execute([sys.executable, test_file, '--help'], timeout=10)
    #     self.assertMultiLineEqual(result.stdout.strip(), target_result.strip())

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
                "   global options: --conf CONF\n"
                "\n"
                "   another-thing  THIS THAT\n"
                "   that-thing     OTHER\n"
                "   whatever       THIS THAT\n"
                )
        test_file = self.write_script(file_data)
        result = Execute([sys.executable, test_file, '--help'], timeout=10)
        self.assertMultiLineEqual(result.stdout.strip(), target_result.strip())


class TestDocStrings(TestCase):

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
        self.bad_file = bad_file_path = os.path.join(tempdir, 'bad_output')
        bad_file = open(bad_file_path, 'w')
        try:
            bad_file.write("raise ValueError('uh-oh -- bad value!')")
        finally:
            bad_file.close()
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
        self.subp_password_file = password_file_name = os.path.join(tempdir, 'get_subp_pass')
        password_file = open(password_file_name, 'w')
        try:
            password_file.write(
                    "print('super secret santa soda sizzle?')\n"
                    "password = %sinput('make sure no one is watching you type!: ')\n"
                    "print('%%r?  Are you sure??' %% password)"
                    % ('', 'raw_')[py_ver < (3, 0)]
                    )
        finally:
            password_file.close()

    if not is_win:
        def test_pty(self):
            command = Execute([sys.executable, self.good_file], pty=True, timeout=10)
            self.assertEqual(command.stdout, 'good output here!\n')
            self.assertEqual(command.stderr, '')
            command = Execute([sys.executable, self.bad_file], pty=True, timeout=10)
            self.assertEqual(command.stdout, '')
            self.assertTrue(command.stderr.endswith('ValueError: uh-oh -- bad value!\n'))
            command = Execute([sys.executable, self.mixed_file], pty=True, timeout=10)
            self.assertEqual(command.stdout, 'good night\nsweetheart!\n')
            self.assertTrue(command.stderr.endswith("KeyError: 'the key is missing?'\n"),
                    'Failed (actual results):\n%s' % command.stderr)
            command = Execute([sys.executable, self.pty_password_file], password='Salutations!', pty=True, timeout=10)
            self.assertEqual(
                    command.stdout,
                    "super secret santa soda sizzle?\nmake sure no one is watching you type!: \n'Salutations!'?  Are you sure??\n",
                    )
            self.assertEqual(
                    command.stderr,
                    '',
                    )

    if is_win:
        if py_ver >= (3, 3):
            def test_timeout(self):
                "test timeout with subprocess alone"
                command = Execute([sys.executable, '-c', 'import time; time.sleep(30)'], timeout=1, pty=False)
                self.assertTrue(command.returncode)
        else:
            def test_timeout(self):
                "no timeout in this version"
                self.assertRaises(
                        OSError,
                        Execute,
                        [sys.executable, '-c', 'import time; time.sleep(30)'],
                        timeout=1,
                        pty=False,
                        )
                self.assertRaises(
                        OSError,
                        Execute,
                        [sys.executable, '-c', 'import time; time.sleep(30)'],
                        timeout=1,
                        pty=True,
                        )
    else:
        def test_timeout(self):
            "test timeout with pty, and with subprocess/signals"
            command = Execute(
                    [sys.executable, '-c', 'import time; time.sleep(30); raise Exception("did not time out!")'],
                    timeout=1,
                    pty=True,
                    )
            self.assertTrue(command.returncode)
            command = Execute(
                    [sys.executable, '-c', 'import time; time.sleep(30); raise Exception("did not time out!")'],
                    timeout=1,
                    pty=False,
                    )
            self.assertTrue(command.returncode)

    def test_environ(self):
        "test setting environment"
        command = Execute(
                [sys.executable, '-c', 'import os; print(os.environ["HAPPYDAY"])'],
                timeout=1,
                pty=False,
                HAPPYDAY='fonzirelli',
                )
        self.assertIn('fonzirelli', command.stdout)
        command = Execute(
                [sys.executable, '-c', 'import os; print(os.environ["HAPPYDAY"])'],
                timeout=1,
                pty=True,
                HAPPYDAY='fonzirelli',
                )
        self.assertIn('fonzirelli', command.stdout)

    def test_subprocess(self):
        command = Execute(
                [sys.executable, self.good_file],
                pty=False,
                timeout=10,
                )
        self.assertEqual(command.stdout, 'good output here!\n')
        self.assertEqual(command.stderr, '')
        command = Execute(
                [sys.executable, self.bad_file],
                pty=False,
                timeout=10,
                )
        self.assertEqual(command.stdout, '')
        self.assertTrue(command.stderr.endswith('ValueError: uh-oh -- bad value!\n'))
        command = Execute(
                [sys.executable, self.mixed_file],
                pty=False,
                timeout=10,
                )
        self.assertEqual(command.stdout, 'good night\nsweetheart!\n')
        self.assertTrue(command.stderr.endswith("KeyError: 'the key is missing?'\n"),
                'Failed (actual results):\n%r' % command.stderr)
        command = Execute(
                [sys.executable, self.subp_password_file],
                pty=False,
                password='Salutations!',
                timeout=10,
                )
        self.assertEqual(
                command.stdout,
                "super secret santa soda sizzle?\nmake sure no one is watching you type!: 'Salutations!'?  Are you sure??\n",
                'Failed (actual results):\n%r' % command.stdout,
                )
        self.assertEqual(command.stderr, '')


class TestOrm(TestCase):

    def setUp(self):
        self.orm_file = orm_file_name = os.path.join(tempdir, 'test.orm')
        orm_file = open(orm_file_name, 'w')
        try:
            orm_file.write(
                    "home = /usr/bin\n"
                    'who = "ethan"\n'
                    'why = why not?\n'
                    "\n"
                    "[hg]\n"
                    "home = /usr/local/bin\n"
                    "when = 12:45\n"
                    )
        finally:
            orm_file.close()

    def test_iteration(self):
        'test iteration'
        # test whole thing
        complete = OrmFile(self.orm_file)
        hg = list(complete.hg)
        root = list(complete)
        self.assertEqual(len(root), 4)
        self.assertTrue(('home', '/usr/bin') in root)
        self.assertTrue(('who', 'ethan') in root)
        self.assertTrue(('why', 'why not?') in root)
        self.assertTrue(('hg', complete.hg) in root)
        self.assertEqual(len(hg), 4)
        self.assertTrue(('home', '/usr/local/bin') in hg)
        self.assertTrue(('who', 'ethan') in hg)
        self.assertTrue(('why', 'why not?') in hg)
        self.assertTrue(('when', datetime.time(12, 45)) in hg)
        # test subsection
        hg_only = OrmFile(self.orm_file, section='hg')
        hg = list(hg_only)
        self.assertEqual(len(hg), 4)
        self.assertTrue(('home', '/usr/local/bin') in hg)
        self.assertTrue(('who', 'ethan') in hg)
        self.assertTrue(('why', 'why not?') in hg)
        self.assertTrue(('when', datetime.time(12, 45)) in hg)

    def test_standard(self):
        'test standard data types'
        complete = OrmFile(self.orm_file)
        self.assertEqual(complete.home, '/usr/bin')
        self.assertEqual(complete.who, 'ethan')
        self.assertEqual(complete.why, 'why not?')
        self.assertEqual(complete.hg.home, '/usr/local/bin')
        self.assertEqual(complete.hg.who, 'ethan')
        self.assertEqual(complete.hg.when, datetime.time(12, 45))
        self.assertTrue(type(complete.home) is unicode)
        self.assertTrue(type(complete.who) is unicode)
        self.assertTrue(type(complete.hg.when) is datetime.time)
        hg = OrmFile(self.orm_file, section='hg')
        self.assertEqual(hg.home, '/usr/local/bin')
        self.assertEqual(hg.who, 'ethan')
        self.assertEqual(hg.when, datetime.time(12, 45))
        self.assertTrue(type(hg.home) is unicode)
        self.assertTrue(type(hg.who) is unicode)
        self.assertTrue(type(hg.when) is datetime.time)

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


class TestResponse(TestCase):

    class raw_input_cm(object):
        'context manager for mocking raw_input'
        def __init__(self, reply):
            self.reply = reply
        def __call__(self, prompt):
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
            with self.raw_input_cm(reply):
                ans = get_response('copy files? [y]es/[n]o/[a]ll/[m]aybe')
                self.assertEqual(ans, 'maybe')

    def test_multiple_choice_in_one_block(self):
        for reply in ('y', 'yes', 'Yes'):
            with self.raw_input_cm(reply):
                ans = get_response('copy files? [yes/no/all/maybe]')
                self.assertEqual(ans, 'yes')
        for reply in ('n', 'no', 'No'):
            with self.raw_input_cm(reply):
                ans = get_response('copy files? [yes/no/all/maybe]')
                self.assertEqual(ans, 'no')
        for reply in ('a', 'all', 'All'):
            with self.raw_input_cm(reply):
                ans = get_response('copy files? [yes/no/all/maybe]')
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
        job = Execute([sys.executable, test_file], pty=False, timeout=10, input='Bye!\n')
        self.assertEqual(thread_count, threading.active_count())
        self.assertEqual(job.stdout.strip(), 'howdy! Bye!', '\n out: %r\n err: %r' % (job.stdout, job.stderr))
        self.assertEqual(job.returncode, 0, '-- stdout --\n%s\n-- stderr --\n%s' % (job.stdout, job.stderr))

    def test_interactive_pty(self):
        thread_count = threading.active_count()
        test_file = self.write_script(
                '''from getpass import getpass\n'''
                '''print(getpass('howdy!'))\n'''
                )
        job = Execute([sys.executable, test_file], pty=True, timeout=10, input='Bye!\n')
        self.assertEqual(thread_count, threading.active_count())
        self.assertEqual(job.stdout.strip().replace('\n', ' '), 'howdy! Bye!', '\n out: %r\n err: %r' % (job.stdout, job.stderr))
        self.assertEqual(job.returncode, 0, '-- stdout --\n%s\n-- stderr --\n%s' % (job.stdout, job.stderr))

    def test_killed_process(self):
        thread_count = threading.active_count()
        test_file = self.write_script(
                '''import time\n'''
                '''time.sleep(5)\n'''
                )
        job = Execute([sys.executable, test_file], pty=False, timeout=1)
        self.assertEqual(thread_count, threading.active_count())
        self.assertEqual(job.stderr.strip(), 'TIMEOUT: process failed to complete in 1 seconds', '\n out: %r\n err: %r' % (job.stdout, job.stderr))
        self.assertNotEqual(job.returncode, 0, '-- stdout --\n%s\n-- stderr --\n%s' % (job.stdout, job.stderr))

    def test_killed_pty(self):
        thread_count = threading.active_count()
        test_file = self.write_script(
                '''import time\n'''
                '''time.sleep(5)\n'''
                )
        job = Execute([sys.executable, test_file], pty=True, timeout=1)
        self.assertEqual(thread_count, threading.active_count())
        self.assertEqual(job.stderr.strip(), 'TIMEOUT: process failed to complete in 1 seconds', '\n out: %r\n err: %r' % (job.stdout, job.stderr))
        self.assertNotEqual(job.returncode, 0, '-- stdout --\n%s\n-- stderr --\n%s' % (job.stdout, job.stderr))

    def test_died_process(self):
        thread_count = threading.active_count()
        test_file = self.write_script(
                '''import time\n'''
                '''def hello(x\n'''
                '''time.sleep(5)\n'''
                )
        job = Execute([sys.executable, test_file], pty=False, timeout=1)
        self.assertEqual(thread_count, threading.active_count())
        self.assertTrue('TIMEOUT: process failed to complete in 1 seconds' not in job.stdout)
        self.assertNotEqual(job.returncode, 0, '-- stdout --\n%s\n-- stderr --\n%s' % (job.stdout, job.stderr))

    def test_died_pty(self):
        thread_count = threading.active_count()
        test_file = self.write_script(
                '''import time\n'''
                '''def hello(x\n'''
                '''time.sleep(5)\n'''
                )
        job = Execute([sys.executable, test_file], pty=True, timeout=1)
        self.assertEqual(thread_count, threading.active_count())
        self.assertTrue('TIMEOUT: process failed to complete in 1 seconds' not in job.stdout)
        self.assertNotEqual(job.returncode, 0, '-- stdout --\n%s\n-- stderr --\n%s' % (job.stdout, job.stderr))


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
            if py_ver >= (2, 5):
                self.assertEqual((0, 1, -1)[huh], 1)

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
            if py_ver >= (2, 5):
                self.assertEqual((0, 1, -1)[huh], -1)

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
