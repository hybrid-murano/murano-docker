import functools


cache = {'package-def':{}, 'package':{}, 'class-package':{}, 'package-class': {}}
def memoized(group):
    def decorator(func):
        @functools.wraps(func)
        def wrapped(*args):
            key = ':'.join(str(arg) for arg in args[1:])
            try:
                value = cache[group][key]
            except KeyError:
                value = func(*args)
                cache[group][key] = value
                if(group == 'package'):
                    package = ':'.join([args[1], str(getattr(value, 'package_version', '0.0.0'))])
                    cache['package-def'][package] = cache['package-def'].get(package, [])
                    cache['package-def'][package].append(key)
            return value
        return wrapped
    return decorator

memoized_method = memoized

def memoized_del(package_id, package_fqn, package_version):
    key = ':'.join([package_fqn, package_version])
    if key in cache['package-def']:
        for p_key in cache['package-def'].get(key, []):
            del cache['package'][p_key]
        del cache['package-def'][key]
