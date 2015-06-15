from __future__ import print_function
from scription import Script, Command, Run, Spec, InputFile, Bool, _usage, version, empty
from scription import *
from unittest import TestCase, main
import datetime
import os
import scription
import shlex
import shutil
import sys
import tempfile

is_win = sys.platform.startswith('win')
py_ver = sys.version_info[:2]
gubed = False
print('Scription %s.%s.%s' % version, verbose=0)

if py_ver >= (3, 0):
    unicode = str

def test_func_parsing(obj, func, tests, test_type=False):
    global gubed
    try:
        for params, main_args, main_kwds, sub_args, sub_kwds in tests:
            have_gubed = verbose = False
            if '--gubed' in params:
                have_gubed = True
            if '-v' in params or '--verbose' in params or '--verbose=1' in params:
                verbose = 1
            elif '-vv' in params or '--verbose=2' in params:
                verbose = 2
            res_main_args, res_main_kwds, res_sub_args, res_sub_kwds = _usage(func, params)
            obj.assertEqual(res_main_args, main_args)
            obj.assertEqual(res_main_kwds, main_kwds)
            obj.assertEqual(res_sub_args, sub_args)
            obj.assertEqual(res_sub_kwds, sub_kwds)
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
        Script.command = None
        Script.settings = {}
        Script.names = []

def test_func_docstrings(obj, func, docstring):
    try:
        obj.assertEqual(func.__doc__, docstring)
    finally:
        Script.command = None
        Script.settings = {}
        Script.names = []

class TestCommandlineProcessing(TestCase):

    def test_multi(self):
        @Command(
                huh=('misc options', 'multi'),
                )
        def tester(huh):
            pass
        tests = (
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
                huh=Spec('misc options', 'multi', default='woo'),
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
                huh=Spec('misc options', 'multi', default=('woo', )),
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
                huh=Spec('misc options', 'multi', default=(7, )),
                )
        def tester(huh):
            pass
        tests = (
                ( 'tester'.split(), (), {}, ((7, ), ), {} ),
                ( 'tester --huh=1'.split(), (), {}, ((1, ), ), {} ),
                ( 'tester -h 11 -h 13'.split(), (), {}, ((11, 13), ), {} ),
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

    def test_main(self):
        Script(gubed=False)

        @Command(this=('the thingie here', 'option'))
        def whoa(this):
            pass
        tests = (
                (['whoa'], (), {}, (None, ), {}),
                ('whoa --gubed'.split(), (), {}, (None, ), {}),
                ('whoa --gubed -t bukooz'.split(), (), {}, ('bukooz', ), {}),
                ('whoa -t fletcha'.split(), (), {}, ('fletcha', ), {}),
                )
        test_func_parsing(self, whoa, tests)

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
                ('sassy biscuit and --those gravy'.split(), (), {}, ('biscuit', True, 'and' ,'gravy'), {}),
                ('sassy biscuit and gravy --those'.split(), (), {}, ('biscuit', True, 'and' ,'gravy'), {}),
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
                ('sassy biscuit and --those gravy'.split(), (), {}, ('biscuit', True, 'and' ,'gravy'), {}),
                ('sassy biscuit and gravy --those'.split(), (), {}, ('biscuit', True, 'and' ,'gravy'), {}),
                )
        test_func_parsing(self, sassy, tests)

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


class TestCommandNames(TestCase):

    def setUp(self):
        target_dir = os.path.join(os.getcwd(), os.path.split(os.path.split(scription.__file__)[0])[0])
        self.command_file = command_file_name = os.path.join(tempdir, 'Some_Script')
        command_file = open(command_file_name, 'w')
        try:
            command_file.write(
                "from __future__ import print_function\n"
                "'just a test doc'\n"
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
            result = Execute(cmdline)
            self.assertTrue(result.returncode is 0, '%s failed!\n%s\n%s' % (cmdline, result.stdout, result.stderr))
            self.assertEqual(result.stderr, '', '%s failed!\n%s\n%s' % (cmdline, result.stdout, result.stderr))
            self.assertEqual(result.stdout, 'success!\n', '%s failed!\n%s\n%s' % (cmdline, result.stdout, result.stderr))

    def test_capital_in_name(self):
        cmdline = ' '.join([sys.executable, self.command_file])
        result = Execute(cmdline)
        self.assertTrue(result.returncode is 0, '%s failed!\n%s\n%s' % (cmdline, result.stdout, result.stderr))
        self.assertEqual(result.stderr, '', '%s failed!\n%s\n%s' % (cmdline, result.stdout, result.stderr))
        self.assertEqual(result.stdout, 'aint that nice.\n', '%s failed!\n%s\n%s' % (cmdline, result.stdout, result.stderr))
        # cmdline = ' '.join([sys.executable, self.command_file, '--help'])
        # result = Execute(cmdline)
        # self.assertTrue(result.returncode is 0, '%s failed!\n%s\n%s' % (cmdline, result.stdout, result.stderr))
        # self.assertEqual(result.stderr, '', '%s failed!\n%s\n%s' % (cmdline, result.stdout, result.stderr))
        # self.assertEqual(
        #         result.stdout,
        #         'aint that nice.\n',
        #         '%s failed!\n%s\n%s' % (cmdline, result.stdout, result.stderr),
        #         )

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
            command = Execute([sys.executable, self.good_file], pty=True)
            self.assertEqual(command.stdout, 'good output here!\n')
            self.assertEqual(command.stderr, '')
            command = Execute([sys.executable, self.bad_file], pty=True)
            self.assertEqual(command.stdout, '')
            self.assertTrue(command.stderr.endswith('ValueError: uh-oh -- bad value!\n'))
            command = Execute([sys.executable, self.mixed_file], pty=True)
            self.assertEqual(command.stdout, 'good night\nsweetheart!\n')
            self.assertTrue(command.stderr.endswith("KeyError: 'the key is missing?'\n"),
                    'Failed (actual results):\n%s' % command.stderr)
            command = Execute([sys.executable, self.pty_password_file], pty=True, password='Salutations!')
            # if py_ver < (3, 0):
            self.assertEqual(
                    command.stdout,
                    # "super secret santa soda sizzle?\nmake sure no one is watching you type!: \n'Salutations!'?  Are you sure??",
                    "'Salutations!'?  Are you sure??\n",
                    'Failed (actual results):\n%r' % command.stdout)
            self.assertEqual(
                    command.stderr,
                    '',
                    )
            # else:
            #     self.assertEqual(
            #             command.stdout,
            #             "super secret santa soda sizzle?\n'Salutations!'?  Are you sure??",
            #             'Failed (actual results):\n%r' % command.stdout)
            #     self.assertEqual(
            #             command.stderr,
            #             'make sure no one is watching you type!:',
            #             )

    def test_subprocess(self):
        command = Execute([sys.executable, self.good_file], pty=False)
        self.assertEqual(command.stdout, 'good output here!\n')
        self.assertEqual(command.stderr, '')
        command = Execute([sys.executable, self.bad_file], pty=False)
        self.assertEqual(command.stdout, '')
        self.assertTrue(command.stderr.endswith('ValueError: uh-oh -- bad value!\n'))
        command = Execute([sys.executable, self.mixed_file], pty=False)
        self.assertEqual(command.stdout, 'good night\nsweetheart!\n')
        self.assertTrue(command.stderr.endswith("KeyError: 'the key is missing?'\n"),
                'Failed (actual results):\n%r' % command.stderr)
        command = Execute([sys.executable, self.subp_password_file], pty=False, password='Salutations!')
        self.assertTrue(command.stdout.startswith("super secret santa soda sizzle?\nmake sure no one is watching you type!: 'Salutations!'?  Are you sure??\n"),
                'Failed (actual results):\n%r' % command.stdout)
        self.assertEqual(command.stderr, '')


class TestOrm(TestCase):

    def setUp(self):
        self.orm_file = orm_file_name = os.path.join(tempdir, 'test.orm')
        orm_file = open(orm_file_name, 'w')
        try:
            orm_file.write(
                    "home = /usr/bin\n"
                    'who = "ethan"\n'
                    "\n"
                    "[hg]\n"
                    "home = /usr/local/bin\n"
                    "when = 12:45\n"
                    )
        finally:
            orm_file.close()

    def test_standard(self):
        complete = OrmFile(self.orm_file)
        self.assertEqual(complete.home, '/usr/bin')
        self.assertEqual(complete.who, 'ethan')
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


# class TestVersion(TestCase):
# 
#     def test_create(self):
#         self.assertEqual(str(Version(0, 1)), '0.1')
#         self.assertEqual(str(Version('0.1')), '0.1')
#         self.assertEqual(str(Version((0, 1))), '0.1')
#         self.assertEqual(str(Version(1, 0, 4, 'rc.1')), '1.0.4.rc1')
#         self.assertEqual(str(Version(1, 0, 4, 'rc-1')), '1.0.4.rc1')
#         self.assertEqual(str(Version(1, 0, 4, 'rc_1')), '1.0.4.rc1')
#         self.assertEqual(str(Version('1.0.4.rc1')), '1.0.4.rc1')
#         self.assertEqual(str(Version('1.0.4rc1')), '1.0.4.rc1')
#         self.assertEqual(str(Version('1.0.4_rc1')), '1.0.4.rc1')
#         self.assertEqual(str(Version('1.0.4-rc1')), '1.0.4.rc1')
#         self.assertEqual(str(Version(5, 7, sub='dev3')), '5.7.dev3')
#         self.assertEqual(str(Version(5, 7, 0, sub='dev3')), '5.7.dev3')
#         self.assertEqual(str(Version(2, 9, sub='a2')), '2.9.a2')
#         self.assertEqual(str(Version(9, 1, 3, local='blahyadda')), '9.1.3+blahyadda')
#         self.assertEqual(str(Version(2, 3, 5)), '2.3.5')
#         self.assertEqual(str(Version('2.3.5')), '2.3.5')
#         self.assertEqual(str(Version('2.3.05')), '2.3.5')


if __name__ == '__main__':
    scription.HAS_BEEN_RUN = True
    tempdir = tempfile.mkdtemp()
    try:
        main()
    finally:
        shutil.rmtree(tempdir)
