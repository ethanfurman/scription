from scription import Script, Command, Run, Spec, InputFile, Bool, _usage, version, empty
from scription import *
from path import Path
from unittest import TestCase, main
import scription

print('Scription', version)

#@Script(blah=('configuration file',None,None,InputFile))
#def main(jobstep, blah='foo', **stuff):
#    "testing cmd_line..."
#    print jobstep, blah, stuff

def test_func_parsing(obj, func, tests, test_type=False):
    try:
        for params, main, sub in tests:
            res_main, res_sub = _usage(func, params)
            obj.assertEqual((res_main, res_sub), (main, sub))
            if test_type:
                for rk, rv in res_main.items():
                    obj.assertTrue(type(rv) is type(main[rk]))
                for rk, rv in res_sub.items():
                    obj.assertTrue(type(rv) is type(sub[rk]))

            for spec in set(func.__scription__.values()):
                spec._cli_value = empty
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
                ( 'tester -h file1'.split(), {}, {'huh':('file1', )} ),
                ( 'tester -h file1 -h file2'.split(), {}, {'huh':('file1', 'file2')} ),
                )
        test_func_parsing(self, tester, tests)

    def test_multi_with_comma(self):
        @Command(
                huh=('misc options', 'multi'),
                )
        def tester(huh):
            pass
        tests = (
                ( 'tester --huh=one,two,three'.split(), {}, {'huh':('one', 'two', 'three')} ),
                ( 'tester --huh one,two,three'.split(), {}, {'huh':('one', 'two', 'three')} ),
                ( 'tester -h one,two -h three,four'.split(), {}, {'huh':('one', 'two', 'three', 'four')} ),
                )
        test_func_parsing(self, tester, tests)

    def test_multi_with_comma_and_quotes(self):
        @Command(
                huh=('misc options', 'multi'),
                )
        def tester(huh):
            pass
        tests = (
                ( 'tester --huh="one,two,three four"'.split(), {}, {'huh':('one', 'two', 'three four')}),
                ( 'tester --huh "one,two nine,three"'.split(), {}, {'huh':('one', 'two nine', 'three')}),
                ( 'tester -h one,two -h "three,four teen"'.split(), {}, {'huh':('one', 'two', 'three', 'four teen')}),
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
                ( 'tester -h file1'.split(), {}, {'huh':('file1', ), 'wow':None} ),
                ( 'tester -h file1 -w google'.split(), {}, {'huh':('file1', ), 'wow':'google'} ),
                ( 'tester -h file1 -h file2'.split(), {}, {'huh':('file1', 'file2'), 'wow':None} ),
                ( 'tester -h file1 -h file2 -w frizzle'.split(), {}, {'huh':('file1', 'file2'), 'wow':'frizzle'} ),
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
                ('copy file1 file2'.split(), {}, {'file1':'file1', 'file2':'file2'} ),
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
                ('copy file1 file2'.split(), {}, {'file1':'file1', 'file2':'file2', 'binary':False} ),
                ('copy file1 file2 -b'.split(), {}, {'file1':'file1', 'file2':'file2', 'binary':True} ),
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
                ('copy file1 file2'.split(), {}, {'file1':'file1', 'file2':'file2', 'comment':None} ),
                ('copy file1 file2 --comment=howdy!'.split(), {}, {'file1':'file1', 'file2':'file2', 'comment': 'howdy!'} ),
                ('copy file1 file2 --comment howdy!'.split(), {}, {'file1':'file1', 'file2':'file2', 'comment': 'howdy!'} ),
                ('copy file1 file2 --comment="howdy doody!"'.split(), {}, {'file1':'file1', 'file2':'file2', 'comment':'howdy doody!'} ),
                ('copy file1 file2 --comment "howdy doody!"'.split(), {}, {'file1':'file1', 'file2':'file2', 'comment':'howdy doody!'} ),
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
                ('copy file1 file2'.split(), {}, {'file1':'file1', 'file2':'file2', 'binary':True, 'comment':''} ),
                ('copy file1 file2 --no-binary'.split(), {}, {'file1':'file1', 'file2':'file2', 'binary':False, 'comment':''} ),
                ('copy file1 file2 --comment howdy!'.split(), {}, {'file1':'file1', 'file2':'file2', 'binary':True, 'comment':'howdy!'} ),
                ('copy file1 file2 --comment=howdy!'.split(), {}, {'file1':'file1', 'file2':'file2', 'binary':True, 'comment':'howdy!'} ),
                ('copy file1 file2 --no-binary --comment=howdy!'.split(), {}, {'file1':'file1', 'file2':'file2', 'binary':False, 'comment':'howdy!'} ),
                ('copy file1 file2 --comment howdy!'.split(), {}, {'file1':'file1', 'file2':'file2', 'binary':True, 'comment':'howdy!'} ),
                ('copy file1 file2 --no-binary --comment howdy!'.split(), {}, {'file1':'file1', 'file2':'file2', 'binary':False, 'comment':'howdy!'} ),
                ('copy file1 file2 --comment "howdy doody!"'.split(), {}, {'file1':'file1', 'file2':'file2', 'binary':True, 'comment':'howdy doody!'} ),
                ('copy file1 file2 --comment="howdy doody!"'.split(), {}, {'file1':'file1', 'file2':'file2', 'binary':True, 'comment':'howdy doody!'} ),
                ('copy file1 file2 --no-binary --comment="howdy doody!"'.split(), {}, {'file1':'file1', 'file2':'file2', 'binary':False, 'comment':'howdy doody!'} ),
                ('copy file1 file2 --comment "howdy doody!"'.split(), {}, {'file1':'file1', 'file2':'file2', 'binary':True, 'comment':'howdy doody!'} ),
                ('copy file1 file2 --no-binary --comment "howdy doody!"'.split(), {}, {'file1':'file1', 'file2':'file2', 'binary':False, 'comment':'howdy doody!'} ),
                )
        test_func_parsing(self, copy, tests)

    def test_type(self):
        @Command(
                one=Spec('integer', REQUIRED, type=int),
                two=Spec('string', OPTION, type=str),
                three=Spec('path', MULTI, None, type=Path),
                )
        def tester(one='1', two=2, three='/some/path/to/nowhere'):
            pass
        tests = (
                (['tester'], {}, {'one':1, 'two':'2', 'three':(Path('/some/path/to/nowhere'), )} ),
                ('tester 3 -t 4 --three /somewhere/over/the/rainbow'.split(), {}, {'one':3, 'two':'4', 'three':(Path('/somewhere/over/the/rainbow'), )} ),
                ('tester 5 -t 6 --three=/yellow/brick/road.txt'.split(), {}, {'one':5, 'two':'6', 'three':(Path('/yellow/brick/road.txt'), )} ),
                )
        test_func_parsing(self, tester, tests, test_type=True)

    def test_main(self):
        Script(debug=False)

        @Command(this=('the thingie here', 'option'))
        def whoa(this):
            pass
        tests = (
                (['whoa'], {}, {'this':None}),
                ('whoa --debug'.split(), {}, {'this':None}),
                ('whoa --debug -t bukooz'.split(), {}, {'this':'bukooz'}),
                ('whoa -t fletcha'.split(), {}, {'this':'fletcha'}),
                )
        test_func_parsing(self, whoa, tests)

    def test_main_with_feeling(self):
        @Script(
                debug=False,
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
                ('query blahblah'.split(), {'password':None}, {'database':'blahblah'}),
                ('query booboo --password banana'.split(), {'password':'banana'}, {'database':'booboo'}),
                ('query beebee --password banana --debug'.split(), {'password':'banana'}, {'database':'beebee'}),
                )
        test_func_parsing(self, query, tests)

    def test_varargs(self):
        @Command(
                files=('files to destroy', 'required', None),
                )
        def rm(*files):
            pass
        tests = (
                ('rm this.txt'.split(), {}, {'':('this.txt', )} ),
                ('rm those.txt that.doc'.split(), {}, {'':('those.txt', 'that.doc')} ),
                )
        test_func_parsing(self, rm, tests)


if __name__ == '__main__':
    scription.HAS_BEEN_RUN = True
    main()
