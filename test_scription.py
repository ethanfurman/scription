from scription import Script, Command, Run, Spec, InputFile, Bool, usage, version
from scription import *
from path import Path
from unittest import TestCase, main

print('Scription', version)

#@Script(blah=('configuration file',None,None,InputFile))
#def main(jobstep, blah='foo', **stuff):
#    "testing cmd_line..."
#    print jobstep, blah, stuff

class TestCommandlineProcessing(TestCase):

    def test_multi(self):
        @Script(
                huh=('misc options', 'multi'),
                )
        def tester(huh):
            pass
        for func, params, args, kwds in (
                ( tester, 'tester -h file1'.split(), (('file1',),), {},),
                ( tester, 'tester -h file1 -h file2'.split(), (('file1', 'file2'),), {},),
                ):
            self.assertEqual(usage(func, params), (args, kwds))
            for key in func.__annotations__.keys():
                if key not in ('huh', ):
                    del func.__annotations__[key]

    def test_multi_with_comma(self):
        @Script(
                huh=('misc options', 'multi'),
                )
        def tester(huh):
            pass
        for func, params, args, kwds in (
                ( tester, 'tester --huh=one,two,three'.split(), (('one', 'two', 'three'), ), {},),
                ( tester, 'tester --huh one,two,three'.split(), (('one', 'two', 'three'), ), {},),
                ( tester, 'tester -h one,two -h three,four'.split(), (('one', 'two', 'three', 'four'), ), {},),
                ):
            self.assertEqual(usage(func, params), (args, kwds))
            for key in func.__annotations__.keys():
                if key not in ('huh', ):
                    del func.__annotations__[key]

    def test_multi_with_comma_and_quotes(self):
        @Script(
                huh=('misc options', 'multi'),
                )
        def tester(huh):
            pass
        for func, params, args, kwds in (
                ( tester, 'tester --huh="one,two,three four"'.split(), (('one', 'two', 'three four'), ), {},),
                ( tester, 'tester --huh "one,two nine,three"'.split(), (('one', 'two nine', 'three'), ), {},),
                ( tester, 'tester -h one,two -h "three,four teen"'.split(), (('one', 'two', 'three', 'four teen'), ), {},),
                ):
            self.assertEqual(usage(func, params), (args, kwds))
            for key in func.__annotations__.keys():
                if key not in ('huh', ):
                    del func.__annotations__[key]

    def test_multi_with_option(self):
        @Script(
                huh=('misc options', 'multi'),
                wow=('oh yeah', 'option'),
                )
        def tester(huh, wow):
            pass
        for func, params, args, kwds in (
                ( tester, 'tester -h file1'.split(), (('file1',), None), {},),
                ( tester, 'tester -h file1 -w google'.split(), (('file1',), 'google'), {},),
                ( tester, 'tester -h file1 -h file2'.split(), (('file1', 'file2'), None), {},),
                ( tester, 'tester -h file1 -h file2 -w frizzle'.split(), (('file1', 'file2'), 'frizzle'), {},),
                ):
            self.assertEqual(usage(func, params), (args, kwds))
            for key in func.__annotations__.keys():
                if key not in ('huh', 'wow'):
                    del func.__annotations__[key]

    def test_positional_only(self):
        @Script(
                file1=('source file', ),
                file2=('dest file', ),
                )
        def copy(file1, file2):
            pass
        for func, params, args, kwds in (
                (copy, 'copy file1 file2'.split(), ('file1', 'file2'), {}),
                ):
            self.assertEqual(usage(func, params), (args, kwds))

    def test_positional_with_flag(self):
        @Script(
                file1=('source file', ),
                file2=('dest file', ),
                binary=('copy in binary mode', 'flag',),
                )
        def copy(file1, file2, binary):
            pass
        for func, params, args, kwds in (
                (copy, 'copy file1 file2'.split(), ('file1', 'file2', False), {}),
                (copy, 'copy file1 file2 -b'.split(), ('file1', 'file2', True), {}),
                ):
            self.assertEqual(usage(func, params), (args, kwds))
            for key in func.__annotations__.keys():
                if key not in ('file1','file2','binary'):
                    del func.__annotations__[key]

    def test_positional_with_var(self):
        @Script(
                file1=('source file', ),
                file2=('dest file', ),
                comment=('misc comment for testing', 'option',),
                )
        def copy(file1, file2, comment):
            pass
        for func, params, args, kwds in (
                (copy, 'copy file1 file2'.split(), ('file1', 'file2', None), {}),
                (copy, 'copy file1 file2 --comment=howdy!'.split(), ('file1', 'file2', 'howdy!'), {}),
                (copy, 'copy file1 file2 --comment howdy!'.split(), ('file1', 'file2', 'howdy!'), {}),
                (copy, 'copy file1 file2 --comment="howdy doody!"'.split(), ('file1', 'file2', 'howdy doody!'), {}),
                (copy, 'copy file1 file2 --comment "howdy doody!"'.split(), ('file1', 'file2', 'howdy doody!'), {}),
                ):
            self.assertEqual(usage(func, params), (args, kwds))
            for key in func.__annotations__.keys():
                if key not in ('file1','file2','comment'):
                    del func.__annotations__[key]

    def test_positional_with_flag_and_var(self):
        @Script(
                file1=('source file', ),
                file2=('dest file', ),
                binary=('copy in binary mode', 'flag',),
                comment=('misc comment for testing', 'option',),
                )
        def copy(file1, file2, binary=True, comment=''):
            pass
        for func, params, args, kwds in (
                (copy, 'copy file1 file2'.split(), ('file1', 'file2', True, ''), {}),
                (copy, 'copy file1 file2 --no-binary'.split(), ('file1', 'file2', False, ''), {}),
                (copy, 'copy file1 file2 --comment howdy!'.split(), ('file1', 'file2', True, 'howdy!'), {}),
                (copy, 'copy file1 file2 --comment=howdy!'.split(), ('file1', 'file2', True, 'howdy!'), {}),
                (copy, 'copy file1 file2 --no-binary --comment=howdy!'.split(), ('file1', 'file2', False, 'howdy!'), {}),
                (copy, 'copy file1 file2 --comment howdy!'.split(), ('file1', 'file2', True, 'howdy!'), {}),
                (copy, 'copy file1 file2 --no-binary --comment howdy!'.split(), ('file1', 'file2', False, 'howdy!'), {}),
                (copy, 'copy file1 file2 --comment "howdy doody!"'.split(), ('file1', 'file2', True, 'howdy doody!'), {}),
                (copy, 'copy file1 file2 --comment="howdy doody!"'.split(), ('file1', 'file2', True, 'howdy doody!'), {}),
                (copy, 'copy file1 file2 --no-binary --comment="howdy doody!"'.split(), ('file1', 'file2', False, 'howdy doody!'), {}),
                (copy, 'copy file1 file2 --comment "howdy doody!"'.split(), ('file1', 'file2', True, 'howdy doody!'), {}),
                (copy, 'copy file1 file2 --no-binary --comment "howdy doody!"'.split(), ('file1', 'file2', False, 'howdy doody!'), {}),
                ):
            self.assertEqual(usage(func, params), (args, kwds))
            for key in func.__annotations__.keys():
                if key not in ('file1','file2','binary','comment'):
                    del func.__annotations__[key]

    def test_type(self):
        @Script(
                one=Spec('integer', REQUIRED, type=int),
                two=Spec('string', OPTION, type=str),
                three=Spec('path', MULTI, None, type=Path),
                )
        def tester(one='1', two=2, three='/some/path/to/nowhere'):
            pass
        for func, params, args, kwds in (
                (tester, ['tester'], (1, '2', (Path('/some/path/to/nowhere'), )), {}),
                (tester, 'tester 3 -t 4 --three /somewhere/over/the/rainbow'.split(), (3, '4', (Path('/somewhere/over/the/rainbow'), )), {}),
                (tester, 'tester 5 -t 6 --three=/yellow/brick/road.txt'.split(), (5, '6', (Path('/yellow/brick/road.txt'), )), {}),
                ):
            usage_args, usage_kwds = usage(func, params)
            self.assertEqual((usage_args, usage_kwds), (args, kwds))
            self.assertTrue(isinstance(usage_args[0], int))
            self.assertTrue(isinstance(usage_args[1], str))
            self.assertTrue(all([isinstance(p, Path) for p in usage_args[2]]))
            for key in func.__annotations__.keys():
                if key not in ('one','two','three'):
                    del func.__annotations__[key]



if __name__ == '__main__':
    main()
