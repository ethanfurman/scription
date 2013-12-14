from scription import Script, Command, Run, InputFile, Bool, usage
from unittest import TestCase, main

#@Script(blah=('configuration file',None,None,InputFile))
#def main(jobstep, blah='foo', **stuff):
#    "testing cmd_line..."
#    print jobstep, blah, stuff

class TestCommandlineProcessing(TestCase):

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
                (copy, 'copy file1 file2 --comment=howdy doody!'.split(), ('file1', 'file2', 'howdy doody!'), {}),
                (copy, 'copy file1 file2 --comment howdy doody!'.split(), ('file1', 'file2', 'howdy doody!'), {}),
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
                (copy, 'copy file1 file2 --comment=howdy!'.split(), ('file1', 'file2', True, 'howdy!'), {}),
                (copy, 'copy file1 file2 --no-binary --comment=howdy!'.split(), ('file1', 'file2', False, 'howdy!'), {}),
                (copy, 'copy file1 file2 --comment howdy!'.split(), ('file1', 'file2', True, 'howdy!'), {}),
                (copy, 'copy file1 file2 --no-binary --comment howdy!'.split(), ('file1', 'file2', False, 'howdy!'), {}),
                (copy, 'copy file1 file2 --comment=howdy doody!'.split(), ('file1', 'file2', True, 'howdy doody!'), {}),
                (copy, 'copy file1 file2 --no-binary --comment=howdy doody!'.split(), ('file1', 'file2', False, 'howdy doody!'), {}),
                (copy, 'copy file1 file2 --comment howdy doody!'.split(), ('file1', 'file2', True, 'howdy doody!'), {}),
                (copy, 'copy file1 file2 --no-binary --comment howdy doody!'.split(), ('file1', 'file2', False, 'howdy doody!'), {}),
                ):
            self.assertEqual(usage(func, params), (args, kwds))
            for key in func.__annotations__.keys():
                if key not in ('file1','file2','binary','comment'):
                    del func.__annotations__[key]

if __name__ == '__main__':
    main()
