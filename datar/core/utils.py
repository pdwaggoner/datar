"""Core utilities"""
import sys
import logging
import inspect
from functools import singledispatch

import numpy as np
from pandas import DataFrame, Index, Series
from pandas.api.types import is_scalar
from pandas.core.groupby import SeriesGroupBy
from pipda.utils import CallingEnvs


# logger
logger = logging.getLogger("datar")
logger.setLevel(logging.INFO)
stream_handler = logging.StreamHandler(sys.stderr)
stream_handler.setFormatter(
    logging.Formatter(
        "[%(asctime)s][%(name)s][%(levelname)7s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
)
logger.addHandler(stream_handler)


@singledispatch
def name_of(value):
    return str(value)


@name_of.register(Series)
def _(value):
    return value.name


@name_of.register(SeriesGroupBy)
def _(value):
    return value.obj.name


@name_of.register(DataFrame)
def _(value):
    return None


def regcall(func, *args, **kwargs):
    """Call function with regular calling env"""
    return func(*args, **kwargs, __calling_env=CallingEnvs.REGULAR)


def ensure_nparray(x):
    if is_scalar(x):
        return np.array(x).ravel()

    if isinstance(x, dict):
        return np.array(list(x))

    if not isinstance(x, np.ndarray):
        return np.array(x)

    return x


def arg_match(arg, argname, values, errmsg=None):
    """Make sure arg is in one of the values.

    Mimics `rlang::arg_match`.
    """
    if not errmsg:
        values = list(values)
        errmsg = f"`{argname}` must be one of {values}."
    if arg not in values:
        raise ValueError(errmsg)
    return arg


def vars_select(
    all_columns,
    *columns,
    raise_nonexists=True,
):
    # TODO: support selecting data-frame columns
    """Select columns

    Args:
        all_columns: The column pool to select
        *columns: arguments to select from the pool
        raise_nonexist: Whether raise exception when column not exists
            in the pool

    Returns:
        The selected indexes for columns

    Raises:
        KeyError: When the column does not exist in the pool
            and raise_nonexists is True.
    """
    from .collections import Collection
    from ..base import unique

    if not isinstance(all_columns, Index):
        all_columns = Index(all_columns, dtype=object)

    columns = [
        column.name
        if isinstance(column, Series)
        else column.obj.name
        if isinstance(column, SeriesGroupBy)
        else column
        for column in columns
    ]
    for col in columns:
        if not isinstance(col, str):
            continue
        colidx = all_columns.get_indexer_for([col])
        if colidx.size > 1:
            raise ValueError(
                "Names must be unique. Name "
                f'"{col}" found at locations {list(colidx)}.'
            )

    selected = Collection(*columns, pool=list(all_columns))
    if raise_nonexists and selected.unmatched and selected.unmatched != {None}:
        raise KeyError(f"Columns `{selected.unmatched}` do not exist.")
    return regcall(unique, selected).astype(int)


def nargs(fun):
    """Get the number of arguments of a function"""
    return len(inspect.signature(fun).parameters)
