import setuptools
from distutils.core import setup

description = '''\
scription

light-weight library to enhance command-line scripts; includes conversion of
parameters to specified data types, parameter checking, basic input/output with
users, support for suid [1], sending email, executing sub-programs, and having
sub-commands within a script


decorators

  - Script:  sets global variables and/or parameters for Commands; the decorated
    function will be called by Main/Run before any specified Command

  - Command:  marks function as a subcommand for the script (e.g. add, delete,
    list, etc.); if no subcommand is specified on the command-line, scription
    will look for a Command with the same name as the script

  - Alias:  registers other names for Commands (e.g. delete / remove / kill)


functions

  - Main:  if the importing module's __name__ is __main__, call Run() (this
    allows for importing the script as a module)

  - Run:  unconditionally attempts to run the Script function (if any) and the
    Command found on the command-line

  Main() or Run() should be the last thing in the script


classes

  - Spec:  can be used when defining the command-line parameters (can also just
    use tuples)


helper functions/classes

  - abort: quits immediately by raising SystemExit

  - Execute:  class for executing other programs; uses subprocess.Popen by
    default, but if `pty=True` is specified then `pty.fork` will be used
    (handy for programs that only accept input from a pty)

  - get_response:  function for displaying text and getting feedback

  - help: quits immediately, but adds a reference to --help in the quit message

  - log_exception:  logs an exception with logging.logger

  - mail: rudimentary mail sender

  - OrmFile:  lightweight orm -- supports str, int, float, date, time,
    datetime, bool, and path (which defaults to str); custom data types can
    also be specified

  - print: wrapper around print that adds a 'verbose_level' keyword (default: 1);
    default verbosity is 0 (so print does nothing), but can be increased using
    -v, -vv, --verbose, or --verbose=2 (in Python 2 the script must use
    'from __future__ import print_function' to use scription's print)

  - user_ids:  context manager useful for suid scripts -- all actions taken
    within the context are run as the user/group specified


features

  - extra parameters defined by Script are global, and can be accessed from any
    function or Command

  - 'module' is a namespace inserted into the script

  - 'script_command' is the Command selected from the command line (useful when
    one needs to call the subcommand directly from a main() function)

  - 'script_command_name' is the name of the script_command

  - 'script_verbosity' is the level of verboseness selected (defaults to 0)

  - 'script_name' is the name of the script

  - builtin options are:  --help, --verbose (-v or -vv), --version, --all-versions
    --version attempts to display the version of the main package in use
    --all-versions attempts to display the versions of any imported packages

  - command-line is decoded to unicode under Python 2 (Python 3 does this for us)


[1] I use the suid-python program, available at http://selliott.org/python/suid-python.c
'''
py2_only = ()
py3_only = ()
make = []

data = dict(
        name='scription',
        version='0.86.15',
        license='BSD License',
        description='simple script parameter parser',
        long_description=description,
        url='https://github.com/ethanfurman/scription.git',
        install_requires=['aenum >= 3.1.0'],
        packages=['scription'],
        package_data={
             'scription': [
                 'CHANGES', 'LICENSE',
                 ],
             },
        author='Ethan Furman',
        author_email='ethan@stoneleaf.us',
        classifiers=[
             'Development Status :: 4 - Beta',
             'Intended Audience :: Developers',
             'Intended Audience :: End Users/Desktop',
             'Intended Audience :: System Administrators',
             'License :: OSI Approved :: BSD License',
             'Programming Language :: Python',
             'Topic :: System :: Shells',
             'Topic :: Utilities',
             'Programming Language :: Python :: 2.7',
             'Programming Language :: Python :: 3.3',
             'Programming Language :: Python :: 3.4',
             'Programming Language :: Python :: 3.5',
             'Programming Language :: Python :: 3.6',
             'Programming Language :: Python :: 3.7',
             'Programming Language :: Python :: 3.8',
             'Programming Language :: Python :: 3.9',
             'Programming Language :: Python :: 3.10',
             'Programming Language :: Python :: 3.11',
             ],
    )

if __name__ == '__main__':
    setup(**data)
