"""
This module defines the command-line interface arguments for the
``hutch-python`` script. It also provides utilities that are only used at
startup.
"""
from pathlib import Path
import argparse
import logging
import matplotlib.pyplot as plt
import os
import sys

from IPython.terminal.embed import InteractiveShellEmbed
from cookiecutter.main import cookiecutter
from pcdsdaq.sim import set_sim_mode as set_daq_sim

from .bug import BugMagics
from .constants import CONDA_BASE, DIR_MODULE
from .ipython_log import init_ipython_logger
from .load_conf import load
from .log_setup import (setup_logging, set_console_level, debug_mode,
                        debug_context, debug_wrapper)

logger = logging.getLogger(__name__)
opts_cache = {}

# Define the parser
parser = argparse.ArgumentParser(prog='hutch-python',
                                 description='Launch LCLS Hutch Python')
parser.add_argument('--cfg', required=False, default=None,
                    help='Configuration yaml file')
parser.add_argument('--debug', action='store_true', default=False,
                    help='Start in debug mode')
parser.add_argument('--sim', action='store_true', default=False,
                    help='Run with simulated DAQ')
parser.add_argument('--create', action='store', default=False,
                    help='Create a new hutch deployment')
parser.add_argument('script', nargs='?',
                    help='Run a script instead of running interactively')

# Append to module docs
__doc__ += '\n::\n\n    ' + parser.format_help().replace('\n', '\n    ')


def setup_cli_env():
    """
    Parse the user's arguments and gather the session's objects.

    Inlcudes objects defined by `load_conf.load` as well as debug methods
    from :mod:`log_setup`.

    Returns
    -------
    objs: ``dict``
        Mapping of object name ``str`` to object
    """
    # Parse the user's arguments
    args = parser.parse_args()

    # Make sure the hutch's directory is in the path
    sys.path.insert(0, os.getcwd())

    # Set up logging first
    if args.cfg is None:
        log_dir = None
    else:
        log_dir = os.path.join(os.path.dirname(args.cfg), 'logs')
    setup_logging(dir_logs=log_dir)

    # Debug mode next
    if args.debug:
        debug_mode(True)

    # Options that mean skipping the python environment
    if args.create:
        hutch = args.create
        envs_dir = CONDA_BASE / 'envs'
        if envs_dir.exists():
            # Pick most recent pcds release in our common env
            base = str(CONDA_BASE)
            path_obj = sorted(envs_dir.glob('pcds-*'))[-1]
            env = path_obj.name
        else:
            # Fallback: pick current env
            base = str(Path(os.environ['CONDA_EXE']).parent.parent)
            env = os.environ['CONDA_DEFAULT_ENV']
        logger.info(('Creating hutch-python dir for hutch %s using'
                     ' base=%s env=%s'), hutch, base, env)
        cookiecutter(str(DIR_MODULE / 'cookiecutter'), no_input=True,
                     extra_context=dict(base=base, env=env, hutch=hutch))
        return {}

    # Now other flags
    if args.sim:
        set_daq_sim(True)

    # Save whether we are an interactive session or a script session
    opts_cache['script'] = args.script

    # Load objects based on the configuration file
    objs = load(cfg=args.cfg)

    # Add cli debug tools
    objs['_debug_console_level'] = set_console_level
    objs['_debug_mode'] = debug_mode
    objs['_debug_context'] = debug_context
    objs['_debug_wrapper'] = debug_wrapper

    return objs


def hutch_ipython_embed(stack_offset=0):
    """
    Make a shell, customize it, then run it

    Parameters
    ----------
    stack_offset: int, optional
        Determines which scope to run ipython in.
        If you're embedding the terminal inside the current scope, leave this
        as zero. If you're embedding the terminal inside a scope that is n
        levels up the stack, set this to n.
    """
    logger.info('Starting IPython shell')
    stack_depth = 2 + stack_offset
    # 1 = whoever called this function
    # + 1 = 2 because this is used inside the shell call
    # + stack_offset for extra levels between this call and user space
    shell = InteractiveShellEmbed.instance()
    init_ipython_logger(shell)
    shell.enable_matplotlib()
    plt.ion()
    # Add our Bug Reporting Magic
    logger.debug('Registering bug_report magics')
    shell.register_magics(BugMagics)
    # Disable jedi completion, it's buggy
    shell.Completer.use_jedi = False
    shell(stack_depth=stack_depth)


def run_script(filename, stack_offset=0):
    """
    Basic shortcut to running a script in the current hutch python scope.

    Parameters
    ----------
    stack_offset: int, optional
        Determines which scope to run the script in.
        If you're running a script from the current scope, leave this as zero.
        If you're running a script from a scope that is n levels up the stack,
        set this to n.
    """
    logger.info('Running script %s', filename)
    stack_depth = 1 + stack_offset
    # 1 = whoever called this function
    # + stack_offset for extra levels between this call and user space
    frame = sys._getframe(stack_depth)
    with open(filename) as f:
        code = compile(f.read(), filename, 'exec')
        exec(code, frame.f_globals, frame.f_locals)


def start_user():
    """
    Picks `hutch_ipython_embed` or `run_script` based on the args.

    This is meant to be called directly in the ``hutch-python`` script.
    """
    script = opts_cache.get('script')
    if script is None:
        hutch_ipython_embed(stack_offset=1)
    else:
        run_script(script, stack_offset=1)
