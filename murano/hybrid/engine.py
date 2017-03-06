from murano.packages import package

def patch():
    package.PackageType.ALL + ['Environment', 'Schedule', 'Cloud', 'DRS']
