import os

from types import SimpleNamespace

def from_env(varname, default=None, coerce_to=None):
    val = os.environ.get(varname, default)
    if val is None:
        raise ValueError(f"No var '{varname}' defined in the environment.")
    if coerce_to:
        val = coerce_to(val)
    return val


def read_config(varnames, config_file=None):
    cfg = {tup[0]: None for tup in varnames}
    
    if config_file:
        with open(config_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            for line in lines:
                varname, val = line.split('=', 1)
                if varname.strip() in cfg:
                    cfg[varname.strip()] = val.strip()
    
    for var, default, coerce_type in varnames:
        defined = cfg.get(var)
        if defined is not None:
            cfg[var] = coerce_type(defined)
            continue

        val = from_env(var, default, coerce_type)
        if val is None:
            raise ValueError(f"No var '{var}' defined in config file "
                             f"{config_file} or in environment variables.")
        cfg[var] = val

    return SimpleNamespace(**cfg)
