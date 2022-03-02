"""Set operations

https://github.com/tidyverse/dplyr/blob/master/R/sets.r
"""

import pandas as pd
from pandas import DataFrame
from pipda import register_verb

from ..core.contexts import Context
from ..core.tibble import TibbleGrouped, reconstruct_tibble
from ..core.utils import regcall

from ..base.verbs import intersect, union, setdiff, setequal
from .bind import bind_rows


def _check_xy(x, y):
    """Check the dimension and columns of x and y for set operations"""
    if x.shape[1] != y.shape[1]:
        raise ValueError(
            "not compatible:\n"
            f"- different number of columns: {x.shape[1]} vs {y.shape[1]}"
        )

    in_y_not_x = regcall(setdiff, y.columns, x.columns)
    in_x_not_y = regcall(setdiff, x.columns, y.columns)
    if in_y_not_x or in_x_not_y:
        msg = ["not compatible:"]
        if in_y_not_x:
            msg.append(f"- Cols in `y` but not `x`: {in_y_not_x}.")
        if in_x_not_y:
            msg.append(f"- Cols in `x` but not `y`: {in_x_not_y}.")
        raise ValueError("\n".join(msg))


@intersect.register(DataFrame, context=Context.EVAL)
def _(x: DataFrame, y: DataFrame) -> DataFrame:
    """Intersect of two dataframes

    Args:
        _data, data2, *datas: Dataframes to perform operations
        on: The columns to the dataframes to perform operations on

    Returns:
        The dataframe of intersect of input dataframes
    """
    _check_xy(x, y)
    from .distinct import distinct

    return regcall(distinct, pd.merge(x, y, how="inner"))


@intersect.register(TibbleGrouped, context=Context.EVAL)
def _(x, y):
    out = intersect.dispatch(DataFrame)(x, y)
    return reconstruct_tibble(x, out)


@union.register(DataFrame, context=Context.EVAL)
def _(x, y):
    """Union of two dataframes

    Args:
        _data, data2, *datas: Dataframes to perform operations
        on: The columns to the dataframes to perform operations on

    Returns:
        The dataframe of union of input dataframes
    """
    _check_xy(x, y)
    from .distinct import distinct

    return regcall(distinct, pd.merge(x, y, how="outer"))


@union.register(TibbleGrouped, context=Context.EVAL)
def _(x, y):
    out = union.dispatch(DataFrame)(x, y)
    return reconstruct_tibble(x, out)


@setdiff.register(DataFrame, context=Context.EVAL)
def _(x, y):
    """Set diff of two dataframes

    Args:
        _data, *datas: Dataframes to perform operations
        on: The columns to the dataframes to perform operations on

    Returns:
        The dataframe of setdiff of input dataframes
    """
    _check_xy(x, y)
    indicator = "__datar_setdiff__"
    out = pd.merge(x, y, how="left", indicator=indicator)

    from .distinct import distinct

    return regcall(
        distinct,
        out[out[indicator] == "left_only"]
        .drop(columns=[indicator])
        .reset_index(drop=True),
    )


@setdiff.register(TibbleGrouped, context=Context.EVAL)
def _(x, y):
    out = setdiff.dispatch(DataFrame)(x, y)
    return reconstruct_tibble(x, out)


@register_verb(DataFrame, context=Context.EVAL)
def union_all(x, y):
    """Union of all rows of two dataframes

    Args:
        _data, *datas: Dataframes to perform operations
        on: The columns to the dataframes to perform operations on

    Returns:
        The dataframe of union of all rows of input dataframes
    """
    _check_xy(x, y)
    return regcall(bind_rows, x, y)


@union_all.register(TibbleGrouped, context=Context.EVAL)
def _(x, y):
    out = union_all.dispatch(DataFrame)(x, y)
    return reconstruct_tibble(x, out)


@setequal.register(DataFrame, context=Context.EVAL)
def _(x, y):
    """Check if two dataframes equal

    Args:
        _data: The first dataframe
        data2: The second dataframe

    Returns:
        True if they equal else False
    """
    _check_xy(x, y)

    x = x.sort_values(by=x.columns.to_list()).reset_index(drop=True)
    y = y.sort_values(by=y.columns.to_list()).reset_index(drop=True)
    return x.equals(y)
