from scription import Script, Command, Run, InputFile, Bool, usage, version
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
                (tester, 'tester -h file1'.split(), (['file1'],), {}),
                (tester, 'tester -h file1 -h file2'.split(), (['file1', 'file2'],), {}),
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
                (tester, 'tester -h file1'.split(), (['file1'], None), {}),
                (tester, 'tester -h file1 -w google'.split(), (['file1'], 'google'), {}),
                (tester, 'tester -h file1 -h file2'.split(), (['file1', 'file2'], None), {}),
                (tester, 'tester -h file1 -h file2 -w frizzle'.split(), (['file1', 'file2'], 'frizzle'), {}),
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

if __name__ == '__main__':
    main()
