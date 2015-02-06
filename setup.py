from distutils.core import setup

description = '''\
scription

light-weight library to enhance command-line scripts; includes conversion of
parameters to specified data types, parameter checking, basic input/output with
users, support for suid [1], sending email, executing sub-programs, and having
sub-commands within a script


decorators

  - Script:  sets global variables and/or parameters for Commands; when used as
    decorator, the decorated function will be called by Main/Run before any
    specified Command

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

  - Execute:  class for executing other programs; uses subprocess.Popen by
    default, but if `pty=True` is specified then `pty.fork` will be used
    (handy for programs that only accept input from a pty)

  - get_response:  function for displaying text and getting feedback

  - OrmFile:  lightweight orm -- supports str, int, float, date, time,
    datetime, bool, and path (which defaults to str); custom data types can
    also be specified

  - user_ids:  context manager useful for suid scripts -- all actions taken
    within the context are run as the user/group specified



[1] I use the suid-python program, available at http://selliott.org/python/suid-python.c
'''

setup( name='scription',
       version= '0.73.02',
       license='BSD License',
       description='simple script parameter parser',
       long_description=description,
       url='https://bitbucket.org/stoneleaf/scription',
       packages=['scription'],
       package_data={'scription':['CHANGES', 'LICENSE', 'README']},
       author='Ethan Furman',
       author_email='ethan@stoneleaf.us',
       classifiers=[
            'Development Status :: 4 - Beta',
            'Intended Audience :: Developers',
            'Intended Audience :: End Users/Desktop',
            'Intended Audience :: System Administrators',
            'License :: OSI Approved :: BSD License',
            'Programming Language :: Python',
            'Topic :: Database',
            'Programming Language :: Python :: 2.4',
            'Programming Language :: Python :: 2.5',
            'Programming Language :: Python :: 2.6',
            'Programming Language :: Python :: 2.7',
            'Programming Language :: Python :: 3',
            ],
    )

