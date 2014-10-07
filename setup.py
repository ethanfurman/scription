from distutils.core import setup


long_desc="""\
Scription -- simple script parameter parser
===========================================


"""

setup( name='scription',
       version= '0.50.06',
       license='BSD License',
       description='simple script parameter parser',
       long_description=long_desc,
       py_modules=['scription'],
       provides=['scription'],
       author='Ethan Furman',
       author_email='ethan@stoneleaf.us',
       classifiers=[
            'Development Status :: 3 - Alpha',
            'Intended Audience :: Developers',
            'License :: OSI Approved :: BSD License',
            'Programming Language :: Python',
            'Topic :: Database',
            'Programming Language :: Python :: 2.4',
            'Programming Language :: Python :: 2.5',
            'Programming Language :: Python :: 2.6',
            'Programming Language :: Python :: 2.7',
            ],
    )

