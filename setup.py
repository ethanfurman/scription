from distutils.core import setup


long_desc="""\
Scription -- simple script parameter parser
===========================================
"""

setup( name='scription',
       version= '0.73.00',
       license='BSD License',
       description='simple script parameter parser',
       long_description=long_desc,
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

