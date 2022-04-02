from setuptools import setup, find_packages

with open('readme.md', encoding='utf-8') as f:
    long_description = f.read()

setup(
    packages = find_packages(),
    name = 'pbat',
    version = '0.0.10',
    author = "Stanislav Doronin",
    author_email = "mugisbrows@gmail.com",
    url = 'https://github.com/mugiseyebrows/pbat',
    description = 'Batch file preprocessor',
    long_description = long_description,
    long_description_content_type = 'text/markdown',
    install_requires = [],
    package_data = {
        'pbat': ['examples/*.pbat', 'examples/*.bat']
    },
    entry_points = {
        'console_scripts': [
            'pbat = pbat.compile:main',
            'pbat.compile = pbat.compile:main',
            'pbat.watch = pbat.watch:main'
        ]
    }
)